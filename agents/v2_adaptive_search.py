"""Gap-directed v2 Round-2/3 continuation with deterministic application authority."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ConfigDict, Field, field_validator, model_validator

from agents.v2_acquisition import run_v2_acquisition_probe
from agents.v2_discovery import V2DiscoveryResponse, run_v2_discovery_and_scout
from agents.v2_gap_analysis import V2GapAnalysisRunResult, run_v2_gap_analysis
from models import (
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    ResearchDirection,
    SourceCluster,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchQuery,
    V2DiscoveryScoutOutput,
    V2GapAcquisitionFailure,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAttemptedQuery,
    V2GapBudgetState,
    V2GapDuplicatePattern,
    V2GapProbePassage,
    V2GapSourceFamily,
    V2GapSurvivingSourceMetadata,
    V2InitialPlannerOutput,
    V2ProviderSearchBudget,
    V2SearchAgentInput,
    V2SurvivingSource,
)
from money import add_usd
from providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationError,
    LLMProvider,
    LLMRequest,
    LLMStage,
    invoke_llm,
    load_prompt,
    render_stage_prompt,
)
from providers.pricing import conservative_token_estimate
from providers.ranking import canonical_discovery_url
from providers.scraper import ScraperProvider
from providers.search import (
    SearchFailureCode,
    SearchIntent,
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResult,
)
from providers.v2_routing import V2RoutingConfig
from research_governor import (
    V2RoundThreeGovernorDecision,
    V2RoundThreeGovernorInput,
    V2RoundThreeReasonCode,
    evaluate_v2_round_three_authorization,
)
from store import insert_v2_artifact, read_v2_artifact

V2_ADAPTIVE_COMPLETION_KEY = "phase-7-adaptive-search-completion"
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PROVIDER_TOTAL_CEILINGS = {
    DiscoveryProvider.SERPSEARCH: 12,
    DiscoveryProvider.EXA: 18,
    DiscoveryProvider.OPENALEX: 10,
    DiscoveryProvider.ARXIV: 6,
    DiscoveryProvider.PUBMED: 6,
    DiscoveryProvider.SERPER: 6,
}
_ROUND_TWO_PER_DIRECTION_CAPS = {
    DiscoveryProvider.SERPSEARCH: 2,
    DiscoveryProvider.EXA: 3,
    DiscoveryProvider.OPENALEX: 1,
    DiscoveryProvider.ARXIV: 1,
    DiscoveryProvider.PUBMED: 1,
    DiscoveryProvider.SERPER: 1,
}


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("adaptive continuation timestamps must be timezone-aware")
    return value


class V2AdaptiveRoundStatus(StrEnum):
    COMPLETED = "completed"
    DEGRADED = "degraded"
    CANCELLED = "cancelled"


class V2AdaptiveStopCode(StrEnum):
    ROUND_ONE_COMPLETE = "round_one_complete"
    ROUND_TWO_COMPLETE = "round_two_complete"
    ROUND_THREE_COMPLETE = "round_three_complete"
    NO_ELIGIBLE_PROVIDER = "no_eligible_provider"
    NO_NEW_QUERY = "no_materially_new_query"
    BUDGET = "insufficient_budget"
    CANCELLED = "cancelled"
    PROVIDER_FAILURE = "provider_failure"
    GAP_ANALYSIS_DEGRADED = "gap_analysis_degraded"
    GOVERNOR_REJECTED = "governor_rejected"


class V2AdaptiveBudgetState(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls_remaining: int = Field(ge=0)
    tokens_remaining: int | None = Field(default=None, ge=0)
    cost_remaining_usd: Decimal | None = Field(default=None, ge=0)
    protected_downstream_model_calls: int = Field(default=1, ge=0)
    round_three_complete_workload_reservable: bool = True


class V2SearchAgentReservation(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(ge=1)
    output_tokens: int = Field(ge=1)
    reserved_tokens: int = Field(ge=1)
    reserved_cost_usd: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self) -> V2SearchAgentReservation:
        if self.input_tokens + self.output_tokens != self.reserved_tokens:
            raise ValueError("Search Agent token reservation must be internally consistent")
        return self


class V2AdaptivePlannedRound(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    plan: V2AdaptiveRoundPlan
    reservation: V2SearchAgentReservation


class V2AdaptiveSearchOutcome(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: V2AdaptiveSearchQuery
    succeeded: bool
    results: tuple[SearchResult, ...] = ()
    failure_code: str | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> V2AdaptiveSearchOutcome:
        if self.succeeded:
            if (
                not self.results
                or self.failure_code is not None
                or self.failure_message is not None
            ):
                raise ValueError("successful adaptive searches require results and no failure")
        elif self.results or self.failure_code is None or self.failure_message is None:
            raise ValueError("failed adaptive searches require paired failure fields")
        return self


class V2AdaptiveSearchResults(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: int = Field(ge=2, le=3)
    outcomes: tuple[V2AdaptiveSearchOutcome, ...]
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware_datetime)


class V2MergedSurvivor(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    research_round: int = Field(ge=1, le=3)
    source_url: str = Field(min_length=1)
    survivor: V2SurvivingSource


class V2MergedSurvivorPool(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    sources: tuple[V2MergedSurvivor, ...]


class V2AdaptiveRoundExecution(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: int = Field(ge=2, le=3)
    targeted_gap_ids: tuple[str, ...]
    status: V2AdaptiveRoundStatus
    planned_query_count: int = Field(ge=0)
    completed_query_count: int = Field(ge=0)
    failed_query_count: int = Field(ge=0)
    new_source_count: int = Field(ge=0)
    duplicate_source_count: int = Field(ge=0)
    survivor_additions: int = Field(ge=0)
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware_datetime)


class V2AdaptiveStoppingDecision(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    completed_rounds: int = Field(ge=1, le=3)
    stop_code: V2AdaptiveStopCode
    stopping_reason: str = Field(min_length=1)
    decided_at: datetime

    _decided_at_is_aware = field_validator("decided_at")(_aware_datetime)


class V2AdaptiveContinuationResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    rounds: tuple[V2AdaptiveRoundExecution, ...]
    merged_survivors: V2MergedSurvivorPool
    stopping_decision: V2AdaptiveStoppingDecision
    governor_decision: V2RoundThreeGovernorDecision | None = None
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware_datetime)


def normalize_query_text(value: str) -> str:
    """Cheap canonical query form used for exact history rejection."""
    return " ".join(_TOKEN_RE.findall(value.casefold()))


def queries_are_materially_new(candidate: str, previous_queries: tuple[str, ...]) -> bool:
    """Reject exact repeats and obvious token-preserving or one-token rewrites."""
    normalized = normalize_query_text(candidate)
    if not normalized:
        return False
    candidate_tokens = Counter(normalized.split())
    for previous in previous_queries:
        prior = normalize_query_text(previous)
        if normalized == prior:
            return False
        prior_tokens = Counter(prior.split())
        difference = sum((candidate_tokens - prior_tokens).values()) + sum(
            (prior_tokens - candidate_tokens).values()
        )
        if difference <= 1:
            return False
    return True


def run_v2_adaptive_search_continuation(
    *,
    db_path: str | Path,
    initial_plan: V2InitialPlannerOutput,
    round_one_discovery: V2DiscoveryScoutOutput,
    round_one_acquisition: V2AcquisitionProbeOutput,
    round_one_gap: V2GapAnalysisOutput,
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None = None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None = None,
    budget: V2AdaptiveBudgetState,
    provider_attempts: Mapping[DiscoveryProvider, int] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2AdaptiveContinuationResult:
    """Continue a completed Round 1 through at most two gap-directed adaptive rounds."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    try:
        stored = read_v2_artifact(path, initial_plan.run_id, V2_ADAPTIVE_COMPLETION_KEY)
    except KeyError:
        stored = None
    if stored is not None:
        return V2AdaptiveContinuationResult.model_validate_json(stored.payload_json)
    _validate_round_one_inputs(
        initial_plan, round_one_discovery, round_one_acquisition, round_one_gap
    )
    initial_pool = _merge_survivors(
        initial_plan.run_id, ((1, round_one_discovery, round_one_acquisition),)
    )
    if _cancelled(cancellation_requested):
        return _finish(
            path,
            initial_plan.run_id,
            (),
            initial_pool,
            V2AdaptiveStopCode.CANCELLED,
            "Research stopped because cancellation was requested.",
            1,
            now,
        )
    if round_one_gap.stop_adaptive_continuation:
        code = (
            V2AdaptiveStopCode.GAP_ANALYSIS_DEGRADED
            if round_one_gap.result is None
            else V2AdaptiveStopCode.ROUND_ONE_COMPLETE
        )
        reason = (
            "Adaptive continuation stopped because Round-1 Gap Analysis degraded safely."
            if round_one_gap.result is None
            else round_one_gap.result.stop_reason or "Luna recommended stopping after Round 1."
        )
        return _finish(path, initial_plan.run_id, (), initial_pool, code, reason, 1, now)

    attempts = dict(provider_attempts or {})
    planned_round_one_counts = Counter(query.provider for query in initial_plan.searches)
    for provider, count in planned_round_one_counts.items():
        attempts[provider] = max(attempts.get(provider, 0), count)
    history = tuple(query.query_text for query in initial_plan.searches)
    round_two = _run_round(
        path=path,
        round_number=2,
        initial_plan=initial_plan,
        gap_output=round_one_gap,
        previous_queries=history,
        provider_attempts=attempts,
        search_providers=search_providers,
        llm_provider=llm_provider,
        routing_config=routing_config,
        wigolo_provider=wigolo_provider,
        firecrawl_provider=firecrawl_provider,
        crossref_resolver=crossref_resolver,
        known_urls=_known_urls((round_one_discovery,)),
        base_pool=initial_pool,
        budget=budget,
        cancellation_requested=cancellation_requested,
        clock=now,
    )
    if isinstance(round_two, V2AdaptiveContinuationResult):
        return round_two
    plan_two, search_two, discovery_two, acquisition_two, summary_two = round_two
    pool_two = _merge_survivors(
        initial_plan.run_id,
        (
            (1, round_one_discovery, round_one_acquisition),
            (2, discovery_two, acquisition_two),
        ),
    )
    if summary_two.status is V2AdaptiveRoundStatus.CANCELLED:
        return _finish(
            path,
            initial_plan.run_id,
            (summary_two,),
            pool_two,
            V2AdaptiveStopCode.CANCELLED,
            "Research stopped at the Round-2 boundary because cancellation was requested.",
            2,
            now,
        )
    if not any(outcome.succeeded for outcome in search_two.outcomes):
        return _finish(
            path,
            initial_plan.run_id,
            (summary_two,),
            pool_two,
            V2AdaptiveStopCode.PROVIDER_FAILURE,
            "Round 2 stopped after all eligible search providers failed; "
            "completed work was preserved.",
            2,
            now,
        )

    gap_two_input = _round_two_gap_input(
        round_one_gap, plan_two, discovery_two, acquisition_two, budget
    )
    gap_two = run_v2_gap_analysis(
        db_path=path,
        gap_input=gap_two_input,
        llm_provider=llm_provider,
        routing_config=routing_config,
        clock=now,
    )
    if gap_two.stop_adaptive_continuation:
        code = (
            V2AdaptiveStopCode.GAP_ANALYSIS_DEGRADED
            if gap_two.result is None
            else V2AdaptiveStopCode.ROUND_TWO_COMPLETE
        )
        reason = (
            "Adaptive continuation stopped because post-Round-2 Gap Analysis degraded safely."
            if gap_two.result is None
            else gap_two.result.stop_reason or "Luna recommended stopping after Round 2."
        )
        return _finish(path, initial_plan.run_id, (summary_two,), pool_two, code, reason, 2, now)

    for query in plan_two.searches:
        attempts[query.provider] = attempts.get(query.provider, 0) + 1
    duplicate_rate = (
        summary_two.duplicate_source_count
        / (summary_two.new_source_count + summary_two.duplicate_source_count)
        if summary_two.new_source_count + summary_two.duplicate_source_count
        else 0.0
    )
    preliminary_reason = _round_three_precheck(
        gap_two,
        initial_plan,
        attempts,
        search_providers,
        duplicate_rate,
        budget,
        cancellation_requested,
    )
    if preliminary_reason is not None:
        decision = _rejected_governor(
            initial_plan.run_id, preliminary_reason, duplicate_rate, now()
        )
        return _finish(
            path,
            initial_plan.run_id,
            (summary_two,),
            pool_two,
            V2AdaptiveStopCode.GOVERNOR_REJECTED,
            decision.explanation,
            2,
            now,
            decision,
        )

    try:
        round_three_plan = _plan_round(
            path=path,
            round_number=3,
            initial_plan=initial_plan,
            gap_output=gap_two,
            previous_queries=(*history, *(query.query_text for query in plan_two.searches)),
            provider_attempts=attempts,
            search_providers=search_providers,
            llm_provider=llm_provider,
            routing_config=routing_config,
            budget=budget,
            clock=now,
        )
    except LLMInvocationError as exc:
        return _finish(
            path,
            initial_plan.run_id,
            (summary_two,),
            pool_two,
            V2AdaptiveStopCode.PROVIDER_FAILURE,
            f"Adaptive Search Agent failed; completed work was preserved: {exc}",
            2,
            now,
        )
    except (LookupError, ValueError) as exc:
        reason = (
            V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER
            if "provider" in str(exc).casefold()
            else V2RoundThreeReasonCode.NO_NEW_QUERY
        )
        decision = _rejected_governor(initial_plan.run_id, reason, duplicate_rate, now())
        insert_v2_artifact(
            path,
            "phase-7-round-3-governor-decision",
            decision,
            decision.decided_at,
        )
        return _finish(
            path,
            initial_plan.run_id,
            (summary_two,),
            pool_two,
            V2AdaptiveStopCode.GOVERNOR_REJECTED,
            decision.explanation,
            2,
            now,
            decision,
        )
    decision = evaluate_v2_round_three_authorization(
        V2RoundThreeGovernorInput(
            run_id=initial_plan.run_id,
            current_round=2,
            material_gap_remains=bool(gap_two.result and gap_two.result.material_gaps),
            luna_recommends_continue=bool(gap_two.result and gap_two.result.continue_research),
            new_search_direction_exists=bool(
                gap_two.result and gap_two.result.new_search_directions
            ),
            eligible_provider_exists=True,
            materially_new_queries=bool(round_three_plan.plan.searches),
            provider_ceiling_permits=True,
            protected_downstream_budget_remains=(
                budget.model_calls_remaining > budget.protected_downstream_model_calls + 2
            ),
            complete_workload_reservable=budget.round_three_complete_workload_reservable,
            round_two_duplicate_rate=duplicate_rate,
            decided_at=now(),
        )
    )
    insert_v2_artifact(path, "phase-7-round-3-governor-decision", decision, decision.decided_at)
    if not decision.authorized:
        return _finish(
            path,
            initial_plan.run_id,
            (summary_two,),
            pool_two,
            V2AdaptiveStopCode.GOVERNOR_REJECTED,
            decision.explanation,
            2,
            now,
            decision,
        )
    round_three = _run_round_from_plan(
        path=path,
        planned=round_three_plan,
        search_providers=search_providers,
        llm_provider=llm_provider,
        routing_config=routing_config,
        wigolo_provider=wigolo_provider,
        firecrawl_provider=firecrawl_provider,
        crossref_resolver=crossref_resolver,
        known_urls=_known_urls((round_one_discovery, discovery_two)),
        cancellation_requested=cancellation_requested,
        clock=now,
    )
    search_three, discovery_three, acquisition_three, summary_three = round_three
    pool_three = _merge_survivors(
        initial_plan.run_id,
        (
            (1, round_one_discovery, round_one_acquisition),
            (2, discovery_two, acquisition_two),
            (3, discovery_three, acquisition_three),
        ),
    )
    reason = (
        "Research stopped at the fixed three-round maximum after the narrow Round 3."
        if any(item.succeeded for item in search_three.outcomes)
        else "Research stopped at the fixed three-round maximum after Round-3 provider degradation."
    )
    return _finish(
        path,
        initial_plan.run_id,
        (summary_two, summary_three),
        pool_three,
        V2AdaptiveStopCode.ROUND_THREE_COMPLETE,
        reason,
        3,
        now,
        decision,
    )


