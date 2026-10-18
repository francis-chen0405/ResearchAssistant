"""Budget-aware Round-2/3 continuation and compatible adaptive-search exports."""

from __future__ import annotations

import re as re
from collections import Counter as Counter
from collections.abc import Callable as Callable
from collections.abc import Mapping as Mapping
from datetime import UTC as UTC
from datetime import datetime as datetime
from decimal import Decimal as Decimal
from enum import StrEnum as StrEnum
from hashlib import sha256 as sha256
from pathlib import Path as Path
from typing import Literal as Literal
from uuid import NAMESPACE_URL as NAMESPACE_URL
from uuid import UUID as UUID
from uuid import uuid5 as uuid5

from pydantic import (
    ConfigDict as ConfigDict,
)
from pydantic import (
    Field as Field,
)
from pydantic import (
    field_validator as field_validator,
)
from pydantic import (
    model_validator as model_validator,
)

from researchassistant.agents.adaptive_execution import (
    _execute_searches as _execute_searches,
)
from researchassistant.agents.adaptive_execution import (
    _run_round_from_plan as _run_round_from_plan,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveBudgetError as V2AdaptiveBudgetError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveBudgetState as V2AdaptiveBudgetState,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveCancellationError as V2AdaptiveCancellationError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveContinuationResult as V2AdaptiveContinuationResult,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveNoContinuationError as V2AdaptiveNoContinuationError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveNoEligibleProviderError as V2AdaptiveNoEligibleProviderError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptivePlannedRound as V2AdaptivePlannedRound,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptivePlanValidationError as V2AdaptivePlanValidationError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveRoundExecution as V2AdaptiveRoundExecution,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveRoundStatus as V2AdaptiveRoundStatus,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveSearchOutcome as V2AdaptiveSearchOutcome,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveSearchResults as V2AdaptiveSearchResults,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveStopCode as V2AdaptiveStopCode,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveStoppingDecision as V2AdaptiveStoppingDecision,
)
from researchassistant.agents.adaptive_handoffs import (
    V2MergedSurvivor as V2MergedSurvivor,
)
from researchassistant.agents.adaptive_handoffs import (
    V2MergedSurvivorPool as V2MergedSurvivorPool,
)
from researchassistant.agents.adaptive_handoffs import (
    V2PlanningAttempt as V2PlanningAttempt,
)
from researchassistant.agents.adaptive_handoffs import (
    V2PlanningOutcome as V2PlanningOutcome,
)
from researchassistant.agents.adaptive_handoffs import (
    V2PlanningRepairInput as V2PlanningRepairInput,
)
from researchassistant.agents.adaptive_handoffs import (
    V2SearchAgentReservation as V2SearchAgentReservation,
)
from researchassistant.agents.adaptive_handoffs import (
    _aware_datetime as _aware_datetime,
)
from researchassistant.agents.adaptive_handoffs import (
    _cancelled as _cancelled,
)
from researchassistant.agents.adaptive_handoffs import (
    _utc_now as _utc_now,
)
from researchassistant.agents.adaptive_handoffs import (
    round_artifact_key as round_artifact_key,
)
from researchassistant.agents.adaptive_planning import (
    _PROVIDER_TOTAL_CEILINGS as _PROVIDER_TOTAL_CEILINGS,
)
from researchassistant.agents.adaptive_planning import (
    _ROUND_TWO_PER_DIRECTION_CAPS as _ROUND_TWO_PER_DIRECTION_CAPS,
)
from researchassistant.agents.adaptive_planning import (
    _TOKEN_RE as _TOKEN_RE,
)
from researchassistant.agents.adaptive_planning import (
    _adaptive_concept_lanes as _adaptive_concept_lanes,
)
from researchassistant.agents.adaptive_planning import (
    _eligible_budgets as _eligible_budgets,
)
from researchassistant.agents.adaptive_planning import (
    _maximum_queries as _maximum_queries,
)
from researchassistant.agents.adaptive_planning import (
    _plan_round as _plan_round_owned,
)
from researchassistant.agents.adaptive_planning import (
    _plan_with_repair as _plan_with_repair,
)
from researchassistant.agents.adaptive_planning import (
    _require_budget as _require_budget,
)
from researchassistant.agents.adaptive_planning import (
    _validate_and_assemble_plan as _validate_and_assemble_plan,
)
from researchassistant.agents.adaptive_planning import (
    normalize_query_text as normalize_query_text,
)
from researchassistant.agents.adaptive_planning import (
    queries_are_materially_new as queries_are_materially_new,
)
from researchassistant.agents.adaptive_summary import (
    V2_ADAPTIVE_COMPLETION_KEY as V2_ADAPTIVE_COMPLETION_KEY,
)
from researchassistant.agents.adaptive_summary import (
    _cluster_direction as _cluster_direction,
)
from researchassistant.agents.adaptive_summary import (
    _cluster_urls as _cluster_urls,
)
from researchassistant.agents.adaptive_summary import (
    _finish as _finish,
)
from researchassistant.agents.adaptive_summary import (
    _known_urls as _known_urls,
)
from researchassistant.agents.adaptive_summary import (
    _merge_survivors as _merge_survivors,
)
from researchassistant.agents.adaptive_summary import (
    _round_two_gap_input as _round_two_gap_input,
)
from researchassistant.agents.adaptive_summary import (
    _validate_round_one_inputs as _validate_round_one_inputs,
)
from researchassistant.agents.v2_acquisition import (
    run_v2_acquisition_probe as run_v2_acquisition_probe,
)
from researchassistant.agents.v2_discovery import (
    V2DiscoveryResponse as V2DiscoveryResponse,
)
from researchassistant.agents.v2_discovery import (
    run_v2_discovery_and_scout as run_v2_discovery_and_scout,
)
from researchassistant.agents.v2_gap_analysis import (
    V2GapAnalysisRunResult as V2GapAnalysisRunResult,
)
from researchassistant.agents.v2_gap_analysis import (
    run_v2_gap_analysis as run_v2_gap_analysis,
)
from researchassistant.common.money import add_usd as add_usd
from researchassistant.common.resources import prompt_resource as prompt_resource
from researchassistant.contracts.discovery_v2 import (
    SearchMode as SearchMode,
)
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction as V2CompiledQueryAction,
)
from researchassistant.contracts.discovery_v2 import (
    V2ConceptGroup as V2ConceptGroup,
)
from researchassistant.contracts.discovery_v2 import (
    V2ConceptualQuery as V2ConceptualQuery,
)
from researchassistant.contracts.discovery_v2 import (
    V2GraphNeighborAction as V2GraphNeighborAction,
)
from researchassistant.contracts.discovery_v2 import (
    V2MetadataDiscoveryPolicy as V2MetadataDiscoveryPolicy,
)
from researchassistant.contracts.discovery_v2 import (
    discovery_id as discovery_id,
)
from researchassistant.contracts.model_research import (
    V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY as V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
)
from researchassistant.contracts.model_research import (
    V2AcquisitionPolicy as V2AcquisitionPolicy,
)
from researchassistant.contracts.models import (
    CrossrefIdentityMetadata as CrossrefIdentityMetadata,
)
from researchassistant.contracts.models import (
    DiscoveryProvider as DiscoveryProvider,
)
from researchassistant.contracts.models import (
    ResearchDirection as ResearchDirection,
)
from researchassistant.contracts.models import (
    SourceCluster as SourceCluster,
)
from researchassistant.contracts.models import (
    StrictModel as StrictModel,
)
from researchassistant.contracts.models import (
    V2AcquisitionProbeOutput as V2AcquisitionProbeOutput,
)
from researchassistant.contracts.models import (
    V2AdaptiveRoundPlan as V2AdaptiveRoundPlan,
)
from researchassistant.contracts.models import (
    V2AdaptiveSearchConceptsOutput as V2AdaptiveSearchConceptsOutput,
)
from researchassistant.contracts.models import (
    V2AdaptiveSearchModelOutput as V2AdaptiveSearchModelOutput,
)
from researchassistant.contracts.models import (
    V2AdaptiveSearchProposal as V2AdaptiveSearchProposal,
)
from researchassistant.contracts.models import (
    V2AdaptiveSearchQuery as V2AdaptiveSearchQuery,
)
from researchassistant.contracts.models import (
    V2DiscoveryScoutOutput as V2DiscoveryScoutOutput,
)
from researchassistant.contracts.models import (
    V2GapAcquisitionFailure as V2GapAcquisitionFailure,
)
from researchassistant.contracts.models import (
    V2GapAnalysisInput as V2GapAnalysisInput,
)
from researchassistant.contracts.models import (
    V2GapAnalysisOutput as V2GapAnalysisOutput,
)
from researchassistant.contracts.models import (
    V2GapAttemptedQuery as V2GapAttemptedQuery,
)
from researchassistant.contracts.models import (
    V2GapBudgetState as V2GapBudgetState,
)
from researchassistant.contracts.models import (
    V2GapDuplicatePattern as V2GapDuplicatePattern,
)
from researchassistant.contracts.models import (
    V2GapProbePassage as V2GapProbePassage,
)
from researchassistant.contracts.models import (
    V2GapSourceFamily as V2GapSourceFamily,
)
from researchassistant.contracts.models import (
    V2GapSurvivingSourceMetadata as V2GapSurvivingSourceMetadata,
)
from researchassistant.contracts.models import (
    V2InitialPlannerOutput as V2InitialPlannerOutput,
)
from researchassistant.contracts.models import (
    V2ProviderSearchBudget as V2ProviderSearchBudget,
)
from researchassistant.contracts.models import (
    V2SearchAgentInput as V2SearchAgentInput,
)
from researchassistant.contracts.models import (
    V2SurvivingSource as V2SurvivingSource,
)
from researchassistant.contracts.query_compiler import (
    compile_query as compile_query,
)
from researchassistant.contracts.query_compiler import (
    conceptual_signature as conceptual_signature,
)
from researchassistant.contracts.query_planning import (
    V2ConceptualAdaptiveLane as V2ConceptualAdaptiveLane,
)
from researchassistant.contracts.query_planning import (
    V2ConceptualSearchAgentInput as V2ConceptualSearchAgentInput,
)
from researchassistant.contracts.query_planning import (
    V2NeighborhoodSearchAgentInput as V2NeighborhoodSearchAgentInput,
)
from researchassistant.contracts.query_planning import (
    V2NeighborhoodSearchOutput as V2NeighborhoodSearchOutput,
)
from researchassistant.contracts.search import (
    SearchFailureCode as SearchFailureCode,
)
from researchassistant.contracts.search import (
    SearchResult as SearchResult,
)
from researchassistant.providers.llm import (
    V2_LLM_ROUTING as V2_LLM_ROUTING,
)
from researchassistant.providers.llm import (
    LLMInvocationError as LLMInvocationError,
)
from researchassistant.providers.llm import (
    LLMProvider as LLMProvider,
)
from researchassistant.providers.llm import (
    LLMRequest as LLMRequest,
)
from researchassistant.providers.llm import (
    LLMResponseValidationError as LLMResponseValidationError,
)
from researchassistant.providers.llm import (
    LLMStage as LLMStage,
)
from researchassistant.providers.llm import (
    invoke_llm as invoke_llm,
)
from researchassistant.providers.llm import (
    load_prompt as load_prompt,
)
from researchassistant.providers.llm import (
    load_prompt_file as load_prompt_file,
)
from researchassistant.providers.llm import (
    render_stage_prompt as render_stage_prompt,
)
from researchassistant.providers.mimo import (
    MimoFailureCode as MimoFailureCode,
)
from researchassistant.providers.mimo import (
    MimoProviderError as MimoProviderError,
)
from researchassistant.providers.pricing import (
    conservative_token_estimate as conservative_token_estimate,
)
from researchassistant.providers.ranking import canonical_discovery_url as canonical_discovery_url
from researchassistant.providers.scraper import ScraperProvider as ScraperProvider
from researchassistant.providers.search import (
    SearchProvider as SearchProvider,
)
from researchassistant.providers.search import (
    SearchProviderError as SearchProviderError,
)
from researchassistant.providers.v2_routing import V2RoutingConfig as V2RoutingConfig
from researchassistant.research.query_execution import (
    available_query_budgets as available_query_budgets,
)
from researchassistant.research.query_execution import (
    execute_query as execute_query,
)
from researchassistant.research.query_execution import (
    fair_query_order as fair_query_order,
)
from researchassistant.research.research_governor import (
    V2RoundThreeGovernorDecision as V2RoundThreeGovernorDecision,
)
from researchassistant.research.research_governor import (
    V2RoundThreeGovernorInput as V2RoundThreeGovernorInput,
)
from researchassistant.research.research_governor import (
    V2RoundThreeReasonCode as V2RoundThreeReasonCode,
)
from researchassistant.research.research_governor import (
    evaluate_v2_round_three_authorization as evaluate_v2_round_three_authorization,
)
from researchassistant.research.seed_expansion import (
    execute_expansion as execute_expansion,
)
from researchassistant.research.seed_expansion import (
    offer_expansions as offer_expansions,
)
from researchassistant.storage.discovery_store import (
    read_discovery_binding as read_discovery_binding,
)
from researchassistant.storage.store import (
    insert_v2_artifact as insert_v2_artifact,
)
from researchassistant.storage.store import (
    read_v2_artifact as read_v2_artifact,
)


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
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
    legacy_prompt: bool = False,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState] | None = None,
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
    legacy_prompt = legacy_prompt or all(
        query.compiled_query is None for query in initial_plan.searches
    )
    resolved_query_modes = dict(query_modes or {})
    for query in initial_plan.searches:
        if query.compiled_query is not None:
            resolved_query_modes.setdefault(query.provider, query.compiled_query.mode)
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
        previous_compiled_queries=tuple(
            query.compiled_query
            for query in initial_plan.searches
            if query.compiled_query is not None
        ),
        search_providers=search_providers,
        llm_provider=llm_provider,
        routing_config=routing_config,
        query_modes=resolved_query_modes,
        legacy_prompt=legacy_prompt,
        wigolo_provider=wigolo_provider,
        firecrawl_provider=firecrawl_provider,
        crossref_resolver=crossref_resolver,
        known_urls=_known_urls((round_one_discovery,)),
        base_pool=initial_pool,
        budget=budget,
        budget_snapshot=budget_snapshot,
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

    budget = budget_snapshot() if budget_snapshot else budget
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
    budget = budget_snapshot() if budget_snapshot else budget
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
    try:
        saved_governor = read_v2_artifact(
            path, initial_plan.run_id, "phase-7-round-3-governor-decision"
        )
    except KeyError:
        saved_governor = None
    prior_decision = (
        V2RoundThreeGovernorDecision.model_validate_json(saved_governor.payload_json)
        if saved_governor is not None
        else None
    )

    def authorization_time() -> datetime:
        return prior_decision.decided_at if prior_decision is not None else now()

    previously_authorized = prior_decision is not None and prior_decision.authorized
    # Authorization is a completed checkpoint. Later physical exposure cannot
    # revoke its historical facts; every remaining call still uses current accounting.
    preliminary_reason = (
        None
        if previously_authorized
        else _round_three_precheck(
            gap_two,
            initial_plan,
            attempts,
            search_providers,
            duplicate_rate,
            budget,
            cancellation_requested,
        )
    )
    if preliminary_reason is not None:
        decision = _rejected_governor(
            initial_plan.run_id, preliminary_reason, duplicate_rate, authorization_time()
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
            previous_queries=(
                *history,
                *(query.query_text for query in plan_two.searches if query.query_text is not None),
            ),
            provider_attempts=attempts,
            previous_compiled_queries=tuple(
                query.compiled_query
                for query in (*initial_plan.searches, *plan_two.searches)
                if query.compiled_query is not None
            ),
            search_providers=search_providers,
            llm_provider=llm_provider,
            routing_config=routing_config,
            query_modes=resolved_query_modes,
            legacy_prompt=legacy_prompt,
            budget=budget,
            budget_snapshot=budget_snapshot,
            cancellation_requested=cancellation_requested,
            clock=now,
        )
    except V2AdaptiveCancellationError:
        return _finish(
            path,
            initial_plan.run_id,
            (summary_two,),
            pool_two,
            V2AdaptiveStopCode.CANCELLED,
            "Research stopped before follow-up search planning.",
            2,
            now,
        )
    except LLMResponseValidationError as exc:
        reason = V2RoundThreeReasonCode.INVALID_SEARCH_AGENT_PLAN
        decision = _rejected_governor(
            initial_plan.run_id, reason, duplicate_rate, authorization_time()
        )
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
            V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN,
            f"Search Agent plan validation failed; completed work was preserved: {exc}",
            2,
            now,
            decision,
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
    except V2AdaptivePlanValidationError as exc:
        reason = V2RoundThreeReasonCode.INVALID_SEARCH_AGENT_PLAN
        decision = _rejected_governor(
            initial_plan.run_id, reason, duplicate_rate, authorization_time()
        )
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
            V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN,
            f"Search Agent plan validation failed; completed work was preserved: {exc}",
            2,
            now,
            decision,
        )
    except V2AdaptiveNoEligibleProviderError as exc:
        reason = V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER
        decision = _rejected_governor(
            initial_plan.run_id, reason, duplicate_rate, authorization_time()
        )
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
            V2AdaptiveStopCode.NO_ELIGIBLE_PROVIDER,
            str(exc),
            2,
            now,
            decision,
        )
    except V2AdaptiveBudgetError as exc:
        reason = V2RoundThreeReasonCode.PROTECTED_BUDGET
        decision = _rejected_governor(
            initial_plan.run_id, reason, duplicate_rate, authorization_time()
        )
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
            V2AdaptiveStopCode.BUDGET,
            str(exc),
            2,
            now,
            decision,
        )
    except V2AdaptiveNoContinuationError:
        reason = V2RoundThreeReasonCode.LUNA_STOP
        decision = _rejected_governor(
            initial_plan.run_id, reason, duplicate_rate, authorization_time()
        )
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
    except (LookupError, ValueError):
        reason = V2RoundThreeReasonCode.NO_NEW_QUERY
        decision = _rejected_governor(
            initial_plan.run_id, reason, duplicate_rate, authorization_time()
        )
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
                previously_authorized
                or budget.model_calls_remaining > budget.protected_downstream_model_calls + 2
            ),
            complete_workload_reservable=(
                previously_authorized or budget.round_three_complete_workload_reservable
            ),
            round_two_duplicate_rate=duplicate_rate,
            decided_at=authorization_time(),
        )
    )
    insert_v2_artifact(
        path,
        "phase-7-round-3-governor-decision",
        decision,
        saved_governor.created_at if saved_governor is not None else decision.decided_at,
    )
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
        exact_claim=initial_plan.raw_claim,
        asserted_components=tuple(
            x.claim_component
            for x in initial_plan.claim_coverage_focus
            if x.claim_component in initial_plan.raw_claim
        ),
        preview_gaps=tuple(x.missing_evidence for x in gap_two.result.material_gaps)[:6]
        if gap_two.result is not None
        else (),
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
    if summary_three.status is V2AdaptiveRoundStatus.CANCELLED:
        stop_code = V2AdaptiveStopCode.CANCELLED
        reason = "Research stopped at the Round-3 boundary because cancellation was requested."
    elif summary_three.status is V2AdaptiveRoundStatus.DEGRADED:
        stop_code = V2AdaptiveStopCode.PROVIDER_FAILURE
        reason = (
            "Research stopped after Round-3 provider degradation; completed work was preserved."
        )
    else:
        stop_code = V2AdaptiveStopCode.ROUND_THREE_COMPLETE
        reason = "Research stopped at the fixed three-round maximum after the narrow Round 3."
    return _finish(
        path,
        initial_plan.run_id,
        (summary_two, summary_three),
        pool_three,
        stop_code,
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
    previous_compiled_queries: tuple[V2CompiledQueryAction, ...],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    query_modes: Mapping[DiscoveryProvider, SearchMode],
    legacy_prompt: bool,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None,
    known_urls: frozenset[str],
    base_pool: V2MergedSurvivorPool,
    budget: V2AdaptiveBudgetState,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState] | None = None,
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
            previous_compiled_queries=previous_compiled_queries,
            search_providers=search_providers,
            llm_provider=llm_provider,
            routing_config=routing_config,
            query_modes=query_modes,
            legacy_prompt=legacy_prompt,
            budget=budget,
            budget_snapshot=budget_snapshot,
            cancellation_requested=cancellation_requested,
            clock=clock,
        )
    except V2AdaptiveCancellationError:
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.CANCELLED,
            "Research stopped before follow-up search planning.",
            round_number - 1,
            clock,
        )
    except LLMResponseValidationError as exc:
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN,
            f"Search Agent plan validation failed; completed work was preserved: {exc}",
            round_number - 1,
            clock,
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
    except V2AdaptivePlanValidationError as exc:
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN,
            f"Search Agent plan validation failed; completed work was preserved: {exc}",
            round_number - 1,
            clock,
        )
    except V2AdaptiveNoEligibleProviderError as exc:
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.NO_ELIGIBLE_PROVIDER,
            str(exc),
            round_number - 1,
            clock,
        )
    except V2AdaptiveBudgetError as exc:
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.BUDGET,
            str(exc),
            round_number - 1,
            clock,
        )
    except V2AdaptiveNoContinuationError as exc:
        return _finish(
            path,
            initial_plan.run_id,
            (),
            base_pool,
            V2AdaptiveStopCode.NO_NEW_QUERY,
            str(exc),
            round_number - 1,
            clock,
        )
    except (LookupError, ValueError) as exc:
        code = V2AdaptiveStopCode.NO_NEW_QUERY
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
        exact_claim=initial_plan.raw_claim,
        asserted_components=tuple(
            x.claim_component
            for x in initial_plan.claim_coverage_focus
            if x.claim_component in initial_plan.raw_claim
        ),
        preview_gaps=tuple(x.missing_evidence for x in gap_output.result.material_gaps)[:6]
        if gap_output.result is not None
        else (),
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
        search_agent_plan_valid=(reason is not V2RoundThreeReasonCode.INVALID_SEARCH_AGENT_PLAN),
        decided_at=decided_at,
    )
    decision = evaluate_v2_round_three_authorization(probe)
    if decision.reason_code is not reason:
        raise ValueError("v2 Governor rejection facts did not reproduce their reason code")
    return decision


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
    budget_snapshot: Callable[[], V2AdaptiveBudgetState] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime],
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
    legacy_prompt: bool = False,
    previous_compiled_queries: tuple[V2CompiledQueryAction, ...] = (),
) -> V2AdaptivePlannedRound:
    """Preserve the public persistence replacement seam for planning callers."""
    return _plan_round_owned(
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
        budget_snapshot=budget_snapshot,
        cancellation_requested=cancellation_requested,
        clock=clock,
        query_modes=query_modes,
        legacy_prompt=legacy_prompt,
        previous_compiled_queries=previous_compiled_queries,
        persist_artifact=insert_v2_artifact,
    )
