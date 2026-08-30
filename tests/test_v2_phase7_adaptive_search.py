from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveRoundStatus,
    V2AdaptiveStopCode,
    _execute_searches,
    _round_two_gap_input,
    normalize_query_text,
    queries_are_materially_new,
    run_v2_adaptive_search_continuation,
)
from agents.v2_discovery import (
    V2DiscoveryResponse,
    cluster_discovery_items,
    normalize_discovery_responses,
)
from models import (
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    ScoutBatchAudit,
    ScoutItem,
    Stage,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchProposal,
    V2AdaptiveSearchQuery,
    V2ClaimCoverageDimension,
    V2ClaimCoverageFocus,
    V2ClaimCoverageKind,
    V2DiscoveryScoutOutput,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2GapBudgetState,
    V2GapSearchDirection,
    V2InitialPlannerOutput,
    V2MaterialGap,
    V2PipelineIdentity,
    V2ProviderSearchBudget,
    V2RoundOneSearchQuery,
    V2SearchAgentInput,
)
from providers.llm import LLMProviderCapabilities, LLMStage
from providers.scraper import ScrapeRequest, ScrapeResponse
from providers.search import (
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from providers.v2_routing import V2RoutingConfig
from research_governor import (
    V2RoundThreeGovernorInput,
    V2RoundThreeReasonCode,
    evaluate_v2_round_three_authorization,
)
from store import init_db, insert_run, insert_v2_pipeline_identity

NOW = datetime(2026, 8, 20, tzinfo=UTC)


class FakeAdaptiveLLM:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(
        self,
        *,
        search_outputs: list[V2AdaptiveSearchModelOutput],
        gap_outputs: list[object],
    ) -> None:
        self.search_outputs = search_outputs
        self.gap_outputs = gap_outputs
        self.requests: list[object] = []

    def generate(self, request: object) -> object:
        self.requests.append(request)
        if request.stage is LLMStage.SEARCH_AGENT:
            return self.search_outputs.pop(0)
        if request.stage is LLMStage.GAP_ANALYSIS:
            return self.gap_outputs.pop(0)
        if request.stage is LLMStage.SCOUT:
            return ScoutBatch(
                run_id=request.run_id,
                items=tuple(
                    ScoutItem(
                        item_id=item.item_id,
                        decision="retrieve",
                        rationale="fixture",
                    )
                    for item in request.input_artifact.candidates
                ),
            )
        raise AssertionError(f"unexpected stage {request.stage}")


class FailingSearchAgentLLM(FakeAdaptiveLLM):
    def generate(self, request: object) -> object:
        if request.stage is LLMStage.SEARCH_AGENT:
            raise RuntimeError("fixture returned malformed JSON")
        return super().generate(request)


class MalformedSearchAgentLLM(FakeAdaptiveLLM):
    def generate(self, request: object) -> object:
        if request.stage is LLMStage.SEARCH_AGENT:
            return object()
        return super().generate(request)


class FakeSearch:
    def __init__(self, *, fail: bool = False, duplicate_url: str | None = None) -> None:
        self.fail = fail
        self.duplicate_url = duplicate_url
        self.requests: list[SearchRequest] = []

    def search(self, request: SearchRequest) -> SearchResponse:
        self.requests.append(request)
        if self.fail:
            raise SearchProviderError(
                SearchFailureCode.TRANSIENT_OUTAGE,
                "fixture provider unavailable",
                retryable=True,
            )
        url = self.duplicate_url or f"https://example.org/round-{len(self.requests)}"
        return SearchResponse(
            results=[SearchResult(original_url=url, title="Independent outcome study")],
            provider_name="fixture-search",
        )


class EmptySearch(FakeSearch):
    def search(self, request: SearchRequest) -> SearchResponse:
        self.requests.append(request)
        return SearchResponse(results=[], provider_name="fixture-search")


class RoundThreeFailureSearch(FakeSearch):
    def search(self, request: SearchRequest) -> SearchResponse:
        if len(self.requests) == 1:
            raise SearchProviderError(
                SearchFailureCode.TRANSIENT_OUTAGE,
                "fixture Round-3 provider degradation",
                retryable=True,
            )
        return super().search(request)


class FakeScraper:
    def __init__(self) -> None:
        self.requests: list[ScrapeRequest] = []

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.requests.append(request)
        return ScrapeResponse(
            resolved_url=request.url,
            original_url=request.url,
            content_type="text/plain",
            text=(
                "Opening evidence reports a 42% outcome in the specified population. "
                "The methods compare an independent cohort with the baseline. "
                "In conclusion, the evaluation reports a bounded result."
            ),
            provider_name="fixture",
            provider_version="v1",
        )


def _routing() -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        {
            "MIMO_API_KEY": "mimo-secret",
            "MIMO_V25_MODEL": "mimo-v2.5",
            "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
            "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
            "LUNA_API_KEY": "luna-secret",
            "LUNA_BASE_URL": "https://luna.example.test/v1",
            "LUNA_MODEL": "deployment-owned-luna-model",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="v2-phase7-tests",
    )


def _initial_plan(
    run_id: UUID,
    *,
    directions: ResearchDirections | None = None,
    discovery_providers: tuple[DiscoveryProvider, ...] = (DiscoveryProvider.EXA,),
) -> V2InitialPlannerOutput:
    selected_directions = directions or ResearchDirections()
    strategies = {
        DiscoveryProvider.SERPSEARCH: ("broad_web", "institutional_coverage"),
        DiscoveryProvider.EXA: ("direct_evidence", "mechanism", "analysis"),
        DiscoveryProvider.OPENALEX: ("academic_studies",),
        DiscoveryProvider.ARXIV: ("preprints",),
        DiscoveryProvider.PUBMED: ("biomedical_studies",),
        DiscoveryProvider.SERPER: ("broad_web",),
    }
    return V2InitialPlannerOutput(
        run_id=run_id,
        raw_claim="A public claim.",
        directions=selected_directions,
        discovery_providers=discovery_providers,
        searches=tuple(
            V2RoundOneSearchQuery(
                run_id=run_id,
                query_id=uuid4(),
                direction=direction,
                provider=provider,
                strategy=strategy,
                query_text=(
                    f"broad round one {strategy}"
                    if provider is DiscoveryProvider.EXA
                    else f"broad round one {provider.value} {strategy}"
                ),
                created_at=NOW,
            )
            for direction in selected_directions.enabled_directions
            for provider in discovery_providers
            for strategy in strategies[provider]
        ),
        planner_prompt_version="fixture-v1",
        planned_at=NOW,
    )


def _round_one_outputs(
    plan: V2InitialPlannerOutput,
    known_url: str | None = None,
) -> tuple[V2DiscoveryScoutOutput, V2AcquisitionProbeOutput]:
    items = (
        normalize_discovery_responses(
            run_id=plan.run_id,
            directions=plan.directions,
            responses=(
                V2DiscoveryResponse(
                    query=plan.searches[0],
                    results=(
                        SearchResult(
                            original_url=known_url,
                            title="Known source",
                        ),
                    ),
                ),
            ),
            discovered_at=NOW,
        )
        if known_url is not None
        else ()
    )
    discovery = V2DiscoveryScoutOutput(
        run_id=plan.run_id,
        directions=plan.directions,
        items=items,
        clusters=cluster_discovery_items(items),
        scout_batches=(
            (
                ScoutBatch(
                    run_id=plan.run_id,
                    items=tuple(
                        ScoutItem(
                            item_id=item.item_id,
                            decision="retrieve",
                            rationale="fixture",
                        )
                        for item in items
                    ),
                ),
            )
            if items
            else ()
        ),
        scout_audits=(() if not items else (ScoutBatchAudit(batch_number=1, attempted_calls=1),)),
        completed_at=NOW,
    )
    acquisition = V2AcquisitionProbeOutput(
        run_id=plan.run_id,
        directions=plan.directions,
        acquisitions=(),
        attempts=(),
        probes=(),
        survivors=(),
        completed_at=NOW,
    )
    return discovery, acquisition


def _gap(plan: V2InitialPlannerOutput, *, continue_research: bool) -> V2GapAnalysisOutput:
    gap_input = V2GapAnalysisInput(
        run_id=plan.run_id,
        exact_claim=plan.raw_claim,
        directions=plan.directions,
        attempted_queries=(),
        surviving_sources=(),
        probe_passages=(),
        source_families=(),
        discovered_terms=("independent cohort", "outcome measure"),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=(),
        remaining_budget=V2GapBudgetState(model_calls_remaining=20),
    )
    if continue_research:
        material_gap = V2MaterialGap(
            gap_id="gap-outcome",
            direction=ResearchDirection.SUPPORT,
            missing_evidence="Independent outcome evidence for the population",
            rationale="Round one did not contain an independent outcome source.",
        )
        result = V2GapAnalysisResult(
            run_id=plan.run_id,
            directions=plan.directions,
            coverage_summary="A material outcome gap remains.",
            material_gaps=(material_gap,),
            continue_research=True,
            new_search_directions=(
                V2GapSearchDirection(
                    gap_id=material_gap.gap_id,
                    direction=material_gap.direction,
                    missing_evidence=material_gap.missing_evidence,
                    search_focus="Independent cohort outcome evaluation",
                ),
            ),
            discovered_terms=("independent cohort",),
            analyzed_at=NOW,
        )
    else:
        result = V2GapAnalysisResult(
            run_id=plan.run_id,
            directions=plan.directions,
            coverage_summary="Round one is materially useful.",
            material_gaps=(),
            continue_research=False,
            stop_reason="Additional research is not materially useful.",
            new_search_directions=(),
            discovered_terms=(),
            analyzed_at=NOW,
        )
    return V2GapAnalysisOutput(
        run_id=plan.run_id,
        input=gap_input,
        state=V2GapAnalysisState.COMPLETED,
        result=result,
        attempts=(),
        stop_adaptive_continuation=not continue_research,
        completed_at=NOW,
    )


def test_round_two_gap_input_preserves_initial_planner_claim_coverage_focus() -> None:
    run_id = uuid4()
    initial_plan = _initial_plan(run_id)
    round_one_gap = _gap(initial_plan, continue_research=True)
    focus = V2ClaimCoverageFocus(
        dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        claim_component="the stated effect",
        kind=V2ClaimCoverageKind.CLAIM_COMPONENT,
    )
    round_one_gap = round_one_gap.model_copy(
        update={"input": round_one_gap.input.model_copy(update={"claim_coverage_focus": (focus,)})}
    )
    round_two_plan = V2AdaptiveRoundPlan(
        run_id=run_id,
        round_number=2,
        directions=initial_plan.directions,
        enabled_providers=(DiscoveryProvider.EXA,),
        targeted_gap_ids=("gap-outcome",),
        discovered_terms=(),
        searches=(
            V2AdaptiveSearchQuery(
                run_id=run_id,
                query_id=uuid4(),
                round_number=2,
                direction=ResearchDirection.SUPPORT,
                provider=DiscoveryProvider.EXA,
                targeted_gap_ids=("gap-outcome",),
                strategy="independent_outcome",
                query_text="independent outcome evidence for the population",
                created_at=NOW,
            ),
        ),
        search_agent_prompt_version="test-v1",
        planned_at=NOW,
    )
    discovery, acquisition = _round_one_outputs(initial_plan)

    gap_input = _round_two_gap_input(
        round_one_gap,
        round_two_plan,
        discovery,
        acquisition,
        V2AdaptiveBudgetState(model_calls_remaining=10),
    )

    assert gap_input.claim_coverage_focus == (focus,)


def test_adaptive_search_preserves_successful_empty_provider_results(tmp_path: Path) -> None:
    run_id = uuid4()
    query = V2AdaptiveSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        round_number=2,
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.EXA,
        targeted_gap_ids=("gap-outcome",),
        strategy="independent_outcome",
        query_text="independent outcome evidence for the population",
        created_at=NOW,
    )
    plan = V2AdaptiveRoundPlan(
        run_id=run_id,
        round_number=2,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        enabled_providers=(DiscoveryProvider.EXA,),
        targeted_gap_ids=("gap-outcome",),
        discovered_terms=(),
        searches=(query,),
        search_agent_prompt_version="test-v1",
        planned_at=NOW,
    )
    search = EmptySearch()

    result = _execute_searches(
        _db(tmp_path, run_id),
        plan,
        {DiscoveryProvider.EXA: search},
        None,
        lambda: NOW,
    )

    assert result.outcomes[0].succeeded
    assert result.outcomes[0].results == ()


