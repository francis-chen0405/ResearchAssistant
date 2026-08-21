"""PubMed E-utilities adapter for metadata-only fresh-v2 discovery."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from models import DiscoveryProvider
from providers.config import PubMedConfig
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
)


class PubMedSearchAdapter:
    """Search PubMed then retrieve only bibliographic summaries for discovery."""

    def __init__(self, config: PubMedConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is not DiscoveryProvider.PUBMED:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "PubMed requires a typed PubMed search request",
            )
        params: dict[str, str] = {
            "db": "pubmed",
            "term": request.query_text,
            "retmode": "json",
            "retmax": str(request.limit),
            "sort": "relevance",
        }
        if self._config.api_key is not None:
            params["api_key"] = self._config.api_key.get_secret_value()
        body = self._get_json("/entrez/eutils/esearch.fcgi", params)
        result = body.get("esearchresult") if isinstance(body, dict) else None
        ids = result.get("idlist") if isinstance(result, dict) else None
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "PubMed response omitted result identifiers"
            )
        if not ids:
            raise SearchProviderError(SearchFailureCode.EMPTY_RESULTS, "PubMed returned no results")
        summary_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
        if self._config.api_key is not None:
            summary_params["api_key"] = self._config.api_key.get_secret_value()
        summaries = self._get_json("/entrez/eutils/esummary.fcgi", summary_params)
        records = summaries.get("result") if isinstance(summaries, dict) else None
        if not isinstance(records, dict):
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "PubMed response omitted article summaries"
            )
        results = _parse_records(ids, records, request.limit)
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

    def _get_json(self, path: str, params: dict[str, str]) -> object:
        try:
            response = self._client.get(path, params=params)
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


def _parse_records(ids: list[str], records: dict[str, Any], limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for uid in ids:
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
                rank=len(results) + 1,
                metadata=SearchDiscoveryMetadata(
                    engine="pubmed",
                    published_at=_string(item.get("pubdate")) or _string(item.get("sortpubdate")),
                    display_url=url,
                    category="biomedical",
                    author=", ".join(author_names) if author_names else None,
                    external_id=uid,
                    doi=doi,
                    is_open_access=_string(item.get("pmc")) is not None,
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
