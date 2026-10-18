"""Real HTTPX/httpcore reads share one request deadline and conservative audit."""

from __future__ import annotations

import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Barrier, local
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from test_model_cache_pricing import _config, _request
from test_public_source_transport import WireSocket
from test_v2_phase7_adaptive_search import _db

from researchassistant.contracts.models import DiscoveryProvider
from researchassistant.providers import acquisition, bounded_network, mimo
from researchassistant.providers.acquisition import WigoloAcquisitionAdapter
from researchassistant.providers.bounded_network import DeadlineHTTPTransport
from researchassistant.providers.config import WigoloConfig
from researchassistant.providers.llm import LLMStage
from researchassistant.providers.mimo import MimoFailureCode, MimoProviderError, XiaomiMimoAdapter
from researchassistant.providers.model_choices import ModelChoice, StageModelSelections
from researchassistant.providers.scraper import ScrapeRequest, ScraperTimeoutError
from researchassistant.providers.v2_budget import (
    BudgetedV2LLMProvider,
    V2RunCeilings,
    read_v2_physical_call_audit,
)
from researchassistant.providers.v2_factory import V2ProductionFactoryConfig


@dataclass
class Clock:
    elapsed: float = 0.0
    budgets: list[float] = field(default_factory=list)

    def now(self) -> float:
        return self.elapsed


class SlowWire(WireSocket):
    def __init__(self, clock: Clock, *, header_delay: float = 0.0, redirect: bool = False) -> None:
        super().__init__()
        self.clock = clock
        self.timeout: float | None = None
        self.header_delay = header_delay
        self.headers_pending = True
        self.body = b"Public text."
        self.redirect = redirect

    def settimeout(self, timeout: float | None) -> None:
        self.timeout = timeout

    def recv(self, count: int) -> bytes:
        assert self.timeout is not None
        self.clock.budgets.append(self.timeout)
        delay = self.header_delay if self.headers_pending else 0.005
        if delay >= self.timeout:
            self.clock.elapsed += self.timeout
            raise TimeoutError("generated socket exhausted its remaining budget")
        self.clock.elapsed += delay
        if self.headers_pending:
            self.headers_pending = False
            if self.redirect:
                return b"HTTP/1.1 302 Found\r\nLocation: /next\r\nContent-Length: 0\r\n\r\n"
            return b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 12\r\n\r\n"
        chunk, self.body = self.body[:1], self.body[1:]
        return chunk


@pytest.mark.parametrize("phase", ["headers", "body", "redirect"])
def test_source_preflight_owns_one_budget_across_reads_and_redirects(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    clock = Clock()
    wires = (
        [SlowWire(clock, header_delay=0.015, redirect=True), SlowWire(clock, header_delay=0.015)]
        if phase == "redirect"
        else [SlowWire(clock, header_delay=0.03 if phase == "headers" else 0)]
    )
    pending = iter(wires)
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: next(pending))
    monkeypatch.setattr(acquisition, "monotonic", clock.now)
    adapter = WigoloAcquisitionAdapter(WigoloConfig(), host_resolver=lambda _: ("93.184.216.34",))
    try:
        with pytest.raises(ScraperTimeoutError) as error:
            adapter._preflight(
                ScrapeRequest(url="http://source.example/article", timeout_seconds=0.02)
            )
        assert error.value.code == "timeout" and error.value.retryable
        assert clock.elapsed == pytest.approx(0.02)
        assert all(wire.closed for wire in wires)
        assert max(clock.budgets) <= 0.02
        if phase == "redirect":
            assert b"GET /next" in wires[1].sent
            assert clock.budgets[-1] == pytest.approx(0.005)
    finally:
        adapter._source_client.close()
        adapter._wigolo_client.close()


