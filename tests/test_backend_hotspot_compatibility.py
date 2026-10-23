"""Public handoffs keep pre-split schemas, frozen configuration and class identity."""

from __future__ import annotations

import importlib
import json
import pickle
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from review_schema_compatibility import (
    normalize_current_product_capacity,
    verify_review_schema_additions,
)

BEFORE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures/backend-hotspots-before.json").read_text()
)


@pytest.mark.parametrize("qualified", BEFORE)
def test_public_handoff_preserves_schema_config_and_identity(qualified: str) -> None:
    module_name, name = qualified.split(":")
    module = importlib.import_module(module_name)
    contract = getattr(module, name)
    expected = BEFORE[qualified]
    if "schema_sha256" in expected:
        document = contract.model_json_schema()
        verify_review_schema_additions(document)
        normalize_current_product_capacity(document)
        # R35 adds one explicit four-round policy. Keep the frozen fixture and
        # compare all historical schema bytes after verifying just this delta.
        selection = (
            document
            if name == "V2SourceSelectionInput"
            else document.get("$defs", {}).get("V2SourceSelectionInput")
        )
        if selection is not None:
            properties = selection["properties"]
            assert properties["survivors"]["maxItems"] == 100
            assert properties["policy_identity"]["enum"] == [
                "researchassistant-v2-phase-8-source-selection-v1",
                "researchassistant-v2-phase-8-source-selection-v2",
                "researchassistant-v2-phase-8-source-selection-v3",
            ]
            properties["survivors"]["maxItems"] = 75
            properties["policy_identity"]["enum"].pop()
        schema = json.dumps(document, sort_keys=True).encode()
        assert sha256(schema).hexdigest() == expected["schema_sha256"]
        assert contract.model_config == expected["config"]
    elif "enum" in expected:
        assert {name: item.value for name, item in contract.__members__.items()} == expected["enum"]
    # Persisted/public names resolve to the original class, never a wrapper subclass.
    assert contract.__module__ == module_name
    assert getattr(importlib.import_module(contract.__module__), name) is contract
    assert pickle.loads(pickle.dumps(contract)) is contract
    if ".agents." in module_name:
        alias = importlib.import_module(module_name.removeprefix("researchassistant."))
        assert alias is module
        assert getattr(alias, name) is contract
    elif module_name == "researchassistant.research.orchestrator":
        assert importlib.import_module("orchestrator") is module
    elif expected["shared_export"]:
        shared = importlib.import_module("researchassistant.contracts.models")
        assert getattr(shared, name) is contract
        assert getattr(importlib.import_module("models"), name) is contract


@pytest.mark.parametrize(
    "first",
    [
        "policy",
        "planning",
        "discovery",
        "acquisition",
        "coverage",
        "gaps",
        "round_four",
        "selection",
        "historical",
    ],
)
def test_research_contract_import_and_schema_resolution_need_no_execution(first: str) -> None:
    program = f"""
import importlib, inspect, sys
from pydantic import BaseModel
class BlockExecution:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('researchassistant.providers', 'researchassistant.agents',
                                'researchassistant.research', 'providers', 'agents',
                                'orchestrator')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockExecution())
module = importlib.import_module('researchassistant.contracts.research_' + {first!r})
for value in vars(module).values():
    if inspect.isclass(value) and issubclass(value, BaseModel):
        assert value.__pydantic_complete__
        value.model_json_schema()
from researchassistant.contracts import model_research, models
assert model_research.V2InitialPlannerOutput is models.V2InitialPlannerOutput
"""
    subprocess.run([sys.executable, "-c", program], check=True)


def test_pre_split_source_identity_rejects_resume_before_calls_or_rewrites(tmp_path: Path) -> None:
    from test_v2_phase12_production import _routing, _run, _Scraper, _Search, _V2Model

    from researchassistant.runtime.application_runtime import repository_identity

    # Recorded from the live source at the start of Prompt 13, before any split.
    previous = "source-sha256:3768f41771f0fe210ceda310b7867b7963df52c9c8ec1a549b5aec63dc2a577f"
    current = repository_identity()
    assert current != previous
    database = tmp_path / "pre-split.sqlite3"
    routing = _routing().model_copy(update={"repository_revision": previous})
    result = _run(database, _V2Model(), _Search(), _Scraper(), routing_config=routing)
    before = database.read_bytes(), database.stat().st_mtime_ns
    model, search, scraper = _V2Model(), _Search(), _Scraper()
    with pytest.raises(ValueError, match="cross-version v2 resume is forbidden"):
        _run(
            database,
            model,
            search,
            scraper,
            run_id=result.run_id,
            routing_config=routing.model_copy(update={"repository_revision": current}),
        )
    assert model.requests == search.requests == scraper.requests == []
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before