def _proposal(
    query: str,
    *,
    direction: ResearchDirection = ResearchDirection.SUPPORT,
    provider: DiscoveryProvider = DiscoveryProvider.EXA,
    targeted_gap_ids: tuple[str, ...] = ("gap-outcome",),
) -> V2AdaptiveSearchModelOutput:
    return V2AdaptiveSearchModelOutput(
        searches=(
            V2AdaptiveSearchProposal(
                direction=direction,
                provider=provider,
                targeted_gap_ids=targeted_gap_ids,
                strategy="independent_outcome",
                query_text=query,
            ),
        )
    )


def _proposal_batch(
    queries: tuple[str, ...],
    *,
    direction: ResearchDirection = ResearchDirection.SUPPORT,
    provider: DiscoveryProvider = DiscoveryProvider.EXA,
    targeted_gap_ids: tuple[str, ...] = ("gap-outcome",),
) -> V2AdaptiveSearchModelOutput:
    return V2AdaptiveSearchModelOutput(
        searches=tuple(
            V2AdaptiveSearchProposal(
                direction=direction,
                provider=provider,
                targeted_gap_ids=targeted_gap_ids,
                strategy=f"independent_outcome_{index}",
                query_text=query,
            )
            for index, query in enumerate(queries, start=1)
        )
    )


