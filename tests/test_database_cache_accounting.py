from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from researchassistant.contracts.models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    RunManifest,
    RunStatus,
    Stage,
)
from researchassistant.storage.store import (
    finish_model_route_attempt,
    init_db,
    insert_run,
    open_read_only_store,
    read_model_route_attempts,
    reserve_model_route_attempt,
)

NOW = datetime(2026, 9, 27, tzinfo=UTC)


def _manifest(run_id: UUID) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_claim="Cache accounting persistence regression",
        current_stage=Stage.CLAIM_PLANNER,
        created_at=NOW,
        updated_at=NOW,
    )


def _attempt(run_id: UUID) -> ModelRouteAttempt:
    return ModelRouteAttempt(
        run_id=run_id,
        operation_id=UUID(int=1001),
        attempt_id=UUID(int=2001),
        stage="planner",
        output_type="PlannerOutput",
        model_alias="mimo-v2.6-pro",
        route_index=0,
        attempt_number=1,
        input_artifact_ids=(UUID(int=3001),),
        status=ModelAttemptStatus.RUNNING,
        started_at=NOW,
        reserved_tokens=100,
        reserved_cost_usd=Decimal("0.1"),
    )


def _finished(attempt: ModelRouteAttempt) -> ModelRouteAttempt:
    return attempt.model_copy(
        update={
            "status": ModelAttemptStatus.COMPLETED,
            "ended_at": attempt.started_at + timedelta(seconds=1),
            "latency_ms": 1000,
            "usage": ModelUsageMetadata(
                input_tokens=1000,
                cached_input_tokens=800,
                uncached_input_tokens=200,
                output_tokens=75,
                total_tokens=1075,
                cost_usd=Decimal("0.01234567890123456789"),
            ),
            "output_json": "{}",
        }
    )


def _database(tmp_path: Path) -> tuple[Path, UUID, ModelRouteAttempt]:
    db_path = tmp_path / "cache-accounting.sqlite3"
    run_id = UUID(int=42)
    init_db(str(db_path))
    insert_run(str(db_path), _manifest(run_id))
    attempt = _attempt(run_id)
    reserve_model_route_attempt(str(db_path), attempt, max_model_calls=2)
    return db_path, run_id, attempt


def test_cache_tokens_round_trip_when_finishing_reserved_attempt(tmp_path: Path) -> None:
    db_path, run_id, attempt = _database(tmp_path)
    finished = _finished(attempt)

    finish_model_route_attempt(str(db_path), finished)

    restored = read_model_route_attempts(str(db_path), run_id)[0]
    assert restored.usage == finished.usage
    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT cached_input_tokens, uncached_input_tokens "
            "FROM model_route_attempts WHERE attempt_id = ?",
            (str(attempt.attempt_id),),
        ).fetchone()
    assert stored == (800, 200)


def test_historical_attempt_without_cache_columns_reads_unknown_values(tmp_path: Path) -> None:
    db_path, run_id, attempt = _database(tmp_path)
    finish_model_route_attempt(str(db_path), _finished(attempt))
    with sqlite3.connect(db_path) as connection:
        connection.execute("ALTER TABLE model_route_attempts DROP COLUMN cached_input_tokens")
        connection.execute("ALTER TABLE model_route_attempts DROP COLUMN uncached_input_tokens")
        connection.execute("DELETE FROM schema_migrations WHERE version = 14")
        connection.execute("PRAGMA user_version = 13")
        connection.commit()

    before = db_path.read_bytes()
    with open_read_only_store(db_path) as reader:
        restored = read_model_route_attempts(reader.connection, run_id)[0]
        assert reader.compatibility.schema_version == 13
    assert db_path.read_bytes() == before
    assert restored.usage is not None
    assert restored.usage.cached_input_tokens is None
    assert restored.usage.uncached_input_tokens is None
    assert restored.usage.input_tokens == 1000
    init_db(str(db_path))
    upgraded = read_model_route_attempts(str(db_path), run_id)[0]
    assert upgraded == restored


def test_repeated_identical_finish_is_idempotent_and_conflict_is_rejected(
    tmp_path: Path,
) -> None:
    db_path, run_id, attempt = _database(tmp_path)
    finished = _finished(attempt)

    finish_model_route_attempt(str(db_path), finished)
    finish_model_route_attempt(str(db_path), finished)
    changed = finished.model_copy(
        update={
            "usage": finished.usage.model_copy(
                update={"cached_input_tokens": 700, "uncached_input_tokens": 300}
            ),
        }
    )
    with pytest.raises(sqlite3.IntegrityError, match="already finished differently"):
        finish_model_route_attempt(str(db_path), changed)

    restored = read_model_route_attempts(str(db_path), run_id)[0]
    assert restored == finished
