"""Contract parity, request isolation and snapshot ownership across the API move."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import pytest
from api_contract_support import contract_inventory, registered_routes
from fastapi.testclient import TestClient
from test_mlp3_api import FakeController, FakeServices
from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run
from test_v2_phase11_final_output import _continuation, _synthesis

from researchassistant.agents.v2_final_output import build_v2_final_research_output
from researchassistant.api import api
from researchassistant.api.application_services import result_reads
from researchassistant.contracts.models import ValidationError
from researchassistant.storage.store import ReadOnlyStore, insert_v2_artifact


def test_routes_schemas_and_offline_responses_match_before_split(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = json.loads((Path(__file__).parent / "fixtures/api-contract-before.json").read_text())
    after = contract_inventory(monkeypatch, tmp_path)
    # Prompt 15 adds one independent read-only projection. Preserve the frozen
    # inventory of every pre-existing route/schema/response byte-for-byte.
    routes = after["routes"]
    assert len(routes) == len({(method, path) for method, path, _, _ in routes}) == 22
    lead_path = "/api/research/{run_id}/source-leads"
    assert [row for row in routes if row[1] == lead_path] == [
        ["GET", lead_path, "source_leads", 200]
    ]
    after["routes"] = [row for row in routes if row[1] != lead_path]
    after["openapi"]["paths"].pop(lead_path)
    for name in ("SourceLead", "SourceLeadStage", "SourceLeadsPage"):
        after["openapi"]["components"]["schemas"].pop(name)
    # R21 documents the existing catalog wire projection without changing any
    # response bytes. Compare the rest of the original inventory unchanged.
    for name in ("ModelOptionDisplay", "ModelOptionsResponse"):
        assert name in after["openapi"]["components"]["schemas"]
        after["openapi"]["components"]["schemas"].pop(name)
    catalog = after["openapi"]["paths"]["/api/model-options"]["get"]["responses"]["200"]
    assert catalog["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ModelOptionsResponse"
    }
    catalog["content"]["application/json"]["schema"] = before["openapi"]["paths"][
        "/api/model-options"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    # R27 corrects only the previously documented 422 validation envelopes.
    schemas = after["openapi"]["components"]["schemas"]
    assert schemas.pop("RequestErrorResponse") == {
        "additionalProperties": False,
        "properties": {"detail": {"title": "Detail", "type": "string"}},
        "required": ["detail"],
        "title": "RequestErrorResponse",
        "description": "Redacted HTTP input error; never includes submitted fields or values.",
        "type": "object",
    }
    assert "HTTPValidationError" not in schemas
    for path, methods in before["openapi"]["paths"].items():
        for method, operation in methods.items():
            previous = operation["responses"].get("422")
            current = after["openapi"]["paths"][path][method]["responses"]
            if previous is not None:
                assert current["422"] == {
                    "description": "Validation Error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/RequestErrorResponse"}
                        }
                    },
                }
                current["422"] = previous
    # Removing the default HTTP schema also removes its short-name collision
    # with the real research ValidationError definition.
    research_error = ValidationError.model_json_schema(
        mode="serialization", ref_template="#/components/schemas/{model}"
    )
    research_error.pop("$defs")
    assert schemas["ValidationError"] == research_error
    for name in ("HTTPValidationError", "ValidationError"):
        schemas[name] = before["openapi"]["components"]["schemas"][name]
    assert after == before


def test_every_route_shares_session_host_and_origin_guard() -> None:
    runtime = api.ApiRuntime(controller=FakeController({}), services=FakeServices(), environment={})
    app = api.create_app(
        runtime, load_keychain_on_start=False, allowed_hosts=("testserver",), session_token="a" * 64
    )
    client = TestClient(app)
    for route in registered_routes(app.routes):
        path = route.path.replace("{run_id}", str(UUID(int=1))).replace("{name}", "mimo")
        for method in route.methods:
            response = client.request(method, path)
            assert response.status_code == 401, (method, path)
            assert response.json() == {"detail": "Desktop session required."}
            for headers in (
                {"Origin": "https://outside.example"},
                {"Host": "outside.example"},
            ):
                response = client.request(
                    method, path, headers={"Authorization": "Bearer " + "a" * 64, **headers}
                )
                assert response.status_code == 403, (method, path)


def test_import_facades_create_no_runtime_or_application() -> None:
    script = """
