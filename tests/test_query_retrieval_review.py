from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from test_query_execution import _action, _clock, _freeze
from test_query_retrieval_depth import _body, _retrieval, _serp_adapter

from providers.search import SearchResponse, SearchResult
from providers.serpsearch import SerpSearchAdapter
from researchassistant.contracts.discovery_v2 import V2CompiledQueryAction
from researchassistant.contracts.model_contracts import DiscoveryProvider, StrictModel
from researchassistant.contracts.model_research import (
    V2PersistedArtifact,
    canonical_v2_artifact_json,
    v2_payload_fingerprint,
)
from researchassistant.contracts.query_retrieval import V2QueryRetrievalResult
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import execute_query
from researchassistant.storage import store as store_module
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact


def _execute(
    path: Path, run_id: UUID, action: V2CompiledQueryAction, adapter: SerpSearchAdapter
) -> SearchResponse:
    return execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.SERPSEARCH,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.SERPSEARCH: adapter},
        clock=_clock(),
    )


def test_checksum_valid_cached_result_cannot_introduce_uncheckpointed_candidate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "forged-cached-result.sqlite"
    run_id, binding = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _action(run_id, DiscoveryProvider.SERPSEARCH)
    candidate = SearchResult(
        original_url="https://forged.example/paper",
        title="Forged cached result",
        rank=1,
    )
    cached = V2QueryRetrievalResult(
        run_id=run_id,
        operation_id=action.artifact_id,
        binding_fingerprint=binding.fingerprint,
        requested_depth=action.requested_depth,
        effective_depth=action.effective_depth,
        raw_hits=1,
        retained_records=1,
        page_count=1,
        stopping_reason="depth_reached",
        response=SearchResponse(results=[candidate]),
    )
    # insert_v2_artifact computes a valid canonical payload checksum. The forged
    # result still has no owned physical page or response provenance.
    insert_v2_artifact(
        str(path), f"metadata-retrieval-v2:{action.artifact_id}:result", cached, _clock()()
    )

    with pytest.raises(ValueError, match="differs from owned parsed pages"):
        _execute(path, run_id, action, _serp_adapter(lambda _: httpx.Response(200, json=_body())))


def test_checksum_valid_forged_page_cannot_replace_owned_response_candidate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "forged-cached-page.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _action(run_id, DiscoveryProvider.SERPSEARCH)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_body())

    adapter = _serp_adapter(handler)
    _execute(path, run_id, action, adapter)
    page_key = f"metadata-retrieval-v2:{action.artifact_id}:page:1"
    page_artifact = read_v2_artifact(str(path), run_id, page_key)
    from researchassistant.contracts.query_retrieval import V2QueryPageCheckpoint

    page = V2QueryPageCheckpoint.model_validate_json(page_artifact.payload_json)
    invented = SearchResult(
        original_url="https://forged.example/not-in-provider-response",
        title="Invented candidate",
        rank=1,
    )
    forged = page.model_copy(
        update={"response": page.response.model_copy(update={"results": [invented]})}
    )
    payload = canonical_v2_artifact_json(forged)
    # Model a checksum-valid page rewrite while preserving the real immutable
    # physical attempt and response hash. The parser receipt remains unchanged.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER v2_artifacts_immutable_update")
        connection.execute(
            "UPDATE v2_artifacts SET payload_json = ?, payload_sha256 = ? "
            "WHERE run_id = ? AND artifact_key = ?",
            (payload, v2_payload_fingerprint(payload), str(run_id), page_key),
        )

    with pytest.raises(ValueError, match="immutable parser receipt"):
        _execute(path, run_id, action, adapter)


def test_serp_physical_ten_hits_are_counted_when_requested_depth_is_five(
    tmp_path: Path,
) -> None:
    path = tmp_path / "serp-physical-ten-requested-five.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    conceptual = _action(run_id, DiscoveryProvider.SERPSEARCH).conceptual_query
    action = compile_query(conceptual, requested_depth=5)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_body(1, 10))

    response = _execute(path, run_id, action, _serp_adapter(handler))
    result = _retrieval(path, run_id, action)

    assert len(seen) == 1
    assert len(response.results) == 5
    assert (result.requested_depth, result.effective_depth) == (5, 5)
    assert (result.raw_hits, result.retained_records, result.page_count) == (10, 5, 1)


def test_malformed_later_page_still_counts_physical_raw_hits(tmp_path: Path) -> None:
    path = tmp_path / "serp-malformed-later-page-raw-hits.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    shallow = _action(run_id, DiscoveryProvider.SERPSEARCH)
    action = compile_query(shallow.conceptual_query, requested_depth=20)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=_body())
        body = _body(1, 10)
        # Invalid page-local rank makes the adapter reject page 2 after the
        # durable physical completion has recorded its ten returned rows.
        body["organic_results"][0]["position"] = 99  # type: ignore[index]
        return httpx.Response(200, json=body)

    response = _execute(path, run_id, action, _serp_adapter(handler))
    result = _retrieval(path, run_id, action)

    assert len(response.results) == 10
    assert result.stopping_reason == "malformed_page"
    assert result.page_count == 1
    assert result.raw_hits == 20


def test_no_new_results_terminal_checkpoint_resumes_without_a_third_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "serp-no-new-results-resume.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = compile_query(
        _action(run_id, DiscoveryProvider.SERPSEARCH).conceptual_query,
        requested_depth=20,
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_body(1, 10, rank_start=1))

    adapter = _serp_adapter(handler)
    original_insert = store_module.insert_v2_artifact

    def crash_before_result(
        db_path: str,
        artifact_key: str,
        artifact: StrictModel,
        created_at: datetime,
    ) -> V2PersistedArtifact:
        if artifact_key == f"metadata-retrieval-v2:{action.artifact_id}:result":
            raise RuntimeError("simulated crash before terminal result persistence")
        return original_insert(db_path, artifact_key, artifact, created_at)

    monkeypatch.setattr(store_module, "insert_v2_artifact", crash_before_result)
    with pytest.raises(RuntimeError, match="simulated crash"):
        _execute(path, run_id, action, adapter)
    assert len(requests) == 2

    monkeypatch.setattr(store_module, "insert_v2_artifact", original_insert)
    response = _execute(path, run_id, action, adapter)
    result = _retrieval(path, run_id, action)

    assert len(requests) == 2
    assert len(response.results) == result.retained_records == 10
    assert (result.raw_hits, result.page_count, result.stopping_reason) == (
        20,
        2,
        "no_new_results",
    )