def _luna_stop() -> object:
    from models import V2GapAnalysisModelOutput

    return V2GapAnalysisModelOutput(
        coverage_summary="Round two resolved the material gap.",
        material_gaps=(),
        continue_research=False,
        stop_reason="No material gap remains after Round 2.",
        new_search_directions=(),
        discovered_terms=("outcome",),
    )


def _luna_continue() -> object:
    from models import V2GapAnalysisModelOutput

    gap = V2MaterialGap(
        gap_id="gap-outcome",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="A remaining independent replication",
        rationale="One narrow replication gap remains.",
    )
    return V2GapAnalysisModelOutput(
        coverage_summary="One narrow replication gap remains.",
        material_gaps=(gap,),
        continue_research=True,
        new_search_directions=(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=gap.direction,
                missing_evidence=gap.missing_evidence,
                search_focus="Replication using a distinct outcome instrument",
            ),
        ),
        discovered_terms=("replication instrument",),
    )


def _db(tmp_path: Path, run_id: UUID) -> str:
    db_path = str(tmp_path / "phase7.sqlite3")
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim="A public claim.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)
    return db_path


def _run(
    tmp_path: Path,
    *,
    initial_gap_continue: bool,
    llm: FakeAdaptiveLLM,
    search: FakeSearch | None,
    budget: V2AdaptiveBudgetState | None = None,
    cancellation_requested: object | None = None,
    known_round_one_url: str | None = None,
    provider_attempts: dict[DiscoveryProvider, int] | None = None,
    directions: ResearchDirections | None = None,
    discovery_providers: tuple[DiscoveryProvider, ...] = (DiscoveryProvider.EXA,),
    additional_search_providers: dict[DiscoveryProvider, FakeSearch] | None = None,
) -> object:
    run_id = uuid4()
    plan = _initial_plan(
        run_id,
        directions=directions,
        discovery_providers=discovery_providers,
    )
    discovery, acquisition = _round_one_outputs(plan, known_round_one_url)
    search_providers = {} if search is None else {DiscoveryProvider.EXA: search}
    if additional_search_providers:
        search_providers.update(additional_search_providers)
    return run_v2_adaptive_search_continuation(
        db_path=_db(tmp_path, run_id),
        initial_plan=plan,
        round_one_discovery=discovery,
        round_one_acquisition=acquisition,
        round_one_gap=_gap(plan, continue_research=initial_gap_continue),
        search_providers=search_providers,
        llm_provider=llm,
        routing_config=_routing(),
        wigolo_provider=FakeScraper(),
        budget=budget or V2AdaptiveBudgetState(model_calls_remaining=20),
        provider_attempts=provider_attempts,
        cancellation_requested=cancellation_requested,
        clock=lambda: NOW,
    )


