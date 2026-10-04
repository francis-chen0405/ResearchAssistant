from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from pydantic import ValidationError

import researchassistant.storage.store as store_module
from researchassistant.contracts.models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageCostBasis,
    ModelUsageMetadata,
    RunManifest,
    RunStatus,
    Stage,
)
from researchassistant.storage import store_schema
from researchassistant.storage.database_recovery import BackupPolicy, list_backups
from researchassistant.storage.store import (
    ModelAttemptBudgetError,
    finish_model_route_attempt,
    init_db,
    insert_run,
    read_model_route_attempts,
    reserve_model_route_attempt,
)

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
RUN_ID = UUID(int=442)


def _manifest(run_id: UUID = RUN_ID) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_claim="Attempt accounting integrity phase 2",
        current_stage=Stage.EVIDENCE_ANALYST,
        created_at=NOW,
        updated_at=NOW,
    )


def _attempt(
    index: int = 0,
    *,
    status: ModelAttemptStatus = ModelAttemptStatus.RUNNING,
    usage: ModelUsageMetadata | None = None,
    reserved_tokens: int | None = 100,
    reserved_cost_usd: Decimal | None = Decimal("0.1"),
    operation_id: UUID | None = None,
    attempt_id: UUID | None = None,
) -> ModelRouteAttempt:
    started = NOW + timedelta(seconds=index)
    finished = status is not ModelAttemptStatus.RUNNING
    return ModelRouteAttempt(
        run_id=RUN_ID,
        operation_id=operation_id or UUID(int=1000 + index),
        attempt_id=attempt_id or UUID(int=2000 + index),
        stage="analyst",
        output_type="AnalystOutput",
        model_alias="gpt-6-luna-xhigh",
        pinned_model_snapshot="gpt-6-luna-xhigh-2026-10-01",
        route_index=index % 2,
        attempt_number=index + 1,
        input_artifact_ids=(UUID(int=3000 + index),),
        status=status,
        retry_reason="retry after provider timeout" if index else None,
        escalation_reason="escalate for difficult evidence" if index else None,
        failure_code="timeout" if status is ModelAttemptStatus.FAILED else None,
        failure_reason="provider timed out" if status is ModelAttemptStatus.FAILED else None,
        started_at=started,
        ended_at=started + timedelta(seconds=2) if finished else None,
        latency_ms=2000 if finished else None,
        reserved_tokens=reserved_tokens,
        reserved_cost_usd=reserved_cost_usd,
        usage=usage,
        output_json="{}" if status is ModelAttemptStatus.COMPLETED else None,
    )


def _finished(
    attempt: ModelRouteAttempt,
    *,
    usage: ModelUsageMetadata | None = None,
) -> ModelRouteAttempt:
    updates: dict[str, object] = {
        "status": ModelAttemptStatus.COMPLETED,
        "ended_at": attempt.started_at + timedelta(seconds=2),
        "latency_ms": 2000,
        "usage": usage
        or ModelUsageMetadata(
            input_tokens=60,
            cached_input_tokens=20,
            uncached_input_tokens=40,
            output_tokens=10,
            total_tokens=70,
            cost_usd=Decimal("0.0001234567890123456789"),
        ),
        "output_json": "{}",
    }
    return attempt.model_copy(update=updates)


