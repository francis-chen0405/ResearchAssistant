"""Barrier-controlled service/configuration ordering; no real services or vault."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient

import frontend.api as api
import frontend.live_service as live
from frontend.live_contracts import LiveRunRequest, LiveRunSnapshot
from frontend.live_lifecycle import LifecycleConflict
from frontend.service_manager import ServiceDiagnostic
from providers.config import ExaConfig
from providers.llm import LLMRequest
from providers.v2_budget import V2RunCeilings, read_v2_physical_call_audit
from providers.v2_factory import V2ProductionFactoryConfig
from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
from researchassistant.platform_support.credential_store import (
    KeychainUnavailableError,
    ProviderCredentials,
)
from researchassistant.runtime.application_runtime import CLIExitCode
from researchassistant.storage.history_import import HistoryImportResult
from tests.test_live_resume_status import _InterruptedModel, _RunFixture
from tests.test_mlp3_api import FakeServices
from tests.test_query_production import _ConceptModel
from tests.test_v2_phase12_production import _routing, _Scraper, _Search, _V2Model


class _Pause:
    def __init__(self, parties: int = 2) -> None:
        self.barrier = Barrier(parties)
        self.release = Event()

    def block(self) -> None:
        self.barrier.wait(timeout=10)
        assert self.release.wait(10), "barrier operation was not released"

    def entered(self) -> None:
        self.barrier.wait(timeout=10)


class _Services(FakeServices):
    def __init__(self, controller: live.LiveResearchController) -> None:
        super().__init__()
        self.controller = controller
        self.stop_pause: _Pause | None = None
        self.start_pause: _Pause | None = None
        self.stopped_while_active: list[bool] = []
        self.fail_start = False

    def stop(self) -> ServiceDiagnostic:
        if self.stop_pause is not None:
            self.stop_pause.block()
        self.stopped_while_active.append(self.controller.has_active_runs())
        return super().stop()

    def start(self) -> ServiceDiagnostic:
        if self.start_pause is not None:
            self.start_pause.block()
        if self.fail_start:
            return ServiceDiagnostic(
                state="launch_failed",
                wigolo_ready=False,
                searxng_readiness="unavailable",
                message="Offline fixture launch failed.",
            )
        return super().start()


class _Harness:
    def __init__(self, folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.folder = folder
        self.factory = V2ProductionFactoryConfig(
            routing=_routing(),
            discovery_providers=(DiscoveryProvider.EXA,),
            exa=ExaConfig(api_key="offline-fixture"),
            research_controls=ResearchControls(discovery_providers=(DiscoveryProvider.EXA,)),
            ceilings=V2RunCeilings(max_total_cost_usd=Decimal("1")),
        )
        self.controller = live.LiveResearchController(environment={})
        self.services = _Services(self.controller)
        self.saved: list[ProviderCredentials] = []
        self.runtime = api.ApiRuntime(
            controller=self.controller,
            services=self.services,
            environment={},
            credential_saver=self.saved.append,
        )
        self.client = TestClient(
            api.create_app(self.runtime, load_keychain_on_start=False),
            base_url="http://127.0.0.1",
            raise_server_exceptions=False,
        )
        self.worker_pause = _Pause()
        self.workers: list[UUID] = []
        self.pool = ThreadPoolExecutor(max_workers=4)

        def factory(*args: object, **kwargs: object) -> V2ProductionFactoryConfig:
            return self.factory

        def worker(
            request: LiveRunRequest,
            run_id: UUID,
            factory_config: V2ProductionFactoryConfig,
            database_lock: live._DatabaseLock,
        ) -> LiveRunSnapshot:
            try:
                self.workers.append(run_id)
                self.worker_pause.block()
                return self.controller._early_snapshot(
                    request, run_id, "failed", CLIExitCode.FAILED, "Offline worker completed."
                )
            finally:
                database_lock.release()

        monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", factory)
        monkeypatch.setattr(live, "check_start_reservation", lambda *args: None)
        monkeypatch.setattr(self.controller, "_run", worker)

    def request(self, *, name: str = "run", run_id: UUID | None = None) -> LiveRunRequest:
        return LiveRunRequest(
            raw_claim="A public claim",
            db_path=str(self.folder / f"{name}.sqlite3"),
            run_id=run_id or uuid4(),
            research_controls=self.factory.research_controls,
            max_tokens=500_000,
            max_cost_usd=Decimal("1"),
        )

    def start(self, request: LiveRunRequest) -> httpx2.Response:
        return self.client.post(
            "/api/research/start",
            json={
                "raw_claim": request.raw_claim,
                "acknowledged_public": True,
                "db_path": request.db_path,
                "run_id": str(request.run_id),
                "max_cost_usd": "1",
                "use_serpsearch": False,
                "use_openalex": False,
            },
        )

    def complete(self, request: LiveRunRequest) -> None:
        assert request.run_id is not None
        key = (str(Path(request.db_path).resolve()), request.run_id)
        with self.controller._lock:
            future = self.controller._active[key].future
        self.worker_pause.release.set()
        future.result(timeout=10)
        self.controller._evict_completed_run(key, future)

    def close(self) -> None:
        self.worker_pause.release.set()
        for pause in (self.services.stop_pause, self.services.start_pause):
            if pause is not None:
                pause.release.set()
        self.pool.shutdown(wait=True)
        assert self.controller.shutdown(timeout=10)


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Harness]:
    instance = _Harness(tmp_path, monkeypatch)
    try:
        yield instance
    finally:
        instance.close()


def _mutation(
    harness: _Harness, operation: str, monkeypatch: pytest.MonkeyPatch, pause: _Pause | None
) -> Future[httpx2.Response]:
    def change(*args: object, **kwargs: object) -> None:
        if pause is not None:
            pause.block()

    def history(source: Path) -> HistoryImportResult:
        change()
        return HistoryImportResult(db_path=str(harness.folder / "copy.sqlite3"), run_count=0)

    if operation == "stop":
        harness.services.stop_pause = pause
        return harness.pool.submit(harness.client.post, "/api/service/stop")
    if operation == "save":
        harness.runtime.credential_saver = change
        return harness.pool.submit(
            harness.client.post, "/api/credentials", json={"mimo_api_key": "offline-key"}
        )
    if operation == "remove":
        monkeypatch.setattr(api, "remove_credential", change)
        return harness.pool.submit(harness.client.post, "/api/credentials/MIMO_API_KEY/remove")
    assert operation == "import"
    monkeypatch.setattr(api, "import_history", history)
    return harness.pool.submit(
        harness.client.post,
        "/api/history/import",
        params={"source": str(harness.folder / "source.sqlite3")},
    )


@pytest.mark.parametrize("operation", ("stop", "save", "remove", "import"))
def test_idle_change_finishes_before_admission(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    pause = _Pause()
    mutation = _mutation(harness, operation, monkeypatch, pause)
    try:
        pause.entered()
        request = harness.request()
        rejected = harness.start(request)
        assert rejected.status_code == 409
        assert "Retry shortly" in rejected.json()["detail"]
        with pytest.raises(LifecycleConflict):
            harness.controller.start(request)
        # The operation may spend arbitrary time in teardown/vault/SQLite; its
        # lifecycle mutex is available, and unrelated HTTP health remains responsive.
        assert harness.runtime.lifecycle._lock.acquire(blocking=False)
        harness.runtime.lifecycle._lock.release()
        assert harness.client.get("/api/health").status_code == 200
        assert not harness.workers
    finally:
        pause.release.set()
    assert mutation.result(timeout=10).status_code == 200
    admitted = harness.start(request)
    assert admitted.status_code == 200 and admitted.json()["started"]
    harness.worker_pause.entered()
    assert harness.client.post("/api/service/stop").status_code == 409
    harness.complete(request)
    assert harness.services.stopped_while_active == ([False] if operation == "stop" else [])


@pytest.mark.parametrize("operation", ("stop", "save", "remove", "import"))
@pytest.mark.parametrize("direct", (False, True))
def test_pending_admission_excludes_idle_change_before_registration(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, operation: str, direct: bool
) -> None:
    pause = _Pause()
    original_factory = V2ProductionFactoryConfig.from_environment

    def preflight(*args: object, **kwargs: object) -> V2ProductionFactoryConfig:
        pause.block()
        return harness.factory

    monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", preflight)
    request = harness.request()
    pending = harness.pool.submit(harness.controller.start if direct else harness.start, request)
    try:
        pause.entered()
        assert not harness.controller.has_active_runs()
        conflict = _mutation(harness, operation, monkeypatch, None).result(timeout=10)
        assert conflict.status_code == 409
        assert not harness.saved and not harness.services.stopped_while_active
    finally:
        pause.release.set()
    admitted = pending.result(timeout=10)
    monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", original_factory)
    if direct:
        assert admitted.started
    else:
        assert admitted.status_code == 200 and admitted.json()["started"]
    harness.worker_pause.entered()
    assert _mutation(harness, operation, monkeypatch, None).result(timeout=10).status_code == 409
    harness.complete(request)
    assert _mutation(harness, operation, monkeypatch, None).result(timeout=10).status_code == 200
    assert all(active is False for active in harness.services.stopped_while_active)


def test_duplicate_stop_does_not_repeat_teardown_and_recovers(harness: _Harness) -> None:
    pause = _Pause()
    harness.services.stop_pause = pause
    first = harness.pool.submit(harness.client.post, "/api/service/stop")
    try:
        pause.entered()
        assert harness.client.post("/api/service/stop").status_code == 409
        assert not harness.services.stopped_while_active
    finally:
        pause.release.set()
    assert first.result(timeout=10).status_code == 200
    harness.services.stop_pause = None
    assert harness.client.post("/api/service/stop").status_code == 200
    assert harness.services.stopped_while_active == [False, False]


def test_duplicate_admission_at_preflight_submits_one_worker(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause = _Pause(parties=3)

    def preflight(*args: object, **kwargs: object) -> V2ProductionFactoryConfig:
        pause.block()
        return harness.factory

    monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", preflight)
    request = harness.request()
    first = harness.pool.submit(harness.start, request)
    second = harness.pool.submit(harness.start, request)
    try:
        pause.entered()
        assert harness.client.post("/api/service/stop").status_code == 409
    finally:
        pause.release.set()
    responses = [first.result(timeout=10), second.result(timeout=10)]
    assert all(response.status_code == 200 for response in responses)
    assert sorted(response.json()["started"] for response in responses) == [False, True]
    assert {response.json()["classification"] for response in responses} == {
        "starting",
        "duplicate_active",
    }
    harness.worker_pause.entered()
    assert harness.workers == [request.run_id]
    harness.complete(request)


def test_separate_databases_remain_concurrent_and_service_start_available(
    harness: _Harness,
) -> None:
    harness.worker_pause = _Pause(parties=3)
    first, second = harness.request(name="first"), harness.request(name="second")
    assert harness.start(first).json()["started"]
    assert harness.start(second).json()["started"]
    harness.worker_pause.entered()
    assert set(harness.workers) == {first.run_id, second.run_id}
    for _ in range(2):
        assert harness.client.post("/api/service/start").status_code == 200
        assert harness.client.post("/api/service/stop").status_code == 409
    harness.complete(first)
    # The second future may already be complete; draining does not require the gate.
    assert harness.controller.shutdown(timeout=10)
    assert harness.client.post("/api/service/stop").status_code == 200
    assert harness.services.stopped_while_active == [False]


@pytest.mark.parametrize("fail", (False, True))
def test_service_start_in_flight_blocks_stop_and_releases_on_failure(
    harness: _Harness, fail: bool
) -> None:
    pause = _Pause()
    harness.services.start_pause = pause
    harness.services.fail_start = fail
    starting = harness.pool.submit(harness.client.post, "/api/service/start")
    try:
        pause.entered()
        assert harness.client.post("/api/service/stop").status_code == 409
        assert harness.runtime.lifecycle._lock.acquire(blocking=False)
        harness.runtime.lifecycle._lock.release()
    finally:
        pause.release.set()
    response = starting.result(timeout=10)
    assert response.status_code == 200
    assert response.json()["state"] == ("launch_failed" if fail else "healthy")
    assert harness.client.post("/api/service/stop").status_code == 200


@pytest.mark.parametrize("failure", ("configuration", "submit", "vault", "import", "stop"))
def test_failure_does_not_leave_lifecycle_reserved(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Offline failure")

    if failure == "configuration":
        monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", fail)
        response = harness.start(harness.request())
        assert response.status_code == 200
        assert response.json()["classification"] == "configuration_error"
    elif failure == "submit":
        monkeypatch.setattr(harness.controller._executor, "submit", fail)
        request = harness.request()
        assert harness.start(request).status_code == 500
        lock = live._DatabaseLock(Path(request.db_path))
        assert lock.acquire()
        lock.release()
    elif failure == "vault":

        def denied(credentials: ProviderCredentials) -> None:
            raise KeychainUnavailableError("Offline vault denied")

        harness.runtime.credential_saver = denied
        assert (
            harness.client.post(
                "/api/credentials", json={"mimo_api_key": "offline-key"}
            ).status_code
            == 503
        )
        assert not harness.runtime.environment
    elif failure == "import":
        monkeypatch.setattr(api, "import_history", fail)
        assert (
            harness.client.post(
                "/api/history/import", params={"source": "offline.sqlite3"}
            ).status_code
            == 500
        )
    else:
        original_stop = harness.services.stop
        monkeypatch.setattr(harness.services, "stop", fail)
        assert harness.client.post("/api/service/stop").status_code == 500
        monkeypatch.setattr(harness.services, "stop", original_stop)
    assert harness.runtime.lifecycle._admissions == 0
    assert harness.runtime.lifecycle._changing is False
    # Configuration/submission failures do not prevent idle operations.
    if failure != "stop":
        assert harness.client.post("/api/service/stop").status_code == 200


def test_completed_future_can_stop_before_callback_eviction(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    callback = _Pause()
    original = harness.controller._evict_completed_run

    def evict(key: tuple[str, UUID], future: Future[LiveRunSnapshot]) -> None:
        callback.block()
        original(key, future)

    monkeypatch.setattr(harness.controller, "_evict_completed_run", evict)
    request = harness.request()
    assert harness.start(request).json()["started"]
    harness.worker_pause.entered()
    harness.worker_pause.release.set()
    try:
        callback.entered()
        assert not harness.controller.has_active_runs()
        assert harness.client.post("/api/service/stop").status_code == 200
        assert harness.services.stopped_while_active == [False]
    finally:
        callback.release.set()


def test_run_finishing_as_stop_checks_ownership_allows_stop(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = harness.request()
    assert harness.start(request).json()["started"]
    harness.worker_pause.entered()
    check = _Pause()
    original = harness.controller.has_active_runs

    def finishing_check() -> bool:
        check.block()
        return original()

    monkeypatch.setattr(harness.controller, "has_active_runs", finishing_check)
    stopping = harness.pool.submit(harness.client.post, "/api/service/stop")
    try:
        check.entered()
        harness.complete(request)
    finally:
        check.release.set()
        monkeypatch.setattr(harness.controller, "has_active_runs", original)
    assert stopping.result(timeout=10).status_code == 200
    assert harness.services.stopped_while_active == [False]


def test_cancel_and_shutdown_keep_service_owned_and_unknown_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real controller/pipeline/audit, fake providers, interrupted physical call."""
    factory = V2ProductionFactoryConfig(
        routing=_routing(),
        discovery_providers=(DiscoveryProvider.EXA,),
        research_controls=ResearchControls(
            discovery_providers=(DiscoveryProvider.EXA,), metadata_depth=20
        ),
        exa=ExaConfig(api_key="offline-fixture"),
        ceilings=V2RunCeilings(
            max_physical_calls=40, max_total_tokens=100_000, max_total_cost_usd=Decimal("1")
        ),
    )
    fixture = _RunFixture(tmp_path / "runs.sqlite3", uuid4(), factory)
    with pytest.raises(KeyboardInterrupt):
        fixture.execute(_InterruptedModel())
    original_audit = read_v2_physical_call_audit(fixture.path, fixture.run_id)
    pause = _Pause()
    model, search, scraper = _V2Model(), _Search(), _Scraper()

    def configuration(*args: object, **kwargs: object) -> V2ProductionFactoryConfig:
        return factory

    def bundle(config: V2ProductionFactoryConfig) -> SimpleNamespace:
        pause.block()
        return SimpleNamespace(
            llm=model,
            search_providers={DiscoveryProvider.EXA: search},
            wigolo=scraper,
            firecrawl=None,
            crossref_resolver=None,
        )

    monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", configuration)
    monkeypatch.setattr(live, "build_v2_production_bundle", bundle)
    controller = live.LiveResearchController(environment={})
    services = _Services(controller)
    runtime = api.ApiRuntime(controller=controller, services=services, environment={})
    client = TestClient(
        api.create_app(runtime, load_keychain_on_start=False), base_url="http://127.0.0.1"
    )
    try:
        assert controller.start(fixture.request()).started
        pause.entered()
        assert controller.start(fixture.request()).classification == "duplicate_active"
        assert client.post("/api/service/stop").status_code == 409
        cancelled = client.post(
            f"/api/research/{fixture.run_id}/cancel", json={"db_path": str(fixture.path)}
        )
        assert cancelled.status_code == 200
        assert controller.shutdown(timeout=0) is False
        assert client.post("/api/service/stop").status_code == 409
        assert runtime.lifecycle._lock.acquire(blocking=False)
        runtime.lifecycle._lock.release()
        with controller._lock:
            future = controller._active[(str(fixture.path), fixture.run_id)].future
        pause.release.set()
        result = future.result(timeout=10)
        assert result.classification == "cancelled"
        assert client.post("/api/service/stop").status_code == 200
        assert model.requests == search.requests == scraper.requests == []
        assert read_v2_physical_call_audit(fixture.path, fixture.run_id) == original_audit
        assert original_audit.starts and original_audit.completions == (None,)
        assert services.stopped_while_active == [False]
    finally:
        pause.release.set()
        controller.shutdown(timeout=10)


