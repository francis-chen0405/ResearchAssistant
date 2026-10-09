"""Compatibility checks for the source discovery controls exposed in the UI."""

import pytest
from pydantic import ValidationError

from researchassistant.platform_support.desktop_settings import InterfaceSettings


def test_legacy_interface_preferences_receive_documented_discovery_defaults() -> None:
    settings = InterfaceSettings.model_validate({"sourceTarget": 10, "useOpenAlex": True})

    assert settings.metadataDepth == 20
    assert settings.seedExpansionEnabled is True
    assert settings.scholarlySearchMode == "lexical"


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
