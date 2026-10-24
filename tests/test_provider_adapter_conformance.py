"""Offline conformance checks for existing neutral metadata search adapters."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import httpx
import pytest

from researchassistant.contracts.models import DiscoveryProvider, SearchIntent
from researchassistant.contracts.search import (
    SearchFailureCode,
    SearchRequest,
    SearchResponse,
)
from researchassistant.providers.arxiv import ArxivSearchAdapter
from researchassistant.providers.config import (
    ArxivConfig,
    ExaConfig,
    OpenAlexConfig,
    PubMedConfig,
    SerpSearchConfig,
)
from researchassistant.providers.exa import ExaSearchAdapter
from researchassistant.providers.openalex import OpenAlexSearchAdapter
from researchassistant.providers.pubmed import PubMedSearchAdapter
from researchassistant.providers.search import SearchProvider, SearchProviderError
from researchassistant.providers.serpsearch import SerpSearchAdapter

ProviderName = str
ResponseFactory = Callable[[httpx.Request], httpx.Response]


def _arxiv_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry><title>Missing identifier</title></entry>
      <entry>
        <id>https://arxiv.org/abs/2401.00001</id>
        <title>Offline adapter fixture</title>
        <summary>Abstract metadata only.</summary>
        <published>2024-01-01T00:00:00Z</published>
        <author><name>Example Author</name></author>
        <category term="cs.IR" />
        <arxiv:doi>10.1000/offline</arxiv:doi>
        <link title="pdf" href="https://arxiv.org/pdf/2401.00001" />
      </entry>
      <entry><id>https://arxiv.org/abs/2401.00001</id><title>Duplicate</title></entry>
    </feed>"""


def _openalex_work(identifier: str, title: str) -> dict[str, object]:
    return {
        "id": identifier,
        "doi": "https://doi.org/10.1000/offline",
        "title": title,
        "publication_year": 2024,
        "publication_date": "2024-01-01",
        "type": "article",
        "cited_by_count": 3,
        "is_retracted": False,
        "relevance_score": 0.75,
        "open_access": {"is_oa": True},
        "primary_location": {
            "landing_page_url": identifier,
            "pdf_url": "https://example.org/paper.pdf",
        },
        "abstract_inverted_index": {"Offline": [0], "abstract.": [1]},
    }


def _fixture_response(provider: ProviderName, request: httpx.Request) -> httpx.Response:
    if provider == "exa":
        return httpx.Response(
            200,
            json={
                "requestId": "fixture-request",
                "results": [
                    {"url": "javascript:blocked", "title": "Invalid"},
                    {
                        "url": "https://example.org/exa",
                        "title": "Offline adapter fixture",
                        "publishedDate": "2024-01-01",
                    },
                    {"url": "https://example.org/exa", "title": "Duplicate"},
                ],
            },
            request=request,
        )
    if provider == "serpsearch":
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"url": "file:///blocked", "title": "Invalid", "position": 1},
                    {
                        "url": "https://example.org/serp",
                        "title": "Offline adapter fixture",
                        "description": "A search snippet, not evidence.",
                        "position": 2,
                    },
                    {"url": "https://example.org/serp", "title": "Duplicate", "position": 3},
                ]
            },
            request=request,
        )
    if provider == "arxiv":
        return httpx.Response(200, text=_arxiv_xml(), request=request)
    if provider == "pubmed":
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}}, request=request)
        return httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["123"],
                    "123": {
                        "title": "Offline adapter fixture",
                        "pubdate": "2024 Jan",
                        "authors": [{"name": "Example Author"}],
                        "articleids": [{"idtype": "doi", "value": "10.1000/offline"}],
                    },
                }
            },
            request=request,
        )
    if provider == "openalex":
        invalid_work = _openalex_work("ftp://invalid.example/work", "Invalid")
        invalid_work["doi"] = "ftp://invalid.example/doi"
        return httpx.Response(
            200,
            json={
                "results": [
                    invalid_work,
                    _openalex_work("https://openalex.org/W123", "Offline adapter fixture"),
                    _openalex_work("https://openalex.org/W123", "Duplicate"),
                ],
                "meta": {"cost_usd": "0.001"},
            },
            request=request,
        )
    raise AssertionError(f"unknown provider fixture: {provider}")


