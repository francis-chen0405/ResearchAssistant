"""Versioned deterministic normalization for acquired HTML, Markdown, text, and PDF."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
import time
import unicodedata
from html.parser import HTMLParser
from io import BytesIO
from typing import Literal

from markdown_it import MarkdownIt
from pydantic import ConfigDict, Field, field_validator
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from researchassistant.contracts.models import SegmentOffset, StrictModel

NORMALIZATION_VERSION = "ra-normalization-v1"
PDF_POLICY_VERSION = "ra-digital-pdf-v4"
PDF_NORMALIZATION_VERSION = "ra-normalization-pdf-v3"
PDF_CAPTURE_WORD_LIMIT = 12_000
_PDF_PAGE_OPENING_WORDS = 80
_PDF_PAGE_MAX_WORDS = 1_800
_PDF_LATER_WINDOW_CHUNK_WORDS = 32
PDF_OMISSION_MARKER = "[PDF text omitted]"
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n(?:[ \t]*\n)+")
_WORDS = re.compile(r"\S+")
_BOILERPLATE_LINES = frozenset({"skip to content", "skip to main content"})
_PDF_SUBSTANTIVE_HEADING = re.compile(
    r"\b(?:key (?:messages|findings)|main findings|results|findings|conclusions|"
    r"summary for policymakers|evidence|assessment)\b",
    re.IGNORECASE,
)
_PDF_FRONT_MATTER = re.compile(
    r"\b(?:acknowledg(?:e)?ments|copyright|table of contents|contributors|"
    r"publication information)\b",
    re.IGNORECASE,
)


class NormalizationFailureCode(str):
    UNDECODABLE = "undecodable_content"
    BINARY = "binary_content"
    UNSUPPORTED_PDF = "unsupported_pdf"
    PDF_TIMEOUT = "pdf_timeout"
    PDF_PAGE_LIMIT = "pdf_page_limit"


class NormalizationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class NormalizedDocument(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    word_count: int = Field(ge=1, le=PDF_CAPTURE_WORD_LIMIT)
    truncated: bool
    normalization_version: str = NORMALIZATION_VERSION
    media_type: Literal["text/html", "text/plain", "application/pdf"]
    pdf_policy_version: str | None = None

    @field_validator("pdf_policy_version")
    @classmethod
    def validate_pdf_policy(cls, value: str | None, info: object) -> str | None:
        media_type = getattr(info, "data", {}).get("media_type")
        if media_type == "application/pdf" and value != PDF_POLICY_VERSION:
            raise ValueError("PDF documents require the current PDF policy version")
        if media_type != "application/pdf" and value is not None:
            raise ValueError("non-PDF documents cannot carry a PDF policy version")
        return value


def decode_text(payload: bytes, declared_charset: str | None = None) -> str:
    """Decode deterministically without replacement or heuristic charset guessing."""
    if b"\x00" in payload:
        raise NormalizationError(NormalizationFailureCode.BINARY, "content is binary")
    encodings: list[str] = []
    if declared_charset:
        encodings.append(declared_charset.strip().lower())
    encodings.extend(["utf-8-sig", "utf-8", "windows-1252"])
    seen: set[str] = set()
    for encoding in encodings:
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return payload.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
    raise NormalizationError(
        NormalizationFailureCode.UNDECODABLE,
        "content could not be decoded with the deterministic charset policy",
    )


def normalize_markdown(markdown: str, *, max_words: int = 3000) -> NormalizedDocument:
    parser = MarkdownIt("commonmark", {"html": False})
    lines: list[str] = []
    for token in parser.parse(markdown):
        if token.type != "inline" or token.children is None:
            continue
        parts: list[str] = []
        for child in token.children:
            if child.type in {"text", "code_inline"}:
                parts.append(child.content)
            elif child.type in {"softbreak", "hardbreak"}:
                parts.append("\n")
            elif child.type == "image":
                parts.append(child.content)
        value = "".join(parts)
        if value:
            lines.append(value)
    return _document_from_text("\n\n".join(lines), "text/html", max_words=max_words)


def normalize_html(
    payload: bytes, *, declared_charset: str | None = None, max_words: int = 3000
) -> NormalizedDocument:
    parser = _VisibleHTMLParser()
    parser.feed(decode_text(payload, declared_charset))
    parser.close()
    return _document_from_text("\n".join(parser.lines), "text/html", max_words=max_words)


def normalize_plain_text(
    payload: bytes, *, declared_charset: str | None = None, max_words: int = 3000
) -> NormalizedDocument:
    return _document_from_text(
        decode_text(payload, declared_charset), "text/plain", max_words=max_words
    )


def normalize_pdf(
    payload: bytes,
    *,
    max_words: int = PDF_CAPTURE_WORD_LIMIT,
    max_pages: int = 100,
    deadline_seconds: float = 30.0,
) -> NormalizedDocument:
    """Bound the entire untrusted parse in a separately owned process."""
    if not 0 < deadline_seconds <= 120 or not math.isfinite(deadline_seconds):
        raise ValueError("PDF deadline must be finite and within 120 seconds")
    if not 1 <= max_pages <= 100 or not 3 <= max_words <= PDF_CAPTURE_WORD_LIMIT:
        raise ValueError("PDF normalization bounds are invalid")
    if len(payload) > 25 * 1024 * 1024:
        raise NormalizationError(NormalizationFailureCode.UNSUPPORTED_PDF, "PDF exceeds byte limit")
    command = (
        [sys.executable, "--pdf-worker"]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "researchassistant.providers.pdf_worker"]
    )
    header = (
        json.dumps(
            {"max_words": max_words, "max_pages": max_pages, "deadline_seconds": deadline_seconds}
        ).encode()
        + b"\n"
    )
    started = time.monotonic()
    job = None
    process = None
    try:
        if sys.platform == "win32":
            from researchassistant.platform_support.windows_job import WindowsJob

            job = WindowsJob(memory_limit_bytes=1024 * 1024 * 1024)
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        if job is not None:
            job.attach(int(process._handle))
        remaining = deadline_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, deadline_seconds)
        output, _ = process.communicate(header + payload, timeout=remaining)
        if time.monotonic() - started >= deadline_seconds:
            raise subprocess.TimeoutExpired(command, deadline_seconds)
        if process.returncode != 0 or len(output) > 8 * 1024 * 1024:
            raise NormalizationError(
                NormalizationFailureCode.UNSUPPORTED_PDF, "PDF worker failed safely"
            )
        result = json.loads(output)
        if "error" in result:
            raise NormalizationError(
                result["error"], "PDF could not be normalized", retryable=False
            )
        return NormalizedDocument.model_validate(result)
    except subprocess.TimeoutExpired:
        raise NormalizationError(
            NormalizationFailureCode.PDF_TIMEOUT,
            "PDF extraction exceeded its deadline",
            retryable=True,
        ) from None
    except (OSError, ValueError) as exc:
        raise NormalizationError(
            NormalizationFailureCode.UNSUPPORTED_PDF,
            "PDF worker could not complete safely",
        ) from exc
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate()
        if job is not None:
            job.close()


def _normalize_pdf_in_worker(
    payload: bytes, *, max_words: int, max_pages: int, deadline_seconds: float
) -> NormalizedDocument:
    """Internal worker implementation; callers must use the owned process boundary."""
    started = time.monotonic()
    try:
        reader = PdfReader(BytesIO(payload), strict=True)
        if reader.is_encrypted:
            raise NormalizationError(
                NormalizationFailureCode.UNSUPPORTED_PDF,
                "encrypted PDFs are unsupported",
            )
        if len(reader.pages) > max_pages:
            raise NormalizationError(
                NormalizationFailureCode.PDF_PAGE_LIMIT,
                "PDF exceeds the configured page limit",
            )
        pages: list[tuple[int, str]] = []
        missing_text_pages = False
        for index, page in enumerate(reader.pages, start=1):
            if time.monotonic() - started > deadline_seconds:
                raise NormalizationError(
                    NormalizationFailureCode.PDF_TIMEOUT,
                    "PDF extraction exceeded its deadline",
                    retryable=True,
                )
            extracted = page.extract_text()
            if extracted and extracted.strip():
                pages.append((index, extracted))
            else:
                missing_text_pages = True
    except NormalizationError:
        raise
    except (PdfReadError, ValueError, TypeError, KeyError) as exc:
        raise NormalizationError(
            NormalizationFailureCode.UNSUPPORTED_PDF,
            "PDF is malformed or cannot be deterministically parsed",
        ) from exc
    if not pages:
        raise NormalizationError(
            NormalizationFailureCode.UNSUPPORTED_PDF,
            "PDF contains no usable embedded text",
        )
    return _document_from_pdf_pages(pages, max_words=max_words, omitted=missing_text_pages)


def _document_from_pdf_pages(
    pages: list[tuple[int, str]], *, max_words: int, omitted: bool
) -> NormalizedDocument:
    """Keep page openings throughout a PDF, then expand substantive pages within one cap."""
    normalized_pages = [(number, _normalize_visible_text(text)) for number, text in pages]
    nonempty_pages = [(number, text) for number, text in normalized_pages if _WORDS.search(text)]
    omitted = omitted or len(nonempty_pages) != len(normalized_pages)
    normalized_pages = nonempty_pages
    if not normalized_pages:
        raise NormalizationError(
            NormalizationFailureCode.UNSUPPORTED_PDF,
            "PDF contains no usable embedded text",
        )
    page_words = [list(_WORDS.finditer(text)) for _number, text in normalized_pages]
    # Every retained page needs its two-word provenance marker and at least one
    # source word. Very small caller caps still sample the document's full span.
    if len(normalized_pages) * 3 > max_words:
        slots = max(1, max_words // 3)
        positions = (
            [0]
            if slots == 1
            else [index * (len(normalized_pages) - 1) // (slots - 1) for index in range(slots)]
        )
        normalized_pages = [normalized_pages[index] for index in positions]
        page_words = [page_words[index] for index in positions]
        omitted = True
    available = max_words - 2 * len(normalized_pages)
    opening = min(_PDF_PAGE_OPENING_WORDS, max(1, available // len(normalized_pages)))
    allocations = [min(opening, len(words)) for words in page_words]
    opening_allocations = allocations.copy()
    later_allocations = [0] * len(page_words)
    remaining = available - sum(allocations)
    ranked = sorted(
        range(len(normalized_pages)),
        key=lambda index: (
            -_pdf_page_score(normalized_pages[index][1], normalized_pages[index][0]),
            normalized_pages[index][0],
        ),
    )
    while remaining:
        advanced = False
        for index in ranked:
            # Spend one omission marker when opening a later window. Small
            # increments reach more pages before any one page takes the cap.
            marker_words = 3 if later_allocations[index] == 0 else 0
            additional = min(
                _PDF_LATER_WINDOW_CHUNK_WORDS,
                max(0, remaining - marker_words),
                _PDF_PAGE_MAX_WORDS - allocations[index],
                len(page_words[index]) - allocations[index],
            )
            if additional > 0:
                allocations[index] += additional
                later_allocations[index] += additional
                remaining -= additional + marker_words
                advanced = True
        if not advanced:
            break
    captured: list[str] = []
    for (number, text), words, count, first_count, later_count in zip(
        normalized_pages,
        page_words,
        allocations,
        opening_allocations,
        later_allocations,
        strict=True,
    ):
        if count < len(words):
            omitted = True
        if count == len(words) or not later_count:
            page_text = text[: words[count - 1].end()]
        else:
            # Center the second window late in the page rather than merely
            # extending its opening. It remains a literal contiguous slice.
            later_start = min(
                4 * len(words) // 5 - later_count // 2,
                len(words) - later_count,
            )
            later_start = max(first_count, later_start)
            if later_start == first_count:
                page_text = text[: words[count - 1].end()]
            else:
                later_end = words[later_start + later_count - 1].end()
                page_text = (
                    f"{text[: words[first_count - 1].end()]}\n"
                    f"{PDF_OMISSION_MARKER}\n"
                    f"{text[words[later_start].start() : later_end]}"
                )
        captured.append(f"Page {number}\n{page_text}")
    return _document_from_text(
        "\n\n".join(captured),
        "application/pdf",
        max_words=max_words,
        pdf_policy_version=PDF_POLICY_VERSION,
        normalization_version=PDF_NORMALIZATION_VERSION,
        omitted=omitted,
    )


def _pdf_page_score(text: str, page_number: int) -> int:
    score = 4 * len(_PDF_SUBSTANTIVE_HEADING.findall(text[:1500]))
    score += 1 if page_number > 3 else 0
    score -= 5 * len(_PDF_FRONT_MATTER.findall(text[:1500]))
    return score


def locate_exact_quotes(text: str, exact_quotes: tuple[str, ...]) -> tuple[SegmentOffset, ...]:
    """Locate exact quotes sequentially and prove every returned slice is identical."""
    cursor = 0
    offsets: list[SegmentOffset] = []
    for quote in exact_quotes:
        if not quote:
            raise ValueError("exact quotes cannot be empty")
        start = text.find(quote, cursor)
        if start < 0:
            raise ValueError("exact quote is absent or out of sequence")
        end = start + len(quote)
        if text[start:end] != quote:
            raise AssertionError("quote offset invariant failed")
        offsets.append(SegmentOffset(start_char=start, end_char=end))
        cursor = end
    return tuple(offsets)


def _document_from_text(
    text: str,
    media_type: Literal["text/html", "text/plain", "application/pdf"],
    *,
    max_words: int,
    pdf_policy_version: str | None = None,
    normalization_version: str = NORMALIZATION_VERSION,
    omitted: bool = False,
) -> NormalizedDocument:
    normalized = _normalize_visible_text(text)
    matches = list(_WORDS.finditer(normalized))
    if not matches:
        raise NormalizationError("empty_content", "normalization produced no visible text")
    truncated = omitted or len(matches) > max_words
    if len(matches) > max_words:
        normalized = normalized[: matches[max_words - 1].end()].rstrip()
        matches = matches[:max_words]
    return NormalizedDocument(
        text=normalized,
        sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        word_count=len(matches),
        truncated=truncated,
        normalization_version=normalization_version,
        media_type=media_type,
        pdf_policy_version=pdf_policy_version,
    )


def _normalize_visible_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    normalized = "\n".join(
        _HORIZONTAL_SPACE.sub(" ", line).strip() for line in normalized.split("\n")
    )
    normalized = "\n".join(
        line for line in normalized.split("\n") if line.casefold() not in _BOILERPLATE_LINES
    )
    normalized = _BLANK_LINES.sub("\n\n", normalized).strip()
    return normalized


class _VisibleHTMLParser(HTMLParser):
    _SKIPPED = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form"}
    _BLOCKS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._current: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIPPED:
            self._skip_depth += 1
        elif not self._skip_depth and tag in self._BLOCKS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED and self._skip_depth:
            self._skip_depth -= 1
        elif not self._skip_depth and tag in self._BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._current.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        value = "".join(self._current).strip()
        if value:
            self.lines.append(value)
        self._current.clear()
