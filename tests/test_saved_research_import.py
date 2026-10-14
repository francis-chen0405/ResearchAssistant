from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

import pytest

from evaluations import import_saved_research
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.research_acquisition import V2AcquisitionProbeOutput
from researchassistant.contracts.research_directions import ResearchDirections
from researchassistant.contracts.research_planning import (
    V2InitialPlannerOutput,
    V2InitialPlannerPolicy,
    V2RoundOneSearchQuery,
)
from researchassistant.providers.v2_budget import V2PhysicalCallAudit


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    handoff = json.loads(
        (
            Path(__file__).parents[1]
            / "evaluations/cases/research_quality/fixture_bundle/handoff.json"
        ).read_text()
    )
    run_id = handoff["query"]["run_id"]
    payload = json.dumps(
        {
            "run_id": run_id,
            "completed_at": "2026-10-11T20:00:01Z",
            "outcomes": [{"query": handoff["query"], "results": handoff["results"]}],
        }
    )
    path = tmp_path / "fixture.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE runs (run_id, raw_claim, created_at, completed_at)")
        conn.execute(
            "CREATE TABLE v2_artifacts "
            "(run_id, artifact_key, artifact_type, payload_json, payload_sha256, created_at)"
        )
        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            (
                run_id,
                "Authored historical fixture claim.",
                "2026-10-11T20:00:00Z",
                "2026-10-11T20:00:02Z",
            ),
        )
        conn.execute(
            "INSERT INTO v2_artifacts VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                "phase-13-round-1-search",
                "V2RoundOneSearchResult",
                payload,
                hashlib.sha256(payload.encode()).hexdigest(),
                "2026-10-11T20:00:01Z",
            ),
        )

    @contextmanager
    def open_fixture(database: Path) -> Iterator[SimpleNamespace]:
        # Export behavior is isolated from the production schema reader, tested elsewhere.
        conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            yield SimpleNamespace(connection=conn, compatibility=SimpleNamespace(schema_version=14))
        finally:
            conn.close()

    def audit(*args: object, **kwargs: object) -> V2PhysicalCallAudit:
        return V2PhysicalCallAudit(starts=(), completions=())

    def receipts(*args: object, **kwargs: object) -> tuple[object, ...]:
        return ()

    monkeypatch.setattr(import_saved_research, "open_read_only_store", open_fixture)
    monkeypatch.setattr(import_saved_research, "read_v2_physical_call_audit", audit)
    monkeypatch.setattr(import_saved_research, "read_v2_physical_call_artifacts", receipts)
    return path


def _stage_payload(database: Path, label: Literal["acquisition", "plan"]) -> dict[str, object]:
    with sqlite3.connect(database) as conn:
        run_id, claim = conn.execute("SELECT run_id, raw_claim FROM runs").fetchone()
    now = datetime(2026, 10, 11, 20, 0, 1, tzinfo=UTC)
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    if label == "acquisition":
        output = V2AcquisitionProbeOutput(
            run_id=UUID(run_id),
            directions=directions,
            acquisitions=(),
            attempts=(),
            probes=(),
            survivors=(),
            policy_identity="researchassistant-v2-phase-5-acquisition-probe-v1",
            completed_at=now,
        )
    else:
        output = V2InitialPlannerOutput(
            run_id=UUID(run_id),
            raw_claim=claim,
            directions=directions,
            discovery_providers=(DiscoveryProvider.EXA,),
            searches=tuple(
                V2RoundOneSearchQuery(
                    run_id=UUID(run_id),
                    query_id=uuid4(),
                    direction=lane.direction,
                    provider=lane.provider,
                    strategy=lane.strategy,
                    query_text=f"Historical café evidence {lane.strategy}",
                    created_at=now,
                )
                for lane in V2InitialPlannerPolicy().search_lanes(
                    directions, (DiscoveryProvider.EXA,)
                )
            ),
            planner_prompt_version="historical-synthetic-v1",
            planned_at=now,
        )
    return json.loads(output.model_dump_json())


