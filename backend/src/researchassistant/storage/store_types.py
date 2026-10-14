"""Shared persistence types, exact row decoding primitives and read cursor ownership."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, closing
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from researchassistant.contracts.models import SegmentOffset, StrictModel


class DatabaseCompatibilityIssue(StrEnum):
    MISSING_FILE = "missing_file"
    INVALID_SQLITE = "invalid_sqlite"
    OLDER_SCHEMA = "older_schema"
    NEWER_SCHEMA = "newer_schema"
    CORRUPT_SCHEMA = "corrupt_schema"
    OPEN_FAILED = "open_failed"
    BUSY = "busy"


class DatabaseCompatibilityResult(StrictModel):
    compatible: bool
    issue: DatabaseCompatibilityIssue | None = None
    schema_version: int | None = None
    message: str
    retryable: bool = False


class DatabaseCompatibilityError(RuntimeError):
    """An inspection database cannot be opened without modifying it."""

    def __init__(self, result: DatabaseCompatibilityResult) -> None:
        self.result = result
        super().__init__(result.message)


DatabaseReader = str | Path | sqlite3.Connection


class _ReadRows:
    """Detached results: readers cannot leave SQLite cursors alive after a query."""

    def __init__(self, rows: list[sqlite3.Row]) -> None:
        self.rows = rows

    def fetchone(self) -> sqlite3.Row | None:
        return self.rows.pop(0) if self.rows else None

    def fetchall(self) -> list[sqlite3.Row]:
        rows, self.rows = self.rows, []
        return rows


def _read_execute(
    conn: sqlite3.Connection,
    sql: str,
    parameters: Sequence[object] = (),
) -> _ReadRows:
    """Use named rows without altering a caller-owned connection's row factory."""
    with closing(conn.cursor()) as cursor:
        cursor.row_factory = sqlite3.Row
        cursor.execute(sql, parameters)
        return _ReadRows(cursor.fetchall())


def _compatibility_error(
    issue: DatabaseCompatibilityIssue,
    message: str,
    *,
    schema_version: int | None = None,
) -> DatabaseCompatibilityError:
    return DatabaseCompatibilityError(
        DatabaseCompatibilityResult(
            compatible=False,
            issue=issue,
            schema_version=schema_version,
            message=message,
            retryable=issue is DatabaseCompatibilityIssue.BUSY,
        )
    )


def _dt_to_iso(dt: datetime) -> str:
    """Convert a timezone-aware datetime to an ISO-8601 string."""
    return dt.astimezone(UTC).isoformat()


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    """Reject naive timestamps at a store boundary before SQLite serialization."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _iso_to_dt(value: str) -> datetime:
    """Parse an ISO-8601 string back to a timezone-aware datetime."""
    return datetime.fromisoformat(value)


def _offsets_to_json(offsets: Sequence[SegmentOffset]) -> str:
    return json.dumps([{"start_char": o.start_char, "end_char": o.end_char} for o in offsets])


def _json_to_offsets(raw: str) -> list[SegmentOffset]:
    return [
        SegmentOffset(start_char=d["start_char"], end_char=d["end_char"]) for d in json.loads(raw)
    ]


# Preserve the historical public class identity for persisted consumers.
DatabaseCompatibilityIssue.__module__ = "researchassistant.storage.store"
DatabaseCompatibilityResult.__module__ = "researchassistant.storage.store"
DatabaseCompatibilityError.__module__ = "researchassistant.storage.store"
_ReadRows.__module__ = "researchassistant.storage.store"


WriteConnectionFactory = Callable[[str], sqlite3.Connection]
ReadConnectionFactory = Callable[[DatabaseReader], AbstractContextManager[sqlite3.Connection]]
