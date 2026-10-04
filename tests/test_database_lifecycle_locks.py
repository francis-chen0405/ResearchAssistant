from __future__ import annotations

import queue
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from stat import S_IMODE
from threading import Event, Thread
from uuid import UUID, uuid4

import pytest

import frontend.live_service as live_service
import researchassistant.research.orchestrator as orchestrator
import researchassistant.research.v2_orchestrator as v2_orchestrator
import researchassistant.storage.database_lock as database_lock_module
import researchassistant.storage.history_import as history_import_module
import researchassistant.storage.store_schema as store_schema
from frontend.live_contracts import LiveRunRequest
from researchassistant.contracts.models import (
    RunManifest,
    RunStatus,
    Stage,
)
from researchassistant.platform_support.file_lock import FileLock
from researchassistant.storage.database_lock import database_lock, retained_database_lock
from researchassistant.storage.store import (
    init_db,
    insert_run,
    read_cancellation_request,
)

_MIGRATIONS = (
    store_schema._apply_raw_claim_immutability_migration,
    store_schema._apply_mvp68_integrity_migration,
    store_schema._apply_mvp69_provenance_migration,
    store_schema._apply_mvp10_evidence_portfolio_migration,
    store_schema._apply_mvp11_research_governor_migration,
    store_schema._apply_mlp4_discovery_query_migration,
    store_schema._apply_v2_phase1_artifact_migration,
    store_schema._apply_v2_phase3_initial_planner_migration,
    store_schema._apply_v2_phase10_reviewer_ledger_migration,
    store_schema._apply_cache_usage_migration,
    store_schema._apply_complete_usage_migration,
    store_schema._apply_update_provenance_migration,
)


def _environment() -> dict[str, str]:
    return {
        "MIMO_API_KEY": "lifecycle-test-mimo",
        "MIMO_BASE_URL": "https://mimo.example.test/v1",
        "MIMO_MODEL": "mimo-v2.5-pro",
        "MIMO_V25_MODEL": "mimo-v2.5",
        "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
        "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
        "MIMO_V25_PRO_MODEL": "mimo-v2.5-pro",
        "MIMO_V25_PRO_INPUT_USD_PER_TOKEN": "0.000001",
        "MIMO_V25_PRO_OUTPUT_USD_PER_TOKEN": "0.000002",
        "EXA_API_KEY": "lifecycle-test-exa",
        "OPENALEX_API_KEY": "lifecycle-test-openalex",
    }


def _request(database: Path, run_id: UUID) -> LiveRunRequest:
    return LiveRunRequest(
        raw_claim="A stable cancellation test claim.",
        db_path=str(database),
        run_id=run_id,
        max_tokens=100_000,
        max_cost_usd="0.20",
        research_controls={"discovery_providers": ["exa", "openalex"]},
    )


def _legacy_result(
    db_path: str | Path, run_id: UUID, raw_claim: str
) -> orchestrator.ProviderPipelineResult:
    return orchestrator.ProviderPipelineResult(
        run_id=run_id,
        status=orchestrator.ProviderRunStatus.FAILED,
        raw_claim=raw_claim,
        db_path=str(db_path),
        current_stage=Stage.CLAIM_PLANNER,
        failure_reason="offline lifecycle test result",
    )


@contextmanager
def _external_database_lock(database: Path) -> Iterator[subprocess.Popen[str]]:
    child_code = """
from pathlib import Path
import sys
from researchassistant.platform_support.file_lock import FileLock

def main() -> int:
    lock = FileLock(Path(sys.argv[1]).with_name(Path(sys.argv[1]).name + '.mvp5.lock'))
    if not lock.acquire(blocking=True):
        return 2
    print('LOCKED', flush=True)
    sys.stdin.readline()
    lock.release()
    return 0

raise SystemExit(main())
"""
    process = subprocess.Popen(
        [sys.executable, "-c", child_code, str(database)],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    ready: queue.Queue[str] = queue.Queue()
    reader = Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True)
    reader.start()
    try:
        line = ready.get(timeout=10)
        assert line.strip() == "LOCKED"
        yield process
    finally:
        if process.poll() is None:
            if process.stdin is not None:
                process.stdin.write("release\n")
                process.stdin.flush()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        reader.join(timeout=1)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def test_subprocess_database_lock_excludes_init_import_and_legacy_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "shared.sqlite3"
    init_db(str(database))
    legacy_calls: list[object] = []

    def unexpected_legacy_call(
        *args: object, **kwargs: object
    ) -> orchestrator.ProviderPipelineResult:
        legacy_calls.append((args, kwargs))
        raise AssertionError(
            "the legacy write body must not start while another process owns the lock"
        )

    monkeypatch.setattr(orchestrator, "_run_provider_pipeline", unexpected_legacy_call)
    with _external_database_lock(database):
        with pytest.raises(RuntimeError, match="busy"):
            init_db(str(database))
        with pytest.raises(ValueError, match="active research"):
            history_import_module.import_history(database, destination_dir=tmp_path / "imports")
        with pytest.raises(RuntimeError, match="busy"):
            orchestrator.run_provider_pipeline(
                "A lock contention claim.",
                db_path=database,
                search_provider=object(),
                scraper_provider=object(),
                llm_provider=object(),
            )
    assert legacy_calls == []


def test_init_db_uses_retained_and_explicit_lock_ownership_without_reacquiring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "owned.sqlite3"
    acquire_count = 0

    class CountingFileLock(FileLock):
        def acquire(self, *, blocking: bool = False) -> bool:
            nonlocal acquire_count
            acquire_count += 1
            return super().acquire(blocking=blocking)

    monkeypatch.setattr(database_lock_module, "FileLock", CountingFileLock)
    with database_lock(database):
        init_db(str(database))
        init_db(str(database), lock_owned=True)
    assert acquire_count == 1

    with retained_database_lock(database):
        init_db(str(database))
    assert acquire_count == 1


