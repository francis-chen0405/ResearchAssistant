from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from test_v2_phase9_luna_evidence_analyst import (
    NOW,
    FakeLunaAnalyst,
    _assessment,
    _batch_input,
    _prepare_db,
    _routing,
)
from test_v2_phase9_luna_evidence_analyst import (
    _prepare_db as _prepare_analyst_db,
)
from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved

import agents.v2_evidence_analyst as analyst_agent
import agents.v2_reviewer_ledger as reviewer_ledger
from agents.v2_evidence_analyst import V2EvidenceAnalystFailure, run_v2_evidence_analyst
from researchassistant.contracts.models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    StatementReviewResult,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystModelOutput,
    V2EvidenceAnalystSourceResult,
)
from researchassistant.storage.store import finish_model_route_attempt, read_model_route_attempts


def _analyst_setup(
    tmp_path: Path,
) -> tuple[str, V2EvidenceAnalystBatchResult, V2EvidenceAnalystSourceResult]:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=_batch_input(run_id),
        llm_provider=Phase10Provider([_approved()]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    source = analyst.source_results[0]
    assert source.candidate is not None
    assert source.statement_draft is not None
    return path, analyst, source


def _review_once(
    path: str,
    analyst: V2EvidenceAnalystBatchResult,
    source: V2EvidenceAnalystSourceResult,
    provider: Phase10Provider,
    clock: Callable[[], datetime] = lambda: NOW,
) -> tuple[StatementReviewResult | None, str | None]:
    assert source.candidate is not None
    assert source.statement_draft is not None
    return reviewer_ledger._review_once(
        path,
        analyst,
        source.source_id,
        source.candidate,
        source.statement_draft,
        provider,
        _routing(),
        clock,
        0,
    )


@pytest.mark.parametrize(
    ("column", "sql_value"),
    [
        ("stage", "'planner'"),
        ("output_type", "'OtherDecision'"),
        ("model_alias", "'different-model'"),
        ("pinned_model_snapshot", "'different-deployment'"),
        ("input_artifact_ids", "'[\"00000000-0000-0000-0000-000000000099\"]'"),
        ("reserved_tokens", "reserved_tokens + 1"),
        ("reserved_cost_usd_exact", "'0.123'"),
    ],
    ids=["stage", "output", "model", "pin", "inputs", "reserved-tokens", "reserved-cost"],
)
def test_reviewer_completed_replay_rejects_identity_drift(
    tmp_path: Path,
    column: str,
    sql_value: str,
) -> None:
    path, analyst, source = _analyst_setup(tmp_path)
    first, failure = _review_once(path, analyst, source, Phase10Provider([_approved()]))
    assert first is not None and failure is None
    operation_id = uuid5(
        NAMESPACE_URL,
        f"v2-phase10::{analyst.run_id}::{source.source_id}::reviewer::0",
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE model_route_attempts SET {column} = {sql_value} WHERE operation_id = ?",
            (str(operation_id),),
        )
        connection.commit()

    provider = Phase10Provider([])
    with pytest.raises(ValueError, match="identity"):
        _review_once(path, analyst, source, provider)
    assert provider.requests == []


def test_reviewer_compatible_completion_reuses_original_start_without_provider(
    tmp_path: Path,
) -> None:
    path, analyst, source = _analyst_setup(tmp_path)
    first, failure = _review_once(path, analyst, source, Phase10Provider([_approved()]))
    assert first is not None and failure is None
    provider = Phase10Provider([])

    resumed, failure = _review_once(
        path, analyst, source, provider, lambda: NOW + timedelta(minutes=20)
    )

    assert first is not None and resumed is not None
    assert resumed.model_copy(update={"reviewed_at": first.reviewed_at}) == first
    assert resumed.reviewed_at == NOW + timedelta(minutes=20)
    assert failure is None
    assert provider.requests == []


def test_terminal_completion_returned_by_reservation_is_reused_without_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, analyst, source = _analyst_setup(tmp_path)
    original_reserve = reviewer_ledger.reserve_model_route_attempt
    draft = source.statement_draft
    assert draft is not None

    def reserve_then_complete(
        path: str,
        attempt: ModelRouteAttempt,
        *,
        max_model_calls: int,
        max_total_tokens: int | None = None,
        max_total_cost_usd: Decimal | None = None,
    ) -> ModelRouteAttempt:
        reserved = original_reserve(
            path,
            attempt,
            max_model_calls=max_model_calls,
            max_total_tokens=max_total_tokens,
            max_total_cost_usd=max_total_cost_usd,
        )
        decision = _approved().model_copy(update={"reviewed_statement": draft.draft_statement})
        completed = reserved.model_copy(
            update={
                "status": ModelAttemptStatus.COMPLETED,
                "ended_at": NOW + timedelta(seconds=1),
                "latency_ms": 1000,
                "usage": ModelUsageMetadata(total_tokens=15, cost_usd=Decimal("0.001")),
                "output_json": decision.model_dump_json(),
            }
        )
        finish_model_route_attempt(path, completed)
        return completed

    monkeypatch.setattr(reviewer_ledger, "reserve_model_route_attempt", reserve_then_complete)
    provider = Phase10Provider([])

    result, failure = _review_once(path, analyst, source, provider)

    assert result is not None
    assert result.approved is True
    assert failure is None
    assert provider.requests == []


def test_reviewer_budget_uses_reservation_for_running_usage_claims(tmp_path: Path) -> None:
    path, analyst, _source = _analyst_setup(tmp_path)
    attempt = read_model_route_attempts(path, analyst.run_id)[0]
    assert attempt.reserved_tokens is not None
    assert attempt.reserved_cost_usd is not None
    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE model_route_attempts
               SET status = 'running', ended_at = NULL, latency_ms = NULL,
                   output_json = NULL,
                   input_tokens = 1, output_tokens = 0, total_tokens = 1,
                   cost_usd = NULL, cost_usd_exact = '0.000001'
               WHERE attempt_id = ?""",
            (str(attempt.attempt_id),),
        )
        connection.commit()

    initial = analyst.input.queue_result.initial_budget
    _calls, token_ceiling, cost_ceiling = reviewer_ledger._budget_ceiling(path, analyst)

    assert token_ceiling == initial.tokens_remaining + attempt.reserved_tokens
    assert cost_ceiling == initial.cost_remaining_usd + attempt.reserved_cost_usd


def test_reviewer_budget_refuses_unknown_running_exposure_without_reservation(
    tmp_path: Path,
) -> None:
    path, analyst, _source = _analyst_setup(tmp_path)
    attempt = read_model_route_attempts(path, analyst.run_id)[0]
    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE model_route_attempts
               SET status = 'running', ended_at = NULL, latency_ms = NULL,
                   output_json = NULL, input_tokens = NULL, output_tokens = NULL,
                   total_tokens = NULL, cost_usd = NULL, cost_usd_exact = NULL,
                   reserved_tokens = NULL, reserved_cost_usd = NULL,
                   reserved_cost_usd_exact = NULL
               WHERE attempt_id = ?""",
            (str(attempt.attempt_id),),
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="token exposure cannot be proven"):
        reviewer_ledger._budget_ceiling(path, analyst)


