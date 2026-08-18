from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from models import DiscoveryProvider, ResearchControls, SearchIntent
from providers.config import SerpSearchConfig
from providers.search import SearchFailureCode, SearchProviderError, SearchRequest
from providers.serpsearch import SerpSearchAdapter


def test_source_controls_default_to_all_three_and_require_one() -> None:
    assert ResearchControls().discovery_providers == (
        DiscoveryProvider.SERPSEARCH,
        DiscoveryProvider.EXA,
        DiscoveryProvider.OPENALEX,
    )
    with pytest.raises(ValidationError, match="at least one"):
        ResearchControls(discovery_providers=())


def test_serpsearch_uses_bearer_auth_and_keeps_only_organic_http_results() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        assert request.url.path == "/api/v1/search"
        assert request.url.params["query"] == "four day workweek productivity"
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"position": 1, "title": "Study", "link": "https://example.org/study"},
                    {"position": 2, "title": "Unsafe", "link": "ftp://example.org/file"},
                ]
            },
        )

    adapter = SerpSearchAdapter(
        SerpSearchConfig(api_key=SecretStr("serp-secret")),
        client=httpx.Client(
            base_url="https://api.serpsearch.com", transport=httpx.MockTransport(handler)
        ),
    )
    response = adapter.search(
        SearchRequest(
            run_id=uuid4(),
            provider=DiscoveryProvider.SERPSEARCH,
            intent=SearchIntent.BROAD_WEB,
            query_text="four day workweek productivity",
            limit=10,
        )
    )

    assert captured["authorization"] == "Bearer serp-secret"
    assert [result.original_url for result in response.results] == ["https://example.org/study"]
    assert response.results[0].metadata.engine == "serpsearch"


def test_serpsearch_counts_attempts_against_the_twelve_call_ceiling() -> None:
    adapter = SerpSearchAdapter(
        SerpSearchConfig(api_key=SecretStr("serp-secret")),
        client=httpx.Client(
            base_url="https://api.serpsearch.com",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={"organic_results": [{"link": "https://example.org/result"}]},
                )
            ),
        ),
    )
    request = SearchRequest(
        run_id=uuid4(),
        provider=DiscoveryProvider.SERPSEARCH,
        intent=SearchIntent.BROAD_WEB,
        query_text="query",
        limit=1,
    )

    for _ in range(12):
        adapter.search(request)
    with pytest.raises(SearchProviderError) as exc_info:
        adapter.search(request)
    assert exc_info.value.code is SearchFailureCode.BUDGET_EXHAUSTED
