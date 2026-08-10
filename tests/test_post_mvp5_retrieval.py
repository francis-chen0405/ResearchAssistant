from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from providers.acquisition import AcquisitionFailureCode
from providers.config import ExaConfig, FirecrawlConfig
from providers.exa import DEFAULT_EXCLUDED_DOMAINS, ExaSearchAdapter
from providers.firecrawl import FallbackAcquisitionAdapter, FirecrawlAcquisitionAdapter
from providers.scraper import ScrapeRequest, ScrapeResponse, ScraperProviderError
from providers.search import SearchRequest


def test_exa_search_uses_auto_metadata_only_and_merges_domain_exclusions() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert request.headers["authorization"] == "Bearer exa-test-secret"
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "requestId": "request-1",
                "searchType": "auto",
                "costDollars": {"total": 0.007},
                "results": [
                    {
                        "id": "exa-result-1",
                        "title": "A useful source",
                        "url": "https://example.org/source",
                        "publishedDate": "2025-01-02T00:00:00.000Z",
                        "author": "Researcher",
                        "text": "must not cross the discovery boundary",
                    }
                ],
            },
            request=request,
        )

    client = httpx.Client(
        base_url="https://api.exa.ai",
        transport=httpx.MockTransport(handler),
    )
    response = ExaSearchAdapter(ExaConfig(api_key="exa-test-secret"), client=client).search(
        SearchRequest(query_text="lunar settlement -site:example.net", limit=5)
    )

    assert observed == {
        "query": "lunar settlement",
        "type": "auto",
        "numResults": 5,
        "excludeDomains": [*DEFAULT_EXCLUDED_DOMAINS, "example.net"],
    }
    assert response.results[0].snippet is None
    assert response.results[0].original_url == "https://example.org/source"
    assert response.request_id == "request-1"
    assert response.cost_usd == Decimal("0.007")


class _Primary:
    def __init__(self, error: ScraperProviderError | None = None) -> None:
        self.error = error

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        if self.error is not None:
            raise self.error
        raise AssertionError("primary success is not needed in this test")


class _Fallback:
    def __init__(self) -> None:
        self.calls = 0

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.calls += 1
        return ScrapeResponse(
            resolved_url=request.url,
            original_url=request.url,
            content_type="text/html",
            text="usable fallback evidence",
            provider_name="firecrawl",
            provider_version="v2",
        )


@pytest.mark.parametrize(
    "code",
    [
        AcquisitionFailureCode.WIGOLO_CONNECTION,
        AcquisitionFailureCode.WIGOLO_TIMEOUT,
        AcquisitionFailureCode.MALFORMED,
        AcquisitionFailureCode.EXTRACTION,
        AcquisitionFailureCode.CHALLENGE,
    ],
)
def test_firecrawl_is_used_only_for_approved_wigolo_failures(code: str) -> None:
    fallback = _Fallback()
    adapter = FallbackAcquisitionAdapter(
        primary=_Primary(ScraperProviderError(code, "primary failed")),
        fallback=fallback,
    )

    response = adapter.scrape(ScrapeRequest(url="https://example.org", timeout_seconds=10))

    assert response.provider_name == "firecrawl"
    assert fallback.calls == 1


@pytest.mark.parametrize(
    "code",
    [
        AcquisitionFailureCode.AUTHENTICATION,
        AcquisitionFailureCode.PAYWALL,
        AcquisitionFailureCode.INACCESSIBLE,
        AcquisitionFailureCode.TOO_LARGE,
        AcquisitionFailureCode.REDIRECT,
        AcquisitionFailureCode.CONTENT_TYPE,
    ],
)
def test_firecrawl_never_bypasses_source_access_or_policy_failures(code: str) -> None:
    fallback = _Fallback()
    adapter = FallbackAcquisitionAdapter(
        primary=_Primary(ScraperProviderError(code, "source refused")),
        fallback=fallback,
    )

    with pytest.raises(ScraperProviderError) as error:
        adapter.scrape(ScrapeRequest(url="https://example.org", timeout_seconds=10))

    assert error.value.code == code
    assert fallback.calls == 0


def test_firecrawl_scrape_normalizes_markdown_without_provider_metadata_leakage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/scrape"
        assert request.headers["authorization"] == "Bearer firecrawl-test-secret"
        assert json.loads(request.content) == {
            "url": "https://example.org/article",
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "markdown": "# Heading\n\nExact public evidence.",
                    "metadata": {
                        "sourceURL": "https://example.org/article",
                        "statusCode": 200,
                        "contentType": "text/html; charset=utf-8",
                    },
                },
            },
            request=request,
        )

    client = httpx.Client(
        base_url="https://api.firecrawl.dev",
        transport=httpx.MockTransport(handler),
    )
    response = FirecrawlAcquisitionAdapter(
        FirecrawlConfig(api_key="firecrawl-test-secret"),
        client=client,
        host_resolver=lambda hostname: ("93.184.216.34",),
    ).scrape(ScrapeRequest(url="https://example.org/article", timeout_seconds=10))

    assert response.text == "Heading\n\nExact public evidence."
    assert response.snapshot_sha256 is not None
    assert response.provider_name == "firecrawl"


def test_firecrawl_configuration_is_optional_but_exa_is_required() -> None:
    assert FirecrawlConfig.from_environment({}) is None
    with pytest.raises(RuntimeError, match="EXA_API_KEY"):
        ExaConfig.from_environment({})