def test_v2_database_lock_creates_missing_parent_without_chmodding_existing_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing_parent = tmp_path / "existing-parent"
    existing_parent.mkdir(mode=0o751)
    existing_parent.chmod(0o751)
    original_mode = S_IMODE(existing_parent.stat().st_mode)
    database = existing_parent / "new" / "nested" / "research.sqlite3"
    acquire_count = 0

    class CountingFileLock(FileLock):
        def acquire(self, *, blocking: bool = False) -> bool:
            nonlocal acquire_count
            acquire_count += 1
            return super().acquire(blocking=blocking)

    monkeypatch.setattr(database_lock_module, "FileLock", CountingFileLock)
    with v2_orchestrator._v2_database_lock(database):
        init_db(str(database))

    assert database.is_file()
    assert acquire_count == 1
    assert S_IMODE(existing_parent.stat().st_mode) == original_mode


def test_direct_legacy_run_retains_shared_lock_until_write_scope_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "direct-legacy.sqlite3"
    init_db(str(database))
    entered = Event()
    release = Event()
    result_run_id = uuid4()

    def blocking_write(raw_claim: str, **kwargs: object) -> orchestrator.ProviderPipelineResult:
        init_db(str(kwargs["db_path"]))
        entered.set()
        assert release.wait(5), "test did not release the simulated legacy write"
        return _legacy_result(kwargs["db_path"], result_run_id, raw_claim)

    monkeypatch.setattr(orchestrator, "_run_provider_pipeline", blocking_write)
    errors: list[BaseException] = []

    def run_legacy() -> None:
        try:
            orchestrator.run_provider_pipeline(
                "A direct legacy run.",
                db_path=database,
                search_provider=object(),
                scraper_provider=object(),
                llm_provider=object(),
                run_id=result_run_id,
            )
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=run_legacy)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(ValueError, match="active research"):
            history_import_module.import_history(database, destination_dir=tmp_path / "imports")
    finally:
        release.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert errors == []
    imported = history_import_module.import_history(database, destination_dir=tmp_path / "imports")
    assert Path(imported.db_path).is_file()


def test_live_legacy_cancellation_keeps_import_blocked_through_timed_out_shutdown(
    tmp_path: Path,
) -> None:
    database = tmp_path / "live-legacy.sqlite3"
    init_db(str(database))
    run_id = uuid4()
    now = datetime.now(UTC)
    insert_run(
        str(database),
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="A stable cancellation test claim.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=now,
            updated_at=now,
        ),
    )
    entered = Event()
    release = Event()

    def legacy_runner(raw_claim: str, **kwargs: object) -> orchestrator.ProviderPipelineResult:
        init_db(str(kwargs["db_path"]))
        entered.set()
        assert release.wait(5), "test did not release the simulated live legacy run"
        return _legacy_result(kwargs["db_path"], UUID(str(kwargs["run_id"])), raw_claim)

    controller = live_service.LiveResearchController(
        environment=_environment(), legacy_runner=legacy_runner
    )
    try:
        start = controller.start(_request(database, run_id))
        assert start.started
        assert entered.wait(5)
        controller.cancel(database, run_id)
        assert read_cancellation_request(str(database), run_id).run_id == run_id
        assert controller.shutdown(timeout=0.01) is False
        with pytest.raises(ValueError, match="active research"):
            history_import_module.import_history(database, destination_dir=tmp_path / "imports")
    finally:
        release.set()
        if controller.has_active_runs():
            assert controller.shutdown(timeout=5)
    assert not controller.has_active_runs()
    imported = history_import_module.import_history(database, destination_dir=tmp_path / "imports")
    assert Path(imported.db_path).is_file()


def test_cancellation_of_missing_database_does_not_create_it(tmp_path: Path) -> None:
    database = tmp_path / "missing" / "not-created.sqlite3"

    with pytest.raises(ValueError, match="initialized compatible database"):
        orchestrator.request_run_cancellation(database, uuid4())

    assert not database.exists()


def _historical_database(path: Path, version: int, run_id: UUID) -> None:
    original_migrations = {migration.__name__: migration for migration in _MIGRATIONS}
    for name in original_migrations:
        setattr(store_schema, name, lambda _connection: None)
    try:
        connection = sqlite3.connect(path)
        try:
            connection.row_factory = sqlite3.Row
            store_schema._initialize_schema(connection)
        finally:
            connection.close()
    finally:
        for name, migration in original_migrations.items():
            setattr(store_schema, name, migration)

    connection = sqlite3.connect(path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("DELETE FROM schema_migrations WHERE version > ?", (version,))
        connection.commit()
        for migration_version, migration in enumerate(_MIGRATIONS, start=5):
            if migration_version <= version:
                migration(connection)
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(run_id),
                "running",
                "A historical cancellation claim.",
                "claim_planner",
                "2026-10-03T12:00:00+00:00",
                "2026-10-03T12:00:00+00:00",
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize("version", range(7, store_schema.CURRENT_SCHEMA_VERSION + 1))
def test_cancellation_preserves_supported_read_only_schema_versions(
    tmp_path: Path, version: int
) -> None:
    database = tmp_path / f"historical-{version}.sqlite3"
    run_id = uuid4()
    _historical_database(database, version, run_id)

    orchestrator.request_run_cancellation(database, run_id)

    with sqlite3.connect(database) as connection:
        latest_version = connection.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone()[0]
    assert latest_version == version
