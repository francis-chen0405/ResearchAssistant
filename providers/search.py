"""Vendor-neutral synchronous search provider contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator

from models import StrictModel


class SearchFailureCode(StrEnum):
    MISSING_CONFIGURATION = "missing_configuration"
    CONNECTION = "connection_failure"
    AUTHENTICATION = "authentication_failure"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    TRANSIENT_OUTAGE = "transient_outage"
    PERMANENT_FAILURE = "permanent_request_failure"
    MALFORMED_RESPONSE = "malformed_success_response"
    EMPTY_RESULTS = "empty_results"
    INVALID_URL = "invalid_url"


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


class SearchRequest(StrictModel):
    query_text: str = Field(min_length=1)
    limit: int = Field(ge=1)


class SearchDiscoveryMetadata(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: str | None = None
    published_at: str | None = None
    display_url: str | None = None
    category: str | None = None


class SearchEngineTelemetry(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: str
    status: str
    result_count: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)


class SearchResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_url: str = Field(min_length=1)
    title: str = ""
    rank: int = Field(default=1, ge=1, le=5)
    relevance_score: float | None = None
    snippet: str | None = None
    metadata: SearchDiscoveryMetadata = SearchDiscoveryMetadata()

    @field_validator("original_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("search result URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("search result URL cannot contain credentials")
        return value


class SearchResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    results: list[SearchResult]
    provider_name: str = "unknown"
    provider_version: str = "unknown"
    adapter_version: str = "unknown"
    engine_telemetry: tuple[SearchEngineTelemetry, ...] = ()
    warnings: tuple[str, ...] = ()
    degraded_pool: bool = False


@runtime_checkable
class SearchProvider(Protocol):
    """A vendor-isolated, synchronous search provider."""

    def search(self, request: SearchRequest) -> SearchResponse:
        """Return results in provider rank order."""
