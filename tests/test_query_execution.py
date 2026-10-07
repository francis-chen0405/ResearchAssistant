from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from test_discovery_store import _init_run

from agents.v2_adaptive_search import _execute_searches
from providers.arxiv import ArxivSearchAdapter
from providers.config import ArxivConfig, OpenAlexConfig, PubMedConfig
from providers.discovery_transport import physical_request
from providers.openalex import OpenAlexSearchAdapter
from providers.pubmed import PubMedSearchAdapter
from providers.search import SearchFailureCode, SearchProviderError
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2DiscoveryBinding,
    V2DiscoveryOperation,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    ResearchDirection,
    ResearchDirections,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchQuery,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2GapBudgetState,
    V2GapSearchDirection,
    V2MaterialGap,
    V2RoundOneSearchQuery,
)
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import execute_query, freeze_query_execution
from researchassistant.research.v2_orchestrator import _run_round_one_search
from researchassistant.storage.discovery_store import (
    compute_discovery_audit_counters,
    provider_attempt_audit,
    read_discovery_artifacts,
    read_discovery_binding,
)
from researchassistant.storage.store import insert_v2_artifact

NOW = datetime(2026, 10, 6, tzinfo=UTC)
CLAIM = "The intervention changes the outcome."
DIRECTIONS = ResearchDirections(support_enabled=True, challenge_enabled=False)


def _clock() -> Callable[[], datetime]:
    tick = 0

    def now() -> datetime:
        nonlocal tick
        value = NOW + timedelta(seconds=tick)
        tick += 1
        return value

    return now


def _freeze(
    path: Path,
    provider: DiscoveryProvider,
    *,
    mode: str | None = None,
    run_id: UUID | None = None,
) -> tuple[UUID, V2DiscoveryBinding]:
    run_id = run_id or uuid4()
    _init_run(path, run_id)
    modes = {provider: mode} if mode else None
    binding = freeze_query_execution(
        str(path), run_id, CLAIM, DIRECTIONS, (provider,), _clock(), query_modes=modes
    )
    return run_id, binding


def _action(
    run_id: UUID,
    provider: DiscoveryProvider,
    *,
    mode: str | None = None,
    term: str = "community health",
    round_number: int = 1,
    target_gap_ids: tuple[str, ...] = (),
    purpose: str = "broad",
) -> V2CompiledQueryAction:
    identity = f"concept-{uuid4().hex}"
    query = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", identity),
        identity_key=identity,
        required_concepts=(V2ConceptGroup(concept=term),),
        purpose=purpose,
        direction=ResearchDirection.SUPPORT,
        provider=provider,
        round_number=round_number,
        target_gap_ids=target_gap_ids,
    )
    return compile_query(query, mode=mode)


def _round_one_query(
    action: V2CompiledQueryAction, *, run_id: UUID | None = None
) -> V2RoundOneSearchQuery:
    return V2RoundOneSearchQuery(
        run_id=run_id or action.run_id,
        query_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        provider=action.conceptual_query.provider,
        strategy="broad",
        query_text=action.query_text,
        compiled_query=action,
        created_at=NOW,
    )


def _persist_round_one_gap(path: Path, run_id: UUID) -> None:
    gap = V2MaterialGap(
        gap_id="gap-1",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="Independent replication is missing.",
        rationale="The broad search did not locate independent replication.",
    )
    gap_direction = V2GapSearchDirection(
        gap_id=gap.gap_id,
        direction=gap.direction,
        missing_evidence=gap.missing_evidence,
        search_focus="independent replication study",
    )
    gap_input = V2GapAnalysisInput(
        run_id=run_id,
        exact_claim=CLAIM,
        directions=DIRECTIONS,
        attempted_queries=(),
        surviving_sources=(),
        probe_passages=(),
        source_families=(),
        discovered_terms=(),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=(),
        remaining_budget=V2GapBudgetState(model_calls_remaining=1),
    )
    gap_result = V2GapAnalysisResult(
        run_id=run_id,
        directions=DIRECTIONS,
        analyzed_at=NOW,
        coverage_summary="Independent replication remains unresolved.",
        material_gaps=(gap,),
        continue_research=True,
        new_search_directions=(gap_direction,),
        discovered_terms=("replication",),
    )
    output = V2GapAnalysisOutput(
        run_id=run_id,
        input=gap_input,
        state=V2GapAnalysisState.COMPLETED,
        result=gap_result,
        attempts=(),
        stop_adaptive_continuation=False,
        completed_at=NOW,
    )
    insert_v2_artifact(str(path), "phase-6-gap-analysis", output, NOW)


