from __future__ import annotations

from pathlib import Path

import pytest

from evidence_browser import (
    EvidenceBrowserError,
    EvidenceBrowserFilter,
    EvidenceStage,
    _artifact_label,
    browse_evidence_run,
    trace_released_statement,
)
from orchestrator import run_fixture_pipeline

_ROOT = Path(__file__).resolve().parents[1]
_VALID = _ROOT / "tests" / "fixtures" / "basic_valid_run"
_INVALID = _ROOT / "tests" / "fixtures" / "invalid_release_run"


def test_browser_traces_each_released_statement_to_snapshot_and_approval(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_VALID, output_dir=tmp_path / "released")

    browser = browse_evidence_run(result.db_path, result.run_id)

    assert len(browser.trails) == len(result.candidates)
    assert len(browser.released_statement_traces) == len(result.ledger_records)
    trace = trace_released_statement(browser, result.ledger_records[0].ledger_claim_id)
    assert (
        trace.ledger_record.approved_factual_statement
        == result.ledger_records[0].approved_factual_statement
    )
    assert trace.reviewer_decision.approved is True
    assert trace.candidate.snapshot_id == trace.snapshot.snapshot_id
    assert browser.trusted_snapshot_text_label.startswith("Trusted")
    assert browser.provider_metadata_label.endswith("non-authoritative)")


def test_browser_filters_by_stance_stage_url_approval_and_release(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_VALID, output_dir=tmp_path / "released")
    first = result.candidates[0]

    assert (
        len(
            browse_evidence_run(
                result.db_path,
                result.run_id,
                EvidenceBrowserFilter(stance=first.stance.value),
            ).trails
        )
        == 1
    )
    assert (
        len(
            browse_evidence_run(
                result.db_path,
                result.run_id,
                EvidenceBrowserFilter(stage=EvidenceStage.LEDGER, approved=True, released=True),
            ).trails
        )
        == 2
    )
    assert (
        len(
            browse_evidence_run(
                result.db_path, result.run_id, EvidenceBrowserFilter(source_url=first.source_url)
            ).trails
        )
        == 1
    )


def test_blocked_run_is_labeled_not_released_and_rejected_label_is_explicit(
    tmp_path: Path,
) -> None:
    result = run_fixture_pipeline(_INVALID, output_dir=tmp_path / "blocked")

    browser = browse_evidence_run(result.db_path, result.run_id)

    assert browser.released_statement_traces == ()
    assert all(trail.artifact_label == "Not released" for trail in browser.trails)
    assert _artifact_label(None, (), False) == "Not released"


def test_browser_missing_and_corrupt_databases_fail_without_creating_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(EvidenceBrowserError, match="cannot open"):
        browse_evidence_run(missing, __import__("uuid").uuid4())
    assert not missing.exists()

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(EvidenceBrowserError, match="cannot open"):
        browse_evidence_run(corrupt, __import__("uuid").uuid4())
    assert corrupt.read_bytes() == b"not a sqlite database"


def test_browser_redacts_provider_request_material_by_not_exposing_it(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_VALID, output_dir=tmp_path / "released")

    browser = browse_evidence_run(result.db_path, result.run_id)
    serialized = browser.model_dump_json()

    assert "authorization" not in serialized.lower()
    assert "mimo_api_key" not in serialized.lower()
    assert "provider request headers" not in serialized.lower()


def test_browser_does_not_mutate_database_bytes(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_VALID, output_dir=tmp_path / "released")
    database = Path(result.db_path)
    before = database.read_bytes()

    browse_evidence_run(database, result.run_id)

    assert database.read_bytes() == before
