"""Regression coverage for non-creating, side-effect-free path readers."""

from __future__ import annotations

import ast
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

import pytest

import researchassistant.storage.store as store
from researchassistant.contracts.models import CheckpointStatus, OrchestrationCheckpoint
from researchassistant.research.fixture_pipeline import FixturePipelineResult, run_fixture_pipeline
from researchassistant.storage import store_schema
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    DatabaseCompatibilityIssue,
    init_db,
    list_runs,
    read_orchestration_checkpoint,
    read_run,
    read_snapshot,
    upsert_orchestration_checkpoint,
)

_ROOT = Path(__file__).resolve().parents[1]
_VALID = _ROOT / "tests" / "fixtures" / "basic_valid_run"


@pytest.fixture(scope="module")
def offline_run(tmp_path_factory: pytest.TempPathFactory) -> FixturePipelineResult:
    result = run_fixture_pipeline(_VALID, output_dir=tmp_path_factory.mktemp("reader-run"))
    upsert_orchestration_checkpoint(
        result.db_path,
        OrchestrationCheckpoint(
            run_id=result.run_id,
            stage_key="phase3-reader-checkpoint",
            status=CheckpointStatus.COMPLETED,
            failure_reason=None,
            updated_at=result.planner_output.planned_at,
        ),
    )
    return result


@pytest.mark.parametrize(
    ("reader", "args"),
    [
        (read_run, (uuid4(),)),
        (list_runs, ()),
        (read_snapshot, (uuid4(),)),
        (read_orchestration_checkpoint, (uuid4(), "missing")),
    ],
)
def test_path_readers_leave_missing_files_absent(
    reader: Callable[..., object], args: tuple[object, ...], tmp_path: Path
) -> None:
    missing = tmp_path / "missing read-only.sqlite3"
    with pytest.raises(DatabaseCompatibilityError) as caught:
        reader(missing, *args)
    assert caught.value.result.issue is DatabaseCompatibilityIssue.MISSING_FILE
    assert not missing.exists()


def test_shared_and_direct_readers_are_byte_and_mtime_stable(
    offline_run: FixturePipelineResult,
) -> None:
    path = Path(offline_run.db_path)
    candidate = offline_run.candidates[0]
    stage_key = "phase3-reader-checkpoint"
    before = path.read_bytes(), path.stat().st_mtime_ns

    assert read_run(path, offline_run.run_id).run_id == offline_run.run_id
    assert list_runs(path)[0].run_id == offline_run.run_id
    assert read_snapshot(path, candidate.snapshot_id).snapshot_id == candidate.snapshot_id
    assert read_orchestration_checkpoint(path, offline_run.run_id, stage_key).stage_key == stage_key
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_readers_encode_uri_sensitive_path_characters(
    offline_run: FixturePipelineResult, tmp_path: Path
) -> None:
    source = Path(offline_run.db_path)
    odd_path = tmp_path / "reader # percent% question?.sqlite3"
    odd_path.write_bytes(source.read_bytes())

    assert read_run(odd_path, offline_run.run_id).run_id == offline_run.run_id
    assert list_runs(odd_path)[0].run_id == offline_run.run_id
    assert read_snapshot(odd_path, offline_run.candidates[0].snapshot_id).snapshot_id
    assert (
        read_orchestration_checkpoint(
            odd_path, offline_run.run_id, "phase3-reader-checkpoint"
        ).stage_key
        == "phase3-reader-checkpoint"
    )


@pytest.mark.parametrize("named_rows", [False, True])
def test_caller_owned_connection_is_reused_without_close_commit_or_pragma_changes(
    offline_run: FixturePipelineResult,
    named_rows: bool,
) -> None:
    connection = sqlite3.connect(offline_run.db_path)
    try:
        if named_rows:
            connection.row_factory = sqlite3.Row
        original_factory = connection.row_factory
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA query_only = OFF")
        connection.execute("BEGIN")
        assert connection.in_transaction

        assert read_run(connection, offline_run.run_id).run_id == offline_run.run_id
        assert list_runs(connection)[0].run_id == offline_run.run_id
        assert (
            read_snapshot(connection, offline_run.candidates[0].snapshot_id).snapshot_id
            == offline_run.candidates[0].snapshot_id
        )
        assert (
            read_orchestration_checkpoint(
                connection, offline_run.run_id, "phase3-reader-checkpoint"
            ).stage_key
            == "phase3-reader-checkpoint"
        )

        assert connection.in_transaction
        assert connection.row_factory is original_factory
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 0
        connection.execute("SELECT 1")
    finally:
        connection.close()


def test_path_connection_closes_even_when_projection_raises(
    offline_run: FixturePipelineResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect

    def track_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(store.sqlite3, "connect", track_connect)
    with pytest.raises(KeyError, match="not found"):
        read_run(offline_run.db_path, uuid4())
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        opened[0].execute("SELECT 1")


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("directory", DatabaseCompatibilityIssue.OPEN_FAILED),
        ("malformed", DatabaseCompatibilityIssue.INVALID_SQLITE),
        ("old", DatabaseCompatibilityIssue.OLDER_SCHEMA),
        ("future", DatabaseCompatibilityIssue.NEWER_SCHEMA),
    ],
)
def test_public_inspection_boundary_reports_typed_open_and_schema_errors(
    kind: str, expected: DatabaseCompatibilityIssue, tmp_path: Path
) -> None:
    path = tmp_path / f"{kind}.sqlite3"
    if kind == "directory":
        path.mkdir()
    elif kind == "malformed":
        path.write_bytes(b"not a sqlite database")
    elif kind == "old":
        with closing(sqlite3.connect(path)) as connection:
            connection.row_factory = sqlite3.Row
            store_schema._initialize_schema(connection, target_version=6)
    else:
        init_db(str(path))
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO schema_migrations VALUES (99, 'future', '2026-10-04')")

    with pytest.raises(DatabaseCompatibilityError) as caught:
        store.open_read_only_store(path)
    assert caught.value.result.issue is expected


def test_low_level_readers_reject_unsupported_source_types_without_stringifying(
    tmp_path: Path,
) -> None:
    unexpected = object()
    path = tmp_path / str(unexpected)
    with pytest.raises(TypeError):
        read_run(unexpected, uuid4())  # type: ignore[arg-type]
    assert not path.exists()


@pytest.mark.parametrize(
    "opening_error",
    [
        PermissionError("permission denied"),
        sqlite3.OperationalError("unable to open database file"),
    ],
)
def test_sqlite_open_failures_become_typed_errors_without_changing_the_file(
    opening_error: BaseException, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "existing.sqlite3"
    init_db(str(path))
    before = path.read_bytes(), path.stat().st_mtime_ns

    def fail_connect(*args: object, **kwargs: object) -> NoReturn:
        raise opening_error

    monkeypatch.setattr(store.sqlite3, "connect", fail_connect)
    with pytest.raises(DatabaseCompatibilityError) as caught:
        read_run(path, uuid4())

    assert caught.value.result.issue is DatabaseCompatibilityIssue.OPEN_FAILED
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_every_path_based_store_reader_uses_the_shared_read_boundary() -> None:
    source = Path(store.__file__).read_text(encoding="utf-8")
    module = ast.parse(source)
    readers = {
        node.name: node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and (node.name.startswith("read_") or node.name == "list_runs")
    }
    assert readers
    bypassing = [
        name
        for name, function in readers.items()
        if not any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_read_connection"
            for call in ast.walk(function)
        )
    ]
    assert bypassing == []
