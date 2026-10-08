from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from uuid import uuid4

import httpx
import pytest

from providers.arxiv import ArxivSearchAdapter
from providers.config import ArxivConfig, ExaConfig, OpenAlexConfig, PubMedConfig, SerpSearchConfig
from providers.discovery_transport import RequestKind, observe_physical_requests
from providers.exa import ExaSearchAdapter
from providers.openalex import OpenAlexSearchAdapter
from providers.pubmed import PubMedSearchAdapter
from providers.search import SearchRequest
from providers.serpsearch import SerpSearchAdapter
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SearchIntent
from researchassistant.contracts.model_research import ResearchDirection
from researchassistant.research.query_compiler import compile_query


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


def _action(provider: DiscoveryProvider) -> V2CompiledQueryAction:
    run_id = uuid4()
    query = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", f"depth-{provider.value}"),
        identity_key=f"depth-{provider.value}",
        required_concepts=(V2ConceptGroup(concept="camera enforcement study"),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=provider,
        round_number=1,
    )
    return compile_query(query, requested_depth=20)


def _request(
    action: V2CompiledQueryAction,
    *,
    page_number: int,
    limit: int = 10,
    page_cursor: str | None = None,
) -> SearchRequest:
    provider = action.conceptual_query.provider
    academic = provider in {
        DiscoveryProvider.OPENALEX,
        DiscoveryProvider.ARXIV,
        DiscoveryProvider.PUBMED,
    }
    return SearchRequest(
        run_id=action.run_id,
        provider=provider,
        intent=SearchIntent.ACADEMIC_STUDY if academic else SearchIntent.BROAD_WEB,
        semantic=action.mode == "semantic",
        query_text=action.query_text,
        limit=limit,
        compiled_query=action,
        page_number=page_number,
        page_cursor=page_cursor,
    )


def test_openalex_cursor_page_is_observed_and_returns_next_cursor() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "meta": {"next_cursor": "opaque-next-cursor", "cost_usd": 0.001},
                "results": [
                    {
                        "id": "https://openalex.org/W12",
                        "title": "Page two paper",
                        "is_retracted": False,
                    }
                ],
            },
        )

    action = _action(DiscoveryProvider.OPENALEX)
    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="fixture-key"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    observer = _PageObserver()

    with observe_physical_requests(observer):
        response = adapter.search(_request(action, page_number=1, limit=20))

    assert requests[0].url.params["cursor"] == "*"
    assert requests[0].url.params["per_page"] == "20"
    assert observer.calls[0][0:2] == (1, "primary")
    assert response.results[0].rank == 1
    assert response.next_cursor == "opaque-next-cursor"


def test_arxiv_offset_page_keeps_global_rank_and_physical_parameters() -> None:
    requests: list[httpx.Request] = []
    body = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<id>https://arxiv.org/abs/2401.00012</id><title>Page two paper</title>"
        "</entry></feed>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=body)

    action = _action(DiscoveryProvider.ARXIV)
    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
        ),
    )
    observer = _PageObserver()

    with observe_physical_requests(observer):
        response = adapter.search(_request(action, page_number=1, limit=20))

    assert requests[0].url.params["start"] == "0"
    assert requests[0].url.params["max_results"] == "20"
    assert observer.calls[0][0:2] == (1, "primary")
    assert response.results[0].rank == 1


def test_arxiv_spaces_compiled_request_starts_by_three_seconds() -> None:
    now = 0.0
    starts: list[float] = []
    body = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<id>https://arxiv.org/abs/2401.00012</id><title>Paper</title>"
        "</entry></feed>"
    )

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    def handler(_: httpx.Request) -> httpx.Response:
        starts.append(now)
        return httpx.Response(200, text=body)

    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
        ),
        monotonic=lambda: now,
        sleep=sleep,
    )
    observer = _PageObserver()

    with observe_physical_requests(observer):
        adapter.search(_request(_action(DiscoveryProvider.ARXIV), page_number=1, limit=20))
        adapter.search(_request(_action(DiscoveryProvider.ARXIV), page_number=1, limit=20))

    assert len(starts) == 2
    assert starts[1] - starts[0] >= 3.0


def test_pubmed_offset_page_accounts_esearch_and_summary_as_page_two() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["120"]}})
        return httpx.Response(
            200,
            json={"result": {"uids": ["120"], "120": {"title": "Page two PMID"}}},
        )

    action = _action(DiscoveryProvider.PUBMED)
    adapter = PubMedSearchAdapter(
        PubMedConfig(),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov", transport=httpx.MockTransport(handler)
        ),
    )
    observer = _PageObserver()

    with observe_physical_requests(observer):
        response = adapter.search(_request(action, page_number=1, limit=20))

    assert "retstart" not in requests[0].url.params
    assert requests[0].url.params["retmax"] == "20"
    assert [call[0:2] for call in observer.calls] == [(1, "primary"), (1, "metadata")]
    assert observer.calls[0][2]["retmax"] == 20
    assert observer.calls[1][2]["id"] == "120"
    assert response.results[0].rank == 1
    assert response.results[0].metadata.provider_page == 1
    assert response.results[0].metadata.raw_provider_rank == 1