def _save_stage(
    database: Path,
    label: Literal["acquisition", "plan"],
    payload: dict[str, object],
    *,
    corrupt_checksum: bool = False,
) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=3) + "\n\n"
    key = "phase-5-acquisition-probe" if label == "acquisition" else "phase-3-initial-round-1-plan"
    artifact_type = (
        "V2AcquisitionProbeOutput" if label == "acquisition" else "V2InitialPlannerOutput"
    )
    with sqlite3.connect(database) as conn:
        run_id = conn.execute("SELECT run_id FROM runs").fetchone()[0]
        conn.execute(
            "INSERT INTO v2_artifacts VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                key,
                artifact_type,
                text,
                "0" * 64 if corrupt_checksum else hashlib.sha256(text.encode()).hexdigest(),
                "2026-10-11T20:00:01Z",
            ),
        )
    return text


def test_saved_fixture_replay_is_private_read_only_and_keeps_unknowns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    before = (database.read_bytes(), database.stat().st_mtime_ns)
    output = tmp_path / "export"
    report = import_saved_research.import_history(database, output, origin="fixture")
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before
    assert report["origins"] == {"fixture": 1}
    observed = report["observations"][0]
    assert observed["discovery_replay"]["normalized_items"] == 4
    assert not observed["discovery_replay"]["candidate_inventory_available"]
    assert observed["actual_total_cost_usd"] is None
    assert observed["stages"]["returned"]["reference_recall"] is None
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir())
    with pytest.raises(ValueError, match="fresh private"):
        import_saved_research.import_history(database, output, origin="fixture")


def test_importer_refuses_fixture_to_observation_relabel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="fixture URLs"):
        import_saved_research.import_history(
            database, tmp_path / "export", origin="replayed_observation"
        )


def test_importer_rejects_corrupt_saved_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE v2_artifacts SET payload_sha256=?", ("0" * 64,))
    with pytest.raises(ValueError, match="checksum mismatch"):
        import_saved_research.import_history(database, tmp_path / "export", origin="fixture")
    assert not (tmp_path / "export").exists()


@pytest.mark.parametrize("label", ["acquisition", "plan"])
def test_importer_preserves_exact_valid_historical_stage_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: Literal["acquisition", "plan"]
) -> None:
    database = _database(tmp_path, monkeypatch)
    payload = _stage_payload(database, label)
    if label == "plan":
        # Old saved plans omit these later optional fields.
        payload.pop("claim_coverage_focus")
        for query in payload["searches"]:
            query.pop("compiled_query")
    expected = _save_stage(database, label, payload)
    before = database.read_bytes(), database.stat().st_mtime_ns
    output = tmp_path / "export"

    import_saved_research.import_history(database, output, origin="fixture")

    assert (output / f"run-1-original-{label}.json").read_bytes() == expected.encode("utf-8")
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


@pytest.mark.parametrize("label", ["acquisition", "plan"])
def test_importer_rejects_corrupt_saved_stage_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: Literal["acquisition", "plan"]
) -> None:
    database = _database(tmp_path, monkeypatch)
    _save_stage(database, label, _stage_payload(database, label), corrupt_checksum=True)
    before = database.read_bytes(), database.stat().st_mtime_ns
    output = tmp_path / "export"

    with pytest.raises(ValueError, match="checksum mismatch"):
        import_saved_research.import_history(database, output, origin="fixture")

    assert not output.exists()
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


@pytest.mark.parametrize("label", ["acquisition", "plan"])
def test_importer_rejects_stage_envelope_with_wrong_contract_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: Literal["acquisition", "plan"]
) -> None:
    database = _database(tmp_path, monkeypatch)
    _save_stage(database, label, _stage_payload(database, label))
    key = "phase-5-acquisition-probe" if label == "acquisition" else "phase-3-initial-round-1-plan"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE v2_artifacts SET artifact_type='AnotherStage' WHERE artifact_key=?", (key,)
        )
    output = tmp_path / "export"
    with pytest.raises(ValueError, match="artifact type differs"):
        import_saved_research.import_history(database, output, origin="fixture")
    assert not output.exists()