import importlib
from researchassistant.api.live_service import LiveResearchController
from researchassistant.api.service_manager import WigoloServiceManager
def fail(*args: object, **kwargs: object) -> None:
    raise AssertionError("import constructed a global runtime")
LiveResearchController.__init__ = fail
WigoloServiceManager.__init__ = fail
canonical = importlib.import_module("researchassistant.api.api")
compatibility = importlib.import_module("frontend.api")
assert canonical is compatibility
assert "app" not in canonical.__dict__
assert "runtime" not in canonical.__dict__
assert canonical._default_application.cache_info().currsize == 0
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)


def test_legacy_lazy_app_and_runtime_are_one_explicitly_requested_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[api.ApiRuntime] = []

    def factory() -> api.ApiRuntime:
        runtime = api.ApiRuntime(
            controller=FakeController({}), services=FakeServices(), environment={}
        )
        calls.append(runtime)
        return runtime

    monkeypatch.setattr(api, "create_default_runtime", factory)
    api._default_application.cache_clear()
    try:
        first = api.app
        assert api.app is first
        assert api.runtime is calls[0]
        assert len(calls) == 1
        assert len(list(registered_routes(first.routes))) == 22
    finally:
        api._default_application.cache_clear()


@pytest.mark.parametrize("endpoint", ("v2-result", "v2-evidence"))
@pytest.mark.parametrize(
    "artifact_key",
    (
        api.V2_FINAL_OUTPUT_ARTIFACT_KEY,
        api.V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
        api.V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    ),
)
def test_result_requests_use_one_validated_snapshot_and_close_before_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoint: str, artifact_key: str
) -> None:
    database, admitted = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=admitted,
        continuation=_continuation(admitted.run_id),
        synthesis=_synthesis(admitted),
        created_at=admitted.completed_at,
    )
    insert_v2_artifact(database, artifact_key, output, admitted.completed_at)
    expected = (
        output.model_dump(mode="json")
        if endpoint == "v2-result"
        else api._build_v2_evidence_display(output, admitted).model_dump(mode="json")
    )
    before = Path(database).read_bytes()
    open_reader = result_reads.open_read_only_store
    read_artifact = result_reads.read_v2_artifact
    project = result_reads._build_v2_evidence_display
    readers: list[ReadOnlyStore] = []
    connections: list[sqlite3.Connection] = []
    closed: list[bool] = []

    @contextmanager
    def tracked_reader(path: str | Path) -> Iterator[ReadOnlyStore]:
        with open_reader(path) as reader:
            readers.append(reader)
            assert reader.connection.in_transaction
            yield reader
        # Check closure on the request thread that owns this connection.
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            reader.connection.execute("SELECT 1")
        closed.append(True)

    def tracked_artifact(connection: sqlite3.Connection, run_id: UUID, key: str) -> object:
        assert connection.in_transaction
        connections.append(connection)
        return read_artifact(connection, run_id, key)

    def closed_projection(*args: object, **kwargs: object) -> api.V2EvidenceDisplay:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            readers[0].connection.execute("SELECT 1")
        return project(*args, **kwargs)

    monkeypatch.setattr(result_reads, "open_read_only_store", tracked_reader)
    monkeypatch.setattr(result_reads, "read_v2_artifact", tracked_artifact)
    monkeypatch.setattr(result_reads, "_build_v2_evidence_display", closed_projection)
    runtime = api.ApiRuntime(controller=FakeController({}), services=FakeServices(), environment={})
    client = TestClient(
        api.create_app(runtime, load_keychain_on_start=False, allowed_hosts=("testserver",))
    )
    response = client.get(
        f"/api/research/{admitted.run_id}/{endpoint}", params={"db_path": database}
    )
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert len(readers) == 1
    assert connections and all(connection is readers[0].connection for connection in connections)
    assert Path(database).read_bytes() == before
    assert closed == [True]
