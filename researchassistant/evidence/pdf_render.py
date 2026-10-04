"""Paginated Unicode plain-text rendering with an embedded, licensed font."""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

FONT_NAME = "ResearchAssistantUnifont15001"
FONT_SIZE = 10
LEADING = 14
PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN = 50


class PDFTextCompatibilityError(ValueError):
    """The bundled renderer cannot faithfully display a supplied code point."""


@lru_cache(maxsize=1)
def _font() -> TTFont:
    font = TTFont(FONT_NAME, str(Path(__file__).with_name("fonts") / "unifont-15.0.01.ttf"))
    pdfmetrics.registerFont(font)
    return font


def _check_text(text: str, font: TTFont) -> None:
    unsupported = sorted(
        {
            ord(char)
            for char in text
            if char not in "\n\r\t"
            and (
                not font.face.charToGlyph.get(ord(char), 0)
                or unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn"}
                # This plain-text renderer does not perform complex-script shaping.
                or unicodedata.bidirectional(char) in {"R", "AL", "AN"}
                or 0x0900 <= ord(char) <= 0x109F
                or 0x1780 <= ord(char) <= 0x17FF
            )
        }
    )
    if unsupported:
        codes = ", ".join(f"U+{value:04X}" for value in unsupported[:12])
        raise PDFTextCompatibilityError(
            f"PDF font/shaping coverage does not support {codes}; use Markdown or DOCX "
            "to preserve the original text"
        )


def _wrapped_lines(text: str) -> tuple[str, ...]:
    width = PAGE_WIDTH - 2 * MARGIN
    lines: list[str] = []
    for original in text.expandtabs(4).splitlines() or [""]:
        remaining = original
        while pdfmetrics.stringWidth(remaining, FONT_NAME, FONT_SIZE) > width:
            # Binary search also breaks arbitrarily long URLs/words by glyph width.
            low, high = 1, len(remaining)
            while low < high:
                middle = (low + high + 1) // 2
                if pdfmetrics.stringWidth(remaining[:middle], FONT_NAME, FONT_SIZE) <= width:
                    low = middle
                else:
                    high = middle - 1
            boundary = remaining.rfind(" ", 0, low + 1)
            split = boundary + 1 if boundary > 0 else low
            lines.append(remaining[:split])
            remaining = remaining[split:]
        lines.append(remaining)
    return tuple(lines)


def render_pdf_text(text: str) -> bytes:
    """Render already materialized trusted text; no database or provider work."""
    font = _font()
    _check_text(text, font)
    payload = BytesIO()
    canvas = Canvas(
        payload, pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1, pdfVersion=(1, 4)
    )
    canvas.setTitle("ResearchAssistant released brief")
    canvas.setFont(FONT_NAME, FONT_SIZE)
    baseline = PAGE_HEIGHT - MARGIN - FONT_SIZE
    for line in _wrapped_lines(text):
        if baseline < MARGIN:
            canvas.showPage()
            canvas.setFont(FONT_NAME, FONT_SIZE)
            baseline = PAGE_HEIGHT - MARGIN - FONT_SIZE
        canvas.drawString(MARGIN, baseline, line)
        baseline -= LEADING
    canvas.save()
    return payload.getvalue()
