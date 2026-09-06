"""Regression coverage for import order and executable identity after source moves."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from application_runtime import repository_identity


@pytest.mark.parametrize("first_import", ["model_evidence", "model_research", "model_contracts"])
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
        "model_contracts.py",
        "model_research.py",
        "model_evidence.py",
        "store_schema.py",
        "fixture_pipeline.py",
        "pipeline_artifacts.py",
        "application_runtime.py",
        "frontend/live_contracts.py",
        "frontend/live_history.py",
        "frontend/live_progress.py",
    ],
)
def test_extracted_source_changes_invalidate_execution_identity(
    tmp_path: Path, relative: str
) -> None:
    (tmp_path / "v2_orchestrator.py").write_text("# engine\n", encoding="utf-8")
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
    import cli
    import fixture_pipeline
    import orchestrator
    from application_runtime import CLIExitCode
    from pipeline_artifacts import FixturePipelineError

    assert cli.CLIExitCode is CLIExitCode
    assert orchestrator.run_fixture_pipeline is fixture_pipeline.run_fixture_pipeline
    assert orchestrator.FixturePipelineResult is fixture_pipeline.FixturePipelineResult
    assert orchestrator.FixturePipelineError is FixturePipelineError
    assert fixture_pipeline.FixturePipelineError is FixturePipelineError
