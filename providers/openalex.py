"""Strict OpenAlex Works search adapter for scholarly discovery metadata."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import nullcontext
from decimal import Decimal
from threading import Lock
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import ValidationError

from providers.config import OpenAlexConfig
from providers.discovery_transport import bounded_send, physical_request
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
    compiled_parameters,
    metadata_page_size,
    validate_request_url,
)
from researchassistant.common.money import add_usd, parse_exact_usd
from researchassistant.contracts.discovery_v2 import SearchMode, V2DiscoveryProviderBudget
from researchassistant.contracts.models import DiscoveryProvider

if TYPE_CHECKING:
    from providers.openalex_neighborhood import OpenAlexNeighborhoodAdapter

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
        "abstract_inverted_index",
    )
)


class OpenAlexSearchAdapter:
    """Search OpenAlex without exposing its query-parameter credential."""

    physical_accounting = True

    def __init__(
        self,
        config: OpenAlexConfig,
        *,
        client: httpx.Client | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )
        self._usage_lock = Lock()
        self._semantic_lock = Lock()
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_semantic_start: float | None = None
        self._calls_by_run: dict[UUID, int] = {}
        self._cost_by_run: dict[UUID, Decimal] = {}
        self._neighborhood_adapter: OpenAlexNeighborhoodAdapter | None = None

    @property
    def neighborhood_adapter(self) -> OpenAlexNeighborhoodAdapter:
        """Return the cached bounded ID/citation adapter used by discovery scouting."""
        if self._neighborhood_adapter is None:
            from providers.openalex_neighborhood import OpenAlexNeighborhoodAdapter

            self._neighborhood_adapter = OpenAlexNeighborhoodAdapter(
                self._config, client=self._client
            )
        return self._neighborhood_adapter

    def query_budget(
        self, provider: DiscoveryProvider, mode: SearchMode
    ) -> V2DiscoveryProviderBudget | None:
        if provider is not DiscoveryProvider.OPENALEX:
            return None
        return V2DiscoveryProviderBudget(
            provider=provider,
            max_requests=self._config.max_search_calls_per_run,
            max_cost_usd=self._config.max_search_cost_usd_per_run,
            cost_policy_identity=f"query-openalex-{mode}-2026-10-06-v2",
            reservation_per_request_usd=Decimal("0.001"),
            cost_basis="configured_upper_bound",
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is not DiscoveryProvider.OPENALEX or request.run_id is None:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "OpenAlex requires a typed OpenAlex search request with run identity",
            )
        base_parameters = compiled_parameters(
            request,
            allowed_names=frozenset({"search", "search.semantic", "per_page", "cursor"}),
            required_names=frozenset({"per_page"}),
        )
        search_parameter = "search.semantic" if request.semantic else "search"
        if base_parameters is None:
            query_parameters: dict[str, str | int | bool] = {
                search_parameter: request.query_text,
                "per_page": request.limit,
            }
        else:
            if set(base_parameters) != {search_parameter, "per_page"}:
                if set(base_parameters) != {search_parameter, "per_page", "cursor"}:
                    raise SearchProviderError(
                        SearchFailureCode.PERMANENT_FAILURE,
                        "compiled OpenAlex page parameters do not match the selected search mode",
                    )
            if (
                base_parameters[search_parameter] != request.query_text
                or base_parameters["per_page"] != request.limit
                or ("cursor" in base_parameters and not isinstance(base_parameters["cursor"], str))
            ):
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE,
                    "compiled OpenAlex page parameters do not match query text or page depth",
                )
            query_parameters = base_parameters
        params = {
            **query_parameters,
            "api_key": self._config.api_key.get_secret_value(),
            "select": OPENALEX_SELECT,
        }
        if request.compiled_query is not None:
            validate_request_url(str(self._client.base_url) + "works", params, max_bytes=4094)
        try:
            semantic_guard = self._semantic_lock if request.semantic else nullcontext()
            with semantic_guard:
                if request.semantic and request.compiled_query is None:
                    self._wait_for_semantic_slot(None)
                if request.compiled_query is None:
                    self._reserve(request.run_id, semantic=request.semantic)

                def send() -> httpx.Response:
                    if request.semantic:
                        self._last_semantic_start = self._monotonic()
                    return bounded_send(
                        self._client,
                        "GET",
                        "/works",
                        expected_base_url=self._config.base_url,
                        params=params,
                        timeout=self._config.deadlines.search_seconds,
                    )

                response = physical_request(
                    request,
                    query_parameters,
                    send,
                    before_reservation=self._wait_for_semantic_slot if request.semantic else None,
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
        page_size = (
            metadata_page_size(request.compiled_query) if request.compiled_query else request.limit
        )
        rank_offset = (request.page_number - 1) * page_size
        results = _parse_results(
            body["results"], request.limit, rank_offset, provider_page=request.page_number
        )
        if not results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS,
                "OpenAlex returned no usable non-retracted discovery results",
            )
        cost = _response_cost(body)
        meta = body.get("meta")
        next_cursor = meta.get("next_cursor") if isinstance(meta, dict) else None
        return SearchResponse(
            results=results,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            adapter_version=self._config.adapter_version,
            search_type="semantic" if request.semantic else "search",
            cost_usd=cost,
            next_cursor=next_cursor if isinstance(next_cursor, str) and next_cursor else None,
        )

    def _wait_for_semantic_slot(self, cancelled: Callable[[], bool] | None) -> None:
        """Wait for this adapter's next semantic start, checking cancellation while waiting."""
        if cancelled is not None and cancelled():
            raise SearchProviderError(
                SearchFailureCode.CANCELLED, "query cancelled before transport"
            )
        now = self._monotonic()
        if self._last_semantic_start is not None:
            deadline = self._last_semantic_start + 1.0
            while now < deadline:
                if cancelled is not None and cancelled():
                    raise SearchProviderError(
                        SearchFailureCode.CANCELLED, "query cancelled while waiting for OpenAlex"
                    )
                self._sleep(min(max(deadline - now, 0.001), 0.1))
                now = self._monotonic()
        if cancelled is not None and cancelled():
            raise SearchProviderError(
                SearchFailureCode.CANCELLED, "query cancelled before transport"
            )

    def _reserve(self, run_id: UUID, *, semantic: bool = False) -> None:
        with self._usage_lock:
            calls = self._calls_by_run.get(run_id, 0)
            cost = self._cost_by_run.get(run_id, Decimal("0"))
            nominal = (
                self._config.nominal_semantic_search_cost_usd
                if semantic
                else self._config.nominal_search_cost_usd
            )
            next_cost = add_usd(cost, nominal)
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