def _database(tmp_path: Path, *, run_id: UUID = RUN_ID) -> Path:
    db_path = tmp_path / "attempt-integrity.sqlite3"
    init_db(str(db_path))
    insert_run(str(db_path), _manifest(run_id))
    return db_path


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _downgrade_to_v14(path: Path) -> None:
    with closing(_connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        canonical = store_schema._canonical_schema()
        for kind, name, _sql in reversed(canonical):
            if store_schema._object_version(kind, name) > 14 and kind in {"trigger", "index"}:
                connection.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')
        for kind, name, _sql in reversed(canonical):
            if kind == "table" and store_schema._object_version(kind, name) > 14:
                connection.execute(f'DROP TABLE IF EXISTS "{name}"')
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for table_row in table_rows:
            table_name = table_row["name"]
            columns = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            for column in columns:
                if store_schema._column_version(table_name, column["name"]) > 14:
                    connection.execute(f'ALTER TABLE "{table_name}" DROP COLUMN "{column["name"]}"')
        connection.execute("DELETE FROM schema_migrations WHERE version > 14")
        connection.execute("PRAGMA user_version = 14")
        connection.commit()


def _reserved_database(
    tmp_path: Path, attempt: ModelRouteAttempt | None = None
) -> tuple[Path, ModelRouteAttempt]:
    db_path = _database(tmp_path)
    attempt = attempt or _attempt()
    reserve_model_route_attempt(str(db_path), attempt, max_model_calls=8)
    return db_path, attempt


def test_cache_write_tokens_survive_finish_replay_and_database_round_trip(
    tmp_path: Path,
) -> None:
    db_path, attempt = _reserved_database(tmp_path)
    usage = ModelUsageMetadata(
        input_tokens=90,
        cached_input_tokens=30,
        uncached_input_tokens=60,
        cache_write_tokens=10,
        output_tokens=12,
        total_tokens=102,
        cost_usd=Decimal("0.01234567890123456789"),
        usage_cost_basis=ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES,
    )
    completed = _finished(attempt, usage=usage)

    finish_model_route_attempt(str(db_path), completed)
    finish_model_route_attempt(str(db_path), completed)

    restored = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert restored.usage == usage
    assert restored.usage.cache_write_tokens == 10
    assert restored.usage.usage_cost_basis is (
        ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES
    )


def test_attempt_reservation_round_trip_preserves_full_provenance_and_reservation(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    attempt = _attempt(1)

    returned = reserve_model_route_attempt(str(db_path), attempt, max_model_calls=8)
    restored = read_model_route_attempts(str(db_path), RUN_ID)[0]

    assert returned == attempt
    assert restored.run_id == attempt.run_id
    assert restored.operation_id == attempt.operation_id
    assert restored.attempt_id == attempt.attempt_id
    assert restored.stage == attempt.stage
    assert restored.output_type == attempt.output_type
    assert restored.model_alias == attempt.model_alias
    assert restored.pinned_model_snapshot == attempt.pinned_model_snapshot
    assert restored.route_index == attempt.route_index
    assert restored.attempt_number == attempt.attempt_number
    assert restored.input_artifact_ids == attempt.input_artifact_ids
    assert restored.retry_reason == attempt.retry_reason
    assert restored.escalation_reason == attempt.escalation_reason
    assert restored.started_at == attempt.started_at
    assert restored.reserved_tokens == attempt.reserved_tokens
    assert restored.reserved_cost_usd == attempt.reserved_cost_usd


@pytest.mark.parametrize(
    "usage",
    [
        ModelUsageMetadata(
            input_tokens=90,
            cached_input_tokens=30,
            uncached_input_tokens=60,
            cache_write_tokens=0,
            output_tokens=10,
            total_tokens=100,
            cost_usd=Decimal("0"),
            usage_cost_basis=ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES,
        ),
        ModelUsageMetadata(
            input_tokens=90,
            cached_input_tokens=30,
            uncached_input_tokens=60,
            output_tokens=10,
            total_tokens=100,
            cost_usd=Decimal("0.00000000000000000001"),
            usage_cost_basis=(
                ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_ASSUMED_ALL_UNCACHED_WRITES
            ),
        ),
        ModelUsageMetadata(
            input_tokens=90,
            output_tokens=10,
            total_tokens=100,
            cost_usd=Decimal("1.23456789012345678901"),
            usage_cost_basis=ModelUsageCostBasis.CONFIGURED_PRICE_CAP,
        ),
        ModelUsageMetadata(
            input_tokens=90,
            output_tokens=10,
            total_tokens=100,
            cost_usd=None,
            usage_cost_basis=None,
        ),
    ],
    ids=["reported-zero-cost", "assumed-write-cost", "configured-cap", "null-cost"],
)
def test_usage_cost_basis_and_decimal_values_round_trip(
    tmp_path: Path, usage: ModelUsageMetadata
) -> None:
    db_path, attempt = _reserved_database(tmp_path, _attempt(usage=usage))
    reserved = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert reserved.usage == usage
    completed = _finished(attempt, usage=usage)

    finish_model_route_attempt(str(db_path), completed)

    restored = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert restored.usage == usage


def test_running_reservation_round_trips_nullable_cost_without_inventing_usage(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    attempt = _attempt(reserved_tokens=None, reserved_cost_usd=None)

    reserve_model_route_attempt(str(db_path), attempt, max_model_calls=8)

    restored = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert restored.reserved_tokens is None
    assert restored.reserved_cost_usd is None
    assert restored.usage is None


def test_empty_usage_metadata_and_missing_usage_have_identical_persistence_semantics(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    empty_usage = ModelUsageMetadata()
    attempt = _attempt(usage=empty_usage)

    replayed = reserve_model_route_attempt(str(db_path), attempt, max_model_calls=8)
    assert replayed.usage is None
    completed = _finished(attempt, usage=empty_usage)
    finish_model_route_attempt(str(db_path), completed)
    finish_model_route_attempt(str(db_path), completed.model_copy(update={"usage": None}))

    restored = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert restored.usage is None


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "operation_id",
        "stage",
        "output_type",
        "model_alias",
        "pinned_model_snapshot",
        "route_index",
        "attempt_number",
        "input_artifact_ids",
        "retry_reason",
        "escalation_reason",
        "started_at",
        "reserved_tokens",
        "reserved_cost_usd",
    ],
)
def test_reservation_replay_rejects_same_attempt_id_with_different_identity(
    tmp_path: Path, field: str
) -> None:
    db_path = _database(tmp_path)
    original = _attempt()
    reserve_model_route_attempt(str(db_path), original, max_model_calls=8)
    replacements = {
        "run_id": UUID(int=9001),
        "operation_id": UUID(int=9002),
        "stage": "changed-stage",
        "output_type": "ChangedOutput",
        "model_alias": "other-model",
        "pinned_model_snapshot": "other-pinned-model",
        "route_index": 1,
        "attempt_number": 2,
        "input_artifact_ids": (UUID(int=9999),),
        "retry_reason": "different retry reason",
        "escalation_reason": "different escalation reason",
        "started_at": NOW + timedelta(days=1),
        "reserved_tokens": 101,
        "reserved_cost_usd": Decimal("0.11"),
    }
    replay = original.model_copy(update={field: replacements[field]})

    with pytest.raises(sqlite3.IntegrityError):
        reserve_model_route_attempt(str(db_path), replay, max_model_calls=8)

    assert read_model_route_attempts(str(db_path), RUN_ID) == [original]


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "operation_id",
        "stage",
        "output_type",
        "model_alias",
        "pinned_model_snapshot",
        "route_index",
        "attempt_number",
        "input_artifact_ids",
        "retry_reason",
        "escalation_reason",
        "started_at",
        "reserved_tokens",
        "reserved_cost_usd",
    ],
)
def test_completion_rejects_changes_to_reserved_identity_and_original_exposure(
    tmp_path: Path, field: str
) -> None:
    db_path, original = _reserved_database(tmp_path)
    completed = _finished(original)
    replacements = {
        "run_id": UUID(int=9001),
        "operation_id": UUID(int=9002),
        "stage": "changed-stage",
        "output_type": "ChangedOutput",
        "model_alias": "other-model",
        "pinned_model_snapshot": "other-pinned-model",
        "route_index": 1,
        "attempt_number": 2,
        "input_artifact_ids": (UUID(int=9999),),
        "retry_reason": "different retry reason",
        "escalation_reason": "different escalation reason",
        "started_at": NOW - timedelta(days=1),
        "reserved_tokens": 101,
        "reserved_cost_usd": Decimal("0.11"),
    }
    forged_completion = completed.model_copy(update={field: replacements[field]})

    with pytest.raises(sqlite3.IntegrityError):
        finish_model_route_attempt(str(db_path), forged_completion)

    assert read_model_route_attempts(str(db_path), RUN_ID) == [original]


