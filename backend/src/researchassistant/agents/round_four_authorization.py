"""Round-4 Governor authorization, protected reservations and terminal outcomes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY as V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    _read as _read,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptivePlannedRound,
    V2AdaptiveRoundExecution,
)
from researchassistant.agents.v2_discovery import V2_SCOUT_BATCH_SIZE
from researchassistant.common.money import add_usd
from researchassistant.contracts.models import (
    DiscoveryProvider,
    V2GapAnalysisInput,
    V2GapAnalysisModelOutput,
    V2GapAnalysisOutput,
    V2GapAnalysisState,
    V2InitialPlannerOutput,
    V2RoundFourDecisionCode,
    V2RoundFourGovernorDecision,
    V2RoundFourReservation,
    V2RoundFourTerminalOutcome,
)
from researchassistant.providers.llm import (
    LLMStage,
    load_prompt,
    render_stage_prompt,
)
from researchassistant.providers.pricing import conservative_token_estimate
from researchassistant.providers.v2_routing import V2ModelReservation, V2RoutingConfig
from researchassistant.research.research_governor import (
    V2RoundFourGovernorInput,
    evaluate_v2_round_four_authorization,
)
from researchassistant.storage.store import insert_v2_artifact


def _validate_round_four_decision_against_gap(
    *,
    gap: V2GapAnalysisOutput,
    decision: V2RoundFourGovernorDecision,
) -> None:
    """Reject a persisted governor reason that contradicts its post-Round-3 Gap result."""
    if decision.run_id != gap.run_id:
        raise ValueError("Round-4 Governor decision must match the post-Round-3 Gap run")
    result = gap.result
    reason = decision.reason_code
    if reason is V2RoundFourDecisionCode.NO_PRODUCTIVE_SEARCH:
        if result is None or result.continue_research:
            raise ValueError(
                "NO_PRODUCTIVE_SEARCH requires a usable Gap Analysis result that declines search"
            )
        return
    if reason is V2RoundFourDecisionCode.NO_MATERIAL_GAPS:
        if result is None or result.material_gaps:
            raise ValueError("NO_MATERIAL_GAPS requires a usable result with no material gaps")
        return
    if reason is V2RoundFourDecisionCode.GAP_ANALYSIS_UNUSABLE:
        if result is not None:
            raise ValueError("GAP_ANALYSIS_UNUSABLE cannot carry a usable Gap Analysis result")
        return
    if reason is V2RoundFourDecisionCode.INSUFFICIENT_RESERVATION and result is None:
        return
    if reason in {
        V2RoundFourDecisionCode.CANCELLED,
        V2RoundFourDecisionCode.TERMINAL_FAILURE,
    }:
        return
    if result is None or not result.continue_research or not result.material_gaps:
        raise ValueError(
            f"{reason.value} requires a usable Gap Analysis result with a continuing material gap"
        )


def _reservation(
    budget: V2AdaptiveBudgetState,
    post_gap_budget: V2AdaptiveBudgetState,
    plan: V2AdaptivePlannedRound,
    gap: V2GapAnalysisOutput,
    routing_config: V2RoutingConfig,
) -> V2RoundFourReservation | None:
    return _conservative_reservation(
        budget=budget,
        post_gap_budget=post_gap_budget,
        gap=gap,
        routing_config=routing_config,
        maximum_queries=len(plan.plan.searches),
        search_agent_tokens=plan.reservation.reserved_tokens,
        search_agent_cost=plan.reservation.reserved_cost_usd,
    )


def _conservative_reservation(
    *,
    budget: V2AdaptiveBudgetState,
    post_gap_budget: V2AdaptiveBudgetState,
    gap: V2GapAnalysisOutput,
    routing_config: V2RoutingConfig,
    maximum_queries: int,
    search_agent_tokens: int,
    search_agent_cost: Decimal,
) -> V2RoundFourReservation | None:
    scout_calls = ((maximum_queries * 5 + V2_SCOUT_BATCH_SIZE - 1) // V2_SCOUT_BATCH_SIZE) * 2
    scout_reserve = routing_config.preflight().reserve(LLMStage.SCOUT, 1)
    gap_reserve = _gap_reservation(gap.input, routing_config)
    optional_tokens = (
        2 * gap_reserve.reserved_tokens
        + search_agent_tokens
        + scout_calls * scout_reserve.reserved_tokens
    )
    optional_cost = add_usd(
        gap_reserve.reserved_cost_usd,
        gap_reserve.reserved_cost_usd,
        search_agent_cost,
        *(scout_reserve.reserved_cost_usd for _ in range(scout_calls)),
    )
    future_tokens = search_agent_tokens + scout_calls * scout_reserve.reserved_tokens
    future_cost = add_usd(
        search_agent_cost,
        *(scout_reserve.reserved_cost_usd for _ in range(scout_calls)),
    )
    try:
        return V2RoundFourReservation(
            protected_downstream_calls=budget.protected_downstream_model_calls,
            protected_downstream_tokens=budget.protected_downstream_tokens,
            protected_downstream_cost_usd=budget.protected_downstream_cost_usd,
            gap_attempt_calls=2,
            search_agent_calls=1,
            scout_calls=scout_calls,
            provider_search_calls=maximum_queries,
            acquisition_cluster_capacity=maximum_queries * 5,
            optional_calls=3 + scout_calls,
            optional_tokens=optional_tokens,
            optional_cost_usd=optional_cost,
            available_calls=budget.model_calls_remaining,
            available_tokens=budget.tokens_remaining,
            available_cost_usd=budget.cost_remaining_usd,
            consumed_gap_attempt_calls=len(gap.attempts),
            future_optional_calls=1 + scout_calls,
            future_optional_tokens=future_tokens,
            future_optional_cost_usd=future_cost,
            post_gap_available_calls=post_gap_budget.model_calls_remaining,
            post_gap_available_tokens=post_gap_budget.tokens_remaining,
            post_gap_available_cost_usd=post_gap_budget.cost_remaining_usd,
        )
    except ValueError:
        return None


def _gap_envelope_fits(
    budget: V2AdaptiveBudgetState,
    gap_input: V2GapAnalysisInput,
    routing_config: V2RoutingConfig,
) -> bool:
    reservation = _gap_reservation(gap_input, routing_config)
    return _fits_reserve(
        budget,
        calls=2,
        tokens=2 * reservation.reserved_tokens,
        cost=add_usd(reservation.reserved_cost_usd, reservation.reserved_cost_usd),
    )


def _gap_reservation(
    gap_input: V2GapAnalysisInput, routing_config: V2RoutingConfig
) -> V2ModelReservation:
    prompt = load_prompt(LLMStage.GAP_ANALYSIS)
    rendered = render_stage_prompt(prompt, gap_input, V2GapAnalysisModelOutput)
    return routing_config.preflight().reserve(
        LLMStage.GAP_ANALYSIS, conservative_token_estimate(rendered)
    )


def _fits_reserve(
    budget: V2AdaptiveBudgetState,
    *,
    calls: int,
    tokens: int,
    cost: Decimal,
) -> bool:
    if budget.model_calls_remaining < budget.protected_downstream_model_calls + calls:
        return False
    if (
        budget.tokens_remaining is not None
        and budget.tokens_remaining < budget.protected_downstream_tokens + tokens
    ):
        return False
    return budget.cost_remaining_usd is None or budget.cost_remaining_usd >= add_usd(
        budget.protected_downstream_cost_usd, cost
    )


def _unavailable_gap_output(
    gap_input: V2GapAnalysisInput, clock: Callable[[], datetime]
) -> V2GapAnalysisOutput:
    return V2GapAnalysisOutput(
        run_id=gap_input.run_id,
        input=gap_input,
        state=V2GapAnalysisState.DEGRADED,
        attempts=(),
        stop_adaptive_continuation=True,
        completed_at=clock(),
    )


def _provider_attempts(
    initial_plan: V2InitialPlannerOutput, path: str
) -> dict[DiscoveryProvider, int]:
    counts: Counter[DiscoveryProvider] = Counter(query.provider for query in initial_plan.searches)
    for round_number in (2, 3):
        payload = _read(path, initial_plan.run_id, f"phase-7-round-{round_number}-plan")
        if payload is not None:
            counts.update(
                query.provider
                for query in V2AdaptivePlannedRound.model_validate_json(payload).plan.searches
            )
    return dict(counts)


def _duplicate_rate(summary: V2AdaptiveRoundExecution) -> float:
    total = summary.new_source_count + summary.duplicate_source_count
    return summary.duplicate_source_count / total if total else 0.0


def _governor_decision(
    *,
    run_id: UUID,
    clock: Callable[[], datetime],
    gap: V2GapAnalysisOutput | None = None,
    gap_attempted: bool = True,
    eligible_provider_exists: bool = False,
    novel_query_opportunity: bool = False,
    round_three_duplicate_rate: float = 0.0,
    productive_opportunity: bool = True,
    protected_downstream_budget_remains: bool = True,
    complete_workload_reservable: bool = True,
    cancelled: bool = False,
    terminal_provider_failure: bool = False,
    reservation: V2RoundFourReservation | None = None,
) -> V2RoundFourGovernorDecision:
    """Evaluate typed Round-4 inputs, including explicit preauthorization opportunities."""
    result = gap.result if gap is not None else None
    return evaluate_v2_round_four_authorization(
        V2RoundFourGovernorInput(
            run_id=run_id,
            gap_analysis_attempted=gap_attempted,
            gap_analysis_usable=result is not None,
            material_gap_remains=bool(result and result.material_gaps),
            luna_recommends_continue=bool(result and result.continue_research),
            eligible_provider_exists=eligible_provider_exists,
            novel_query_opportunity=novel_query_opportunity,
            round_three_duplicate_rate=round_three_duplicate_rate,
            productive_opportunity=productive_opportunity,
            protected_downstream_budget_remains=protected_downstream_budget_remains,
            complete_workload_reservable=complete_workload_reservable,
            cancelled=cancelled,
            terminal_provider_failure=terminal_provider_failure,
            decided_at=clock(),
        ),
        reservation=reservation,
    )


def _persist_terminal_outcome(
    path: str, run_id: UUID, failed_stage: str, clock: Callable[[], datetime]
) -> V2RoundFourGovernorDecision:
    """Persist a terminal lifecycle record without replacing immutable authorization."""
    decision = _governor_decision(
        run_id=run_id,
        clock=clock,
        terminal_provider_failure=True,
    )
    if _read(path, run_id, V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY) is None:
        outcome = V2RoundFourTerminalOutcome(
            run_id=run_id,
            reason_code=V2RoundFourDecisionCode.TERMINAL_FAILURE,
            failed_stage=failed_stage,
            completed_at=decision.decided_at,
        )
        insert_v2_artifact(
            path,
            V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY,
            outcome,
            outcome.completed_at,
        )
    return decision