def test_pubmed_paces_each_search_and_summary_request() -> None:
    now = 0.0
    starts: list[float] = []

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(now)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["120"]}})
        return httpx.Response(
            200,
            json={"result": {"uids": ["120"], "120": {"title": "Paper"}}},
        )

    adapter = PubMedSearchAdapter(
        PubMedConfig(),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov", transport=httpx.MockTransport(handler)
        ),
        monotonic=lambda: now,
        sleep=sleep,
    )
    observer = _PageObserver()
    with observe_physical_requests(observer):
        adapter.search(_request(_action(DiscoveryProvider.PUBMED), page_number=1, limit=20))

    assert len(starts) == 2
    assert starts[1] - starts[0] >= 3.0
    assert [kind for _, kind, _ in observer.calls] == ["primary", "metadata"]


@pytest.mark.parametrize(
    ("articleids", "expected"),
    [
        (
            [{"idtype": "pmc", "value": "PMC12345"}],
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC12345/",
        ),
        ([{"idtype": "pmc", "value": "https://evil.example/PMC12345"}], None),
    ],
)
def test_pubmed_adds_only_validated_pmc_locations(
    articleids: list[dict[str, str]], expected: str | None
) -> None:
    adapter = PubMedSearchAdapter(
        PubMedConfig(),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=(
                        {"esearchresult": {"idlist": ["120"]}}
                        if request.url.path.endswith("esearch.fcgi")
                        else {
                            "result": {
                                "uids": ["120"],
                                "120": {"title": "Paper", "articleids": articleids},
                            }
                        }
                    ),
                )
            ),
        ),
    )

    response = adapter.search(
        SearchRequest(
            provider=DiscoveryProvider.PUBMED,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="camera enforcement study",
            limit=10,
        )
    )

    assert response.results[0].metadata.full_text_url == expected


def test_serpsearch_page_number_is_observed_and_fallback_rank_is_global() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"url": "https://example.org/page-two", "title": "Study"},
                    {
                        "url": "https://example.org/page-two-ranked",
                        "title": "Ranked study",
                        "position": 3,
                    },
                ]
            },
        )

    action = _action(DiscoveryProvider.SERPSEARCH)
    adapter = SerpSearchAdapter(
        SerpSearchConfig(api_key="fixture-key"),
        client=httpx.Client(
            base_url="https://api.serpsearch.com", transport=httpx.MockTransport(handler)
        ),
    )
    observer = _PageObserver()

    with observe_physical_requests(observer):
        response = adapter.search(_request(action, page_number=2))

    assert requests[0].url.params["page"] == "2"
    assert observer.calls[0][0:2] == (2, "primary")
    assert [result.rank for result in response.results] == [11, 13]


def test_exa_uses_one_requested_depth_without_cursor_paging() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"results": [{"url": "https://example.org/one", "title": "Study"}]},
        )

    action = _action(DiscoveryProvider.EXA)
    adapter = ExaSearchAdapter(
        ExaConfig(api_key="fixture-key"),
        client=httpx.Client(base_url="https://api.exa.ai", transport=httpx.MockTransport(handler)),
    )
    observer = _PageObserver()

    with observe_physical_requests(observer):
        response = adapter.search(_request(action, page_number=1, limit=20))

    assert len(requests) == 1
    assert json.loads(requests[0].content) == {
        "query": action.query_text,
        "type": "auto",
        "numResults": 20,
    }
    assert observer.calls[0][0:2] == (1, "primary")
    assert response.next_cursor is None
    assert response.results[0].metadata.provider_page == 1
    assert response.results[0].metadata.raw_provider_rank == 1


def test_nonpaged_provider_rejects_page_two_before_transport() -> None:
    seen: list[httpx.Request] = []
    action = _action(DiscoveryProvider.EXA)
    adapter = ExaSearchAdapter(
        ExaConfig(api_key="fixture-key"),
        client=httpx.Client(
            base_url="https://api.exa.ai",
            transport=httpx.MockTransport(
                lambda request: seen.append(request) or httpx.Response(200, json={"results": []})
            ),
        ),
    )

    with pytest.raises(ValueError):
        adapter.search(_request(action, page_number=2, limit=20))

    assert seen == []
