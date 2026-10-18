"""Pure format representability checks, without modifying released text."""

from __future__ import annotations


def xml_invalid_codepoints(text: str) -> tuple[int, ...]:
    """Return code points outside the XML 1.0 Char production used by DOCX."""
    return tuple(
        sorted(
            {
                ord(char)
                for char in text
                if not (
                    char in "\t\n\r"
                    or 0x20 <= ord(char) <= 0xD7FF
                    or 0xE000 <= ord(char) <= 0xFFFD
                    or 0x10000 <= ord(char) <= 0x10FFFF
                )
            }
        )
    )
