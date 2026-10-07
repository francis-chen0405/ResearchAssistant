"""arXiv Atom API adapter for metadata-only fresh-v2 discovery."""

from __future__ import annotations

import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx
from pydantic import ValidationError

from providers.config import ArxivConfig
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

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_WHITESPACE = re.compile(r"\s+")


class ArxivSearchAdapter:
    """Fetch published arXiv metadata without treating abstracts as evidence."""

    physical_accounting = True

    def __init__(self, config: ArxivConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is not DiscoveryProvider.ARXIV:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "arXiv requires a typed arXiv search request",
            )
        parameters = compiled_parameters(
            request,
            allowed_names=frozenset(
                {"search_query", "start", "max_results", "sortBy", "sortOrder"}
            ),
            required_names=frozenset(
                {"search_query", "start", "max_results", "sortBy", "sortOrder"}
            ),
        )
        if parameters is None:
            query_params: dict[str, str | int | bool] = {
                "search_query": _legacy_search_query(request.query_text),
                "start": 0,
                "max_results": request.limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        else:
            expected = {
                "start": 0,
                "max_results": request.limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            if any(parameters.get(key) != value for key, value in expected.items()):
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE,
                    "compiled arXiv parameters contain unsupported paging or sorting settings",
                )
            query_value = parameters.get("search_query")
            if not isinstance(query_value, str) or not query_value.strip():
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE,
                    "compiled arXiv search_query must be a nonempty fielded expression",
                )
            query_params = parameters
        if request.compiled_query is not None:
            validate_request_url(
                str(self._client.base_url) + "api/query", query_params, max_bytes=7500
            )
        try:
            response = physical_request(
                request,
                query_params,
                lambda: self._client.get(
                    "/api/query",
                    params=query_params,
                    timeout=self._config.deadlines.search_seconds,
                ),
            )
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT, "arXiv search timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION, "arXiv search connection failed", retryable=True
            ) from exc
        _raise_status(response.status_code)
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "arXiv returned invalid Atom XML"
            ) from exc
        results = _parse_entries(root, request.limit)
        if not results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS, "arXiv returned no usable results"
            )
        return SearchResponse(
            results=results,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            adapter_version=self._config.adapter_version,
            search_type="metadata",
        )


def _parse_entries(root: ElementTree.Element, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for entry in root.findall(f"{_ATOM}entry"):
        url = _text(entry.find(f"{_ATOM}id"))
        if url is None or url in seen or not _http_url(url):
            continue
        authors = tuple(
            author
            for author in (
                _text(item.find(f"{_ATOM}name")) for item in entry.findall(f"{_ATOM}author")
            )
            if author
        )
        pdf_url = next(
            (
                href
                for link in entry.findall(f"{_ATOM}link")
                if link.get("title") == "pdf" and (href := link.get("href")) and _http_url(href)
            ),
            None,
        )
        try:
            result = SearchResult(
                original_url=url,
                title=_text(entry.find(f"{_ATOM}title")) or "",
                snippet=_text(entry.find(f"{_ATOM}summary")),
                rank=len(results) + 1,
                metadata=SearchDiscoveryMetadata(
                    engine="arxiv",
                    published_at=_text(entry.find(f"{_ATOM}published")),
                    display_url=url,
                    category=_category(entry),
                    author=", ".join(authors) if authors else None,
                    abstract=_text(entry.find(f"{_ATOM}summary")),
                    external_id=url,
                    doi=_text(entry.find(f"{_ARXIV}doi")),
                    is_open_access=True,
                    work_type="preprint",
                    pdf_url=pdf_url,
                ),
            )
        except ValidationError:
            continue
        results.append(result)
        seen.add(url)
        if len(results) >= limit:
            break
    return results


def _category(entry: ElementTree.Element) -> str | None:
    category = entry.find(f"{_ATOM}category")
    return category.get("term") if category is not None else None


def _legacy_search_query(query: str) -> str:
    """Use all-fields for legacy free text without doubling an existing field prefix."""
    normalized = query.strip()
    return normalized if normalized.lower().startswith("all:") else f"all:{normalized}"


def _text(element: ElementTree.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = _WHITESPACE.sub(" ", element.text).strip()
    return value or None


def _http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _raise_status(status: int) -> None:
    if 200 <= status < 300:
        return
    if status == 429:
        raise SearchProviderError(
            SearchFailureCode.RATE_LIMIT, "arXiv rate limit reached", retryable=True
        )
    if status in {408, 504}:
        raise SearchProviderError(
            SearchFailureCode.TIMEOUT, "arXiv search timed out", retryable=True
        )
    if 500 <= status < 600:
        raise SearchProviderError(
            SearchFailureCode.TRANSIENT_OUTAGE, "arXiv is temporarily unavailable", retryable=True
        )
    raise SearchProviderError(
        SearchFailureCode.PERMANENT_FAILURE, f"arXiv search failed with HTTP {status}"
    )
