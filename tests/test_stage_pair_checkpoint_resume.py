"""Paired stage commits and older partial prefixes retain original work on resume."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
import test_product_discovery_pipeline as product
from test_v2_checkpoint_resume import _saved_rows

from researchassistant.agents.round_four_handoffs import V2_POST13_ROUND_FOUR_COMPLETION_KEY
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    StrictModel,
    V2DiscoveryScoutOutput,
)
from researchassistant.providers.llm import LLMStage
from researchassistant.providers.v2_budget import read_v2_physical_call_audit
from researchassistant.research.v2_orchestrator import V2ProductionPipelineResult, V2ProductionState
from researchassistant.storage import v2_transactions
from researchassistant.storage.store import (
    insert_v2_artifact,
    insert_v2_artifact_batch,
    list_runs,
    read_v2_artifact,
)


@pytest.mark.parametrize("legacy_prefix", [False, True])
@pytest.mark.parametrize(
    ("owner", "key"),
    [
        ("v2_discovery", "phase-3-metadata-ranking-round-1"),
        ("v2_acquisition", "metadata-acquisition-v2-round-1"),
        ("round_four_summary", "post-phase-13-round-4-post-plan-facts-v1"),
    ],
)
def test_stage_pairs_resume_without_repeating_completed_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_prefix: bool,
    owner: str,
    key: str,
) -> None:
    path = tmp_path / "generated.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    entry = product.run_v2_production_pipeline

    def advancing(*args: Any, **kwargs: Any) -> V2ProductionPipelineResult:
        kwargs["clock"] = lambda: datetime.now(UTC)
        return entry(*args, **kwargs)

    monkeypatch.setattr(product, "run_v2_production_pipeline", advancing)
    module = import_module("researchassistant.agents." + owner)
    original = module.insert_v2_artifact_batch
    captured = []

    def interrupt(
        database: str, artifacts: tuple[tuple[str, StrictModel, datetime], ...]
    ) -> object:
        if not captured and artifacts[0][0] == key:
            captured.append(artifacts)
            if legacy_prefix:
                insert_v2_artifact(database, *artifacts[0])
            else:
                original(database, artifacts)
            raise KeyboardInterrupt("generated interruption after " + key)
        return original(database, artifacts)

    monkeypatch.setattr(module, "insert_v2_artifact_batch", interrupt)
    with pytest.raises(KeyboardInterrupt):
        product._run(path, controls)
    monkeypatch.setattr(module, "insert_v2_artifact_batch", original)
    partial = list_runs(path)[0]
    before = _saved_rows(path)
    assert key in before
    assert (captured[0][1][0] in before) is (not legacy_prefix)
    audit = read_v2_physical_call_audit(path, partial.run_id)
    resumed, model, search = product._run(path, controls, run_id=partial.run_id)
    assert resumed.state is V2ProductionState.RELEASED, resumed.failure_reason
    after = _saved_rows(path)
    assert {name: after[name] for name in before} == before
    current = read_v2_physical_call_audit(path, partial.run_id)
    assert current.starts[: len(audit.starts)] == audit.starts
    assert current.completions[: len(audit.completions)] == audit.completions
    assert resumed.budget.physical_calls_used == len(audit.starts) + len(model.requests)
    if owner in {"v2_discovery", "v2_acquisition"}:
        assert all(
            request.compiled_query.conceptual_query.round_number > 1 for request in search.requests
        )
        first_round_items = set(
            item.item_id
            for item in V2DiscoveryScoutOutput.model_validate_json(
                read_v2_artifact(path, partial.run_id, "phase-4-discovery-scout").payload_json
            ).items
        )
        assert not any(
            request.stage is LLMStage.SCOUT
            and any(item.item_id in first_round_items for item in request.input_artifact.candidates)
            for request in model.requests
        )
    else:
        assert not search.requests
        completed = read_v2_artifact(path, partial.run_id, V2_POST13_ROUND_FOUR_COMPLETION_KEY)
        assert (
            key in before
            and captured[0][0][1].model_dump(mode="json")
            == (json.loads(completed.payload_json)["post_plan_facts"])
        )


def test_artifact_pair_failure_rolls_back_both_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real current run supplies a valid immutable artifact and identity.
    path = tmp_path / "generated.sqlite3"
    result, _, _ = product._run(
        path, ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    )
    assert result.state is V2ProductionState.RELEASED
    original = v2_transactions._insert_v2_artifact_on_connection
    calls = []

    def fail_second(*args: Any, **kwargs: Any) -> object:
        calls.append(args[1])
        if len(calls) == 2:
            raise RuntimeError("generated failure between paired writes")
        return original(*args, **kwargs)

    saved = read_v2_artifact(path, result.run_id, "phase-4-discovery-scout")
    artifact = V2DiscoveryScoutOutput.model_validate_json(saved.payload_json)
    monkeypatch.setattr(v2_transactions, "_insert_v2_artifact_on_connection", fail_second)
    with pytest.raises(RuntimeError, match="between paired writes"):
        insert_v2_artifact_batch(
            str(path),
            (
                ("generated-first", artifact, saved.created_at),
                ("generated-second", artifact, saved.created_at),
            ),
        )
    for key in ("generated-first", "generated-second"):
        with pytest.raises(KeyError):
            read_v2_artifact(path, result.run_id, key)