def _run_round(
    *,
    path: str,
    round_number: int,
    initial_plan: V2InitialPlannerOutput,
    gap_output: V2GapAnalysisOutput,
    previous_queries: tuple[str, ...],
    provider_attempts: Mapping[DiscoveryProvider, int],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None,
    known_urls: frozenset[str],
    base_pool: V2MergedSurvivorPool,
    budget: V2AdaptiveBudgetState,
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
) -> (
    tuple[
        V2AdaptiveRoundPlan,
        V2AdaptiveSearchResults,
        V2DiscoveryScoutOutput,
        V2AcquisitionProbeOutput,
        V2AdaptiveRoundExecution,
    ]
    | V2AdaptiveContinuationResult
):
    if _cancelled(cancellation_requested):
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.CANCELLED,
            "Research stopped because cancellation was requested.",
            round_number - 1,
            clock,
        )
    try:
        planned = _plan_round(
            path=path,
            round_number=round_number,
            initial_plan=initial_plan,
            gap_output=gap_output,
            previous_queries=previous_queries,
            provider_attempts=provider_attempts,
            search_providers=search_providers,
            llm_provider=llm_provider,
            routing_config=routing_config,
            budget=budget,
            clock=clock,
        )
    except LLMInvocationError as exc:
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.PROVIDER_FAILURE,
            f"Adaptive Search Agent failed; completed work was preserved: {exc}",
            round_number - 1,
            clock,
        )
    except (LookupError, ValueError) as exc:
        code = (
            V2AdaptiveStopCode.NO_ELIGIBLE_PROVIDER
            if "provider" in str(exc).casefold()
            else V2AdaptiveStopCode.NO_NEW_QUERY
        )
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            code,
            str(exc),
            round_number - 1,
            clock,
        )
    search, discovery, acquisition, summary = _run_round_from_plan(
        path=path,
        planned=planned,
        search_providers=search_providers,
        llm_provider=llm_provider,
        routing_config=routing_config,
        wigolo_provider=wigolo_provider,
        firecrawl_provider=firecrawl_provider,
        crossref_resolver=crossref_resolver,
        known_urls=known_urls,
        cancellation_requested=cancellation_requested,
        clock=clock,
    )
    return planned.plan, search, discovery, acquisition, summary


