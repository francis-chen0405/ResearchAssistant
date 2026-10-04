"""Explicit SQLite backup import preserving immutable history and the source file."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

from researchassistant.contracts.models import StrictModel
from researchassistant.platform_support.desktop_paths import application_data_dir
from researchassistant.platform_support.file_lock import FileLock
from researchassistant.platform_support.private_files import (
    create_private_file,
    private_directory,
    secure_private_path,
)
from researchassistant.storage.store import open_read_only_store, read_run


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
    destination_created = False
    destination_identity: tuple[int, int] | None = None
    try:
        with open_read_only_store(source) as original:
            before = [
                read_run(original.connection, UUID(row[0]))
                for row in original.connection.execute("SELECT run_id FROM runs ORDER BY run_id")
            ]
            if destination_dir is None:
                folder = private_directory(private_directory(application_data_dir()) / "imports")
            else:
                # This location belongs to the caller; preserve its directory policy.
                folder = destination_dir
                folder.mkdir(parents=True, exist_ok=True)
                if not folder.is_dir():
                    raise NotADirectoryError(folder)
            destination = folder / f"history-{uuid4()}.sqlite3"
            # Exclusive creation prevents accidental overwrite even on a name collision.
            descriptor = create_private_file(destination)
            destination_created = True
            created_info = os.fstat(descriptor)
            destination_identity = (created_info.st_dev, created_info.st_ino)
            try:
                # SQLite opens by path below, so first close the exclusive creation fd.
                secure_private_path(destination)
            finally:
                os.close(descriptor)
            with closing(sqlite3.connect(destination)) as target:
                secure_private_path(destination)
                original.connection.backup(target)
            # SQLite must not have relaxed permissions while writing the copy.
            secure_private_path(destination)
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
        if destination is not None and destination_created:
            try:
                current = destination.lstat()
            except FileNotFoundError:
                pass
            else:
                if destination_identity == (current.st_dev, current.st_ino):
                    destination.unlink()
        raise
    finally:
        lock.release()