def _openalex_response() -> dict[str, object]:
    return {
        "meta": {"cost_usd": 0.001},
        "results": [
            {
                "id": "https://openalex.org/W1",
                "title": "Community health study",
                "is_retracted": False,
            }
        ],
    }


def test_round_one_uses_frozen_openalex_semantic_mode_and_durable_reservation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "round-one-openalex.sqlite"
    run_id, binding = _freeze(path, DiscoveryProvider.OPENALEX, mode="semantic")
    action = _action(run_id, DiscoveryProvider.OPENALEX, mode="semantic")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_openalex_response())

    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    result = _run_round_one_search(
        str(path),
        (_round_one_query(action),),
        {DiscoveryProvider.OPENALEX: adapter},
        None,
        _clock(),
    )

    assert result.outcomes[0].succeeded
    assert seen[0].url.params["search.semantic"] == action.query_text
    assert "search" not in seen[0].url.params
    assert seen[0].url.params["per_page"] == str(action.effective_depth)
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == len(audit.completions) == 1
    assert (
        audit.starts[0].reserved_cost_usd == binding.provider_budgets[0].reservation_per_request_usd
    )
    assert audit.completions[0].actual_cost_usd == audit.starts[0].reserved_cost_usd
    assert audit.starts[0].operation_id == action.artifact_id
    assert adapter._calls_by_run.get(run_id, 0) == 0
    assert run_id not in adapter._cost_by_run


def test_adaptive_search_uses_same_compiled_executor(tmp_path: Path) -> None:
    from agents.v2_adaptive_search import V2AdaptiveSearchResults

    path = tmp_path / "adaptive-arxiv.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.ARXIV)
    _persist_round_one_gap(path, run_id)
    action = _action(
        run_id,
        DiscoveryProvider.ARXIV,
        term="independent replication fairness",
        round_number=2,
        target_gap_ids=("gap-1",),
        purpose="gap",
    )
    query = V2AdaptiveSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        round_number=2,
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.ARXIV,
        targeted_gap_ids=("gap-1",),
        strategy="gap",
        query_text=action.query_text,
        compiled_query=action,
        created_at=NOW,
    )
    plan = V2AdaptiveRoundPlan(
        run_id=run_id,
        round_number=2,
        directions=DIRECTIONS,
        enabled_providers=(DiscoveryProvider.ARXIV,),
        targeted_gap_ids=("gap-1",),
        discovered_terms=(),
        searches=(query,),
        search_agent_prompt_version="test-concepts-v1",
        planned_at=NOW,
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            text=(
                '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                "<id>https://arxiv.org/abs/2401.00001</id><title>Fairness study</title>"
                "</entry></feed>"
            ),
        )

    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
        ),
    )
    result = _execute_searches(str(path), plan, {DiscoveryProvider.ARXIV: adapter}, None, _clock())

    assert isinstance(result, V2AdaptiveSearchResults)
    assert result.outcomes[0].succeeded
    assert seen[0].url.params["search_query"] == action.query_text
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == len(audit.completions) == 1
    assert audit.starts[0].operation_id == action.artifact_id


@pytest.mark.parametrize("mismatch", ["round", "gap"])
def test_adaptive_query_rejects_compiled_lane_mismatch_before_execution(
    tmp_path: Path, mismatch: str
) -> None:
    path = tmp_path / f"adaptive-mismatch-{mismatch}.sqlite"
    run_id = uuid4()
    _freeze(path, DiscoveryProvider.ARXIV, run_id=run_id)
    _persist_round_one_gap(path, run_id)
    wrong_action = _action(
        run_id,
        DiscoveryProvider.ARXIV,
        term="independent replication fairness",
        round_number=3 if mismatch == "round" else 2,
        target_gap_ids=("gap-other" if mismatch == "gap" else "gap-1",),
        purpose="gap",
    )

    with pytest.raises(ValueError, match="compiled query must preserve its application-owned lane"):
        V2AdaptiveSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            round_number=2,
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.ARXIV,
            targeted_gap_ids=("gap-1",),
            strategy="gap",
            query_text=wrong_action.query_text,
            compiled_query=wrong_action,
            created_at=NOW,
        )
    assert not any(
        isinstance(item, V2DiscoveryOperation)
        for item in read_discovery_artifacts(str(path), run_id)
    )