def test_round_one_stop_creates_no_round_two_work(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(search_outputs=[], gap_outputs=[])
    result = _run(
        tmp_path,
        initial_gap_continue=False,
        llm=llm,
        search=FakeSearch(),
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.ROUND_ONE_COMPLETE
    assert result.stopping_decision.completed_rounds == 1
    assert result.rounds == () and llm.requests == []


def test_restart_after_round_one_boundary_creates_no_work(tmp_path: Path) -> None:
    run_id = uuid4()
    plan = _initial_plan(run_id)
    discovery, acquisition = _round_one_outputs(plan)
    db_path = _db(tmp_path, run_id)
    llm = FakeAdaptiveLLM(search_outputs=[], gap_outputs=[])
    arguments = dict(
        db_path=db_path,
        initial_plan=plan,
        round_one_discovery=discovery,
        round_one_acquisition=acquisition,
        round_one_gap=_gap(plan, continue_research=False),
        search_providers={DiscoveryProvider.EXA: FakeSearch()},
        llm_provider=llm,
        routing_config=_routing(),
        wigolo_provider=FakeScraper(),
        budget=V2AdaptiveBudgetState(model_calls_remaining=20),
        clock=lambda: NOW,
    )

    first = run_v2_adaptive_search_continuation(**arguments)
    resumed = run_v2_adaptive_search_continuation(**arguments)

    assert resumed == first
    assert llm.requests == []


def test_gap_directed_round_two_runs_existing_sequence_then_stops(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("independent cohort outcome instrument evaluation")],
        gap_outputs=[_luna_stop()],
    )
    search = FakeSearch()
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=search,
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.ROUND_TWO_COMPLETE
    assert result.stopping_decision.completed_rounds == 2
    assert result.rounds[0].targeted_gap_ids == ("gap-outcome",)
    assert result.rounds[0].survivor_additions == 1
    assert len(result.merged_survivors.sources) == 1
    assert search.requests[0].provider is DiscoveryProvider.EXA


def test_round_three_requires_governor_and_stops_at_hard_maximum(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal("independent cohort outcome instrument evaluation"),
            _proposal("distinct replication instrument longitudinal outcome"),
        ],
        gap_outputs=[_luna_continue()],
    )
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(),
    )

    assert result.stopping_decision.completed_rounds == 3
    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.ROUND_THREE_COMPLETE
    assert result.governor_decision is not None and result.governor_decision.authorized
    assert len(result.rounds) == 2
    assert result.rounds[1].planned_query_count == 1
    assert all(item.round_number <= 3 for item in result.rounds)


