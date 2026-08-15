"""Strict OpenAlex Works search adapter for scholarly discovery metadata."""

from __future__ import annotations

from decimal import Decimal
from threading import Lock
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import ValidationError

from models import DiscoveryProvider
from money import add_usd, parse_exact_usd
from providers.config import OpenAlexConfig
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
)

OPENALEX_SELECT = ",".join(
    (
        "id",
        "doi",
        "title",
        "publication_year",
        "publication_date",
        "type",
        "cited_by_count",
        "is_retracted",
        "relevance_score",
        "open_access",
        "primary_location",
        "best_oa_location",
    )
)


class OpenAlexSearchAdapter:
    """Search OpenAlex without exposing its query-parameter credential."""

    def __init__(self, config: OpenAlexConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )
        self._usage_lock = Lock()
        self._calls_by_run: dict[UUID, int] = {}
        self._cost_by_run: dict[UUID, Decimal] = {}

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is not DiscoveryProvider.OPENALEX or request.run_id is None:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "OpenAlex requires a typed OpenAlex search request with run identity",
            )
        self._reserve(request.run_id)
        search_parameter = "search.semantic" if request.semantic else "search"
        params = {
            "api_key": self._config.api_key.get_secret_value(),
            search_parameter: request.query_text,
            "per_page": str(request.limit),
            "select": OPENALEX_SELECT,
        }
        try:
            response = self._client.get(
                "/works",
                params=params,
                timeout=self._config.deadlines.search_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT,
                "OpenAlex search timed out",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION,
                "OpenAlex search connection failed",
                retryable=True,
            ) from exc
        _raise_status(response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "OpenAlex returned invalid JSON",
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "OpenAlex response omitted results",
            )
        results = _parse_results(body["results"], request.limit)
        if not results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS,
                "OpenAlex returned no usable non-retracted discovery results",
            )
        cost = _response_cost(body)
        return SearchResponse(
            results=results,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            adapter_version=self._config.adapter_version,
            search_type="semantic" if request.semantic else "search",
            cost_usd=cost,
        )

    def _reserve(self, run_id: UUID) -> None:
        with self._usage_lock:
            calls = self._calls_by_run.get(run_id, 0)
            cost = self._cost_by_run.get(run_id, Decimal("0"))
            next_cost = add_usd(cost, self._config.nominal_search_cost_usd)
            if (
                calls >= self._config.max_search_calls_per_run
                or next_cost > self._config.max_search_cost_usd_per_run
            ):
                raise SearchProviderError(
                    SearchFailureCode.BUDGET_EXHAUSTED,
                    "OpenAlex run ceiling reached: at most 10 searches and USD 0.01",
                )
            self._calls_by_run[run_id] = calls + 1
            self._cost_by_run[run_id] = next_cost


def _parse_results(items: list[object], limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or item.get("is_retracted") is True:
            continue
        url = _work_url(item)
        if url is None or url in seen:
            continue
        try:
            result = SearchResult(
                original_url=url,
                title=_string(item.get("title")) or "",
                rank=len(results) + 1,
                relevance_score=_number(item.get("relevance_score")),
                metadata=SearchDiscoveryMetadata(
                    engine="openalex",
                    published_at=_string(item.get("publication_date")),
                    display_url=url,
                    category="academic",
                    external_id=_string(item.get("id")),
                    doi=_string(item.get("doi")),
                    cited_by_count=_nonnegative_int(item.get("cited_by_count")),
                    is_open_access=_open_access(item.get("open_access")),
                    work_type=_string(item.get("type")),
                    is_retracted=False,
                    pdf_url=_location_url(item.get("primary_location"), "pdf_url")
                    or _location_url(item.get("best_oa_location"), "pdf_url"),
                ),
            )
        except ValidationError:
            continue
        results.append(result)
        seen.add(url)
        if len(results) >= limit:
            break
    return results


def _work_url(item: dict[str, Any]) -> str | None:
    candidates = (
        _location_url(item.get("primary_location"), "landing_page_url"),
        _location_url(item.get("best_oa_location"), "landing_page_url"),
        _string(item.get("doi")),
        _string(item.get("id")),
    )
    for candidate in candidates:
        if candidate is not None and _is_http_url(candidate):
            return candidate
    return None


def _location_url(value: object, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    candidate = _string(value.get(key))
    return candidate if candidate is not None and _is_http_url(candidate) else None


def _is_http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not (parsed.username or parsed.password)
    )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _open_access(value: object) -> bool | None:
    if not isinstance(value, dict) or not isinstance(value.get("is_oa"), bool):
        return None
    return value["is_oa"]


def _response_cost(body: dict[str, Any]) -> Decimal:
    meta = body.get("meta")
    if not isinstance(meta, dict):
        return Decimal("0.001")
    value = meta.get("cost_usd")
    try:
        return parse_exact_usd(value)
    except (TypeError, ValueError):
        return Decimal("0.001")


def _raise_status(status_code: int) -> None:
    if status_code < 400:
        return
    if status_code in {401, 403}:
        raise SearchProviderError(
            SearchFailureCode.AUTHENTICATION,
            "OpenAlex authentication failed",
        )
    if status_code == 429:
        raise SearchProviderError(
            SearchFailureCode.RATE_LIMIT,
            "OpenAlex rate limit reached",
            retryable=True,
        )
    if status_code >= 500:
        raise SearchProviderError(
            SearchFailureCode.TRANSIENT_OUTAGE,
            "OpenAlex service is temporarily unavailable",
            retryable=True,
        )
    raise SearchProviderError(
        SearchFailureCode.PERMANENT_FAILURE,
        "OpenAlex rejected the search request",
    )
