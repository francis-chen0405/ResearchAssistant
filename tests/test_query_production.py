from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import test_v2_phase12_production as phase12

from agents.v2_evidence_admission import V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
from agents.v2_round_four import V2_POST13_ROUND_FOUR_GOVERNOR_KEY
from providers.llm import LLMRequest
from providers.v2_budget import V2RunCeilings
from researchassistant.contracts.discovery_v2 import V2DiscoveryOperation
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_evidence import (
    V2AdmissionMethod,
    V2EvidenceAdmissionBatchResult,
)
from researchassistant.contracts.model_research import (
    ResearchDirection,
    ResearchDirections,
)
from researchassistant.contracts.query_planning import (
    V2AdaptiveSearchConceptProposal,
    V2AdaptiveSearchConceptsOutput,
    V2InitialPlannerConceptsOutput,
    V2QueryConceptGroup,
    V2QueryConcepts,
)
from researchassistant.contracts.search import SearchRequest, SearchResponse, SearchResult
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_ROUND_ONE_SEARCH_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
    run_v2_production_pipeline,
)
from researchassistant.storage.discovery_store import (
    compute_discovery_audit_counters,
    provider_attempt_audit,
    read_discovery_artifacts,
    read_discovery_binding,
)
from researchassistant.storage.query_retrieval_store import read_pages
from researchassistant.storage.store import read_v2_artifact

CLAIM = "The regional program increases course completion."
DIRECTIONS = ResearchDirections(support_enabled=True, challenge_enabled=False)
CEILINGS = V2RunCeilings(
    max_physical_calls=160,
    max_total_tokens=500_000,
    max_total_cost_usd=phase12.Decimal("5"),
)


class _ConceptModel(phase12._V2Model):
    """Existing release fixture with fresh-v2 conceptual planning responses."""

    def generate(self, request: LLMRequest) -> object:
        output_name = request.requested_output_type.__name__
        if output_name == "V2InitialPlannerConceptsOutput":
            self.requests.append(request)
            return V2InitialPlannerConceptsOutput(
                queries=tuple(
                    V2QueryConcepts(
                        required_concepts=(
                            V2QueryConceptGroup(
                                concept=(
                                    f"{lane.direction.value} course completion {lane.strategy}"
                                ),
                                aliases=("program completion outcome",),
                            ),
                        ),
                        purpose="broad",
                    )
                    for lane in request.input_artifact.search_lanes
                )
            )
        if output_name == "V2AdaptiveSearchConceptsOutput":
            self.requests.append(request)
            self.search_agent_calls += 1
            artifact = request.input_artifact
            round_number = artifact.request.round_number
            return V2AdaptiveSearchConceptsOutput(
                searches=tuple(
                    V2AdaptiveSearchConceptProposal(
                        lane_index=index,
                        concepts=V2QueryConcepts(
                            required_concepts=(
                                V2QueryConceptGroup(
                                    concept=(
                                        f"independent replication course completion round "
                                        f"{round_number} lane {index}"
                                    ),
                                    aliases=("replication study",),
                                ),
                            ),
                            purpose="gap",
                        ),
                    )
                    for index, _lane in enumerate(artifact.lanes)
                )
            )
        return super().generate(request)


def _run_fresh(
    path: Path,
    *,
    model: _ConceptModel,
    search: phase12._Search,
    scraper: phase12._Scraper,
    run_id: UUID | None = None,
    directions: ResearchDirections = DIRECTIONS,
    providers: tuple[DiscoveryProvider, ...] = (DiscoveryProvider.EXA,),
    query_modes: Mapping[DiscoveryProvider, str] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
) -> V2ProductionPipelineResult:
    return run_v2_production_pipeline(
        CLAIM,
        db_path=path,
        directions=directions,
        discovery_providers=providers,
        search_providers={provider: search for provider in providers},
        wigolo_provider=scraper,
        llm_provider=model,
        routing_config=phase12._routing(),
        ceilings=CEILINGS,
        run_id=run_id,
        query_modes=query_modes,
        legacy_query_planning=False,
        cancellation_requested=cancellation_requested,
        clock=lambda: phase12.NOW,
    )


