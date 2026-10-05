from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from researchassistant.contracts.models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    RunManifest,
    RunStatus,
    Stage,
)
from researchassistant.storage.store import (
    init_db,
    insert_run,
    open_read_only_store,
    read_model_route_attempts,
    reserve_model_route_attempt,
)

_ROOT = Path(__file__).resolve().parents[1]
_DESKTOP = str(_ROOT / "desktop")
_RUN_ID = UUID(int=9001)
_OPERATION_ID = UUID(int=9002)
_ATTEMPT_ID = UUID(int=9003)
_INPUT_ID = UUID(int=9004)
_NOW = datetime(2026, 10, 4, tzinfo=UTC)
sys.path.insert(0, _DESKTOP)
try:
    _SPEC = importlib.util.spec_from_file_location(
        "upgrade_smoke", _ROOT / "desktop" / "upgrade-smoke.py"
    )
    if _SPEC is None or _SPEC.loader is None:
        raise ImportError("could not load desktop upgrade smoke module")
    upgrade_smoke = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(upgrade_smoke)
finally:
    sys.path.remove(_DESKTOP)


def _generated_database(path: Path) -> None:
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=_RUN_ID,
            status=RunStatus.RUNNING,
            raw_claim="Disposable schema-13 upgrade fixture",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    reserve_model_route_attempt(
        str(path),
        ModelRouteAttempt(
            run_id=_RUN_ID,
            operation_id=_OPERATION_ID,
            attempt_id=_ATTEMPT_ID,
            stage="planner",
            output_type="FixtureOutput",
            model_alias="fixture-model",
            pinned_model_snapshot="fixture-model-2026-10-04",
            route_index=0,
            attempt_number=1,
            input_artifact_ids=(_INPUT_ID,),
            status=ModelAttemptStatus.RUNNING,
            started_at=_NOW,
            reserved_tokens=11,
            reserved_cost_usd=Decimal("0.01"),
        ),
        max_model_calls=5,
    )


def _downgrade_generated_database(path: Path, version: int) -> None:
    with sqlite3.connect(path) as connection:
        if version < 16:
            for table in upgrade_smoke._SCHEMA13_PROVENANCE_GUARD_TABLES:
                connection.execute(f"DROP TRIGGER {table}_provenance_immutable_update")
        if version < 17:
            for index in upgrade_smoke._SCHEMA17_INDEXES:
                connection.execute(f"DROP INDEX {index}")
        if version == 14:
            for name in ("cache_write_tokens", "usage_cost_basis"):
                connection.execute(f"ALTER TABLE model_route_attempts DROP COLUMN {name}")
        connection.execute("DELETE FROM schema_migrations WHERE version > ?", (version,))
        connection.commit()


def _schema_state(path: Path) -> tuple[list[tuple[int, str]], set[str], set[str]]:
    with sqlite3.connect(path) as connection:
        migrations = connection.execute(
            "SELECT version, description FROM schema_migrations ORDER BY version"
        ).fetchall()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(model_route_attempts)")}
        triggers = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
    return migrations, columns, triggers


@pytest.mark.parametrize("version", [14, 15, 16])
def test_generated_schema_14_and_16_convert_to_schema13_without_losing_prior_data(
    tmp_path: Path,
    version: int,
) -> None:
    database = tmp_path / f"schema-{version}.sqlite3"
    _generated_database(database)
    if version < 16:
        _downgrade_generated_database(database, version)

    upgrade_smoke._prepare_schema13_fixture(database)

    migrations, columns, triggers = _schema_state(database)
    assert [row[0] for row in migrations] == list(range(1, 14))
    assert not set(upgrade_smoke._SCHEMA13_USAGE_COLUMNS) & columns
    assert not any(name.endswith("_provenance_immutable_update") for name in triggers)
    assert "retrieval_attempt_same_run" in triggers
    with open_read_only_store(database) as store:
        assert store.compatibility.schema_version == 13
        attempts = read_model_route_attempts(store.connection, _RUN_ID)
    assert attempts == [
        ModelRouteAttempt(
            run_id=_RUN_ID,
            operation_id=_OPERATION_ID,
            attempt_id=_ATTEMPT_ID,
            stage="planner",
            output_type="FixtureOutput",
            model_alias="fixture-model",
            pinned_model_snapshot="fixture-model-2026-10-04",
            route_index=0,
            attempt_number=1,
            input_artifact_ids=(_INPUT_ID,),
            status=ModelAttemptStatus.RUNNING,
            started_at=_NOW,
            reserved_tokens=11,
            reserved_cost_usd=Decimal("0.01"),
        )
    ]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT run_id FROM runs").fetchone() == (str(_RUN_ID),)


@pytest.mark.parametrize(
    "column,value",
    [
        ("cached_input_tokens", 0),
        ("uncached_input_tokens", 0),
        ("cache_write_tokens", 0),
        ("usage_cost_basis", "configured_price_cap"),
    ],
)
def test_populated_usage_refuses_conversion_without_mutation(
    tmp_path: Path,
    column: str,
    value: int | str,
) -> None:
    database = tmp_path / "populated.sqlite3"
    _generated_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"UPDATE model_route_attempts SET {column} = ? WHERE attempt_id = ?",
            (value, str(_ATTEMPT_ID)),
        )
        connection.commit()
    before = _schema_state(database)

    with pytest.raises(ValueError, match="Cannot discard recorded cache usage"):
        upgrade_smoke._prepare_schema13_fixture(database)

    assert _schema_state(database) == before


def test_unknown_or_incomplete_schema_refuses_conversion_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "unknown.sqlite3"
    _generated_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO schema_migrations VALUES (18, 'unknown', '2026-10-04T00:00:00Z')"
        )
        connection.commit()
    before = _schema_state(database)

    with pytest.raises(ValueError, match="complete recognized schema"):
        upgrade_smoke._prepare_schema13_fixture(database)

    assert _schema_state(database) == before


def test_conversion_rolls_back_all_ddl_and_ledger_changes_on_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "rollback.sqlite3"
    _generated_database(database)
    before = _schema_state(database)
    original = upgrade_smoke._remove_post_schema13_objects

    def remove_then_interrupt(conn: sqlite3.Connection, version: int) -> None:
        original(conn, version)
        raise RuntimeError("injected fixture conversion failure")

    monkeypatch.setattr(upgrade_smoke, "_remove_post_schema13_objects", remove_then_interrupt)

    with pytest.raises(RuntimeError, match="injected fixture conversion failure"):
        upgrade_smoke._prepare_schema13_fixture(database)

    assert _schema_state(database) == before