def _plan_round(
    *,
    path: str,
    round_number: int,
    initial_plan: V2InitialPlannerOutput,
    gap_output: V2GapAnalysisOutput | V2GapAnalysisRunResult,
    previous_queries: tuple[str, ...],
    provider_attempts: Mapping[DiscoveryProvider, int],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    budget: V2AdaptiveBudgetState,
    clock: Callable[[], datetime],
) -> V2AdaptivePlannedRound:
    key = f"phase-7-round-{round_number}-plan"
    try:
        stored = read_v2_artifact(path, initial_plan.run_id, key)
    except KeyError:
        stored = None
    if stored is not None:
        return V2AdaptivePlannedRound.model_validate_json(stored.payload_json)
    if gap_output.result is None or not gap_output.result.continue_research:
        raise LookupError("Luna did not authorize a material adaptive search recommendation")
    budgets = _eligible_budgets(initial_plan, provider_attempts, search_providers)
    if not budgets:
        raise LookupError("No eligible enabled provider remains within its search ceiling.")
    maximum_queries = _maximum_queries(round_number, initial_plan, budgets)
    request_input = V2SearchAgentInput(
        run_id=initial_plan.run_id,
        exact_claim=initial_plan.raw_claim,
        round_number=round_number,
        directions=initial_plan.directions,
        eligible_providers=tuple(item.provider for item in budgets),
        material_gaps=gap_output.result.material_gaps,
        search_directions=gap_output.result.new_search_directions,
        discovered_terms=tuple(
            dict.fromkeys((*gap_output.input.discovered_terms, *gap_output.result.discovered_terms))
        )[:40],
        previous_queries=previous_queries,
        provider_budgets=budgets,
        maximum_queries=maximum_queries,
    )
    route = routing_config.preflight().for_stage(LLMStage.SEARCH_AGENT)
    if (
        route.logical_alias is not V2_LLM_ROUTING.for_stage(LLMStage.SEARCH_AGENT).primary
        or route.physical_model != "mimo-v2.5-pro"
    ):
        raise ValueError("v2 adaptive Search Agent requires MiMo-v2.5-Pro")
    prompt = load_prompt(LLMStage.SEARCH_AGENT)
    request = LLMRequest(
        run_id=initial_plan.run_id,
        stage=LLMStage.SEARCH_AGENT,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, request_input, V2AdaptiveSearchModelOutput),
        input_artifact=request_input,
        input_artifact_ids=(initial_plan.run_id,),
        requested_output_type=V2AdaptiveSearchModelOutput,
        model_alias=route.logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.SEARCH_AGENT).generation,
    )
    reservation = routing_config.preflight().reserve(
        LLMStage.SEARCH_AGENT, conservative_token_estimate(request.rendered_prompt)
    )
    _require_budget(budget, reservation.reserved_tokens, reservation.reserved_cost_usd)
    invocation = invoke_llm(llm_provider, request, clock=clock)
    response = invocation.output_artifact
    if not isinstance(response, V2AdaptiveSearchModelOutput):
        raise TypeError("Search Agent returned an unexpected typed artifact")
    plan = _validate_and_assemble_plan(request_input, response, prompt.version, clock())
    planned = V2AdaptivePlannedRound(
        run_id=initial_plan.run_id,
        plan=plan,
        reservation=V2SearchAgentReservation(
            input_tokens=reservation.input_tokens,
            output_tokens=reservation.output_tokens,
            reserved_tokens=reservation.reserved_tokens,
            reserved_cost_usd=reservation.reserved_cost_usd,
        ),
    )
    insert_v2_artifact(path, key, planned, plan.planned_at)
    return planned