def test_degraded_round_three_emits_terminal_provider_failure(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal("independent cohort outcome instrument evaluation"),
            _proposal("distinct replication instrument longitudinal outcome"),
        ],
        gap_outputs=[_luna_continue()],
    )
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=RoundThreeFailureSearch(),
    )

    assert result.rounds[-1].round_number == 3
    assert result.rounds[-1].status is V2AdaptiveRoundStatus.DEGRADED
    assert result.stopping_decision.completed_rounds == 3
    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.PROVIDER_FAILURE


def test_round_three_rejects_a_trivial_query_rewrite(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal("independent cohort outcome instrument evaluation"),
            _proposal("evaluation instrument outcome cohort independent"),
        ],
        gap_outputs=[_luna_continue()],
    )
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(),
    )

    assert result.stopping_decision.completed_rounds == 2
    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN
    assert result.governor_decision.reason_code is V2RoundThreeReasonCode.INVALID_SEARCH_AGENT_PLAN


def test_no_eligible_provider_stops_before_search_agent(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(search_outputs=[], gap_outputs=[])
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=None,
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.NO_ELIGIBLE_PROVIDER
    assert llm.requests == []


def test_provider_ceiling_makes_an_enabled_provider_ineligible(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(search_outputs=[], gap_outputs=[])
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(),
        provider_attempts={DiscoveryProvider.EXA: 18},
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.NO_ELIGIBLE_PROVIDER
    assert llm.requests == []


def test_provider_failure_degrades_without_inventing_survivors(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("independent cohort outcome instrument evaluation")],
        gap_outputs=[],
    )
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(fail=True),
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.PROVIDER_FAILURE
    assert result.rounds[0].failed_query_count == 1
    assert result.rounds[0].survivor_additions == 0


def test_search_agent_provider_failure_preserves_round_one_work(tmp_path: Path) -> None:
    llm = FailingSearchAgentLLM(search_outputs=[], gap_outputs=[])
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(),
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.PROVIDER_FAILURE
    assert result.stopping_decision.completed_rounds == 1
    assert "Search Agent failed" in result.stopping_decision.stopping_reason


def test_duplicate_heavy_round_two_stops_before_round_three(tmp_path: Path) -> None:
    duplicate_url = "https://example.org/known"
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("independent cohort outcome instrument evaluation")],
        gap_outputs=[_luna_continue()],
    )
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(duplicate_url=duplicate_url),
        known_round_one_url=duplicate_url,
    )

    assert result.rounds[0].duplicate_source_count == 1
    assert result.rounds[0].survivor_additions == 0
    assert result.governor_decision.reason_code is V2RoundThreeReasonCode.DUPLICATE_HEAVY
    assert result.stopping_decision.completed_rounds == 2


