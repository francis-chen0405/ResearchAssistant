"""PubMed E-utilities adapter for metadata-only fresh-v2 discovery."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from threading import Lock
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from providers.config import PubMedConfig
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
    validate_request_url,
)
from researchassistant.contracts.models import DiscoveryProvider


class PubMedSearchAdapter:
    """Search PubMed then retrieve only bibliographic summaries for discovery."""

    physical_accounting = True

    def __init__(
        self,
        config: PubMedConfig,
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
        self._request_lock = Lock()
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request_start: float | None = None

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is not DiscoveryProvider.PUBMED:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "PubMed requires a typed PubMed search request",
            )
        parameters = compiled_parameters(
            request,
            allowed_names=frozenset({"db", "term", "retmode", "retmax", "retstart", "sort"}),
            required_names=frozenset({"db", "term", "retmode", "retmax", "sort"}),
        )
        if parameters is None:
            query_params: dict[str, str | int | bool] = {
                "db": "pubmed",
                "term": request.query_text,
                "retmode": "json",
                "retmax": request.limit,
                "sort": "relevance",
            }
        else:
            term = parameters.get("term")
            if (
                parameters.get("db") != "pubmed"
                or parameters.get("retmode") != "json"
                or parameters.get("retmax") != request.limit
                or parameters.get("sort") != "relevance"
                or not isinstance(term, str)
                or not term.strip()
                or not any(tag in term.lower() for tag in ("[tiab]", "[title/abstract]"))
            ):
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE,
                    "compiled PubMed query must use a bounded Title/Abstract search",
                )
            query_params = parameters
        if self._config.api_key is not None:
            query_params["api_key"] = self._config.api_key.get_secret_value()
        body = self._get_json("/entrez/eutils/esearch.fcgi", query_params, request=request)
        result = body.get("esearchresult") if isinstance(body, dict) else None
        ids = result.get("idlist") if isinstance(result, dict) else None
        if not isinstance(ids, list) or not all(
            isinstance(item, str) and item.isascii() and item.isdecimal() and len(item) <= 20
            for item in ids
        ):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "PubMed response omitted result identifiers"
            )
        if len(ids) > request.limit:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE,
                "PubMed response exceeds the reserved identifier limit",
            )
        if not ids:
            raise SearchProviderError(SearchFailureCode.EMPTY_RESULTS, "PubMed returned no results")
        summary_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
        if self._config.api_key is not None:
            summary_params["api_key"] = self._config.api_key.get_secret_value()
        summaries = self._get_json(
            "/entrez/eutils/esummary.fcgi",
            summary_params,
            request=request,
            request_kind="metadata",
        )
        records = summaries.get("result") if isinstance(summaries, dict) else None
        if not isinstance(records, dict):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "PubMed response omitted article summaries"
            )
        results = _parse_records(
            ids,
            records,
            request.limit,
            rank_offset=int(query_params.get("retstart", 0)),
            provider_page=request.page_number,
        )
        if not results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS, "PubMed returned no usable results"
            )
        return SearchResponse(
            results=results,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            adapter_version=self._config.adapter_version,
            search_type="metadata",
        )

    def _get_json(
        self,
        path: str,
        params: dict[str, str | int | bool],
        *,
        request: SearchRequest | None = None,
        request_kind: Literal["primary", "metadata"] = "primary",
    ) -> object:
        if request is not None and request.compiled_query is not None:
            validate_request_url(str(self._client.base_url) + path, params)
        try:
            with self._request_lock:
                if request is None or request.compiled_query is None:
                    self._wait_for_slot(None)
                observed_params = {key: value for key, value in params.items() if key != "api_key"}

                def send() -> httpx.Response:
                    return self._send(path, params)

                if request is None:
                    response = send()
                else:
                    response = physical_request(
                        request,
                        observed_params,
                        send,
                        request_kind=request_kind,
                        before_reservation=self._wait_for_slot
                        if request.compiled_query is not None
                        else None,
                    )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT, "PubMed search timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION, "PubMed search connection failed", retryable=True
            ) from exc
        _raise_status(response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "PubMed returned invalid JSON"
            ) from exc

    def _wait_for_slot(self, cancelled: Callable[[], bool] | None) -> None:
        if cancelled is not None and cancelled():
            raise SearchProviderError(SearchFailureCode.CANCELLED, "PubMed request cancelled")
        now = self._monotonic()
        if self._last_request_start is not None:
            deadline = self._last_request_start + 3.0
            while now < deadline:
                if cancelled is not None and cancelled():
                    raise SearchProviderError(
                        SearchFailureCode.CANCELLED,
                        "PubMed request cancelled while rate limited",
                    )
                self._sleep(min(max(deadline - now, 0.001), 0.1))
                now = self._monotonic()
        if cancelled is not None and cancelled():
            raise SearchProviderError(SearchFailureCode.CANCELLED, "PubMed request cancelled")

    def _send(self, path: str, params: dict[str, str | int | bool]) -> httpx.Response:
        self._last_request_start = self._monotonic()
        return bounded_send(
            self._client,
            "GET",
            path,
            expected_base_url=self._config.base_url,
            params=params,
            timeout=self._config.deadlines.search_seconds,
        )


def _parse_records(
    ids: list[str],
    records: dict[str, Any],
    limit: int,
    rank_offset: int = 0,
    *,
    provider_page: int = 1,
) -> list[SearchResult]:
    results: list[SearchResult] = []
    for index, uid in enumerate(ids, start=1):
        item = records.get(uid)
        if not isinstance(item, dict):
            continue
        url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
        article_ids = item.get("articleids")
        doi = (
            next(
                (
                    entry.get("value")
                    for entry in article_ids
                    if isinstance(entry, dict)
                    and entry.get("idtype") == "doi"
                    and isinstance(entry.get("value"), str)
                ),
                None,
            )
            if isinstance(article_ids, list)
            else None
        )
        authors = item.get("authors")
        pmc_id = _pmc_id(item.get("pmc"))
        if pmc_id is None and isinstance(article_ids, list):
            pmc_id = next(
                (
                    parsed
                    for entry in article_ids
                    if isinstance(entry, dict) and entry.get("idtype") == "pmc"
                    if (parsed := _pmc_id(entry.get("value"))) is not None
                ),
                None,
            )
        author_names = (
            tuple(
                author.get("name")
                for author in authors
                if isinstance(author, dict) and isinstance(author.get("name"), str)
            )
            if isinstance(authors, list)
            else ()
        )
        try:
            result = SearchResult(
                original_url=url,
                title=item.get("title") if isinstance(item.get("title"), str) else "",
                rank=rank_offset + index,
                metadata=SearchDiscoveryMetadata(
                    engine="pubmed",
                    provider_page=provider_page,
                    raw_provider_rank=index,
                    published_at=_string(item.get("pubdate")) or _string(item.get("sortpubdate")),
                    display_url=url,
                    category="biomedical",
                    author=", ".join(author_names) if author_names else None,
                    external_id=uid,
                    doi=doi,
                    is_open_access=_string(item.get("pmc")) is not None,
                    full_text_url=(
                        f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc_id}/"
                        if pmc_id is not None
                        else None
                    ),
                    work_type=_string(item.get("pubtype")) or "journal_article",
                ),
            )
        except ValidationError:
            continue
        results.append(result)
        if len(results) >= limit:
            break
    return results


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _pmc_id(value: object) -> str | None:
    candidate = _string(value)
    return candidate if candidate is not None and re.fullmatch(r"PMC[0-9]+", candidate) else None


def _raise_status(status: int) -> None:
    if 200 <= status < 300:
        return
    if status in {401, 403}:
        raise SearchProviderError(SearchFailureCode.AUTHENTICATION, "PubMed authentication failed")
    if status == 429:
        raise SearchProviderError(
            SearchFailureCode.RATE_LIMIT, "PubMed rate limit reached", retryable=True
        )
    if status in {408, 504}:
        raise SearchProviderError(
            SearchFailureCode.TIMEOUT, "PubMed search timed out", retryable=True
        )
    if 500 <= status < 600:
        raise SearchProviderError(
            SearchFailureCode.TRANSIENT_OUTAGE, "PubMed is temporarily unavailable", retryable=True
        )
    raise SearchProviderError(
        SearchFailureCode.PERMANENT_FAILURE, f"PubMed search failed with HTTP {status}"
    )
