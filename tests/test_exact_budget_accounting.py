from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveBudgetState,
    V2SearchAgentReservation,
)
from researchassistant.agents.adaptive_planning import _budget_after_rejected_plan_attempt
from researchassistant.agents.evidence_checkpoint import _checkpoint_cost_allowance
from researchassistant.agents.post_analysis_round import (
    _combined_queue_cost,
    _source_budget_fits,
)
from researchassistant.agents.round_four_summary import _gap_budget_after_protection
from researchassistant.agents.v2_gap_analysis import _budget_can_reserve
from researchassistant.contracts.models import V2GapBudgetState
from researchassistant.contracts.research_gaps import V2GapAnalysisAttempt, V2GapReservation
from researchassistant.providers.llm import LLMStage


def test_retry_reserve_subtraction_keeps_sub_cent_precision() -> None:
    remaining = V2AdaptiveBudgetState(
        model_calls_remaining=4,
        cost_remaining_usd=Decimal("1.00000000000000000000000000009"),
    )
    reservation = V2SearchAgentReservation(
        input_tokens=1,
        output_tokens=1,
        reserved_tokens=2,
        reserved_cost_usd=Decimal("0.00000000000000000000000000008"),
    )

    reduced = _budget_after_rejected_plan_attempt(remaining, reservation)

    assert reduced.cost_remaining_usd == Decimal("1.00000000000000000000000000001")


def test_gap_attempt_cost_gate_does_not_round_down() -> None:
    attempt = V2GapAnalysisAttempt(
        attempt_number=1,
        reservation=V2GapReservation(
            input_tokens=1,
            output_tokens=1,
            reserved_tokens=2,
            reserved_cost_usd=Decimal("1.00000000000000000000000000001"),
        ),
        succeeded=True,
    )
    next_reservation = V2GapReservation(
        input_tokens=1,
        output_tokens=1,
        reserved_tokens=2,
        reserved_cost_usd=Decimal("0.00000000000000000000000000001"),
    )
    budget = V2GapBudgetState(
        model_calls_remaining=3,
        tokens_remaining=10,
        cost_remaining_usd=Decimal("1.00000000000000000000000000001"),
    )

    assert not _budget_can_reserve(budget, [attempt], next_reservation)


def test_round_four_summary_subtracts_protected_cost_exactly() -> None:
    budget = V2AdaptiveBudgetState(
        model_calls_remaining=10,
        cost_remaining_usd=Decimal("1.00000000000000000000000000009"),
        protected_downstream_cost_usd=Decimal("0.00000000000000000000000000008"),
    )

    gap_budget = _gap_budget_after_protection(budget)

    assert gap_budget.cost_remaining_usd == Decimal("1.00000000000000000000000000001")


def test_evidence_checkpoint_halves_high_precision_budget_exactly() -> None:
    assert _checkpoint_cost_allowance(Decimal("1.00000000000000000000000000001")) == Decimal(
        "0.500000000000000000000000000005"
    )


@dataclass(frozen=True)
class _Reservation:
    reserved_tokens: int
    reserved_cost_usd: Decimal


class _Preflight:
    def reserve(self, stage: LLMStage, input_tokens: int) -> _Reservation:
        del input_tokens
        cost = Decimal("1.00000000000000000000000000001")
        if stage is LLMStage.EXTRACTOR:
            return _Reservation(reserved_tokens=1, reserved_cost_usd=cost)
        return _Reservation(reserved_tokens=1, reserved_cost_usd=Decimal("0"))


class _RoutingConfig:
    def preflight(self) -> _Preflight:
        return _Preflight()


def test_post_analysis_cost_gate_counts_repeated_reservations_exactly() -> None:
    budget = V2AdaptiveBudgetState(
        model_calls_remaining=100,
        tokens_remaining=100_000,
        cost_remaining_usd=Decimal("2.00000000000000000000000000001"),
        protected_downstream_model_calls=0,
    )

    assert not _source_budget_fits(budget, _RoutingConfig(), planned_queries=2)  # type: ignore[arg-type]


def test_combined_post_analysis_queue_cost_preserves_precision() -> None:
    assert _combined_queue_cost(
        Decimal("1.00000000000000000000000000001"),
        Decimal("0.00000000000000000000000000001"),
    ) == Decimal("1.00000000000000000000000000002")
