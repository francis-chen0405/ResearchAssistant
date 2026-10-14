"""Disposable native filesystem/crash checks; timing hooks do not simulate power loss."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from desktop.smoke_support import BackendMonitor
from researchassistant.platform_support.private_files import create_private_file, private_directory
from researchassistant.storage import database_recovery, store_schema
from researchassistant.storage.database_lock import database_lock
from researchassistant.storage.store import init_db, open_read_only_store


def _old_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        store_schema._initialize_schema(connection, target_version=16)
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "crash-run",
                "running",
                "A preserved fixture claim",
                "claim_planner",
                "2026-10-13T12:00:00+00:00",
                "2026-10-13T12:00:00+00:00",
                None,
            ),
        )
        connection.commit()
        assert store_schema.validate_recorded_database(connection) == 16


def _contents(path: Path) -> tuple[int, tuple[object, ...]]:
    with open_read_only_store(path) as session:
        connection = session.connection
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        version = store_schema.validate_recorded_database(connection)
        row = tuple(connection.execute("SELECT * FROM runs WHERE run_id='crash-run'").fetchone())
        return version, row


@pytest.mark.parametrize("depth", [0, 4])
def test_native_unicode_long_path_upgrade_backup_restore_and_no_overwrite(
    tmp_path: Path,
    depth: int,
) -> None:
    folder = tmp_path / "résultats 研究 # percent%"
    for index in range(depth):
        folder /= f"{index}-" + "long-path-" * 4
    private_directory(folder)
    path = folder / "historique 研究 # %.sqlite3"
    if depth:
        assert len(str(path)) > 300
    _old_database(path)
    before = _contents(path)
    init_db(path)
    after = _contents(path)
    assert after == (store_schema.CURRENT_SCHEMA_VERSION, before[1])
    records = database_recovery.list_backups(path)
    assert len(records) == 1
    assert _contents(records[0].path) == before
    restored = folder / "restauré 研究 # %.sqlite3"
    database_recovery.restore_backup(records[0].path, restored)
    assert _contents(restored) == before
    original = restored.read_bytes()
    with pytest.raises(FileExistsError):
        database_recovery.restore_backup(records[0].path, restored)
    assert restored.read_bytes() == original
    # Link publication itself must atomically refuse a colliding directory entry.
    pending = folder / ".pending-publication"
    descriptor = create_private_file(pending)
    os.close(descriptor)
    pending.write_bytes(b"must not replace existing history")
    with pytest.raises(FileExistsError):
        database_recovery._publish(pending, restored)
    assert restored.read_bytes() == original
    assert pending.read_bytes() == b"must not replace existing history"


@pytest.mark.parametrize(
    "phase",
    [
        "backup-file-flushed",
        "backup-linked",
        "marker-linked",
        "migration-uncommitted",
        "migration-committed",
    ],
)
def test_native_killed_upgrade_recovers_and_retains_verified_backup(
    tmp_path: Path,
    phase: str,
) -> None:
    path = tmp_path / "crash 研究 # %.sqlite3"
    _old_database(path)
    before = _contents(path)
    driver = Path(__file__).with_name("storage_crash_driver.py")
    process = subprocess.Popen(
        [sys.executable, "-u", str(driver), str(path), phase],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    monitor = BackendMonitor(process, label=f"native upgrade {phase}")
    try:
        assert monitor.startup(timeout=30) == phase + "\n"
        process.kill()  # Owned handle: TerminateProcess on Windows, SIGKILL on POSIX.
        assert process.wait(timeout=10) != 0
        monitor.finish_reading()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        monitor.finish_reading()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    expected_version = 17 if phase == "migration-committed" else 16
    assert _contents(path) == (expected_version, before[1])
    # Abrupt termination must release the application and SQLite process locks.
    with database_lock(path):
        pass
    records = database_recovery.list_backups(path)
    published = phase in {"marker-linked", "migration-uncommitted", "migration-committed"}
    assert len(records) == int(published)
    if records:
        restored = tmp_path / "restored.sqlite3"
        database_recovery.restore_backup(records[0].path, restored)
        assert _contents(restored) == before
    init_db(path)
    assert _contents(path) == (17, before[1])
    assert database_recovery.list_backups(path)
