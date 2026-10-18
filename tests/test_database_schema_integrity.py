"""Regression coverage for safe schema upgrades and inspection validation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from researchassistant.storage import store_schema
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    init_db,
    open_read_only_store,
)
from researchassistant.storage.store_schema import CURRENT_SCHEMA_VERSION


def _connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_writable_future_schema_is_rejected_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    init_db(str(path))
    with _connection(path) as conn:
        conn.execute(
            "INSERT INTO schema_migrations VALUES (?, 'future', '2026-09-27')",
            (CURRENT_SCHEMA_VERSION + 1,),
        )
        conn.execute(
            "UPDATE schema_migrations SET description = 'future meaning' WHERE version = 4"
        )
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError, match="newer"):
        init_db(str(path))
    assert path.read_bytes() == before


def test_foreign_key_corruption_is_rejected_read_only(tmp_path: Path) -> None:
    path = tmp_path / "orphan.db"
    init_db(str(path))
    with _connection(path) as conn:
        conn.execute(
            "INSERT INTO run_cancellations VALUES (?, '2026-09-27', 'orphan')", (str(uuid4()),)
        )
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    before = path.read_bytes()
    with pytest.raises(DatabaseCompatibilityError, match="foreign.key"):
        open_read_only_store(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "name",
    ["runs_raw_claim_immutable", "snapshots_immutable_update", "v2_artifacts_immutable_update"],
)
def test_disabled_trigger_is_rejected_without_mutation(tmp_path: Path, name: str) -> None:
    path = tmp_path / "trigger.db"
    init_db(str(path))
    with _connection(path) as conn:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()[0]
        conn.execute(f'DROP TRIGGER "{name}"')
        if "WHEN NEW.raw_claim IS NOT OLD.raw_claim" in sql:
            sql = sql.replace(
                "WHEN NEW.raw_claim IS NOT OLD.raw_claim",
                "WHEN NEW.raw_claim IS NOT OLD.raw_claim AND 0",
            )
        else:
            sql = sql.replace("BEGIN", "WHEN 0 BEGIN")
        conn.execute(sql)
    before = path.read_bytes()
    with pytest.raises(DatabaseCompatibilityError):
        open_read_only_store(path)
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "declaration",
    [
        "run_id TEXT",
        "run_id TEXT, ledger_claim_id TEXT, source_family_id TEXT, payload_json TEXT",
        "run_id TEXT NOT NULL, ledger_claim_id TEXT NOT NULL, source_family_id TEXT NOT NULL, "
        "payload_json TEXT NOT NULL, PRIMARY KEY (run_id, ledger_claim_id)",
    ],
)
def test_malformed_existing_table_is_rejected_before_migration(
    tmp_path: Path, declaration: str
) -> None:
    path = tmp_path / "shape.db"
    init_db(str(path))
    with _connection(path) as conn:
        conn.execute("DROP TABLE portfolio_items")
        conn.execute(f"CREATE TABLE portfolio_items ({declaration})")
    before = path.read_bytes()
    with pytest.raises(DatabaseCompatibilityError):
        open_read_only_store(path)
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))
    assert path.read_bytes() == before


def test_malformed_future_table_does_not_record_its_migration(tmp_path: Path) -> None:
    path = tmp_path / "partial.db"
    init_db(str(path))
    with _connection(path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version >= 8")
        conn.execute("DROP TABLE portfolio_items")
        conn.execute("CREATE TABLE portfolio_items (run_id TEXT)")
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))
    assert path.read_bytes() == before


def test_cache_migration_preserves_old_unknowns_and_rolls_back_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "upgrade.db"
    init_db(str(path))
    assert CURRENT_SCHEMA_VERSION == 18
    with _connection(path) as conn:
        _restore_round_three_constraint(conn)
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            if store_schema._object_version("trigger", row["name"]) > 13:
                conn.execute(f'DROP TRIGGER "{row["name"]}"')
        conn.execute("DELETE FROM schema_migrations WHERE version >= 14")
        conn.execute("ALTER TABLE model_route_attempts DROP COLUMN cached_input_tokens")
        conn.execute("ALTER TABLE model_route_attempts DROP COLUMN uncached_input_tokens")
        conn.execute("ALTER TABLE model_route_attempts DROP COLUMN cache_write_tokens")
        conn.execute("ALTER TABLE model_route_attempts DROP COLUMN usage_cost_basis")
        conn.execute(
            "CREATE TRIGGER reject_upgrade BEFORE INSERT ON schema_migrations "
            "WHEN NEW.version = 14 BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == 13
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        init_db(str(path))
    with _connection(path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(model_route_attempts)")}
        assert "cached_input_tokens" not in columns
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 13
        conn.execute("DROP TRIGGER reject_upgrade")
    init_db(str(path))
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == CURRENT_SCHEMA_VERSION


@pytest.mark.parametrize("version", range(7, CURRENT_SCHEMA_VERSION + 1))
def test_supported_historical_schema_reads_unchanged_and_upgrades(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / "historical.db"
    init_db(str(path))
    with _connection(path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        if 13 <= version < 18:
            _restore_round_three_constraint(conn)
        for kind, name, _sql in reversed(store_schema._canonical_schema()):
            if store_schema._object_version(kind, name) > version and kind in {"trigger", "index"}:
                conn.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')
        for kind, name, _sql in reversed(store_schema._canonical_schema()):
            if kind == "table" and store_schema._object_version(kind, name) > version:
                conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        for table in ("model_route_attempts", "snapshots", "search_queries"):
            columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            for column in columns:
                if store_schema._column_version(table, column["name"]) > version:
                    conn.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column["name"]}"')
        conn.execute("DELETE FROM schema_migrations WHERE version > ?", (version,))
    before = path.read_bytes()
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == version
    assert path.read_bytes() == before
    init_db(str(path))
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == CURRENT_SCHEMA_VERSION


def _restore_round_three_constraint(conn: sqlite3.Connection) -> None:
    """Construct the actual historical table, rather than only relabeling its ledger."""
    triggers = [
        row[0]
        for row in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='v2_ledger_admissions'"
        )
    ]
    definition = next(
        sql
        for kind, name, sql in store_schema._canonical_boundaries()[13]
        if kind == "table" and name == "v2_ledger_admissions"
    )
    rows = [tuple(row) for row in conn.execute("SELECT * FROM v2_ledger_admissions")]
    conn.execute("DROP TABLE v2_ledger_admissions")
    conn.execute(definition)
    conn.executemany(
        "INSERT INTO v2_ledger_admissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    for trigger in triggers:
        conn.execute(trigger)


def test_round_four_migration_preserves_rows_and_rolls_back_atomically(tmp_path: Path) -> None:
    from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run

    database, _admitted = _run(tmp_path, Phase10Provider([_approved()]))
    path = Path(database)
    with _connection(path) as conn:
        original = [tuple(row) for row in conn.execute("SELECT * FROM v2_ledger_admissions")]
        assert original
        _restore_round_three_constraint(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version=18")
        conn.execute("CREATE INDEX custom_admission_run ON v2_ledger_admissions(run_id)")
        conn.execute(
            "CREATE TRIGGER reject_round_four BEFORE INSERT ON schema_migrations "
            "WHEN NEW.version=18 BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    before = path.read_bytes()
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == 17
    assert path.read_bytes() == before
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        init_db(str(path))
    with _connection(path) as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 17
        assert (
            "BETWEEN 1 AND 3"
            in conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='v2_ledger_admissions'"
            ).fetchone()[0]
        )
        assert [
            tuple(row) for row in conn.execute("SELECT * FROM v2_ledger_admissions")
        ] == original
        conn.execute("DROP TRIGGER reject_round_four")
    init_db(str(path))
    with _connection(path) as conn:
        assert [
            tuple(row) for row in conn.execute("SELECT * FROM v2_ledger_admissions")
        ] == original
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='custom_admission_run'"
        ).fetchone()
        changed = list(original[0])
        changed[0] = str(uuid4())
        changed[2] = str(uuid4())
        changed[4] = 4
        conn.execute(
            "INSERT INTO v2_ledger_admissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", changed
        )
        changed[0] = str(uuid4())
        changed[2] = str(uuid4())
        changed[4] = 5
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(
                "INSERT INTO v2_ledger_admissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", changed
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM v2_ledger_admissions")


@pytest.mark.parametrize("fragment", ["NOT NULL", "PRIMARY KEY (run_id, ledger_claim_id)"])
def test_required_table_constraints_are_validated(tmp_path: Path, fragment: str) -> None:
    path = tmp_path / "constraint.db"
    init_db(str(path))
    with _connection(path) as conn:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='portfolio_items'").fetchone()[
            0
        ]
        sql = (
            sql.replace(",\n                " + fragment, "")
            if fragment.startswith("PRIMARY")
            else sql.replace(fragment, "", 1)
        )
        conn.execute("DROP TABLE portfolio_items")
        conn.execute(sql)
    with pytest.raises(DatabaseCompatibilityError):
        open_read_only_store(path)


def test_unexpected_table_constraint_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra-constraint.db"
    init_db(str(path))
    with _connection(path) as conn:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='portfolio_items'").fetchone()[
            0
        ]
        conn.execute("DROP TABLE portfolio_items")
        conn.execute(sql.rsplit(")", 1)[0] + ", CHECK (0))")
    before = path.read_bytes()
    with pytest.raises(DatabaseCompatibilityError):
        open_read_only_store(path)
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))
    assert path.read_bytes() == before


def test_malformed_migration_versions_are_a_typed_compatibility_error(tmp_path: Path) -> None:
    path = tmp_path / "bad-version.db"
    init_db(str(path))
    with _connection(path) as conn:
        conn.execute("DROP TABLE schema_migrations")
        conn.execute(
            "CREATE TABLE schema_migrations(version TEXT, description TEXT, applied_at TEXT)"
        )
        conn.execute("INSERT INTO schema_migrations VALUES ('bad', 'x', 'today')")
    with pytest.raises(DatabaseCompatibilityError, match="migration versions are invalid"):
        open_read_only_store(path)
