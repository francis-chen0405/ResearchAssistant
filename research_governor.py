"""Deterministic MVP-11 Research Governor policy and terminal classification."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from models import (
    ResearchGovernorDecision,
    ResearchGovernorDecisionOutcome,
    ResearchGovernorEvaluationInput,
    ResearchGovernorPolicy,
    ResearchGovernorReasonCode,
    ResearchTerminalOutcome,
    ResearchTerminalResult,
    StrictModel,
)

DEFAULT_RESEARCH_GOVERNOR_POLICY = ResearchGovernorPolicy()


class V2RoundThreeReasonCode(StrEnum):
    AUTHORIZED = "round_three_authorized"
    NO_MATERIAL_GAP = "no_material_gap"
    LUNA_STOP = "luna_recommended_stop"
    NO_NEW_DIRECTION = "no_new_search_direction"
    NO_ELIGIBLE_PROVIDER = "no_eligible_provider"
    NO_NEW_QUERY = "no_materially_new_query"
    DUPLICATE_HEAVY = "duplicate_heavy_round_two"
    PROVIDER_CEILING = "provider_search_ceiling"
    PROTECTED_BUDGET = "protected_downstream_budget"
    INSUFFICIENT_RESERVATION = "insufficient_complete_workload_reservation"
    CANCELLED = "cancelled"
    TERMINAL_FAILURE = "terminal_provider_failure"
    ROUND_LIMIT = "round_limit_reached"


class V2RoundThreeGovernorInput(StrictModel):
    """Typed v2 facts; Luna recommends while deterministic policy authorizes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    current_round: int = Field(ge=2, le=3)
    material_gap_remains: bool
    luna_recommends_continue: bool
    new_search_direction_exists: bool
    eligible_provider_exists: bool
    materially_new_queries: bool
    provider_ceiling_permits: bool
    protected_downstream_budget_remains: bool
    complete_workload_reservable: bool
    round_two_duplicate_rate: float = Field(ge=0, le=1)
    cancelled: bool = False
    terminal_provider_failure: bool = False
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("v2 Governor decided_at must be timezone-aware")
        return value