def _analyst_call(
    path: str,
    batch_input: V2EvidenceAnalystBatchInput,
    provider: FakeLunaAnalyst,
    clock: Callable[[], datetime],
) -> tuple[V2EvidenceAnalystModelOutput, tuple[UUID, ...]]:
    source_input = batch_input.queued_candidates[0]
    return analyst_agent._invoke_bounded_analyst(
        db_path=path,
        batch_input=batch_input,
        source_id=source_input.source_id,
        operation="database-replay-phase2-test",
        input_artifact=source_input,
        output_type=V2EvidenceAnalystModelOutput,
        llm_provider=provider,
        routing_config=_routing(),
        clock=clock,
        objective_validator=lambda _output: None,
    )


def _analyst_direct_setup(tmp_path: Path) -> tuple[str, V2EvidenceAnalystBatchInput]:
    run_id = uuid4()
    batch_input = _batch_input(run_id)
    return _prepare_analyst_db(tmp_path, run_id), batch_input


@pytest.mark.parametrize(
    ("column", "sql_value"),
    [
        ("stage", "'planner'"),
        ("output_type", "'OtherDecision'"),
        ("model_alias", "'different-model'"),
        ("pinned_model_snapshot", "'different-deployment'"),
        ("input_artifact_ids", "'[\"00000000-0000-0000-0000-000000000099\"]'"),
        ("reserved_tokens", "reserved_tokens + 1"),
        ("reserved_cost_usd_exact", "'0.123'"),
    ],
    ids=["stage", "output", "model", "pin", "inputs", "reserved-tokens", "reserved-cost"],
)
def test_analyst_completed_replay_rejects_identity_drift(
    tmp_path: Path,
    column: str,
    sql_value: str,
) -> None:
    path, batch_input = _analyst_direct_setup(tmp_path)
    _analyst_call(path, batch_input, FakeLunaAnalyst([_assessment()]), lambda: NOW)
    attempt = read_model_route_attempts(path, batch_input.run_id)[0]
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE model_route_attempts SET {column} = {sql_value} WHERE attempt_id = ?",
            (str(attempt.attempt_id),),
        )
        connection.commit()

    provider = FakeLunaAnalyst([])
    with pytest.raises(V2EvidenceAnalystFailure, match="identity"):
        _analyst_call(path, batch_input, provider, lambda: NOW + timedelta(minutes=10))
    assert provider.requests == []


def test_analyst_matching_completion_reuses_original_start_with_new_clock(
    tmp_path: Path,
) -> None:
    path, batch_input = _analyst_direct_setup(tmp_path)
    output, _ = _analyst_call(path, batch_input, FakeLunaAnalyst([_assessment()]), lambda: NOW)
    later = NOW + timedelta(minutes=30)
    provider = FakeLunaAnalyst([])

    replayed, _ = _analyst_call(path, batch_input, provider, lambda: later)

    assert replayed == output
    assert provider.requests == []


