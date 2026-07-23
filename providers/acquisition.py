"""Bounded source acquisition and deterministic snapshot construction."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from providers.config import WigoloConfig
from providers.normalization import (
    NormalizationError,
    normalize_markdown,
    normalize_pdf,
    normalize_plain_text,
)
from providers.scraper import (
    ScrapeRequest,
    ScrapeResponse,
    ScraperProviderError,
    ScraperTimeoutError,
)

ACQUISITION_VERSION = "mvp2b-acquisition-v1"
_CANONICAL = re.compile(
    r"<link\b[^>]*\brel=[\"']?canonical[\"']?[^>]*\bhref=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


class AcquisitionFailureCode:
    CONNECTION = "connection_failure"
    AUTHENTICATION = "authentication_failure"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient_outage"
    INACCESSIBLE = "inaccessible"
    PAYWALL = "paywalled"
    CHALLENGE = "challenge_blocked"
    UNSUPPORTED = "unsupported_content"
    TOO_LARGE = "response_too_large"
    REDIRECT = "redirect_limit"
    CONTENT_TYPE = "invalid_content_type"
    MALFORMED = "malformed_response"
    EXTRACTION = "extraction_failure"


class WigoloAcquisitionAdapter:
    """Preflight source metadata, then use Wigolo only for supported HTML extraction."""

    def __init__(
        self,
        config: WigoloConfig,
        *,
        source_client: httpx.Client | None = None,
        wigolo_client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._source_client = source_client or httpx.Client(
            timeout=httpx.Timeout(config.deadlines.html_fetch_seconds),
            follow_redirects=True,
            max_redirects=config.max_redirects,
        )
        self._wigolo_client = wigolo_client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.browser_fetch_seconds),
            follow_redirects=False,
        )

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.monotonic()
        preflight = self._preflight(request)
        if time.monotonic() - started > self._config.deadlines.candidate_seconds:
            raise ScraperTimeoutError(
                AcquisitionFailureCode.TIMEOUT,
                "candidate acquisition exceeded its total deadline",
                retryable=True,
            )
        media_type = preflight["media_type"]
        payload = preflight["payload"]
        rendered = False
        try:
            if media_type == "application/pdf":
                document = normalize_pdf(
                    payload,
                    max_pages=self._config.max_pdf_pages,
                    deadline_seconds=self._config.deadlines.pdf_fetch_seconds,
                )
            elif media_type == "text/plain":
                document = normalize_plain_text(payload, declared_charset=preflight["charset"])
            elif media_type == "text/html":
                markdown, rendered = self._fetch_markdown(request.url)
                document = normalize_markdown(markdown)
            else:
                raise ScraperProviderError(
                    AcquisitionFailureCode.UNSUPPORTED,
                    "source content type is unsupported",
                    retryable=False,
                )
        except NormalizationError as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.UNSUPPORTED,
                str(exc),
                retryable=exc.retryable,
            ) from exc
        return ScrapeResponse(
            resolved_url=preflight["final_url"],
            original_url=request.url,
            canonical_url=preflight["canonical_url"],
            content_type=media_type,
            text=document.text,
            snapshot_sha256=document.sha256,
            word_count=document.word_count,
            truncated=document.truncated,
            normalization_version=document.normalization_version,
            acquisition_version=ACQUISITION_VERSION,
            provider_name=self._config.provider_name,
            provider_version=self._config.provider_version,
            rendered=rendered,
        )

    def _preflight(self, request: ScrapeRequest) -> dict[str, Any]:
        _validate_public_url(request.url)
        try:
            with self._source_client.stream(
                "GET",
                request.url,
                timeout=min(request.timeout_seconds, self._config.deadlines.pdf_fetch_seconds),
            ) as response:
                if len(response.history) > self._config.max_redirects:
                    raise ScraperProviderError(
                        AcquisitionFailureCode.REDIRECT,
                        "source exceeded the redirect limit",
                        retryable=False,
                    )
                _raise_source_status(response.status_code)
                content_type, charset = _parse_content_type(response.headers.get("content-type"))
                limit = (
                    self._config.max_pdf_bytes
                    if content_type == "application/pdf" or request.url.lower().endswith(".pdf")
                    else self._config.max_html_bytes
                )
                declared_length = response.headers.get("content-length")
                if declared_length and declared_length.isdigit() and int(declared_length) > limit:
                    raise _too_large()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise _too_large()
                    chunks.append(chunk)
                payload = b"".join(chunks)
                if payload.startswith(b"%PDF-"):
                    content_type = "application/pdf"
                if content_type not in {"text/html", "text/plain", "application/pdf"}:
                    raise ScraperProviderError(
                        AcquisitionFailureCode.CONTENT_TYPE,
                        "source did not return a supported content type",
                        retryable=False,
                    )
                final_url = str(response.url)
                canonical = _canonical_url(
                    response.headers.get("link"), payload, final_url, content_type
                )
        except ScraperProviderError:
            raise
        except httpx.TooManyRedirects as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.REDIRECT,
                "source exceeded the redirect limit",
                retryable=False,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ScraperTimeoutError(
                AcquisitionFailureCode.TIMEOUT, "source preflight timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.CONNECTION,
                "source preflight connection failed",
                retryable=True,
            ) from exc
        return {
            "payload": payload,
            "media_type": content_type,
            "charset": charset,
            "final_url": final_url,
            "canonical_url": canonical,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }

    def _fetch_markdown(self, url: str) -> tuple[str, bool]:
        first = self._wigolo_fetch(
            url, render_js="never", timeout=self._config.deadlines.html_fetch_seconds
        )
        if first[0] == "ok":
            return first[1], False
        if first[0] not in {"challenge", "javascript_required"}:
            raise _wigolo_failure(first[0])
        second = self._wigolo_fetch(
            url, render_js="always", timeout=self._config.deadlines.browser_fetch_seconds
        )
        if second[0] != "ok":
            raise ScraperProviderError(
                AcquisitionFailureCode.CHALLENGE,
                "source remained inaccessible after the controlled render attempt",
                retryable=False,
            )
        return second[1], True

    def _wigolo_fetch(self, url: str, *, render_js: str, timeout: float) -> tuple[str, str]:
        try:
            response = self._wigolo_client.post(
                "/v1/fetch",
                json={"url": url, "render_js": render_js, "force_refresh": True},
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise ScraperTimeoutError(
                AcquisitionFailureCode.TIMEOUT, "Wigolo fetch timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.CONNECTION,
                "Wigolo fetch could not connect to loopback service",
                retryable=True,
            ) from exc
        if response.status_code != 200:
            _raise_source_status(response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise ScraperProviderError(
                AcquisitionFailureCode.MALFORMED,
                "Wigolo fetch response was not valid JSON",
                retryable=True,
            ) from exc
        if not isinstance(body, dict):
            raise ScraperProviderError(
                AcquisitionFailureCode.MALFORMED,
                "Wigolo fetch response was not an object",
                retryable=True,
            )
        status = str(body.get("status") or ("ok" if body.get("markdown") else "failed"))
        markdown = body.get("markdown") or body.get("content") or ""
        if status == "ok" and not isinstance(markdown, str):
            raise ScraperProviderError(
                AcquisitionFailureCode.MALFORMED,
                "Wigolo fetch content was malformed",
                retryable=True,
            )
        return status, markdown


def _parse_content_type(value: str | None) -> tuple[str, str | None]:
    if not value:
        return "", None
    parts = [part.strip() for part in value.split(";")]
    media_type = parts[0].lower()
    charset = None
    for part in parts[1:]:
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip('"')
    return media_type, charset


def _canonical_url(link: str | None, payload: bytes, final_url: str, media_type: str) -> str | None:
    if link:
        for value in link.split(","):
            if 'rel="canonical"' in value.lower() or "rel=canonical" in value.lower():
                match = re.search(r"<([^>]+)>", value)
                if match:
                    return urljoin(final_url, match.group(1))
    if media_type == "text/html":
        match = _CANONICAL.search(payload[:262_144].decode("utf-8", errors="ignore"))
        if match:
            return urljoin(final_url, match.group(1))
    return None


def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise ScraperProviderError(
            AcquisitionFailureCode.INACCESSIBLE,
            "source URL must be an absolute credential-free HTTP(S) URL",
            retryable=False,
        )


def _raise_source_status(status: int) -> None:
    if 200 <= status < 300:
        return
    if status in {401, 403}:
        raise ScraperProviderError(
            AcquisitionFailureCode.AUTHENTICATION, "source access was denied", retryable=False
        )
    if status in {402, 451}:
        raise ScraperProviderError(
            AcquisitionFailureCode.PAYWALL,
            "source is paywalled or legally unavailable",
            retryable=False,
        )
    if status in {408, 504}:
        raise ScraperTimeoutError(
            AcquisitionFailureCode.TIMEOUT, "source timed out", retryable=True
        )
    if status == 429:
        raise ScraperProviderError(
            AcquisitionFailureCode.RATE_LIMIT, "source rate limited the request", retryable=True
        )
    if 500 <= status < 600:
        raise ScraperProviderError(
            AcquisitionFailureCode.TRANSIENT, "source is temporarily unavailable", retryable=True
        )
    raise ScraperProviderError(
        AcquisitionFailureCode.INACCESSIBLE, "source request failed permanently", retryable=False
    )


def _too_large() -> ScraperProviderError:
    return ScraperProviderError(
        AcquisitionFailureCode.TOO_LARGE,
        "source response exceeded the configured byte limit",
        retryable=False,
    )


def _wigolo_failure(status: str) -> ScraperProviderError:
    code = (
        AcquisitionFailureCode.PAYWALL if status == "paywall" else AcquisitionFailureCode.EXTRACTION
    )
    return ScraperProviderError(code, "Wigolo could not extract the source", retryable=False)
