from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from test_discovery_store import _init_run

from providers.composite_search import CompositeSearchProvider
from providers.config import OpenAlexConfig
from providers.openalex import OpenAlexSearchAdapter
from providers.search import (
    SearchFailureCode,
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
)
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2ProviderAttemptStart,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import ResearchDirection
from researchassistant.contracts.research_directions import ResearchDirections
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import execute_query, freeze_query_execution
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.store import RunManifest, RunStatus, Stage, init_db, insert_run

NOW = datetime(2026, 10, 7, tzinfo=UTC)
CLAIM = "The intervention changes the outcome."
DIRECTIONS = ResearchDirections(support_enabled=True, challenge_enabled=False)


class _Adapter:
    def __init__(self) -> None:
        self.calls: list[SearchRequest] = []

    def search(self, request: SearchRequest) -> SearchResponse:
        self.calls.append(request)
        return SearchResponse(results=[])


def _clock() -> datetime:
    return NOW


class _VirtualClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.now += duration


def _semantic_action(run_id: UUID, term: str) -> V2CompiledQueryAction:
    identity = f"semantic-{term.replace(' ', '-')}"
    conceptual = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", identity),
        identity_key=identity,
        required_concepts=(V2ConceptGroup(concept=term),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        round_number=1,
    )
    return compile_query(conceptual, mode="semantic", requested_depth=4)


def _oa_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "meta": {"cost_usd": "0.001"},
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "title": "A study",
                    "is_retracted": False,
                }
            ],
        },
    )


def _semantic_run(path: Path) -> UUID:
    run_id = uuid4()
    _init_run(path, run_id)
    binding = freeze_query_execution(
        str(path),
        run_id,
        CLAIM,
        DIRECTIONS,
        (DiscoveryProvider.OPENALEX,),
        _clock,
        query_modes={DiscoveryProvider.OPENALEX: "semantic"},
    )
    assert binding.compiler_identity == "source-query-compiler-v3"
    return run_id


def _execute_semantic(
    path: Path,
    run_id: UUID,
    action: V2CompiledQueryAction,
    adapter: SearchProvider,
    *,
    cancellation_requested: Callable[[], bool] | None = None,
) -> SearchResponse:
    return execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.OPENALEX,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.OPENALEX: adapter},
        clock=_clock,
        cancellation_requested=cancellation_requested,
    )


def test_fresh_compiler_binding_rejects_uncompiled_execution(tmp_path: Path) -> None:
    path = tmp_path / "fresh-binding.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    binding = freeze_query_execution(
        str(path),
        run_id,
        CLAIM,
        DIRECTIONS,
        (DiscoveryProvider.EXA,),
        _clock,
    )
    assert binding.compiler_identity == "source-query-compiler-v3"
    adapter = _Adapter()

    with pytest.raises(SearchProviderError) as exc_info:
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.EXA,
            query_text="legacy text",
            compiled_query=None,
            providers={DiscoveryProvider.EXA: adapter},
            clock=_clock,
        )
    assert exc_info.value.code is SearchFailureCode.PERMANENT_FAILURE
    assert "compiled-query runs require an application-owned compiled action" in str(exc_info.value)

    assert adapter.calls == []


def test_unbound_legacy_execution_keeps_historical_adapter_path(tmp_path: Path) -> None:
    path = tmp_path / "legacy-run.sqlite"
    init_db(str(path))
    run_id = uuid4()
    insert_run(
        str(path),
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim=CLAIM,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    adapter = _Adapter()

    result = execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.EXA,
        query_text="legacy text",
        compiled_query=None,
        providers={DiscoveryProvider.EXA: adapter},
        clock=_clock,
    )

    assert result.results == []
    assert len(adapter.calls) == 1
    assert adapter.calls[0].compiled_query is None


def test_composite_openalex_semantic_sends_are_spaced_by_one_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "semantic-spacing.sqlite"
    run_id = _semantic_run(path)
    virtual = _VirtualClock()
    sent_at: list[float] = []
    reservation_delays = iter((0.4, 0.1))
    from researchassistant.research import query_execution

    reserve_provider_attempt = query_execution.reserve_provider_attempt

    def delayed_reservation(db_path: str, start: V2ProviderAttemptStart) -> V2ProviderAttemptStart:
        virtual.sleep(next(reservation_delays))
        return reserve_provider_attempt(db_path, start)

    monkeypatch.setattr(query_execution, "reserve_provider_attempt", delayed_reservation)

    def handler(request: httpx.Request) -> httpx.Response:
        sent_at.append(virtual.monotonic())
        return _oa_response()

    openalex = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="key"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
        monotonic=virtual.monotonic,
        sleep=virtual.sleep,
    )
    composite = CompositeSearchProvider(openalex=openalex)

    _execute_semantic(path, run_id, _semantic_action(run_id, "first intervention"), composite)
    _execute_semantic(path, run_id, _semantic_action(run_id, "second intervention"), composite)

    assert sent_at[0] == 0.4
    assert sent_at[1] - sent_at[0] >= 1.0
    assert virtual.sleeps


def test_cancelling_while_openalex_semantic_waits_creates_no_attempt(tmp_path: Path) -> None:
    path = tmp_path / "semantic-cancel.sqlite"
    run_id = _semantic_run(path)
    virtual = _VirtualClock()
    sent_at: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_at.append(virtual.monotonic())
        return _oa_response()

    openalex = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="key"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
        monotonic=virtual.monotonic,
        sleep=virtual.sleep,
    )
    composite = CompositeSearchProvider(openalex=openalex)
    _execute_semantic(path, run_id, _semantic_action(run_id, "first intervention"), composite)

    with pytest.raises(SearchProviderError) as exc_info:
        _execute_semantic(
            path,
            run_id,
            _semantic_action(run_id, "second intervention"),
            composite,
            cancellation_requested=lambda: virtual.monotonic() >= 0.3,
        )

    assert exc_info.value.code is SearchFailureCode.CANCELLED
    assert sent_at == [0.0]
    assert len(virtual.sleeps) == 3
    assert len(provider_attempt_audit(str(path), run_id).starts) == 1


def test_openalex_semantic_retry_is_also_rate_limited(tmp_path: Path) -> None:
    path = tmp_path / "semantic-retry-spacing.sqlite"
    run_id = _semantic_run(path)
    virtual = _VirtualClock()
    sent_at: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_at.append(virtual.monotonic())
        if len(sent_at) == 1:
            return httpx.Response(429, json={"meta": {"cost_usd": "0.001"}})
        return _oa_response()

    openalex = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="key"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
        monotonic=virtual.monotonic,
        sleep=virtual.sleep,
    )
    composite = CompositeSearchProvider(openalex=openalex)

    _execute_semantic(path, run_id, _semantic_action(run_id, "retry intervention"), composite)

    assert sent_at[0] == 0.0
    assert sent_at[1] - sent_at[0] >= 1.0
    assert len(provider_attempt_audit(str(path), run_id).starts) == 2
