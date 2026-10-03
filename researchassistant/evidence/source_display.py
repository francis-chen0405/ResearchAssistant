"""Display-only fallbacks for source titles that contain PDF citation metadata."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_ARTICLE_NUMBER_TITLE = re.compile(r"\s*S?\d{7,}[a-z0-9]*\s+\d+\.\.\d+\s*", re.IGNORECASE)
_REPORTER_CITATION_TITLE = re.compile(
    r"\s*\d+\s+F\.\s*\d+d\s+\d+,\s*\*;\s*\d{4}\s+"
    r"U\.S\.\s+App\.\s+LEXIS\s+\d+,\s*\*\*\s*",
    re.IGNORECASE,
)


def display_source_title(*, title: str | None, source_url: str) -> str:
    """Return a readable card heading without changing the captured source title."""
    parsed = urlsplit(source_url)
    path = unquote(parsed.path)
    filename = path.rsplit("/", 1)[-1]
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return title or source_url
    if not filename.casefold().endswith(".pdf"):
        return title or source_url
    if title and not _is_unhelpful_pdf_title(title):
        return title
    host = parsed.hostname.casefold().removeprefix("www.")
    return f"PDF file: {filename} ({host})"


def _is_unhelpful_pdf_title(title: str) -> bool:
    return bool(_ARTICLE_NUMBER_TITLE.fullmatch(title) or _REPORTER_CITATION_TITLE.fullmatch(title))
