"""Offline Phase 3 profile, connection and preference compatibility regressions."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from desktop_settings import InterfaceSettings, read_preferences, update_preferences
from frontend.api import ResearchStartInput
from frontend.live_contracts import LiveRunRequest
from frontend.profile_preflight import check_start_reservation
from frontend.provider_connections import check_connection
from models import DiscoveryProvider, ResearchControls
from providers.config import ProviderConfigurationError
from providers.model_profiles import STANDARD_PROFILE, profile_environment
from providers.v2_routing import V2RoutingConfig


def test_profile_preserves_credentials_defaults_and_frozen_run_routes() -> None:
    original = {"MIMO_API_KEY": "test-mimo", "LUNA_API_KEY": "test-luna"}
    resolved = profile_environment(original, STANDARD_PROFILE.id)
    routes = V2RoutingConfig.from_environment(resolved, repository_revision="test")
    assert original == {"MIMO_API_KEY": "test-mimo", "LUNA_API_KEY": "test-luna"}
    assert routes.mimo_v25.model == "mimo-v2.5"
    assert routes.mimo_v25_pro.model == "mimo-v2.5-pro"
    assert routes.luna.model == "gpt-5.6-luna"
    assert routes.luna_price_cap.input_usd_per_token == Decimal("0.0000005")
    assert routes.luna_price_cap.output_usd_per_token == Decimal("0.0000018")
    original["LUNA_MODEL"] = "unknown-later-setting"
    assert routes.luna.model == "gpt-5.6-luna"
    assert "test-luna" not in str(routes.fingerprint_payload())
    with pytest.raises(ValidationError):
        routes.luna.model = "changed"
    assert profile_environment(original, None) == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("LUNA_MODEL", "arbitrary-model"),
        ("LUNA_BASE_URL", "https://example.com/v1"),
        ("MIMO_V25_MODEL", "other-mimo"),
    ],
)
def test_profile_rejects_untested_routes(field: str, value: str) -> None:
    with pytest.raises(ProviderConfigurationError, match="not supported"):
        profile_environment({field: value}, STANDARD_PROFILE.id)


def test_unknown_profile_and_secret_preferences_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ResearchStartInput(
            raw_claim="Public claim", acknowledged_public=True, model_profile="anything"
        )
    with pytest.raises(ValidationError):
        InterfaceSettings(modelProfile="anything")
    with pytest.raises(ValidationError):
        InterfaceSettings(api_key="secret")


def test_old_preferences_upgrade_without_losing_data(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text(
        '{"version":1,"interface":{"dbPath":"old-history.sqlite3","maxCost":"0.50","useArxiv":true},"provider_settings":{"LUNA_MODEL":"gpt-5.6-luna"}}'
    )
    saved = read_preferences(path)
    assert saved.interface.modelProfile == STANDARD_PROFILE.id
    updated = update_preferences(interface=saved.interface, path=path)
    assert updated.interface.dbPath == "old-history.sqlite3"
    assert updated.interface.maxCost == "0.50"
    assert updated.interface.useArxiv
    assert updated.provider_settings == saved.provider_settings


def test_preflight_reserves_real_planner_prompt_offline(tmp_path: Path) -> None:
    environment = {"MIMO_API_KEY": "test-mimo", "LUNA_API_KEY": "test-luna"}
    request = LiveRunRequest(
        raw_claim="A public claim",
        db_path=str(tmp_path / "new.sqlite3"),
        max_tokens=500_000,
        model_profile=STANDARD_PROFILE.id,
        research_controls=ResearchControls(discovery_providers=(DiscoveryProvider.ARXIV,)),
    )
    reservation = check_start_reservation(request, environment)
    assert reservation.input_tokens > 1000
    assert reservation.output_tokens == 4096
    assert reservation.reserved_cost_usd > 0
    assert not (tmp_path / "new.sqlite3").exists()
    with pytest.raises(ValueError, match="token limit"):
        check_start_reservation(request.model_copy(update={"max_tokens": 1}), environment)
    with pytest.raises(ValueError, match="budget"):
        check_start_reservation(
            request.model_copy(update={"max_cost_usd": Decimal("0.000001")}), environment
        )


@pytest.mark.parametrize(
    "provider,secret_name,model",
    [("mimo", "MIMO_API_KEY", "mimo-v2.5"), ("openai", "LUNA_API_KEY", "gpt-5.6-luna")],
)
def test_connection_check_never_generates_or_returns_secrets(
    provider: str, secret_name: str, model: str
) -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": model}, {"id": "mimo-v2.5-pro"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(provider, {secret_name: "not-a-real-secret"}, client=client)
    assert result.state == "connected"
    assert len(seen) == 1 and seen[0].method == "GET"
    assert seen[0].url.path == "/v1/models"
    assert not seen[0].content
    assert "not-a-real-secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "rejected"),
        (403, "rejected"),
        (429, "unavailable"),
        (302, "unavailable"),
        (500, "unavailable"),
    ],
)
def test_connection_failures_are_sanitized(status: int, expected: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="private-secret-and-provider-detail")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection("openai", {"LUNA_API_KEY": "test"}, client=client)
    assert result.state == expected
    assert "private-secret" not in result.model_dump_json()


def test_source_presence_check_is_not_misrepresented_as_authentication() -> None:
    assert check_connection("exa", {}).state == "missing"
    result = check_connection("exa", {"EXA_API_KEY": "test"})
    assert result.state == "saved"
    assert "explicit research run" in result.message
    with pytest.raises(ValueError):
        check_connection("unknown", {})
