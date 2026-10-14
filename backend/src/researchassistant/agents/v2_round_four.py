"""Bounded Round-4 scheduling and compatible public exports."""

from __future__ import annotations

from collections import Counter as Counter
from collections.abc import Callable as Callable
from collections.abc import Mapping as Mapping
from datetime import UTC as UTC
from datetime import datetime as datetime
from decimal import Decimal as Decimal
from pathlib import Path as Path
from typing import TypeVar as TypeVar
from uuid import NAMESPACE_URL as NAMESPACE_URL
from uuid import UUID as UUID
from uuid import uuid5 as uuid5

from pydantic import ConfigDict as ConfigDict
from pydantic import Field as Field
from pydantic import field_validator as field_validator
from pydantic import model_validator as model_validator

from researchassistant.agents.round_four_authorization import (
    _conservative_reservation as _conservative_reservation,
)
from researchassistant.agents.round_four_authorization import (
    _duplicate_rate as _duplicate_rate,
)
from researchassistant.agents.round_four_authorization import (
    _fits_reserve as _fits_reserve,
)
from researchassistant.agents.round_four_authorization import (
    _gap_envelope_fits as _gap_envelope_fits,
)
from researchassistant.agents.round_four_authorization import (
    _gap_reservation as _gap_reservation,
)
from researchassistant.agents.round_four_authorization import (
    _governor_decision as _governor_decision,
)
from researchassistant.agents.round_four_authorization import (
    _persist_terminal_outcome as _persist_terminal_outcome,
)
from researchassistant.agents.round_four_authorization import (
    _provider_attempts as _provider_attempts,
)
from researchassistant.agents.round_four_authorization import (
    _reservation as _reservation,
)
from researchassistant.agents.round_four_authorization import (
    _unavailable_gap_output as _unavailable_gap_output,
)
from researchassistant.agents.round_four_authorization import (
    _validate_round_four_decision_against_gap as _validate_round_four_decision_against_gap,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_GAP_AFTER_ROUND_THREE_KEY as V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_GAP_RECONCILIATION_KEY as V2_POST13_GAP_RECONCILIATION_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_COMPLETION_KEY as V2_POST13_ROUND_FOUR_COMPLETION_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY as V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_PLAN_KEY as V2_POST13_ROUND_FOUR_PLAN_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_POST_PLAN_FACTS_KEY as V2_POST13_ROUND_FOUR_POST_PLAN_FACTS_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY as V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2RoundFourAuthorizationError as V2RoundFourAuthorizationError,
)
from researchassistant.agents.round_four_handoffs import (
    V2RoundFourBudgetError as V2RoundFourBudgetError,
)
from researchassistant.agents.round_four_handoffs import (
    V2RoundFourPostPlanFacts as V2RoundFourPostPlanFacts,
)
from researchassistant.agents.round_four_handoffs import (
    V2RoundFourRunResult as V2RoundFourRunResult,
)
from researchassistant.agents.round_four_handoffs import (
    _aware_datetime as _aware_datetime,
)
from researchassistant.agents.round_four_handoffs import (
    _cancellation_from_error as _cancellation_from_error,
)
from researchassistant.agents.round_four_handoffs import (
    _cancelled as _cancelled,
)
from researchassistant.agents.round_four_handoffs import (
    _read as _read,
)
from researchassistant.agents.round_four_handoffs import (
    _utc_now as _utc_now,
)
from researchassistant.agents.round_four_planning import (
    _build_round_four_search_agent_request as _build_round_four_search_agent_request,
)
from researchassistant.agents.round_four_planning import (
    _plan_round_four as _plan_round_four_owned,
)
from researchassistant.agents.round_four_reconciliation import (
    _validate_reconciliation_admission as _validate_reconciliation_admission,
)
from researchassistant.agents.round_four_reconciliation import (
    reconcile_post_round_three_gaps as reconcile_post_round_three_gaps,
)
from researchassistant.agents.round_four_summary import (
    _build_post_plan_facts as _build_post_plan_facts,
)
from researchassistant.agents.round_four_summary import (
    _claim_coverage_specification as _claim_coverage_specification,
)
from researchassistant.agents.round_four_summary import (
    _direction_balanced as _direction_balanced,
)
from researchassistant.agents.round_four_summary import (
    _finish as _finish,
)
from researchassistant.agents.round_four_summary import (
    _representative_families as _representative_families,
)
from researchassistant.agents.round_four_summary import (
    _representative_queries as _representative_queries,
)
from researchassistant.agents.round_four_summary import (
    _representative_round_rows as _representative_round_rows,
)
from researchassistant.agents.round_four_summary import (
    _row_sort_key as _row_sort_key,
)
from researchassistant.agents.round_four_summary import (
    _RowT as _RowT,
)
from researchassistant.agents.round_four_summary import (
    build_post_round_three_gap_input as build_post_round_three_gap_input,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveBudgetState as V2AdaptiveBudgetState,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveContinuationResult as V2AdaptiveContinuationResult,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptivePlannedRound as V2AdaptivePlannedRound,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptivePlanValidationError as V2AdaptivePlanValidationError,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveRoundExecution as V2AdaptiveRoundExecution,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveRoundStatus as V2AdaptiveRoundStatus,
)
from researchassistant.agents.v2_adaptive_search import V2AdaptiveStopCode as V2AdaptiveStopCode
from researchassistant.agents.v2_adaptive_search import (
    V2SearchAgentReservation as V2SearchAgentReservation,
)
from researchassistant.agents.v2_adaptive_search import (
    _adaptive_concept_lanes as _adaptive_concept_lanes,
)
from researchassistant.agents.v2_adaptive_search import _eligible_budgets as _eligible_budgets
from researchassistant.agents.v2_adaptive_search import _known_urls as _known_urls
from researchassistant.agents.v2_adaptive_search import _maximum_queries as _maximum_queries
from researchassistant.agents.v2_adaptive_search import _merge_survivors as _merge_survivors
from researchassistant.agents.v2_adaptive_search import _run_round_from_plan as _run_round_from_plan
from researchassistant.agents.v2_adaptive_search import (
    _validate_and_assemble_plan as _validate_and_assemble_plan,
)
from researchassistant.agents.v2_coverage import claim_component_focus as claim_component_focus
from researchassistant.agents.v2_discovery import V2_SCOUT_BATCH_SIZE as V2_SCOUT_BATCH_SIZE
from researchassistant.agents.v2_gap_analysis import run_v2_gap_analysis as run_v2_gap_analysis
from researchassistant.common.resources import prompt_resource as prompt_resource
from researchassistant.contracts.discovery_v2 import SearchMode as SearchMode
from researchassistant.contracts.discovery_v2 import V2CompiledQueryAction as V2CompiledQueryAction
from researchassistant.contracts.model_research import (
    V2_PREVIEW_SELECTION_POLICY_IDENTITY as V2_PREVIEW_SELECTION_POLICY_IDENTITY,
)
from researchassistant.contracts.models import (
    V2_EVIDENCE_ADMISSION_POLICY_IDENTITY as V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
)
from researchassistant.contracts.models import (
    V2_EVIDENCE_ADMISSION_PREVIOUS_POLICY_IDENTITY,  # noqa: F401 - compatibility export
)
from researchassistant.contracts.models import (
    V2_EVIDENCE_ANALYST_POLICY_IDENTITY as V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
)
from researchassistant.contracts.models import (
    V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY as V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY,
)
from researchassistant.contracts.models import (
    V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY as V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
)
from researchassistant.contracts.models import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY as V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
)
from researchassistant.contracts.models import (
    V2_SOURCE_SELECTION_POLICY_IDENTITY as V2_SOURCE_SELECTION_POLICY_IDENTITY,
)
from researchassistant.contracts.models import CrossrefIdentityMetadata as CrossrefIdentityMetadata
from researchassistant.contracts.models import DiscoveryProvider as DiscoveryProvider
from researchassistant.contracts.models import ResearchDirection as ResearchDirection
from researchassistant.contracts.models import ResearchDirections as ResearchDirections
from researchassistant.contracts.models import StrictModel as StrictModel
from researchassistant.contracts.models import V2AcquisitionProbeOutput as V2AcquisitionProbeOutput
from researchassistant.contracts.models import V2AdaptiveRoundPlan as V2AdaptiveRoundPlan
from researchassistant.contracts.models import (
    V2AdaptiveSearchModelOutput as V2AdaptiveSearchModelOutput,
)
from researchassistant.contracts.models import V2AdmissionMethod as V2AdmissionMethod
from researchassistant.contracts.models import V2ClaimCoverageDimension as V2ClaimCoverageDimension
from researchassistant.contracts.models import V2ClaimCoverageFocus as V2ClaimCoverageFocus
from researchassistant.contracts.models import V2ClaimCoverageKind as V2ClaimCoverageKind
from researchassistant.contracts.models import (
    V2ClaimCoverageSpecification as V2ClaimCoverageSpecification,
)
from researchassistant.contracts.models import V2DiscoveryScoutOutput as V2DiscoveryScoutOutput
from researchassistant.contracts.models import (
    V2EvidenceAdmissionBatchResult as V2EvidenceAdmissionBatchResult,
)
from researchassistant.contracts.models import V2EvidenceAdmissionState as V2EvidenceAdmissionState
from researchassistant.contracts.models import (
    V2EvidenceAnalystCandidateInput as V2EvidenceAnalystCandidateInput,
)
from researchassistant.contracts.models import (
    V2EvidenceAnalystSourceResult as V2EvidenceAnalystSourceResult,
)
from researchassistant.contracts.models import V2EvidenceAnalystState as V2EvidenceAnalystState
from researchassistant.contracts.models import V2GapAcquisitionFailure as V2GapAcquisitionFailure
from researchassistant.contracts.models import V2GapAnalysisInput as V2GapAnalysisInput
from researchassistant.contracts.models import V2GapAnalysisModelOutput as V2GapAnalysisModelOutput
from researchassistant.contracts.models import V2GapAnalysisOutput as V2GapAnalysisOutput
from researchassistant.contracts.models import V2GapAnalysisState as V2GapAnalysisState
from researchassistant.contracts.models import V2GapAttemptedQuery as V2GapAttemptedQuery
from researchassistant.contracts.models import V2GapBudgetState as V2GapBudgetState
from researchassistant.contracts.models import (
    V2GapCoverageReconciliation as V2GapCoverageReconciliation,
)
from researchassistant.contracts.models import V2GapCoverageRecord as V2GapCoverageRecord
from researchassistant.contracts.models import V2GapCoverageState as V2GapCoverageState
from researchassistant.contracts.models import V2GapDuplicatePattern as V2GapDuplicatePattern
from researchassistant.contracts.models import V2GapProbePassage as V2GapProbePassage
from researchassistant.contracts.models import V2GapSourceFamily as V2GapSourceFamily
from researchassistant.contracts.models import (
    V2GapSurvivingSourceMetadata as V2GapSurvivingSourceMetadata,
)
from researchassistant.contracts.models import V2InitialPlannerOutput as V2InitialPlannerOutput
from researchassistant.contracts.models import V2LedgerProvenance as V2LedgerProvenance
from researchassistant.contracts.models import V2MaterialGap as V2MaterialGap
from researchassistant.contracts.models import V2ProviderSearchBudget as V2ProviderSearchBudget
from researchassistant.contracts.models import V2RoundFourDecisionCode as V2RoundFourDecisionCode
from researchassistant.contracts.models import (
    V2RoundFourGovernorDecision as V2RoundFourGovernorDecision,
)
from researchassistant.contracts.models import V2RoundFourReservation as V2RoundFourReservation
from researchassistant.contracts.models import (
    V2RoundFourTerminalOutcome as V2RoundFourTerminalOutcome,
)
from researchassistant.contracts.models import V2SearchAgentInput as V2SearchAgentInput
from researchassistant.contracts.models import (
    V2SourceSelectionCandidate as V2SourceSelectionCandidate,
)
from researchassistant.contracts.models import (
    validate_v2_gap_history_against_material_gaps as validate_v2_gap_history_against_material_gaps,
)
from researchassistant.contracts.query_planning import (
    V2AdaptiveSearchConceptsOutput as V2AdaptiveSearchConceptsOutput,
)
from researchassistant.contracts.query_planning import (
    V2ConceptualAdaptiveLane as V2ConceptualAdaptiveLane,
)
from researchassistant.contracts.query_planning import (
    V2ConceptualSearchAgentInput as V2ConceptualSearchAgentInput,
)
from researchassistant.evidence.evidence_portfolio import (
    identify_source_family as identify_source_family,
)
from researchassistant.providers.llm import V2_LLM_ROUTING as V2_LLM_ROUTING
from researchassistant.providers.llm import LLMProvider as LLMProvider
from researchassistant.providers.llm import LLMProviderExecutionError as LLMProviderExecutionError
from researchassistant.providers.llm import LLMRequest as LLMRequest
from researchassistant.providers.llm import LLMResponseValidationError as LLMResponseValidationError
from researchassistant.providers.llm import LLMStage as LLMStage
from researchassistant.providers.llm import invoke_llm as invoke_llm
from researchassistant.providers.llm import load_prompt as load_prompt
from researchassistant.providers.llm import render_stage_prompt as render_stage_prompt
from researchassistant.providers.pricing import (
    conservative_token_estimate as conservative_token_estimate,
)
from researchassistant.providers.scraper import ScraperProvider as ScraperProvider
from researchassistant.providers.search import SearchProvider as SearchProvider
from researchassistant.providers.v2_budget import V2CancellationRequested as V2CancellationRequested
from researchassistant.providers.v2_routing import V2ModelReservation as V2ModelReservation
from researchassistant.providers.v2_routing import V2RoutingConfig as V2RoutingConfig
from researchassistant.research.research_governor import (
    V2RoundFourGovernorInput as V2RoundFourGovernorInput,
)
from researchassistant.research.research_governor import (
    evaluate_v2_round_four_authorization as evaluate_v2_round_four_authorization,
)
from researchassistant.storage.store import insert_v2_artifact as insert_v2_artifact
from researchassistant.storage.store import read_v2_artifact as read_v2_artifact