def test_source_canonical_check_uses_the_preflight_remaining_dns_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    budgets: list[float | None] = []

    def resolve(hostname: str, *, timeout: float | None = None) -> tuple[str, ...]:
        budgets.append(timeout)
        if hostname == "canonical.example":
            raise TimeoutError("generated stalled canonical resolver")
        return ("93.184.216.34",)

    def response(request: httpx.Request) -> httpx.Response:
        clock.elapsed = 0.015
        return httpx.Response(
            200,
            headers={
                "content-type": "text/plain",
                "link": '<http://canonical.example/>; rel="canonical"',
            },
            content=b"Generated source.",
        )

    monkeypatch.setattr(acquisition, "monotonic", clock.now)
    monkeypatch.setattr(acquisition, "resolve_host_addresses", resolve)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        adapter = WigoloAcquisitionAdapter(WigoloConfig(), source_client=client)
        try:
            with pytest.raises(ScraperTimeoutError, match="hostname resolution timed out"):
                adapter._preflight(
                    ScrapeRequest(url="http://source.example/", timeout_seconds=0.02)
                )
            assert budgets == [0.02, pytest.approx(0.005)]
        finally:
            adapter._wigolo_client.close()


@pytest.mark.parametrize("stage", [LLMStage.SCOUT, LLMStage.GAP_ANALYSIS])
@pytest.mark.parametrize("phase", ["headers", "body"])
@pytest.mark.parametrize("fresh", [False, True])
def test_model_transport_timeout_preserves_unknown_physical_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: LLMStage, phase: str, fresh: bool
) -> None:
    config = (
        V2ProductionFactoryConfig.from_environment(
            {
                "MIMO_API_KEY": "offline-mimo",
                "LUNA_API_KEY": "offline-luna",
                "EXA_API_KEY": "offline-exa",
            },
            repository_revision="deadline-regression",
            discovery_providers=(DiscoveryProvider.EXA,),
            stage_models=StageModelSelections(scout=ModelChoice.MIMO_V26_PRO),
        )
        if fresh
        else _config()
    )
    route = config.routing.preflight().for_stage(stage)
    selected = (
        config.routing.configuration_for_stage(stage).config
        if fresh
        else config.routing.mimo_v25
        if stage is LLMStage.SCOUT
        else config.routing.luna
    )
    assert selected is not None
    deadline_config = selected.deadlines.model_copy(update={f"{stage.value}_seconds": 0.02})
    model_config = selected.model_copy(update={"deadlines": deadline_config})
    clock = Clock()
    wire = SlowWire(clock, header_delay=0.03 if phase == "headers" else 0)
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: wire)
    monkeypatch.setattr(
        bounded_network, "resolve_host_addresses", lambda host, **kwargs: ("93.184.216.34",)
    )
    monkeypatch.setattr(mimo, "time", SimpleNamespace(monotonic=clock.now))
    run_id = uuid4()
    database = _db(tmp_path, run_id)
    with httpx.Client(base_url="http://api.example", transport=DeadlineHTTPTransport()) as client:
        adapter = XiaomiMimoAdapter(
            model_config,
            client=client,
            price_cap=route.price_cap,
            expected_model_alias=route.logical_alias,
        )
        budget = BudgetedV2LLMProvider(
            db_path=database,
            run_id=run_id,
            provider=adapter,
            routing_config=config.routing,
            ceilings=V2RunCeilings(),
        )
        with pytest.raises(MimoProviderError) as error:
            budget.generate(
                _request(stage, run_id).model_copy(update={"model_alias": route.logical_alias})
            )
        assert error.value.code is MimoFailureCode.TIMEOUT
        assert adapter.failure_usage_for() is None
        assert clock.elapsed == pytest.approx(0.02)
        assert wire.closed and wire.sent.count(b"POST /chat/completions ") == 1
        audit = read_v2_physical_call_audit(database, run_id)
        assert len(audit.starts) == len(audit.completions) == 1
        completion = audit.completions[0]
        assert completion is not None
        assert completion.usage_tokens is completion.usage_cost_usd is None
        snapshot = budget.snapshot()
        assert snapshot.physical_calls_used == 1
        assert snapshot.token_exposure == audit.starts[0].reserved_tokens
        assert snapshot.cost_exposure_usd == audit.starts[0].reserved_cost_usd
        restarted = BudgetedV2LLMProvider(
            db_path=database,
            run_id=run_id,
            provider=adapter,
            routing_config=config.routing,
            ceilings=V2RunCeilings(),
        )
        assert restarted.snapshot() == snapshot