class V2RoundThreeGovernorDecision(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    authorized: bool
    reason_code: V2RoundThreeReasonCode
    explanation: str = Field(min_length=1)
    policy_version: str = "researchassistant-v2-phase-7-governor-v1"
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("v2 Governor decided_at must be timezone-aware")
        return value


def evaluate_v2_round_three_authorization(
    evaluation: V2RoundThreeGovernorInput,
) -> V2RoundThreeGovernorDecision:
    """Adapt the fixed Governor to v2 Gap Analysis and search-continuation facts."""
    reason = _v2_reason(evaluation)
    authorized = reason is V2RoundThreeReasonCode.AUTHORIZED
    return V2RoundThreeGovernorDecision(
        run_id=evaluation.run_id,
        authorized=authorized,
        reason_code=reason,
        explanation=_v2_explanation(reason, evaluation.round_two_duplicate_rate),
        decided_at=evaluation.decided_at,
    )


def _v2_reason(evaluation: V2RoundThreeGovernorInput) -> V2RoundThreeReasonCode:
    if evaluation.cancelled:
        return V2RoundThreeReasonCode.CANCELLED
    if evaluation.terminal_provider_failure:
        return V2RoundThreeReasonCode.TERMINAL_FAILURE
    if evaluation.current_round >= 3:
        return V2RoundThreeReasonCode.ROUND_LIMIT
    if not evaluation.material_gap_remains:
        return V2RoundThreeReasonCode.NO_MATERIAL_GAP
    if not evaluation.luna_recommends_continue:
        return V2RoundThreeReasonCode.LUNA_STOP
    if not evaluation.new_search_direction_exists:
        return V2RoundThreeReasonCode.NO_NEW_DIRECTION
    if not evaluation.eligible_provider_exists:
        return V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER
    if not evaluation.materially_new_queries:
        return V2RoundThreeReasonCode.NO_NEW_QUERY
    if evaluation.round_two_duplicate_rate >= 0.70:
        return V2RoundThreeReasonCode.DUPLICATE_HEAVY
    if not evaluation.provider_ceiling_permits:
        return V2RoundThreeReasonCode.PROVIDER_CEILING
    if not evaluation.protected_downstream_budget_remains:
        return V2RoundThreeReasonCode.PROTECTED_BUDGET
    if not evaluation.complete_workload_reservable:
        return V2RoundThreeReasonCode.INSUFFICIENT_RESERVATION
    return V2RoundThreeReasonCode.AUTHORIZED


def _v2_explanation(reason: V2RoundThreeReasonCode, duplicate_rate: float) -> str:
    explanations = {
        V2RoundThreeReasonCode.AUTHORIZED: (
            "Round 3 was authorized as a narrow, gap-directed search with eligible "
            "providers and protected budget."
        ),
        V2RoundThreeReasonCode.NO_MATERIAL_GAP: (
            "Round 3 was not started because no material Gap remains."
        ),
        V2RoundThreeReasonCode.LUNA_STOP: (
            "Round 3 was not started because Luna recommended stopping after Round 2."
        ),
        V2RoundThreeReasonCode.NO_NEW_DIRECTION: (
            "Round 3 was not started because no genuinely new search direction remains."
        ),
        V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER: (
            "Round 3 was not started because no enabled provider is eligible."
        ),
        V2RoundThreeReasonCode.NO_NEW_QUERY: (
            "Round 3 was not started because the proposed queries were repeats or trivial rewrites."
        ),
        V2RoundThreeReasonCode.DUPLICATE_HEAVY: (
            f"Round 3 was not started because Round 2 was duplicate-heavy ({duplicate_rate:.0%})."
        ),
        V2RoundThreeReasonCode.PROVIDER_CEILING: (
            "Round 3 was not started because provider search ceilings do not permit the plan."
        ),
        V2RoundThreeReasonCode.PROTECTED_BUDGET: (
            "Round 3 was not started because protected downstream budget would be consumed."
        ),
        V2RoundThreeReasonCode.INSUFFICIENT_RESERVATION: (
            "Round 3 was not started because its complete workload cannot be "
            "conservatively reserved."
        ),
        V2RoundThreeReasonCode.CANCELLED: ("Research stopped because cancellation was requested."),
        V2RoundThreeReasonCode.TERMINAL_FAILURE: (
            "Round 3 was not started after a terminal provider failure."
        ),
        V2RoundThreeReasonCode.ROUND_LIMIT: ("Research stopped at the fixed three-round maximum."),
    }
    return explanations[reason]


def evaluate_round_three_authorization(
    evaluation: ResearchGovernorEvaluationInput,
    *,
    policy: ResearchGovernorPolicy = DEFAULT_RESEARCH_GOVERNOR_POLICY,
) -> ResearchGovernorDecision:
    """Return the one deterministic post-Round-2 decision, never a future round plan."""
    duplicate_rate = _duplicate_rate(
        evaluation.round_two_duplicate_count,
        evaluation.round_two_result_count,
    )
    portfolio_complete = (
        evaluation.independent_approved_family_count >= policy.required_independent_families
    )
    reason = _stopping_reason(evaluation, policy, portfolio_complete, duplicate_rate)
    authorized = reason is ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED
    return ResearchGovernorDecision(
        run_id=evaluation.run_id,
        current_round=evaluation.current_round,
        independent_approved_family_count=evaluation.independent_approved_family_count,
        portfolio_complete=portfolio_complete,
        round_two_duplicate_count=evaluation.round_two_duplicate_count,
        round_two_result_count=evaluation.round_two_result_count,
        round_two_duplicate_rate=duplicate_rate,
        consecutive_unproductive_source_count=evaluation.consecutive_unproductive_source_count,
        remaining_search_angles=evaluation.remaining_search_angles,
        cumulative_budget=evaluation.cumulative_budget,
        decision=(
            ResearchGovernorDecisionOutcome.BEGIN_ROUND_THREE
            if authorized
            else ResearchGovernorDecisionOutcome.FINALIZE
        ),
        reason_code=reason,
        explanation=_explanation(evaluation, policy, reason, duplicate_rate),
        policy_version=policy.policy_version,
        decided_at=evaluation.decided_at,
    )


def classify_terminal_outcome(
    *,
    run_id: UUID,
    completed_rounds: int,
    independent_approved_family_count: int,
    cancelled: bool = False,
    failed: bool = False,
    explanation: str,
    finalized_at: datetime | None = None,
    policy: ResearchGovernorPolicy = DEFAULT_RESEARCH_GOVERNOR_POLICY,
) -> ResearchTerminalResult:
    """Classify the required terminal outcome without authorizing another research round."""
    if completed_rounds < 1 or completed_rounds > policy.maximum_research_rounds:
        raise ValueError("completed research rounds must remain within the fixed range 1..3")
    if failed:
        outcome = ResearchTerminalOutcome.FAILED
    elif cancelled:
        outcome = ResearchTerminalOutcome.CANCELLED
    elif independent_approved_family_count >= policy.required_independent_families:
        outcome = ResearchTerminalOutcome.COMPLETE
    elif independent_approved_family_count > 0:
        outcome = ResearchTerminalOutcome.LIMITED
    else:
        outcome = ResearchTerminalOutcome.INSUFFICIENT
    if not explanation:
        raise ValueError("terminal research results require a plain-language explanation")
    return ResearchTerminalResult(
        run_id=run_id,
        outcome=outcome,
        completed_rounds=completed_rounds,
        independent_approved_family_count=independent_approved_family_count,
        explanation=explanation,
        finalized_at=finalized_at or datetime.now(UTC),
    )


def _duplicate_rate(duplicate_count: int, result_count: int) -> float:
    """Return a stable zero-safe duplicate rate for completed Round-2 discoveries."""
    if result_count == 0:
        return 0.0
    return duplicate_count / result_count


def _stopping_reason(
    evaluation: ResearchGovernorEvaluationInput,
    policy: ResearchGovernorPolicy,
    portfolio_complete: bool,
    duplicate_rate: float,
) -> ResearchGovernorReasonCode:
    """Evaluate authorization conditions in documented fail-closed precedence order."""
    if evaluation.cancelled:
        return ResearchGovernorReasonCode.RUN_CANCELLED
    if evaluation.terminal_provider_or_infrastructure_failure:
        return ResearchGovernorReasonCode.TERMINAL_PROVIDER_FAILURE
    if evaluation.current_round >= policy.maximum_research_rounds:
        return ResearchGovernorReasonCode.ROUND_LIMIT_REACHED
    if portfolio_complete:
        return ResearchGovernorReasonCode.PORTFOLIO_COMPLETE
    if duplicate_rate >= policy.duplicate_heavy_rate:
        return ResearchGovernorReasonCode.DUPLICATE_HEAVY_ROUND_TWO
    if (
        evaluation.consecutive_unproductive_source_count
        >= policy.consecutive_unproductive_source_limit
    ):
        return ResearchGovernorReasonCode.CONSECUTIVE_UNPRODUCTIVE_SOURCES
    if not evaluation.remaining_search_angles:
        return ResearchGovernorReasonCode.NO_MEANINGFUL_SEARCH_ANGLE
    if not evaluation.cumulative_budget.full_round_three_reserved:
        return ResearchGovernorReasonCode.INSUFFICIENT_RESERVED_BUDGET
    return ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED


def _explanation(
    evaluation: ResearchGovernorEvaluationInput,
    policy: ResearchGovernorPolicy,
    reason: ResearchGovernorReasonCode,
    duplicate_rate: float,
) -> str:
    """Render a secret-free application-owned summary of the deterministic decision."""
    family_count = evaluation.independent_approved_family_count
    if reason is ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED:
        return (
            f"Round 3 was authorized: {family_count} independent approved source families "
            f"remain, {len(evaluation.remaining_search_angles)} materially new search angles "
            "remain, and the complete planned workload is conservatively reserved."
        )
    if reason is ResearchGovernorReasonCode.PORTFOLIO_COMPLETE:
        return (
            "Round 3 was not started because the portfolio already has "
            f"{family_count} independent approved source families."
        )
    if reason is ResearchGovernorReasonCode.DUPLICATE_HEAVY_ROUND_TWO:
        return (
            f"Round 3 was not started because {duplicate_rate:.0%} of Round 2 results duplicated "
            "known source families, meeting the "
            f"{policy.duplicate_heavy_rate:.0%} stopping threshold."
        )
    if reason is ResearchGovernorReasonCode.CONSECUTIVE_UNPRODUCTIVE_SOURCES:
        return (
            "Round 3 was not started because recent research reached the deterministic "
            "limit of "
            f"{policy.consecutive_unproductive_source_limit} consecutive unproductive sources."
        )
    if reason is ResearchGovernorReasonCode.NO_MEANINGFUL_SEARCH_ANGLE:
        return "Round 3 was not started because all meaningful search angles were exhausted."
    if reason is ResearchGovernorReasonCode.INSUFFICIENT_RESERVED_BUDGET:
        return (
            "Round 3 was not started because the remaining cumulative budget cannot reserve "
            "its complete planned workload."
        )
    if reason is ResearchGovernorReasonCode.RUN_CANCELLED:
        return "Research was stopped because the user cancelled the run."
    if reason is ResearchGovernorReasonCode.TERMINAL_PROVIDER_FAILURE:
        return (
            "Round 3 was not started because a terminal provider or infrastructure failure "
            "prevents useful research."
        )
    return "Round 3 was not started because the fixed maximum of three research rounds was reached."