def _parse_results(
    items: list[object],
    limit: int,
    rank_offset: int = 0,
    *,
    provider_page: int = 1,
) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or item.get("is_retracted") is True:
            continue
        url = _work_url(item)
        if url is None or url in seen:
            continue
        try:
            result = SearchResult(
                original_url=url,
                title=_string(item.get("title")) or "",
                rank=rank_offset + index,
                relevance_score=_number(item.get("relevance_score")),
                metadata=SearchDiscoveryMetadata(
                    engine="openalex",
                    provider_page=provider_page,
                    raw_provider_rank=index,
                    published_at=_string(item.get("publication_date")),
                    display_url=url,
                    category="academic",
                    external_id=_string(item.get("id")),
                    doi=_string(item.get("doi")),
                    cited_by_count=_nonnegative_int(item.get("cited_by_count")),
                    is_open_access=_open_access(item.get("open_access")),
                    work_type=_string(item.get("type")),
                    abstract=_abstract(item.get("abstract_inverted_index")),
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


def _abstract(value: object) -> str | None:
    """Reconstruct optional OpenAlex abstract metadata without treating it as evidence."""
    if not isinstance(value, dict):
        return None
    terms: list[tuple[int, str]] = []
    for token, positions in value.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                terms.append((position, token))
    if not terms or len({position for position, _ in terms}) != len(terms):
        return None
    return " ".join(token for _, token in sorted(terms))


def _response_cost(body: dict[str, Any]) -> Decimal | None:
    meta = body.get("meta")
    if not isinstance(meta, dict):
        return None
    value = meta.get("cost_usd")
    try:
        return parse_exact_usd(value)
    except (TypeError, ValueError):
        return None


def _raise_status(status_code: int) -> None:
    if 200 <= status_code < 300:
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
