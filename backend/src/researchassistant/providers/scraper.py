"""Vendor-neutral synchronous scraper provider contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from researchassistant.contracts.scraping import RetryPolicy as RetryPolicy
from researchassistant.contracts.scraping import ScrapeFailure as ScrapeFailure
from researchassistant.contracts.scraping import ScrapeRequest as ScrapeRequest
from researchassistant.contracts.scraping import ScrapeResponse as ScrapeResponse
from researchassistant.contracts.scraping import ScrapeStatus as ScrapeStatus
from researchassistant.contracts.scraping import (
    VerifiedAcquisitionPreflight as VerifiedAcquisitionPreflight,
)


class ScraperProviderError(RuntimeError):
    """Raised when a scraper provider fails to retrieve a source."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        retryable: bool = False,
        verified_preflight: VerifiedAcquisitionPreflight | None = None,
    ) -> None:
        if message is None:
            message = code
            code = "provider_error"
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.verified_preflight = verified_preflight


class ScraperTimeoutError(ScraperProviderError):
    """Raised when a scraper provider exceeds its configured timeout."""


@runtime_checkable
class ScraperProvider(Protocol):
    """A vendor-isolated, synchronous scraper provider."""

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        """Retrieve one URL without interpreting its content."""


@runtime_checkable
class FallbackScraperProvider(ScraperProvider, Protocol):
    """Scraper route that exposes one explicit fallback-only acquisition."""

    def scrape_fallback(self, request: ScrapeRequest) -> ScrapeResponse:
        """Retrieve one URL directly through the configured fallback."""
