"""Bounded first-page web discovery for Brave Search and Serper."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import SecretStr, ValidationError

from researchassistant.contracts.models import DiscoveryProvider, StrictModel
from researchassistant.contracts.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from researchassistant.providers.bounded_network import DeadlineHTTPTransport
from researchassistant.providers.config import (
    DeadlineConfig,
    ProviderConfigurationError,
)
from researchassistant.providers.discovery_transport import (
    bounded_send,
    physical_request,
)
from researchassistant.providers.search import (
    SearchProviderError,
    SearchTimeoutError,
    compiled_parameters,
)


@dataclass(frozen=True)
class _Endpoint:
    origin: str
    path: str
    method: Literal["GET", "POST"]
    key_header: str
    count_parameter: str
    url_field: str
    snippet_field: str
    version: str


_ENDPOINTS = {
    DiscoveryProvider.BRAVE: _Endpoint(
        "https://api.search.brave.com",
        "/res/v1/web/search",
        "GET",
        "X-Subscription-Token",
        "count",
        "url",
        "description",
        "web-search-v1",
    ),
    DiscoveryProvider.SERPER: _Endpoint(
        "https://google.serper.dev",
        "/search",
        "POST",
        "X-API-KEY",
        "num",
        "link",
        "snippet",
        "google-organic",
    ),
}


class WebSearchConfig(StrictModel):
    provider: Literal[DiscoveryProvider.BRAVE, DiscoveryProvider.SERPER]
    api_key: SecretStr
    deadlines: DeadlineConfig = DeadlineConfig()

    @classmethod
    def from_environment(
        cls, provider: DiscoveryProvider, environment: Mapping[str, str]
    ) -> WebSearchConfig:
        name = f"{provider.value.upper()}_API_KEY"
        key = environment.get(name, "").strip()
        if not key:
            raise ProviderConfigurationError(
                f"{name} is required when {provider.value} is enabled"
            )
        return cls(provider=provider, api_key=SecretStr(key))


def web_result_records(provider: DiscoveryProvider, body: object) -> list | None:
    if not isinstance(body, dict):
        return None
    if provider is DiscoveryProvider.BRAVE:
        web = body.get("web")
        if web is None and body.get("type") == "search":
            return []
        records = web.get("results") if isinstance(web, dict) else None
    else:
        records = body.get("organic")
        if records is None and isinstance(body.get("searchParameters"), dict):
            return []
    return records if isinstance(records, list) else None


class WebSearchAdapter:
    """Normalize discovery leads while accounting for each physical request."""

    physical_accounting = True

    def __init__(
        self, config: WebSearchConfig, *, client: httpx.Client | None = None
    ) -> None:
        self._config = config
        self._endpoint = _ENDPOINTS[config.provider]
        self._client = client or httpx.Client(
            transport=DeadlineHTTPTransport(),
            trust_env=False,
            base_url=self._endpoint.origin,
            timeout=config.deadlines.search_seconds,
            follow_redirects=False,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        provider = self._config.provider
        endpoint = self._endpoint
        names = frozenset({"q", endpoint.count_parameter})
        expected = {"q": request.query_text, endpoint.count_parameter: request.limit}
        if (
            request.provider is not provider
            or request.compiled_query is None
            or compiled_parameters(request, allowed_names=names, required_names=names)
            != expected
        ):
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "Web search requires a matching compiled query",
            )
        payload = (
            {"params": expected} if endpoint.method == "GET" else {"json": expected}
        )
        try:
            response = physical_request(
                request,
                expected,
                lambda: bounded_send(
                    self._client,
                    endpoint.method,
                    endpoint.origin + endpoint.path,
                    expected_base_url=endpoint.origin,
                    headers={
                        endpoint.key_header: self._config.api_key.get_secret_value()
                    },
                    timeout=self._config.deadlines.search_seconds,
                    **payload,
                ),
            )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT, f"{provider.value} timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION,
                f"{provider.value} connection failed",
                retryable=True,
            ) from exc
        _raise_status(provider, response.status_code)
        try:
            records = web_result_records(provider, response.json())
        except ValueError:
            records = None
        if records is None:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                f"{provider.value} returned invalid results",
            )
        results: list[SearchResult] = []
        seen: set[str] = set()
        for rank, item in enumerate(records[: request.limit], start=1):
            if not isinstance(item, dict):
                continue
            url = item.get(endpoint.url_field)
            if not isinstance(url, str) or url in seen:
                continue
            title, snippet = item.get("title"), item.get(endpoint.snippet_field)
            try:
                result = SearchResult(
                    original_url=url,
                    title=title if isinstance(title, str) else "",
                    snippet=snippet if isinstance(snippet, str) else None,
                    rank=rank,
                    metadata=SearchDiscoveryMetadata(
                        engine=provider.value,
                        provider_page=1,
                        raw_provider_rank=rank,
                        category="general_web",
                    ),
                )
            except ValidationError:
                continue
            results.append(result)
            seen.add(url)
        return SearchResponse(
            results=results,
            provider_name=provider.value,
            provider_version=endpoint.version,
            adapter_version="bounded-web-search-v1",
            search_type="web_organic",
        )


def _raise_status(provider: DiscoveryProvider, status: int) -> None:
    if 200 <= status < 300:
        return
    if status in {401, 403}:
        code = SearchFailureCode.AUTHENTICATION
    elif status == 429:
        code = SearchFailureCode.RATE_LIMIT
    elif status in {408, 504}:
        code = SearchFailureCode.TIMEOUT
    elif 500 <= status < 600:
        code = SearchFailureCode.TRANSIENT_OUTAGE
    else:
        code = SearchFailureCode.PERMANENT_FAILURE
    raise SearchProviderError(
        code,
        f"{provider.value} failed with HTTP {status}",
        retryable=code
        in {
            SearchFailureCode.RATE_LIMIT,
            SearchFailureCode.TIMEOUT,
            SearchFailureCode.TRANSIENT_OUTAGE,
        },
    )
