"""Strict SERP Search adapter for Google-style discovery metadata."""

from __future__ import annotations

from threading import Lock
from uuid import UUID

import httpx
from pydantic import ValidationError

from providers.config import SerpSearchConfig
from providers.discovery_transport import physical_request
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
    compiled_parameters,
    validate_request_url,
)
from researchassistant.contracts.models import DiscoveryProvider


class SerpSearchAdapter:
    """Return normalized organic Google results without treating snippets as evidence."""

    physical_accounting = True

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
        parameters = compiled_parameters(
            request,
            allowed_names=frozenset({"query", "page", "exact_match"}),
            required_names=frozenset({"query", "page"}),
        )
        if parameters is None:
            query_params: dict[str, str | int | bool] = {"query": request.query_text, "page": 1}
            self._reserve(request.run_id)
        else:
            if (
                parameters.get("query") != request.query_text
                or parameters.get("page") != 1
                or ("exact_match" in parameters and parameters["exact_match"] is not True)
            ):
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE,
                    "compiled SERP Search parameters do not preserve the query on the first page",
                )
            query_params = parameters
        if request.compiled_query is not None:
            validate_request_url(
                str(self._client.base_url) + "api/v1/search", query_params, max_bytes=7500
            )
        try:
            response = physical_request(
                request,
                query_params,
                lambda: self._client.get(
                    "/api/v1/search",
                    headers={"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"},
                    params=query_params,
                    timeout=self._config.deadlines.search_seconds,
                ),
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
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            url = item["url"]
            if url in seen:
                continue
            position = item.get("position")
            rank = (
                position
                if isinstance(position, int) and not isinstance(position, bool) and position >= 1
                else len(results) + 1
            )
            try:
                result = SearchResult(
                    original_url=url,
                    title=item.get("title") if isinstance(item.get("title"), str) else "",
                    snippet=(
                        item.get("description")
                        if isinstance(item.get("description"), str)
                        else None
                    ),
                    rank=rank,
                    metadata=SearchDiscoveryMetadata(
                        engine="serpsearch",
                        display_url=(
                            item.get("visible_url")
                            if isinstance(item.get("visible_url"), str)
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
