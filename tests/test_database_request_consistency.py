"""Public request coherence and bounded writer contention on disposable data."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import frontend.live_history as live_history
from frontend.api import _inspection_http_error
from providers.v2_budget import V2BudgetSnapshot
from researchassistant.contracts.models import RunManifest, RunStatus, Stage, V2PipelineIdentity
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
)
from researchassistant.storage.sqlite_policy import DatabaseBusyError
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    _connect,
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    open_read_only_store,
)


def test_history_manifest_and_terminal_projection_share_one_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "history.sqlite3"
    init_db(str(database))
    now = datetime(2026, 10, 4, tzinfo=UTC)
    run_id = uuid4()
    insert_run(
        str(database),
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim="Isolated request coherence",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=now,
            updated_at=now,
        ),
    )
    insert_v2_pipeline_identity(str(database), run_id, V2PipelineIdentity(), now)
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
    terminal = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=str(database),
        raw_claim="Isolated request coherence",
        state=V2ProductionState.FAILED,
        current_stage=Stage.CLAIM_PLANNER,
        failure_reason="Offline fixture",
        budget=V2BudgetSnapshot(
            physical_calls_used=0,
            token_exposure=0,
            cost_exposure_usd=0,
            physical_calls_remaining=10,
            tokens_remaining=1000,
            cost_remaining_usd=1,
        ),
        completed_at=now,
    )
    original_list = live_history.list_runs

    def commit_after_manifests(
        source: sqlite3.Connection, *, limit: int = 100
    ) -> list[RunManifest]:
        manifests = original_list(source, limit=limit)
        insert_v2_artifact(str(database), V2_PRODUCTION_ARTIFACT_KEY, terminal, now)
        return manifests

    with monkeypatch.context() as scoped:
        scoped.setattr(live_history, "list_runs", commit_after_manifests)
        assert live_history.history(database)[0].status == "planned"
    assert live_history.history(database)[0].status == "failed"


def test_writer_timeout_does_not_replay_or_disguise_contention(tmp_path: Path) -> None:
    database = tmp_path / "writer.sqlite3"
    init_db(str(database))
    blocker = sqlite3.connect(database)
    writer = _connect(str(database))
    try:
        assert writer.execute("PRAGMA busy_timeout").fetchone()[0] == 1000
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(DatabaseBusyError) as caught:
            writer.execute("BEGIN IMMEDIATE")
        assert caught.value.retryable
        assert not writer.in_transaction
        assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    finally:
        blocker.rollback()
        blocker.close()
        writer.close()


def test_api_contention_is_retryable_and_next_request_recovers(tmp_path: Path) -> None:
    database = tmp_path / "api-busy.sqlite3"
    init_db(str(database))
    blocker = sqlite3.connect(database)
    try:
        blocker.execute("BEGIN EXCLUSIVE")
        with pytest.raises(DatabaseCompatibilityError) as caught:
            open_read_only_store(database)
        error = _inspection_http_error(caught.value)
        assert error.status_code == 503
        assert error.headers == {"Retry-After": "1"}
        assert error.detail["issue"] == "busy"
        assert error.detail["retryable"] is True
    finally:
        blocker.rollback()
        blocker.close()
    with open_read_only_store(database) as reader:
        with pytest.raises(KeyError):
            reader.read_run(UUID(int=1))


def test_interrupted_validation_closes_local_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import researchassistant.storage.store as store

    database = tmp_path / "interrupted.sqlite3"
    init_db(str(database))
    opened: list[sqlite3.Connection] = []
    original = store._open_read_connection

    def tracked(path: str | Path) -> sqlite3.Connection:
        connection = original(path)
        opened.append(connection)
        return connection

    def interrupted(connection: sqlite3.Connection) -> None:
        assert connection.in_transaction
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "_open_read_connection", tracked)
    monkeypatch.setattr(store, "_validate_read_only_schema", interrupted)
    with pytest.raises(KeyboardInterrupt):
        open_read_only_store(database)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