@pytest.mark.parametrize("label", ["acquisition", "plan"])
def test_importer_rejects_saved_stage_owned_by_another_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: Literal["acquisition", "plan"]
) -> None:
    database = _database(tmp_path, monkeypatch)
    payload = _stage_payload(database, label)
    other_run = str(uuid4())
    payload["run_id"] = other_run
    if label == "plan":
        for query in payload["searches"]:
            query["run_id"] = other_run
    _save_stage(database, label, payload)
    output = tmp_path / "export"

    with pytest.raises(ValueError, match="belongs to another run"):
        import_saved_research.import_history(database, output, origin="fixture")

    assert not output.exists()


def test_importer_rejects_plan_with_cross_run_nested_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    payload = _stage_payload(database, "plan")
    payload["searches"][0]["run_id"] = str(uuid4())
    _save_stage(database, "plan", payload)
    output = tmp_path / "export"

    with pytest.raises(ValueError, match="run_id must match the planner output"):
        import_saved_research.import_history(database, output, origin="fixture")

    assert not output.exists()


def test_importer_rejects_acquisition_with_cross_run_nested_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    payload = _stage_payload(database, "acquisition")
    cluster_id, snapshot_id = str(uuid4()), str(uuid4())
    snapshot_hash = hashlib.sha256(b"Historical synthetic source.").hexdigest()
    payload["acquisitions"] = [
        {
            "cluster_id": cluster_id,
            "direction": "support",
            "provider": "wigolo",
            "snapshot": {
                "run_id": str(uuid4()),
                "retrieval_attempt_id": str(uuid4()),
                "snapshot_id": snapshot_id,
                "source_url": "https://fixture.invalid/source",
                "retrieved_at": "2026-10-11T20:00:01Z",
                "normalized_text": "Historical synthetic source.",
                "snapshot_sha256": snapshot_hash,
                "word_count": 3,
                "truncated": False,
                "created_at": "2026-10-11T20:00:01Z",
            },
        }
    ]
    payload["probes"] = [
        {
            "cluster_id": cluster_id,
            "snapshot_id": snapshot_id,
            "snapshot_sha256": snapshot_hash,
            "succeeded": False,
            "passages": [],
            "failure": "synthetic source lacked a useful passage",
        }
    ]
    _save_stage(database, "acquisition", payload)
    output = tmp_path / "export"

    with pytest.raises(ValueError, match="snapshot run_id must match output run_id"):
        import_saved_research.import_history(database, output, origin="fixture")

    assert not output.exists()


@pytest.mark.parametrize(
    "credential",
    [
        {"api_key": "SYNTHETIC_NOT_A_SECRET"},
        {"endpoint": "https://api.openalex.org/works?api_key=SYNTHETIC_NOT_A_SECRET"},
        {"headers": {"Authorization": "Bearer SYNTHETIC_NOT_A_SECRET"}},
    ],
)
def test_importer_rejects_stage_credentials_before_writing_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, credential: dict[str, object]
) -> None:
    database = _database(tmp_path, monkeypatch)
    payload = _stage_payload(database, "acquisition")
    payload["synthetic_capture"] = credential
    _save_stage(database, "acquisition", payload)
    before = database.read_bytes(), database.stat().st_mtime_ns
    output = tmp_path / "export"
    written: list[bytes] = []
    original_open = import_saved_research.os.open

    def capture_open(path: Path, flags: int, mode: int) -> int:
        # The rejected stage never gets an output descriptor.
        assert "original-acquisition" not in path.name
        written.append(path.name.encode())
        return original_open(path, flags, mode)

    monkeypatch.setattr(import_saved_research.os, "open", capture_open)
    with pytest.raises(ValueError, match="credential") as caught:
        import_saved_research.import_history(database, output, origin="fixture")

    assert "SYNTHETIC_NOT_A_SECRET" not in str(caught.value)
    assert written
    assert not output.exists()
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


