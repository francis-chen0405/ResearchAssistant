"""Vendor-neutral synchronous search provider contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from models import StrictModel


class SearchProviderError(RuntimeError):
    """Raised when a search provider cannot return a usable result set."""


class SearchTimeoutError(SearchProviderError):
    """Raised when a search provider exceeds its configured timeout."""


class SearchRequest(StrictModel):
    query_text: str = Field(min_length=1)
    limit: int = Field(ge=1)


class SearchResult(StrictModel):
    original_url: str = Field(min_length=1)
    title: str = ""


class SearchResponse(StrictModel):
    results: list[SearchResult]


@runtime_checkable
class SearchProvider(Protocol):
    """A vendor-isolated, synchronous search provider."""

    def search(self, request: SearchRequest) -> SearchResponse:
        """Return results in provider rank order."""
