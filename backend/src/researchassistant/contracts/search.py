"""Stable search handoffs shared by providers, research and persistence."""

from __future__ import annotations

import base64
import binascii
import re
from decimal import Decimal
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2MetadataDiscoveryPolicy,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SearchIntent, StrictModel


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
            from researchassistant.contracts.query_compiler import validate_compiled_action

            try:
                validate_compiled_action(compiled)
            except ValueError as exc:
                raise ValueError("compiled query failed deterministic validation") from exc
        return self


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
