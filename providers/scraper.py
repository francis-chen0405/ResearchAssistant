"""Vendor-neutral synchronous scraper provider contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import Field, model_validator

from models import StrictModel


class ScraperProviderError(RuntimeError):
    """Raised when a scraper provider fails to retrieve a source."""


class ScraperTimeoutError(ScraperProviderError):
    """Raised when a scraper provider exceeds its configured timeout."""


class ScrapeStatus(StrEnum):
    RETRIEVED = "retrieved"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"
    DUPLICATE_URL = "duplicate_url"
    DUPLICATE_CONTENT = "duplicate_content"


class ScrapeRequest(StrictModel):
    url: str = Field(min_length=1)
    timeout_seconds: float = Field(gt=0)


class ScrapeResponse(StrictModel):
    resolved_url: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    text: str


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


@runtime_checkable
class ScraperProvider(Protocol):
    """A vendor-isolated, synchronous scraper provider."""

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        """Retrieve one URL without interpreting its content."""
