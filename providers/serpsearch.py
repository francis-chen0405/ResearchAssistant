"""Strict SERP Search adapter for Google-style discovery metadata."""

from __future__ import annotations

from threading import Lock
from uuid import UUID

import httpx
from pydantic import ValidationError

from models import DiscoveryProvider
from providers.config import SerpSearchConfig
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
)


class SerpSearchAdapter:
    """Return normalized organic Google results without treating snippets as evidence."""

    def __init__(self, config: SerpSearchConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )
        self._usage_lock = Lock()
        self._calls_by_run: dict[UUID, int] = {}

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is not DiscoveryProvider.SERPSEARCH or request.run_id is None:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "SERP Search requires a typed request with run identity",
            )
        self._reserve(request.run_id)
        try:
            response = self._client.get(
                "/api/v1/search",
                headers={"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"},
                params={"query": request.query_text, "page": "1"},
                timeout=self._config.deadlines.search_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT, "SERP Search timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION, "SERP Search connection failed", retryable=True
            ) from exc
        _raise_status(response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "SERP Search returned invalid JSON"
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("organic_results"), list):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "SERP Search response omitted organic results",
            )
        results: list[SearchResult] = []
        seen: set[str] = set()
        for item in body["organic_results"]:
            if not isinstance(item, dict) or not isinstance(item.get("link"), str):
                continue
            url = item["link"]
            if url in seen:
                continue
            try:
                result = SearchResult(
                    original_url=url,
                    title=item.get("title") if isinstance(item.get("title"), str) else "",
                    snippet=item.get("snippet") if isinstance(item.get("snippet"), str) else None,
                    rank=len(results) + 1,
                    metadata=SearchDiscoveryMetadata(
                        engine="serpsearch",
                        display_url=(
                            item.get("displayed_link")
                            if isinstance(item.get("displayed_link"), str)
                            else None
                        ),
                        category="general_web",
                    ),
                )
            except ValidationError:
                continue
            results.append(result)
            seen.add(url)
            if len(results) >= request.limit:
                break
        if not results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS, "SERP Search returned no usable organic results"
            )
        return SearchResponse(
            results=results,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            adapter_version=self._config.adapter_version,
            search_type="google_organic",
        )

    def _reserve(self, run_id: UUID) -> None:
        with self._usage_lock:
            calls = self._calls_by_run.get(run_id, 0)
            if calls >= self._config.max_search_calls_per_run:
                raise SearchProviderError(
                    SearchFailureCode.BUDGET_EXHAUSTED,
                    "SERP Search run ceiling reached: at most 12 searches",
                )
            self._calls_by_run[run_id] = calls + 1


def _raise_status(status_code: int) -> None:
    if 200 <= status_code < 300:
        return
    if status_code in {401, 403}:
        code, retryable = SearchFailureCode.AUTHENTICATION, False
    elif status_code == 429:
        code, retryable = SearchFailureCode.RATE_LIMIT, True
    elif status_code in {408, 504}:
        code, retryable = SearchFailureCode.TIMEOUT, True
    elif 500 <= status_code < 600:
        code, retryable = SearchFailureCode.TRANSIENT_OUTAGE, True
    else:
        code, retryable = SearchFailureCode.PERMANENT_FAILURE, False
    raise SearchProviderError(
        code, f"SERP Search failed with HTTP {status_code}", retryable=retryable
    )
