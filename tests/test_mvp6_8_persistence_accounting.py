from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    RunManifest,
    RunStatus,
    Stage,
)
from money import parse_canonical_usd
from orchestrator import summarize_model_usage
from providers.openrouter import _usage as parse_openrouter_usage
from providers.pricing import DEFAULT_PRICE_CAPS
from store import (
    CURRENT_SCHEMA_VERSION,
    ModelAttemptBudgetError,
    finish_model_route_attempt,
    init_db,
    insert_run,
    read_model_route_attempts,
    reserve_model_route_attempt,
)

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _manifest(run_id: UUID) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_claim="MVP-6.8 exact-accounting regression",
        current_stage=Stage.CLAIM_PLANNER,
        created_at=NOW,
        updated_at=NOW,
    )


def _attempt(
    run_id: UUID,
    index: int,
    *,
    reserved_cost_usd: Decimal,
    usage_cost_usd: Decimal | None = None,
) -> ModelRouteAttempt:
    started_at = NOW + timedelta(seconds=index)
    status = ModelAttemptStatus.RUNNING if usage_cost_usd is None else ModelAttemptStatus.COMPLETED
    return ModelRouteAttempt(
        run_id=run_id,
        operation_id=UUID(int=1000 + index),
        attempt_id=UUID(int=2000 + index),
        stage="planner",
        output_type="PlannerOutput",
        model_alias="mimo-v2.5-pro",
        route_index=0,
        attempt_number=1,
        input_artifact_ids=(UUID(int=3000 + index),),
        status=status,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=1) if usage_cost_usd is not None else None,
        latency_ms=1000 if usage_cost_usd is not None else None,
        reserved_tokens=100,
        reserved_cost_usd=reserved_cost_usd,
        usage=(
            ModelUsageMetadata(total_tokens=10, cost_usd=usage_cost_usd)
            if usage_cost_usd is not None
            else None
        ),
        output_json="{}" if usage_cost_usd is not None else None,
    )


def _fixture_database(tmp_path: Path) -> Path:
    from orchestrator import run_fixture_pipeline

    fixture = Path(__file__).parent / "fixtures" / "basic_valid_run"
    result = run_fixture_pipeline(fixture, output_dir=tmp_path / "fixture-output")
    return Path(result.db_path)


@pytest.mark.parametrize(
    ("table", "operation", "expected_error"),
    [
        (
            "snapshots",
            "UPDATE snapshots SET normalized_text = 'tampered'",
            "snapshots rows are immutable",
        ),
        ("snapshots", "DELETE FROM snapshots", "snapshots rows are immutable"),
        (
            "ledger_records",
            "UPDATE ledger_records SET approved_factual_statement = 'tampered'",
            "ledger_records rows are immutable",
        ),
        ("ledger_records", "DELETE FROM ledger_records", "ledger_records rows are immutable"),
    ],
)
def test_sqlite_rejects_direct_mutation_of_immutable_audit_rows(
    tmp_path: Path,
    table: str,
    operation: str,
    expected_error: str,
) -> None:
    db_path = _fixture_database(tmp_path)
    with sqlite3.connect(db_path) as connection:
        before = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match=expected_error):
            connection.execute(operation)
        after = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert before > 0
    assert after == before


def test_fresh_database_installs_mvp6_8_schema_and_repeated_init_is_idempotent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "fresh.sqlite3"
    init_db(str(db_path))
    init_db(str(db_path))
    with sqlite3.connect(db_path) as connection:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        trigger_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
        }
        columns = {row[1] for row in connection.execute("PRAGMA table_info(model_route_attempts)")}
    assert CURRENT_SCHEMA_VERSION == 7
    assert versions == [(1,), (2,), (3,), (4,), (5,), (6,), (7,)]
    assert {
        "snapshots_immutable_update",
        "snapshots_immutable_delete",
        "ledger_records_immutable_update",
        "ledger_records_immutable_delete",
    } <= trigger_names
    assert {"reserved_cost_usd_exact", "cost_usd_exact"} <= columns