def _validate_and_assemble_plan(
    request: V2SearchAgentInput,
    response: V2AdaptiveSearchModelOutput,
    prompt_version: str,
    planned_at: datetime,
) -> V2AdaptiveRoundPlan:
    if len(response.searches) > request.maximum_queries:
        raise ValueError("Search Agent exceeded the application-owned round query ceiling")
    gap_by_id = {gap.gap_id: gap for gap in request.material_gaps}
    counts: Counter[tuple[ResearchDirection, DiscoveryProvider]] = Counter()
    accepted: list[V2AdaptiveSearchQuery] = []
    history = list(request.previous_queries)
    for index, item in enumerate(response.searches, start=1):
        request.directions.require_permitted(item.direction)
        if item.provider not in request.eligible_providers:
            raise ValueError("Search Agent selected a disabled or ineligible provider")
        if any(gap_id not in gap_by_id for gap_id in item.targeted_gap_ids):
            raise ValueError("Search Agent query must target persisted Gap IDs")
        if any(
            gap_by_id[gap_id].direction is not item.direction for gap_id in item.targeted_gap_ids
        ):
            raise ValueError("Search Agent query direction must match every targeted Gap")
        if not queries_are_materially_new(item.query_text, tuple(history)):
            raise ValueError("Search Agent query repeats or trivially rewrites query history")
        counts[(item.direction, item.provider)] += 1
        cap = 1 if request.round_number == 3 else _ROUND_TWO_PER_DIRECTION_CAPS[item.provider]
        if counts[(item.direction, item.provider)] > cap:
            raise ValueError("Search Agent exceeded the authoritative provider-round lane")
        history.append(item.query_text)
        accepted.append(
            V2AdaptiveSearchQuery(
                run_id=request.run_id,
                query_id=uuid5(
                    NAMESPACE_URL,
                    f"researchassistant-v2-adaptive-query::{request.run_id}::{request.round_number}::{index}::{normalize_query_text(item.query_text)}",
                ),
                round_number=request.round_number,
                direction=item.direction,
                provider=item.provider,
                targeted_gap_ids=item.targeted_gap_ids,
                strategy=item.strategy,
                query_text=item.query_text,
                created_at=planned_at,
            )
        )
    if request.round_number == 3 and len(accepted) > 3:
        raise ValueError("Round 3 must remain narrow with at most three queries")
    return V2AdaptiveRoundPlan(
        run_id=request.run_id,
        round_number=request.round_number,
        directions=request.directions,
        enabled_providers=request.eligible_providers,
        targeted_gap_ids=tuple(
            dict.fromkeys(gap_id for item in accepted for gap_id in item.targeted_gap_ids)
        ),
        discovered_terms=request.discovered_terms,
        searches=tuple(accepted),
        search_agent_prompt_version=prompt_version,
        planned_at=planned_at,
    )


