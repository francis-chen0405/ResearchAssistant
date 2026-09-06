"""Explicit SQLite backup import preserving immutable history and the source file."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

from desktop_paths import application_data_dir
from file_lock import FileLock
from models import StrictModel
from store import open_read_only_store, read_run


class HistoryImportResult(StrictModel):
    db_path: str
    run_count: int


def import_history(source: Path, *, destination_dir: Path | None = None) -> HistoryImportResult:
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError("Choose an existing ResearchAssistant SQLite database")
    lock = FileLock(source.with_name(f"{source.name}.mvp5.lock"))
    if not lock.acquire():
        raise ValueError("Source database has active research; finish it before importing")
    destination: Path | None = None
    try:
        with open_read_only_store(source) as original:
            before = [
                read_run(original.connection, UUID(row[0]))
                for row in original.connection.execute("SELECT run_id FROM runs ORDER BY run_id")
            ]
            folder = destination_dir or application_data_dir() / "imports"
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination = folder / f"history-{uuid4()}.sqlite3"
            # Exclusive creation prevents accidental overwrite even on a name collision.
            with destination.open("xb"):
                pass
            with sqlite3.connect(destination) as target:
                original.connection.backup(target)
            with open_read_only_store(destination) as copied:
                after = [
                    read_run(copied.connection, UUID(row[0]))
                    for row in copied.connection.execute("SELECT run_id FROM runs ORDER BY run_id")
                ]
                if (
                    before != after
                    or copied.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                ):
                    raise ValueError("Imported history did not pass verification")
        return HistoryImportResult(db_path=str(destination), run_count=len(after))
    except BaseException:
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise
    finally:
        lock.release()