def test_exact_cost_round_trip_preserves_more_than_binary_float_precision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "exact.sqlite3"
    run_id = uuid4()
    exact = Decimal("0.123456789012345678901234567890123456789")
    init_db(str(db_path))
    insert_run(str(db_path), _manifest(run_id))
    running = _attempt(run_id, 1, reserved_cost_usd=exact)
    reserve_model_route_attempt(
        str(db_path), running, max_model_calls=2, max_total_cost_usd=Decimal("1")
    )
    finished = running.model_copy(
        update={
            "status": ModelAttemptStatus.COMPLETED,
            "ended_at": running.started_at + timedelta(seconds=1),
            "latency_ms": 1000,
            "usage": ModelUsageMetadata(total_tokens=10, cost_usd=exact),
            "output_json": "{}",
        }
    )
    finish_model_route_attempt(str(db_path), finished)

    restored = read_model_route_attempts(str(db_path), run_id)[0]
    assert restored.reserved_cost_usd == exact
    assert restored.usage is not None
    assert restored.usage.cost_usd == exact
    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT reserved_cost_usd_exact, cost_usd_exact FROM model_route_attempts"
        ).fetchone()
    assert stored == (str(exact), str(exact))


@pytest.mark.parametrize(
    ("reservation", "allowed"),
    [
        (Decimal("0.999999999999999999999999999999999999999"), True),
        (Decimal("1.000000000000000000000000000000000000000"), True),
        (Decimal("1.000000000000000000000000000000000000001"), False),
    ],
)
def test_exact_ceiling_boundaries(
    tmp_path: Path,
    reservation: Decimal,
    allowed: bool,
) -> None:
    db_path = tmp_path / f"boundary-{allowed}-{str(reservation)[-3:]}.sqlite3"
    run_id = uuid4()
    init_db(str(db_path))
    insert_run(str(db_path), _manifest(run_id))
    if allowed:
        reserve_model_route_attempt(
            str(db_path),
            _attempt(run_id, 1, reserved_cost_usd=reservation),
            max_model_calls=2,
            max_total_cost_usd=Decimal("1"),
        )
    else:
        with pytest.raises(ModelAttemptBudgetError, match="cannot reserve the next call"):
            reserve_model_route_attempt(
                str(db_path),
                _attempt(run_id, 1, reserved_cost_usd=reservation),
                max_model_calls=2,
                max_total_cost_usd=Decimal("1"),
            )


