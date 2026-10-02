"""Regressions for exact decimal USD addition across exponent ranges."""

from __future__ import annotations

from decimal import Decimal, localcontext

import pytest

from money import add_usd, canonical_usd, parse_exact_usd


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        (
            (Decimal("1"), Decimal("1e-60")),
            "1.000000000000000000000000000000000000000000000000000000000001",
        ),
        ((Decimal("1e50"), Decimal("1")), "100000000000000000000000000000000000000000000000001"),
        ((Decimal("0.1"), Decimal("0.02"), Decimal("0.003")), "0.123"),
        ((Decimal("0E-1000"), Decimal("1.2300")), "1.23"),
    ),
)
def test_add_usd_preserves_widely_separated_decimal_places(
    values: tuple[Decimal, ...], expected: str
) -> None:
    with localcontext() as context:
        context.prec = 2
        result = add_usd(*values)

    assert canonical_usd(result) == expected


@pytest.mark.parametrize("value", (Decimal("-1"), Decimal("-0")))
def test_usd_rejects_negative_values_and_signed_zero(value: Decimal) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        parse_exact_usd(value)


def test_add_usd_keeps_subunit_amount_after_large_amount() -> None:
    with localcontext() as context:
        context.prec = 100
        expected = Decimal("100000000000000000000000000000000000000000000000000") + Decimal("0.01")

    result = add_usd(
        Decimal("100000000000000000000000000000000000000000000000000"),
        Decimal("0.01"),
    )

    assert result == expected
