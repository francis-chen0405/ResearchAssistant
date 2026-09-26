"""Maintained desktop profiles; credentials and legacy routes remain separate."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict

from models import StrictModel
from providers.config import ProviderConfigurationError
from providers.model_choices import (
    CONFIGURABLE_PROFILE_ID,
    DEFAULT_STAGE_MODELS,
    MODEL_OPTIONS,
    StageModelSelections,
)

ProfileId = Literal["standard-2026-09", "configurable-2026-09"]


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
    pricing_reviewed: str = "2026-09-17"
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
            completion_limit=8192,
            input_per_million=Decimal("0.50"),
            output_per_million=Decimal("1.00"),
        ),
        SupportedModel(
            model="gpt-5.6-luna",
            roles="Gap analysis and evidence analysis · High",
            completion_limit=16384,
            input_per_million=Decimal("0.50"),
            output_per_million=Decimal("1.80"),
        ),
    )
)

CONFIGURABLE_PROFILE = ModelProfile(
    id=CONFIGURABLE_PROFILE_ID,
    name="Choose each research model",
    description="Six supported choices for each active model step",
    pricing_reviewed="2026-09-25",
    models=tuple(
        SupportedModel(
            model=option.id.value,
            roles="Any active model step",
            input_per_million=option.input_cap_per_million,
            output_per_million=option.output_cap_per_million,
            completion_limit=16384,
        )
        for option in MODEL_OPTIONS
    ),
)


def profile_environment(
    environment: Mapping[str, str],
    profile: ProfileId | None,
    stage_models: StageModelSelections | None = None,
) -> dict[str, str]:
    """Resolve a run-local environment; never mutate credentials or saved settings.

    Legacy callers retain their exact route configuration. Desktop profile callers
    fail closed on untested endpoint/model overrides instead of silently rerouting keys.
    Reservations include Luna long-context/cache-write exposure without a cache discount.
    Completed usage uses verified route-specific cache rates where metadata permits.
    """
    resolved = dict(environment)
    if profile is None:
        return resolved
    if profile == CONFIGURABLE_PROFILE_ID:
        selections = stage_models or DEFAULT_STAGE_MODELS
        required_providers = {
            option.provider
            for option in MODEL_OPTIONS
            if option.id in set(selections.model_dump().values())
        }
        if (
            "openai" in required_providers
            and resolved.get("LUNA_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            != "https://api.openai.com/v1"
        ):
            raise ProviderConfigurationError("Selected OpenAI models require the official endpoint")
        if (
            "mimo" in required_providers
            and resolved.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
            != "https://api.xiaomimimo.com/v1"
        ):
            raise ProviderConfigurationError("Selected MiMo models require the official endpoint")
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
        resolved[f"{prefix}_MAX_COMPLETION_TOKENS"] = str(model.completion_limit)
        resolved[f"{prefix}_INPUT_USD_PER_TOKEN"] = str(
            model.input_per_million / Decimal(1_000_000)
        )
        resolved[f"{prefix}_OUTPUT_USD_PER_TOKEN"] = str(
            model.output_per_million / Decimal(1_000_000)
        )
    return resolved
