from __future__ import annotations

import json
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from models import (
    CandidateBatch,
    CandidateQuoteBlock,
    LedgerRecord,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    ScoreDecision,
    SourceSnapshot,
    StatementDraft,
    StatementReviewResult,
    SynthesisOutput,
    ValidationErrorCode,
)
from orchestrator import FixturePipelineError, run_fixture_pipeline
from store import read_ledger_record, read_synthesis, read_validation

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VALID_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "basic_valid_run"
_INVALID_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "invalid_release_run"


def test_valid_fixture_releases_brief_with_stable_hash_and_typed_artifacts(
    tmp_path: Path,
) -> None:
    result = run_fixture_pipeline(_VALID_FIXTURE, output_dir=tmp_path / "valid")

    assert result.status == "released"
    assert result.validation_result.valid is True
    assert result.rendered_brief_hash is not None
    assert result.final_brief is not None
    assert "Schools reported higher completion rates" in result.final_brief
    assert isinstance(result.planner_output, PlannerOutput)
    assert all(isinstance(item, RetrievalRecord) for item in result.retrievals)
    assert all(isinstance(item, SourceSnapshot) for item in result.snapshots)
    assert all(isinstance(item, ProvisionalCandidate) for item in result.provisional_candidates)
    assert all(isinstance(item, CandidateQuoteBlock) for item in result.candidates)
    assert all(isinstance(item, CandidateBatch) for item in result.candidate_batches)
    assert all(isinstance(item, ScoreDecision) for item in result.analyst_decisions)
    assert all(isinstance(item, StatementDraft) for item in result.statement_drafts)
    assert all(isinstance(item, StatementReviewResult) for item in result.reviewer_decisions)
    assert all(isinstance(item, LedgerRecord) for item in result.ledger_records)
    assert isinstance(result.synthesis_output, SynthesisOutput)

    second = run_fixture_pipeline(_VALID_FIXTURE, output_dir=tmp_path / "valid")

    assert second.rendered_brief_hash == result.rendered_brief_hash
    assert second.final_brief == result.final_brief


def test_run_id_is_preserved_across_release_relevant_artifacts(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_VALID_FIXTURE, output_dir=tmp_path / "valid")
    run_id = result.run_id

    assert result.planner_output.run_id == run_id
    assert all(item.run_id == run_id for item in result.retrievals)
    assert all(item.run_id == run_id for item in result.snapshots)
    assert all(item.run_id == run_id for item in result.provisional_candidates)
    assert all(item.run_id == run_id for item in result.candidates)
    assert all(item.run_id == run_id for item in result.analyst_decisions)
    assert all(item.run_id == run_id for item in result.statement_drafts)
    assert all(item.run_id == run_id for item in result.reviewer_decisions)
    assert all(item.run_id == run_id for item in result.ledger_records)
    assert result.synthesis_output.run_id == run_id
    assert result.validation_result.run_id == run_id


def test_audit_trail_is_persisted_and_inspectable(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_VALID_FIXTURE, output_dir=tmp_path / "valid")

    audit_payload = json.loads(Path(result.audit_path).read_text(encoding="utf-8"))

    assert len(audit_payload) >= 10
    assert {entry["run_id"] for entry in audit_payload} == {str(result.run_id)}
    assert {entry["stage"] for entry in audit_payload} >= {
        "raw_fixture_input",
        "claim_planner",
        "fixture_snapshots",
        "fixture_provisional_candidates",
        "deterministic_candidate_filter",
        "evidence_analyst",
        "statement_reviewer",
        "claim_ledger",
        "debate_synthesizer",
        "final_renderer_validator",
    }
    assert audit_payload[-1]["status"] == "released"
    assert audit_payload[-1]["artifact_hash"]
    assert audit_payload[-1]["outcome"].startswith("released")