def test_exact_sum_of_valid_calls_and_reservations_cannot_cross_ceiling(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sum.sqlite3"
    run_id = uuid4()
    init_db(str(db_path))
    insert_run(str(db_path), _manifest(run_id))
    first = _attempt(run_id, 1, reserved_cost_usd=Decimal("0.5000000000000000000001"))
    reserve_model_route_attempt(
        str(db_path), first, max_model_calls=3, max_total_cost_usd=Decimal("1")
    )
    with pytest.raises(ModelAttemptBudgetError, match="cannot reserve the next call"):
        reserve_model_route_attempt(
            str(db_path),
            _attempt(run_id, 2, reserved_cost_usd=Decimal("0.49999999999999999999995")),
            max_model_calls=3,
            max_total_cost_usd=Decimal("1"),
        )


def test_usage_summary_keeps_exact_decimal_subtotals_and_unknown_reservations() -> None:
    run_id = uuid4()
    complete = _attempt(
        run_id,
        1,
        reserved_cost_usd=Decimal("0.2"),
        usage_cost_usd=Decimal("0.100000000000000000000000000000000000001"),
    )
    incomplete = _attempt(run_id, 2, reserved_cost_usd=Decimal("0.3"))
    accounting = summarize_model_usage((complete, incomplete))
    assert accounting.exact_total_cost_usd is None
    assert accounting.known_cost_subtotal_usd == Decimal(
        "0.100000000000000000000000000000000000001"
    )
    assert accounting.conservative_reserved_cost_usd == Decimal(
        "0.400000000000000000000000000000000000001"
    )


def test_zero_cost_usage_is_complete_exact_zero() -> None:
    run_id = uuid4()
    attempt = _attempt(
        run_id,
        1,
        reserved_cost_usd=Decimal("0.1"),
        usage_cost_usd=Decimal("0"),
    )
    accounting = summarize_model_usage((attempt,))
    assert accounting.cost_complete is True
    assert accounting.exact_total_cost_usd == Decimal("0")
    assert accounting.conservative_reserved_cost_usd == Decimal("0")


def test_resumed_budget_uses_exact_completed_usage_plus_next_reservation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "resume-exposure.sqlite3"
    run_id = uuid4()
    init_db(str(db_path))
    insert_run(str(db_path), _manifest(run_id))
    first = _attempt(run_id, 1, reserved_cost_usd=Decimal("0.9"))
    reserve_model_route_attempt(
        str(db_path), first, max_model_calls=3, max_total_cost_usd=Decimal("1")
    )
    finished = first.model_copy(
        update={
            "status": ModelAttemptStatus.COMPLETED,
            "ended_at": first.started_at + timedelta(seconds=1),
            "latency_ms": 1000,
            "usage": ModelUsageMetadata(
                total_tokens=10,
                cost_usd=Decimal("0.600000000000000000000000000000000000001"),
            ),
            "output_json": "{}",
        }
    )
    finish_model_route_attempt(str(db_path), finished)

    with pytest.raises(ModelAttemptBudgetError, match="cannot reserve the next call"):
        reserve_model_route_attempt(
            str(db_path),
            _attempt(
                run_id,
                2,
                reserved_cost_usd=Decimal("0.3999999999999999999999999999999999999999"),
            ),
            max_model_calls=3,
            max_total_cost_usd=Decimal("1"),
        )


def test_historical_real_cost_is_migrated_without_inventing_precision(tmp_path: Path) -> None:
    db_path = tmp_path / "historical.sqlite3"
    run_id = uuid4()
    init_db(str(db_path))
    insert_run(str(db_path), _manifest(run_id))
    attempt = _attempt(run_id, 1, reserved_cost_usd=Decimal("0.1"))
    reserve_model_route_attempt(str(db_path), attempt, max_model_calls=2)
    finished = attempt.model_copy(
        update={
            "status": ModelAttemptStatus.COMPLETED,
            "ended_at": attempt.started_at + timedelta(seconds=1),
            "latency_ms": 1000,
            "usage": ModelUsageMetadata(total_tokens=10, cost_usd=Decimal("0.2")),
            "output_json": "{}",
        }
    )
    finish_model_route_attempt(str(db_path), finished)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = 6")
        for trigger in (
            "snapshots_immutable_update",
            "snapshots_immutable_delete",
            "ledger_records_immutable_update",
            "ledger_records_immutable_delete",
        ):
            connection.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
        connection.execute(
            "UPDATE model_route_attempts SET reserved_cost_usd = 0.1, cost_usd = 0.2"
        )
        connection.execute("ALTER TABLE model_route_attempts DROP COLUMN cost_usd_exact")
        connection.execute("ALTER TABLE model_route_attempts DROP COLUMN reserved_cost_usd_exact")
        connection.commit()

    init_db(str(db_path))
    restored = read_model_route_attempts(str(db_path), run_id)[0]
    assert restored.reserved_cost_usd == Decimal("0.1")
    assert restored.usage is not None
    assert restored.usage.cost_usd == Decimal("0.2")
    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT reserved_cost_usd_exact, cost_usd_exact FROM model_route_attempts"
        ).fetchone()
    assert stored == ("0.1", "0.2")


def test_mvp6_8_migration_failure_rolls_back_record_and_partial_triggers(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "failed-migration.sqlite3"
    init_db(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = 6")
        for trigger in (
            "snapshots_immutable_update",
            "snapshots_immutable_delete",
            "ledger_records_immutable_update",
            "ledger_records_immutable_delete",
        ):
            connection.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
        connection.execute(
            """CREATE TRIGGER snapshots_immutable_update
               BEFORE UPDATE ON snapshots BEGIN SELECT 1; END"""
        )
        connection.commit()

    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(db_path))

    with sqlite3.connect(db_path) as connection:
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        installed = {
            row[0]
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type = 'trigger' AND name LIKE '%_immutable_%'"""
            )
        }
    assert 6 not in versions
    assert installed == {"snapshots_immutable_update"}


@pytest.mark.parametrize("value", ["-0.1", "-0", "NaN", "Infinity", "-Infinity"])
def test_invalid_monetary_values_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        ModelUsageMetadata(cost_usd=value)


@pytest.mark.parametrize("value", ["1.00", "01", "1e-3", ".5", "+1"])
def test_noncanonical_persisted_monetary_text_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="canonical decimal text"):
        parse_canonical_usd(value)


def test_provider_decimal_string_keeps_its_long_fraction() -> None:
    exact = Decimal("0.00000000000000000012345678901234567890123456789")
    usage, estimated = parse_openrouter_usage(
        {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "cost": str(exact),
        },
        DEFAULT_PRICE_CAPS["xiaomi/mimo-v2.5-pro"],
    )
    assert estimated is False
    assert usage.cost_usd == exact
