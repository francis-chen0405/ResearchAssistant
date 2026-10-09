"""Exact, canonical decimal handling for authoritative USD accounting."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer


def parse_exact_usd(value: object) -> Decimal:
    """Parse a non-negative finite decimal without using binary-float expansion."""
    if isinstance(value, bool):
        raise ValueError("USD amount must be a decimal value")
    try:
        if isinstance(value, Decimal):
            parsed = value
        elif isinstance(value, float):
            parsed = Decimal(str(value))
        elif isinstance(value, (str, int)):
            parsed = Decimal(value)
        else:
            raise ValueError("USD amount must be a decimal string, integer, or Decimal")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("USD amount must be a valid decimal") from exc
    if not parsed.is_finite() or parsed < 0 or (parsed.is_zero() and parsed.is_signed()):
        raise ValueError("USD amount must be finite and non-negative")
    return parsed


def canonical_usd(value: Decimal) -> str:
    """Serialize a validated USD Decimal as canonical non-exponent text."""
    parsed = parse_exact_usd(value)
    if parsed.is_zero():
        return "0"
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def parse_canonical_usd(value: object) -> Decimal:
    """Parse storage text and reject alternate or ambiguous encodings."""
    if not isinstance(value, str):
        raise ValueError("persisted USD amount must be canonical decimal text")
    parsed = parse_exact_usd(value)
    if value != canonical_usd(parsed):
        raise ValueError("persisted USD amount is not canonical decimal text")
    return parsed


def add_usd(*values: Decimal) -> Decimal:
    """Add USD values without rounding through the process Decimal context."""
    parsed = tuple(parse_exact_usd(value) for value in values)
    precision = max(50, sum(len(value.as_tuple().digits) for value in parsed) + 10)
    with localcontext() as context:
        context.prec = precision
        return sum(parsed, Decimal("0"))


ExactUSD = Annotated[
    Decimal,
    BeforeValidator(parse_exact_usd),
    PlainSerializer(canonical_usd, return_type=str),
]
