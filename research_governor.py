"""Deterministic MVP-11 Research Governor policy and terminal classification."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from models import (
    ResearchGovernorDecision,
    ResearchGovernorDecisionOutcome,
    ResearchGovernorEvaluationInput,
    ResearchGovernorPolicy,
    ResearchGovernorReasonCode,
    ResearchTerminalOutcome,
    ResearchTerminalResult,
)

DEFAULT_RESEARCH_GOVERNOR_POLICY = ResearchGovernorPolicy()


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