def test_invalid_nested_usage_created_with_model_construct_is_rejected_at_reservation(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    invalid_usage = ModelUsageMetadata.model_construct(
        input_tokens=10,
        cached_input_tokens=8,
        uncached_input_tokens=1,
        cache_write_tokens=10,
        output_tokens=-1,
        total_tokens=99,
        cost_usd=Decimal("-0.01"),
        usage_cost_basis=ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES,
    )
    attempt = _attempt().model_copy(update={"usage": invalid_usage})

    with pytest.raises((ValidationError, ValueError)):
        reserve_model_route_attempt(str(db_path), attempt, max_model_calls=8)

    assert read_model_route_attempts(str(db_path), RUN_ID) == []


@pytest.mark.parametrize(
    "updates",
    [
        {"started_at": datetime(2026, 10, 1)},
        {"reserved_tokens": -1},
        {"reserved_cost_usd": Decimal("-0.01")},
        {"status": ModelAttemptStatus.RUNNING, "ended_at": NOW},
        {"status": ModelAttemptStatus.FAILED, "failure_code": None},
        {"status": ModelAttemptStatus.COMPLETED, "ended_at": None},
        {"status": ModelAttemptStatus.COMPLETED, "output_json": None},
        {"status": ModelAttemptStatus.FAILED, "failure_reason": None},
        {"status": ModelAttemptStatus.COMPLETED, "latency_ms": -1},
        {"status": ModelAttemptStatus.COMPLETED, "latency_ms": float("inf")},
    ],
)
def test_invalid_bypassed_attempt_shape_is_revalidated_before_persistence(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    db_path = _database(tmp_path)
    attempt = _attempt().model_copy(update=updates)

    with pytest.raises((ValidationError, ValueError)):
        reserve_model_route_attempt(str(db_path), attempt, max_model_calls=8)

    assert read_model_route_attempts(str(db_path), RUN_ID) == []


def test_invalid_nested_usage_created_with_model_construct_is_rejected_at_finish(
    tmp_path: Path,
) -> None:
    db_path, original = _reserved_database(tmp_path)
    invalid_usage = ModelUsageMetadata.model_construct(
        input_tokens=10,
        cached_input_tokens=8,
        uncached_input_tokens=1,
        cache_write_tokens=10,
        output_tokens=-1,
        total_tokens=99,
        cost_usd=Decimal("-0.01"),
        usage_cost_basis=ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES,
    )
    completed = _finished(original).model_copy(update={"usage": invalid_usage})

    with pytest.raises((ValidationError, ValueError)):
        finish_model_route_attempt(str(db_path), completed)

    assert read_model_route_attempts(str(db_path), RUN_ID) == [original]


def test_bypassed_invalid_decimal_cost_cannot_enter_through_model_copy(
    tmp_path: Path,
) -> None:
    db_path, original = _reserved_database(tmp_path)
    usage = ModelUsageMetadata.model_construct(
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        cost_usd=Decimal("NaN"),
        usage_cost_basis=ModelUsageCostBasis.CONFIGURED_PRICE_CAP,
    )
    completed = _finished(original).model_copy(update={"usage": usage})

    with pytest.raises((ValidationError, ValueError)):
        finish_model_route_attempt(str(db_path), completed)

    assert read_model_route_attempts(str(db_path), RUN_ID) == [original]


@pytest.mark.parametrize(
    "invalid_usage",
    [
        ModelUsageMetadata.model_construct(
            input_tokens=10,
            cached_input_tokens=8,
            uncached_input_tokens=1,
            output_tokens=1,
            total_tokens=11,
        ),
        ModelUsageMetadata.model_construct(
            input_tokens=10,
            cached_input_tokens=8,
            uncached_input_tokens=2,
            cache_write_tokens=3,
            output_tokens=1,
            total_tokens=11,
        ),
        ModelUsageMetadata.model_construct(
            input_tokens=10,
            cached_input_tokens=8,
            uncached_input_tokens=2,
            output_tokens=1,
            total_tokens=11,
            usage_cost_basis=ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES,
        ),
        ModelUsageMetadata.model_construct(
            input_tokens=10,
            cached_input_tokens=8,
            uncached_input_tokens=2,
            cache_write_tokens=1,
            output_tokens=1,
            total_tokens=11,
            usage_cost_basis=(
                ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_ASSUMED_ALL_UNCACHED_WRITES
            ),
        ),
        ModelUsageMetadata.model_construct(
            input_tokens=10,
            output_tokens=1,
            total_tokens=11,
            cost_usd=Decimal("0.1"),
            usage_cost_basis="unrecognized-cost-basis",
        ),
    ],
    ids=[
        "unbalanced-cache-split",
        "write-exceeds-uncached",
        "missing-write-count",
        "assumed-with-write-count",
        "unknown-cost-basis",
    ],
)
def test_completion_rejects_bypassed_cache_and_cost_basis_invariants(
    tmp_path: Path, invalid_usage: ModelUsageMetadata
) -> None:
    db_path, original = _reserved_database(tmp_path)
    completed = _finished(original, usage=invalid_usage)

    with pytest.raises((ValidationError, ValueError)):
        finish_model_route_attempt(str(db_path), completed)

    assert read_model_route_attempts(str(db_path), RUN_ID) == [original]


@pytest.mark.parametrize(
    "updates",
    [
        {"latency_ms": -1},
        {"latency_ms": float("inf")},
        {"latency_ms": float("nan")},
        {"ended_at": datetime(2026, 10, 1)},
        {"ended_at": None},
        {"output_json": None},
        {"output_json": "invalid JSON"},
        {"failure_code": "unexpected failure on completed record"},
        {"status": ModelAttemptStatus.FAILED, "failure_code": None},
        {"status": ModelAttemptStatus.FAILED, "failure_reason": None},
    ],
)
def test_finish_rejects_bypassed_invalid_completion_shape(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    db_path, original = _reserved_database(tmp_path)
    completed = _finished(original).model_copy(update=updates)

    with pytest.raises((ValidationError, ValueError)):
        finish_model_route_attempt(str(db_path), completed)

    assert read_model_route_attempts(str(db_path), RUN_ID) == [original]


def test_identical_sequential_finish_replay_is_idempotent_and_conflict_rejected(
    tmp_path: Path,
) -> None:
    db_path, original = _reserved_database(tmp_path)
    completed = _finished(original)
    finish_model_route_attempt(str(db_path), completed)
    finish_model_route_attempt(str(db_path), completed)
    conflict = completed.model_copy(
        update={"usage": completed.usage.model_copy(update={"cost_usd": Decimal("0.03")})}
    )

    with pytest.raises(sqlite3.IntegrityError, match="already finished differently"):
        finish_model_route_attempt(str(db_path), conflict)

    assert read_model_route_attempts(str(db_path), RUN_ID) == [completed]


def _concurrent_finishes(
    db_path: Path, attempts: tuple[ModelRouteAttempt, ...]
) -> list[BaseException | None]:
    entry = Barrier(len(attempts))

    def finish(attempt: ModelRouteAttempt) -> BaseException | None:
        try:
            entry.wait(timeout=5)
            finish_model_route_attempt(str(db_path), attempt)
        except BaseException as error:
            return error
        return None

    with ThreadPoolExecutor(max_workers=len(attempts)) as executor:
        futures = [executor.submit(finish, attempt) for attempt in attempts]
        return [future.result(timeout=10) for future in futures]


def test_identical_concurrent_finishes_are_idempotent_with_external_entry_barrier(
    tmp_path: Path,
) -> None:
    db_path, original = _reserved_database(tmp_path)
    completed = _finished(original)

    outcomes = _concurrent_finishes(db_path, (completed, completed))

    assert outcomes == [None, None]
    assert read_model_route_attempts(str(db_path), RUN_ID) == [completed]


def test_conflicting_concurrent_finishes_commit_only_one_result(tmp_path: Path) -> None:
    db_path, original = _reserved_database(tmp_path)
    completed = _finished(original)
    conflict = completed.model_copy(
        update={"usage": completed.usage.model_copy(update={"cost_usd": Decimal("0.03")})}
    )

    outcomes = _concurrent_finishes(db_path, (completed, conflict))

    assert sum(outcome is None for outcome in outcomes) == 1
    errors = [outcome for outcome in outcomes if outcome is not None]
    assert len(errors) == 1
    assert isinstance(errors[0], sqlite3.IntegrityError)
    assert read_model_route_attempts(str(db_path), RUN_ID)[0] in (completed, conflict)


def test_interrupted_finish_rolls_back_update_and_closes_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, original = _reserved_database(tmp_path)
    completed = _finished(original)

    class InterruptingConnection(sqlite3.Connection):
        def execute(self, sql: str, parameters: object = ()) -> sqlite3.Cursor:
            cursor = super().execute(sql, parameters)
            if sql.lstrip().upper().startswith("UPDATE MODEL_ROUTE_ATTEMPTS SET"):
                raise KeyboardInterrupt("injected interruption after update")
            return cursor

    def interrupting_connect(path: str) -> sqlite3.Connection:
        connection = sqlite3.connect(path, factory=InterruptingConnection)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(store_module, "_connect", interrupting_connect)
    with pytest.raises(KeyboardInterrupt, match="injected interruption"):
        finish_model_route_attempt(str(db_path), completed)

    monkeypatch.undo()
    assert read_model_route_attempts(str(db_path), RUN_ID) == [original]
    finish_model_route_attempt(str(db_path), completed)
    assert read_model_route_attempts(str(db_path), RUN_ID) == [completed]


@pytest.mark.parametrize(
    ("ceiling", "first_reservation", "second_reservation"),
    [
        ("calls", 0, 0),
        ("tokens", 60, 60),
        ("cost", Decimal("0.06"), Decimal("0.06")),
    ],
)
def test_different_operations_contend_for_shared_run_call_token_and_cost_limits(
    tmp_path: Path,
    ceiling: str,
    first_reservation: int | Decimal,
    second_reservation: int | Decimal,
) -> None:
    db_path = _database(tmp_path)
    first = _attempt(
        0,
        operation_id=UUID(int=777),
        reserved_tokens=first_reservation if ceiling == "tokens" else 10,
        reserved_cost_usd=first_reservation if ceiling == "cost" else Decimal("0.01"),
    )
    second = _attempt(
        1,
        operation_id=UUID(int=888),
        reserved_tokens=second_reservation if ceiling == "tokens" else 10,
        reserved_cost_usd=second_reservation if ceiling == "cost" else Decimal("0.01"),
    )
    reserve_model_route_attempt(str(db_path), first, max_model_calls=1 if ceiling == "calls" else 8)

    budget = {
        "max_total_tokens": 100 if ceiling == "tokens" else None,
        "max_total_cost_usd": Decimal("0.10") if ceiling == "cost" else None,
    }
    with pytest.raises(ModelAttemptBudgetError):
        reserve_model_route_attempt(
            str(db_path),
            second,
            max_model_calls=1 if ceiling == "calls" else 8,
            **budget,
        )

    assert len(read_model_route_attempts(str(db_path), RUN_ID)) == 1


@pytest.mark.parametrize("first_status", [ModelAttemptStatus.RUNNING, ModelAttemptStatus.FAILED])
def test_unknown_running_or_interrupted_usage_keeps_reservation_conservative(
    tmp_path: Path, first_status: ModelAttemptStatus
) -> None:
    db_path = _database(tmp_path)
    first_running = _attempt(
        0,
        status=ModelAttemptStatus.RUNNING,
        reserved_tokens=80,
        reserved_cost_usd=Decimal("0.08"),
    )
    reserve_model_route_attempt(str(db_path), first_running, max_model_calls=8)
    if first_status is ModelAttemptStatus.FAILED:
        interrupted = first_running.model_copy(
            update={
                "status": ModelAttemptStatus.FAILED,
                "failure_code": "interrupted",
                "failure_reason": "process stopped before usage was reported",
                "ended_at": NOW + timedelta(seconds=2),
                "latency_ms": 2000,
            }
        )
        finish_model_route_attempt(str(db_path), interrupted)

    with pytest.raises(ModelAttemptBudgetError):
        reserve_model_route_attempt(
            str(db_path),
            _attempt(1, reserved_tokens=30, reserved_cost_usd=Decimal("0.03")),
            max_model_calls=8,
            max_total_tokens=100,
            max_total_cost_usd=Decimal("0.10"),
        )

    saved = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert saved.status is first_status
    assert saved.usage is None
    assert saved.reserved_tokens == 80
    assert saved.reserved_cost_usd == Decimal("0.08")


def test_running_claimed_usage_does_not_reduce_conservative_budget_exposure(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    running_with_untrusted_claim = _attempt(
        0,
        usage=ModelUsageMetadata(
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            cost_usd=Decimal("0.001"),
        ),
        reserved_tokens=80,
        reserved_cost_usd=Decimal("0.08"),
    )
    reserve_model_route_attempt(str(db_path), running_with_untrusted_claim, max_model_calls=8)

    with pytest.raises(ModelAttemptBudgetError):
        reserve_model_route_attempt(
            str(db_path),
            _attempt(1, reserved_tokens=30, reserved_cost_usd=Decimal("0.03")),
            max_model_calls=8,
            max_total_tokens=100,
            max_total_cost_usd=Decimal("0.10"),
        )

    saved = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert saved.status is ModelAttemptStatus.RUNNING
    assert saved.usage is not None and saved.usage.total_tokens == 2
    assert saved.reserved_tokens == 80
    assert saved.reserved_cost_usd == Decimal("0.08")


@pytest.mark.parametrize("ceiling", ["calls", "tokens", "cost"])
def test_concurrent_different_operations_reserve_one_winner_atomically(
    tmp_path: Path, ceiling: str
) -> None:
    db_path = _database(tmp_path)
    attempts = tuple(
        _attempt(index, reserved_tokens=60, reserved_cost_usd=Decimal("0.06")) for index in range(2)
    )
    entry = Barrier(2)

    def reserve(attempt: ModelRouteAttempt) -> BaseException | None:
        try:
            entry.wait(timeout=5)
            reserve_model_route_attempt(
                str(db_path),
                attempt,
                max_model_calls=1 if ceiling == "calls" else 8,
                max_total_tokens=100 if ceiling == "tokens" else None,
                max_total_cost_usd=Decimal("0.1") if ceiling == "cost" else None,
            )
        except BaseException as exc:
            return exc
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reserve, attempt) for attempt in attempts]
        outcomes = [future.result(timeout=10) for future in futures]
    assert outcomes.count(None) == 1
    rejected = [outcome for outcome in outcomes if outcome is not None]
    assert len(rejected) == 1 and isinstance(rejected[0], ModelAttemptBudgetError)
    saved = read_model_route_attempts(str(db_path), RUN_ID)
    assert len(saved) == 1 and saved[0] in attempts
    # Replaying the accepted reservation must not consume another budget slot.
    assert reserve_model_route_attempt(str(db_path), saved[0], max_model_calls=1) == saved[0]
    assert read_model_route_attempts(str(db_path), RUN_ID) == saved


def test_missing_completion_row_fails_without_attaching_usage(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    with pytest.raises(KeyError, match="not found"):
        finish_model_route_attempt(str(db_path), _finished(_attempt()))
    assert read_model_route_attempts(str(db_path), RUN_ID) == []


def test_migration_15_rolls_back_columns_when_recording_ledger_entry_fails(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    _downgrade_to_v14(db_path)
    with closing(_connect(db_path)) as connection:
        connection.execute(
            "CREATE TRIGGER reject_migration_15 BEFORE INSERT ON schema_migrations "
            "WHEN NEW.version = 15 BEGIN SELECT RAISE(ABORT, 'injected ledger failure'); END"
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected ledger failure"):
            store_schema._apply_complete_usage_migration(connection)

    with closing(_connect(db_path)) as connection:
        column_names = {
            row["name"] for row in connection.execute("PRAGMA table_info(model_route_attempts)")
        }
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    assert "cache_write_tokens" not in column_names
    assert "usage_cost_basis" not in column_names
    assert 15 not in versions


def test_migration_15_upgrade_keeps_legacy_usage_unknown_and_verified_backup(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    original_attempt = _attempt()
    reserve_model_route_attempt(str(db_path), original_attempt, max_model_calls=8)
    legacy_usage = ModelUsageMetadata(
        input_tokens=40,
        output_tokens=10,
        total_tokens=50,
        cost_usd=Decimal("0.025"),
    )
    finish_model_route_attempt(str(db_path), _finished(original_attempt, usage=legacy_usage))
    _downgrade_to_v14(db_path)
    backup_policy = BackupPolicy(directory=tmp_path / "backups")

    init_db(str(db_path), backup_policy=backup_policy)

    restored = read_model_route_attempts(str(db_path), RUN_ID)[0]
    assert restored.usage == legacy_usage
    assert restored.usage.cache_write_tokens is None
    assert restored.usage.usage_cost_basis is None
    backups = list_backups(db_path, policy=backup_policy)
    assert len(backups) == 1
    assert backups[0].schema_version == 14
    with closing(_connect(backups[0].path)) as connection:
        backup_versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        }
        backup_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(model_route_attempts)")
        }
        assert 14 in backup_versions and 15 not in backup_versions
        assert "cache_write_tokens" not in backup_columns
        assert "usage_cost_basis" not in backup_columns


def test_failed_usage_upgrade_retains_verified_source_backup_and_retries(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    _downgrade_to_v14(db_path)
    policy = BackupPolicy(directory=tmp_path / "backups")
    with closing(_connect(db_path)) as connection:
        connection.execute(
            "CREATE TRIGGER reject_usage_upgrade BEFORE INSERT ON schema_migrations "
            "WHEN NEW.version=15 BEGIN SELECT RAISE(ABORT, 'injected usage failure'); END"
        )
    before = db_path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="injected usage failure") as caught:
        init_db(str(db_path), backup_policy=policy)
    assert "Verified recovery backup retained" in str(caught.value)
    assert db_path.read_bytes() == before
    backups = list_backups(db_path, policy=policy)
    assert len(backups) == 1 and backups[0].schema_version == 14
    with closing(_connect(db_path)) as connection:
        assert connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 14
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(model_route_attempts)")
        }
        assert not {"cache_write_tokens", "usage_cost_basis"} & columns
        connection.execute("DROP TRIGGER reject_usage_upgrade")
    init_db(str(db_path), backup_policy=policy)
    assert list_backups(db_path, policy=policy)
