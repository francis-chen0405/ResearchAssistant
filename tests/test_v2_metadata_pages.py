from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from test_discovery_store import _init_run
from test_query_execution import CLAIM, DIRECTIONS, _clock
from test_query_execution import _action as _query_action

from providers.arxiv import ArxivSearchAdapter
from providers.config import ArxivConfig, OpenAlexConfig
from providers.discovery_transport import RequestKind, observe_physical_requests
from providers.openalex import OpenAlexSearchAdapter
from providers.search import (
    SearchRequest,
    metadata_page_size,
    page_parameters,
)
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2MetadataDiscoveryPolicy,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SearchIntent, StrictModel
from researchassistant.contracts.model_research import ResearchDirection, V2PersistedArtifact
from researchassistant.contracts.query_retrieval import V2QueryRetrievalResult
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import execute_query, freeze_query_execution
from researchassistant.storage import store as store_module
from researchassistant.storage.query_retrieval_store import read_pages
from researchassistant.storage.store import read_v2_artifact


class _PageObserver:
    def __init__(self) -> None:
        self.calls: list[tuple[int, RequestKind, dict[str, str | int | bool]]] = []

    def request(
        self,
        request: SearchRequest,
        parameters: Mapping[str, str | int | bool],
        send: Callable[[], httpx.Response],
        *,
        request_kind: RequestKind = "primary",
        before_reservation: Callable[[Callable[[], bool] | None], None] | None = None,
    ) -> httpx.Response:
        if before_reservation is not None:
            before_reservation(None)
        self.calls.append((request.page_number, request_kind, dict(parameters)))
        return send()


def _action(
    provider: DiscoveryProvider, *, mode: str = "lexical", depth: int = 50
) -> V2CompiledQueryAction:
    run_id = uuid4()
    query = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", f"page-{provider.value}-{mode}"),
        identity_key=f"page-{provider.value}-{mode}",
        required_concepts=(V2ConceptGroup(concept="camera enforcement study"),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=provider,
        round_number=1,
    )
    return compile_query(
        query,
        mode=mode,
        requested_depth=depth,
        policy=V2MetadataDiscoveryPolicy(metadata_depth=depth),
    )


def _request(
    action: V2CompiledQueryAction,
    *,
    page: int,
    limit: int,
    cursor: str | None = None,
) -> SearchRequest:
    provider = action.conceptual_query.provider
    return SearchRequest(
        run_id=action.run_id,
        provider=provider,
        intent=(
            SearchIntent.ACADEMIC_STUDY
            if provider
            in {
                DiscoveryProvider.OPENALEX,
                DiscoveryProvider.ARXIV,
                DiscoveryProvider.PUBMED,
            }
            else SearchIntent.BROAD_WEB
        ),
        semantic=action.mode == "semantic",
        query_text=action.query_text,
        limit=limit,
        compiled_query=action,
        page_number=page,
        page_cursor=cursor,
    )


def test_metadata_page_size_is_scoped_to_lexical_openalex_and_arxiv() -> None:
    lexical = _action(DiscoveryProvider.OPENALEX)
    semantic = _action(DiscoveryProvider.OPENALEX, mode="semantic")
    arxiv = _action(DiscoveryProvider.ARXIV)
    pubmed = _action(DiscoveryProvider.PUBMED)
    exa = _action(DiscoveryProvider.EXA, mode="provider_default")

    assert lexical.effective_depth == 50
    assert arxiv.effective_depth == 50
    assert metadata_page_size(lexical) == 20
    assert metadata_page_size(arxiv) == 20
    assert metadata_page_size(semantic) == semantic.effective_depth == 50
    assert metadata_page_size(pubmed) == pubmed.effective_depth == 50
    assert metadata_page_size(exa) == exa.effective_depth


def test_default_successor_depth_remains_twenty_and_one_page() -> None:
    run_id = uuid4()
    query = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", "default-depth"),
        identity_key="default-depth",
        required_concepts=(V2ConceptGroup(concept="camera enforcement study"),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        round_number=1,
    )
    action = compile_query(query, requested_depth=20, policy=V2MetadataDiscoveryPolicy())

    assert action.effective_depth == 20
    assert metadata_page_size(action) == 20


@pytest.mark.parametrize(("page_budget", "expected"), [(1, 20), (2, 40), (3, 50)])
def test_lexical_effective_depth_obeys_successor_page_size(page_budget: int, expected: int) -> None:
    run_id = uuid4()
    query = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", f"budget-{page_budget}"),
        identity_key=f"budget-{page_budget}",
        required_concepts=(V2ConceptGroup(concept="camera enforcement study"),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        round_number=1,
    )
    action = compile_query(
        query,
        requested_depth=50,
        policy=V2MetadataDiscoveryPolicy(metadata_depth=50, max_pages_per_operation=page_budget),
    )

    assert action.effective_depth == expected


def test_openalex_semantic_count_stays_one_fifty_record_page() -> None:
    run_id = uuid4()
    query = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", "semantic-count"),
        identity_key="semantic-count",
        required_concepts=(V2ConceptGroup(concept="camera enforcement study"),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        round_number=1,
    )
    action = compile_query(
        query,
        mode="semantic",
        requested_depth=50,
        policy=V2MetadataDiscoveryPolicy(metadata_depth=50, max_pages_per_operation=1),
    )

    assert action.effective_depth == 50
    assert metadata_page_size(action) == 50


