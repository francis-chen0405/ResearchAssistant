"""Regression coverage for import order and executable identity after source moves."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from researchassistant.runtime.application_runtime import repository_identity


@pytest.mark.parametrize(
    "first_import",
    [
        "researchassistant.contracts.model_evidence",
        "researchassistant.contracts.model_research",
        "researchassistant.contracts.model_contracts",
    ],
)
def test_contract_modules_load_independently_and_keep_public_exports(first_import: str) -> None:
    # A fresh interpreter avoids hiding forward-reference/import-cycle failures behind
    # pytest's already-populated module cache. Generate schemas without model_rebuild.
    program = f"""
import importlib
import inspect
from pydantic import BaseModel
first = importlib.import_module({first_import!r})
import models
for name in models.__all__:
    contract = getattr(models, name)
    if inspect.isclass(contract) and issubclass(contract, BaseModel):
        contract.model_json_schema()
        owner = importlib.import_module(contract.__module__)
        assert getattr(owner, name) is contract, name
"""
    subprocess.run([sys.executable, "-c", program], check=True)


@pytest.mark.parametrize(
    "relative",
    [
        "researchassistant/contracts/model_contracts.py",
        "researchassistant/contracts/model_research.py",
        "researchassistant/contracts/model_evidence.py",
        "researchassistant/storage/store_schema.py",
        "researchassistant/research/fixture_pipeline.py",
        "researchassistant/research/pipeline_artifacts.py",
        "researchassistant/research/pipeline_compatibility.py",
        "researchassistant/runtime/application_runtime.py",
        "researchassistant/runtime/cli.py",
        "researchassistant/research/v2_orchestrator.py",
        "researchassistant/platform_support/credential_store.py",
        "frontend/live_contracts.py",
        "frontend/live_history.py",
        "frontend/live_progress.py",
    ],
)
def test_extracted_source_changes_invalidate_execution_identity(
    tmp_path: Path, relative: str
) -> None:
    engine = tmp_path / "researchassistant/research/v2_orchestrator.py"
    engine.parent.mkdir(parents=True)
    engine.write_text("# engine\n", encoding="utf-8")
    identity_anchor = tmp_path / "researchassistant/contracts/models.py"
    identity_anchor.parent.mkdir(parents=True)
    identity_anchor.write_text("# stable package source\n", encoding="utf-8")
    source = tmp_path / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# original\n", encoding="utf-8")
    baseline = repository_identity(tmp_path)
    source.write_text("# changed\n", encoding="utf-8")
    changed = repository_identity(tmp_path)
    assert changed != baseline
    (tmp_path / "STATUS.md").write_text("documentation only", encoding="utf-8")
    (tmp_path / "history.sqlite3").write_bytes(b"runtime history")
    assert repository_identity(tmp_path) == changed
    source.unlink()
    assert repository_identity(tmp_path) not in (baseline, changed)


def test_fixture_and_exit_contracts_keep_compatibility_imports() -> None:
    import cli as legacy_cli
    import models as legacy_models
    import orchestrator as legacy_orchestrator
    import researchassistant.contracts.models as canonical_models
    import researchassistant.research.fixture_pipeline as fixture_pipeline
    import researchassistant.research.orchestrator as orchestrator
    import researchassistant.runtime.cli as canonical_cli
    import researchassistant.runtime.cli as cli
    import researchassistant.storage.store as canonical_store
    import store as legacy_store
    from researchassistant.research.pipeline_artifacts import FixturePipelineError
    from researchassistant.runtime.application_runtime import CLIExitCode

    assert legacy_models is canonical_models
    assert legacy_models.RunManifest is canonical_models.RunManifest
    assert legacy_store is canonical_store
    assert legacy_store.init_db is canonical_store.init_db
    assert legacy_orchestrator is orchestrator
    assert legacy_cli is canonical_cli
    assert cli.CLIExitCode is CLIExitCode
    assert orchestrator.run_fixture_pipeline is fixture_pipeline.run_fixture_pipeline
    assert orchestrator.FixturePipelineResult is fixture_pipeline.FixturePipelineResult
    assert orchestrator.FixturePipelineError is FixturePipelineError
    assert fixture_pipeline.FixturePipelineError is FixturePipelineError

    repository_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(repository_root / "cli.py"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_fresh_v2_modules_do_not_import_legacy_agent_helpers() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    fresh_modules = [
        repository_root / "researchassistant/research/v2_orchestrator.py",
        *sorted((repository_root / "agents").glob("v2_*.py")),
    ]
    forbidden = {
        "agents.analyst",
        "agents.researcher",
        "agents.supportingresearcher",
    }

    for path in fresh_modules:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert imported.isdisjoint(forbidden), path


def test_historical_evidence_paths_reexport_neutral_implementations() -> None:
    import agents.analyst as historical_analyst
    import agents.researcher as historical_researcher
    import agents.supportingresearcher as historical_supporting
    import researchassistant.evidence.evidence_analysis as evidence_analysis
    import researchassistant.evidence.evidence_core as evidence_core

    assert historical_researcher.build_source_snapshot is evidence_core.build_source_snapshot
    assert historical_researcher.verify_candidate_against_snapshot is (
        evidence_core.verify_candidate_against_snapshot
    )
    assert historical_analyst.score_candidate is evidence_analysis.score_candidate
    assert historical_analyst.admit_ledger_record is evidence_analysis.admit_ledger_record
    assert historical_supporting.UntrustedSourceText is evidence_core.UntrustedSourceText