def test_cancellation_stops_before_round_two_work(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(search_outputs=[], gap_outputs=[])
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(),
        cancellation_requested=lambda: True,
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.CANCELLED
    assert result.stopping_decision.completed_rounds == 1
    assert llm.requests == []


def test_round_two_lane_overflow_preserves_earliest_exa_queries(
    tmp_path: Path,
) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal_batch(
                (
                    "independent cohort outcome instrument evaluation one",
                    "independent cohort outcome instrument evaluation two",
                    "independent cohort outcome instrument evaluation three",
                    "independent cohort outcome instrument evaluation four",
                )
            )
        ],
        gap_outputs=[_luna_stop()],
    )
    search = FakeSearch()
    openalex = FakeSearch()
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=search,
        discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX),
        additional_search_providers={DiscoveryProvider.OPENALEX: openalex},
    )

    assert result.rounds[0].planned_query_count == 3
    assert result.rounds[0].completed_query_count == 3
    assert [request.query_text for request in search.requests] == [
        "independent cohort outcome instrument evaluation one",
        "independent cohort outcome instrument evaluation two",
        "independent cohort outcome instrument evaluation three",
    ]
    assert openalex.requests == []
    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.ROUND_TWO_COMPLETE


def test_round_two_total_query_overflow_preserves_earliest_queries(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal_batch(
                (
                    "independent cohort outcome instrument evaluation one",
                    "independent cohort outcome instrument evaluation two",
                    "independent cohort outcome instrument evaluation three",
                    "independent cohort outcome instrument evaluation four",
                    "independent cohort outcome instrument evaluation five",
                )
            )
        ],
        gap_outputs=[_luna_stop()],
    )
    search = FakeSearch()
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=search,
    )

    assert result.rounds[0].planned_query_count == 3
    assert len(search.requests) == 3
    assert [request.query_text for request in search.requests] == [
        "independent cohort outcome instrument evaluation one",
        "independent cohort outcome instrument evaluation two",
        "independent cohort outcome instrument evaluation three",
    ]
    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.ROUND_TWO_COMPLETE


