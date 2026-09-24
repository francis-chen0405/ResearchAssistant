"""Conservative provider price-cap arithmetic for fail-closed reservations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_UP, Decimal

from pydantic import ConfigDict, Field

from models import StrictModel
from providers.model_choices import MODEL_OPTIONS

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


class CacheTokenPrices(StrictModel):
    """Published standard text-token rates; immutable and separate from reservations."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    input_per_million: Decimal = Field(gt=0)
    cached_per_million: Decimal = Field(gt=0)
    output_per_million: Decimal = Field(gt=0)
    cache_write_multiplier: Decimal = Field(default=Decimal("1"), ge=1)
    long_context_threshold: int | None = Field(default=None, gt=0)

    def estimate(
        self, *, prompt: int, cached: int, output: int, cache_writes: int | None
    ) -> Decimal:
        # Missing write counts are not evidence of free writes. MiMo's multiplier
        # is 1 because its published cache-miss tariff has no additional write fee.
        uncached = prompt - cached
        writes = uncached if cache_writes is None else cache_writes
        if min(prompt, cached, output, writes) < 0 or cached + writes > prompt:
            raise ValueError("cache token counts must partition input tokens")
        input_cost = (
            Decimal(cached) * self.cached_per_million
            + Decimal(uncached - writes) * self.input_per_million
            + Decimal(writes) * self.input_per_million * self.cache_write_multiplier
        )
        output_cost = Decimal(output) * self.output_per_million
        if self.long_context_threshold is not None and prompt > self.long_context_threshold:
            input_cost *= 2
            output_cost *= Decimal("1.5")
        return ((input_cost + output_cost) / Decimal(1_000_000)).quantize(
            Decimal("0.000000001"), rounding=ROUND_UP
        )


def cache_prices_for_route(base_url: str, model: str) -> CacheTokenPrices | None:
    """No published discount is inferred for custom endpoints or unknown models.

    Reviewed 2026-09-23 for the selected OpenAI and MiMo models. Source URLs and
    fallback rules are in docs/model-settings.md.
    """
    for option in MODEL_OPTIONS:
        official_url = (
            "https://api.openai.com/v1"
            if option.provider == "openai"
            else "https://api.xiaomimimo.com/v1"
        )
        if base_url == official_url and model == option.model:
            return CacheTokenPrices(
                input_per_million=option.input_per_million,
                cached_per_million=option.cached_input_per_million,
                output_per_million=option.output_per_million,
                cache_write_multiplier=(
                    Decimal("1.25") if option.provider == "openai" else Decimal("1")
                ),
                long_context_threshold=(272_000 if option.provider == "openai" else None),
            )
    if base_url == "https://api.xiaomimimo.com/v1":
        if model == "mimo-v2.5-pro":
            return CacheTokenPrices(
                input_per_million=Decimal("0.435"),
                cached_per_million=Decimal("0.0036"),
                output_per_million=Decimal("0.87"),
            )
        if model == "mimo-v2.5":
            return CacheTokenPrices(
                input_per_million=Decimal("0.14"),
                cached_per_million=Decimal("0.0028"),
                output_per_million=Decimal("0.28"),
            )
    if base_url == "https://api.openai.com/v1" and model == "gpt-5.6-luna":
        return CacheTokenPrices(
            input_per_million=Decimal("0.20"),
            cached_per_million=Decimal("0.02"),
            output_per_million=Decimal("1.20"),
            cache_write_multiplier=Decimal("1.25"),
            long_context_threshold=272_000,
        )
    return None


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


def price_cap_from_environment(
    environment: Mapping[str, str],
    *,
    model: str,
    environment_prefix: str,
) -> ModelPriceCap:
    """Load explicit v2 pricing; unknown routes never receive a zero-cost fallback."""
    input_name = f"{environment_prefix}_INPUT_USD_PER_TOKEN"
    output_name = f"{environment_prefix}_OUTPUT_USD_PER_TOKEN"
    input_value = environment.get(input_name, "").strip()
    output_value = environment.get(output_name, "").strip()
    if not input_value or not output_value:
        raise ValueError(
            f"{input_name} and {output_name} are required for deterministic route pricing"
        )
    try:
        return ModelPriceCap(
            model=model,
            input_usd_per_token=Decimal(input_value),
            output_usd_per_token=Decimal(output_value),
        )
    except Exception as exc:
        raise ValueError(
            f"{environment_prefix} route pricing must be positive decimal USD-per-token values"
        ) from exc


def conservative_token_estimate(text: str) -> int:
    """Return a deliberately conservative UTF-8 input estimate (one token/byte)."""
    return max(1, len(text.encode("utf-8")))
