"""Stable source acquisition request/result shapes, independent of adapters."""

from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import (
    MediaTypeProvenance,
    StrictModel,
    SupportedOriginMediaType,
)


class ScrapeStatus(StrEnum):
    RETRIEVED = "retrieved"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"
    DUPLICATE_URL = "duplicate_url"
    DUPLICATE_CONTENT = "duplicate_content"


class VerifiedAcquisitionPreflight(StrictModel):
    """Independently established public-source identity available to fallback."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_url: str = Field(min_length=1)
    resolved_url: str = Field(min_length=1)
    canonical_url: str | None = None
    media_type: SupportedOriginMediaType


class ScrapeRequest(StrictModel):
    url: str = Field(min_length=1)
    timeout_seconds: float = Field(gt=0)
    verified_preflight: VerifiedAcquisitionPreflight | None = None


class ScrapeResponse(StrictModel):
    resolved_url: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    text: str
    original_url: str | None = None
    canonical_url: str | None = None
    snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    word_count: int | None = Field(default=None, ge=1, le=12_000)
    truncated: bool = False
    normalization_version: str | None = None
    acquisition_version: str | None = None
    provider_name: str = "unknown"
    provider_version: str = "unknown"
    rendered: bool = False
    media_type_provenance: MediaTypeProvenance = MediaTypeProvenance()

    @model_validator(mode="after")
    def validate_media_type_provenance(self) -> ScrapeResponse:
        provenance = self.media_type_provenance
        if (
            provenance.verified_source_url == self.resolved_url
            and provenance.verified_media_type is not None
            and self.content_type != provenance.verified_media_type
        ):
            raise ValueError("applicable verified media type must remain authoritative")
        return self


class RetryPolicy(StrictModel):
    max_attempts: int = Field(default=2, ge=1, le=5)
    timeout_seconds: float = Field(default=10.0, gt=0)


class ScrapeFailure(StrictModel):
    status: ScrapeStatus
    message: str = Field(min_length=1)
    attempts_made: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_failure_status(self) -> ScrapeFailure:
        if self.status not in {ScrapeStatus.FAILED, ScrapeStatus.TIMEOUT}:
            raise ValueError("scrape failures require failed or timeout status")
        return self
