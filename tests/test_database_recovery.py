"""Recovery copies and upgrades across executable migration boundaries.

These databases are generated from the checked-in executable schema and migration
functions. They are migration-boundary fixtures, not claimed archival snapshots.
"""

from __future__ import annotations

import errno
import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path
from threading import Event, Thread, current_thread
from urllib.parse import quote
from uuid import UUID

import pytest

import researchassistant.storage.store as store_module
from researchassistant.storage import database_recovery, store_schema
from researchassistant.storage.database_recovery import (
    BackupPolicy,
    create_upgrade_backup,
    list_backups,
    prune_backups,
    restore_backup,
)
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    init_db,
    open_read_only_store,
)

_MIGRATIONS = (
    store_schema._apply_raw_claim_immutability_migration,
    store_schema._apply_mvp68_integrity_migration,
    store_schema._apply_mvp69_provenance_migration,
    store_schema._apply_mvp10_evidence_portfolio_migration,
    store_schema._apply_mvp11_research_governor_migration,
    store_schema._apply_mlp4_discovery_query_migration,
    store_schema._apply_v2_phase1_artifact_migration,
    store_schema._apply_v2_phase3_initial_planner_migration,
    store_schema._apply_v2_phase10_reviewer_ledger_migration,
    store_schema._apply_cache_usage_migration,
    store_schema._apply_complete_usage_migration,
    store_schema._apply_update_provenance_migration,
    store_schema._apply_query_indexes_migration,
)


