"""Vendor-neutral synchronous search provider contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from urllib.parse import urlencode

from researchassistant.contracts.models import DiscoveryProvider
from researchassistant.contracts.search import _CURSOR_PATTERN as _CURSOR_PATTERN
from researchassistant.contracts.search import SearchDiscoveryMetadata as SearchDiscoveryMetadata
from researchassistant.contracts.search import SearchEngineTelemetry as SearchEngineTelemetry
from researchassistant.contracts.search import SearchFailureCode as SearchFailureCode
from researchassistant.contracts.search import SearchRequest as SearchRequest
from researchassistant.contracts.search import SearchResponse as SearchResponse
from researchassistant.contracts.search import SearchResult as SearchResult
from researchassistant.contracts.search import _valid_opaque_cursor as _valid_opaque_cursor
from researchassistant.contracts.search import metadata_page_size as metadata_page_size


class SearchProviderError(RuntimeError):
    """Raised when a search provider cannot return a usable result set."""

    def __init__(
        self,
        code: SearchFailureCode | str,
        message: str | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        if message is None:
            message = str(code)
            code = SearchFailureCode.PERMANENT_FAILURE
        super().__init__(message)
        self.code = SearchFailureCode(code)
        self.retryable = retryable


class SearchTimeoutError(SearchProviderError):
    """Raised when a search provider exceeds its configured timeout."""


def compiled_parameters(
    request: SearchRequest,
    *,
    allowed_names: frozenset[str],
    required_names: frozenset[str],
) -> dict[str, str | int | bool] | None:
    """Validate and return the compiler-owned native request parameters.

    ``None`` means this is a legacy request and adapters should retain their historic
    query construction. Compiled requests may only supply the provider's reviewed
    native parameters; authentication and transport-only values stay adapter-owned.
    """
    action = request.compiled_query
    if action is None:
        return None
    parameters = page_parameters(request)
    names = set(parameters)
    if names - allowed_names:
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "compiled query contains unsupported provider parameters: "
            f"{', '.join(sorted(names - allowed_names))}",
        )
    if not required_names <= names:
        missing = ", ".join(sorted(required_names - names))
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            f"compiled query omitted required provider parameters: {missing}",
        )
    return parameters


def page_parameters(request: SearchRequest) -> dict[str, str | int | bool]:
    """Derive native paging values from the immutable application-owned operation."""
    action = request.compiled_query
    if action is None:
        raise ValueError("page parameters require a compiled operation")
    parameters = {item.name: item.value for item in action.parameters}
    provider = request.provider
    page_size = metadata_page_size(action)
    offset = (request.page_number - 1) * page_size
    if offset + request.limit > action.effective_depth:
        raise ValueError("page limit exceeds cumulative operation depth")
    if provider is DiscoveryProvider.SERPSEARCH:
        parameters["page"] = request.page_number
    elif provider is DiscoveryProvider.ARXIV:
        parameters.update(start=offset, max_results=request.limit)
    elif provider is DiscoveryProvider.PUBMED:
        parameters["retmax"] = request.limit
        if request.page_number > 1:
            parameters["retstart"] = offset
    elif provider is DiscoveryProvider.EXA:
        parameters["numResults"] = request.limit
    elif provider is DiscoveryProvider.OPENALEX:
        parameters["per_page"] = request.limit
        if action.mode != "semantic":
            parameters["cursor"] = request.page_cursor or "*"
        elif request.page_number > 1 or request.page_cursor is not None:
            raise ValueError("semantic search is count-only under the bounded policy")
    return parameters


def validate_request_url(
    endpoint: str, parameters: dict[str, str | int | bool], *, max_bytes: int = 7500
) -> None:
    """Check the final encoded URL in memory; errors never reveal credential values."""
    encoded = endpoint + "?" + urlencode(parameters)
    if len(encoded.encode("utf-8")) > max_bytes:
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "encoded provider request URL exceeds its bounded policy",
        )


@runtime_checkable
class SearchProvider(Protocol):
    """A vendor-isolated, synchronous search provider."""

    def search(self, request: SearchRequest) -> SearchResponse:
        """Return results in provider rank order."""
