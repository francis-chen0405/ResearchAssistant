"""Versioned parsed-page checkpoints independent of physical request completions."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from providers.search import SearchResponse
from researchassistant.contracts.model_contracts import StrictModel


class V2QueryPageCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    operation_id: UUID
    binding_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_number: int = Field(strict=True, ge=1, le=3)
    round_number: int = Field(strict=True, ge=1, le=4)
    requested_records: int = Field(strict=True, ge=1, le=50)
    raw_hits: int = Field(strict=True, ge=0, le=50)
    attempt_ids: tuple[UUID, ...] = Field(min_length=1, max_length=3)
    response_hashes: tuple[str, ...] = Field(min_length=1, max_length=3)
    response: SearchResponse

    @model_validator(mode="after")
    def bounded(self) -> V2QueryPageCheckpoint:
        if len(self.attempt_ids) != len(self.response_hashes) or len(set(self.attempt_ids)) != len(
            self.attempt_ids
        ):
            raise ValueError("page requires unique completed physical response identities")
        if (
            len(self.response.results) > self.requested_records
            or len(self.response.results) > self.raw_hits
        ):
            raise ValueError("parsed page exceeds its physical request count")
        return self


class V2QueryParseReceipt(StrictModel):
    """Immutable parser output digest, separate from replayable page contents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    operation_id: UUID
    binding_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_number: int = Field(strict=True, ge=1, le=3)
    attempt_ids: tuple[UUID, ...] = Field(min_length=1, max_length=3)
    response_hashes: tuple[str, ...] = Field(min_length=1, max_length=3)
    parsed_response_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class V2QueryRetrievalResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    operation_id: UUID
    binding_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    retrieval_identity: Literal["source-metadata-retrieval-v2"] = "source-metadata-retrieval-v2"
    requested_depth: int = Field(strict=True, ge=1, le=50)
    effective_depth: int = Field(strict=True, ge=0, le=50)
    raw_hits: int = Field(strict=True, ge=0, le=50)
    retained_records: int = Field(strict=True, ge=0, le=50)
    page_count: int = Field(strict=True, ge=0, le=3)
    stopping_reason: Literal[
        "depth_reached",
        "provider_limit",
        "provider_budget",
        "retention_cap",
        "empty_page",
        "no_new_results",
        "repeated_cursor",
        "malformed_page",
        "provider_failure",
        "unknown_outcome",
        "completed_without_checkpoint",
    ]
    response: SearchResponse