def test_pubmed_reserves_search_and_summary_as_separate_physical_attempts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pubmed.sqlite"
    run_id, binding = _freeze(path, DiscoveryProvider.PUBMED)
    action = _action(run_id, DiscoveryProvider.PUBMED, term="maternal health")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})
        return httpx.Response(
            200,
            json={"result": {"123": {"uid": "123", "title": "Maternal health study"}}},
        )

    adapter = PubMedSearchAdapter(
        PubMedConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov", transport=httpx.MockTransport(handler)
        ),
    )
    response = execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.PUBMED,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.PUBMED: adapter},
        clock=_clock(),
    )

    assert response.results
    assert [request.url.path.rsplit("/", 1)[-1] for request in seen] == [
        "esearch.fcgi",
        "esummary.fcgi",
    ]
    audit = provider_attempt_audit(str(path), run_id)
    primary, metadata = audit.starts
    assert all("api_key" in request.url.params for request in seen)
    assert all("api_key" not in {item.name for item in start.parameters} for start in audit.starts)
    assert [primary.request_kind, metadata.request_kind] == ["primary", "metadata"]
    assert metadata.parent_attempt_id == primary.artifact_id
    assert metadata.parent_response_hash == audit.completions[0].response_hash
    assert len(audit.starts) == len(audit.completions) == 2
    assert [item.metadata_records for item in audit.completions] == [1, 1]
    counters = compute_discovery_audit_counters(str(path), run_id)
    assert counters.http_requests == 2
    assert counters.logical_queries == 1
    assert counters.metadata_records == 2
    assert binding.capabilities[0].physical_requests_per_page == 2


def test_known_free_provider_failure_retries_but_records_both_attempts(tmp_path: Path) -> None:
    path = tmp_path / "known-failure.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.ARXIV)
    action = _action(run_id, DiscoveryProvider.ARXIV)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            text=(
                '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                "<id>https://arxiv.org/abs/2401.00001</id><title>Study</title>"
                "</entry></feed>"
            ),
        )

    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
        ),
    )
    response = execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.ARXIV,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.ARXIV: adapter},
        clock=_clock(),
    )

    assert response.results
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == len(audit.completions) == 2
    assert [item.status for item in audit.completions] == ["failed", "completed"]


def test_unknown_transport_failure_is_durably_exposed_and_operation_cannot_replay(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unknown-outcome.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.OPENALEX)
    action = _action(run_id, DiscoveryProvider.OPENALEX)
    sent = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise httpx.ReadTimeout("connection ended after request start")

    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SearchProviderError) as caught:
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.OPENALEX: adapter},
            clock=_clock(),
        )
    assert caught.value.code is SearchFailureCode.TIMEOUT
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == len(audit.completions) == 1
    assert audit.completions[0].status == "interrupted_unknown"
    assert audit.starts[0].reserved_cost_usd > 0
    assert audit.completions[0].actual_cost_usd is None
    with pytest.raises(SearchProviderError, match="unknown request outcome"):
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=(second := _action(run_id, DiscoveryProvider.OPENALEX)).query_text,
            compiled_query=second,
            providers={DiscoveryProvider.OPENALEX: adapter},
            clock=_clock(),
        )
    assert sent == 1


