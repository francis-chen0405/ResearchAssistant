"""Conservative provider price-cap arithmetic for fail-closed reservations."""

from __future__ import annotations

from decimal import ROUND_UP, Decimal

from pydantic import ConfigDict, Field

from models import StrictModel

DIRECT_MIMO_PRICING_POLICY_VERSION = "xiaomi-mimo-price-cap-2026-08-10-v2"


class ModelPriceCap(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    input_usd_per_token: Decimal = Field(gt=0)
    output_usd_per_token: Decimal = Field(gt=0)

    def upper_bound(self, input_tokens: int, output_tokens: int) -> Decimal:
        value = (
            Decimal(input_tokens) * self.input_usd_per_token
            + Decimal(output_tokens) * self.output_usd_per_token
        )
        return value.quantize(Decimal("0.000000001"), rounding=ROUND_UP)


COMPATIBILITY_PRICE_CAPS = {
    "mimo-v2.5-pro": ModelPriceCap(
        model="mimo-v2.5-pro",
        input_usd_per_token=Decimal("0.000005"),
        output_usd_per_token=Decimal("0.000020"),
    ),
    "minimax-m3": ModelPriceCap(
        model="minimax-m3",
        input_usd_per_token=Decimal("0.000005"),
        output_usd_per_token=Decimal("0.000020"),
    ),
}


# Official overseas pay-as-you-go prices on 2026-07-15 were USD 0.435/M
# cache-miss input tokens and USD 0.87/M output tokens. These deliberately rounded-up
# caps fail closed and do not rely on cache-hit discounts.
DIRECT_MIMO_PRICE_CAP = ModelPriceCap(
    model="mimo-v2.5-pro",
    input_usd_per_token=Decimal("0.0000005"),
    output_usd_per_token=Decimal("0.000001"),
)


def conservative_token_estimate(text: str) -> int:
    """Return a deliberately conservative UTF-8 input estimate (one token/byte)."""
    return max(1, len(text.encode("utf-8")))