def test_rerun_does_not_duplicate_ledger_or_corrupt_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "valid"
    first = run_fixture_pipeline(_VALID_FIXTURE, output_dir=output_dir)
    first_audit = Path(first.audit_path).read_text(encoding="utf-8")
    first_counts = _run_table_counts(first.db_path, str(first.run_id))

    second = run_fixture_pipeline(_VALID_FIXTURE, output_dir=output_dir)
    second_counts = _run_table_counts(second.db_path, str(second.run_id))

    assert second_counts == first_counts
    assert second_counts["ledger_records"] == len(second.ledger_records)
    assert second_counts["provisional_extractions"] == len(second.provisional_candidates)
    assert Path(second.audit_path).read_text(encoding="utf-8") == first_audit


def test_database_can_reopen_after_run(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_VALID_FIXTURE, output_dir=tmp_path / "valid")

    validation = read_validation(result.db_path, result.run_id)
    synthesis = read_synthesis(result.db_path, result.run_id)
    ledger = read_ledger_record(result.db_path, result.ledger_records[0].ledger_claim_id)

    assert validation.rendered_brief_hash == result.rendered_brief_hash
    assert synthesis == result.synthesis_output
    assert ledger in result.ledger_records


def test_invalid_fixture_is_blocked_with_useful_validation_errors(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_INVALID_FIXTURE, output_dir=tmp_path / "invalid")

    assert result.status == "blocked"
    assert result.final_brief is None
    assert result.rendered_brief_hash is None
    assert result.validation_result.valid is False
    assert any(
        error.code is ValidationErrorCode.ALTERED_STATEMENT
        and "Approved factual statement" in error.message
        for error in result.validation_result.errors
    )
    assert result.audit_trail[-1].status == "blocked"


def test_pipeline_errors_are_explicit_for_missing_fixture_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(_VALID_FIXTURE, broken)
    (broken / "synthesis.json").unlink()

    with pytest.raises(FixturePipelineError, match="missing fixture file"):
        run_fixture_pipeline(broken, output_dir=tmp_path / "out")


def test_pipeline_does_not_touch_network_or_provider_surfaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_network_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden in Phase 6")

    monkeypatch.setattr(socket, "create_connection", fail_network_call)
    result = run_fixture_pipeline(_VALID_FIXTURE, output_dir=tmp_path / "valid")

    assert result.status == "released"
    source_text = "\n".join(
        [
            (_REPO_ROOT / "orchestrator.py").read_text(encoding="utf-8"),
            (_REPO_ROOT / "cli.py").read_text(encoding="utf-8"),
        ]
    )
    forbidden = (
        "requests",
        "urllib",
        "openai",
        "anthropic",
        "google",
        "curl",
        "playwright",
        "os.environ",
    )
    assert not any(token in source_text for token in forbidden)


def test_cli_valid_fixture_exits_zero_and_prints_release(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "run-fixture",
            str(_VALID_FIXTURE),
            "--output-dir",
            str(tmp_path / "valid-cli"),
        ],
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "result: released" in completed.stdout
    assert "final brief:" in completed.stdout
    assert "rendered hash:" in completed.stdout
    assert completed.stderr == ""


def test_cli_invalid_fixture_exits_zero_and_prints_block(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "run-fixture",
            str(_INVALID_FIXTURE),
            "--output-dir",
            str(tmp_path / "invalid-cli"),
        ],
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "result: blocked" in completed.stdout
    assert "validation errors:" in completed.stdout
    assert "altered_statement" in completed.stdout
    assert completed.stderr == ""


def test_cli_malformed_fixture_exits_nonzero(tmp_path: Path) -> None:
    broken = tmp_path / "broken-cli"
    shutil.copytree(_VALID_FIXTURE, broken)
    (broken / "planner.json").write_text("{", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "run-fixture",
            str(broken),
            "--output-dir",
            str(tmp_path / "broken-out"),
        ],
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "fixture pipeline error:" in completed.stderr


def _run_table_counts(db_path: str, run_id: str) -> dict[str, int]:
    tables = (
        "retrieval_attempts",
        "snapshots",
        "provisional_extractions",
        "candidates",
        "analyst_decisions",
        "statement_drafts",
        "statement_review_attempts",
        "ledger_records",
        "validation_runs",
    )
    with sqlite3.connect(db_path) as conn:
        return {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            for table in tables
        }
