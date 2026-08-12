"""Offline regression coverage for the bounded MVP-11 Research Governor."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from models import (
    ResearchGovernorBudgetState,
    ResearchGovernorDecisionOutcome,
    ResearchGovernorEvaluationInput,
    ResearchGovernorReasonCode,
    ResearchRoundRecord,
    ResearchRoundStatus,
    ResearchTerminalOutcome,
    RunManifest,
    RunStatus,
    Stage,
)
from research_governor import classify_terminal_outcome, evaluate_round_three_authorization
from store import (
    init_db,
    insert_research_governor_decision,
    insert_research_round_record,
    insert_research_terminal_result,
    insert_run,
    read_research_governor_decision,
    read_research_round_records,
    read_research_terminal_result,
)

RUN_ID = UUID("11000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 11, tzinfo=UTC)


def _budget(*, reserved: bool = True) -> ResearchGovernorBudgetState:
    return ResearchGovernorBudgetState(
        model_calls_used=8,
        model_calls_remaining=48,
        retrievals_used=36,
        retrievals_remaining=36,
        conservative_tokens_used=1000,
        tokens_remaining=9000,
        conservative_cost_used_usd=Decimal("0.10"),
        cost_remaining_usd=Decimal("0.90"),
        round_three_model_calls_required=8,
        round_three_retrievals_required=18,
        round_three_tokens_required=1000,
        round_three_cost_required_usd=Decimal("0.10"),
        full_round_three_reserved=reserved,
    )


def _evaluation(
    *,
    families: int = 2,
    duplicates: int = 0,
    results: int = 10,
    unproductive: int = 0,
    angles: tuple[str, ...] = ("independent longitudinal evidence",),
    reserved: bool = True,
    cancelled: bool = False,
    failure: bool = False,
) -> ResearchGovernorEvaluationInput:
    return ResearchGovernorEvaluationInput(
        run_id=RUN_ID,
        independent_approved_family_count=families,
        round_two_duplicate_count=duplicates,
        round_two_result_count=results,
        consecutive_unproductive_source_count=unproductive,
        remaining_search_angles=angles,
        cumulative_budget=_budget(reserved=reserved),
        cancelled=cancelled,
        terminal_provider_or_infrastructure_failure=failure,
        decided_at=NOW,
    )


@pytest.mark.parametrize(
    ("evaluation", "outcome", "reason"),
    (
        (
            _evaluation(families=3),
            ResearchGovernorDecisionOutcome.FINALIZE,
            ResearchGovernorReasonCode.PORTFOLIO_COMPLETE,
        ),
        (
            _evaluation(duplicates=7),
            ResearchGovernorDecisionOutcome.FINALIZE,
            ResearchGovernorReasonCode.DUPLICATE_HEAVY_ROUND_TWO,
        ),
        (
            _evaluation(unproductive=3),
            ResearchGovernorDecisionOutcome.FINALIZE,
            ResearchGovernorReasonCode.CONSECUTIVE_UNPRODUCTIVE_SOURCES,
        ),
        (
            _evaluation(angles=()),
            ResearchGovernorDecisionOutcome.FINALIZE,
            ResearchGovernorReasonCode.NO_MEANINGFUL_SEARCH_ANGLE,
        ),
        (
            _evaluation(reserved=False),
            ResearchGovernorDecisionOutcome.FINALIZE,
            ResearchGovernorReasonCode.INSUFFICIENT_RESERVED_BUDGET,
        ),
        (
            _evaluation(cancelled=True),
            ResearchGovernorDecisionOutcome.FINALIZE,
            ResearchGovernorReasonCode.RUN_CANCELLED,
        ),
        (
            _evaluation(failure=True),
            ResearchGovernorDecisionOutcome.FINALIZE,
            ResearchGovernorReasonCode.TERMINAL_PROVIDER_FAILURE,
        ),
        (
            _evaluation(),
            ResearchGovernorDecisionOutcome.BEGIN_ROUND_THREE,
            ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED,
        ),
    ),
)
def test_round_three_decision_is_deterministic_and_fail_closed(
    evaluation: ResearchGovernorEvaluationInput,
    outcome: ResearchGovernorDecisionOutcome,
    reason: ResearchGovernorReasonCode,
) -> None:
    decision = evaluate_round_three_authorization(evaluation)

    assert decision.decision is outcome
    assert decision.reason_code is reason
    assert decision.current_round == 2
    assert decision.policy_version == "mvp11-research-governor-v1"


@pytest.mark.parametrize("research_round", (0, 4, -1, 99))
def test_research_round_model_never_accepts_a_round_outside_one_through_three(
    research_round: int,
) -> None:
    with pytest.raises(ValidationError):
        ResearchRoundRecord(
            run_id=RUN_ID,
            research_round=research_round,
            status=ResearchRoundStatus.COMPLETED,
            planned_query_count=6,
            planned_discovery_count=30,
            completed_query_count=6,
            completed_discovery_count=30,
            started_at=NOW,
            completed_at=NOW,
            stopping_reason="Completed all planned work.",
        )


@pytest.mark.parametrize(
    ("families", "cancelled", "failed", "expected"),
    (
        (3, False, False, ResearchTerminalOutcome.COMPLETE),
        (1, False, False, ResearchTerminalOutcome.LIMITED),
        (0, False, False, ResearchTerminalOutcome.INSUFFICIENT),
        (2, True, False, ResearchTerminalOutcome.CANCELLED),
        (2, False, True, ResearchTerminalOutcome.FAILED),
    ),
)
def test_terminal_outcomes_are_always_classified_without_a_fourth_round(
    families: int,
    cancelled: bool,
    failed: bool,
    expected: ResearchTerminalOutcome,
) -> None:
    result = classify_terminal_outcome(
        run_id=RUN_ID,
        completed_rounds=3,
        independent_approved_family_count=families,
        cancelled=cancelled,
        failed=failed,
        explanation="The permitted research rounds are complete.",
        finalized_at=NOW,
    )

    assert result.outcome is expected
    assert result.completed_rounds == 3


def test_governor_records_are_append_only_and_sqlite_rejects_round_four(tmp_path: Path) -> None:
    db_path = tmp_path / "governor.sqlite3"
    init_db(str(db_path))
    insert_run(
        str(db_path),
        RunManifest(
            run_id=RUN_ID,
            status=RunStatus.RUNNING,
            raw_claim="A public claim under review.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    round_one = ResearchRoundRecord(
        run_id=RUN_ID,
        research_round=1,
        status=ResearchRoundStatus.COMPLETED,
        planned_query_count=6,
        planned_discovery_count=30,
        completed_query_count=6,
        completed_discovery_count=30,
        started_at=NOW,
        completed_at=NOW,
        stopping_reason="Round 1 completed.",
    )
    insert_research_round_record(str(db_path), round_one)
    decision = evaluate_round_three_authorization(_evaluation())
    insert_research_governor_decision(str(db_path), decision)
    terminal = classify_terminal_outcome(
        run_id=RUN_ID,
        completed_rounds=2,
        independent_approved_family_count=2,
        explanation="Round 3 was not authorized in this recorded test run.",
        finalized_at=NOW,
    )
    insert_research_terminal_result(str(db_path), terminal)

    assert read_research_round_records(str(db_path), RUN_ID) == (round_one,)
    assert read_research_governor_decision(str(db_path), RUN_ID) == decision
    assert read_research_terminal_result(str(db_path), RUN_ID) == terminal
    with sqlite3.connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            connection.execute(
                """INSERT INTO research_round_records
                   (run_id, research_round, payload_json, completed_at) VALUES (?, 4, '{}', ?)""",
                (str(RUN_ID), NOW.isoformat()),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM research_round_records WHERE run_id = ?", (str(RUN_ID),)
            )