def run_v2_round_four_continuation(
    *,
    db_path: str | Path,
    initial_plan: V2InitialPlannerOutput,
    continuation: V2AdaptiveContinuationResult,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None,
    budget: V2AdaptiveBudgetState,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState],
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2RoundFourRunResult:
    """Run Round 4 only after persisting its conservative preauthorization."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    persisted = _read(path, initial_plan.run_id, V2_POST13_ROUND_FOUR_COMPLETION_KEY)
    if persisted is not None:
        result = V2RoundFourRunResult.model_validate_json(persisted)
        if result.continuation.run_id != initial_plan.run_id:
            raise ValueError("persisted Round-4 continuation does not match the initial plan")
        return result.model_copy(update={"resumed": True})
    if continuation.stopping_decision.completed_rounds != 3 or not continuation.rounds:
        raise ValueError("Round-4 continuation requires exactly one completed Round 3")
    round_three = continuation.rounds[-1]
    if round_three.round_number != 3 or round_three.status is not V2AdaptiveRoundStatus.COMPLETED:
        raise ValueError("Round-4 continuation requires a successful non-degraded Round 3")
    gap_input = build_post_round_three_gap_input(
        initial_plan=initial_plan,
        discovery_outputs=discovery_outputs,
        acquisition_outputs=acquisition_outputs,
        remaining_budget=budget,
        db_path=path,
    )
    if not _gap_envelope_fits(budget, gap_input, routing_config):
        return _finish(
            path,
            continuation,
            _unavailable_gap_output(gap_input, now),
            _governor_decision(
                run_id=initial_plan.run_id,
                clock=now,
                gap_attempted=False,
                protected_downstream_budget_remains=False,
                complete_workload_reservable=False,
            ),
            now,
        )
    gap = run_v2_gap_analysis(
        db_path=path,
        gap_input=gap_input,
        llm_provider=llm_provider,
        routing_config=routing_config,
        artifact_key=V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
        clock=now,
    )
    post_gap_budget = budget_snapshot()
    if _cancelled(cancellation_requested):
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap, cancelled=True),
            now,
        )
    if gap.result is None:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap),
            now,
        )
    if not gap.result.material_gaps or not gap.result.continue_research:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap),
            now,
        )
    attempts = _provider_attempts(initial_plan, path)
    eligible = _eligible_budgets(initial_plan, attempts, search_providers, path=path)
    if not eligible:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap),
            now,
        )
    duplicate_rate = _duplicate_rate(round_three)
    if duplicate_rate >= 0.70:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(
                run_id=initial_plan.run_id,
                clock=now,
                gap=gap,
                eligible_provider_exists=True,
                round_three_duplicate_rate=duplicate_rate,
            ),
            now,
        )
    persisted_decision = _read(path, initial_plan.run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY)
    if persisted_decision is None:
        built = _build_round_four_search_agent_request(
            path=path,
            initial_plan=initial_plan,
            gap=gap,
            eligible=eligible,
            routing_config=routing_config,
        )
        if built is None:
            return _finish(
                path,
                continuation,
                gap,
                _governor_decision(
                    run_id=initial_plan.run_id,
                    clock=now,
                    gap=gap,
                    eligible_provider_exists=True,
                    round_three_duplicate_rate=duplicate_rate,
                    novel_query_opportunity=False,
                    productive_opportunity=False,
                    complete_workload_reservable=False,
                ),
                now,
            )
        (
            request_input,
            _request,
            search_reservation,
            _lanes,
            _prior_actions,
            _legacy_prompt,
            _modes,
        ) = built
        if isinstance(request_input, V2ConceptualSearchAgentInput):
            request_input = request_input.request
        if request_input.maximum_queries == 0:
            return _finish(
                path,
                continuation,
                gap,
                _governor_decision(
                    run_id=initial_plan.run_id,
                    clock=now,
                    gap=gap,
                    eligible_provider_exists=True,
                    round_three_duplicate_rate=duplicate_rate,
                    novel_query_opportunity=False,
                ),
                now,
            )
        reservation = _conservative_reservation(
            budget=budget,
            post_gap_budget=post_gap_budget,
            gap=gap,
            routing_config=routing_config,
            maximum_queries=request_input.maximum_queries,
            search_agent_tokens=search_reservation.reserved_tokens,
            search_agent_cost=search_reservation.reserved_cost_usd,
        )
        # This is preauthorization of a bounded novel-query opportunity exposed by the
        # persisted Gap result. The Search Agent can only validate and narrow this envelope;
        # it cannot broaden the persisted reservation or authorize itself.
        decision = _governor_decision(
            run_id=initial_plan.run_id,
            clock=now,
            gap=gap,
            eligible_provider_exists=True,
            round_three_duplicate_rate=duplicate_rate,
            novel_query_opportunity=True,
            productive_opportunity=True,
            complete_workload_reservable=reservation is not None,
            reservation=reservation,
        )
        insert_v2_artifact(path, V2_POST13_ROUND_FOUR_GOVERNOR_KEY, decision, decision.decided_at)
    else:
        decision = V2RoundFourGovernorDecision.model_validate_json(persisted_decision)
        if decision.run_id != initial_plan.run_id:
            raise ValueError("persisted Round-4 Governor decision does not match the initial plan")
    if not decision.authorized:
        return _finish(path, continuation, gap, decision, now)
    if _cancelled(cancellation_requested):
        cancelled = continuation.model_copy(
            update={
                "stopping_decision": continuation.stopping_decision.model_copy(
                    update={
                        "stop_code": V2AdaptiveStopCode.CANCELLED,
                        "stopping_reason": "Cancellation was observed before Round-4 planning.",
                        "decided_at": now(),
                    }
                ),
                "completed_at": now(),
            }
        )
        return _finish(
            path,
            cancelled,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap, cancelled=True),
            now,
        )
    try:
        plan = _plan_round_four(
            path=path,
            initial_plan=initial_plan,
            gap=gap,
            eligible=eligible,
            attempts=attempts,
            llm_provider=llm_provider,
            routing_config=routing_config,
            clock=now,
        )
    except LLMProviderExecutionError as exc:
        cancellation = _cancellation_from_error(exc)
        if cancellation is not None:
            raise cancellation from None
        terminal = _persist_terminal_outcome(path, initial_plan.run_id, "search_agent", now)
        return _finish(
            path,
            continuation,
            gap,
            terminal,
            now,
        )
    except LLMResponseValidationError:
        terminal = _persist_terminal_outcome(path, initial_plan.run_id, "search_agent", now)
        return _finish(path, continuation, gap, terminal, now)
    except V2AdaptivePlanValidationError:
        terminal = _persist_terminal_outcome(path, initial_plan.run_id, "search_agent_plan", now)
        return _finish(path, continuation, gap, terminal, now)
    if plan is None:
        terminal = _persist_terminal_outcome(path, initial_plan.run_id, "search_agent_plan", now)
        return _finish(path, continuation, gap, terminal, now)
    search, discovery, acquisition, summary = _run_round_from_plan(
        path=path,
        planned=plan,
        exact_claim=initial_plan.raw_claim,
        asserted_components=tuple(
            x.claim_component
            for x in initial_plan.claim_coverage_focus
            if x.claim_component in initial_plan.raw_claim
        ),
        preview_gaps=tuple(x.missing_evidence for x in gap.result.material_gaps)[:6]
        if gap.result is not None
        else (),
        search_providers=search_providers,
        llm_provider=llm_provider,
        routing_config=routing_config,
        wigolo_provider=wigolo_provider,
        firecrawl_provider=firecrawl_provider,
        crossref_resolver=crossref_resolver,
        known_urls=_known_urls(discovery_outputs),
        cancellation_requested=cancellation_requested,
        clock=now,
    )
    del search
    post_plan_facts = _build_post_plan_facts(plan, summary, now)
    rounds_with_round_four = tuple(
        (
            round_number,
            discovery_outputs[round_number - 1],
            acquisition_outputs[round_number - 1],
        )
        for round_number in range(1, 4)
    ) + ((4, discovery, acquisition),)
    if summary.status is V2AdaptiveRoundStatus.CANCELLED:
        cancelled = continuation.model_copy(
            update={
                "stopping_decision": continuation.stopping_decision.model_copy(
                    update={
                        "stop_code": V2AdaptiveStopCode.CANCELLED,
                        "stopping_reason": "Cancellation was observed during targeted Round 4.",
                        "decided_at": now(),
                    }
                ),
                "completed_at": now(),
            }
        )
        return _finish(path, cancelled, gap, decision, now, post_plan_facts)
    if summary.status is V2AdaptiveRoundStatus.DEGRADED:
        merged = _merge_survivors(initial_plan.run_id, rounds_with_round_four)
        failed = continuation.model_copy(
            update={
                "rounds": (*continuation.rounds, summary),
                "merged_survivors": merged,
                "stopping_decision": continuation.stopping_decision.model_copy(
                    update={
                        "completed_rounds": 4,
                        "stop_code": V2AdaptiveStopCode.PROVIDER_FAILURE,
                        "stopping_reason": "Targeted Round 4 ended after a provider failure.",
                        "decided_at": now(),
                    }
                ),
                "completed_at": now(),
            }
        )
        terminal = _persist_terminal_outcome(path, initial_plan.run_id, "provider", now)
        return _finish(
            path,
            failed,
            gap,
            terminal,
            now,
            post_plan_facts,
        )
    merged = _merge_survivors(initial_plan.run_id, rounds_with_round_four)
    updated = continuation.model_copy(
        update={
            "rounds": (*continuation.rounds, summary),
            "merged_survivors": merged,
            "stopping_decision": continuation.stopping_decision.model_copy(
                update={
                    "completed_rounds": 4,
                    "stop_code": V2AdaptiveStopCode.ROUND_FOUR_COMPLETE,
                    "stopping_reason": (
                        "Targeted Round 4 completed; no further research round is permitted."
                    ),
                    "decided_at": now(),
                }
            ),
            "completed_at": now(),
        }
    )
    return _finish(path, updated, gap, decision, now, post_plan_facts)


def _plan_round_four(
    *,
    path: str,
    initial_plan: V2InitialPlannerOutput,
    gap: V2GapAnalysisOutput,
    eligible: tuple[V2ProviderSearchBudget, ...],
    attempts: Mapping[DiscoveryProvider, int],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
) -> V2AdaptivePlannedRound | None:
    """Preserve the public plan-validation replacement seam for Round-4 callers."""
    return _plan_round_four_owned(
        path=path,
        initial_plan=initial_plan,
        gap=gap,
        eligible=eligible,
        attempts=attempts,
        llm_provider=llm_provider,
        routing_config=routing_config,
        clock=clock,
        assemble_plan=_validate_and_assemble_plan,
        request_builder=_build_round_four_search_agent_request,
    )
