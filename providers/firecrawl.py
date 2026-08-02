"""Optional Firecrawl fallback behind the primary Wigolo acquisition boundary."""

from __future__ import annotations

from typing import Any

import httpx

from providers.acquisition import ACQUISITION_VERSION, AcquisitionFailureCode
from providers.config import FirecrawlConfig
from providers.normalization import NormalizationError, normalize_markdown
from providers.scraper import (
    ScrapeRequest,
    ScrapeResponse,
    ScraperProvider,
    ScraperProviderError,
    ScraperTimeoutError,
)

_FALLBACK_CODES = frozenset(
    {
        AcquisitionFailureCode.WIGOLO_CONNECTION,
        AcquisitionFailureCode.WIGOLO_TIMEOUT,
        AcquisitionFailureCode.MALFORMED,
        AcquisitionFailureCode.EXTRACTION,
        AcquisitionFailureCode.CHALLENGE,
    }
)


class FallbackAcquisitionAdapter:
    def __init__(self, *, primary: ScraperProvider, fallback: ScraperProvider | None) -> None:
        self._primary = primary
        self._fallback = fallback

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        try:
            return self._primary.scrape(request)
        except ScraperProviderError as exc:
            if self._fallback is None or exc.code not in _FALLBACK_CODES:
                raise
            return self._fallback.scrape(request)


class FirecrawlAcquisitionAdapter:
    def __init__(self, config: FirecrawlConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.browser_fetch_seconds),
            follow_redirects=False,
        )

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        try:
            response = self._client.post(
                "/v2/scrape",
                headers={
                    "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={"url": request.url, "formats": ["markdown"], "onlyMainContent": True},
                timeout=min(request.timeout_seconds, self._config.deadlines.browser_fetch_seconds),
            )
        except httpx.TimeoutException as exc:
            raise ScraperTimeoutError(
                AcquisitionFailureCode.TIMEOUT, "Firecrawl fallback timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.CONNECTION,
                "Firecrawl fallback connection failed",
                retryable=True,
            ) from exc
        if response.status_code in {401, 403}:
            raise ScraperProviderError(
                AcquisitionFailureCode.AUTHENTICATION, "Firecrawl rejected its API key"
            )
        if response.status_code == 429:
            raise ScraperProviderError(
                AcquisitionFailureCode.RATE_LIMIT, "Firecrawl rate limited the fallback"
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise ScraperProviderError(
                AcquisitionFailureCode.TRANSIENT, "Firecrawl fallback request failed"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.MALFORMED, "Firecrawl returned invalid JSON"
            ) from exc
        data = body.get("data") if isinstance(body, dict) and body.get("success") is True else None
        metadata = data.get("metadata") if isinstance(data, dict) else None
        markdown = data.get("markdown") if isinstance(data, dict) else None
        if not isinstance(metadata, dict) or not isinstance(markdown, str) or not markdown.strip():
            raise ScraperProviderError(
                AcquisitionFailureCode.MALFORMED, "Firecrawl returned no usable markdown"
            )
        status = metadata.get("statusCode")
        if isinstance(status, int) and not 200 <= status < 300:
            raise ScraperProviderError(
                AcquisitionFailureCode.INACCESSIBLE,
                "Firecrawl reported that the public source was inaccessible",
            )
        try:
            document = normalize_markdown(markdown)
        except NormalizationError as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.EXTRACTION, str(exc), retryable=exc.retryable
            ) from exc
        resolved = _text(metadata.get("sourceURL")) or request.url
        content_type = (_text(metadata.get("contentType")) or "text/html").split(";", 1)[0]
        return ScrapeResponse(
            resolved_url=resolved,
            original_url=request.url,
            content_type=content_type,
            text=document.text,
            snapshot_sha256=document.sha256,
            word_count=document.word_count,
            truncated=document.truncated,
            normalization_version=document.normalization_version,
            acquisition_version=ACQUISITION_VERSION,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            rendered=False,
        )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
