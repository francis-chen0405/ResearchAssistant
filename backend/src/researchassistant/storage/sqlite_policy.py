"""Bounded SQLite contention policy; never replay an application operation."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

BUSY_TIMEOUT_MS = 1000


def is_busy_error(exc: BaseException) -> bool:
    """Use SQLite result codes, including extended BUSY/LOCKED codes."""
    code = getattr(exc, "sqlite_errorcode", None)
    return isinstance(code, int) and (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


class DatabaseBusyError(sqlite3.OperationalError):
    """A bounded wait expired; the caller may retry an inspection request."""

    retryable = True


class PolicyConnection(sqlite3.Connection):
    """Add a clear error without retrying writes, reservations or provider work."""

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        try:
            return super().execute(sql, parameters)
        except sqlite3.Error as exc:
            self._raise_contention(exc)
            raise

    def executemany(self, sql: str, parameters: Iterable[Sequence[Any]]) -> sqlite3.Cursor:
        try:
            return super().executemany(sql, parameters)
        except sqlite3.Error as exc:
            self._raise_contention(exc)
            raise

    def commit(self) -> None:
        try:
            super().commit()
        except sqlite3.Error as exc:
            self._raise_contention(exc)
            raise

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        try:
            return super().executescript(sql_script)
        except sqlite3.Error as exc:
            self._raise_contention(exc)
            raise

    @staticmethod
    def _raise_contention(exc: sqlite3.Error) -> None:
        if is_busy_error(exc):
            error = DatabaseBusyError(
                "Database is busy; the bounded wait expired. Retry inspection shortly. "
                "No application operation was replayed."
            )
            error.sqlite_errorcode = exc.sqlite_errorcode
            error.sqlite_errorname = exc.sqlite_errorname
            raise error from exc


def connect_database(path: str, *, uri: bool = False) -> sqlite3.Connection:
    return sqlite3.connect(path, uri=uri, timeout=BUSY_TIMEOUT_MS / 1000, factory=PolicyConnection)
