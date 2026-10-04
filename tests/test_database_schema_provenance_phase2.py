"""Regression tests for strict schema preflight and update-safe provenance."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from researchassistant.storage import store_schema
from researchassistant.storage.database_recovery import BackupPolicy, list_backups
from researchassistant.storage.history_import import import_history
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    DatabaseCompatibilityIssue,
    init_db,
    open_read_only_store,
)
from researchassistant.storage.store_schema import CURRENT_SCHEMA_VERSION


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("table", "model_invocations"),
        ("index", "model_route_attempts_run_operation"),
        ("trigger", "retrieval_attempt_same_run"),
    ],
)
def test_missing_committed_object_is_rejected_without_writable_repair(
    tmp_path: Path, kind: str, name: str
) -> None:
    path = tmp_path / f"missing-{name}.sqlite3"
    init_db(str(path))
    with _connect(path) as connection:
        connection.execute(f'DROP {kind.upper()} "{name}"')
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError):
        open_read_only_store(path)
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))

    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_changed_committed_migration_description_is_not_normalized(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / f"description-{version}.sqlite3"
    init_db(str(path))
    with _connect(path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET description = 'incorrect meaning' WHERE version = ?",
            (version,),
        )
    before = path.read_bytes()

    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))

    assert path.read_bytes() == before


@pytest.mark.parametrize("damage", ["gap", "future"])
def test_invalid_migration_ledger_is_rejected_before_any_write(tmp_path: Path, damage: str) -> None:
    path = tmp_path / f"{damage}.sqlite3"
    init_db(str(path))
    with _connect(path) as connection:
        if damage == "gap":
            connection.execute("DELETE FROM schema_migrations WHERE version = 4")
        else:
            connection.execute(
                "INSERT INTO schema_migrations(version, description, applied_at) "
                "VALUES (?, 'future', '2026-10-04')",
                (CURRENT_SCHEMA_VERSION + 1,),
            )
    before = path.read_bytes()

    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))

    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 3, 6])
def test_recognized_early_schema_upgrades_to_current(tmp_path: Path, version: int) -> None:
    path = tmp_path / f"early-{version}.sqlite3"
    init_db(str(path))
    _reduce_to_recorded_version(path, version)

    init_db(str(path))

    with _connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == (
            CURRENT_SCHEMA_VERSION
        )


@pytest.mark.parametrize("version", range(7, CURRENT_SCHEMA_VERSION + 1))
def test_read_only_supported_schema_versions_remain_unmodified(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / f"read-only-{version}.sqlite3"
    init_db(str(path))
    if version < CURRENT_SCHEMA_VERSION:
        _reduce_to_recorded_version(path, version)
    before = path.read_bytes()

    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == version

    assert path.read_bytes() == before


def test_retrieval_child_provenance_updates_cannot_cross_run(tmp_path: Path) -> None:
    path = tmp_path / "child-update.sqlite3"
    _provenance_database(path)

    with _connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE retrieval_attempts SET run_id = 'run-b' WHERE retrieval_attempt_id = 'r-a'"
        )

    with _connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE retrieval_attempts SET query_id = 'q-b' WHERE retrieval_attempt_id = 'r-a'"
        )


def test_referenced_parent_ownership_cannot_move_away_from_child(tmp_path: Path) -> None:
    path = tmp_path / "parent-update.sqlite3"
    _provenance_database(path)

    with _connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE search_queries SET run_id = 'run-b' WHERE query_id = 'q-a'")


def test_semantically_inconsistent_same_run_relationship_is_rejected_on_open(
    tmp_path: Path,
) -> None:
    path = tmp_path / "semantic-corruption.sqlite3"
    _provenance_database(path)
    with _connect(path) as connection:
        # Simulate an older SQLite writer that bypassed the new ownership guard.
        trigger_rows = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('retrieval_attempts', 'search_queries')"
        ).fetchall()
        for row in trigger_rows:
            connection.execute(f'DROP TRIGGER "{row["name"]}"')
        connection.execute("UPDATE search_queries SET run_id = 'run-b' WHERE query_id = 'q-a'")
        for row in trigger_rows:
            connection.execute(row["sql"])
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError, match="provenance|ownership|same.run"):
        open_read_only_store(path)

    assert path.read_bytes() == before


@pytest.mark.parametrize("gap", [1, 2, 3, 4, 6, 8, 15])
def test_committed_ledger_gap_cannot_masquerade_as_a_pending_upgrade(
    tmp_path: Path, gap: int
) -> None:
    path = tmp_path / "committed-gap.sqlite3"
    init_db(str(path))
    with _connect(path) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version=?", (gap,))
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError, match="incomplete"):
        init_db(str(path))
    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA
    assert path.read_bytes() == before


@pytest.mark.parametrize("damage", ["noninteger", "negative", "unreadable", "empty"])
def test_malformed_or_empty_migration_records_never_bootstrap_known_database(
    tmp_path: Path, damage: str
) -> None:
    path = tmp_path / "malformed-ledger.sqlite3"
    init_db(str(path))
    with _connect(path) as connection:
        if damage == "negative":
            connection.execute("INSERT INTO schema_migrations VALUES (-1, 'bad', 'now')")
        elif damage == "empty":
            connection.execute("DELETE FROM schema_migrations")
        else:
            connection.execute("DROP TABLE schema_migrations")
            if damage == "noninteger":
                connection.execute(
                    "CREATE TABLE schema_migrations "
                    "(version TEXT, description TEXT, applied_at TEXT)"
                )
                connection.execute("INSERT INTO schema_migrations VALUES ('bad', 'bad', 'now')")
            else:
                connection.execute("CREATE TABLE schema_migrations (unrelated TEXT)")
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))
    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA
    assert path.read_bytes() == before


@pytest.mark.parametrize("vacuum", [False, True], ids=["freelist-pages", "vacuumed-header"])
def test_initialized_database_with_all_objects_dropped_is_not_reinitialized(
    tmp_path: Path,
    vacuum: bool,
) -> None:
    path = tmp_path / f"all-objects-dropped-{vacuum}.sqlite3"
    backup_dir = tmp_path / f"backups-{vacuum}"
    policy = BackupPolicy(directory=backup_dir)
    init_db(str(path))
    with _connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        objects = connection.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for kind in ("trigger", "index", "view", "table"):
            for row in objects:
                if row["type"] == kind:
                    connection.execute(f'DROP {kind.upper()} IF EXISTS "{row["name"]}"')
        if vacuum:
            connection.execute("VACUUM")

    with _connect(path) as connection:
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            == 0
        )
        if vacuum:
            assert page_count == 1
        else:
            assert page_count > 1
        # VACUUM may shrink the file to one page, but the schema cookie records
        # that this was a database with DDL, not a fresh header-only database.
        if vacuum:
            assert connection.execute("PRAGMA schema_version").fetchone()[0] > 0

    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns
    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_mtime
    assert list_backups(path, policy=policy) == []
    assert not backup_dir.exists()


@pytest.mark.parametrize("header_only", [False, True], ids=["zero-byte", "header-only"])
def test_genuinely_empty_sqlite_database_can_bootstrap(
    tmp_path: Path,
    header_only: bool,
) -> None:
    path = tmp_path / f"empty-{header_only}.sqlite3"
    if header_only:
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA user_version=0")

    if path.exists():
        with _connect(path) as connection:
            assert connection.execute("PRAGMA page_count").fetchone()[0] <= 1
            assert connection.execute("PRAGMA freelist_count").fetchone()[0] == 0
            assert connection.execute("PRAGMA schema_version").fetchone()[0] == 0
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
            assert connection.execute("PRAGMA application_id").fetchone()[0] == 0
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
                == 0
            )

    init_db(str(path))

    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == CURRENT_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("pragma", "value"),
    [("user_version", 7), ("application_id", 0x52415353)],
)
def test_empty_schema_with_nonzero_sqlite_identity_is_not_bootstrapped(
    tmp_path: Path,
    pragma: str,
    value: int,
) -> None:
    path = tmp_path / f"empty-with-{pragma}.sqlite3"
    policy = BackupPolicy(directory=tmp_path / f"backups-{pragma}")
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA {pragma}={value}")
    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_mtime
    assert list_backups(path, policy=policy) == []
    assert not policy.directory.exists()


def test_semantically_corrupt_but_fk_valid_source_is_rejected_before_import(tmp_path: Path) -> None:
    path = tmp_path / "bad-import.sqlite3"
    destination = tmp_path / "imports"
    _provenance_database(path)
    _corrupt_parent_owner_without_changing_schema(path)
    with _connect(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before = path.read_bytes()
    with pytest.raises(DatabaseCompatibilityError, match="same.run provenance") as caught:
        import_history(path, destination_dir=destination)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA
    assert path.read_bytes() == before
    assert not destination.exists()


def test_semantically_inconsistent_same_run_relationship_is_rejected_before_upgrade(
    tmp_path: Path,
) -> None:
    path = tmp_path / "semantic-upgrade-corruption.sqlite3"
    _provenance_database(path)
    _corrupt_parent_owner_without_changing_schema(path)
    before = path.read_bytes()

    with pytest.raises(sqlite3.DatabaseError, match="same.run provenance"):
        init_db(str(path))

    assert path.read_bytes() == before


def test_strict_table_option_is_rejected_without_repair_or_backup(tmp_path: Path) -> None:
    path = tmp_path / "strict-table.sqlite3"
    backup_dir = tmp_path / "strict-backups"
    policy = BackupPolicy(directory=backup_dir)
    init_db(str(path))
    with _connect(path) as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='runs'"
        ).fetchone()[0]
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET sql=? WHERE type='table' AND name='runs'",
            (sql.rstrip() + " STRICT",),
        )
        schema_version = connection.execute("PRAGMA schema_version").fetchone()[0]
        connection.execute(f"PRAGMA schema_version={schema_version + 1}")

    with _connect(path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_mtime
    assert list_backups(path, policy=policy) == []
    assert not backup_dir.exists()


def test_without_rowid_table_option_is_rejected_without_repair_or_backup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "without-rowid-table.sqlite3"
    backup_dir = tmp_path / "without-rowid-backups"
    policy = BackupPolicy(directory=backup_dir)
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        runs_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='runs'"
        ).fetchone()[0]
        replacement_sql = runs_sql.replace("CREATE TABLE runs", "CREATE TABLE runs_new", 1)
        connection.execute(replacement_sql.rstrip() + " WITHOUT ROWID")
        connection.execute("DROP TABLE runs")
        connection.execute("ALTER TABLE runs_new RENAME TO runs")
        connection.execute(store_schema._raw_claim_trigger_sql())
        connection.commit()
        connection.execute("PRAGMA foreign_keys=ON")

    with _connect(path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA
    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_mtime
    assert list_backups(path, policy=policy) == []
    assert not backup_dir.exists()


@pytest.mark.parametrize(
    ("child", "reference", "parent", "parent_key"),
    store_schema._SAME_RUN_RELATIONSHIPS,
    ids=[
        f"{child}.{reference}"
        for child, reference, _parent, _parent_key in store_schema._SAME_RUN_RELATIONSHIPS
    ],
)
def test_every_same_run_child_reference_is_immutable_on_update(
    tmp_path: Path, child: str, reference: str, parent: str, parent_key: str
) -> None:
    path = tmp_path / f"child-{child}-{reference}.sqlite3"
    _provenance_database(path)
    _insert_relationship_rows(path, child, reference, parent, parent_key)

    with _connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f'UPDATE "{child}" SET run_id = ? WHERE "{reference}" = ?',
            ("run-b", f"shared-{child}-{reference}"),
        )
    with _connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f'UPDATE "{child}" SET "{reference}" = ? WHERE "{reference}" = ?',
            (f"changed-{child}-{reference}", f"shared-{child}-{reference}"),
        )


@pytest.mark.parametrize(
    ("child", "reference", "parent", "parent_key"),
    store_schema._SAME_RUN_RELATIONSHIPS,
    ids=[
        f"{parent}.{parent_key}"
        for _child, _reference, parent, parent_key in store_schema._SAME_RUN_RELATIONSHIPS
    ],
)
def test_every_referenced_parent_owner_and_key_is_immutable_on_update(
    tmp_path: Path, child: str, reference: str, parent: str, parent_key: str
) -> None:
    path = tmp_path / f"parent-{parent}-{parent_key}.sqlite3"
    _provenance_database(path)
    _insert_relationship_rows(path, child, reference, parent, parent_key)
    relation_key = f"shared-{child}-{reference}"

    with _connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f'UPDATE "{parent}" SET run_id = ? WHERE "{parent_key}" = ?', ("run-b", relation_key)
        )
    with _connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f'UPDATE "{parent}" SET "{parent_key}" = ? WHERE "{parent_key}" = ?',
            (f"changed-{relation_key}", relation_key),
        )


def test_run_status_and_checkpoint_updates_remain_mutable(tmp_path: Path) -> None:
    path = tmp_path / "mutable-run-state.sqlite3"
    _provenance_database(path)

    with _connect(path) as connection:
        connection.execute("UPDATE runs SET status='completed' WHERE run_id='run-a'")
        connection.execute(
            "INSERT INTO orchestration_checkpoints "
            "(run_id, stage_key, status, failure_reason, updated_at) "
            "VALUES ('run-a', 'planner', 'running', NULL, 'before')"
        )
        connection.execute(
            "UPDATE orchestration_checkpoints SET status='completed', updated_at='after' "
            "WHERE run_id='run-a' AND stage_key='planner'"
        )
        assert connection.execute("SELECT status FROM runs WHERE run_id='run-a'").fetchone()[0] == (
            "completed"
        )
        assert tuple(
            connection.execute(
                "SELECT status, updated_at FROM orchestration_checkpoints "
                "WHERE run_id='run-a' AND stage_key='planner'"
            ).fetchone()
        ) == ("completed", "after")


def test_migration_sixteen_rolls_back_triggers_and_retains_backup_then_retries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "migration-16-failure.sqlite3"
    backup_dir = tmp_path / "verified-backups"
    policy = BackupPolicy(directory=backup_dir)
    init_db(str(path))
    _reduce_to_recorded_version(path, 15)
    with _connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_provenance_migration BEFORE INSERT ON schema_migrations "
            "WHEN NEW.version=16 BEGIN SELECT RAISE(ABORT, 'injected migration 16 failure'); END"
        )
    before = path.read_bytes()

    with pytest.raises(sqlite3.IntegrityError, match="injected migration 16 failure"):
        init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert list_backups(path, policy=policy)[0].schema_version == 15
    with _connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 15
        update_triggers = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE '%_provenance_immutable_update'"
        ).fetchone()[0]
        assert update_triggers == 0
        connection.execute("DROP TRIGGER reject_provenance_migration")

    init_db(str(path), backup_policy=policy)
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == CURRENT_SCHEMA_VERSION
    assert list_backups(path, policy=policy)


def test_pending_migration_sixteen_reuses_matching_preinstalled_guards(tmp_path: Path) -> None:
    path = tmp_path / "pending-valid-guards.sqlite3"
    init_db(str(path))
    with _connect(path) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version=16")
    with _connect(path) as connection:
        connection.row_factory = sqlite3.Row
        store_schema._apply_update_provenance_migration(connection)

    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == CURRENT_SCHEMA_VERSION


def _corrupt_parent_owner_without_changing_schema(path: Path) -> None:
    with _connect(path) as connection:
        rows = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('retrieval_attempts', 'search_queries')"
        ).fetchall()
        for row in rows:
            connection.execute(f'DROP TRIGGER "{row["name"]}"')
        connection.execute("UPDATE search_queries SET run_id='run-b' WHERE query_id='q-a'")
        for row in rows:
            connection.execute(row["sql"])


def _insert_relationship_rows(
    path: Path, child: str, reference: str, parent: str, parent_key: str
) -> None:
    relation_key = f"shared-{child}-{reference}"
    with _connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        _insert_minimal_row(connection, parent, {"run_id": "run-a", parent_key: relation_key})
        _insert_minimal_row(connection, child, {"run_id": "run-a", reference: relation_key})


def _insert_minimal_row(
    connection: sqlite3.Connection, table: str, overrides: dict[str, str]
) -> None:
    values: dict[str, object] = {}
    for column in connection.execute(f'PRAGMA table_info("{table}")'):
        name = column["name"]
        if name in overrides:
            values[name] = overrides[name]
        elif name == "run_id":
            values[name] = "run-a"
        elif column["notnull"] or column["pk"]:
            declaration = str(column["type"]).upper()
            values[name] = 1 if "INT" in declaration else "fixture"
    columns = ", ".join(f'"{name}"' for name in values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', tuple(values.values())
    )


def _reduce_to_recorded_version(path: Path, version: int) -> None:
    """Remove schema objects introduced later, preserving executable older boundaries."""
    with _connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        canonical = store_schema._canonical_schema()
        for kind, name, _sql in reversed(canonical):
            if store_schema._object_version(kind, name) > version and kind in {
                "trigger",
                "index",
            }:
                connection.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')
        for kind, name, _sql in reversed(canonical):
            if kind == "table" and store_schema._object_version(kind, name) > version:
                connection.execute(f'DROP TABLE IF EXISTS "{name}"')
        for table in ("model_route_attempts", "snapshots", "search_queries"):
            columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            for column in columns:
                if store_schema._column_version(table, column["name"]) > version:
                    connection.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column["name"]}"')
        connection.execute("DELETE FROM schema_migrations WHERE version > ?", (version,))


def _provenance_database(path: Path) -> None:
    init_db(str(path))
    with _connect(path) as connection:
        for run_id in ("run-a", "run-b"):
            connection.execute(
                "INSERT INTO runs(run_id, status, raw_claim, current_stage, created_at, "
                "updated_at) "
                "VALUES (?, 'running', 'claim', 'planner', 'now', 'now')",
                (run_id,),
            )
            connection.execute(
                "INSERT INTO planner_outputs(run_id, planner_prompt_version, planner_model_name, "
                "planned_at) VALUES (?, 'v1', 'model', 'now')",
                (run_id,),
            )
        for query_id, run_id in (("q-a", "run-a"), ("q-b", "run-b")):
            connection.execute(
                "INSERT INTO search_queries(query_id, run_id, stance, query_round, strategy, "
                "query_text, exclusion_parameters, created_at) "
                "VALUES (?, ?, 'support', 1, 'broad', 'query', '[]', 'now')",
                (query_id, run_id),
            )
        connection.execute(
            "INSERT INTO retrieval_attempts(retrieval_attempt_id, run_id, query_id, query_round, "
            "query_text, search_rank, source_url, resolved_url, status, retrieved_at) "
            "VALUES ('r-a', 'run-a', 'q-a', 1, 'query', 1, 'https://a.test', "
            "'https://a.test', 'retrieved', 'now')"
        )