def _boundary_database(path: Path, version: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Build a recorded migration boundary from the executable definitions."""
    originals = {migration.__name__: migration for migration in _MIGRATIONS}
    for name in originals:
        monkeypatch.setattr(store_schema, name, lambda _conn: None)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        store_schema._initialize_schema(conn)
    finally:
        conn.close()

    for migration in _MIGRATIONS:
        monkeypatch.setattr(store_schema, migration.__name__, originals[migration.__name__])

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        if version < 4:
            conn.execute("DELETE FROM schema_migrations WHERE version > ?", (version,))
        for migration_version, migration in enumerate(_MIGRATIONS, start=5):
            if migration_version <= version:
                migration(conn)
        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "boundary-run",
                "running",
                "A preserved recovery claim",
                "claim_planner",
                "2026-10-03T12:00:00+00:00",
                "2026-10-03T12:00:00+00:00",
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _recorded_version(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0])


def _run_row(path: Path) -> tuple[object, ...]:
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT run_id, status, raw_claim, current_stage, created_at, updated_at, completed_at "
            "FROM runs WHERE run_id='boundary-run'"
        ).fetchone()


@pytest.mark.parametrize("version", range(1, 7))
def test_read_only_inspection_rejects_schema_one_through_six_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: int
) -> None:
    path = tmp_path / f"schema-{version}.sqlite3"
    _boundary_database(path, version, monkeypatch)
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError):
        open_read_only_store(path)

    assert path.read_bytes() == before


@pytest.mark.parametrize("version", range(7, store_schema.CURRENT_SCHEMA_VERSION + 1))
def test_read_only_inspection_accepts_schema_seven_through_current_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: int
) -> None:
    path = tmp_path / f"schema-{version}.sqlite3"
    _boundary_database(path, version, monkeypatch)
    before = path.read_bytes()

    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == version

    assert path.read_bytes() == before


@pytest.mark.parametrize("version", range(1, store_schema.CURRENT_SCHEMA_VERSION))
def test_generated_historical_boundary_upgrades_with_verified_backup_and_run_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: int
) -> None:
    path = tmp_path / f"upgrade-{version}.sqlite3"
    backup_dir = tmp_path / f"backups-{version}"
    policy = BackupPolicy(directory=backup_dir)
    _boundary_database(path, version, monkeypatch)
    prior_run = _run_row(path)

    init_db(str(path), backup_policy=policy)

    assert _recorded_version(path) == store_schema.CURRENT_SCHEMA_VERSION
    assert _run_row(path) == prior_run
    records = list_backups(path, policy=policy)
    assert len(records) == 1
    assert records[0].schema_version == version
    assert records[0].path.is_file()
    with sqlite3.connect(records[0].path) as backup:
        assert backup.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == version
        assert (
            backup.execute(
                "SELECT run_id, status, raw_claim, current_stage, created_at, updated_at, "
                "completed_at "
                "FROM runs WHERE run_id='boundary-run'"
            ).fetchone()
            == prior_run
        )


def test_current_schema_initialization_does_not_create_upgrade_backup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "current.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    init_db(str(path), backup_policy=policy)
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime
    assert _recorded_version(path) == store_schema.CURRENT_SCHEMA_VERSION
    assert list_backups(path, policy=policy) == []


def test_backup_failure_stops_upgrade_and_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "backup-failure.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)
    before = path.read_bytes()

    def fail_backup(*_args: object, **_kwargs: object) -> object:
        raise OSError("injected backup failure")

    monkeypatch.setattr(database_recovery, "create_upgrade_backup", fail_backup)
    with pytest.raises(OSError, match="injected backup failure"):
        init_db(str(path), backup_policy=policy)
    assert path.read_bytes() == before
    assert list_backups(path, policy=policy) == []

    monkeypatch.undo()
    init_db(str(path), backup_policy=policy)
    assert _recorded_version(path) == store_schema.CURRENT_SCHEMA_VERSION
    assert len(list_backups(path, policy=policy)) == 1


@pytest.mark.parametrize("failure", [InterruptedError, KeyboardInterrupt])
def test_interrupted_backup_leaves_source_read_only_and_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
) -> None:
    path = tmp_path / "interrupted-backup.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)
    before = path.read_bytes()

    def interrupt_backup(*_args: object, **_kwargs: object) -> object:
        raise failure("injected interruption")

    monkeypatch.setattr(database_recovery, "create_upgrade_backup", interrupt_backup)
    with pytest.raises(failure, match="injected interruption"):
        init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert _recorded_version(path) == 13
    assert list_backups(path, policy=policy) == []


def test_failed_migration_keeps_verified_copy_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "migration-failure.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)
    prior_run = _run_row(path)
    original_initialize = store_schema._initialize_schema

    def fail_migration(_conn: sqlite3.Connection) -> None:
        raise sqlite3.OperationalError("injected migration failure")

    monkeypatch.setattr(store_schema, "_initialize_schema", fail_migration)
    with pytest.raises(sqlite3.OperationalError, match="injected migration failure"):
        init_db(str(path), backup_policy=policy)

    records = list_backups(path, policy=policy)
    assert len(records) == 1
    assert records[0].schema_version == 13
    assert _recorded_version(path) == 13
    assert _run_row(path) == prior_run

    monkeypatch.setattr(store_schema, "_initialize_schema", original_initialize)
    init_db(str(path), backup_policy=policy)
    assert _recorded_version(path) == store_schema.CURRENT_SCHEMA_VERSION
    assert records[0] in list_backups(path, policy=policy)


def test_restore_requires_new_destination_and_restores_verified_old_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "restore-source.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 7, monkeypatch)
    init_db(str(path), backup_policy=policy)
    backup = list_backups(path, policy=policy)[0]

    with pytest.raises(FileExistsError):
        restore_backup(backup.path, backup.path)
    occupied = tmp_path / "occupied.sqlite3"
    occupied.write_bytes(b"keep these bytes")
    with pytest.raises(FileExistsError):
        restore_backup(backup.path, occupied)
    assert occupied.read_bytes() == b"keep these bytes"

    restored = tmp_path / "restored.sqlite3"
    assert restore_backup(backup.path, restored) == restored
    assert _recorded_version(restored) == 7
    assert _run_row(restored) == _run_row(backup.path)


def test_retention_prunes_old_verified_copies_and_keeps_latest(
    tmp_path: Path,
) -> None:
    path = tmp_path / "retention.sqlite3"
    policy = BackupPolicy(count=2, directory=tmp_path / "backups")
    init_db(str(path))

    for _ in range(3):
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as source:
            source.row_factory = sqlite3.Row
            source.execute("PRAGMA query_only=ON")
            source.execute("BEGIN")
            create_upgrade_backup(path, source, store_schema.CURRENT_SCHEMA_VERSION, policy=policy)

    before_prune = list_backups(path, policy=policy)
    assert len(before_prune) == 3
    newest = before_prune[0]

    prune_backups(path, policy=policy)

    after_prune = list_backups(path, policy=policy)
    assert len(after_prune) == 2
    assert newest in after_prune
    assert all(record.path.is_file() for record in after_prune)


def test_custom_backup_directory_expansion_matches_creation_and_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "custom-expansion.sqlite3"
    selected_directory = Path("~/recovery-copies")
    actual_directory = tmp_path / "recovery-copies"
    original_expanduser = Path.expanduser

    def expanduser(value: Path) -> Path:
        # Keep this user-directory case entirely inside disposable storage.
        return actual_directory if value == selected_directory else original_expanduser(value)

    monkeypatch.setattr(Path, "expanduser", expanduser)
    _boundary_database(path, 13, monkeypatch)
    policy = BackupPolicy(directory=selected_directory)
    init_db(str(path), backup_policy=policy)
    records = list_backups(path, policy=policy)
    assert len(records) == 1
    assert records[0].path.parent == actual_directory


def test_retention_defers_a_copy_in_use_until_restore_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "concurrent-retention.sqlite3"
    policy = BackupPolicy(count=1, directory=tmp_path / "backups")
    init_db(str(path))
    for _ in range(2):
        with database_recovery._read_only(path) as source:
            create_upgrade_backup(path, source, store_schema.CURRENT_SCHEMA_VERSION, policy=policy)
    newest, oldest = list_backups(path, policy=policy)
    destination = tmp_path / "concurrent-restored.sqlite3"
    verified = Event()
    release = Event()
    errors: list[BaseException] = []
    original_verify = database_recovery._verified_record

    def pause_verified_restore(
        backup: Path,
    ) -> tuple[database_recovery.BackupRecord, dict[str, object]]:
        result = original_verify(backup)
        if current_thread() is worker:
            verified.set()
            assert release.wait(5), "test did not release the verified restore"
        return result

    def restore() -> None:
        try:
            restore_backup(oldest.path, destination)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(database_recovery, "_verified_record", pause_verified_restore)
    worker = Thread(target=restore)
    worker.start()
    try:
        assert verified.wait(5), "restore did not reach its verification-to-copy boundary"
        prune_backups(path, policy=policy)
        assert list_backups(path, policy=policy) == [newest, oldest]
    finally:
        release.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert errors == []
    assert _recorded_version(destination) == store_schema.CURRENT_SCHEMA_VERSION
    prune_backups(path, policy=policy)
    assert list_backups(path, policy=policy) == [newest]


def test_wal_backup_and_restore_include_committed_uncheckpointed_row(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wal-source.sqlite3"
    init_db(str(path))
    writer = sqlite3.connect(path)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "wal-committed-run",
                "running",
                "Committed while still in WAL",
                "claim_planner",
                "2026-10-03T12:00:00+00:00",
                "2026-10-03T12:00:00+00:00",
                None,
            ),
        )
        writer.commit()
        assert Path(f"{path}-wal").exists()

        backup_policy = BackupPolicy(directory=tmp_path / "wal-backups")
        source_uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            source.row_factory = sqlite3.Row
            source.execute("PRAGMA query_only=ON")
            source.execute("BEGIN")
            record = create_upgrade_backup(
                path, source, store_schema.CURRENT_SCHEMA_VERSION, policy=backup_policy
            )
        restored = tmp_path / "wal-restored.sqlite3"
        restore_backup(record.path, restored)
        with sqlite3.connect(restored) as conn:
            row = conn.execute(
                "SELECT raw_claim FROM runs WHERE run_id='wal-committed-run'"
            ).fetchone()
        assert row == ("Committed while still in WAL",)
    finally:
        writer.close()


def test_backup_verification_failure_aborts_upgrade_before_source_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "verify-failure.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)
    before = path.read_bytes()

    def fail_verification(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.DatabaseError("injected verification failure")

    monkeypatch.setattr(database_recovery, "_verify", fail_verification)
    with pytest.raises(sqlite3.DatabaseError, match="injected verification failure"):
        init_db(str(path), backup_policy=policy)

    assert path.read_bytes() == before
    assert _recorded_version(path) == 13
    assert list_backups(path, policy=policy) == []


def test_publication_name_collision_preserves_occupied_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "collision.sqlite3"
    backup_dir = tmp_path / "backups"
    policy = BackupPolicy(directory=backup_dir)
    _boundary_database(path, 13, monkeypatch)
    token = UUID("11111111-1111-1111-1111-111111111111")
    collision = backup_dir / f"{path.name}.pre-v13-{token}.sqlite3"
    backup_dir.mkdir()
    collision.write_bytes(b"preserve occupied backup name")
    before = path.read_bytes()
    monkeypatch.setattr(database_recovery, "uuid4", lambda: token)

    with pytest.raises(FileExistsError):
        init_db(str(path), backup_policy=policy)

    assert collision.read_bytes() == b"preserve occupied backup name"
    assert path.read_bytes() == before
    assert _recorded_version(path) == 13


def test_backup_discovery_ignores_orphans_without_cleaning_them(tmp_path: Path) -> None:
    path = tmp_path / "orphan-source.sqlite3"
    init_db(str(path))
    folder = tmp_path / "backups"
    folder.mkdir()
    pending = folder / ".pending-interrupted.sqlite3"
    pending.write_bytes(b"partial copy")
    orphan = folder / "unverified.sqlite3"
    orphan.write_bytes(b"unverified bytes")
    marker = folder / "unverified.sqlite3.verified.json"
    marker.write_text("not valid metadata", encoding="utf-8")
    policy = BackupPolicy(directory=folder)

    assert list_backups(path, policy=policy) == []

    assert pending.read_bytes() == b"partial copy"
    assert orphan.read_bytes() == b"unverified bytes"
    assert marker.read_text(encoding="utf-8") == "not valid metadata"


@pytest.mark.skipif(os.name != "posix", reason="directory mode bits are POSIX-specific")
def test_custom_backup_directory_mode_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "custom-dir-source.sqlite3"
    _boundary_database(path, 13, monkeypatch)
    os.chmod(tmp_path, 0o750)
    original_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    policy = BackupPolicy(directory=tmp_path)

    init_db(str(path), backup_policy=policy)

    assert stat.S_IMODE(tmp_path.stat().st_mode) == original_mode
    assert len(list_backups(path, policy=policy)) == 1


@pytest.mark.parametrize("error_number", [errno.ENOSPC, errno.EACCES])
def test_private_file_creation_failure_aborts_upgrade_without_source_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    path = tmp_path / f"private-file-{error_number}.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)
    before = path.read_bytes()

    def fail_private_file(_path: Path) -> int:
        raise OSError(error_number, "injected private file failure")

    monkeypatch.setattr(database_recovery, "create_private_file", fail_private_file)
    with pytest.raises(OSError) as error:
        init_db(str(path), backup_policy=policy)

    assert error.value.errno == error_number
    assert path.read_bytes() == before
    assert _recorded_version(path) == 13
    assert list_backups(path, policy=policy) == []


def test_backup_prune_permission_failure_does_not_invalidate_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "prune-permission.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)

    def fail_prune(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("injected retention failure")

    monkeypatch.setattr(database_recovery, "prune_backups", fail_prune)
    init_db(str(path), backup_policy=policy)

    assert _recorded_version(path) == store_schema.CURRENT_SCHEMA_VERSION
    records = list_backups(path, policy=policy)
    assert len(records) == 1
    assert records[0].schema_version == 13


def test_corrupted_verified_backup_is_refused_without_creating_restore_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "corrupt-copy-source.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)
    init_db(str(path), backup_policy=policy)
    record = list_backups(path, policy=policy)[0]
    with record.path.open("ab") as handle:
        handle.write(b"corruption")
    target = tmp_path / "must-not-exist.sqlite3"

    with pytest.raises(ValueError, match="does not match its verification record"):
        restore_backup(record.path, target)

    assert not target.exists()


def test_restore_publication_race_preserves_new_occupied_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "restore-race-source.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 7, monkeypatch)
    init_db(str(path), backup_policy=policy)
    backup = list_backups(path, policy=policy)[0]
    destination = tmp_path / "restore-race-target.sqlite3"
    original_link = os.link
    occupied_bytes = b"created by competing publisher"

    def race_link(source: str | Path, target: str | Path, *args: object, **kwargs: object) -> None:
        if Path(target) == destination and not destination.exists():
            destination.write_bytes(occupied_bytes)
        original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(database_recovery.os, "link", race_link)
    with pytest.raises(FileExistsError):
        restore_backup(backup.path, destination)

    assert destination.read_bytes() == occupied_bytes


def test_cache_migration_keyboard_interrupt_keeps_copy_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "migration-interrupted.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 13, monkeypatch)
    prior_run = _run_row(path)
    original_migration = store_schema._apply_cache_usage_migration

    def interrupt_migration(_conn: sqlite3.Connection) -> None:
        raise KeyboardInterrupt("injected migration interruption")

    monkeypatch.setattr(store_schema, "_apply_cache_usage_migration", interrupt_migration)
    with pytest.raises(KeyboardInterrupt, match="injected migration interruption"):
        init_db(str(path), backup_policy=policy)

    records = list_backups(path, policy=policy)
    assert len(records) == 1
    assert records[0].schema_version == 13
    assert _recorded_version(path) == 13
    assert _run_row(path) == prior_run

    monkeypatch.setattr(store_schema, "_apply_cache_usage_migration", original_migration)
    init_db(str(path), backup_policy=policy)
    assert _recorded_version(path) == store_schema.CURRENT_SCHEMA_VERSION
    assert records[0] in list_backups(path, policy=policy)


def test_interrupted_baseline_upgrade_rolls_back_ledger_and_pending_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "baseline-interrupted.sqlite3"
    policy = BackupPolicy(directory=tmp_path / "backups")
    _boundary_database(path, 1, monkeypatch)
    with sqlite3.connect(path) as conn:
        for name in (
            "model_route_attempts",
            "provider_run_contracts",
            "run_cancellations",
            "orchestration_checkpoints",
            "orchestration_stage_artifacts",
        ):
            conn.execute(f'DROP TABLE "{name}"')
    before = path.read_bytes()
    original_connect = store_module._connect

    class InterruptedBaselineConnection(sqlite3.Connection):
        def executescript(self, script: str) -> sqlite3.Cursor:
            # Execute real baseline SQL through the first pending tables and
            # ledger rows, then simulate a process interruption before completion.
            prefix = script.split("CREATE TABLE IF NOT EXISTS provider_run_contracts", 1)[0]
            super().executescript(prefix)
            raise KeyboardInterrupt("interrupted baseline DDL")

    def interrupted_connect(db_path: str) -> sqlite3.Connection:
        connection = sqlite3.connect(db_path, factory=InterruptedBaselineConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    monkeypatch.setattr(store_module, "_connect", interrupted_connect)
    with pytest.raises(KeyboardInterrupt, match="interrupted baseline DDL"):
        init_db(str(path), backup_policy=policy)
    assert path.read_bytes() == before
    assert _recorded_version(path) == 1
    records = list_backups(path, policy=policy)
    assert len(records) == 1
    assert records[0].schema_version == 1

    monkeypatch.setattr(store_module, "_connect", original_connect)
    init_db(str(path), backup_policy=policy)
    assert _recorded_version(path) == store_schema.CURRENT_SCHEMA_VERSION


@pytest.mark.skipif(os.name != "posix", reason="POSIX recovery permissions")
def test_backup_metadata_and_restored_copy_are_private_under_permissive_umask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "private-recovery.sqlite3"
    _boundary_database(path, 13, monkeypatch)
    folder = path.with_name(f"{path.name}.backups")
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    parent_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    previous_umask = os.umask(0)
    try:
        init_db(str(path))
        record = list_backups(path)[0]
        metadata = record.path.with_name(f"{record.path.name}.verified.json")
        restored = restore_backup(record.path, tmp_path / "private-restored.sqlite3")
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(tmp_path.stat().st_mode) == parent_mode
    for private_path in (record.path, metadata, restored):
        assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    assert "A preserved recovery claim" not in metadata.read_text()