def test_analyst_terminal_completion_returned_by_reservation_skips_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, batch_input = _analyst_direct_setup(tmp_path)
    original_reserve = analyst_agent.reserve_model_route_attempt

    def reserve_then_complete(
        path: str,
        attempt: ModelRouteAttempt,
        *,
        max_model_calls: int,
        max_total_tokens: int | None = None,
        max_total_cost_usd: Decimal | None = None,
    ) -> ModelRouteAttempt:
        reserved = original_reserve(
            path,
            attempt,
            max_model_calls=max_model_calls,
            max_total_tokens=max_total_tokens,
            max_total_cost_usd=max_total_cost_usd,
        )
        output = _assessment()
        completed = reserved.model_copy(
            update={
                "status": ModelAttemptStatus.COMPLETED,
                "ended_at": NOW + timedelta(seconds=1),
                "latency_ms": 1000,
                "usage": ModelUsageMetadata(total_tokens=120, cost_usd=Decimal("0.0012")),
                "output_json": output.model_dump_json(),
            }
        )
        finish_model_route_attempt(path, completed)
        return completed

    monkeypatch.setattr(analyst_agent, "reserve_model_route_attempt", reserve_then_complete)
    provider = FakeLunaAnalyst([])

    output, _ = _analyst_call(path, batch_input, provider, lambda: NOW)

    assert output == _assessment()
    assert provider.requests == []


def test_analyst_mismatched_terminal_reservation_fails_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, batch_input = _analyst_direct_setup(tmp_path)
    original_reserve = analyst_agent.reserve_model_route_attempt

    def reserve_then_return_mismatched_terminal(
        path: str,
        attempt: ModelRouteAttempt,
        *,
        max_model_calls: int,
        max_total_tokens: int | None = None,
        max_total_cost_usd: Decimal | None = None,
    ) -> ModelRouteAttempt:
        reserved = original_reserve(
            path,
            attempt,
            max_model_calls=max_model_calls,
            max_total_tokens=max_total_tokens,
            max_total_cost_usd=max_total_cost_usd,
        )
        return reserved.model_copy(
            update={
                "status": ModelAttemptStatus.COMPLETED,
                "pinned_model_snapshot": "different-deployment",
                "ended_at": NOW + timedelta(seconds=1),
                "latency_ms": 1000,
                "output_json": _assessment().model_dump_json(),
            }
        )

    monkeypatch.setattr(
        analyst_agent, "reserve_model_route_attempt", reserve_then_return_mismatched_terminal
    )
    provider = FakeLunaAnalyst([])

    with pytest.raises(V2EvidenceAnalystFailure, match="identity") as exc_info:
        _analyst_call(path, batch_input, provider, lambda: NOW)

    assert isinstance(exc_info.value.__cause__, sqlite3.IntegrityError)
    assert provider.requests == []


def test_analyst_running_claim_uses_reservation_and_unknown_fails_closed(
    tmp_path: Path,
) -> None:
    path, batch_input = _analyst_direct_setup(tmp_path)
    _analyst_call(path, batch_input, FakeLunaAnalyst([_assessment()]), lambda: NOW)
    attempt = read_model_route_attempts(path, batch_input.run_id)[0]
    assert attempt.reserved_tokens is not None
    assert attempt.reserved_cost_usd is not None
    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE model_route_attempts
               SET output_type = 'BaselineDecision', status = 'running',
                   ended_at = NULL, latency_ms = NULL,
                   output_json = NULL, input_tokens = 1, output_tokens = 0,
                   total_tokens = 1, cost_usd = NULL, cost_usd_exact = '0.000001'
               WHERE attempt_id = ?""",
            (str(attempt.attempt_id),),
        )
        connection.commit()

    _calls, tokens, cost = analyst_agent._attempt_budget_ceilings(path, batch_input)
    initial = batch_input.queue_result.initial_budget
    assert tokens == initial.tokens_remaining + attempt.reserved_tokens
    assert cost == initial.cost_remaining_usd + attempt.reserved_cost_usd

    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE model_route_attempts
               SET input_tokens = NULL, output_tokens = NULL, total_tokens = NULL,
                   cost_usd = NULL, cost_usd_exact = NULL, reserved_tokens = NULL,
                   reserved_cost_usd = NULL, reserved_cost_usd_exact = NULL
               WHERE attempt_id = ?""",
            (str(attempt.attempt_id),),
        )
        connection.commit()
    with pytest.raises(V2EvidenceAnalystFailure, match="unprovable token exposure"):
        analyst_agent._attempt_budget_ceilings(path, batch_input)


def test_analyst_terminal_input_output_usage_proves_tokens_without_reservation(
    tmp_path: Path,
) -> None:
    path, batch_input = _analyst_direct_setup(tmp_path)
    _analyst_call(path, batch_input, FakeLunaAnalyst([_assessment()]), lambda: NOW)
    attempt = read_model_route_attempts(path, batch_input.run_id)[0]
    terminal_without_reservation = attempt.model_copy(
        update={
            "reserved_tokens": None,
            "usage": ModelUsageMetadata(
                input_tokens=17,
                output_tokens=23,
                total_tokens=None,
                cost_usd=Decimal("0.001"),
            ),
        }
    )

    assert analyst_agent._token_exposure(terminal_without_reservation) == 40
