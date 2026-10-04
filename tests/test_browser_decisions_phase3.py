"""Public browser filters distinguish pending evidence from explicit decisions."""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from researchassistant.evidence.evidence_browser import (
    EvidenceBrowserFilter,
    EvidenceStage,
    browse_evidence_run,
)
from researchassistant.research.fixture_pipeline import FixturePipelineResult, run_fixture_pipeline

_ROOT = Path(__file__).resolve().parents[1]
_VALID = _ROOT / "tests" / "fixtures" / "basic_valid_run"


def _mutable_fixture_copy(tmp_path: Path) -> tuple[Path, FixturePipelineResult]:
    result = run_fixture_pipeline(_VALID, output_dir=tmp_path / "source")
    database = tmp_path / "decision-state.sqlite3"
    shutil.copyfile(result.db_path, database)
    return database, result


@contextmanager
def _temporarily_mutable(connection: sqlite3.Connection, tables: set[str]) -> Iterator[None]:
    rows = connection.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    saved = []
    for name, table, sql in rows:
        if table in tables:
            escaped = name.replace('"', '""')
            connection.execute(f'DROP TRIGGER "{escaped}"')
            saved.append(sql)
    try:
        yield
    finally:
        for sql in saved:
            connection.execute(sql)


def test_pending_candidate_is_not_returned_by_explicit_rejection_filter(
    tmp_path: Path,
) -> None:
    database, result = _mutable_fixture_copy(tmp_path)
    candidate = result.candidates[0]
    with closing(sqlite3.connect(database)) as connection:
        with _temporarily_mutable(
            connection,
            {
                "analyst_decisions",
                "statement_drafts",
                "statement_review_attempts",
                "ledger_records",
                "synthesis_items",
                "portfolio_items",
            },
        ):
            connection.execute(
                "DELETE FROM synthesis_items WHERE ledger_claim_id IN "
                "(SELECT ledger_claim_id FROM ledger_records WHERE run_id=? AND quote_block_id=?)",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM portfolio_items WHERE ledger_claim_id IN "
                "(SELECT ledger_claim_id FROM ledger_records WHERE run_id=? AND quote_block_id=?)",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM ledger_records WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM statement_review_attempts WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM statement_drafts WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM analyst_decisions WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
        connection.commit()

    pending = browse_evidence_run(database, result.run_id).trails[0]
    assert pending.candidate.quote_block_id == candidate.quote_block_id
    assert pending.analyst_decision is None
    assert pending.reviewer_decisions == ()
    assert pending.artifact_label == "Not released"
    rejected = browse_evidence_run(database, result.run_id, EvidenceBrowserFilter(approved=False))
    assert candidate.quote_block_id not in {
        trail.candidate.quote_block_id for trail in rejected.trails
    }


def test_explicit_analyst_rejection_is_filterable_at_analyst_stage(tmp_path: Path) -> None:
    database, result = _mutable_fixture_copy(tmp_path)
    candidate = result.candidates[0]
    with closing(sqlite3.connect(database)) as connection:
        with _temporarily_mutable(
            connection,
            {"analyst_decisions", "ledger_records", "synthesis_items", "portfolio_items"},
        ):
            connection.execute(
                "DELETE FROM synthesis_items WHERE ledger_claim_id IN "
                "(SELECT ledger_claim_id FROM ledger_records WHERE run_id=? AND quote_block_id=?)",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM portfolio_items WHERE ledger_claim_id IN "
                "(SELECT ledger_claim_id FROM ledger_records WHERE run_id=? AND quote_block_id=?)",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM ledger_records WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "UPDATE analyst_decisions SET approved=0, ledger_score=NULL, placement=NULL "
                "WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
        connection.commit()

    rejected = browse_evidence_run(
        database,
        result.run_id,
        EvidenceBrowserFilter(stage=EvidenceStage.ANALYST, approved=False),
    )
    trail = next(
        item
        for item in rejected.trails
        if item.candidate.quote_block_id == candidate.quote_block_id
    )
    assert trail.analyst_decision is not None and trail.analyst_decision.approved is False
    assert trail.artifact_label == "Rejected by Analyst — not released"


def test_explicit_reviewer_rejection_is_filterable_at_reviewer_stage(tmp_path: Path) -> None:
    database, result = _mutable_fixture_copy(tmp_path)
    candidate = result.candidates[0]
    with closing(sqlite3.connect(database)) as connection:
        with _temporarily_mutable(
            connection,
            {"statement_review_attempts", "ledger_records", "synthesis_items", "portfolio_items"},
        ):
            connection.execute(
                "DELETE FROM synthesis_items WHERE ledger_claim_id IN "
                "(SELECT ledger_claim_id FROM ledger_records WHERE run_id=? AND quote_block_id=?)",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM portfolio_items WHERE ledger_claim_id IN "
                "(SELECT ledger_claim_id FROM ledger_records WHERE run_id=? AND quote_block_id=?)",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "DELETE FROM ledger_records WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
            connection.execute(
                "UPDATE statement_review_attempts SET approved=0, reviewer_approval_id=NULL, "
                "approved_factual_statement=NULL, failure_code='not_entailed' "
                "WHERE run_id=? AND quote_block_id=?",
                (str(result.run_id), str(candidate.quote_block_id)),
            )
        connection.commit()

    rejected = browse_evidence_run(
        database,
        result.run_id,
        EvidenceBrowserFilter(stage=EvidenceStage.REVIEWER, approved=False),
    )
    trail = next(
        item
        for item in rejected.trails
        if item.candidate.quote_block_id == candidate.quote_block_id
    )
    assert trail.reviewer_decisions
    assert all(not decision.approved for decision in trail.reviewer_decisions)
    assert trail.artifact_label == "Rejected by Reviewer — not released"


def test_explicit_approval_is_filterable_and_pending_is_not_decided(tmp_path: Path) -> None:
    database, result = _mutable_fixture_copy(tmp_path)
    candidate = result.candidates[1]
    approved = browse_evidence_run(
        database,
        result.run_id,
        EvidenceBrowserFilter(stage=EvidenceStage.ANALYST, approved=True),
    )
    trail = next(
        item
        for item in approved.trails
        if item.candidate.quote_block_id == candidate.quote_block_id
    )
    assert trail.analyst_decision is not None and trail.analyst_decision.approved is True
    assert trail.reviewer_decisions and all(item.approved for item in trail.reviewer_decisions)