def _run_round_from_plan(
    *,
    path: str,
    planned: V2AdaptivePlannedRound,
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None,
    known_urls: frozenset[str],
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
) -> tuple[
    V2AdaptiveSearchResults,
    V2DiscoveryScoutOutput,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundExecution,
]:
    plan = planned.plan
    search = _execute_searches(path, plan, search_providers, cancellation_requested, clock)
    cancelled_after_search = _cancelled(cancellation_requested)
    responses = tuple(
        V2DiscoveryResponse(query=item.query, results=item.results)
        for item in search.outcomes
        if item.succeeded
    )
    if responses and not cancelled_after_search:
        discovery = run_v2_discovery_and_scout(
            db_path=path,
            planner_output=plan,
            responses=responses,
            llm_provider=llm_provider,
            routing_config=routing_config,
            clock=clock,
            crossref_resolver=crossref_resolver,
        ).output
    else:
        discovery = V2DiscoveryScoutOutput(
            run_id=plan.run_id,
            directions=plan.directions,
            items=(),
            clusters=(),
            scout_batches=(),
            scout_audits=(),
            completed_at=clock(),
        )
        insert_v2_artifact(
            path,
            f"phase-7-round-{plan.round_number}-discovery-scout",
            discovery,
            discovery.completed_at,
        )
    duplicate_ids = frozenset(
        cluster.cluster_id for cluster in discovery.clusters if _cluster_urls(cluster) & known_urls
    )
    cancelled_before_acquisition = _cancelled(cancellation_requested)
    if discovery.items and not cancelled_before_acquisition:
        acquisition = run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            excluded_cluster_ids=duplicate_ids,
            clock=clock,
        ).output
    else:
        acquisition = V2AcquisitionProbeOutput(
            run_id=plan.run_id,
            directions=plan.directions,
            acquisitions=(),
            attempts=(),
            probes=(),
            survivors=(),
            completed_at=clock(),
        )
        insert_v2_artifact(
            path,
            f"phase-7-round-{plan.round_number}-acquisition-probe",
            acquisition,
            acquisition.completed_at,
        )
    cancelled = (
        cancelled_after_search or cancelled_before_acquisition or _cancelled(cancellation_requested)
    )
    summary = V2AdaptiveRoundExecution(
        run_id=plan.run_id,
        round_number=plan.round_number,
        targeted_gap_ids=plan.targeted_gap_ids,
        status=(
            V2AdaptiveRoundStatus.CANCELLED
            if cancelled
            else V2AdaptiveRoundStatus.DEGRADED
            if any(not item.succeeded for item in search.outcomes)
            else V2AdaptiveRoundStatus.COMPLETED
        ),
        planned_query_count=len(plan.searches),
        completed_query_count=sum(item.succeeded for item in search.outcomes),
        failed_query_count=sum(not item.succeeded for item in search.outcomes),
        new_source_count=len(discovery.clusters) - len(duplicate_ids),
        duplicate_source_count=len(duplicate_ids),
        survivor_additions=len(acquisition.survivors),
        completed_at=clock(),
    )
    insert_v2_artifact(
        path, f"phase-7-round-{plan.round_number}-execution", summary, summary.completed_at
    )
    return search, discovery, acquisition, summary


