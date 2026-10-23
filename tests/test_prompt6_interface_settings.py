"""Compatibility checks for the source discovery controls exposed in the UI."""

import pytest
from pydantic import ValidationError

from researchassistant.platform_support.desktop_settings import InterfaceSettings


def test_legacy_interface_preferences_receive_documented_discovery_defaults() -> None:
    settings = InterfaceSettings.model_validate({"sourceTarget": 10, "useOpenAlex": True})

    assert settings.metadataDepth == 50
    assert settings.seedExpansionEnabled is True
    assert settings.scholarlySearchMode == "lexical"


def test_new_interface_preferences_default_to_twenty_sources() -> None:
    settings = InterfaceSettings()

    assert settings.sourceTarget == 20
    assert settings.metadataDepth == 50
    assert InterfaceSettings(sourceTarget=30).sourceTarget == 30
    # Existing preferences saved with 15 remain readable after the choice is hidden.
    assert InterfaceSettings(sourceTarget=15).sourceTarget == 15


@pytest.mark.parametrize(
    "values",
    [
        {"metadataDepth": 5},
        {"seedExpansionEnabled": "yes"},
        {"scholarlySearchMode": "automatic"},
    ],
)
def test_discovery_preferences_reject_unsupported_values(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InterfaceSettings.model_validate(values)
