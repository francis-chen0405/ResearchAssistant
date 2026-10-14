"""Ownership moves preserve the public objects and pre-move validation surface."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from researchassistant.contracts.search import SearchRequest, SearchResponse, SearchResult

FIXTURE = Path(__file__).parent / "fixtures/contract-ownership-before.json"
BEFORE: dict[str, Any] = json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("qualified", BEFORE)
def test_public_contract_keeps_original_schema_config_and_enum_values(qualified: str) -> None:
    module, name = qualified.rsplit(".", 1)
    contract = getattr(importlib.import_module(module), name)
    expected = BEFORE[qualified]
    if "schema_sha256" in expected:
        schema = json.dumps(contract.model_json_schema(), sort_keys=True).encode()
        assert sha256(schema).hexdigest() == expected["schema_sha256"]
        assert contract.model_config == expected["config"]
    else:
        assert {item.name: item.value for item in contract} == expected["values"]
    owner = importlib.import_module(contract.__module__)
    assert getattr(owner, name) is contract
    # Historical installed namespaces must expose the same class, not subclasses.
    for prefix in ("providers", "agents"):
        if module.startswith("researchassistant." + prefix + "."):
            alias = importlib.import_module(module.removeprefix("researchassistant."))
            assert getattr(alias, name) is contract


@pytest.mark.parametrize(
    "first",
    ["search", "neighborhood", "query_retrieval", "retrieval", "extraction", "provider_results"],
)
def test_neutral_contract_imports_and_schemas_need_no_adapters_or_agents(first: str) -> None:
    program = f"""
import importlib, inspect, sys
from pydantic import BaseModel
class BlockExecution:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('researchassistant.providers', 'researchassistant.agents',
                                'providers', 'agents')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockExecution())
module = importlib.import_module('researchassistant.contracts.' + {first!r})
for value in vars(module).values():
    if inspect.isclass(value) and issubclass(value, BaseModel):
        value.model_json_schema()
assert 'researchassistant.research.orchestrator' not in sys.modules
assert 'researchassistant.research.historical_execution' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", program], check=True)


def test_compiled_request_validation_needs_only_neutral_contracts_at_call_time() -> None:
    program = """
import sys
from uuid import UUID
class BlockExecution:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('researchassistant.providers', 'researchassistant.agents',
                                'researchassistant.research', 'providers', 'agents')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockExecution())
from pydantic import ValidationError
from researchassistant.contracts.discovery_v2 import V2ConceptGroup, V2ConceptualQuery, discovery_id
from researchassistant.contracts.model_contracts import DiscoveryProvider, SearchIntent
from researchassistant.contracts.research_directions import ResearchDirection
from researchassistant.contracts.query_compiler import compile_query
from researchassistant.contracts.search import SearchRequest
run_id = UUID(int=1)
query = V2ConceptualQuery(run_id=run_id, artifact_id=discovery_id(run_id, 'V2ConceptualQuery', 'q'),
    identity_key='q', required_concepts=(V2ConceptGroup(concept='crime prevention'),),
    purpose='broad', direction=ResearchDirection.SUPPORT, provider=DiscoveryProvider.OPENALEX,
    round_number=1)
compiled = compile_query(query)
request = SearchRequest(run_id=run_id, provider=DiscoveryProvider.OPENALEX,
    intent=SearchIntent.ACADEMIC_STUDY, query_text=compiled.query_text, limit=3,
    compiled_query=compiled)
assert SearchRequest.model_validate_json(request.model_dump_json()) == request
forged = compiled.model_copy(update={'compiler_identity': 'forged'})
try:
    SearchRequest(run_id=run_id, provider=DiscoveryProvider.OPENALEX,
        intent=SearchIntent.ACADEMIC_STUDY, query_text=forged.query_text, limit=3,
        compiled_query=forged)
except ValidationError:
    pass
else:
    raise AssertionError('forged compiler accepted')
"""
    subprocess.run([sys.executable, "-c", program], check=True)


def test_search_serialized_bytes_frozen_fields_and_validation_remain_compatible() -> None:
    response = SearchResponse(
        results=[SearchResult(original_url="https://example.org/work", title="Study")],
        cost_usd="0.0010",
        next_cursor="YWJj",
    )
    assert response.model_dump_json() == (
        '{"results":[{"original_url":"https://example.org/work","title":"Study","rank":1,'
        '"relevance_score":null,"snippet":null,"metadata":{"engine":null,"provider_page":null,'
        '"raw_provider_rank":null,"published_at":null,"display_url":null,"category":null,'
        '"author":null,"abstract":null,"external_id":null,"doi":null,"cited_by_count":null,'
        '"is_open_access":null,"work_type":null,"is_retracted":null,"pdf_url":null,'
        '"full_text_url":null}}],"provider_name":"unknown","provider_version":"unknown",'
        '"adapter_version":"unknown","engine_telemetry":[],"warnings":[],"degraded_pool":false,'
        '"request_id":null,"search_type":null,"cost_usd":"0.0010","next_cursor":"YWJj"}'
    )
    assert SearchResponse.model_validate_json(response.model_dump_json()) == response
    with pytest.raises(ValidationError, match="frozen"):
        response.provider_name = "changed"
    for url in ("relative", "https://user:secret@example.org/work"):
        with pytest.raises(ValidationError):
            SearchResult(original_url=url)
    for cursor in ("*", "https://example.org/next", "A", "abc def"):
        with pytest.raises(ValidationError):
            SearchResponse(results=[], next_cursor=cursor)
    with pytest.raises(ValidationError):
        SearchRequest(query_text="study", limit=3, semantic=True)
