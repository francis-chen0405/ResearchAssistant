"""Maintained desktop profiles; credentials and legacy routes remain separate."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict

from models import StrictModel
from providers.config import ProviderConfigurationError

ProfileId = Literal["standard-2026-09"]


class SupportedModel(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str
    roles: str
    input_per_million: Decimal
    output_per_million: Decimal
    completion_limit: int = 4096
    output_contract: str = "Strict typed JSON; existing adapter validation"


class ModelProfile(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: ProfileId = "standard-2026-09"
    name: str = "Standard research"
    description: str = "MiMo discovery and extraction · Luna High analysis"
    pricing_reviewed: str = "2026-09-07"
    models: tuple[SupportedModel, ...]


STANDARD_PROFILE = ModelProfile(
    models=(
        SupportedModel(
            model="mimo-v2.5",
            roles="Source scouting",
            input_per_million=Decimal("0.15"),
            output_per_million=Decimal("0.30"),
        ),
        SupportedModel(
            model="mimo-v2.5-pro",
            roles="Planning, search, selection and exact extraction",
            input_per_million=Decimal("0.50"),
            output_per_million=Decimal("1.00"),
        ),
        SupportedModel(
            model="gpt-5.6-luna",
            roles="Gap analysis and evidence analysis · High",
            input_per_million=Decimal("0.50"),
            output_per_million=Decimal("1.80"),
        ),
    )
)


def profile_environment(
    environment: Mapping[str, str], profile: ProfileId | None
) -> dict[str, str]:
    """Resolve a run-local environment; never mutate credentials or saved settings.

    Legacy callers retain their exact route configuration. Desktop profile callers
    fail closed on untested endpoint/model overrides instead of silently rerouting keys.
    Price caps include Luna long-context and cache-write exposure. No cache discount.
    """
    resolved = dict(environment)
    if profile is None:
        return resolved
    if profile != STANDARD_PROFILE.id:
        raise ProviderConfigurationError("Select a supported model profile.")
    expected = {
        "MIMO_BASE_URL": "https://api.xiaomimimo.com/v1",
        "LUNA_BASE_URL": "https://api.openai.com/v1",
        "MIMO_V25_MODEL": "mimo-v2.5",
        "MIMO_V25_PRO_MODEL": "mimo-v2.5-pro",
        "LUNA_MODEL": "gpt-5.6-luna",
    }
    for key, value in expected.items():
        if resolved.get(key, value).rstrip("/") != value:
            raise ProviderConfigurationError(
                "Saved custom model routes are not supported by Standard research. "
                "Restore the standard route in provider settings before starting a "
                "new run."
            )
        resolved[key] = value
    for prefix, model in zip(
        ("MIMO_V25", "MIMO_V25_PRO", "LUNA"), STANDARD_PROFILE.models, strict=True
    ):
        resolved[f"{prefix}_INPUT_USD_PER_TOKEN"] = str(
            model.input_per_million / Decimal(1_000_000)
        )
        resolved[f"{prefix}_OUTPUT_USD_PER_TOKEN"] = str(
            model.output_per_million / Decimal(1_000_000)
        )
    return resolved
