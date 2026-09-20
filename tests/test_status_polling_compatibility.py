"""Status inspection preserves read-only failure and session lifecycle contracts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import frontend.live_service as live_service
from store import (
    RAW_CLAIM_TRIGGER_NAME,
    DatabaseCompatibilityError,
    DatabaseCompatibilityIssue,
    ReadOnlyStore,
    init_db,
)


@pytest.mark.parametrize(
    "issue",
    [
        DatabaseCompatibilityIssue.INVALID_SQLITE,
        DatabaseCompatibilityIssue.OLDER_SCHEMA,
        DatabaseCompatibilityIssue.NEWER_SCHEMA,
        DatabaseCompatibilityIssue.CORRUPT_SCHEMA,
    ],
)
def test_snapshot_rejects_incompatible_database_without_changes(
    tmp_path: Path, issue: DatabaseCompatibilityIssue
) -> None:
    path = tmp_path / "incompatible.sqlite3"
    if issue is DatabaseCompatibilityIssue.INVALID_SQLITE:
        path.write_bytes(b"not a SQLite database\x00")
    else:
        init_db(str(path))
        with sqlite3.connect(path) as connection:
            if issue is DatabaseCompatibilityIssue.OLDER_SCHEMA:
                connection.execute("DELETE FROM schema_migrations")
            elif issue is DatabaseCompatibilityIssue.NEWER_SCHEMA:
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (99, 'future', '2026-09-19')"
                )
            else:
                connection.execute(f'DROP TRIGGER "{RAW_CLAIM_TRIGGER_NAME}"')
    before = path.read_bytes(), path.stat().st_mtime_ns
    controller = live_service.LiveResearchController(environment={})

    with pytest.raises(DatabaseCompatibilityError) as caught:
        controller.snapshot(path, uuid4())

    assert caught.value.result.issue is issue
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert not path.with_name(path.name + "-journal").exists()


def test_missing_snapshot_does_not_create_database(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(KeyError, match="not found"):
        live_service.LiveResearchController(environment={}).snapshot(path, uuid4())
    assert not path.exists()


def test_snapshot_revalidates_replaced_database(tmp_path: Path) -> None:
    path = tmp_path / "replaceable.sqlite3"
    init_db(str(path))
    controller = live_service.LiveResearchController(environment={})
    run_id = uuid4()
    with pytest.raises(KeyError, match="not found"):
        controller.snapshot(path, run_id)
    replacement = tmp_path / "replacement.sqlite3"
    replacement.write_bytes(b"replacement is not a database")
    replacement.replace(path)
    before = path.read_bytes(), path.stat().st_mtime_ns

    with pytest.raises(DatabaseCompatibilityError) as caught:
        controller.snapshot(path, run_id)

    assert caught.value.result.issue is DatabaseCompatibilityIssue.INVALID_SQLITE
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_snapshot_closes_read_session_after_projection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "projection-error.sqlite3"
    init_db(str(path))
    connections: list[sqlite3.Connection] = []
    original_open = live_service.open_read_only_store

    def tracked_open(db_path: str | Path) -> ReadOnlyStore:
        reader = original_open(db_path)
        connections.append(reader.connection)
        return reader

    def failed_projection(
        source: str | Path | sqlite3.Connection,
        run_id: UUID,
        artifact_keys: tuple[str, ...],
    ) -> None:
        assert source is connections[0]
        raise RuntimeError("injected projection error")

    monkeypatch.setattr(live_service, "open_read_only_store", tracked_open)
    monkeypatch.setattr(live_service, "_read_first_v2_artifact", failed_projection)
    before = path.read_bytes(), path.stat().st_mtime_ns
    with pytest.raises(RuntimeError, match="injected projection error"):
        live_service.LiveResearchController(environment={}).snapshot(path, uuid4())
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connections[0].execute("SELECT 1")
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
