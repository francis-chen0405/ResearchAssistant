"""Supported fresh-v2 model choices and their per-stage defaults."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict

from models import StrictModel
from providers.llm import LLMStage

CONFIGURABLE_PROFILE_ID = "configurable-2026-09"


class ModelChoice(StrEnum):
    GPT_6_LUNA_HIGH = "gpt-6-luna-high"
    GPT_6_LUNA_XHIGH = "gpt-6-luna-xhigh"
    MIMO_V26_PRO = "mimo-v2.6-pro"
    MIMO_V26_FLASH = "mimo-v2.6-flash"
    GPT_6_SOL_HIGH = "gpt-6-sol-high"
    GPT_5_6_TERRA_HIGH = "gpt-5.6-terra-high"


class StageModelSelections(StrictModel):
    """One immutable model choice for every active fresh-v2 model stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planner: ModelChoice = ModelChoice.GPT_6_LUNA_XHIGH
    scout: ModelChoice = ModelChoice.GPT_6_LUNA_HIGH
    gap_analysis: ModelChoice = ModelChoice.GPT_6_LUNA_XHIGH
    search_agent: ModelChoice = ModelChoice.GPT_6_LUNA_XHIGH
    source_selection: ModelChoice = ModelChoice.GPT_6_LUNA_XHIGH
    extractor: ModelChoice = ModelChoice.GPT_6_LUNA_HIGH
    analyst: ModelChoice = ModelChoice.GPT_6_LUNA_XHIGH

    def for_stage(self, stage: LLMStage) -> ModelChoice:
        if stage in (LLMStage.REVIEWER, LLMStage.SYNTHESIZER):
            raise ValueError(f"{stage.value} is not an active fresh-v2 model stage")
        return getattr(self, stage.value)


DEFAULT_STAGE_MODELS = StageModelSelections()
ACTIVE_MODEL_STAGES = (
    LLMStage.PLANNER,
    LLMStage.SCOUT,
    LLMStage.GAP_ANALYSIS,
    LLMStage.SEARCH_AGENT,
    LLMStage.SOURCE_SELECTION,
    LLMStage.EXTRACTOR,
    LLMStage.ANALYST,
)


class ModelOption(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ModelChoice
    label: str
    provider: Literal["openai", "mimo"]
    model: str
    reasoning_effort: Literal["high", "xhigh"] | None = None
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    input_cap_per_million: Decimal
    output_cap_per_million: Decimal


MODEL_OPTIONS = (
    ModelOption(
        id=ModelChoice.GPT_6_LUNA_HIGH,
        label="GPT-6 Luna · High",
        provider="openai",
        model="gpt-6-luna",
        reasoning_effort="high",
        input_per_million=Decimal("0.10"),
        cached_input_per_million=Decimal("0.01"),
        output_per_million=Decimal("0.50"),
        input_cap_per_million=Decimal("0.25"),
        output_cap_per_million=Decimal("0.75"),
    ),
    ModelOption(
        id=ModelChoice.GPT_6_LUNA_XHIGH,
        label="GPT-6 Luna · XHigh",
        provider="openai",
        model="gpt-6-luna",
        reasoning_effort="xhigh",
        input_per_million=Decimal("0.10"),
        cached_input_per_million=Decimal("0.01"),
        output_per_million=Decimal("0.50"),
        input_cap_per_million=Decimal("0.25"),
        output_cap_per_million=Decimal("0.75"),
    ),
    ModelOption(
        id=ModelChoice.MIMO_V26_PRO,
        label="MiMo v2.6 Pro",
        provider="mimo",
        model="mimo-v2.6-pro",
        input_per_million=Decimal("0.435"),
        cached_input_per_million=Decimal("0.0036"),
        output_per_million=Decimal("0.87"),
        input_cap_per_million=Decimal("0.50"),
        output_cap_per_million=Decimal("1.00"),
    ),
    ModelOption(
        id=ModelChoice.MIMO_V26_FLASH,
        label="MiMo v2.6 Flash",
        provider="mimo",
        model="mimo-v2.6-flash",
        input_per_million=Decimal("0.14"),
        cached_input_per_million=Decimal("0.0028"),
        output_per_million=Decimal("0.28"),
        input_cap_per_million=Decimal("0.15"),
        output_cap_per_million=Decimal("0.30"),
    ),
    ModelOption(
        id=ModelChoice.GPT_6_SOL_HIGH,
        label="GPT-6 Sol · High",
        provider="openai",
        model="gpt-6-sol",
        reasoning_effort="high",
        input_per_million=Decimal("2.00"),
        cached_input_per_million=Decimal("0.20"),
        output_per_million=Decimal("10.00"),
        input_cap_per_million=Decimal("5.00"),
        output_cap_per_million=Decimal("15.00"),
    ),
    ModelOption(
        id=ModelChoice.GPT_5_6_TERRA_HIGH,
        label="GPT-5.6 Terra · High",
        provider="openai",
        model="gpt-5.6-terra",
        reasoning_effort="high",
        input_per_million=Decimal("2.00"),
        cached_input_per_million=Decimal("0.20"),
        output_per_million=Decimal("12.00"),
        input_cap_per_million=Decimal("5.00"),
        output_cap_per_million=Decimal("18.00"),
    ),
)


class ModelOptionsPayload(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    choices: tuple[ModelOption, ...]
    defaults: StageModelSelections


def model_options_payload() -> ModelOptionsPayload:
    return ModelOptionsPayload(choices=MODEL_OPTIONS, defaults=DEFAULT_STAGE_MODELS)


def option_for(choice: ModelChoice) -> ModelOption:
    for option in MODEL_OPTIONS:
        if option.id is choice:
            return option
    raise ValueError(f"unsupported model choice: {choice.value}")


def completion_limit_for(stage: LLMStage) -> int:
    if stage is LLMStage.SCOUT:
        return 4096
    if stage in (LLMStage.GAP_ANALYSIS, LLMStage.ANALYST):
        return 16384
    if stage in ACTIVE_MODEL_STAGES:
        return 8192
    raise ValueError(f"{stage.value} is not an active fresh-v2 model stage")