def test_failed_import_preserves_preexisting_output_and_unowned_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    output = tmp_path / "export"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_text("preserve existing output")

    with pytest.raises(ValueError, match="fresh private"):
        import_saved_research.import_history(database, output, origin="fixture")
    assert sentinel.read_text() == "preserve existing output"

    sentinel.unlink()
    output.rmdir()

    def fail_evaluation(manifest: Path, *, replay: bool) -> dict[str, object]:
        sentinel.write_text("preserve externally added file")
        raise ValueError("synthetic evaluation failure")

    monkeypatch.setattr(import_saved_research, "evaluate", fail_evaluation)
    with pytest.raises(ValueError, match="synthetic evaluation failure"):
        import_saved_research.import_history(database, output, origin="fixture")

    assert list(output.iterdir()) == [sentinel]
    assert sentinel.read_text() == "preserve externally added file"


def _snapshot_hash(database: Path) -> str:
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        connection.execute("BEGIN")
        connection.execute("SELECT * FROM runs").fetchall()
        return hashlib.sha256(connection.serialize()).hexdigest()


def _manifest(output: Path) -> dict[str, object]:
    return json.loads((output / "manifest.json").read_text())


def test_saved_history_snapshot_digest_identifies_committed_wal_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE runs SET raw_claim='First committed WAL claim.'")
        writer.commit()
        wal = database.with_name(database.name + "-wal")
        before = database.read_bytes(), database.stat().st_mtime_ns, wal.read_bytes()
        expected_first = _snapshot_hash(database)
        first_output = tmp_path / "first-export"
        import_saved_research.import_history(database, first_output, origin="fixture")
        first = _manifest(first_output)
        assert (database.read_bytes(), database.stat().st_mtime_ns, wal.read_bytes()) == before

        writer.execute("UPDATE runs SET raw_claim='Second committed WAL claim.'")
        writer.commit()
        second_before = database.read_bytes(), database.stat().st_mtime_ns, wal.read_bytes()
        expected_second = _snapshot_hash(database)
        second_output = tmp_path / "second-export"
        import_saved_research.import_history(database, second_output, origin="fixture")
        second = _manifest(second_output)
        assert (
            database.read_bytes(),
            database.stat().st_mtime_ns,
            wal.read_bytes(),
        ) == second_before

    assert first["topics"][0]["claim"] == "First committed WAL claim."
    assert second["topics"][0]["claim"] == "Second committed WAL claim."
    assert (
        first["baseline"]["database_main_file_sha256"]
        == second["baseline"]["database_main_file_sha256"]
    )
    assert first["baseline"]["database_snapshot_sha256"] == expected_first
    assert second["baseline"]["database_snapshot_sha256"] == expected_second
    assert expected_first != expected_second
    assert "database_sha256" not in first["baseline"]
    assert "database_bytes_and_mtime_unchanged" not in first["baseline"]


