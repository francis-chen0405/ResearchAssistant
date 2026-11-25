"""Offline demand, fairness, overload and cancellation checks with controlled time."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from threading import Event, Semaphore

import httpx
import pytest

from researchassistant.agents.capture_overlap import ControlledCaptureProvider
from researchassistant.providers.acquisition import (
    CaptureControls,
    WigoloAcquisitionAdapter,
    capture_controls,
)
from researchassistant.providers.config import WigoloConfig
from researchassistant.providers.dispatch_intent import clear_intent, commit_intent, defer_intent
from researchassistant.providers.llm import V2CancellationRequested
from researchassistant.providers.run_scheduler import (
    POLICY,
    RunScheduler,
    StageControl,
    explicit_overload_response,
    retry_after_delay,
)
from researchassistant.providers.scraper import ScrapeRequest, ScraperProviderError


@pytest.mark.parametrize("name", ("scout", "capture", "extraction", "analysis"))
def test_independent_demand_expansion_and_shrink(name: str) -> None:
    policy = getattr(POLICY, name)
    control = StageControl(policy)
    assert control.update(ready=0, running=0, now=0) == 0
    assert control.update(ready=1, running=0, now=0) == 1
    assert control.update(ready=2, running=0, now=0) == 2
    assert control.update(ready=2, running=policy.initial, now=1) == policy.initial
    assert (
        control.update(ready=2, running=policy.initial, now=policy.expansion_seconds)
        == policy.initial
    )
    assert (
        control.update(ready=2, running=policy.initial, now=1 + policy.expansion_seconds)
        == policy.initial + 1
    )
    # Each additional slot requires its own full interval of sustained demand.
    now = 2 + policy.expansion_seconds
    while control.limit < policy.maximum:
        before = control.limit
        control.update(ready=3, running=before, now=now)
        control.update(ready=3, running=before, now=now + policy.expansion_seconds)
        assert control.limit == before + 1
        now += policy.expansion_seconds + 1
    control.update(ready=0, running=1, now=now)
    control.update(ready=0, running=1, now=now + 29)
    assert control.limit == policy.maximum
    assert control.update(ready=0, running=1, now=now + 30) == 1
    assert control.limit == policy.initial


@pytest.mark.parametrize("name", ("scout", "capture", "extraction", "analysis"))
@pytest.mark.parametrize("lost", ("ready", "running", "capacity", "reservable", "downstream"))
def test_expansion_requires_continuous_eligible_backlog(name: str, lost: str) -> None:
    policy = getattr(POLICY, name)
    if lost == "downstream" and policy.downstream_threshold is None:
        return
    control = StageControl(policy)
    args = dict(ready=2, running=policy.initial, capacity=True, reservable=True, downstream=0)
    control.update(**args, now=0)
    interrupted = {
        **args,
        lost: {
            "ready": 1,
            "running": policy.initial - 1,
            "capacity": False,
            "reservable": False,
            "downstream": policy.downstream_threshold,
        }[lost],
    }
    control.update(**interrupted, now=policy.expansion_seconds - 1)
    control.update(**args, now=policy.expansion_seconds)
    assert control.limit == policy.initial
    control.update(**args, now=2 * policy.expansion_seconds - 1)
    assert control.limit == policy.initial
    control.update(**args, now=2 * policy.expansion_seconds)
    assert control.limit == policy.initial + 1


def _wait_for_waiters(scheduler: RunScheduler, count: int) -> None:
    with scheduler.condition:
        assert scheduler.condition.wait_for(lambda: len(scheduler.waiters) == count, timeout=3)


def test_ten_request_ceiling_decision_priority_and_stage_rotation() -> None:
    scheduler = RunScheduler()
    order: list[str] = []
    release = Event()

    def request(stage: str) -> None:
        with scheduler.model_slot(stage, "shared"):
            with scheduler.condition:
                order.append(stage)
                scheduler.condition.notify_all()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=5) as pool, ExitStack() as held:
        slots = [held.enter_context(scheduler.model_slot("scout", "shared")) for _ in range(10)]
        futures = []
        for i, stage in enumerate(
            ("analyst", "extractor", "analyst", "planner", "gap_analysis"), 1
        ):
            futures.append(pool.submit(request, stage))
            _wait_for_waiters(scheduler, i)
        assert scheduler.snapshot()["model_admitted"] == 10
        assert order == []
        assert scheduler.model_waiting("analyst") == 2
        assert scheduler.model_waiting("extractor") == 1
        assert scheduler.model_waiting("scout") == 0
        # Eight unstarted analyses plus two requests waiting for provider capacity
        # reach the Extraction backpressure threshold. Active sources alone do not.
        extraction = scheduler.stages["extraction"]
        assert extraction.update(ready=2, running=4, now=0, downstream=8) == 4
        assert (
            extraction.update(
                ready=2, running=4, now=7, downstream=8 + scheduler.model_waiting("analyst")
            )
            == 4
        )
        assert extraction.limit == 4
        for count, (expected, slot) in enumerate(
            zip(
                ("planner", "gap_analysis", "analyst", "extractor", "analyst"), slots, strict=False
            ),
            1,
        ):
            slot()
            with scheduler.condition:
                assert scheduler.condition.wait_for(
                    lambda count=count: len(order) == count, timeout=3
                )
                assert order[-1] == expected
                assert scheduler.model_running == 10
        release.set()
        for future in futures:
            future.result(3)
    assert scheduler.model_running == 0
    assert not scheduler.waiters


def test_cancelled_capacity_wait_consumes_no_deferred_intent_and_leaks_no_slots() -> None:
    scheduler = RunScheduler()
    written: list[str] = []

    class Deferred:
        defers_dispatch_intents = True

    def waiting() -> None:
        defer_intent(Deferred(), lambda: written.append("intent"))
        try:
            with scheduler.model_slot("analyst", "shared"):
                commit_intent()
        finally:
            clear_intent()

    with ThreadPoolExecutor(max_workers=1) as pool, ExitStack() as held:
        for _ in range(10):
            held.enter_context(scheduler.model_slot("scout", "shared"))
        future = pool.submit(waiting)
        _wait_for_waiters(scheduler, 1)
        scheduler.stop_admission()
        with pytest.raises(V2CancellationRequested):
            future.result(3)
        assert written == []
        assert scheduler.model_running == 10
        assert not scheduler.waiters
    assert scheduler.model_running == 0


def test_provider_cooldown_retry_after_and_successful_recovery() -> None:
    now = [0.0]
    scheduler = RunScheduler(clock=lambda: now[0])
    scheduler.overload("shared", retry_after=90)
    assert scheduler.provider("shared").limit == 5
    assert not scheduler.capacity_available("shared")
    assert scheduler.capacity_available("other")
    now[0] = 89
    scheduler.success("shared")
    assert scheduler.provider("shared").limit == 5
    now[0] = 90
    scheduler.success("shared")
    assert scheduler.capacity_available("shared")
    now[0] = 119
    scheduler.success("shared")
    assert scheduler.provider("shared").limit == 5
    now[0] = 120
    scheduler.success("shared")
    assert scheduler.provider("shared").limit == 6
    scheduler.failure("shared")
    now[0] = 150
    scheduler.success("shared")
    assert scheduler.provider("shared").limit == 6
    now[0] = 180
    scheduler.success("shared")
    assert scheduler.provider("shared").limit == 7


def test_capture_wait_parks_transport_and_cancellation_releases_service() -> None:
    scheduler = RunScheduler()
    now = [0.0]
    scheduler.clock = lambda: now[0]
    scheduler.provider("capture:primary", 6)
    scheduler.overload("capture:primary")
    parked = Event()

    def capture() -> None:
        assert scheduler.transport_slots.acquire()
        owns_transport = True

        def park() -> None:
            nonlocal owns_transport
            if owns_transport:
                scheduler.transport_slots.release()
                owns_transport = False
            parked.set()

        try:
            with scheduler.service_slot("capture:primary", park):
                pytest.fail("overloaded service must not dispatch")
        finally:
            if owns_transport:
                scheduler.transport_slots.release()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(capture)
        assert parked.wait(3)
        assert scheduler.transport_running == 0
        scheduler.stop_admission()
        with pytest.raises(V2CancellationRequested):
            future.result(3)
    assert scheduler.provider("capture:primary").limit == 3
    assert scheduler.provider("capture:primary").running == 0


def test_overload_classification_and_retry_after_parsing() -> None:
    assert explicit_overload_response(httpx.Response(429))
    assert explicit_overload_response(httpx.Response(529))
    assert explicit_overload_response(
        httpx.Response(503, json={"error": {"type": "overloaded_error"}})
    )
    assert not explicit_overload_response(httpx.Response(503, text="unavailable"))
    assert not explicit_overload_response(httpx.Response(403, text="blocked source"))
    assert retry_after_delay("45") == 45
    assert retry_after_delay("-1") == 0
    assert retry_after_delay("nan") is None
    assert retry_after_delay("invalid") is None


@pytest.mark.parametrize("status,explicit", [(429, True), (503, True), (503, False)])
def test_capture_service_overload_survives_verified_preflight_wrapping(
    status: int, explicit: bool
) -> None:
    def source(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html>Article</html>", headers={"content-type": "text/html"}
        )

    def service(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ra/network-policy":
            return httpx.Response(200, json={"identity": "ra-public-network-v1"})
        return httpx.Response(
            status,
            json={"error": {"type": "overloaded_error" if explicit else "upstream_failure"}},
            headers={"retry-after": "45"},
        )

    scheduler = RunScheduler(clock=lambda: 0)
    controls = CaptureControls(
        lambda _response: False,
        scheduler.transport_slots,
        Semaphore(1),
        scheduler.check_cancelled,
        lambda _waiting: None,
    )
    with (
        httpx.Client(transport=httpx.MockTransport(source)) as origin,
        httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(service)) as local,
        capture_controls(controls),
        controls.transport_slot(),
    ):
        adapter = WigoloAcquisitionAdapter(
            WigoloConfig(),
            source_client=origin,
            wigolo_client=local,
            host_resolver=lambda _host: ("93.184.216.34",),
        )
        controlled = ControlledCaptureProvider(adapter, controls, scheduler, "capture:primary")
        with pytest.raises(ScraperProviderError) as failure:
            controlled.scrape(
                ScrapeRequest(url="https://article.example/study", timeout_seconds=10)
            )
        assert failure.value.verified_preflight is not None
        assert failure.value.capacity_overload is explicit
        assert failure.value.retry_after_seconds == (45 if explicit else None)
        assert scheduler.provider("capture:primary").limit == (3 if explicit else 6)
        assert scheduler.provider("capture:primary").blocked_until == (45 if explicit else 0)
    assert scheduler.transport_running == 0