@pytest.mark.parametrize(
    ("case_name", "proposal"),
    [
        (
            "disabled-provider",
            _proposal(
                "independent disabled provider outcome",
                provider=DiscoveryProvider.OPENALEX,
            ),
        ),
        (
            "disabled-direction",
            _proposal(
                "independent disabled direction outcome",
                direction=ResearchDirection.CHALLENGE,
            ),
        ),
        (
            "unknown-gap",
            _proposal(
                "independent unknown gap outcome",
                targeted_gap_ids=("gap-unknown",),
            ),
        ),
    ],
)
def test_semantically_invalid_search_agent_plans_fail_closed(
    tmp_path: Path,
    case_name: str,
    proposal: V2AdaptiveSearchModelOutput,
) -> None:
    case_path = tmp_path / case_name
    case_path.mkdir()
    llm = FakeAdaptiveLLM(search_outputs=[proposal], gap_outputs=[])
    search = FakeSearch()
    result = _run(
        case_path,
        initial_gap_continue=True,
        llm=llm,
        search=search,
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN
    assert result.stopping_decision.completed_rounds == 1
    assert search.requests == []


def test_gap_direction_mismatch_is_an_invalid_search_agent_plan(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal(
                "independent challenge direction outcome",
                direction=ResearchDirection.CHALLENGE,
            )
        ],
        gap_outputs=[],
    )
    search = FakeSearch()
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=search,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=True),
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN
    assert search.requests == []


def test_malformed_search_agent_output_is_an_invalid_plan(tmp_path: Path) -> None:
    llm = MalformedSearchAgentLLM(search_outputs=[], gap_outputs=[])
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=FakeSearch(),
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN


def test_restart_after_completed_round_boundary_reuses_every_artifact(tmp_path: Path) -> None:
    run_id = uuid4()
    plan = _initial_plan(run_id)
    discovery, acquisition = _round_one_outputs(plan)
    db_path = _db(tmp_path, run_id)
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("independent cohort outcome instrument evaluation")],
        gap_outputs=[_luna_stop()],
    )
    search = FakeSearch()
    arguments = dict(
        db_path=db_path,
        initial_plan=plan,
        round_one_discovery=discovery,
        round_one_acquisition=acquisition,
        round_one_gap=_gap(plan, continue_research=True),
        search_providers={DiscoveryProvider.EXA: search},
        llm_provider=llm,
        routing_config=_routing(),
        wigolo_provider=FakeScraper(),
        budget=V2AdaptiveBudgetState(model_calls_remaining=20),
        clock=lambda: NOW,
    )
    first = run_v2_adaptive_search_continuation(**arguments)
    request_count = len(llm.requests)
    search_count = len(search.requests)
    resumed = run_v2_adaptive_search_continuation(**arguments)

    assert resumed == first
    assert len(llm.requests) == request_count
    assert len(search.requests) == search_count


def test_restart_after_round_three_boundary_reuses_every_artifact(tmp_path: Path) -> None:
    run_id = uuid4()
    plan = _initial_plan(run_id)
    discovery, acquisition = _round_one_outputs(plan)
    db_path = _db(tmp_path, run_id)
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal("independent cohort outcome instrument evaluation"),
            _proposal("distinct replication instrument longitudinal outcome"),
        ],
        gap_outputs=[_luna_continue()],
    )
    search = FakeSearch()
    arguments = dict(
        db_path=db_path,
        initial_plan=plan,
        round_one_discovery=discovery,
        round_one_acquisition=acquisition,
        round_one_gap=_gap(plan, continue_research=True),
        search_providers={DiscoveryProvider.EXA: search},
        llm_provider=llm,
        routing_config=_routing(),
        wigolo_provider=FakeScraper(),
        budget=V2AdaptiveBudgetState(model_calls_remaining=20),
        clock=lambda: NOW,
    )

    first = run_v2_adaptive_search_continuation(**arguments)
    request_count = len(llm.requests)
    search_count = len(search.requests)
    resumed = run_v2_adaptive_search_continuation(**arguments)

    assert resumed == first
    assert len(llm.requests) == request_count
    assert len(search.requests) == search_count