@pytest.mark.parametrize(
    ("status_code", "failure_code", "retryable", "durable_code"),
    [
        (302, SearchFailureCode.PERMANENT_FAILURE, False, "invalid_request"),
        (401, SearchFailureCode.AUTHENTICATION, False, "authentication"),
        (503, SearchFailureCode.TRANSIENT_OUTAGE, True, "connection"),
    ],
)
def test_openalex_non_success_status_is_typed_and_durably_failed(
    tmp_path: Path,
    status_code: int,
    failure_code: SearchFailureCode,
    retryable: bool,
    durable_code: str,
) -> None:
    path = tmp_path / f"openalex-status-{status_code}.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.OPENALEX)
    action = _action(run_id, DiscoveryProvider.OPENALEX)
    sent: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        sent.append(status_code)
        return httpx.Response(status_code, headers={"location": "https://example.org/"})

    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SearchProviderError) as caught:
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.OPENALEX: adapter},
            clock=_clock(),
        )

    assert caught.value.code is failure_code
    assert caught.value.retryable is retryable
    assert sent == [status_code]
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == len(audit.completions) == 1
    assert audit.completions[0].status == "failed"
    assert audit.completions[0].failure is not None
    assert audit.completions[0].failure.code == durable_code
    # OpenAlex is paid: without reported cost, a 503 cannot authorize another
    # physical attempt even though the surfaced provider error is retryable.
    assert audit.completions[0].failure.retryable is (retryable and status_code != 503)


def test_cancel_before_transport_leaves_no_provider_attempt(tmp_path: Path) -> None:
    path = tmp_path / "cancel-before-start.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.ARXIV)
    action = _action(run_id, DiscoveryProvider.ARXIV)
    sent = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        return httpx.Response(500)

    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SearchProviderError) as caught:
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.ARXIV,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.ARXIV: adapter},
            clock=_clock(),
            cancellation_requested=lambda: True,
        )
    assert caught.value.code is SearchFailureCode.CANCELLED
    assert sent == 0
    assert provider_attempt_audit(str(path), run_id).starts == ()


def test_openalex_run_request_ceiling_blocks_the_eleventh_physical_call(tmp_path: Path) -> None:
    path = tmp_path / "openalex-run-ceiling.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.OPENALEX)
    sent = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        return httpx.Response(200, json=_openalex_response())

    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    for _ in range(10):
        action = _action(run_id, DiscoveryProvider.OPENALEX)
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.OPENALEX: adapter},
            clock=_clock(),
        )
    final_action = _action(run_id, DiscoveryProvider.OPENALEX)
    with pytest.raises(SearchProviderError, match="provider request budget"):
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=final_action.query_text,
            compiled_query=final_action,
            providers={DiscoveryProvider.OPENALEX: adapter},
            clock=_clock(),
        )

    audit = provider_attempt_audit(str(path), run_id)
    assert sent == len(audit.starts) == len(audit.completions) == 10
    assert compute_discovery_audit_counters(str(path), run_id).http_requests == 10


def test_cancellation_between_pubmed_requests_preserves_primary_reservation(tmp_path: Path) -> None:
    path = tmp_path / "cancel-between-pubmed.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.PUBMED)
    action = _action(run_id, DiscoveryProvider.PUBMED)
    cancelled = False
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled
        seen.append(request.url.path)
        cancelled = True
        return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})

    adapter = PubMedSearchAdapter(
        PubMedConfig(),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SearchProviderError) as caught:
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.PUBMED,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.PUBMED: adapter},
            clock=_clock(),
            cancellation_requested=lambda: cancelled,
        )
    assert caught.value.code is SearchFailureCode.CANCELLED
    audit = provider_attempt_audit(str(path), run_id)
    assert seen == ["/entrez/eutils/esearch.fcgi"]
    assert len(audit.starts) == len(audit.completions) == 1
    assert audit.starts[0].request_kind == "primary"
    assert audit.completions[0].status == "completed"


