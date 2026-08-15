from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

import store as store_module
from cli import CLIExitCode, main
from frontend.live_service import LiveResearchController
from models import RunManifest, RunStatus, Stage
from orchestrator import ProviderRunStatus, inspect_provider_run
from store import (
    RAW_CLAIM_TRIGGER_NAME,
    DatabaseCompatibilityError,
    DatabaseCompatibilityIssue,
    init_db,
    insert_run,
    open_read_only_store,
    read_run,
    update_run,
)

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _manifest(status: RunStatus = RunStatus.RUNNING, *, claim: str = "Exact claim") -> RunManifest:
    completed_at = NOW if status is not RunStatus.RUNNING else None
    return RunManifest(
        run_id=uuid4(),
        status=status,
        raw_claim=claim,
        current_stage=Stage.CLAIM_PLANNER,
        created_at=NOW,
        updated_at=NOW,
        completed_at=completed_at,
    )


def _migration_rows(path: Path) -> list[tuple[int, str]]:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT version, description FROM schema_migrations ORDER BY version"
        ).fetchall()


def _remove_mvp68_schema_records(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM schema_migrations WHERE version >= 6")
    for trigger_name in store_module.IMMUTABLE_ARTIFACT_TRIGGERS:
        connection.execute(f'DROP TRIGGER IF EXISTS "{trigger_name}"')


def _schema_objects(path: Path) -> list[tuple[str, str, str | None]]:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            """SELECT type, name, sql FROM sqlite_master
               WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"""
        ).fetchall()


@pytest.mark.parametrize(
    "status",
    [
        RunStatus.RUNNING,
        RunStatus.COMPLETED,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    ],
)
def test_sqlite_rejects_actual_claim_changes_for_every_status(
    tmp_path: Path, status: RunStatus
) -> None:
    path = tmp_path / f"{status.value}.sqlite3"
    init_db(str(path))
    manifest = _manifest(status)
    insert_run(str(path), manifest)

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="runs.raw_claim is immutable"):
            connection.execute(
                "UPDATE runs SET raw_claim = ? WHERE run_id = ?",
                ("Changed claim", str(manifest.run_id)),
            )

    assert read_run(str(path), manifest.run_id).raw_claim == manifest.raw_claim


