"""Complete content and page geometry checks for the embedded-font PDF exporter."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from researchassistant.evidence.brief_export import _pdf
from researchassistant.evidence.pdf_render import PDFTextCompatibilityError


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)


def test_seventy_lines_paginate_with_all_content() -> None:
    lines = [f"Research line {number:02d}" for number in range(70)]
    reader = PdfReader(BytesIO(_pdf("\n".join(lines))))
    assert len(reader.pages) == 2
    for line in lines:
        assert line in "\n".join(page.extract_text() for page in reader.pages)
    for page in reader.pages:
        positions: list[tuple[float, float]] = []

        def visit(
            text: str,
            cm: list[float],
            tm: list[float],
            font: object,
            size: float,
            positions: list[tuple[float, float]] = positions,
        ) -> None:
            if text.strip():
                positions.append((tm[4], tm[5]))

        page.extract_text(visitor_text=visit)
        assert positions
        assert all(50 <= x <= 562 and 50 <= y <= 742 for x, y in positions)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Short report",
        "(escaped) \\ symbols < > &",
        "Résumé — “quotes” α β ∑ ≤ √ ∞",
        "研究证据 日本語 한국어 Кириллица",
    ],
)
def test_unicode_short_and_pdf_metacharacters_round_trip(text: str) -> None:
    pdf = _pdf(text)
    assert len(PdfReader(BytesIO(pdf)).pages) == 1
    assert _text(pdf).strip() == text


def test_unbroken_urls_and_words_are_wrapped_without_lost_characters() -> None:
    text = "https://example.test/" + "verylongpath" * 200
    pdf = _pdf(text)
    extracted = _text(pdf)
    assert extracted.replace("\n", "") == text
    assert len(extracted.splitlines()) > 10


@pytest.mark.parametrize("count,pages", [(49, 1), (50, 2), (98, 2), (99, 3)])
def test_exact_page_boundary(count: int, pages: int) -> None:
    reader = PdfReader(BytesIO(_pdf("\n".join("boundary" for _ in range(count)))))
    assert len(reader.pages) == pages


def test_unsupported_glyph_or_shaping_is_explicit() -> None:
    for text in ("unsupported 😀", "العربية", "\x00"):
        with pytest.raises(PDFTextCompatibilityError, match="coverage"):
            _pdf(text)
