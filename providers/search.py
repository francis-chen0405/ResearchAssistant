"""Vendor-neutral synchronous search provider contracts."""

from __future__ import annotations

import base64
import binascii
import re
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2MetadataDiscoveryPolicy,
)
from researchassistant.contracts.models import DiscoveryProvider, SearchIntent, StrictModel


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
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"


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
    run_id: UUID | None = None
    provider: DiscoveryProvider = DiscoveryProvider.EXA
    intent: SearchIntent = SearchIntent.BROAD_WEB
    semantic: bool = False
    query_text: str = Field(min_length=1)
    limit: int = Field(ge=1, le=100)
    compiled_query: V2CompiledQueryAction | None = None
    page_number: int = Field(default=1, strict=True, ge=1, le=3)
    page_cursor: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_provider_controls(self) -> SearchRequest:
        if self.semantic and self.provider is not DiscoveryProvider.OPENALEX:
            raise ValueError("semantic search is available only for OpenAlex")
        if self.provider is DiscoveryProvider.OPENALEX:
            if self.run_id is None:
                raise ValueError("OpenAlex searches require a run_id for budget accounting")
            if self.intent is not SearchIntent.ACADEMIC_STUDY:
                raise ValueError("OpenAlex searches require academic-study intent")
        if self.compiled_query is not None:
            compiled = self.compiled_query
            if compiled.run_id != self.run_id:
                raise ValueError("compiled query run does not match the search request")
            if compiled.conceptual_query.provider is not self.provider:
                raise ValueError("compiled query provider does not match the search request")
            if compiled.query_text != self.query_text:
                raise ValueError("compiled query text does not match the search request")
            page_size = metadata_page_size(compiled)
            if self.limit > min(compiled.effective_depth, page_size):
                raise ValueError("search limit exceeds compiled page depth")
            page_budget = (
                compiled.policy.max_pages_per_operation
                // compiled.capabilities.physical_requests_per_page
            )
            if compiled.capabilities.executable_pagination == "none" or (
                self.provider is DiscoveryProvider.OPENALEX and compiled.mode == "semantic"
            ):
                page_budget = min(page_budget, 1)
            page_count = (compiled.effective_depth + page_size - 1) // page_size
            if self.page_number > min(page_budget, page_count):
                raise ValueError("page number exceeds physical request policy")
            if compiled.capabilities.executable_pagination == "none" and self.page_number != 1:
                raise ValueError("provider does not support page transport")
            cursor_paging = (
                compiled.capabilities.executable_pagination == "cursor"
                and self.provider is DiscoveryProvider.OPENALEX
                and compiled.mode != "semantic"
            )
            if self.page_cursor is not None and (
                not cursor_paging or not _valid_opaque_cursor(self.page_cursor)
            ):
                raise ValueError("invalid opaque provider cursor")
            if cursor_paging and self.page_number > 1 and self.page_cursor is None:
                raise ValueError("cursor page requires the prior page cursor")
            if cursor_paging and self.page_number > 1 and self.page_cursor == "*":
                raise ValueError("cursor page cannot restart at the provider start cursor")
            if self.page_number == 1 and self.page_cursor not in (None, "*"):
                raise ValueError("first cursor page must use the provider start cursor")
            if self.semantic != (compiled.mode == "semantic"):
                raise ValueError("semantic flag does not match compiled query mode")
            if (
                self.provider is DiscoveryProvider.OPENALEX
                and compiled.mode == "semantic"
                and compiled.effective_depth > 50
            ):
                raise ValueError("OpenAlex semantic searches are limited to 50 results")
            from researchassistant.research.query_compiler import validate_compiled_action

            try:
                validate_compiled_action(compiled)
            except ValueError as exc:
                raise ValueError("compiled query failed deterministic validation") from exc
        return self


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


def metadata_page_size(action: V2CompiledQueryAction) -> int:
    """Return the deterministic page size shared by execution and adapters."""
    provider = action.conceptual_query.provider
    native_page_limit = min(action.effective_depth, action.capabilities.max_metadata_per_page)
    if isinstance(action.policy, V2MetadataDiscoveryPolicy):
        return action.policy.page_size_for(provider, action.mode, native_page_limit)
    return native_page_limit


_CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9+/_-]+={0,2}$")


def _valid_opaque_cursor(value: str) -> bool:
    if value == "*":
        return True
    if (
        not value
        or len(value) > 512
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        or "://" in value
        or not _CURSOR_PATTERN.fullmatch(value)
        or len(value.rstrip("=")) % 4 == 1
        or ("=" in value and len(value) % 4 != 0)
    ):
        return False
    padded = value + "=" * (-len(value) % 4)
    try:
        base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return False
    return True


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


class SearchDiscoveryMetadata(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: str | None = None
    provider_page: int | None = Field(default=None, strict=True, ge=1, le=3)
    raw_provider_rank: int | None = Field(default=None, strict=True, ge=1, le=100)
    published_at: str | None = None
    display_url: str | None = None
    category: str | None = None
    author: str | None = None
    abstract: str | None = None
    external_id: str | None = None
    doi: str | None = None
    cited_by_count: int | None = Field(default=None, ge=0)
    is_open_access: bool | None = None
    work_type: str | None = None
    is_retracted: bool | None = None
    pdf_url: str | None = None
    full_text_url: str | None = None


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
    rank: int = Field(default=1, ge=1, le=100)
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
    request_id: str | None = None
    search_type: str | None = None
    cost_usd: Decimal | None = Field(default=None, ge=0)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("next_cursor")
    @classmethod
    def validate_next_cursor(cls, value: str | None) -> str | None:
        if value is not None and (value == "*" or not _valid_opaque_cursor(value)):
            raise ValueError("provider next cursor must be bounded opaque base64")
        return value


@runtime_checkable
class SearchProvider(Protocol):
    """A vendor-isolated, synchronous search provider."""

    def search(self, request: SearchRequest) -> SearchResponse:
        """Return results in provider rank order."""
