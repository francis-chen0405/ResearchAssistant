"""Exact NBER working-paper metadata from the series' EconPapers record."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpcore
import httpx
from pydantic import ConfigDict

from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.providers.bounded_network import DeadlineHTTPTransport
from researchassistant.providers.config import DeadlineConfig
from researchassistant.providers.discovery_transport import bounded_send
from researchassistant.providers.search import SearchProviderError

_ORIGIN = "https://econpapers.repec.org"
_NBER_PATH = re.compile(r"/papers/w([1-9][0-9]{0,7})(?:\.pdf)?/?")
_NBER_FILES_PATH = re.compile(r"/system/files/working_papers/w([1-9][0-9]{0,7})/w\1\.pdf")
_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)"
)
_DATE = rf"(?:{_MONTH}\s+)?(?:19|20)\d{{2}}(?:-\d{{2}}(?:-\d{{2}})?)?"
_PLACEHOLDER = re.compile(
    rf"(?:{_DATE}(?:\s*[,;]\s*(?:revised|updated)\s+{_DATE})?"
    r"|(?:NBER\s+)?Working\s+Paper\s+(?:No\.?\s*|#\s*)?w?\d+|w\d+|[0-9]{4,8})",
    re.IGNORECASE,
)


class NberPaperMetadata(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    handle: str
    title: str
    abstract: str | None = None


def is_placeholder_title(title: str | None) -> bool:
    normalized = " ".join((title or "").split())
    return not normalized or _PLACEHOLDER.fullmatch(normalized) is not None


def nber_paper_number(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
            "nber.org",
            "www.nber.org",
        }:
            return None
    except ValueError:
        return None
    match = _NBER_PATH.fullmatch(parsed.path) or _NBER_FILES_PATH.fullmatch(parsed.path)
    return match[1] if match else None


def nber_metadata_url(number: str) -> str:
    return f"{_ORIGIN}/paper/nbrnberwo/{number}.htm"


class _CitationMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, set[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        fields = dict(attrs)
        name, content = fields.get("name"), fields.get("content")
        if name and content:
            self.values.setdefault(name.lower(), set()).add(content.strip())

    def value(self, name: str) -> str | None:
        values = self.values.get(name, set())
        return next(iter(values)) if len(values) == 1 else None


def resolve_nber_metadata(
    number: str, *, client: httpx.Client | None = None
) -> NberPaperMetadata | None:
    """Read bibliographic tags from one fixed-origin request, without redirects."""
    if client is None:
        with httpx.Client(
            transport=DeadlineHTTPTransport(ssl_context=httpcore.default_ssl_context()),
            trust_env=False,
            timeout=DeadlineConfig().search_seconds,
        ) as bounded_client:
            return resolve_nber_metadata(number, client=bounded_client)

    try:
        response = bounded_send(
            client,
            "GET",
            nber_metadata_url(number),
            expected_base_url=_ORIGIN,
            max_response_bytes=256 * 1024,
        )
    except (httpx.HTTPError, SearchProviderError):
        return None
    if response.status_code != 200:
        return None
    parser = _CitationMetadata()
    try:
        parser.feed(response.text)
        parser.close()
    except (ValueError, AssertionError):
        return None
    handle, title = parser.value("handle"), parser.value("citation_title")
    if handle != f"RePEc:nbr:nberwo:{number}" or not title or is_placeholder_title(title):
        return None
    abstract = parser.value("citation_abstract")
    return NberPaperMetadata(handle=handle, title=title, abstract=abstract or None)
