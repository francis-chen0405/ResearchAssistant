"""Pause real storage operations at named boundaries for parent-owned termination.

Only generated temporary databases are passed by test_native_storage_durability.
This injects timing; file/link/SQLite operations and process termination are native.
It cannot model loss of the OS page cache, disk/controller cache or physical power.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from researchassistant.storage import database_recovery, store_schema
from researchassistant.storage.sqlite_policy import PolicyConnection


def pause(phase: str) -> NoReturn:
    print(phase, flush=True)
    while True:
        time.sleep(1)


class CrashConnection(PolicyConnection):
    phase: str = ""
    migration_pending: bool = False

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        result = super().execute(sql, parameters)
        if sql.startswith("INSERT INTO schema_migrations") and parameters and parameters[0] == 17:
            self.migration_pending = True
            if self.phase == "migration-uncommitted":
                assert self.in_transaction
                pause(self.phase)
        return result

    def commit(self) -> None:
        super().commit()
        if self.migration_pending and self.phase == "migration-committed":
            assert not self.in_transaction
            pause(self.phase)


def main() -> None:
    path, phase = Path(sys.argv[1]), sys.argv[2]
    original_flush = database_recovery._flush_file
    original_publish = database_recovery._publish

    def flush_file(target: Path) -> None:
        original_flush(target)
        if phase == "backup-file-flushed" and target.suffix == ".sqlite3":
            pause(phase)

    def publish(temporary: Path, destination: Path) -> None:
        original_publish(temporary, destination)
        if phase == "backup-linked" and destination.suffix == ".sqlite3":
            pause(phase)
        if phase == "marker-linked" and destination.name.endswith(".verified.json"):
            pause(phase)

    def connect(target: str) -> sqlite3.Connection:
        connection = sqlite3.connect(target, factory=CrashConnection, timeout=1)
        connection.phase = phase
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    database_recovery._flush_file = flush_file
    database_recovery._publish = publish
    store_schema.initialize_database(str(path), connect=connect)
    raise AssertionError(f"Storage did not reach the requested boundary: {phase}")


if __name__ == "__main__":
    main()
