"""Advancing-clock resumes preserve intermediate immutable stage checkpoints."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
import test_product_discovery_pipeline as product

from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
from researchassistant.providers.search import SearchFailureCode, SearchProviderError
from researchassistant.providers.v2_budget import read_v2_physical_call_audit
from researchassistant.research.v2_orchestrator import (
    V2ProductionPipelineResult,
    V2ProductionState,
)
from researchassistant.storage.store import list_runs


def _saved_rows(path: Path) -> dict[str, tuple[str, str, str]]:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        return {
            key: (payload, digest, created_at)
            for key, payload, digest, created_at in connection.execute(
                "SELECT artifact_key,payload_json,payload_sha256,created_at FROM v2_artifacts"
            )
        }


@pytest.mark.parametrize(
    ("owner", "key", "empty_round"),
    [
        ("v2_source_selection", "phase-13-complete-survivor-pool-analyzer-admission", False),
        ("v2_source_selection", "source-selection-preview-shortlist-v3", False),
        ("v2_source_selection", "phase-13-source-statuses-analyzer-admission", False),
        ("adaptive_execution", "phase-7-round-2-execution", False),
        ("adaptive_execution", "phase-7-round-3-execution", False),
        ("adaptive_summary", "phase-7-merged-survivor-pool", False),
        ("adaptive_summary", "phase-7-stopping-decision", False),
        ("adaptive_execution", "phase-7-round-2-discovery-scout", True),
        ("adaptive_execution", "phase-7-round-2-acquisition-probe", True),
    ],
)
def test_partial_checkpoint_prefix_resumes_with_original_bytes_and_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner: str, key: str, empty_round: bool
) -> None:
    path = tmp_path / "generated.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    original_entry = product.run_v2_production_pipeline

    def advancing_clock(*args: Any, **kwargs: Any) -> V2ProductionPipelineResult:
        kwargs["clock"] = lambda: datetime.now(UTC)
        return original_entry(*args, **kwargs)

    monkeypatch.setattr(product, "run_v2_production_pipeline", advancing_clock)
    if empty_round:
        original_search = product.phase12._Search.search

        def failed_second_round(self: Any, request: Any) -> object:
            if request.compiled_query.conceptual_query.round_number == 2:
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE, "generated empty second round"
                )
            return original_search(self, request)

        monkeypatch.setattr(product.phase12._Search, "search", failed_second_round)
    module = import_module("researchassistant.agents." + owner)
    original_insert = module.insert_v2_artifact

    def interrupt_after_commit(*args: Any, **kwargs: Any) -> object:
        saved = original_insert(*args, **kwargs)
        if args[1] == key:
            raise KeyboardInterrupt("generated interruption after " + key)
        return saved

    monkeypatch.setattr(module, "insert_v2_artifact", interrupt_after_commit)
    with pytest.raises(KeyboardInterrupt):
        product._run(path, controls)
    monkeypatch.setattr(module, "insert_v2_artifact", original_insert)
    partial = list_runs(path)[0]
    assert partial.status.value == "running"
    before = _saved_rows(path)
    assert key in before
    audit = read_v2_physical_call_audit(path, partial.run_id)
    resumed, model, search = product._run(path, controls, run_id=partial.run_id)
    assert resumed.state is V2ProductionState.RELEASED, resumed.failure_reason
    after = _saved_rows(path)
    assert {key: after[key] for key in before} == before
    assert resumed.budget.physical_calls_used == len(audit.starts) + len(model.requests)
    current = read_v2_physical_call_audit(path, partial.run_id)
    assert current.starts[: len(audit.starts)] == audit.starts
    assert current.completions[: len(audit.completions)] == audit.completions
    if owner == "v2_source_selection":
        # A saved selection cannot repeat Round-1 dispatch. A new assessed
        # evidence gap may still authorize one later search after admission.
        assert all(
            request.compiled_query is not None
            and request.compiled_query.conceptual_query.round_number > 1
            for request in search.requests
        )
