"""Recorded historical contracts reconstruct without weakening fresh admission."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from agents.renderer import validate_final_release
from agents.v2_extraction import V2ExactExtractionResult
from frontend.live_history import history, research_trail
from researchassistant.contracts import models
from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryPolicy,
    V2GraphNeighborAction,
    V2ProviderCapabilities,
    V2SeedEligibility,
    V2WorkIdentity,
    discovery_id,
)
from researchassistant.contracts.historical import HistoricalRead, RecordCompatibilityError
from researchassistant.contracts.models import (
    LedgerRecord,
    PersistedStageArtifact,
    ProviderRunContract,
    RunManifest,
    RunStatus,
    Stage,
    V2PersistedArtifact,
    V2PipelineIdentity,
)
from researchassistant.evidence.brief_export import BriefExportFormat, export_released_brief
from researchassistant.evidence.evidence_browser import browse_evidence_run
from researchassistant.evidence.historical_render import RELEASE_V1_TEMPLATES
from researchassistant.research.fixture_pipeline import FixturePipelineResult, run_fixture_pipeline
from researchassistant.research.orchestrator import (
    MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
    PHASE9_ANALYSIS_ARTIFACT,
    AnalysisStageResult,
    ProviderRunStatus,
    ResearcherPairResult,
    _combine_analysis_results,
    _read_optional_stage_result,
    inspect_provider_run,
)
from researchassistant.storage.historical_decode import (
    decode_ledger,
    decode_native_artifact,
    decode_v2_artifact,
)
from researchassistant.storage.store import (
    init_db,
    insert_ledger_record,
    insert_provider_run_contract,
    insert_run,
    insert_stage_artifact,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_ledger_record,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/historical_reads"
WHEN = datetime(2026, 8, 2, tzinfo=UTC)


def _cases(name: str, field: str = "cases") -> list[dict[str, Any]]:
    return json.loads((FIXTURES / name).read_text())[field]


def _v2_envelope(case: dict[str, Any]) -> V2PersistedArtifact:
    return V2PersistedArtifact(
        run_id=case["run_id"],
        artifact_key=case["artifact_key"],
        artifact_type=case["artifact_type"],
        payload_json=case["payload_json"],
        payload_sha256=case["fixture_payload_sha256"],
        created_at=WHEN,
    )


def _v2_trail_pair(
    run_id: UUID,
    round_number: int,
    graph_action: V2GraphNeighborAction | None = None,
) -> tuple[models.V2DiscoveryScoutOutput, models.V2AcquisitionProbeOutput, UUID]:
    """Build one realistic, entirely offline discovery/acquisition trail pair."""
    direction = models.ResearchDirection.SUPPORT
    directions = models.ResearchDirections(support_enabled=True, challenge_enabled=False)
    item_id, cluster_id = UUID(int=round_number), UUID(int=200 + round_number)
    query_id = (
        graph_action.artifact_id if graph_action is not None else UUID(int=100 + round_number)
    )
    url = f"https://example.test/history/{round_number}"
    provenance = models.DiscoveryProvenance(
        provider=graph_action.provider
        if graph_action is not None
        else models.DiscoveryProvider.EXA,
        query_id=query_id,
        query_text=None if graph_action is not None else f"offline history query {round_number}",
        graph_action=graph_action,
        direction=direction,
        round_number=round_number,
        provider_rank=1,
        original_url=url,
        targeted_gap_ids=graph_action.target_gap_ids if graph_action is not None else (),
    )
    item = models.NormalizedDiscoveryItem(
        run_id=run_id,
        item_id=item_id,
        provider=graph_action.provider
        if graph_action is not None
        else models.DiscoveryProvider.EXA,
        query_id=query_id,
        query_text=provenance.query_text,
        graph_action=graph_action,
        direction=direction,
        round_number=round_number,
        provider_rank=1,
        source_url=url,
        canonical_url=url,
        provenance_chain=(provenance,),
        discovered_at=WHEN,
    )
    cluster = models.SourceCluster(
        cluster_id=cluster_id,
        preferred_url=url,
        canonical_url=url,
        item_ids=(item_id,),
        provider_references=(
            models.DiscoveryProviderReference(
                provider=models.DiscoveryProvider.EXA,
                item_id=item_id,
                provider_rank=1,
            ),
        ),
        query_references=(query_id,),
        metadata_provenance=(provenance,),
    )
    discovery = models.V2DiscoveryScoutOutput(
        run_id=run_id,
        directions=directions,
        items=(item,),
        clusters=(cluster,),
        scout_batches=(
            models.ScoutBatch(
                run_id=run_id,
                items=(
                    models.ScoutItem(
                        item_id=item_id,
                        decision=models.ScoutDecision.RETRIEVE,
                        rationale="offline regression fixture",
                    ),
                ),
            ),
        ),
        scout_audits=(models.ScoutBatchAudit(batch_number=1, attempted_calls=1),),
        completed_at=WHEN,
    )
    text = f"Offline source text for public research trail round {round_number}."
    snapshot = models.SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=UUID(int=300 + round_number),
        snapshot_id=UUID(int=400 + round_number),
        source_url=url,
        retrieved_at=WHEN,
        normalized_text=text,
        snapshot_sha256=sha256(text.encode()).hexdigest(),
        word_count=len(text.split()),
        truncated=False,
        created_at=WHEN,
    )
    acquisition = models.V2AcquisitionProbeOutput(
        run_id=run_id,
        directions=directions,
        acquisitions=(
            models.V2AcquiredSource(
                cluster_id=cluster_id,
                direction=direction,
                snapshot=snapshot,
                provider=models.V2AcquisitionProvider.FIRECRAWL,
            ),
        ),
        attempts=(
            models.V2AcquisitionAttempt(
                cluster_id=cluster_id,
                url=url,
                provider=models.V2AcquisitionProvider.FIRECRAWL,
                succeeded=True,
            ),
        ),
        probes=(
            models.V2ProbeResult(
                cluster_id=cluster_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot.snapshot_sha256,
                succeeded=True,
            ),
        ),
        survivors=(),
        completed_at=WHEN,
    )
    return discovery, acquisition, item_id


def _v2_failed_production_result(
    database: Path,
    run_id: UUID,
    raw_claim: str,
) -> models.StrictModel:
    from providers.v2_budget import V2BudgetSnapshot
    from researchassistant.research.v2_orchestrator import (
        V2ProductionPipelineResult,
        V2ProductionState,
    )

    return V2ProductionPipelineResult(
        run_id=run_id,
        db_path=str(database),
        raw_claim=raw_claim,
        state=V2ProductionState.FAILED,
        current_stage=Stage.CLAIM_PLANNER,
        failure_reason="offline fixture failure",
        budget=V2BudgetSnapshot(
            physical_calls_used=0,
            token_exposure=0,
            cost_exposure_usd=0,
            physical_calls_remaining=1,
            tokens_remaining=1,
            cost_remaining_usd=1,
        ),
        completed_at=WHEN,
    )


def _v2_trail_database(
    path: Path, *, graph_action: V2GraphNeighborAction | None = None
) -> tuple[UUID, dict[int, UUID]]:
    run_id = UUID(int=500)
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=run_id,
            raw_claim="Offline claim for historical trail compatibility.",
            status=RunStatus.RUNNING,
            current_stage=Stage.ACQUISITION,
            created_at=WHEN,
            updated_at=WHEN,
        ),
    )
    insert_v2_pipeline_identity(str(path), run_id, V2PipelineIdentity(), WHEN)
    item_ids: dict[int, UUID] = {}
    for round_number in (1, 2):
        action = graph_action if round_number == 2 else None
        discovery, acquisition, item_id = _v2_trail_pair(run_id, round_number, action)
        item_ids[round_number] = item_id
        discovery_key = (
            "phase-4-discovery-scout"
            if round_number == 1
            else f"phase-7-round-{round_number}-discovery-scout"
        )
        acquisition_key = (
            "phase-5-acquisition-probe"
            if round_number == 1
            else f"phase-7-round-{round_number}-acquisition-probe"
        )
        insert_v2_artifact(str(path), discovery_key, discovery, WHEN)
        insert_v2_artifact(str(path), acquisition_key, acquisition, WHEN)
    return run_id, item_ids


def _history_graph_action(run_id: UUID) -> V2GraphNeighborAction:
    provider = models.DiscoveryProvider.OPENALEX
    capabilities = V2ProviderCapabilities(
        provider=provider,
        search_modes=("lexical",),
        max_metadata_per_page=20,
        max_metadata_per_operation=20,
        pagination="none",
        identity_lookup=True,
        executable_identity_lookup=True,
        relationships=("references", "citing", "related"),
        executable_relationships=("references", "citing", "related"),
        executable_search_modes=("lexical",),
        documentation_urls=("https://docs.openalex.org/api-entities/works/search-works",),
    )
    seed = V2SeedEligibility(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2SeedEligibility", "history-seed"),
        identity_key="history-seed",
        candidate_id=UUID(int=701),
        source_id=UUID(int=702),
        snapshot_id=UUID(int=703),
        work=V2WorkIdentity(
            grouping_key="doi:10.5555/history-seed",
            doi="10.5555/history-seed",
            provider_work_id="https://openalex.org/W-history",
            title="Persisted seed paper",
            resolution="verified_identifiers",
        ),
        eligible=True,
        reason="resolved seed",
    )
    return V2GraphNeighborAction(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2GraphNeighborAction", "history-citing"),
        identity_key="history-citing",
        seed=seed,
        relationship="citing",
        provider=provider,
        direction=models.ResearchDirection.SUPPORT,
        round_number=2,
        target_gap_ids=("gap-history-a",),
        requested_depth=3,
        policy=V2DiscoveryPolicy(),
        capabilities=capabilities,
    )


def test_public_v2_graph_trail_preserves_saved_action_and_legacy_text(tmp_path: Path) -> None:
    database = tmp_path / "v2-graph-trail.sqlite3"
    run_id = UUID(int=500)
    action = _history_graph_action(run_id)
    _v2_trail_database(database, graph_action=action)

    trail = research_trail(database, run_id)

    graph_item = next(item for item in trail.items if item.research_round == 2)
    text_item = next(item for item in trail.items if item.research_round == 1)
    assert graph_item.query_text is None
    assert graph_item.graph_action == action
    assert graph_item.model_dump(mode="json")["graph_action"]["artifact_id"] == str(
        action.artifact_id
    )
    assert text_item.query_text == "offline history query 1"
    assert "graph_action" not in text_item.model_dump(mode="json")


def _tamper_v2_artifact(
    path: Path,
    run_id: UUID,
    artifact_key: str,
    mutation: str,
) -> None:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT artifact_type, payload_json, payload_sha256 FROM v2_artifacts "
            "WHERE run_id=? AND artifact_key=?",
            (str(run_id), artifact_key),
        ).fetchone()
        assert row is not None
        artifact_type, payload_json, payload_sha256 = row
        if mutation == "payload_hash":
            payload_sha256 = "0" * 64
        else:
            payload = json.loads(payload_json)
            if mutation == "unsupported_field":
                payload["unrecognized_historical_field"] = "opaque"
            elif mutation == "embedded_run":
                payload["run_id"] = str(UUID(int=999))
            elif mutation == "snapshot_hash":
                payload["acquisitions"][0]["snapshot"]["snapshot_sha256"] = "0" * 64
            elif mutation == "wrong_type":
                artifact_type = (
                    "V2AcquisitionProbeOutput"
                    if artifact_key.endswith("discovery-scout")
                    or artifact_key == "phase-4-discovery-scout"
                    else "V2DiscoveryScoutOutput"
                )
            else:
                raise AssertionError(f"unknown test mutation {mutation}")
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if mutation != "payload_hash":
                payload_sha256 = sha256(payload_json.encode()).hexdigest()

        triggers = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='v2_artifacts'"
        ).fetchall()
        try:
            for name, _sql in triggers:
                connection.execute(f'DROP TRIGGER "{name}"')
            connection.execute(
                "UPDATE v2_artifacts SET artifact_type=?, payload_json=?, payload_sha256=? "
                "WHERE run_id=? AND artifact_key=?",
                (artifact_type, payload_json, payload_sha256, str(run_id), artifact_key),
            )
        finally:
            for _name, sql in triggers:
                connection.execute(sql)
        connection.commit()


@pytest.mark.parametrize(
    ("kind", "mutation"),
    [
        ("discovery", "unsupported_field"),
        ("discovery", "wrong_type"),
        ("discovery", "embedded_run"),
        ("discovery", "payload_hash"),
        ("acquisition", "unsupported_field"),
        ("acquisition", "wrong_type"),
        ("acquisition", "embedded_run"),
        ("acquisition", "snapshot_hash"),
        ("acquisition", "payload_hash"),
    ],
)
def test_public_v2_trail_reports_unsafe_artifacts_per_record_without_mutation(
    kind: str,
    mutation: str,
    tmp_path: Path,
) -> None:
    database = tmp_path / "v2-trail.sqlite3"
    run_id, _item_ids = _v2_trail_database(database)
    artifact_key = "phase-4-discovery-scout" if kind == "discovery" else "phase-5-acquisition-probe"
    _tamper_v2_artifact(database, run_id, artifact_key, mutation)
    with closing(sqlite3.connect(database)) as connection:
        before_rows = connection.execute(
            "SELECT artifact_key, artifact_type, payload_json, payload_sha256 "
            "FROM v2_artifacts WHERE run_id=? ORDER BY artifact_key",
            (str(run_id),),
        ).fetchall()
    before = database.read_bytes(), database.stat().st_mtime_ns

    trail = research_trail(database, run_id)

    assert len(trail.compatibility_issues) == 1
    assert trail.compatibility_issues[0].record_key == artifact_key
    assert trail.compatibility_issues[0].message
    trail_rounds = {item.research_round: item for item in trail.items}
    assert 2 in trail_rounds
    assert trail_rounds[2].url == "https://example.test/history/2"
    if kind == "discovery":
        assert 1 not in trail_rounds
    else:
        assert 1 in trail_rounds
        assert trail_rounds[1].url == "https://example.test/history/1"
        assert trail_rounds[1].acquisition_state is None
    with closing(sqlite3.connect(database)) as connection:
        after_rows = connection.execute(
            "SELECT artifact_key, artifact_type, payload_json, payload_sha256 "
            "FROM v2_artifacts WHERE run_id=? ORDER BY artifact_key",
            (str(run_id),),
        ).fetchall()
    assert after_rows == before_rows
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


def test_public_history_keeps_other_runs_visible_when_production_payload_hash_is_bad(
    tmp_path: Path,
) -> None:
    from researchassistant.research.v2_orchestrator import V2_PRODUCTION_ARTIFACT_KEY

    database = tmp_path / "v2-history.sqlite3"
    init_db(str(database))
    bad_run_id, good_run_id = UUID(int=600), UUID(int=601)
    for run_id in (bad_run_id, good_run_id):
        insert_run(
            str(database),
            RunManifest(
                run_id=run_id,
                raw_claim=f"Offline claim {run_id.int}.",
                status=RunStatus.FAILED,
                current_stage=Stage.CLAIM_PLANNER,
                created_at=WHEN,
                updated_at=WHEN,
            ),
        )
        insert_v2_pipeline_identity(str(database), run_id, V2PipelineIdentity(), WHEN)
        insert_v2_artifact(
            str(database),
            V2_PRODUCTION_ARTIFACT_KEY,
            _v2_failed_production_result(database, run_id, f"Offline claim {run_id.int}."),
            WHEN,
        )
    assert all(not item.compatibility_issues for item in history(database))
    _tamper_v2_artifact(database, bad_run_id, V2_PRODUCTION_ARTIFACT_KEY, "payload_hash")
    with closing(sqlite3.connect(database)) as connection:
        before_rows = connection.execute(
            "SELECT run_id, artifact_key, artifact_type, payload_json, payload_sha256 "
            "FROM v2_artifacts ORDER BY run_id, artifact_key"
        ).fetchall()
    before = database.read_bytes(), database.stat().st_mtime_ns

    items = history(database)

    by_id = {item.run_id: item for item in items}
    assert set(by_id) == {bad_run_id, good_run_id}
    assert len(by_id[bad_run_id].compatibility_issues) == 1
    assert by_id[bad_run_id].compatibility_issues[0].record_key == V2_PRODUCTION_ARTIFACT_KEY
    assert "hash" in by_id[bad_run_id].compatibility_issues[0].message.lower()
    assert by_id[good_run_id].compatibility_issues == ()
    with closing(sqlite3.connect(database)) as connection:
        after_rows = connection.execute(
            "SELECT run_id, artifact_key, artifact_type, payload_json, payload_sha256 "
            "FROM v2_artifacts ORDER BY run_id, artifact_key"
        ).fetchall()
    assert after_rows == before_rows
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


def test_public_history_keeps_terminal_result_when_child_stage_hash_is_bad(
    tmp_path: Path,
) -> None:
    from researchassistant.research.v2_orchestrator import (
        V2_PRODUCTION_ARTIFACT_KEY,
    )

    database = tmp_path / "v2-stage-history.sqlite3"
    run_id = UUID(int=602)
    init_db(str(database))
    insert_run(
        str(database),
        RunManifest(
            run_id=run_id,
            raw_claim="Offline terminal history claim.",
            status=RunStatus.FAILED,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=WHEN,
            updated_at=WHEN,
        ),
    )
    insert_v2_pipeline_identity(str(database), run_id, V2PipelineIdentity(), WHEN)
    result = _v2_failed_production_result(database, run_id, "Offline terminal history claim.")
    insert_v2_artifact(str(database), V2_PRODUCTION_ARTIFACT_KEY, result, WHEN)
    discovery, _acquisition, _item_id = _v2_trail_pair(run_id, 1)
    insert_v2_artifact(str(database), "phase-4-discovery-scout", discovery, WHEN)
    _tamper_v2_artifact(database, run_id, "phase-4-discovery-scout", "payload_hash")
    before = database.read_bytes(), database.stat().st_mtime_ns

    items = history(database)

    assert len(items) == 1
    assert items[0].run_id == run_id
    assert items[0].status == "failed"
    assert items[0].stage == Stage.CLAIM_PLANNER.value
    assert len(items[0].compatibility_issues) == 1
    assert "stage reconstruction" in items[0].compatibility_issues[0].message
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


@pytest.mark.parametrize("case", _cases("native-ledger-august2.json", "records"))
def test_both_august_records_preserve_recorded_values_and_strict_current_contract(
    case: dict[str, Any],
    tmp_path: Path,
) -> None:
    contract = ProviderRunContract.model_validate(case["provider_contract"])
    values = case["record"]
    with pytest.raises(ValueError, match="entailment"):
        LedgerRecord.model_validate(values)
    original = json.dumps(values, sort_keys=True)
    record = decode_ledger(values, contract)
    assert isinstance(record, HistoricalRead)
    assert record.claim_fit == record.evidence_quality == record.ledger_score == 4
    assert record.entailment.value == "Strong"
    assert record.placement.value == "secondary"
    decoded = record.model_dump(mode="json")
    for key, value in values.items():
        if key.endswith("_at"):
            assert getattr(record, key) == datetime.fromisoformat(value)
        else:
            assert decoded[key] == value
    assert json.dumps(values, sort_keys=True) == original
    database = tmp_path / "new.sqlite3"
    init_db(str(database))
    before = database.read_bytes(), database.stat().st_mtime_ns
    with pytest.raises(ValueError, match="entailment"):
        insert_ledger_record(str(database), record)
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


@pytest.mark.parametrize("case", _cases("legacy-researcher-trails.json"))
def test_legacy_trails_reconstruct_under_their_recorded_rules(
    case: dict[str, Any],
    tmp_path: Path,
) -> None:
    payload = json.dumps(case["payload"], sort_keys=True, separators=(",", ":"))
    assert sha256(payload.encode()).hexdigest() == case["fixture_payload_sha256"]
    artifact = PersistedStageArtifact(
        run_id=case["run_id"],
        artifact_key=case["stage_artifact_key"],
        artifact_type="ResearcherPairResult",
        payload_json=payload,
        created_at=WHEN,
    )
    with pytest.raises(ValueError):
        ResearcherPairResult.model_validate_json(payload)
    contract = ProviderRunContract.model_validate(case["provider_contract"])
    result = decode_native_artifact(artifact, ResearcherPairResult, contract)
    assert result.run_id == UUID(case["run_id"])
    assert result.supporting.retrieval_batch is not None
    assert result.supporting.retrieval_batch.discovery_ranking
    # Public trail projection retains actual legacy provider/intent/decision values.
    db = tmp_path / "legacy.sqlite3"
    init_db(str(db))
    from researchassistant.contracts.models import RunManifest, RunStatus, Stage
    from researchassistant.storage.store import insert_run

    insert_run(
        str(db),
        RunManifest(
            run_id=artifact.run_id,
            raw_claim=case["exact_claim"],
            status=RunStatus.RUNNING,
            current_stage=Stage.ACQUISITION,
            created_at=WHEN,
            updated_at=WHEN,
        ),
    )
    insert_provider_run_contract(str(db), contract)
    insert_stage_artifact(str(db), artifact)
    before = db.read_bytes(), db.stat().st_mtime_ns
    trail = research_trail(db, artifact.run_id)
    assert trail.items and not trail.compatibility_issues
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before
    # An unknown later round produces its own result without hiding the old round.
    insert_stage_artifact(
        str(db),
        artifact.model_copy(
            update={
                "artifact_key": MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
                "artifact_type": "UnsupportedResearcherPairV99",
            }
        ),
    )
    before = db.read_bytes(), db.stat().st_mtime_ns
    mixed = research_trail(db, artifact.run_id)
    assert mixed.items == trail.items
    assert len(mixed.compatibility_issues) == 1
    inspected = inspect_provider_run(db, artifact.run_id)
    assert inspected.retrieval_attempts_used == sum(
        len(side.retrieval_batch.outcomes)
        for side in (result.supporting, result.opposing)
        if side.retrieval_batch is not None
    )
    assert len(inspected.compatibility_issues) == 1
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before


@pytest.mark.parametrize("case", _cases("v2-prior-policy-artifacts.json"))
def test_all_prior_policy_families_and_nested_wrappers_decode(case: dict[str, Any]) -> None:
    artifact = _v2_envelope(case)
    model_type = (
        V2ExactExtractionResult
        if artifact.artifact_type == "V2ExactExtractionResult"
        else getattr(models, artifact.artifact_type)
    )
    original = artifact.payload_json, artifact.payload_sha256
    result = decode_v2_artifact(artifact, model_type)
    assert result.run_id == artifact.run_id
    assert (artifact.payload_json, artifact.payload_sha256) == original
    if case["case"] in {
        "queue-cap12",
        "extraction-v1-cap12",
        "analyst-v1",
        "analyst-v2",
        "reviewer-v1",
        "reviewer-v2",
        "backfill-phase12",
    }:
        with pytest.raises(ValueError):
            model_type.model_validate_json(artifact.payload_json)
        assert isinstance(result, HistoricalRead)


def test_forged_policy_hash_or_shape_is_not_a_historical_bypass(tmp_path: Path) -> None:
    case = _cases("v2-prior-policy-artifacts.json")[0]
    artifact = _v2_envelope(case)
    with pytest.raises(RecordCompatibilityError, match="hash mismatch"):
        decode_v2_artifact(
            artifact.model_copy(update={"payload_sha256": "0" * 64}),
            models.V2SourceSelectionQueueResult,
        )
    payload = json.loads(artifact.payload_json)
    payload["input"]["policy_identity"] = "forged-policy-v1"
    raw = json.dumps(payload)
    with pytest.raises(RecordCompatibilityError, match="unsupported historical"):
        decode_v2_artifact(
            artifact.model_copy(
                update={"payload_json": raw, "payload_sha256": sha256(raw.encode()).hexdigest()}
            ),
            models.V2SourceSelectionQueueResult,
        )
    decoded = decode_v2_artifact(artifact, models.V2SourceSelectionQueueResult)
    db = tmp_path / "write.sqlite3"
    init_db(str(db))
    with pytest.raises(ValueError, match="inspection values"):
        insert_v2_artifact(str(db), "forged", decoded, WHEN)


def _august_database(tmp_path: Path, index: int) -> tuple[Path, FixturePipelineResult, str]:
    result = run_fixture_pipeline(ROOT / "tests/fixtures/basic_valid_run", output_dir=tmp_path)
    database = Path(result.db_path)
    case = _cases("native-ledger-august2.json", "records")[index]
    values = dict(case["provider_contract"])
    values["run_id"] = str(result.run_id)
    contract = ProviderRunContract.model_validate(values)
    insert_provider_run_contract(str(database), contract)
    ledgers = [record.model_dump(mode="json") for record in result.ledger_records]
    target = ledgers[0]
    target.update(
        {
            key: case["record"][key]
            for key in (
                "evidence_quality",
                "claim_fit",
                "ledger_score",
                "placement",
                "entailment",
                "analyst_prompt_version",
                "reviewer_prompt_version",
            )
        }
    )
    synthesis = result.synthesis_output.model_dump(mode="json")
    lines = ["# Research Brief", "", f"Claim under review: {result.raw_claim}"]
    lookup = {record["ledger_claim_id"]: record for record in ledgers}
    for section in synthesis["sections"]:
        from researchassistant.contracts.models import RELEASE_SECTION_HEADINGS, SectionType

        lines.extend(("", f"## {RELEASE_SECTION_HEADINGS[SectionType(section['section_type'])]}"))
        for item in section["items"]:
            record = lookup[item["ledger_claim_id"]]
            item["placement"], item["entailment"] = record["placement"], record["entailment"]
            if item["ledger_claim_id"] == target["ledger_claim_id"]:
                item["connective_template_id"] = f"{target['stance']}_evidence"
            lines.append(
                f"- {RELEASE_V1_TEMPLATES[item['connective_template_id']]} "
                f"{record['approved_factual_statement']} [source: {record['source_url']}]"
            )
    brief = "\n".join(lines) + "\n"
    with closing(sqlite3.connect(database)) as conn:
        triggers = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('ledger_records','synthesis_items','validation_runs')"
        ).fetchall()
        for name, _sql in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.execute(
            "UPDATE ledger_records SET evidence_quality=4,claim_fit=4,ledger_score=4,"
            "placement='secondary',entailment='Strong',analyst_prompt_version=?,"
            "reviewer_prompt_version=? WHERE ledger_claim_id=?",
            (
                target["analyst_prompt_version"],
                target["reviewer_prompt_version"],
                target["ledger_claim_id"],
            ),
        )
        conn.execute(
            "UPDATE synthesis_items SET placement='secondary',entailment='Strong',"
            "connective_template_id=? WHERE ledger_claim_id=?",
            (f"{target['stance']}_evidence", target["ledger_claim_id"]),
        )
        conn.execute(
            "UPDATE validation_runs SET validator_config_version='mvp1-release-validator-v1',"
            "rendered_brief_hash=? WHERE run_id=?",
            (sha256(brief.encode()).hexdigest(), str(result.run_id)),
        )
        for _name, sql in triggers:
            conn.execute(sql)
        conn.commit()
    insert_stage_artifact(
        str(database),
        PersistedStageArtifact(
            run_id=result.run_id,
            artifact_key=PHASE9_ANALYSIS_ARTIFACT,
            artifact_type="AnalysisStageResult",
            created_at=WHEN,
            payload_json=json.dumps(
                {
                    "run_id": str(result.run_id),
                    "analyst_decisions": [
                        d.model_dump(mode="json") for d in result.analyst_decisions
                    ],
                    "statement_drafts": [
                        d.model_dump(mode="json") for d in result.statement_drafts
                    ],
                    "reviewer_decisions": [
                        d.model_dump(mode="json") for d in result.reviewer_decisions
                    ],
                    "ledger_records": ledgers,
                }
            ),
        ),
    )
    return database, result, brief


@pytest.mark.parametrize("index", [0, 1])
def test_historical_browser_provider_inspection_and_export_reconstruct_released_identity(
    tmp_path: Path,
    index: int,
) -> None:
    db, offline, expected = _august_database(tmp_path / "run", index)
    before = db.read_bytes(), db.stat().st_mtime_ns
    assert len(history(db)) == 1
    browser = browse_evidence_run(db, offline.run_id)
    assert browser.released_statement_traces
    assert not browser.compatibility_issues
    inspected = inspect_provider_run(db, offline.run_id)
    assert inspected.status is ProviderRunStatus.RELEASED
    assert inspected.final_brief == expected
    assert inspected.rendered_brief_hash == sha256(expected.encode()).hexdigest()
    assert not inspected.compatibility_issues
    with pytest.raises(ValueError, match="entailment"):
        _read_optional_stage_result(
            db, offline.run_id, PHASE9_ANALYSIS_ARTIFACT, AnalysisStageResult
        )
    assert inspected.analysis_result is not None
    empty_round = AnalysisStageResult(
        run_id=offline.run_id,
        analyst_decisions=(),
        statement_drafts=(),
        reviewer_decisions=(),
        ledger_records=(),
    )
    combined = _combine_analysis_results(inspected.analysis_result, empty_round)
    assert isinstance(combined, HistoricalRead)
    assert combined.ledger_records == tuple(
        sorted(inspected.analysis_result.ledger_records, key=lambda item: str(item.ledger_claim_id))
    )
    export = export_released_brief(
        db, str(offline.run_id), tmp_path / "historical.md", BriefExportFormat.MARKDOWN
    )
    assert export.metadata.rendered_brief_hash == inspected.rendered_brief_hash
    assert expected in Path(export.output_path).read_text()
    record = read_ledger_record(db, offline.ledger_records[0].ledger_claim_id)
    with pytest.raises(ValueError, match="new release"):
        validate_final_release(
            offline.synthesis_output,
            [record],
            authoritative_claim=offline.raw_claim,
            validated_at=WHEN,
        )
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before


def test_historical_browser_loads_ledger_only_snapshot_in_bounded_batch(tmp_path: Path) -> None:
    db, offline, _brief = _august_database(tmp_path / "run", 0)
    ledger_id = str(offline.ledger_records[0].ledger_claim_id)
    with closing(sqlite3.connect(db)) as connection:
        connection.row_factory = sqlite3.Row
        ledger = connection.execute(
            "SELECT * FROM ledger_records WHERE ledger_claim_id=?", (ledger_id,)
        ).fetchone()
        assert ledger is not None
        snapshot = connection.execute(
            "SELECT * FROM snapshots WHERE snapshot_id=?", (ledger["snapshot_id"],)
        ).fetchone()
        assert snapshot is not None
        snapshot_id = str(uuid4())
        values = dict(snapshot)
        values["snapshot_id"] = snapshot_id
        columns = tuple(values)
        connection.execute(
            f"INSERT INTO snapshots ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            tuple(values[name] for name in columns),
        )
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='ledger_records'"
        ).fetchall()
        for name, _sql in triggers:
            connection.execute(f'DROP TRIGGER "{name}"')
        connection.execute(
            "UPDATE ledger_records SET snapshot_id=? WHERE ledger_claim_id=?",
            (snapshot_id, ledger_id),
        )
        for _name, sql in triggers:
            connection.execute(sql)
        connection.commit()

    before = db.read_bytes(), db.stat().st_mtime_ns
    browser = browse_evidence_run(db, offline.run_id)
    target = next(
        trail
        for trail in browser.trails
        if any(str(record.ledger_claim_id) == ledger_id for record in trail.ledger_records)
    )
    ledger_record = next(
        record for record in target.ledger_records if str(record.ledger_claim_id) == ledger_id
    )
    assert isinstance(ledger_record, HistoricalRead)
    assert ledger_record.snapshot_id != target.candidate.snapshot_id
    assert not browser.compatibility_issues
    assert browser.released_statement_traces
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before


def test_unknown_record_is_reported_without_hiding_unrelated_history_or_evidence(
    tmp_path: Path,
) -> None:
    db, offline, _brief = _august_database(tmp_path / "run", 0)
    with closing(sqlite3.connect(db)) as conn:
        # Permit disposable-fixture corruption only, restoring canonical schema guards.
        triggers = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='ledger_records'"
        ).fetchall()
        for name, _sql in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.execute(
            "UPDATE ledger_records SET analyst_prompt_version='unknown-prompt' "
            "WHERE ledger_claim_id=?",
            (str(offline.ledger_records[0].ledger_claim_id),),
        )
        for _name, sql in triggers:
            conn.execute(sql)
        conn.commit()
    before = db.read_bytes(), db.stat().st_mtime_ns
    browser = browse_evidence_run(db, offline.run_id)
    assert len(browser.compatibility_issues) == 1
    assert browser.compatibility_issues[0].record_key == str(
        offline.ledger_records[0].ledger_claim_id
    )
    assert len(browser.trails) == len(offline.candidates)
    assert browser.released_statement_traces  # The unaffected evidence remains readable.
    assert len(history(db)) == 1
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before


def test_historical_provider_identity_and_fingerprint_cannot_be_forged() -> None:
    case = _cases("native-ledger-august2.json", "records")[0]
    contract = ProviderRunContract.model_validate(case["provider_contract"])
    with pytest.raises(RecordCompatibilityError, match="unsupported recorded"):
        decode_ledger(case["record"], contract.model_copy(update={"schema_identity": "forged-v1"}))
    with pytest.raises(RecordCompatibilityError, match="fingerprint/identity"):
        decode_ledger(case["record"], contract.model_copy(update={"fingerprint_sha256": "0" * 64}))


def test_old_marker_does_not_make_current_extraction_accept_invalid_caps() -> None:
    case = next(
        case
        for case in _cases("v2-prior-policy-artifacts.json")
        if case["case"] == "extraction-v1-cap12"
    )
    payload = json.loads(case["payload_json"])
    payload["policy_identity"] = (
        "researchassistant-v2-phase-13-exact-extraction-analyzer-admission-v3"
    )
    with pytest.raises(ValueError):
        V2ExactExtractionResult.model_validate(payload)
    # Nor can an unknown identity exploit the current string-valued extraction field.
    modern_case = next(
        case for case in _cases("v2-prior-policy-artifacts.json") if case["case"] == "extraction-v2"
    )
    artifact = _v2_envelope(modern_case)
    payload = json.loads(artifact.payload_json)
    payload["policy_identity"] = "unsupported-extraction-v99"
    raw = json.dumps(payload)
    with pytest.raises(RecordCompatibilityError, match="unknown recorded"):
        decode_v2_artifact(
            artifact.model_copy(
                update={"payload_json": raw, "payload_sha256": sha256(raw.encode()).hexdigest()}
            ),
            V2ExactExtractionResult,
        )


def test_snapshot_hash_tampering_is_a_per_record_compatibility_failure() -> None:
    case = next(
        case for case in _cases("v2-prior-policy-artifacts.json") if case["case"] == "analyst-v2"
    )
    artifact = _v2_envelope(case)
    payload = json.loads(artifact.payload_json)
    snapshot = payload["input"]["queued_candidates"][0]["snapshot"]
    snapshot["normalized_text"] += "tampered"
    raw = json.dumps(payload)
    with pytest.raises(RecordCompatibilityError, match="snapshot content hash") as caught:
        decode_v2_artifact(
            artifact.model_copy(
                update={"payload_json": raw, "payload_sha256": sha256(raw.encode()).hexdigest()}
            ),
            models.V2EvidenceAnalystBatchResult,
        )
    assert caught.value.result.record_key == artifact.artifact_key


def test_native_snapshot_hash_failure_leaves_other_records_readable(tmp_path: Path) -> None:
    db, offline, _brief = _august_database(tmp_path / "run", 0)
    with closing(sqlite3.connect(db)) as conn:
        triggers = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='snapshots'"
        ).fetchall()
        for name, _sql in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.execute(
            "UPDATE snapshots SET normalized_text=normalized_text || 'tampered' "
            "WHERE snapshot_id=?",
            (str(offline.ledger_records[0].snapshot_id),),
        )
        for _name, sql in triggers:
            conn.execute(sql)
        conn.commit()
    before = db.read_bytes(), db.stat().st_mtime_ns
    browser = browse_evidence_run(db, offline.run_id)
    assert len(browser.compatibility_issues) == 1
    assert "hash mismatch" in browser.compatibility_issues[0].message
    assert browser.released_statement_traces
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before


def test_pdf_rendering_begins_after_all_inspection_connections_are_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import researchassistant.evidence.brief_export as exporter
    import researchassistant.storage.store as store

    db, offline, _brief = _august_database(tmp_path / "run", 0)
    original_connect = sqlite3.connect
    original_pdf = exporter._pdf
    connections: list[sqlite3.Connection] = []

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = original_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    def pdf(text: str) -> bytes:
        assert connections
        for conn in connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                conn.execute("SELECT 1")
        return original_pdf(text)

    monkeypatch.setattr(store.sqlite3, "connect", connect)
    monkeypatch.setattr(exporter, "_pdf", pdf)
    before = db.read_bytes(), db.stat().st_mtime_ns
    result = export_released_brief(
        db, str(offline.run_id), tmp_path / "brief.pdf", BriefExportFormat.PDF
    )
    assert result.metadata.rendered_brief_hash == sha256(_brief.encode()).hexdigest()
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before
