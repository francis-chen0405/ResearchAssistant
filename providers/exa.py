"""Exa metadata-only discovery adapter for new live research runs."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import ValidationError

from providers.config import ExaConfig
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
)

DEFAULT_EXCLUDED_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "threads.net",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "pinterest.com",
    "snapchat.com",
    "quora.com",
    "reddit.com",
    "vimeo.com",
    "dailymotion.com",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "monster.com",
    "simplyhired.com",
    "careerbuilder.com",
    "governmentjobs.com",
    "usajobs.gov",
    "jobrapido.com",
    "jooble.org",
    "talent.com",
    "jobs2careers.com",
    "learn4good.com",
    "lensa.com",
    "snagajob.com",
    "dice.com",
    "builtin.com",
    "wellfound.com",
    "theorg.com",
    "rocketreach.co",
    "zoominfo.com",
    "crunchbase.com",
    "coursehero.com",
    "chegg.com",
    "scribd.com",
    "slideshare.net",
)
_SITE_EXCLUSION = re.compile(r"(?:^|\s)-site:([^\s]+)", re.IGNORECASE)


class ExaSearchAdapter:
    def __init__(self, config: ExaConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        query, exclusions = _query_and_exclusions(request.query_text)
        if not query:
            raise SearchProviderError(SearchFailureCode.PERMANENT_FAILURE, "search query is empty")
        payload = {
            "query": query,
            "type": self._config.search_type,
            "numResults": request.limit,
            "excludeDomains": exclusions,
        }
        try:
            response = self._client.post(
                "/search",
                headers={
                    "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._config.deadlines.search_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT, "Exa search timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION, "Exa search connection failed", retryable=True
            ) from exc
        _raise_status(response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "Exa returned invalid JSON"
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "Exa response omitted results"
            )
        results: list[SearchResult] = []
        seen: set[str] = set()
        for item in body["results"]:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            url = item["url"]
            if url in seen:
                continue
            try:
                result = SearchResult(
                    original_url=url,
                    title=item.get("title") if isinstance(item.get("title"), str) else "",
                    rank=len(results) + 1,
                    metadata=SearchDiscoveryMetadata(
                        engine="exa",
                        published_at=_string_or_none(item.get("publishedDate")),
                        display_url=url,
                        author=_string_or_none(item.get("author")),
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
                SearchFailureCode.EMPTY_RESULTS, "Exa returned no valid discovery results"
            )
        return SearchResponse(
            results=results,
            provider_name="exa",
            provider_version="search-api",
            adapter_version=self._config.adapter_version,
            request_id=_string_or_none(body.get("requestId")),
            search_type=_string_or_none(body.get("searchType")),
            cost_usd=_cost(body.get("costDollars")),
        )


def _query_and_exclusions(value: str) -> tuple[str, list[str]]:
    discovered = [
        match.group(1).strip().lower().removeprefix("www.")
        for match in _SITE_EXCLUSION.finditer(value)
    ]
    query = " ".join(_SITE_EXCLUSION.sub(" ", value).split())
    return query, list(dict.fromkeys([*DEFAULT_EXCLUDED_DOMAINS, *discovered]))


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _cost(value: Any) -> Decimal | None:
    raw = value.get("total") if isinstance(value, dict) else None
    try:
        return Decimal(str(raw)) if raw is not None else None
    except (InvalidOperation, ValueError):
        return None


def _raise_status(status: int) -> None:
    if 200 <= status < 300:
        return
    if status in {401, 403}:
        code, retryable = SearchFailureCode.AUTHENTICATION, False
    elif status == 429:
        code, retryable = SearchFailureCode.RATE_LIMIT, True
    elif status in {408, 504}:
        code, retryable = SearchFailureCode.TIMEOUT, True
    elif 500 <= status < 600:
        code, retryable = SearchFailureCode.TRANSIENT_OUTAGE, True
    else:
        code, retryable = SearchFailureCode.PERMANENT_FAILURE, False
    raise SearchProviderError(code, f"Exa search failed with HTTP {status}", retryable=retryable)
