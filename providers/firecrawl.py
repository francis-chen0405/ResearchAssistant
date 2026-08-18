"""Optional Firecrawl fallback behind the primary Wigolo acquisition boundary."""

from __future__ import annotations

from typing import Any

import httpx

from models import MediaTypeProvenance
from providers.acquisition import (
    ACQUISITION_VERSION,
    AcquisitionFailureCode,
    HostResolver,
    _resolve_host_addresses,
    _validate_public_url,
)
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
        AcquisitionFailureCode.AUTHENTICATION,
        AcquisitionFailureCode.PAYWALL,
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
            fallback_request = ScrapeRequest(
                url=request.url,
                timeout_seconds=request.timeout_seconds,
                verified_preflight=exc.verified_preflight,
            )
            return self._fallback.scrape(fallback_request)

    def scrape_fallback(self, request: ScrapeRequest) -> ScrapeResponse:
        """Use the configured fallback directly for one bounded re-acquisition."""
        if self._fallback is None:
            raise ScraperProviderError(
                AcquisitionFailureCode.EXTRACTION,
                "Firecrawl fallback is not configured",
            )
        return self._fallback.scrape(request)


class FirecrawlAcquisitionAdapter:
    def __init__(
        self,
        config: FirecrawlConfig,
        *,
        client: httpx.Client | None = None,
        host_resolver: HostResolver | None = None,
    ) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.browser_fetch_seconds),
            follow_redirects=False,
        )
        self._host_resolver = host_resolver or _resolve_host_addresses

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        preflight = request.verified_preflight
        target_url = preflight.resolved_url if preflight is not None else request.url
        _validate_public_url(target_url, resolver=self._host_resolver)
        try:
            response = self._client.post(
                "/v2/scrape",
                headers={
                    "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={"url": target_url, "formats": ["markdown"], "onlyMainContent": True},
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
        returned_source = _optional_url(metadata, "sourceURL")
        resolved = returned_source or target_url
        _validate_public_url(resolved, resolver=self._host_resolver)
        provider_canonical = _firecrawl_canonical_url(metadata)
        if provider_canonical is not None:
            _validate_public_url(provider_canonical, resolver=self._host_resolver)
        canonical = (
            preflight.canonical_url
            if preflight is not None and preflight.canonical_url is not None
            else provider_canonical
        )
        provider_declared_media_type = _provider_declared_media_type(metadata.get("contentType"))
        provenance = MediaTypeProvenance(
            verified_media_type=preflight.media_type if preflight is not None else None,
            verified_source_url=preflight.resolved_url if preflight is not None else None,
            provider_declared_media_type=provider_declared_media_type,
        )
        content_type = (
            preflight.media_type
            if preflight is not None and preflight.resolved_url == resolved
            else "text/markdown"
        )
        return ScrapeResponse(
            resolved_url=resolved,
            original_url=preflight.original_url if preflight is not None else request.url,
            canonical_url=canonical,
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
            media_type_provenance=provenance,
        )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _provider_declared_media_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    base_type = value.split(";", 1)[0].strip().lower()
    if base_type not in {"text/html", "text/plain", "application/pdf"}:
        return None
    return base_type


def _optional_url(metadata: dict[str, Any], key: str) -> str | None:
    if key not in metadata or metadata[key] is None:
        return None
    value = metadata[key]
    if not isinstance(value, str) or not value.strip():
        raise ScraperProviderError(
            AcquisitionFailureCode.MALFORMED,
            f"Firecrawl returned malformed {key} provenance",
            retryable=False,
        )
    return value.strip()


def _firecrawl_canonical_url(metadata: dict[str, Any]) -> str | None:
    values = [
        value
        for key in ("canonicalURL", "canonicalUrl")
        if (value := _optional_url(metadata, key)) is not None
    ]
    if len(set(values)) > 1:
        raise ScraperProviderError(
            AcquisitionFailureCode.MALFORMED,
            "Firecrawl returned conflicting canonical provenance",
            retryable=False,
        )
    return values[0] if values else None
