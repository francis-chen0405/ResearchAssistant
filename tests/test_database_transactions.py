"""Offline regressions for terminal and legacy portfolio crash recovery."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from agents.supportingresearcher import ResearcherRetrievalBatch, RetrievalOutcome
from frontend.live_history import history
from providers.scraper import ScrapeStatus
from providers.v2_budget import V2BudgetSnapshot
from researchassistant.contracts.model_contracts import RetrievalStatus
from researchassistant.contracts.models import (
    EvidenceRole,
    EvidenceTrailEntry,
    EvidenceTrailOutcome,
    PlannerOutput,
    PortfolioItem,
    ResearchRound,
    RetrievalRecord,
    RunManifest,
    RunStatus,
    SourceFamilyIdentity,
    SourceSnapshot,
    Stage,
    Stance,
    V2PipelineIdentity,
)
from researchassistant.research.orchestrator import (
    AnalysisStageResult,
    ResearcherPairResult,
    ResearcherSideStatus,
    ResearcherStageResult,
    _persist_mvp10_portfolio,
)
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
    _persist_terminal,
)
from researchassistant.storage.store import (
    init_db,
    insert_mvp10_portfolio_batch,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_evidence_trail_entries,
    read_run,
    read_v2_artifact,
    update_run,
)
from tests.test_v2_phase12_production import _run, _Scraper, _Search, _V2Model

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


def _terminal_run(tmp_path: Path) -> tuple[str, UUID, V2ProductionPipelineResult]:
    path = str(tmp_path / "terminal.sqlite3")
    run_id = uuid4()
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="A precise test claim.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW - timedelta(minutes=1),
            updated_at=NOW - timedelta(minutes=1),
        ),
    )
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), NOW)
    result = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=path,
        raw_claim="A precise test claim.",
        state=V2ProductionState.BLOCKED,
        current_stage=Stage.CLAIM_PLANNER,
        failure_reason="No admissible evidence remained.",
        budget=V2BudgetSnapshot(
            physical_calls_used=0,
            token_exposure=0,
            cost_exposure_usd=Decimal("0"),
            physical_calls_remaining=160,
            tokens_remaining=500000,
            cost_remaining_usd=Decimal("1"),
        ),
        completed_at=NOW,
    )
    return path, run_id, result


def test_terminal_manifest_failure_rolls_back_artifact(tmp_path: Path) -> None:
    path, run_id, result = _terminal_run(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TRIGGER fail_terminal_update BEFORE UPDATE ON runs
               BEGIN SELECT RAISE(ABORT, 'simulated manifest failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated manifest failure"):
        _persist_terminal(path, result, lambda: NOW + timedelta(hours=1))
    with pytest.raises(KeyError):
        read_v2_artifact(path, run_id, V2_PRODUCTION_ARTIFACT_KEY)
    assert read_run(path, run_id).status is RunStatus.RUNNING


def test_existing_terminal_artifact_repairs_manifest_from_stored_time(tmp_path: Path) -> None:
    path, run_id, result = _terminal_run(tmp_path)
    first = insert_v2_artifact(path, V2_PRODUCTION_ARTIFACT_KEY, result, NOW)

    _persist_terminal(path, result, lambda: NOW + timedelta(days=1))

    manifest = read_run(path, run_id)
    assert manifest.status is RunStatus.BLOCKED
    assert manifest.completed_at == NOW
    assert manifest.updated_at == NOW
    assert read_v2_artifact(path, run_id, V2_PRODUCTION_ARTIFACT_KEY) == first


def test_resume_repairs_terminal_manifest_without_new_provider_calls(tmp_path: Path) -> None:
    path = tmp_path / "resume.sqlite3"
    run_id = uuid4()
    model = _V2Model()
    first = _run(path, model, _Search(), _Scraper(), run_id=run_id)
    assert first.state is V2ProductionState.RELEASED
    calls = len(model.requests)
    original = read_v2_artifact(str(path), run_id, V2_PRODUCTION_ARTIFACT_KEY)
    running = read_run(str(path), run_id).model_copy(
        update={
            "status": RunStatus.RUNNING,
            "current_stage": Stage.CLAIM_PLANNER,
            "completed_at": None,
        }
    )
    update_run(str(path), running)

    resumed = _run(path, model, _Search(), _Scraper(), run_id=run_id)

    assert resumed == first
    assert len(model.requests) == calls
    assert read_run(str(path), run_id).status is RunStatus.COMPLETED
    assert read_run(str(path), run_id).completed_at == first.completed_at
    assert read_v2_artifact(str(path), run_id, V2_PRODUCTION_ARTIFACT_KEY) == original


def _portfolio_database(tmp_path: Path) -> str:
    path = str(tmp_path / "portfolio.sqlite3")
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """CREATE TABLE source_family_members (
                run_id TEXT, retrieval_attempt_id TEXT, source_family_id TEXT,
                family_key TEXT, identification_basis TEXT, created_at TEXT,
                PRIMARY KEY (run_id, retrieval_attempt_id));
            CREATE TABLE evidence_trail_entries (
                trail_entry_id TEXT PRIMARY KEY, run_id TEXT, retrieval_attempt_id TEXT,
                payload_json TEXT, created_at TEXT,
                UNIQUE (run_id, retrieval_attempt_id));
            CREATE TABLE portfolio_items (
                run_id TEXT, ledger_claim_id TEXT, source_family_id TEXT,
                payload_json TEXT, PRIMARY KEY (run_id, ledger_claim_id));"""
        )
    return path


def _portfolio_records(
    run_id: UUID,
) -> tuple[tuple[EvidenceTrailEntry, ...], tuple[PortfolioItem, ...]]:
    entries = tuple(
        EvidenceTrailEntry(
            trail_entry_id=uuid4(),
            run_id=run_id,
            retrieval_attempt_id=uuid4(),
            research_round=ResearchRound.INITIAL,
            role=EvidenceRole.SUPPORTING,
            source_title=f"Source {index}",
            source_domain="example.test",
            original_url=f"https://example.test/{index}",
            resolved_url=f"https://example.test/{index}",
            source_family=SourceFamilyIdentity(
                source_family_id=uuid4(),
                family_key=f"https://example.test/{index}",
                identification_basis="canonical_primary_url",
            ),
            retrieval_method="provider acquisition",
            snapshot_status="snapshotted",
            snapshot_sha256="a" * 64,
            outcome=EvidenceTrailOutcome.ACCEPTED,
            explanation="Accepted evidence.",
            created_at=NOW,
        )
        for index in range(2)
    )
    items = tuple(
        PortfolioItem(
            run_id=run_id,
            ledger_claim_id=uuid4(),
            source_family_id=entry.source_family.source_family_id,
            role=EvidenceRole.SUPPORTING,
            research_round=ResearchRound.INITIAL,
            added_at=NOW,
        )
        for entry in entries
        if entry.source_family is not None
    )
    return entries, items


def test_portfolio_batch_rolls_back_all_rows_on_late_failure(tmp_path: Path) -> None:
    path = _portfolio_database(tmp_path)
    entries, items = _portfolio_records(uuid4())
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""CREATE TRIGGER fail_second_portfolio BEFORE INSERT ON portfolio_items
               WHEN NEW.ledger_claim_id = '{items[1].ledger_claim_id}'
               BEGIN SELECT RAISE(ABORT, 'simulated late failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated late failure"):
        insert_mvp10_portfolio_batch(path, entries, items)
    with sqlite3.connect(path) as conn:
        for table in ("source_family_members", "evidence_trail_entries", "portfolio_items"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_portfolio_replay_preserves_old_timestamps_and_rejects_conflicts(tmp_path: Path) -> None:
    path = _portfolio_database(tmp_path)
    entries, items = _portfolio_records(uuid4())
    old_entry, old_item = entries[0], items[0]
    insert_mvp10_portfolio_batch(path, (old_entry,), (old_item,))
    replay_entries = tuple(
        entry.model_copy(update={"created_at": NOW + timedelta(hours=1)}) for entry in entries
    )
    replay_items = tuple(
        item.model_copy(update={"added_at": NOW + timedelta(hours=1)}) for item in items
    )

    insert_mvp10_portfolio_batch(path, replay_entries, replay_items)

    with sqlite3.connect(path) as conn:
        saved_entry = EvidenceTrailEntry.model_validate_json(
            conn.execute(
                "SELECT payload_json FROM evidence_trail_entries WHERE trail_entry_id = ?",
                (str(old_entry.trail_entry_id),),
            ).fetchone()[0]
        )
        saved_item = PortfolioItem.model_validate_json(
            conn.execute(
                "SELECT payload_json FROM portfolio_items WHERE ledger_claim_id = ?",
                (str(old_item.ledger_claim_id),),
            ).fetchone()[0]
        )
        assert conn.execute("SELECT COUNT(*) FROM portfolio_items").fetchone()[0] == 2
    assert saved_entry.created_at == NOW
    assert saved_item.added_at == NOW
    conflicting = replay_items[0].model_copy(update={"role": EvidenceRole.OPPOSING})
    with pytest.raises(sqlite3.IntegrityError, match="portfolio replay conflicts"):
        insert_mvp10_portfolio_batch(path, (), (conflicting,))


def test_old_partial_portfolio_replays_missing_snapshot_projection(tmp_path: Path) -> None:
    path = _portfolio_database(tmp_path)
    entries, items = _portfolio_records(uuid4())
    old = entries[0].model_copy(
        update={
            "source_family": None,
            "snapshot_status": "not snapshotted",
            "snapshot_sha256": None,
            "model_attempt_ids": (),
            "accepted_statement": None,
            "accepted_quote": None,
            "cost_incurred": False,
        }
    )
    insert_mvp10_portfolio_batch(path, (old,), (items[0],))

    insert_mvp10_portfolio_batch(path, entries, items)

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM portfolio_items").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM evidence_trail_entries").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM source_family_members").fetchone()[0] == 1
        saved_old = EvidenceTrailEntry.model_validate_json(
            conn.execute(
                "SELECT payload_json FROM evidence_trail_entries WHERE trail_entry_id = ?",
                (str(old.trail_entry_id),),
            ).fetchone()[0]
        )
    assert saved_old == old
    conflicting = entries[0].model_copy(update={"source_title": "Different source"})
    with pytest.raises(sqlite3.IntegrityError, match="evidence trail replay conflicts"):
        insert_mvp10_portfolio_batch(path, (conflicting,), ())


def test_legacy_portfolio_uses_retrieval_attempt_for_snapshot_provenance(
    tmp_path: Path,
) -> None:
    path = str(tmp_path / "legacy.sqlite3")
    run_id, attempt_id, snapshot_id, query_id = (uuid4() for _ in range(4))
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="A precise test claim.",
            current_stage=Stage.EVIDENCE_ANALYST,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    with sqlite3.connect(path) as conn:
        conn.execute(
            """INSERT INTO search_queries
               (query_id, run_id, stance, provider, intent, query_round, strategy,
                query_text, exclusion_parameters, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(query_id),
                str(run_id),
                "supporting",
                "exa",
                "broad_web",
                1,
                "fixture",
                "fixture search",
                "{}",
                NOW.isoformat(),
            ),
        )
        conn.execute(
            """INSERT INTO retrieval_attempts
               (retrieval_attempt_id, run_id, query_id, query_round, query_text,
                search_rank, source_url, resolved_url, status, retrieved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(attempt_id),
                str(run_id),
                str(query_id),
                1,
                "fixture search",
                1,
                "https://example.test/source",
                "https://example.test/source",
                "retrieved",
                NOW.isoformat(),
            ),
        )
    retrieval = RetrievalRecord(
        run_id=run_id,
        retrieval_attempt_id=attempt_id,
        query_id=query_id,
        query_round=1,
        query_text="fixture search",
        search_rank=1,
        source_url="https://example.test/source",
        resolved_url="https://example.test/source",
        status=RetrievalStatus.RETRIEVED,
        retrieved_at=NOW,
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=attempt_id,
        snapshot_id=snapshot_id,
        source_url="https://example.test/source",
        retrieved_at=NOW,
        normalized_text="A source text.",
        snapshot_sha256="a" * 64,
        word_count=3,
        truncated=False,
        created_at=NOW,
    )
    outcome = RetrievalOutcome(
        retrieval=retrieval,
        scrape_status=ScrapeStatus.RETRIEVED,
        content_type="text/html",
        snapshot_id=snapshot_id,
        attempts_made=1,
    )
    batch = ResearcherRetrievalBatch.model_construct(
        run_id=run_id,
        stance=Stance.SUPPORTING,
        outcomes=[outcome],
        snapshots=[snapshot],
    )
    researchers = ResearcherPairResult.model_construct(
        run_id=run_id,
        supporting=ResearcherStageResult.model_construct(
            run_id=run_id,
            stance="supporting",
            status=ResearcherSideStatus.COMPLETED,
            retrieval_batch=batch,
        ),
        opposing=ResearcherStageResult.model_construct(
            run_id=run_id,
            stance="opposing",
            status=ResearcherSideStatus.SKIPPED,
        ),
    )
    analysis = AnalysisStageResult(
        run_id=run_id,
        analyst_decisions=(),
        statement_drafts=(),
        reviewer_decisions=(),
        ledger_records=(),
    )
    _persist_mvp10_portfolio(
        path,
        PlannerOutput.model_construct(run_id=run_id),
        researchers,
        analysis,
        lambda: NOW,
        stopping_reason="Fixture complete.",
    )
    (saved,) = read_evidence_trail_entries(path, run_id)
    assert saved.snapshot_status == "snapshotted"
    assert saved.snapshot_sha256 == snapshot.snapshot_sha256
    assert saved.source_family is not None


@pytest.mark.parametrize(
    "artifact_key",
    [
        V2_PRODUCTION_ARTIFACT_KEY,
        V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
        V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    ],
)
def test_history_projects_terminal_result_without_resuming_or_mutating(
    tmp_path: Path,
    artifact_key: str,
) -> None:
    path, run_id, result = _terminal_run(tmp_path)
    insert_v2_artifact(path, artifact_key, result, NOW)
    before = Path(path).read_bytes()

    (item,) = history(path)

    assert item.status == "blocked"
    assert item.updated_at == NOW.isoformat()
    assert item.completed_at == NOW.isoformat()
    assert Path(path).read_bytes() == before
    assert read_run(path, run_id).status is RunStatus.RUNNING
