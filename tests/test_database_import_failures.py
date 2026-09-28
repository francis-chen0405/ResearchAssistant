from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import history_import as history_import_module
from file_lock import FileLock
from frontend.api import create_app, create_default_runtime
from models import RunManifest, RunStatus, Stage
from store import CURRENT_SCHEMA_VERSION, init_db, insert_run, read_run


def _source_database(path: Path) -> RunManifest:
    init_db(str(path))
    manifest = RunManifest(
        run_id=uuid4(),
        status=RunStatus.RUNNING,
        raw_claim="Import regression claim",
        current_stage=Stage.DISCOVERY,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    insert_run(str(path), manifest)
    return manifest


def test_uuid_collision_preserves_existing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.sqlite3"
    _source_database(source)
    destination_dir = tmp_path / "imports"
    destination_dir.mkdir()
    collision = destination_dir / "history-11111111-1111-1111-1111-111111111111.sqlite3"
    collision.write_bytes(b"preexisting destination bytes")
    monkeypatch.setattr(
        history_import_module, "uuid4", lambda: UUID("11111111-1111-1111-1111-111111111111")
    )

    with pytest.raises(FileExistsError):
        history_import_module.import_history(source, destination_dir=destination_dir)

    assert collision.read_bytes() == b"preexisting destination bytes"


def test_verification_failure_removes_only_created_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.sqlite3"
    manifest = _source_database(source)
    destination_dir = tmp_path / "imports"
    original_read_run = history_import_module.read_run
    calls = 0

    def fail_copied_read(database: sqlite3.Connection, run_id: UUID) -> RunManifest:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("injected verification failure")
        return original_read_run(database, run_id)

    monkeypatch.setattr(history_import_module, "read_run", fail_copied_read)

    with pytest.raises(ValueError, match="injected verification failure"):
        history_import_module.import_history(source, destination_dir=destination_dir)

    assert list(destination_dir.glob("*.sqlite3")) == []
    assert read_run(source, manifest.run_id) == manifest


@pytest.mark.parametrize("source_kind", ["malformed", "older", "newer"])
def test_api_import_compatibility_errors_are_sanitized_422_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_kind: str
) -> None:
    source = tmp_path / f"{source_kind}-private-path.sqlite3"
    if source_kind == "malformed":
        source.write_bytes(b"not sqlite; private source bytes")
    else:
        _source_database(source)
        with sqlite3.connect(source) as connection:
            if source_kind == "older":
                connection.execute("DELETE FROM schema_migrations WHERE version > 6")
            else:
                connection.execute(
                    "INSERT INTO schema_migrations(version, description, applied_at) "
                    "VALUES (?, 'future schema', '2026-09-27T00:00:00+00:00')",
                    (CURRENT_SCHEMA_VERSION + 1,),
                )
    before = source.read_bytes()
    monkeypatch.setenv("RESEARCHASSISTANT_DATA_DIR", str(tmp_path / "app-data"))
    runtime = create_default_runtime()
    app = create_app(runtime, load_keychain_on_start=False, session_token="a" * 64)
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.post(
        "/api/history/import",
        params={"source": str(source)},
        headers={"Authorization": "Bearer " + "a" * 64},
    )

    assert response.status_code == 422
    assert str(source) not in response.text
    assert response.json()["detail"] == (
        "History import failed; check the source database and ensure it is idle."
    )
    assert source.read_bytes() == before
    runtime.controller.shutdown(timeout=0)


def test_api_import_keeps_active_research_conflict_as_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.sqlite3"
    _source_database(source)
    monkeypatch.setenv("RESEARCHASSISTANT_DATA_DIR", str(tmp_path / "app-data"))
    runtime = create_default_runtime()
    monkeypatch.setattr(runtime.controller, "has_active_runs", lambda: True)
    app = create_app(runtime, load_keychain_on_start=False, session_token="b" * 64)
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.post(
        "/api/history/import",
        params={"source": str(source)},
        headers={"Authorization": "Bearer " + "b" * 64},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Wait for active research to finish."
    runtime.controller.shutdown(timeout=0)


def test_import_releases_source_lock_after_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.sqlite3"
    _source_database(source)
    destination_dir = tmp_path / "imports"
    destination_dir.mkdir()
    monkeypatch.setattr(
        history_import_module, "uuid4", lambda: UUID("22222222-2222-2222-2222-222222222222")
    )
    collision = destination_dir / "history-22222222-2222-2222-2222-222222222222.sqlite3"
    collision.write_bytes(b"owned by another import")

    with pytest.raises(FileExistsError):
        history_import_module.import_history(source, destination_dir=destination_dir)

    lock = FileLock(source.with_name(f"{source.name}.mvp5.lock"))
    assert lock.acquire()
    lock.release()
    assert collision.read_bytes() == b"owned by another import"