def test_openalex_page_cursor_is_bounded_base64_and_not_a_url() -> None:
    action = _action(DiscoveryProvider.OPENALEX)
    valid_cursor = "++++/w=="
    request = _request(action, page=2, limit=20, cursor=valid_cursor)

    assert page_parameters(request)["per_page"] == 20
    assert page_parameters(request)["cursor"] == valid_cursor
    for invalid in ("https://attacker.invalid/cursor", "a\nb", "x" * 513, "bad.", "a"):
        with pytest.raises(ValidationError):
            _request(action, page=2, limit=20, cursor=invalid)


def test_openalex_depth_50_follows_each_cursor_with_stable_global_ranks() -> None:
    requests: list[httpx.Request] = []
    cursors = ("Y3Vyc29yLTI=", "Y3Vyc29yLTM=", None)
    page = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page
        requests.append(request)
        page += 1
        item = {
            "id": f"https://openalex.org/W{page}",
            "title": f"Page {page} paper",
            "is_retracted": False,
        }
        return httpx.Response(
            200,
            json={"results": [item], "meta": {"next_cursor": cursors[page - 1]}},
        )

    action = _action(DiscoveryProvider.OPENALEX)
    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="fixture-key"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    observer = _PageObserver()
    cursor = None
    responses = []
    with observe_physical_requests(observer):
        for page_number, limit in ((1, 20), (2, 20), (3, 10)):
            response = adapter.search(
                _request(action, page=page_number, limit=limit, cursor=cursor)
            )
            responses.append(response)
            cursor = response.next_cursor

    assert [request.url.params["per_page"] for request in requests] == ["20", "20", "10"]
    assert [request.url.params["cursor"] for request in requests] == [
        "*",
        "Y3Vyc29yLTI=",
        "Y3Vyc29yLTM=",
    ]
    assert [call[0] for call in observer.calls] == [1, 2, 3]
    assert [response.results[0].rank for response in responses] == [1, 21, 41]
    assert [response.results[0].metadata.provider_page for response in responses] == [1, 2, 3]
    assert [response.results[0].metadata.raw_provider_rank for response in responses] == [1, 1, 1]


def test_repeated_cursor_terminal_page_resumes_without_a_third_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "openalex-repeated-cursor-resume.sqlite"
    shallow = _query_action(uuid4(), DiscoveryProvider.OPENALEX)
    action = compile_query(
        shallow.conceptual_query,
        requested_depth=50,
        policy=V2MetadataDiscoveryPolicy(metadata_depth=50),
    )
    run_id = action.run_id
    _init_run(path, run_id)
    freeze_query_execution(
        str(path),
        run_id,
        CLAIM,
        DIRECTIONS,
        (DiscoveryProvider.OPENALEX,),
        _clock(),
        discovery_policy=V2MetadataDiscoveryPolicy(metadata_depth=50),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page_number = len(requests)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": f"https://openalex.org/W{page_number}_{index}",
                        "title": f"Page {page_number} unique paper {index}",
                        "is_retracted": False,
                    }
                    for index in range(20)
                ],
                "meta": {"next_cursor": "Y3Vyc29yLTI="},
            },
        )

    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="fixture-key"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
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
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.OPENALEX: adapter},
            clock=_clock(),
        )

    assert len(requests) == 2
    assert len(read_pages(str(path), run_id)) == 2
    monkeypatch.setattr(store_module, "insert_v2_artifact", original_insert)

    response = execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.OPENALEX,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.OPENALEX: adapter},
        clock=_clock(),
    )

    result_artifact = read_v2_artifact(
        str(path), run_id, f"metadata-retrieval-v2:{action.artifact_id}:result"
    )
    result = V2QueryRetrievalResult.model_validate_json(result_artifact.payload_json)
    assert len(requests) == 2
    assert len(response.results) == result.retained_records == 40
    assert (result.raw_hits, result.page_count, result.stopping_reason) == (
        40,
        2,
        "repeated_cursor",
    )


def test_arxiv_depth_50_uses_twenty_record_offsets_then_ten() -> None:
    requests: list[httpx.Request] = []
    now = 0.0

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        offset = request.url.params["start"]
        body = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            f"<id>https://arxiv.org/abs/2401.{int(offset) + 1:05d}</id>"
            f"<title>Paper at {offset}</title></entry></feed>"
        )
        return httpx.Response(200, text=body)

    action = _action(DiscoveryProvider.ARXIV)
    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
        ),
        monotonic=lambda: now,
        sleep=sleep,
    )
    observer = _PageObserver()
    responses = []
    with observe_physical_requests(observer):
        for page_number, limit in ((1, 20), (2, 20), (3, 10)):
            responses.append(adapter.search(_request(action, page=page_number, limit=limit)))

    assert [(r.url.params["start"], r.url.params["max_results"]) for r in requests] == [
        ("0", "20"),
        ("20", "20"),
        ("40", "10"),
    ]
    assert [call[0] for call in observer.calls] == [1, 2, 3]
    assert [response.results[0].rank for response in responses] == [1, 21, 41]
    assert [response.results[0].metadata.provider_page for response in responses] == [1, 2, 3]
    assert [response.results[0].metadata.raw_provider_rank for response in responses] == [1, 1, 1]
