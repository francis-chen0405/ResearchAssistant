"""Read-only native trails reject corrupted source and approval relationships."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from researchassistant.evidence.evidence_browser import EvidenceBrowserError, browse_evidence_run
from researchassistant.research.fixture_pipeline import run_fixture_pipeline

FIXTURE = Path(__file__).parent / "fixtures/basic_valid_run"


@pytest.mark.parametrize(
    ("table", "field", "value"),
    [
        ("snapshots", "normalized_text", "Substituted generated source text."),
        ("snapshots", "run_id", str(uuid4())),
        ("candidates", "snapshot_sha256", "0" * 64),
        ("candidates", "source_url", "https://example.test/different-source"),
        ("ledger_records", "snapshot_sha256", "0" * 64),
        ("ledger_records", "approved_claim_text", '[Before.] "Changed quotation." [After.]'),
        ("ledger_records", "approved_factual_statement", "Changed approved statement."),
        ("statement_review_attempts", "approved_factual_statement", "Changed reviewed statement."),
    ],
)
def test_corruption_cannot_be_projected_as_trusted_released_evidence(
    tmp_path: Path,
    table: str,
    field: str,
    value: str,
) -> None:
    result = run_fixture_pipeline(FIXTURE, output_dir=tmp_path / "generated")
    path = Path(result.db_path)
    assert len(browse_evidence_run(path, result.run_id).released_statement_traces) == 2
    connection = sqlite3.connect(path)
    try:
        triggers = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)
        ).fetchall()
        for name, _ in triggers:
            connection.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        connection.execute(
            f"UPDATE {table} SET {field}=? WHERE run_id=?", (value, str(result.run_id))
        )
        for _, sql in triggers:
            connection.execute(sql)
        connection.commit()
    finally:
        connection.close()
    before = path.read_bytes(), path.stat().st_mtime_ns
    if field == "run_id":
        with pytest.raises(EvidenceBrowserError, match="foreign-key integrity"):
            browse_evidence_run(path, result.run_id)
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
        return
    browser = browse_evidence_run(path, result.run_id)
    assert browser.compatibility_issues
    assert not browser.released_statement_traces
    assert not any(trail.released for trail in browser.trails)
    if table in ("snapshots", "candidates", "statement_review_attempts"):
        assert not browser.trails  # No corrupt source/decision is labeled trusted.
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_valid_native_trails_keep_exact_saved_quotes_hashes_and_approvals(tmp_path: Path) -> None:
    result = run_fixture_pipeline(FIXTURE, output_dir=tmp_path / "generated")
    path = Path(result.db_path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    browser = browse_evidence_run(path, result.run_id)
    assert not browser.compatibility_issues
    assert {trace.ledger_record.ledger_claim_id for trace in browser.released_statement_traces} == {
        ledger.ledger_claim_id for ledger in result.ledger_records
    }
    for trace in browser.released_statement_traces:
        assert trace.ledger_record.snapshot_sha256 == trace.snapshot.snapshot_sha256
        assert trace.ledger_record.approved_claim_text == trace.candidate.extracted_quote_block
        assert (
            trace.ledger_record.approved_factual_statement
            == trace.reviewer_decision.approved_factual_statement
        )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
