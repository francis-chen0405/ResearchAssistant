"""Optional Crossref source-identity enrichment for fresh-v2 discovery metadata."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from models import CrossrefIdentityMetadata


class CrossrefEnrichmentError(RuntimeError):
    """An optional identity lookup failed; discovery callers must continue without it."""


class CrossrefEnricher:
    """Resolve one DOI to canonical bibliographic identity without supplying evidence."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.crossref.org",
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self._base_url, follow_redirects=False)

    def resolve(self, doi: str) -> CrossrefIdentityMetadata:
        """Return verified title/author/date metadata or raise an optional-lookup failure."""
        try:
            response = self._client.get(f"/works/{quote(doi, safe='')}")
        except httpx.HTTPError as exc:
            raise CrossrefEnrichmentError("Crossref request failed") from exc
        if response.status_code != 200:
            raise CrossrefEnrichmentError(f"Crossref returned HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise CrossrefEnrichmentError("Crossref returned invalid JSON") from exc
        message = body.get("message") if isinstance(body, dict) else None
        if not isinstance(message, dict):
            raise CrossrefEnrichmentError("Crossref response omitted work metadata")
        canonical_doi = _string(message.get("DOI")) or doi
        title = _first_string(message.get("title"))
        return CrossrefIdentityMetadata(
            doi=canonical_doi.casefold(),
            canonical_title=title,
            canonical_authors=_authors(message.get("author")),
            publication_date=_publication_date(message),
            verified=True,
        )


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _first_string(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    return next((_string(item) for item in value if _string(item)), None)


def _authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        given, family = _string(item.get("given")), _string(item.get("family"))
        name = " ".join(part for part in (given, family) if part)
        if name:
            names.append(name)
    return tuple(names)


def _publication_date(message: dict[str, Any]) -> str | None:
    for key in ("published-print", "published-online", "issued"):
        value = message.get(key)
        if not isinstance(value, dict) or not isinstance(value.get("date-parts"), list):
            continue
        parts = value["date-parts"]
        if not parts or not isinstance(parts[0], list) or not parts[0]:
            continue
        numeric = parts[0]
        if all(isinstance(part, int) for part in numeric[:3]):
            return "-".join(
                str(part).zfill(2) if index else str(part) for index, part in enumerate(numeric[:3])
            )
    return None