def test_model_adapter_concurrent_requests_have_independent_absolute_deadlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = local()
    barrier = Barrier(2)
    route_config = _config().routing
    selected = route_config.mimo_v25
    assert selected is not None
    selected = selected.model_copy(
        update={"deadlines": selected.deadlines.model_copy(update={"scout_seconds": 0.02})}
    )
    route = route_config.preflight().for_stage(LLMStage.SCOUT)

    def now() -> float:
        return state.clock.elapsed

    class ConcurrentWire(SlowWire):
        def recv(self, count: int) -> bytes:
            if self.headers_pending:
                barrier.wait(timeout=5)
            return super().recv(count)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: ConcurrentWire(state.clock))
    monkeypatch.setattr(
        bounded_network, "resolve_host_addresses", lambda host, **kwargs: ("93.184.216.34",)
    )
    monkeypatch.setattr(mimo, "time", SimpleNamespace(monotonic=now))
    with httpx.Client(base_url="http://api.example", transport=DeadlineHTTPTransport()) as client:
        adapter = XiaomiMimoAdapter(
            selected,
            client=client,
            price_cap=route.price_cap,
            expected_model_alias=route.logical_alias,
        )

        def attempt(offset: float) -> float:
            state.clock = Clock(elapsed=offset)
            with pytest.raises(MimoProviderError) as error:
                adapter.generate(_request(LLMStage.SCOUT, uuid4()))
            assert error.value.code is MimoFailureCode.TIMEOUT
            assert adapter.failure_usage_for() is None
            return state.clock.elapsed - offset

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt, offset) for offset in (0.0, 1.0)]
            assert [future.result(timeout=10) for future in futures] == [pytest.approx(0.02)] * 2


def test_provider_dns_and_numeric_fallback_share_one_deadline_and_original_tls_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    timeouts: list[float | None] = []
    wires: list[WireSocket] = []
    sni: list[str] = []

    def resolve(host: str, *, timeout: float | None = None) -> tuple[str, ...]:
        assert host == "api.example"
        timeouts.append(timeout)
        clock.elapsed += 0.005
        return ("93.184.216.34", "93.184.216.35")

    class ConnectingWire(WireSocket):
        def settimeout(self, timeout: float | None) -> None:
            timeouts.append(timeout)

        def connect(self, destination: tuple[str, int]) -> None:
            super().connect(destination)
            if destination[0] == "93.184.216.34":
                clock.elapsed += 0.005
                raise OSError("generated failed first address")

    def make_socket(*args: object, **kwargs: object) -> WireSocket:
        wire = ConnectingWire()
        wires.append(wire)
        return wire

    def wrap(context: ssl.SSLContext, wire: WireSocket, *, server_hostname: str) -> WireSocket:
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        sni.append(server_hostname)
        return wire

    def forbidden_lookup(*args: object, **kwargs: object) -> None:
        raise AssertionError("numeric connect must not perform another hostname lookup")

    monkeypatch.setattr(bounded_network, "resolve_host_addresses", resolve)
    monkeypatch.setattr(socket, "socket", make_socket)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden_lookup)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap)
    with httpx.Client(transport=DeadlineHTTPTransport()) as client:
        with bounded_network.network_deadline(clock.now, 0.02):
            response = client.get("https://api.example/study", timeout=0.02)
        assert response.text == "Public text."
    assert wires[0].closed and wires[1].closed
    assert wires[1].destination == ("93.184.216.35", 443)
    assert b"Host: api.example" in wires[1].sent
    assert sni == ["api.example"]
    assert timeouts[:3] == [0.02, pytest.approx(0.015), pytest.approx(0.01)]
