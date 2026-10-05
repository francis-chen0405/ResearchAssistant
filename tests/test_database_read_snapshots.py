"""Regression tests for transaction ownership and coherent read snapshots."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn
from uuid import UUID, uuid4

import pytest

import researchassistant.storage.store as store
from researchassistant.contracts.models import RunManifest, RunStatus, Stage
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    DatabaseCompatibilityIssue,
    DatabaseCompatibilityResult,
    init_db,
    insert_run,
    open_read_only_store,
    read_run,
)


def _manifest(run_id: UUID | None = None) -> RunManifest:
    now = datetime.now(UTC)
    return RunManifest(
        run_id=run_id or uuid4(),
        status=RunStatus.PLANNED,
        raw_claim="Snapshot test claim",
        current_stage=Stage.CLAIM_PLANNER,
        created_at=now,
        updated_at=now,
    )


def _create_marker_database(path: Path, *, journal_mode: str) -> None:
    init_db(str(path))
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA journal_mode = {journal_mode}")
        connection.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES ('before')")


@pytest.mark.parametrize("failure", [False, True])
def test_snapshot_context_finishes_only_its_owned_transaction(
    failure: bool,
) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE values_seen(value TEXT NOT NULL)")
    try:
        if failure:
            with pytest.raises(RuntimeError, match="abort snapshot"):
                with store.read_snapshot_connection(connection):
                    connection.execute("INSERT INTO values_seen VALUES ('local')")
                    raise RuntimeError("abort snapshot")
            assert not connection.in_transaction
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 0
        else:
            with store.read_snapshot_connection(connection):
                connection.execute("INSERT INTO values_seen VALUES ('local')")
            assert not connection.in_transaction
            assert connection.execute("SELECT value FROM values_seen").fetchone()[0] == "local"
    finally:
        connection.close()


@pytest.mark.parametrize("failure", [False, True])
def test_nested_snapshot_preserves_callers_transaction_and_rollback(failure: bool) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE values_seen(value TEXT NOT NULL)")
    connection.execute("BEGIN")
    connection.execute("INSERT INTO values_seen VALUES ('caller')")
    try:
        if failure:
            with pytest.raises(RuntimeError, match="abort nested snapshot"):
                with store.read_snapshot_connection(connection):
                    with store.read_snapshot_connection(connection):
                        connection.execute("INSERT INTO values_seen VALUES ('nested')")
                        raise RuntimeError("abort nested snapshot")
            assert connection.in_transaction
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 2
            connection.rollback()
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 0
        else:
            with store.read_snapshot_connection(connection):
                with store.read_snapshot_connection(connection):
                    connection.execute("INSERT INTO values_seen VALUES ('nested')")
            assert connection.in_transaction
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 2
            connection.rollback()
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 0
    finally:
        connection.close()


@pytest.mark.skipif(
    not hasattr(sqlite3.Connection, "autocommit"),
    reason="sqlite3.Connection.autocommit requires Python 3.12",
)
@pytest.mark.parametrize("failure", [False, True])
def test_owned_snapshot_explicitly_finishes_autocommit_mode_transaction(
    failure: bool,
) -> None:
    connection = sqlite3.connect(":memory:", autocommit=True)
    connection.execute("CREATE TABLE values_seen(value TEXT NOT NULL)")
    try:
        if failure:
            with pytest.raises(RuntimeError, match="abort autocommit snapshot"):
                with store.read_snapshot_connection(connection):
                    connection.execute("INSERT INTO values_seen VALUES ('local')")
                    raise RuntimeError("abort autocommit snapshot")
            assert not connection.in_transaction
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 0
        else:
            with store.read_snapshot_connection(connection):
                connection.execute("INSERT INTO values_seen VALUES ('local')")
            assert not connection.in_transaction
            assert connection.execute("SELECT value FROM values_seen").fetchone()[0] == "local"
    finally:
        connection.close()


@pytest.mark.skipif(
    not hasattr(sqlite3.Connection, "autocommit"),
    reason="sqlite3.Connection.autocommit requires Python 3.12",
)
@pytest.mark.parametrize("failure", [False, True])
def test_autocommit_mode_nested_snapshot_preserves_manual_caller_transaction(
    failure: bool,
) -> None:
    connection = sqlite3.connect(":memory:", autocommit=True)
    connection.execute("CREATE TABLE values_seen(value TEXT NOT NULL)")
    connection.execute("BEGIN")
    connection.execute("INSERT INTO values_seen VALUES ('caller')")
    try:
        if failure:
            with pytest.raises(RuntimeError, match="abort autocommit nested snapshot"):
                with store.read_snapshot_connection(connection):
                    with store.read_snapshot_connection(connection):
                        connection.execute("INSERT INTO values_seen VALUES ('nested')")
                        raise RuntimeError("abort autocommit nested snapshot")
            assert connection.in_transaction
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 2
        else:
            with store.read_snapshot_connection(connection):
                with store.read_snapshot_connection(connection):
                    connection.execute("INSERT INTO values_seen VALUES ('nested')")
            assert connection.in_transaction
            assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 2
        connection.execute("ROLLBACK")
        assert not connection.in_transaction
        assert connection.execute("SELECT count(*) FROM values_seen").fetchone()[0] == 0
    finally:
        connection.close()


@pytest.mark.parametrize("journal_mode", ["DELETE", "WAL"])
def test_read_snapshot_is_stable_across_a_concurrent_writer(
    tmp_path: Path, journal_mode: str
) -> None:
    path = tmp_path / f"coherent-{journal_mode.lower()}.sqlite3"
    _create_marker_database(path, journal_mode=journal_mode)
    reader = sqlite3.connect(path, timeout=0.1)
    writer = sqlite3.connect(path, timeout=0.1)
    try:
        with store.read_snapshot_connection(reader):
            assert reader.execute("SELECT value FROM marker").fetchone()[0] == "before"
            writer.execute("UPDATE marker SET value = 'after'")
            if journal_mode == "WAL":
                writer.commit()
            else:
                # Rollback-journal readers hold a shared lock until the snapshot ends.
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    writer.commit()
                writer.rollback()
            assert reader.execute("SELECT value FROM marker").fetchone()[0] == "before"
        writer.execute("UPDATE marker SET value = 'after'")
        writer.commit()
        with store.read_snapshot_connection(reader):
            assert reader.execute("SELECT value FROM marker").fetchone()[0] == "after"
    finally:
        reader.close()
        writer.close()


def test_read_only_store_starts_snapshot_before_validation_and_releases_on_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "validation-snapshot.sqlite3"
    _create_marker_database(path, journal_mode="WAL")
    original_validate = store._validate_read_only_schema

    def validate_then_commit_writer(
        connection: sqlite3.Connection,
    ) -> DatabaseCompatibilityResult:
        result = original_validate(connection)
        assert connection.in_transaction
        with sqlite3.connect(path) as writer:
            writer.execute("UPDATE marker SET value = 'after-validation'")
        return result

    monkeypatch.setattr(store, "_validate_read_only_schema", validate_then_commit_writer)
    with open_read_only_store(path) as reader:
        assert reader.connection.in_transaction
        assert reader.connection.execute("SELECT value FROM marker").fetchone()[0] == "before"
    with sqlite3.connect(path) as writer:
        assert writer.execute("SELECT value FROM marker").fetchone()[0] == "after-validation"


def test_read_only_store_closes_connection_when_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "validation-failure.sqlite3"
    init_db(str(path))
    opened: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect

    def track_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    def fail_validation(connection: sqlite3.Connection) -> NoReturn:
        assert connection.in_transaction
        raise store._compatibility_error(
            DatabaseCompatibilityIssue.CORRUPT_SCHEMA, "synthetic validation failure"
        )

    monkeypatch.setattr(store.sqlite3, "connect", track_connect)
    monkeypatch.setattr(store, "_validate_read_only_schema", fail_validation)
    with pytest.raises(DatabaseCompatibilityError, match="synthetic validation failure"):
        open_read_only_store(path)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        opened[0].execute("SELECT 1")


def test_transient_read_contention_is_typed_as_busy_and_corruption_stays_distinct(
    tmp_path: Path,
) -> None:
    path = tmp_path / "busy-reader.sqlite3"
    init_db(str(path))
    run = _manifest()
    insert_run(str(path), run)
    blocker = sqlite3.connect(path, timeout=0)
    blocker.execute("BEGIN EXCLUSIVE")
    started = time.monotonic()
    try:
        with pytest.raises(DatabaseCompatibilityError) as caught:
            read_run(path, run.run_id)
        assert caught.value.result.issue is DatabaseCompatibilityIssue.BUSY
        assert caught.value.result.retryable is True
        assert time.monotonic() - started < 3
    finally:
        blocker.rollback()
        blocker.close()

    malformed = tmp_path / "corrupt-reader.sqlite3"
    malformed.write_bytes(b"not a sqlite database")
    with pytest.raises(DatabaseCompatibilityError) as corrupt:
        open_read_only_store(malformed)
    assert corrupt.value.result.issue is DatabaseCompatibilityIssue.INVALID_SQLITE


def test_replaced_database_at_same_path_is_revalidated_on_next_request(tmp_path: Path) -> None:
    target = tmp_path / "replace-me.sqlite3"
    replacement = tmp_path / "replacement.sqlite3"
    init_db(str(target))
    init_db(str(replacement))
    old_run = _manifest()
    new_run = _manifest()
    insert_run(str(target), old_run)
    insert_run(str(replacement), new_run)

    with open_read_only_store(target) as before:
        assert before.read_run(old_run.run_id).run_id == old_run.run_id
    os.replace(replacement, target)
    with open_read_only_store(target) as after:
        assert after.read_run(new_run.run_id).run_id == new_run.run_id
        with pytest.raises(KeyError, match="not found"):
            after.read_run(old_run.run_id)