def test_inflight_provider_call_does_not_hold_lifecycle_lock_or_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause = _Pause()

    class BlockingModel(_ConceptModel):
        def generate(self, request: LLMRequest) -> object:
            pause.block()
            return super().generate(request)

    factory = V2ProductionFactoryConfig(
        routing=_routing(),
        discovery_providers=(DiscoveryProvider.EXA,),
        research_controls=ResearchControls(
            discovery_providers=(DiscoveryProvider.EXA,), metadata_depth=20
        ),
        exa=ExaConfig(api_key="offline-fixture"),
        ceilings=V2RunCeilings(
            max_physical_calls=40, max_total_tokens=100_000, max_total_cost_usd=Decimal("1")
        ),
    )
    fixture = _RunFixture(tmp_path / "paid-boundary.sqlite3", uuid4(), factory)
    model, search, scraper = BlockingModel(), _Search(), _Scraper()

    def configuration(*args: object, **kwargs: object) -> V2ProductionFactoryConfig:
        return factory

    def bundle(config: V2ProductionFactoryConfig) -> SimpleNamespace:
        return SimpleNamespace(
            llm=model,
            search_providers={DiscoveryProvider.EXA: search},
            wigolo=scraper,
            firecrawl=None,
            crossref_resolver=None,
        )

    monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", configuration)
    monkeypatch.setattr(live, "build_v2_production_bundle", bundle)
    controller = live.LiveResearchController(environment={})
    services = _Services(controller)
    client = TestClient(
        api.create_app(
            api.ApiRuntime(controller=controller, services=services, environment={}),
            load_keychain_on_start=False,
        ),
        base_url="http://127.0.0.1",
    )
    try:
        assert controller.start(fixture.request()).started
        pause.entered()
        pending_audit = read_v2_physical_call_audit(fixture.path, fixture.run_id)
        assert len(pending_audit.starts) == 1
        assert pending_audit.completions == (None,)
        assert controller.lifecycle._lock.acquire(blocking=False)
        controller.lifecycle._lock.release()
        assert client.post("/api/service/stop").status_code == 409
        assert controller.start(fixture.request()).classification == "duplicate_active"
        controller.cancel(fixture.path, fixture.run_id)
        assert controller.shutdown(timeout=0) is False
        assert client.post("/api/service/stop").status_code == 409
        with controller._lock:
            future = controller._active[(str(fixture.path), fixture.run_id)].future
        pause.release.set()
        assert future.result(timeout=10).classification == "cancelled"
        assert client.post("/api/service/stop").status_code == 200
        finished_audit = read_v2_physical_call_audit(fixture.path, fixture.run_id)
        assert finished_audit.starts == pending_audit.starts
        assert finished_audit.completions[0] is not None
        assert len(model.requests) == 1
        assert search.requests == scraper.requests == []
        assert services.stopped_while_active == [False]
    finally:
        pause.release.set()
        controller.shutdown(timeout=10)