def _execute_searches(
    path: str,
    plan: V2AdaptiveRoundPlan,
    providers: Mapping[DiscoveryProvider, SearchProvider],
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
) -> V2AdaptiveSearchResults:
    key = f"phase-7-round-{plan.round_number}-search-results"
    try:
        stored = read_v2_artifact(path, plan.run_id, key)
    except KeyError:
        stored = None
    if stored is not None:
        return V2AdaptiveSearchResults.model_validate_json(stored.payload_json)
    outcomes: list[V2AdaptiveSearchOutcome] = []
    for query in plan.searches:
        if _cancelled(cancellation_requested):
            break
        provider = providers[query.provider]
        try:
            response = provider.search(
                SearchRequest(
                    run_id=plan.run_id,
                    provider=query.provider,
                    intent=(
                        SearchIntent.ACADEMIC_STUDY
                        if query.provider
                        in {
                            DiscoveryProvider.OPENALEX,
                            DiscoveryProvider.ARXIV,
                            DiscoveryProvider.PUBMED,
                        }
                        else SearchIntent.BROAD_WEB
                    ),
                    query_text=query.query_text,
                    limit=5,
                )
            )
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query, succeeded=True, results=tuple(response.results)
                )
            )
        except SearchProviderError as exc:
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query,
                    succeeded=False,
                    failure_code=exc.code.value,
                    failure_message=str(exc) or exc.code.value,
                )
            )
        except Exception as exc:
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query,
                    succeeded=False,
                    failure_code=SearchFailureCode.PERMANENT_FAILURE.value,
                    failure_message=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
    result = V2AdaptiveSearchResults(
        run_id=plan.run_id,
        round_number=plan.round_number,
        outcomes=tuple(outcomes),
        completed_at=clock(),
    )
    insert_v2_artifact(path, key, result, result.completed_at)
    return result