def _adapter_and_request(
    provider: ProviderName, responder: ResponseFactory | None = None
) -> tuple[SearchProvider, SearchRequest]:
    handler = responder or _fixture_responder(provider)
    transport = httpx.MockTransport(handler)
    run_id = uuid4()
    if provider == "exa":
        client = httpx.Client(base_url="https://api.exa.ai", transport=transport)
        adapter: SearchProvider = ExaSearchAdapter(ExaConfig(api_key="fixture-key"), client=client)
        request = SearchRequest(query_text="offline metadata fixture", limit=1)
    elif provider == "serpsearch":
        client = httpx.Client(base_url="https://api.serpsearch.com", transport=transport)
        adapter = SerpSearchAdapter(SerpSearchConfig(api_key="fixture-key"), client=client)
        request = SearchRequest(
            run_id=run_id,
            provider=DiscoveryProvider.SERPSEARCH,
            query_text="offline metadata fixture",
            limit=1,
        )
    elif provider == "arxiv":
        client = httpx.Client(base_url="https://export.arxiv.org", transport=transport)
        adapter = ArxivSearchAdapter(ArxivConfig(), client=client)
        request = SearchRequest(
            run_id=run_id,
            provider=DiscoveryProvider.ARXIV,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="offline metadata fixture",
            limit=1,
        )
    elif provider == "pubmed":
        client = httpx.Client(base_url="https://eutils.ncbi.nlm.nih.gov", transport=transport)
        adapter = PubMedSearchAdapter(PubMedConfig(), client=client)
        request = SearchRequest(
            run_id=run_id,
            provider=DiscoveryProvider.PUBMED,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="offline metadata fixture",
            limit=1,
        )
    elif provider == "openalex":
        client = httpx.Client(base_url="https://api.openalex.org", transport=transport)
        adapter = OpenAlexSearchAdapter(OpenAlexConfig(api_key="fixture-key"), client=client)
        request = SearchRequest(
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="offline metadata fixture",
            limit=1,
        )
    else:
        raise AssertionError(f"unknown provider fixture: {provider}")
    return adapter, request


@pytest.mark.slow
@pytest.mark.parametrize(
    ("provider", "expected_url", "expected_raw_rank"),
    (
        ("exa", "https://example.org/exa", 2),
        ("serpsearch", "https://example.org/serp", 2),
        ("arxiv", "https://arxiv.org/abs/2401.00001", 2),
        ("pubmed", "https://pubmed.ncbi.nlm.nih.gov/123/", 1),
        ("openalex", "https://openalex.org/W123", 2),
    ),
)
def test_search_adapters_conform_to_neutral_result_contract(
    provider: ProviderName, expected_url: str, expected_raw_rank: int
) -> None:
    adapter, request = _adapter_and_request(provider)

    response = adapter.search(request)

    assert isinstance(response, SearchResponse)
    assert len(response.results) == request.limit
    assert response.provider_name == provider
    assert response.provider_version != "unknown"
    assert response.adapter_version != "unknown"
    result = response.results[0]
    assert result.original_url == expected_url
    assert result.metadata.engine == provider
    assert result.metadata.provider_page == 1
    assert result.metadata.raw_provider_rank == expected_raw_rank
    assert result.metadata.external_id or result.metadata.doi or result.original_url
    assert SearchResponse.model_validate(response.model_dump()) == response


def _rate_limited_response(provider: ProviderName, request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, request=request)


def _fixture_responder(provider: ProviderName) -> ResponseFactory:
    def respond(request: httpx.Request) -> httpx.Response:
        return _fixture_response(provider, request)

    return respond


def _rate_limited_responder(provider: ProviderName) -> ResponseFactory:
    def respond(request: httpx.Request) -> httpx.Response:
        return _rate_limited_response(provider, request)

    return respond


def _malformed_response(provider: ProviderName, request: httpx.Request) -> httpx.Response:
    if provider == "arxiv":
        return httpx.Response(200, text="not Atom XML", request=request)
    return httpx.Response(200, json={"unexpected": "shape"}, request=request)


def _malformed_responder(provider: ProviderName) -> ResponseFactory:
    def respond(request: httpx.Request) -> httpx.Response:
        return _malformed_response(provider, request)

    return respond


@pytest.mark.parametrize("provider", ("exa", "serpsearch", "arxiv", "pubmed", "openalex"))
def test_search_adapters_expose_rate_limit_as_typed_retryable_failure(
    provider: ProviderName,
) -> None:
    adapter, request = _adapter_and_request(provider, responder=_rate_limited_responder(provider))

    with pytest.raises(SearchProviderError) as raised:
        adapter.search(request)

    assert raised.value.code is SearchFailureCode.RATE_LIMIT
    assert raised.value.retryable is True


@pytest.mark.parametrize("provider", ("exa", "serpsearch", "arxiv", "pubmed", "openalex"))
def test_search_adapters_classify_malformed_success_payloads(
    provider: ProviderName,
) -> None:
    adapter, request = _adapter_and_request(provider, responder=_malformed_responder(provider))

    with pytest.raises(SearchProviderError) as raised:
        adapter.search(request)

    assert raised.value.code is SearchFailureCode.MALFORMED_RESPONSE
