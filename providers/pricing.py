"""Conservative OpenRouter price-cap arithmetic for fail-closed reservations."""

from __future__ import annotations

from decimal import ROUND_UP, Decimal

from pydantic import ConfigDict, Field

from models import StrictModel

PRICING_POLICY_VERSION = "openrouter-price-cap-v1"


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


DEFAULT_PRICE_CAPS = {
    "xiaomi/mimo-v2.5-pro": ModelPriceCap(
        model="xiaomi/mimo-v2.5-pro",
        input_usd_per_token=Decimal("0.000005"),
        output_usd_per_token=Decimal("0.000020"),
    ),
    "minimax/minimax-m3": ModelPriceCap(
        model="minimax/minimax-m3",
        input_usd_per_token=Decimal("0.000005"),
        output_usd_per_token=Decimal("0.000020"),
    ),
}


def conservative_token_estimate(text: str) -> int:
    """Return a deliberately conservative UTF-8 input estimate (one token/byte)."""
    return max(1, len(text.encode("utf-8")))
