from __future__ import annotations

from pathlib import Path

from frontend.streamlit_app import (
    FrontendRunSummary,
    discover_fixture_runs,
    run_fixture_for_frontend,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures"
_VALID_FIXTURE = _FIXTURE_ROOT / "basic_valid_run"
_INVALID_FIXTURE = _FIXTURE_ROOT / "invalid_release_run"


def test_fixture_discovery_finds_expected_fixture_runs() -> None:
    fixtures = discover_fixture_runs(_FIXTURE_ROOT)

    fixture_names = {fixture.name for fixture in fixtures}

    assert {"basic_valid_run", "invalid_release_run"} <= fixture_names
    assert ".phase6_output" not in fixture_names
    assert all(Path(fixture.path).is_dir() for fixture in fixtures)


def test_frontend_wrapper_runs_valid_fixture(tmp_path: Path) -> None:
    summary = run_fixture_for_frontend(_VALID_FIXTURE, output_dir=tmp_path / "valid")

    assert isinstance(summary, FrontendRunSummary)
    assert summary.status == "released"
    assert summary.validation.valid is True
    assert summary.validation.rendered_brief_hash is not None
    assert summary.validation.validation_artifact_hash is not None
    assert summary.final_brief is not None
    assert "Schools reported higher completion rates" in summary.final_brief
    assert summary.block_reason is None
    assert summary.counts.ledger_records >= 1
    assert summary.metadata.fixture_name == "basic_valid_run"


def test_frontend_wrapper_runs_invalid_fixture(tmp_path: Path) -> None:
    summary = run_fixture_for_frontend(_INVALID_FIXTURE, output_dir=tmp_path / "invalid")

    assert summary.status == "blocked"
    assert summary.validation.valid is False
    assert summary.validation.rendered_brief_hash is None
    assert summary.validation.validation_artifact_hash is not None
    assert summary.final_brief is None
    assert summary.block_reason is not None
    assert "altered_statement" in summary.block_reason
    assert any(error.code == "altered_statement" for error in summary.validation.errors)


def test_frontend_summary_contains_structured_display_information(tmp_path: Path) -> None:
    summary = run_fixture_for_frontend(_VALID_FIXTURE, output_dir=tmp_path / "structured")

    assert summary.run_id == "60000000-0000-0000-0000-000000000001"
    assert summary.raw_claim
    assert summary.counts.retrievals == 2
    assert summary.counts.snapshots == 2
    assert summary.counts.provisional_candidates == 2
    assert summary.counts.audit_entries == len(summary.audit_trail)
    assert summary.metadata.db_path.endswith("fixture_pipeline.sqlite3")
    assert summary.metadata.audit_path.endswith("audit.json")
    assert summary.metadata.result_path.endswith("result.json")
    assert summary.validation.validator_config_version