def _round_two_gap_input(
    round_one_gap: V2GapAnalysisOutput,
    plan: V2AdaptiveRoundPlan,
    discovery: V2DiscoveryScoutOutput,
    acquisition: V2AcquisitionProbeOutput,
    budget: V2AdaptiveBudgetState,
) -> V2GapAnalysisInput:
    cluster_by_id = {item.cluster_id: item for item in discovery.clusters}
    item_by_id = {item.item_id: item for item in discovery.items}
    source_by_snapshot = {item.snapshot.snapshot_id: item for item in acquisition.acquisitions}
    new_sources: list[V2GapSurvivingSourceMetadata] = []
    new_passages: list[V2GapProbePassage] = []
    for survivor in acquisition.survivors:
        cluster = cluster_by_id[survivor.cluster_id]
        representative = min(
            (item_by_id[item_id] for item_id in cluster.item_ids),
            key=lambda item: item.provider_rank,
        )
        source = source_by_snapshot[survivor.snapshot_id]
        new_sources.append(
            V2GapSurvivingSourceMetadata(
                source_cluster_id=survivor.cluster_id,
                direction=survivor.direction,
                snapshot_id=survivor.snapshot_id,
                snapshot_sha256=survivor.snapshot_sha256,
                source_url=source.snapshot.source_url,
                title=representative.title,
                source_family_id=f"cluster:{survivor.cluster_id}",
            )
        )
        probe = next(
            item for item in acquisition.probes if item.snapshot_id == survivor.snapshot_id
        )
        passages = {item.passage_id: item for item in probe.passages}
        for passage_id in survivor.passage_ids:
            passage = passages[passage_id]
            new_passages.append(
                V2GapProbePassage(
                    passage_id=passage_id,
                    source_cluster_id=survivor.cluster_id,
                    direction=survivor.direction,
                    text=passage.text[:1200],
                    truncated_for_gap_analysis=len(passage.text) > 1200,
                )
            )
    failures = tuple(
        V2GapAcquisitionFailure(
            source_cluster_id=item.cluster_id,
            direction=_cluster_direction(item.cluster_id, discovery),
            provider=item.provider,
            failure_code=item.failure_code or "unspecified",
        )
        for item in acquisition.attempts
        if not item.succeeded
    )
    families = tuple(
        V2GapSourceFamily(
            family_id=f"cluster:{item.source_cluster_id}",
            direction=item.direction,
            source_cluster_ids=(item.source_cluster_id,),
            discovery_providers=tuple(
                dict.fromkeys(
                    ref.provider
                    for ref in cluster_by_id[item.source_cluster_id].provider_references
                )
            ),
        )
        for item in new_sources
    )
    duplicates = tuple(
        V2GapDuplicatePattern(
            source_cluster_id=cluster.cluster_id,
            direction=_cluster_direction(cluster.cluster_id, discovery),
            duplicate_discovery_count=len(cluster.item_ids),
            pattern="conservatively clustered same-source discovery records",
        )
        for cluster in discovery.clusters
        if len(cluster.item_ids) > 1
    )
    prior = round_one_gap.input
    return V2GapAnalysisInput(
        run_id=prior.run_id,
        exact_claim=prior.exact_claim,
        directions=prior.directions,
        completed_round=2,
        attempted_queries=(
            *prior.attempted_queries,
            *(
                V2GapAttemptedQuery(
                    query_id=item.query_id,
                    direction=item.direction,
                    provider=item.provider,
                    strategy=item.strategy,
                    query_text=item.query_text,
                )
                for item in plan.searches
            ),
        ),
        surviving_sources=(*prior.surviving_sources, *new_sources),
        probe_passages=tuple((*new_passages, *prior.probe_passages))[:40],
        source_families=(*prior.source_families, *families),
        discovered_terms=tuple(dict.fromkeys((*prior.discovered_terms, *plan.discovered_terms)))[
            :40
        ],
        duplicate_patterns=tuple((*prior.duplicate_patterns, *duplicates))[:25],
        acquisition_failures=tuple((*prior.acquisition_failures, *failures))[:150],
        previous_gaps=round_one_gap.result.material_gaps if round_one_gap.result else (),
        remaining_budget=V2GapBudgetState(
            model_calls_remaining=max(0, budget.model_calls_remaining - 1),
            tokens_remaining=budget.tokens_remaining,
            cost_remaining_usd=budget.cost_remaining_usd,
        ),
    )


def _eligible_budgets(
    plan: V2InitialPlannerOutput,
    attempted: Mapping[DiscoveryProvider, int],
    providers: Mapping[DiscoveryProvider, SearchProvider],
) -> tuple[V2ProviderSearchBudget, ...]:
    return tuple(
        V2ProviderSearchBudget(
            provider=provider,
            attempted_calls=attempted.get(provider, 0),
            maximum_calls=_PROVIDER_TOTAL_CEILINGS[provider],
        )
        for provider in plan.discovery_providers
        if provider in providers and attempted.get(provider, 0) < _PROVIDER_TOTAL_CEILINGS[provider]
    )


def _maximum_queries(
    round_number: int, plan: V2InitialPlannerOutput, budgets: tuple[V2ProviderSearchBudget, ...]
) -> int:
    if round_number == 3:
        return min(3, sum(min(1, item.remaining_calls) for item in budgets))
    return min(
        12,
        sum(
            min(
                _ROUND_TWO_PER_DIRECTION_CAPS[item.provider]
                * len(plan.directions.enabled_directions),
                item.remaining_calls,
            )
            for item in budgets
        ),
    )


def _round_three_precheck(
    gap: V2GapAnalysisRunResult,
    plan: V2InitialPlannerOutput,
    attempted: Mapping[DiscoveryProvider, int],
    providers: Mapping[DiscoveryProvider, SearchProvider],
    duplicate_rate: float,
    budget: V2AdaptiveBudgetState,
    cancellation_requested: Callable[[], bool] | None,
) -> V2RoundThreeReasonCode | None:
    if _cancelled(cancellation_requested):
        return V2RoundThreeReasonCode.CANCELLED
    if duplicate_rate >= 0.70:
        return V2RoundThreeReasonCode.DUPLICATE_HEAVY
    if not _eligible_budgets(plan, attempted, providers):
        return V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER
    if budget.model_calls_remaining <= budget.protected_downstream_model_calls + 2:
        return V2RoundThreeReasonCode.PROTECTED_BUDGET
    if not budget.round_three_complete_workload_reservable:
        return V2RoundThreeReasonCode.INSUFFICIENT_RESERVATION
    if gap.result is None or not gap.result.material_gaps:
        return V2RoundThreeReasonCode.NO_MATERIAL_GAP
    if not gap.result.new_search_directions:
        return V2RoundThreeReasonCode.NO_NEW_DIRECTION
    return None


