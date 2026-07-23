"""Production-intended synchronous adapter for pinned local Wigolo 0.2.1."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from threading import Lock
from typing import Any

import httpx
from pydantic import ValidationError

from providers.config import WigoloConfig
from providers.search import (
    SearchDiscoveryMetadata,
    SearchEngineTelemetry,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
)


class WigoloSearchAdapter:
    """Thread-safe discovery-only Wigolo adapter implementing ``SearchProvider``."""

    def __init__(
        self,
        config: WigoloConfig,
        *,
        client: httpx.Client | None = None,
        health_verified: bool = False,
    ) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )
        self._health_verified = health_verified
        self._health_lock = Lock()

    def verify_health(self) -> None:
        if self._health_verified:
            return
        with self._health_lock:
            if self._health_verified:
                return
            try:
                response = self._client.get(
                    "/health", timeout=self._config.deadlines.health_seconds
                )
            except httpx.TimeoutException as exc:
                raise SearchTimeoutError(
                    SearchFailureCode.TIMEOUT,
                    "Wigolo health check timed out",
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise SearchProviderError(
                    SearchFailureCode.CONNECTION,
                    "Wigolo health check could not connect to loopback service",
                    retryable=True,
                ) from exc
            if response.status_code != 200:
                raise _http_error(response.status_code, "Wigolo health check failed")
            payload = _json_object(response, operation="health")
            identity = str(payload.get("name") or payload.get("service") or "").lower()
            version = str(payload.get("version") or "")
            if "wigolo" not in identity or version != self._config.provider_version:
                raise SearchProviderError(
                    SearchFailureCode.MISSING_CONFIGURATION,
                    "loopback service is not the configured Wigolo 0.2.1 instance",
                    retryable=False,
                )
            self._health_verified = True

    def search(self, request: SearchRequest) -> SearchResponse:
        self.verify_health()
        payload = {
            "query": request.query_text,
            "max_results": 5,
            "max_fetches": 0,
            "include_content": False,
            "search_depth": "balanced",
            "force_refresh": True,
            "include_full_markdown": False,
        }
        try:
            response = self._client.post(
                "/v1/search",
                json=payload,
                timeout=self._config.deadlines.search_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT, "Wigolo search timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION,
                "Wigolo search could not connect to loopback service",
                retryable=True,
            ) from exc
        if response.status_code != 200:
            raise _http_error(response.status_code, "Wigolo search failed")
        body = _json_object(response, operation="search")
        if body.get("error") or body.get("success") is False:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "Wigolo returned an error payload",
                retryable=bool(body.get("retryable", False)),
            )
        raw_results = body.get("results")
        if not isinstance(raw_results, list):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "Wigolo success response did not contain a results list",
                retryable=True,
            )
        if not raw_results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS,
                "Wigolo returned no discovery results",
                retryable=False,
            )
        results: list[SearchResult] = []
        seen: set[str] = set()
        warnings = [str(item) for item in body.get("warnings", []) if isinstance(item, str)]
        for rank, raw_result in enumerate(raw_results[:5], start=1):
            if not isinstance(raw_result, Mapping):
                raise _malformed_result(rank)
            url = raw_result.get("url") or raw_result.get("original_url")
            if not isinstance(url, str) or not url.strip():
                raise SearchProviderError(
                    SearchFailureCode.INVALID_URL,
                    f"Wigolo result {rank} has a missing URL",
                    retryable=False,
                )
            if url in seen:
                warnings.append(f"duplicate URL omitted at provider rank {rank}")
                continue
            try:
                result = SearchResult(
                    original_url=url,
                    title=str(raw_result.get("title") or ""),
                    rank=rank,
                    relevance_score=_optional_number(raw_result.get("score"), rank),
                    snippet=_optional_string(raw_result.get("snippet")),
                    metadata=_discovery_metadata(raw_result),
                )
            except ValidationError as exc:
                raise SearchProviderError(
                    SearchFailureCode.INVALID_URL,
                    f"Wigolo result {rank} has an invalid URL or metadata",
                    retryable=False,
                ) from exc
            results.append(result)
            seen.add(url)
        if not results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS,
                "Wigolo returned no unique discovery results",
                retryable=False,
            )
        telemetry = body.get("engines") or body.get("telemetry") or {}
        if not isinstance(telemetry, Mapping):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "Wigolo engine telemetry is malformed",
                retryable=True,
            )
        return SearchResponse(
            results=results,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            adapter_version=self._config.adapter_version,
            engine_telemetry=_engine_telemetry(telemetry),
            warnings=tuple(warnings),
            degraded_pool=bool(body.get("degraded", body.get("degraded_pool", False))),
        )


def _json_object(response: httpx.Response, *, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchProviderError(
            SearchFailureCode.MALFORMED_RESPONSE,
            f"Wigolo {operation} response was not valid JSON",
            retryable=True,
        ) from exc
    if not isinstance(payload, dict):
        raise SearchProviderError(
            SearchFailureCode.MALFORMED_RESPONSE,
            f"Wigolo {operation} response was not an object",
            retryable=True,
        )
    return payload


def _http_error(status: int, message: str) -> SearchProviderError:
    if status in {401, 403}:
        return SearchProviderError(SearchFailureCode.AUTHENTICATION, message, retryable=False)
    if status == 408:
        return SearchTimeoutError(SearchFailureCode.TIMEOUT, message, retryable=True)
    if status == 429:
        return SearchProviderError(SearchFailureCode.RATE_LIMIT, message, retryable=True)
    if 500 <= status < 600:
        return SearchProviderError(SearchFailureCode.TRANSIENT_OUTAGE, message, retryable=True)
    return SearchProviderError(SearchFailureCode.PERMANENT_FAILURE, message, retryable=False)


def _optional_number(value: Any, rank: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SearchProviderError(
            SearchFailureCode.MALFORMED_RESPONSE,
            f"Wigolo result {rank} has malformed relevance metadata",
            retryable=True,
        )
    return float(value)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _discovery_metadata(result: Mapping[str, Any]) -> SearchDiscoveryMetadata:
    published_at = result.get("published_at")
    if published_at is not None:
        if not isinstance(published_at, str):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "Wigolo result has malformed publication metadata",
                retryable=True,
            )
        try:
            datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "Wigolo result has malformed publication metadata",
                retryable=True,
            ) from exc
    return SearchDiscoveryMetadata(
        engine=_optional_string(result.get("engine")),
        published_at=published_at,
        display_url=_optional_string(result.get("display_url")),
        category=_optional_string(result.get("category")),
    )


def _engine_telemetry(raw: Mapping[str, Any]) -> tuple[SearchEngineTelemetry, ...]:
    items: list[SearchEngineTelemetry] = []
    for engine in sorted(raw):
        value = raw[engine]
        if isinstance(value, str):
            items.append(SearchEngineTelemetry(engine=str(engine), status=value))
            continue
        if not isinstance(value, Mapping):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "Wigolo engine telemetry is malformed",
                retryable=True,
            )
        try:
            items.append(
                SearchEngineTelemetry(
                    engine=str(engine),
                    status=str(value.get("status") or "unknown"),
                    result_count=value.get("result_count"),
                    latency_ms=value.get("latency_ms"),
                )
            )
        except ValidationError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "Wigolo engine telemetry is malformed",
                retryable=True,
            ) from exc
    return tuple(items)


def _malformed_result(rank: int) -> SearchProviderError:
    return SearchProviderError(
        SearchFailureCode.MALFORMED_RESPONSE,
        f"Wigolo result {rank} is not an object",
        retryable=True,
    )
