"""Typed non-secret preferences with atomic writes and process exclusion."""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import Field, field_validator

from desktop_paths import application_data_dir
from file_lock import FileLock
from models import StrictModel
from providers.model_choices import (
    CONFIGURABLE_PROFILE_ID,
    DEFAULT_STAGE_MODELS,
    StageModelSelections,
)
from providers.model_profiles import ProfileId


class InterfaceSettings(StrictModel):
    modelProfile: ProfileId = CONFIGURABLE_PROFILE_ID
    stageModels: StageModelSelections = DEFAULT_STAGE_MODELS
    dbPath: str = ""
    maxTokens: int = Field(default=500_000, ge=1, le=500_000)
    maxCost: str = Field(default="0.20", pattern=r"^\d+(?:\.\d+)?$")
    maxCalls: int = Field(default=160, ge=1, le=160)
    supportEnabled: bool = True
    challengeEnabled: bool = False
    sourceTarget: Literal[5, 10, 15, 20] = 10
    useSerpSearch: bool = True
    useExa: bool = True
    useOpenAlex: bool = True
    useArxiv: bool = False
    usePubmed: bool = False
    useCrossref: bool = True

    @field_validator("maxCost")
    @classmethod
    def validate_max_cost(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("maxCost must be a decimal amount") from exc
        if amount <= 0 or amount > Decimal("20.00"):
            raise ValueError("maxCost must be greater than $0 and at most $20.00")
        return value


SETTING_NAMES = frozenset(
    {
        "LUNA_BASE_URL",
        "LUNA_MODEL",
        "MIMO_V25_INPUT_USD_PER_TOKEN",
        "MIMO_V25_OUTPUT_USD_PER_TOKEN",
        "LUNA_INPUT_USD_PER_TOKEN",
        "LUNA_OUTPUT_USD_PER_TOKEN",
    }
)


class Preferences(StrictModel):
    version: Literal[1] = 1
    interface: InterfaceSettings = InterfaceSettings()
    provider_settings: dict[str, str] = Field(default_factory=dict)

    @field_validator("provider_settings")
    @classmethod
    def allow_only_settings(cls, value: dict[str, str]) -> dict[str, str]:
        if value.keys() - SETTING_NAMES:
            raise ValueError("Only non-secret provider settings may be persisted")
        return value


def read_preferences(path: Path | None = None) -> Preferences:
    path = path or application_data_dir() / "preferences.json"
    if not path.exists():
        return Preferences()
    preferences = Preferences.model_validate_json(path.read_text(encoding="utf-8"))
    if preferences.interface.modelProfile == "standard-2026-09":
        migrated_interface = preferences.interface.model_copy(
            update={"modelProfile": CONFIGURABLE_PROFILE_ID}
        )
        return preferences.model_copy(update={"interface": migrated_interface})
    return preferences


def update_preferences(
    *,
    interface: InterfaceSettings | None = None,
    provider_settings: dict[str, str] | None = None,
    path: Path | None = None,
) -> Preferences:
    path = path or application_data_dir() / "preferences.json"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = FileLock(path.with_suffix(".lock"))
    if not lock.acquire(blocking=True):
        raise RuntimeError("Preferences are busy in another process")
    temporary: Path | None = None
    try:
        previous = read_preferences(path)
        result = Preferences(
            interface=interface if interface is not None else previous.interface,
            provider_settings={**previous.provider_settings, **(provider_settings or {})},
        )
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(result.model_dump_json(indent=2))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.release()