def _rejected_governor(
    run_id: UUID, reason: V2RoundThreeReasonCode, duplicate_rate: float, decided_at: datetime
) -> V2RoundThreeGovernorDecision:
    probe = V2RoundThreeGovernorInput(
        run_id=run_id,
        current_round=2,
        material_gap_remains=reason is not V2RoundThreeReasonCode.NO_MATERIAL_GAP,
        luna_recommends_continue=reason is not V2RoundThreeReasonCode.LUNA_STOP,
        new_search_direction_exists=reason is not V2RoundThreeReasonCode.NO_NEW_DIRECTION,
        eligible_provider_exists=reason is not V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER,
        materially_new_queries=reason is not V2RoundThreeReasonCode.NO_NEW_QUERY,
        provider_ceiling_permits=reason is not V2RoundThreeReasonCode.PROVIDER_CEILING,
        protected_downstream_budget_remains=reason is not V2RoundThreeReasonCode.PROTECTED_BUDGET,
        complete_workload_reservable=reason is not V2RoundThreeReasonCode.INSUFFICIENT_RESERVATION,
        round_two_duplicate_rate=duplicate_rate,
        cancelled=reason is V2RoundThreeReasonCode.CANCELLED,
        terminal_provider_failure=reason is V2RoundThreeReasonCode.TERMINAL_FAILURE,
        decided_at=decided_at,
    )
    decision = evaluate_v2_round_three_authorization(probe)
    if decision.reason_code is not reason:
        raise ValueError("v2 Governor rejection facts did not reproduce their reason code")
    return decision


def _merge_survivors(
    run_id: UUID, rounds: tuple[tuple[int, V2DiscoveryScoutOutput, V2AcquisitionProbeOutput], ...]
) -> V2MergedSurvivorPool:
    merged: list[V2MergedSurvivor] = []
    seen: set[str] = set()
    for round_number, _discovery, acquisition in rounds:
        by_snapshot = {item.snapshot.snapshot_id: item for item in acquisition.acquisitions}
        for survivor in acquisition.survivors:
            source_url = by_snapshot[survivor.snapshot_id].snapshot.source_url
            identity = canonical_discovery_url(source_url)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(
                V2MergedSurvivor(
                    research_round=round_number, source_url=source_url, survivor=survivor
                )
            )
    return V2MergedSurvivorPool(run_id=run_id, sources=tuple(merged))


def _known_urls(outputs: tuple[V2DiscoveryScoutOutput, ...]) -> frozenset[str]:
    return frozenset(
        url for output in outputs for cluster in output.clusters for url in _cluster_urls(cluster)
    )


def _cluster_urls(cluster: SourceCluster) -> frozenset[str]:
    return frozenset(
        canonical_discovery_url(url)
        for url in (cluster.preferred_url, cluster.canonical_url, *cluster.alternate_urls)
    )


def _cluster_direction(cluster_id: UUID, output: V2DiscoveryScoutOutput) -> ResearchDirection:
    cluster = next(item for item in output.clusters if item.cluster_id == cluster_id)
    items = {item.item_id: item for item in output.items}
    return min(
        (items[item_id] for item_id in cluster.item_ids), key=lambda item: item.provider_rank
    ).direction


def _require_budget(budget: V2AdaptiveBudgetState, tokens: int, cost: Decimal) -> None:
    if budget.model_calls_remaining <= budget.protected_downstream_model_calls:
        raise LookupError("Insufficient protected model-call budget for adaptive search.")
    if budget.tokens_remaining is not None and tokens > budget.tokens_remaining:
        raise LookupError("Insufficient token budget for adaptive Search Agent reservation.")
    if (
        budget.cost_remaining_usd is not None
        and add_usd(Decimal("0"), cost) > budget.cost_remaining_usd
    ):
        raise LookupError("Insufficient cost budget for adaptive Search Agent reservation.")


def _validate_round_one_inputs(
    initial: V2InitialPlannerOutput,
    discovery: V2DiscoveryScoutOutput,
    acquisition: V2AcquisitionProbeOutput,
    gap: V2GapAnalysisOutput,
) -> None:
    if {initial.run_id, discovery.run_id, acquisition.run_id, gap.run_id} != {initial.run_id}:
        raise ValueError("all adaptive continuation inputs must share one run_id")
    if gap.input.completed_round != 1:
        raise ValueError("adaptive continuation must begin from completed Round-1 Gap Analysis")


def _finish(
    path: str,
    run_id: UUID,
    rounds: tuple[V2AdaptiveRoundExecution, ...],
    pool: V2MergedSurvivorPool,
    code: V2AdaptiveStopCode,
    reason: str,
    completed_rounds: int,
    clock: Callable[[], datetime],
    governor: V2RoundThreeGovernorDecision | None = None,
) -> V2AdaptiveContinuationResult:
    completed_at = clock()
    result = V2AdaptiveContinuationResult(
        run_id=run_id,
        rounds=rounds,
        merged_survivors=pool,
        stopping_decision=V2AdaptiveStoppingDecision(
            run_id=run_id,
            completed_rounds=completed_rounds,
            stop_code=code,
            stopping_reason=reason,
            decided_at=completed_at,
        ),
        governor_decision=governor,
        completed_at=completed_at,
    )
    insert_v2_artifact(
        path,
        "phase-7-merged-survivor-pool",
        pool,
        completed_at,
    )
    insert_v2_artifact(
        path,
        "phase-7-stopping-decision",
        result.stopping_decision,
        completed_at,
    )
    insert_v2_artifact(path, V2_ADAPTIVE_COMPLETION_KEY, result, completed_at)
    return result


def _cancelled(callback: Callable[[], bool] | None) -> bool:
    return bool(callback and callback())


def _utc_now() -> datetime:
    return datetime.now(UTC)
