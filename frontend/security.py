"""Secret-safe text handling for the local live web surface."""

from __future__ import annotations

import re
from collections.abc import Iterable

_AUTHORIZATION_PATTERN = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+")
_KEY_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)((?:MIMO_API_KEY|api[_-]?key|token|secret)\s*[:=]\s*)[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def redact_text(value: object, *, secrets: Iterable[str] = ()) -> str:
    """Return bounded display text with explicit and recognizable secrets removed."""
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", text)
    text = _KEY_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", text)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    return text[:4000]