def test_identical_claim_and_other_mutable_fields_can_be_updated(tmp_path: Path) -> None:
    path = tmp_path / "mutable.sqlite3"
    init_db(str(path))
    manifest = _manifest()
    insert_run(str(path), manifest)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE runs SET raw_claim = raw_claim, status = 'failed'
               WHERE run_id = ?""",
            (str(manifest.run_id),),
        )

    assert read_run(str(path), manifest.run_id).status is RunStatus.FAILED


def test_application_claim_guard_remains_defense_in_depth(tmp_path: Path) -> None:
    path = tmp_path / "application-guard.sqlite3"
    init_db(str(path))
    manifest = _manifest()
    insert_run(str(path), manifest)

    with pytest.raises(ValueError, match="raw_claim is immutable after run creation"):
        update_run(str(path), manifest.model_copy(update={"raw_claim": "Changed claim"}))


def test_migration_five_upgrades_migration_four_without_rewriting_claims(tmp_path: Path) -> None:
    path = tmp_path / "migration-four.sqlite3"
    init_db(str(path))
    manifest = _manifest(claim="Byte-exact claim: \u00e9 and trailing spaces  ")
    insert_run(str(path), manifest)
    original = manifest.raw_claim.encode()
    with sqlite3.connect(path) as connection:
        _remove_mvp68_schema_records(connection)
        connection.execute(f'DROP TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"')
        connection.execute("DELETE FROM schema_migrations WHERE version = 5")
        connection.execute(
            """UPDATE schema_migrations
               SET description = 'same-run provenance triggers and immutable raw claim'
               WHERE version = 4"""
        )

    init_db(str(path))

    assert read_run(str(path), manifest.run_id).raw_claim.encode() == original
    rows = _migration_rows(path)
    assert rows[-7:] == [
        (4, "same-run provenance protection triggers"),
        (5, "database-enforced immutable runs.raw_claim"),
        (6, "immutable snapshots and Ledger with exact decimal model costs"),
        (7, "snapshot acquisition and media-type provenance"),
        (8, "mvp-10 evidence portfolio and trail"),
        (9, "mvp-11 bounded research governor records"),
        (10, "mlp-4 provider-specific discovery query provenance"),
    ]


def test_migration_five_is_idempotent_and_trigger_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "idempotent.sqlite3"
    init_db(str(path))
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (RAW_CLAIM_TRIGGER_NAME,),
        ).fetchone()
    assert trigger is not None
    assert _migration_rows(path).count((5, "database-enforced immutable runs.raw_claim")) == 1


def test_failed_trigger_installation_does_not_record_migration_five(tmp_path: Path) -> None:
    path = tmp_path / "failed-install.sqlite3"
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        _remove_mvp68_schema_records(connection)
        connection.execute(f'DROP TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"')
        connection.execute("DELETE FROM schema_migrations WHERE version = 5")
        connection.execute(
            f"""CREATE TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"
                 BEFORE UPDATE OF status ON runs BEGIN SELECT 1; END"""
        )

    with pytest.raises(sqlite3.DatabaseError):
        init_db(str(path))

    assert all(version != 5 for version, _ in _migration_rows(path))


def test_trigger_error_is_stable_and_does_not_echo_claim_data(tmp_path: Path) -> None:
    path = tmp_path / "secret.sqlite3"
    init_db(str(path))
    manifest = _manifest(claim="current-secret-value")
    insert_run(str(path), manifest)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError) as caught:
            connection.execute(
                "UPDATE runs SET raw_claim = ? WHERE run_id = ?",
                ("replacement-secret-value", str(manifest.run_id)),
            )
    assert str(caught.value) == "runs.raw_claim is immutable"


def test_read_only_inspection_preserves_database_bytes_schema_migrations_and_mtime(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inspection.sqlite3"
    init_db(str(path))
    manifest = _manifest()
    insert_run(str(path), manifest)
    before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    before_mtime = path.stat().st_mtime_ns
    before_schema = _schema_objects(path)
    before_migrations = _migration_rows(path)

    inspected = inspect_provider_run(path, manifest.run_id)

    assert inspected.status is ProviderRunStatus.RUNNING
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_hash
    assert path.stat().st_mtime_ns == before_mtime
    assert _schema_objects(path) == before_schema
    assert _migration_rows(path) == before_migrations


def test_inspection_and_history_never_reopen_through_writable_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "no-writable-reopen.sqlite3"
    init_db(str(path))
    manifest = _manifest()
    insert_run(str(path), manifest)

    def fail_writable_connect(db_path: str) -> sqlite3.Connection:
        raise AssertionError(f"unexpected writable connection for {db_path}")

    monkeypatch.setattr(store_module, "_connect", fail_writable_connect)

    assert inspect_provider_run(path, manifest.run_id).run_id == manifest.run_id
    history = LiveResearchController(environment={}).history(path)
    assert [item.run_id for item in history] == [manifest.run_id]


def test_inspection_reconstructs_partial_running_state(tmp_path: Path) -> None:
    path = tmp_path / "inspect-running.sqlite3"
    init_db(str(path))
    manifest = _manifest(RunStatus.RUNNING)
    insert_run(str(path), manifest)

    inspected = inspect_provider_run(path, manifest.run_id)
    assert inspected.status is ProviderRunStatus.RUNNING
    assert inspected.current_stage is Stage.CLAIM_PLANNER


def test_read_only_open_handles_spaces_and_url_sensitive_characters(tmp_path: Path) -> None:
    path = tmp_path / "space # percent % question ?.sqlite3"
    init_db(str(path))
    manifest = _manifest()
    insert_run(str(path), manifest)

    with open_read_only_store(path) as store:
        assert store.read_run(manifest.run_id) == manifest
        assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert store.connection.execute("PRAGMA query_only").fetchone()[0] == 1


def test_read_only_open_supports_read_only_filesystem_permissions(tmp_path: Path) -> None:
    path = tmp_path / "permissions.sqlite3"
    init_db(str(path))
    manifest = _manifest()
    insert_run(str(path), manifest)
    path.chmod(0o444)
    try:
        assert inspect_provider_run(path, manifest.run_id).raw_claim == manifest.raw_claim
    finally:
        path.chmod(0o600)


def test_missing_inspection_and_history_do_not_create_database(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(DatabaseCompatibilityError) as caught:
        inspect_provider_run(path, uuid4())
    assert caught.value.result.issue is DatabaseCompatibilityIssue.MISSING_FILE
    assert LiveResearchController(environment={}).history(path) == ()
    assert not path.exists()


def test_older_schema_requires_writable_run_or_resume_without_modification(tmp_path: Path) -> None:
    path = tmp_path / "older.sqlite3"
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        _remove_mvp68_schema_records(connection)
        connection.execute(f'DROP TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"')
        connection.execute("DELETE FROM schema_migrations WHERE version = 5")
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)

    assert caught.value.result.issue is DatabaseCompatibilityIssue.OLDER_SCHEMA
    assert "writable run or resume" in caught.value.result.message
    assert path.read_bytes() == before


def test_newer_schema_is_rejected_without_modification(tmp_path: Path) -> None:
    path = tmp_path / "newer.sqlite3"
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO schema_migrations VALUES (99, 'future', '2026-08-09T00:00:00+00:00')"
        )
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)

    assert caught.value.result.issue is DatabaseCompatibilityIssue.NEWER_SCHEMA
    assert path.read_bytes() == before


def test_invalid_sqlite_file_is_rejected_and_remains_byte_identical(tmp_path: Path) -> None:
    path = tmp_path / "invalid.sqlite3"
    path.write_bytes(b"not a sqlite database\x00secret")
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)

    assert caught.value.result.issue is DatabaseCompatibilityIssue.INVALID_SQLITE
    assert path.read_bytes() == before


def test_read_only_open_failure_has_a_distinct_compatibility_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "open-failure.sqlite3"
    init_db(str(path))

    def fail_open(*args: object, **kwargs: object) -> sqlite3.Connection:
        del args, kwargs
        raise sqlite3.OperationalError("injected permission failure")

    monkeypatch.setattr(sqlite3, "connect", fail_open)
    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)

    assert caught.value.result.issue is DatabaseCompatibilityIssue.OPEN_FAILED


def test_recorded_current_migration_with_missing_trigger_is_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        connection.execute(f'DROP TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"')

    with pytest.raises(DatabaseCompatibilityError) as caught:
        open_read_only_store(path)

    assert caught.value.result.issue is DatabaseCompatibilityIssue.CORRUPT_SCHEMA


def test_cli_incompatible_inspection_fails_without_migrating(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "cli-older.sqlite3"
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        _remove_mvp68_schema_records(connection)
        connection.execute(f'DROP TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"')
        connection.execute("DELETE FROM schema_migrations WHERE version = 5")
    before = path.read_bytes()

    result = main(["inspect-run", str(path), str(uuid4())])

    captured = capsys.readouterr()
    assert result == CLIExitCode.INVALID_INPUT
    assert "writable run or resume" in captured.err
    assert path.read_bytes() == before


def test_web_history_rejects_incompatible_database_without_migrating(tmp_path: Path) -> None:
    path = tmp_path / "web-older.sqlite3"
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        _remove_mvp68_schema_records(connection)
        connection.execute(f'DROP TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"')
        connection.execute("DELETE FROM schema_migrations WHERE version = 5")
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError):
        LiveResearchController(environment={}).history(path)

    assert path.read_bytes() == before


def test_read_only_inspection_coexists_with_wal_writer(tmp_path: Path) -> None:
    path = tmp_path / "wal.sqlite3"
    init_db(str(path))
    manifest = _manifest()
    insert_run(str(path), manifest)
    with sqlite3.connect(path) as writer:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            "UPDATE runs SET updated_at = updated_at WHERE run_id = ?",
            (str(manifest.run_id),),
        )
        inspected = inspect_provider_run(path, manifest.run_id)
        writer.rollback()

    assert inspected.run_id == manifest.run_id