def test_saved_history_remains_on_one_snapshot_during_wal_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    read_payload = import_saved_research._saved_payload
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        expected_hash = _snapshot_hash(database)
        original_search = writer.execute("SELECT payload_json FROM v2_artifacts").fetchone()[0]
        updated_search = json.loads(original_search)
        updated_search["outcomes"][0]["results"][0]["title"] = "Changed after snapshot pinned"
        changed_payload = json.dumps(updated_search)
        committed = False

        def commit_before_artifact_read(
            connection: sqlite3.Connection,
            run_id: UUID,
            key: str,
            *,
            expected_type: str | None = None,
        ) -> str:
            nonlocal committed
            if not committed:
                writer.execute("UPDATE runs SET raw_claim='Claim changed during import.'")
                writer.execute(
                    "UPDATE v2_artifacts SET payload_json=?, payload_sha256=?",
                    (changed_payload, hashlib.sha256(changed_payload.encode()).hexdigest()),
                )
                writer.commit()
                committed = True
            return read_payload(connection, run_id, key, expected_type=expected_type)

        monkeypatch.setattr(import_saved_research, "_saved_payload", commit_before_artifact_read)
        output = tmp_path / "export"
        import_saved_research.import_history(database, output, origin="fixture")
        manifest = _manifest(output)

        assert committed
        assert (
            writer.execute("SELECT raw_claim FROM runs").fetchone()[0]
            == "Claim changed during import."
        )
        assert manifest["topics"][0]["claim"] == "Authored historical fixture claim."
        assert (output / "run-1-original-search.json").read_text() == original_search
        assert manifest["baseline"]["database_snapshot_sha256"] == expected_hash
        assert manifest["baseline"]["database_read_snapshot_pinned"] is True
        assert manifest["baseline"]["database_main_file_bytes_and_mtime_unchanged"] is True
        assert _snapshot_hash(database) != expected_hash


def test_saved_history_snapshot_excludes_uncommitted_wal_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path, monkeypatch)
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        expected_hash = _snapshot_hash(database)
        writer.execute("UPDATE runs SET raw_claim='Uncommitted synthetic claim.'")
        output = tmp_path / "export"

        import_saved_research.import_history(database, output, origin="fixture")

        manifest = _manifest(output)
        assert manifest["topics"][0]["claim"] == "Authored historical fixture claim."
        assert manifest["baseline"]["database_snapshot_sha256"] == expected_hash
        writer.rollback()
        assert _snapshot_hash(database) == expected_hash


@pytest.mark.parametrize("journal_mode", ["DELETE", "WAL"])
def test_importer_uses_validated_read_only_session_for_historical_schema_14(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal_mode: str
) -> None:
    from researchassistant.contracts.model_contracts import RunManifest, RunStatus, Stage
    from researchassistant.contracts.research_policy import V2PipelineIdentity
    from researchassistant.storage import store, store_schema

    fixture = _database(tmp_path, monkeypatch)
    with closing(sqlite3.connect(fixture)) as source:
        saved = source.execute("SELECT * FROM v2_artifacts").fetchone()
    database = tmp_path / "schema-14.sqlite3"
    with closing(sqlite3.connect(database)) as setup:
        setup.row_factory = sqlite3.Row
        store_schema._initialize_schema(setup, target_version=14)
    now = datetime(2026, 10, 11, 20, 0, tzinfo=UTC)
    store.insert_run(
        str(database),
        RunManifest(
            run_id=UUID(saved[0]),
            raw_claim="Authored historical fixture claim.",
            status=RunStatus.PLANNED,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=now,
            updated_at=now,
        ),
    )
    store.insert_v2_pipeline_identity(str(database), UUID(saved[0]), V2PipelineIdentity(), now)
    with closing(sqlite3.connect(database)) as writer:
        writer.execute(f"PRAGMA journal_mode={journal_mode}")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(
            "INSERT INTO v2_artifacts "
            "(run_id, artifact_key, artifact_type, payload_json, payload_sha256, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            saved,
        )
        writer.commit()
        before = database.read_bytes(), database.stat().st_mtime_ns
        connections: list[sqlite3.Connection] = []

        def validated_open(path: Path) -> store.ReadOnlyStore:
            reader = store.open_read_only_store(path)
            connections.append(reader.connection)
            assert reader.compatibility.schema_version == 14
            assert reader.connection.in_transaction
            assert reader.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            return reader

        monkeypatch.setattr(import_saved_research, "open_read_only_store", validated_open)
        output = tmp_path / "export"
        report = import_saved_research.import_history(database, output, origin="fixture")

        assert report["origins"] == {"fixture": 1}
        assert (database.read_bytes(), database.stat().st_mtime_ns) == before
        assert _manifest(output)["baseline"]["schema"] == 14
        assert len(connections) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connections[0].execute("SELECT 1")