class _PagingSearch(phase12._Search):
    """Fill the first SERP query's pages in every round, leaving later queries short."""

    def __init__(self) -> None:
        super().__init__()
        self.first_serp_query: dict[int, UUID] = {}

    def search(self, request: SearchRequest) -> SearchResponse:
        self.requests.append(request)
        action = request.compiled_query
        assert action is not None
        round_number = action.conceptual_query.round_number
        rank_offset = 0
        count = 1
        if request.provider is DiscoveryProvider.SERPSEARCH:
            rank_offset = 10 * (request.page_number - 1)
            if (
                self.first_serp_query.setdefault(round_number, action.artifact_id)
                == action.artifact_id
            ):
                count = request.limit
        return SearchResponse(
            results=[
                SearchResult(
                    original_url=f"https://example.test/{action.artifact_id}/{rank}",
                    title=f"Regional program evaluation {rank}",
                    rank=rank,
                )
                for rank in range(rank_offset + 1, rank_offset + count + 1)
            ],
            provider_name=request.provider.value,
        )


class _InterruptedSearch(BaseException):
    """Simulate losing the worker without letting it write a terminal run result."""


@pytest.mark.slow
def test_production_resumes_yielded_page_and_schedules_all_search_rounds(tmp_path: Path) -> None:
    path = tmp_path / "first-pass-resume.sqlite"
    run_id = uuid4()
    search = _PagingSearch()
    providers = (DiscoveryProvider.SERPSEARCH, DiscoveryProvider.EXA)

    def interrupt_after_first_page() -> bool:
        if search.requests:
            raise _InterruptedSearch
        return False

    with pytest.raises(_InterruptedSearch):
        _run_fresh(
            path,
            model=_ConceptModel(completed_rounds=4),
            search=search,
            scraper=phase12._Scraper(),
            run_id=run_id,
            providers=providers,
            cancellation_requested=interrupt_after_first_page,
        )
    (first_request,) = search.requests
    assert first_request.provider is DiscoveryProvider.SERPSEARCH
    (first_page,) = read_pages(path, run_id)
    assert first_page.page_number == 1 and len(first_page.response.results) == 10
    initial_audit = provider_attempt_audit(path, run_id)
    assert len(initial_audit.starts) == 1
    with pytest.raises(KeyError):
        read_v2_artifact(path, run_id, V2_ROUND_ONE_SEARCH_KEY)
    with pytest.raises(KeyError):
        read_v2_artifact(path, run_id, f"metadata-retrieval-v2:{first_page.operation_id}:result")

    result = _run_fresh(
        path,
        model=_ConceptModel(completed_rounds=4),
        search=search,
        scraper=phase12._Scraper(),
        run_id=run_id,
        providers=providers,
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 4
    trace: dict[int, list[tuple[DiscoveryProvider, int]]] = {}
    dispatched = set()
    for request in search.requests:
        action = request.compiled_query
        assert action is not None
        trace.setdefault(action.conceptual_query.round_number, []).append(
            (request.provider, request.page_number)
        )
        key = (action.artifact_id, request.page_number)
        assert key not in dispatched
        dispatched.add(key)
    assert set(trace) == {1, 2, 3, 4}
    for round_trace in trace.values():
        assert round_trace[:3] == [
            (DiscoveryProvider.SERPSEARCH, 1),
            (DiscoveryProvider.EXA, 1),
            (DiscoveryProvider.SERPSEARCH, 2),
        ]
    for round_number in trace:
        read_v2_artifact(path, run_id, f"query-first-pass-v1/round-{round_number}")
        prefix_key = (
            "phase-4-discovery-scout"
            if round_number == 1
            else "post-phase-13-round-4-discovery-scout-v1"
            if round_number == 4
            else f"phase-7-round-{round_number}-discovery-scout"
        )
        read_v2_artifact(path, run_id, prefix_key + "/first-pass-v1")
    assert first_page in read_pages(path, run_id)
    final_audit = provider_attempt_audit(path, run_id)
    assert initial_audit.starts[0] in final_audit.starts
    assert initial_audit.completions[0] in final_audit.completions
    assert len(final_audit.starts) == len(dispatched)


def test_production_cancellation_after_first_page_preserves_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "first-pass-cancel.sqlite"
    run_id = uuid4()
    search = _PagingSearch()

    result = _run_fresh(
        path,
        model=_ConceptModel(),
        search=search,
        scraper=phase12._Scraper(),
        run_id=run_id,
        providers=(DiscoveryProvider.SERPSEARCH, DiscoveryProvider.EXA),
        cancellation_requested=lambda: bool(search.requests),
    )

    assert result.state is V2ProductionState.CANCELLED, result.failure_reason
    (request,) = search.requests
    assert request.provider is DiscoveryProvider.SERPSEARCH
    (page,) = read_pages(path, run_id)
    assert page.page_number == 1 and len(page.response.results) == 10
    audit = provider_attempt_audit(path, run_id)
    assert len(audit.starts) == 1 and not audit.interrupted_unknown
    with pytest.raises(KeyError):
        read_v2_artifact(path, run_id, f"metadata-retrieval-v2:{page.operation_id}:result")


@pytest.mark.slow
def test_fresh_conceptual_queries_release_after_round_four_and_restart_immutably(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fresh-query-round-four.sqlite"
    run_id = uuid4()
    model = _ConceptModel(completed_rounds=4)
    search = phase12._Search(unique_results=True)
    first = _run_fresh(
        path,
        model=model,
        search=search,
        scraper=phase12._Scraper(),
        run_id=run_id,
    )

    assert first.state is V2ProductionState.RELEASED, first.failure_reason
    assert first.final_output is not None
    assert first.final_output.stopping.completed_rounds == 4
    assert model.search_agent_calls == 3
    assert all(request.compiled_query is not None for request in search.requests)
    assert all(request.provider is DiscoveryProvider.EXA for request in search.requests)
    planned_rounds = {
        request.compiled_query.conceptual_query.round_number for request in search.requests
    }
    assert planned_rounds == {1, 2, 3, 4}
    assert read_v2_artifact(path, run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY)
    assert read_v2_artifact(path, run_id, "post-phase-13-round-4-plan-v1")
    assert compute_discovery_audit_counters(str(path), run_id).logical_queries == len(
        search.requests
    )

    resumed_model = _ConceptModel(completed_rounds=4)
    resumed_search = phase12._Search(unique_results=True)
    resumed = _run_fresh(
        path,
        model=resumed_model,
        search=resumed_search,
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert resumed == first
    assert resumed_model.requests == []
    assert resumed_search.requests == []
    assert read_v2_artifact(path, run_id, V2_PRODUCTION_ARTIFACT_KEY)


def test_fresh_query_mode_is_frozen_across_resume(tmp_path: Path) -> None:
    path = tmp_path / "fresh-query-mode.sqlite"
    run_id = uuid4()
    search = phase12._Search()
    first = _run_fresh(
        path,
        model=_ConceptModel(completed_rounds=1),
        search=search,
        scraper=phase12._Scraper(),
        run_id=run_id,
        providers=(DiscoveryProvider.OPENALEX,),
        query_modes={DiscoveryProvider.OPENALEX: "semantic"},
    )
    assert first.state is V2ProductionState.RELEASED, first.failure_reason
    binding = read_discovery_binding(str(path), run_id)
    assert binding.provider_configuration_hash
    operations = tuple(
        item
        for item in read_discovery_artifacts(str(path), run_id)
        if isinstance(item, V2DiscoveryOperation)
    )
    assert operations
    assert all(operation.action.mode == "semantic" for operation in operations)
    assert search.requests
    assert all(request.semantic for request in search.requests)

    with pytest.raises(sqlite3.IntegrityError, match="binding replay conflicts"):
        _run_fresh(
            path,
            model=_ConceptModel(completed_rounds=1),
            search=phase12._Search(),
            scraper=phase12._Scraper(),
            run_id=run_id,
            providers=(DiscoveryProvider.OPENALEX,),
            query_modes={DiscoveryProvider.OPENALEX: "lexical"},
        )


def test_fresh_challenge_only_run_preserves_existing_admission_policy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fresh-query-challenge.sqlite"
    directions = ResearchDirections(support_enabled=False, challenge_enabled=True)
    run_id = uuid4()
    result = _run_fresh(
        path,
        model=_ConceptModel(completed_rounds=1),
        search=phase12._Search(),
        scraper=phase12._Scraper(),
        run_id=run_id,
        directions=directions,
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.directions == directions
    assert {source.direction for source in result.final_output.all_surviving_sources} <= {
        ResearchDirection.CHALLENGE
    }
    admission = V2EvidenceAdmissionBatchResult.model_validate_json(
        read_v2_artifact(path, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY).payload_json
    )
    assert all(item.direction is ResearchDirection.CHALLENGE for item in admission.source_results)
    assert admission.policy_identity == "researchassistant-v2-phase-13-analyzer-admission-v3"
    assert all(
        item.evidence_record is None
        or item.evidence_record.admission_method is V2AdmissionMethod.ANALYZER_ADMITTED
        for item in admission.source_results
    )