@pytest.mark.parametrize("tamper", ["primary", "metadata", "parameter_type"])
def test_pubmed_physical_observer_rejects_malicious_adapter_parameters_before_http(
    tmp_path: Path, tamper: str
) -> None:
    path = tmp_path / f"pubmed-malicious-{tamper}.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.PUBMED)
    action = _action(run_id, DiscoveryProvider.PUBMED, term="maternal health")
    if tamper == "parameter_type":
        action = compile_query(action.conceptual_query, requested_depth=1)
    sent: list[str] = []

    class MaliciousAccountingAdapter:
        physical_accounting = True

        def search(self, request: object) -> object:
            from providers.search import SearchRequest

            assert isinstance(request, SearchRequest)
            primary = {item.name: item.value for item in action.parameters}
            if tamper != "metadata":
                altered = dict(primary)
                if tamper == "parameter_type":
                    altered["retmax"] = True
                else:
                    altered["term"] = str(altered["term"]) + "[mesh]"
                physical_request(
                    request,
                    altered,
                    lambda: sent.append("primary") or httpx.Response(200),
                )
            else:
                physical_request(
                    request,
                    primary,
                    lambda: (
                        sent.append("primary")
                        or httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})
                    ),
                )
                physical_request(
                    request,
                    {"db": "pubmed", "id": "999", "retmode": "json"},
                    lambda: (
                        sent.append("metadata")
                        or httpx.Response(200, json={"result": {"999": {"uid": "999"}}})
                    ),
                    request_kind="metadata",
                )
            raise AssertionError("tampered request unexpectedly passed the physical observer")

    with pytest.raises(SearchProviderError, match="physical parameters differ"):
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.PUBMED,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.PUBMED: MaliciousAccountingAdapter()},
            clock=_clock(),
        )

    assert sent == ([] if tamper != "metadata" else ["primary"])
    audit = provider_attempt_audit(str(path), run_id)
    assert [start.request_kind for start in audit.starts] == (
        [] if tamper != "metadata" else ["primary"]
    )
    assert [completion.status for completion in audit.completions] == (
        [] if tamper != "metadata" else ["completed"]
    )


def test_pubmed_invalid_identifier_list_stops_before_summary_request(tmp_path: Path) -> None:
    path = tmp_path / "pubmed-invalid-id.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.PUBMED)
    action = _action(run_id, DiscoveryProvider.PUBMED)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(
            200,
            json={"esearchresult": {"idlist": ["123", "not-an-id"]}},
        )

    adapter = PubMedSearchAdapter(
        PubMedConfig(),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SearchProviderError) as caught:
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.PUBMED,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.PUBMED: adapter},
            clock=_clock(),
        )

    assert caught.value.code is SearchFailureCode.MALFORMED_RESPONSE
    assert seen == ["esearch.fcgi"]
    audit = provider_attempt_audit(str(path), run_id)
    assert [start.request_kind for start in audit.starts] == ["primary"]
    assert [completion.status for completion in audit.completions] == ["completed"]
    assert audit.completions[0].metadata_records == 2


def test_missing_provider_configuration_starts_no_operation_or_attempt(tmp_path: Path) -> None:
    path = tmp_path / "missing-provider.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.ARXIV)
    action = _action(run_id, DiscoveryProvider.ARXIV)

    with pytest.raises(SearchProviderError) as caught:
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.ARXIV,
            query_text=action.query_text,
            compiled_query=action,
            providers={},
            clock=_clock(),
        )
    assert caught.value.code is SearchFailureCode.MISSING_CONFIGURATION
    assert provider_attempt_audit(str(path), run_id).starts == ()


def test_freeze_rejects_unsupported_or_unselected_modes_before_binding(tmp_path: Path) -> None:
    path = tmp_path / "invalid-modes.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)

    with pytest.raises(ValueError, match="unsupported search mode"):
        freeze_query_execution(
            str(path),
            run_id,
            CLAIM,
            DIRECTIONS,
            (DiscoveryProvider.PUBMED,),
            _clock(),
            query_modes={DiscoveryProvider.PUBMED: "semantic"},
        )
    with pytest.raises(ValueError, match="cannot enable an unselected provider"):
        freeze_query_execution(
            str(path),
            run_id,
            CLAIM,
            DIRECTIONS,
            (DiscoveryProvider.ARXIV,),
            _clock(),
            query_modes={DiscoveryProvider.OPENALEX: "semantic"},
        )


def test_frozen_mode_cannot_be_changed_by_a_compiled_operation(tmp_path: Path) -> None:
    path = tmp_path / "frozen-mode.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.OPENALEX, mode="lexical")
    semantic = _action(run_id, DiscoveryProvider.OPENALEX, mode="semantic")
    seen = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen += 1
        return httpx.Response(200, json=_openalex_response())

    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SearchProviderError, match="mode differs from frozen"):
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=semantic.query_text,
            compiled_query=semantic,
            providers={DiscoveryProvider.OPENALEX: adapter},
            clock=_clock(),
        )
    assert seen == 0
    assert read_discovery_binding(str(path), run_id).providers == (DiscoveryProvider.OPENALEX,)
    assert provider_attempt_audit(str(path), run_id).starts == ()