def test_query_novelty_rejects_exact_and_trivial_rewrites() -> None:
    history = ("independent cohort outcome evaluation",)
    assert normalize_query_text(" Independent, COHORT outcome evaluation! ") == (
        "independent cohort outcome evaluation"
    )
    assert not queries_are_materially_new("independent cohort outcome evaluation", history)
    assert not queries_are_materially_new("cohort outcome evaluation independent", history)
    assert not queries_are_materially_new(
        "independent cohort outcome evaluation study",
        history,
    )
    assert queries_are_materially_new("replication instrument longitudinal result", history)


def test_invalid_search_agent_repeat_is_rejected_before_provider_work(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("broad round one direct evidence")],
        gap_outputs=[],
    )
    search = FakeSearch()
    result = _run(
        tmp_path,
        initial_gap_continue=True,
        llm=llm,
        search=search,
    )

    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN
    assert search.requests == []


def test_query_contract_rejects_recursive_fourth_round() -> None:
    with pytest.raises(ValidationError, match="2 or 3"):
        V2AdaptiveSearchQuery(
            run_id=uuid4(),
            query_id=uuid4(),
            round_number=4,
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.EXA,
            targeted_gap_ids=("gap-outcome",),
            strategy="forbidden",
            query_text="forbidden fourth round",
            created_at=NOW,
        )


def test_direction_and_provider_isolation_are_strict() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        V2AdaptiveSearchModelOutput(searches=())
    challenge_gap = V2MaterialGap(
        gap_id="gap-challenge",
        direction=ResearchDirection.CHALLENGE,
        missing_evidence="Challenge evidence",
        rationale="Fixture",
    )
    with pytest.raises(ValidationError, match="disabled research direction"):
        V2SearchAgentInput(
            run_id=uuid4(),
            exact_claim="A public claim.",
            round_number=2,
            directions=ResearchDirections(),
            eligible_providers=(DiscoveryProvider.EXA,),
            material_gaps=(challenge_gap,),
            search_directions=(
                V2GapSearchDirection(
                    gap_id=challenge_gap.gap_id,
                    direction=challenge_gap.direction,
                    missing_evidence=challenge_gap.missing_evidence,
                    search_focus="Challenge-only focus",
                ),
            ),
            discovered_terms=(),
            previous_queries=(),
            provider_budgets=(
                V2ProviderSearchBudget(
                    provider=DiscoveryProvider.EXA,
                    attempted_calls=0,
                    maximum_calls=18,
                ),
            ),
            maximum_queries=1,
        )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"round_two_duplicate_rate": 0.70}, V2RoundThreeReasonCode.DUPLICATE_HEAVY),
        ({"eligible_provider_exists": False}, V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER),
        ({"materially_new_queries": False}, V2RoundThreeReasonCode.NO_NEW_QUERY),
        ({"protected_downstream_budget_remains": False}, V2RoundThreeReasonCode.PROTECTED_BUDGET),
        ({"complete_workload_reservable": False}, V2RoundThreeReasonCode.INSUFFICIENT_RESERVATION),
    ],
)
def test_round_three_governor_rejects_each_hard_condition(
    overrides: dict[str, object],
    reason: V2RoundThreeReasonCode,
) -> None:
    values = {
        "run_id": uuid4(),
        "current_round": 2,
        "material_gap_remains": True,
        "luna_recommends_continue": True,
        "new_search_direction_exists": True,
        "eligible_provider_exists": True,
        "materially_new_queries": True,
        "provider_ceiling_permits": True,
        "protected_downstream_budget_remains": True,
        "complete_workload_reservable": True,
        "round_two_duplicate_rate": 0.0,
        "decided_at": NOW,
    }
    values.update(overrides)
    decision = evaluate_v2_round_three_authorization(V2RoundThreeGovernorInput(**values))

    assert not decision.authorized
    assert decision.reason_code is reason
