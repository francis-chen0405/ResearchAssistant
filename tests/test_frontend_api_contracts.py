"""Offline wire examples and generated renderer contracts stay tied to the API."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from api_contract_support import contract_inventory
from fastapi.testclient import TestClient
from test_mlp3_api import FakeController, FakeServices
from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run
from test_v2_phase11_final_output import _continuation, _synthesis

from researchassistant.agents.v2_final_output import build_v2_final_research_output
from researchassistant.api import api
from researchassistant.storage.store import insert_v2_artifact

ROOT = Path(__file__).resolve().parents[1]


def generator() -> ModuleType:
    path = ROOT / "frontend/scripts/generate_api_contracts.py"
    spec = importlib.util.spec_from_file_location("frontend_api_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_frontend_types_match_live_backend() -> None:
    module = generator()
    document = module.backend_contract()
    generated = module.render_contract(document)
    assert module.OUTPUT.read_text() == generated, "Run frontend/scripts/generate_api_contracts.py"
    # Serializer and catalog fallbacks must expose fields, never unknown blobs.
    for name in (
        "ModelOptionsPayload",
        "V2FinalResearchOutput",
        "ResearchTrailItem",
        "V2PreviewResult",
    ):
        assert document["components"]["schemas"][name].get("properties"), name


def test_schema_generation_preserves_nullable_defaults_and_rejects_unknown_structure() -> None:
    module = generator()
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "state": {"enum": ["starting", "released"]},
            "usage": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None},
        },
        "required": ["state"],
    }
    generated = module.ts_type(schema)
    assert '"state": "starting" | "released"' in generated
    assert '"usage"?: (number | null)' in generated
    with pytest.raises(ValueError, match="Unsupported structural"):
        module.ts_type({"type": "object", "patternProperties": {".*": {"type": "number"}}})


def test_successful_offline_payloads_satisfy_renderer_types(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Compile real JSON responses against client types, including a released run.

    Python-only environments skip the JS check; the independent frontend CI job
    installs both runtimes and therefore executes it, without native packaging.
    """
    node = shutil.which("node")
    compiler = ROOT / "frontend/node_modules/typescript/bin/tsc"
    if node is None or not compiler.exists():
        pytest.skip("Frontend contract compilation requires installed Node/TypeScript")
    inventory = contract_inventory(monkeypatch, tmp_path)
    examples: list[tuple[str, object]] = []
    response_types = {
        "/api/model-profiles": "ModelProfile[]",
        "/api/model-options": "ModelOptions",
        "/api/configuration": "Configuration",
        "/api/configuration/check": "Configuration",
        "/api/preferences": "InterfaceSettings",
        "/api/service": "ServiceDiagnostic",
        "/api/service/start": "ServiceDiagnostic",
        "/api/service/stop": "ServiceDiagnostic",
        "/api/history": "{ items: HistoryItem[] }",
    }
    responses = inventory["responses"]
    assert isinstance(responses, list)
    for response in responses:
        if response["status"] != 200:
            continue
        name = response_types.get(response["path"])
        if name:
            examples.append((name, response["body"]))
        if response["path"].endswith("000000000001"):
            examples.append(("RunSnapshot", response["body"]))
    database, admitted = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=admitted,
        continuation=_continuation(admitted.run_id),
        synthesis=_synthesis(admitted),
        created_at=admitted.completed_at,
    )
    insert_v2_artifact(database, api.V2_FINAL_OUTPUT_ARTIFACT_KEY, output, admitted.completed_at)
    controller = FakeController({})
    controller.run_id = admitted.run_id
    runtime = api.ApiRuntime(controller=controller, services=FakeServices(), environment={})
    client = TestClient(
        api.create_app(runtime, load_keychain_on_start=False, allowed_hosts=("testserver",))
    )
    for suffix, name in (
        ("v2-result", "V2FinalResearchOutput"),
        ("v2-evidence", "V2EvidenceDisplay"),
        ("trail", "ResearchTrail"),
    ):
        response = client.get(
            f"/api/research/{admitted.run_id}/{suffix}", params={"db_path": database}
        )
        assert response.status_code == 200, response.text
        examples.append((name, response.json()))
    assert len(examples) >= 12
    imported_types = ", ".join(
        sorted(
            {name.split("[")[0] for name, _ in examples if not name.startswith("{")}
            | {"HistoryItem", "ResearchTrailItem"}
        )
    )
    source = [
        f"import type {{ {imported_types} }} from {json.dumps(str(ROOT / 'frontend/lib/api'))};"
    ]
    source.extend(
        f"const response{index} = {json.dumps(body)} satisfies {name};"
        for index, (name, body) in enumerate(examples)
    )
    # Bad wire values must fail, so this checks that aliases were not weakened
    # to `any`/unknown or a permissive catch-all during schema generation.
    source.extend(
        [
            "// @ts-expect-error Invalid classification is outside the backend enum.",
            'const invalidState: RunSnapshot["classification"] = "invented_state";',
            "// @ts-expect-error A preview is not admitted evidence.",
            'const invalidEvidence: V2EvidenceDisplay["items"][number] = '
            '{ quote_passage: "lead" };',
        ]
    )
    contract_file = tmp_path / "wire-examples.ts"
    contract_file.write_text("\n".join(source))
    result = subprocess.run(
        [
            node,
            str(compiler),
            "--noEmit",
            "--strict",
            "--skipLibCheck",
            "--target",
            "ES2022",
            "--module",
            "ESNext",
            "--moduleResolution",
            "bundler",
            "--typeRoots",
            str(ROOT / "frontend/node_modules/@types"),
            str(contract_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
