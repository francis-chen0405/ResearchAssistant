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
from providers.llm import LLMStage
from providers.model_choices import (
    CONFIGURABLE_PROFILE_ID,
    DEFAULT_STAGE_MODELS,
    ModelChoice,
    StageModelSelections,
)
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
    assert saved.interface.modelProfile == CONFIGURABLE_PROFILE_ID
    assert saved.interface.stageModels == DEFAULT_STAGE_MODELS
    updated = update_preferences(interface=saved.interface, path=path)
    assert updated.interface.dbPath == "old-history.sqlite3"
    assert updated.interface.maxCost == "0.50"
    assert updated.interface.useArxiv
    assert updated.provider_settings == saved.provider_settings


def test_saved_luna_56_stage_choices_migrate_to_luna_6(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text(
        '{"version":1,"interface":{"stageModels":{'
        '"planner":"gpt-5.6-luna-xhigh",'
        '"scout":"gpt-5.6-luna-high",'
        '"gap_analysis":"gpt-5.6-luna-xhigh",'
        '"search_agent":"mimo-v2.6-pro",'
        '"source_selection":"gpt-6-sol-high",'
        '"extractor":"gpt-5.6-luna-high",'
        '"analyst":"gpt-5.6-terra-high"}}}'
    )

    saved = read_preferences(path)

    assert saved.interface.stageModels.model_dump(mode="json") == {
        "planner": "gpt-6-luna-xhigh",
        "scout": "gpt-6-luna-high",
        "gap_analysis": "gpt-6-luna-xhigh",
        "search_agent": "mimo-v2.6-pro",
        "source_selection": "gpt-6-sol-high",
        "extractor": "gpt-6-luna-high",
        "analyst": "gpt-5.6-terra-high",
    }
    assert path.read_text().find("gpt-5.6-luna") >= 0


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
    assert reservation.output_tokens == 8192
    assert reservation.reserved_cost_usd > 0
    assert not (tmp_path / "new.sqlite3").exists()
    with pytest.raises(ValueError, match="token limit"):
        check_start_reservation(request.model_copy(update={"max_tokens": 1}), environment)
    with pytest.raises(ValueError, match="budget"):
        check_start_reservation(
            request.model_copy(update={"max_cost_usd": Decimal("0.000001")}), environment
        )


def test_profile_response_allowances_are_reserved_and_fingerprinted() -> None:
    environment = {"MIMO_API_KEY": "test-mimo", "LUNA_API_KEY": "test-luna"}
    resolved = profile_environment(environment, STANDARD_PROFILE.id)
    routes = V2RoutingConfig.from_environment(resolved, repository_revision="test")
    for stage, allowance in (
        (LLMStage.SCOUT, 4096),
        (LLMStage.SOURCE_SELECTION, 8192),
        (LLMStage.GAP_ANALYSIS, 16384),
    ):
        reservation = routes.preflight().reserve(stage, 1000)
        assert reservation.output_tokens == allowance
        assert reservation.reserved_tokens == 1000 + allowance
        assert reservation.reserved_cost_usd == routes.preflight().for_stage(
            stage
        ).price_cap.upper_bound(1000, allowance)
    old = V2RoutingConfig.from_environment(
        {**resolved, "LUNA_MAX_COMPLETION_TOKENS": "4096"}, repository_revision="test"
    )
    assert old.fingerprint_payload() != routes.fingerprint_payload()
    assert [model.completion_limit for model in STANDARD_PROFILE.models] == [4096, 8192, 16384]


@pytest.mark.parametrize(
    "provider,secret_name,model",
    [
        ("mimo", "MIMO_API_KEY", "mimo-v2.6-flash"),
        ("openai", "LUNA_API_KEY", "gpt-6-luna"),
    ],
)
def test_connection_check_never_generates_or_returns_secrets(
    provider: str, secret_name: str, model: str
) -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": model}, {"id": "mimo-v2.5-pro"}]})

    stage_models = DEFAULT_STAGE_MODELS
    if provider == "mimo":
        stage_models = StageModelSelections(
            planner=ModelChoice.MIMO_V26_FLASH,
            scout=ModelChoice.MIMO_V26_FLASH,
            gap_analysis=ModelChoice.MIMO_V26_FLASH,
            search_agent=ModelChoice.MIMO_V26_FLASH,
            source_selection=ModelChoice.MIMO_V26_FLASH,
            extractor=ModelChoice.MIMO_V26_FLASH,
            analyst=ModelChoice.MIMO_V26_FLASH,
        )
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            provider,
            {secret_name: "not-a-real-secret"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=stage_models,
            client=client,
        )
    assert result.state == "connected"
    assert len(seen) == 1 and seen[0].method == "GET"
    assert seen[0].url.path == "/v1/models"
    assert not seen[0].content
    assert "not-a-real-secret" not in result.model_dump_json()


def test_connection_check_rejects_accounts_without_selectable_models() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"data": [{"id": "mimo-v2.5-pro"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            "mimo",
            {"MIMO_API_KEY": "test"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert result.state == "unavailable"
    assert "selected" in result.message.lower()


def test_connection_check_requires_every_distinct_selected_model() -> None:
    selections = StageModelSelections(
        planner=ModelChoice.GPT_6_LUNA_HIGH,
        scout=ModelChoice.GPT_6_LUNA_XHIGH,
        gap_analysis=ModelChoice.GPT_6_SOL_HIGH,
        search_agent=ModelChoice.GPT_6_SOL_HIGH,
        source_selection=ModelChoice.GPT_6_LUNA_HIGH,
        extractor=ModelChoice.GPT_6_LUNA_XHIGH,
        analyst=ModelChoice.GPT_6_SOL_HIGH,
    )

    def luna_only(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]})

    with httpx.Client(transport=httpx.MockTransport(luna_only)) as client:
        missing_sol = check_connection(
            "openai",
            {"LUNA_API_KEY": "test"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=selections,
            client=client,
        )
    assert missing_sol.state == "unavailable"

    def selected_models(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-6-luna"}, {"id": "gpt-6-sol"}]},
        )

    with httpx.Client(transport=httpx.MockTransport(selected_models)) as client:
        available = check_connection(
            "openai",
            {"LUNA_API_KEY": "test"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=selections,
            client=client,
        )
    assert available.state == "connected"


def test_connection_check_for_named_provider_ignores_other_selected_provider() -> None:
    selections = StageModelSelections(
        planner=ModelChoice.MIMO_V26_FLASH,
        scout=ModelChoice.GPT_6_SOL_HIGH,
        gap_analysis=ModelChoice.GPT_6_SOL_HIGH,
        search_agent=ModelChoice.GPT_6_SOL_HIGH,
        source_selection=ModelChoice.GPT_6_SOL_HIGH,
        extractor=ModelChoice.GPT_6_SOL_HIGH,
        analyst=ModelChoice.GPT_6_SOL_HIGH,
    )
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "mimo-v2.6-flash"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            "mimo",
            {"MIMO_API_KEY": "test"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=selections,
            client=client,
        )
    assert result.state == "connected"
    assert len(seen) == 1
    assert seen[0].url.host == "api.xiaomimimo.com"


def test_connection_check_standard_profile_uses_historical_physical_models() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-5.6-luna"}, {"id": "gpt-6-luna"}]},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            "openai",
            {"LUNA_API_KEY": "test"},
            model_profile="standard-2026-09",
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert result.state == "connected"


def test_connection_check_standard_mimo_requires_both_historical_models() -> None:
    def pro_only(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"data": [{"id": "mimo-v2.5-pro"}]})

    with httpx.Client(transport=httpx.MockTransport(pro_only)) as client:
        missing = check_connection(
            "mimo",
            {"MIMO_API_KEY": "test"},
            model_profile="standard-2026-09",
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert missing.state == "unavailable"

    def both_models(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"data": [{"id": "mimo-v2.5"}, {"id": "mimo-v2.5-pro"}]},
        )

    with httpx.Client(transport=httpx.MockTransport(both_models)) as client:
        connected = check_connection(
            "mimo",
            {"MIMO_API_KEY": "test"},
            model_profile="standard-2026-09",
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert connected.state == "connected"


def test_connection_check_unselected_provider_makes_no_request() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "mimo-v2.6-flash"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            "mimo",
            {"MIMO_API_KEY": "test"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert result.state == "unavailable"
    assert "not selected" in result.message.lower()
    assert seen == []


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"data": [{"name": "gpt-6-luna"}]},
        {"data": "malformed"},
        {},
    ],
)
def test_connection_check_requires_a_well_formed_selected_model_list(
    payload: object,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            "openai",
            {"LUNA_API_KEY": "test"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert result.state == "unavailable"
    assert "not listed" in result.message.lower() or "could not be confirmed" in (
        result.message.lower()
    )


def test_connection_check_custom_endpoint_makes_no_request() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            "openai",
            {
                "LUNA_API_KEY": "test",
                "LUNA_BASE_URL": "https://gateway.example.test/v1",
            },
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert result.state == "unavailable"
    assert seen == []


def test_connection_check_custom_model_override_makes_no_request() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = check_connection(
            "openai",
            {"LUNA_API_KEY": "test", "LUNA_MODEL": "gateway-deployment"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert result.state == "unavailable"
    assert seen == []


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
        result = check_connection(
            "openai",
            {"LUNA_API_KEY": "test"},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
            client=client,
        )
    assert result.state == expected
    assert "private-secret" not in result.model_dump_json()


def test_source_presence_check_is_not_misrepresented_as_authentication() -> None:
    assert (
        check_connection(
            "exa",
            {},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
        ).state
        == "missing"
    )
    result = check_connection(
        "exa",
        {"EXA_API_KEY": "test"},
        model_profile=CONFIGURABLE_PROFILE_ID,
        stage_models=DEFAULT_STAGE_MODELS,
    )
    assert result.state == "saved"
    assert "explicit research run" in result.message
    with pytest.raises(ValueError):
        check_connection(
            "unknown",
            {},
            model_profile=CONFIGURABLE_PROFILE_ID,
            stage_models=DEFAULT_STAGE_MODELS,
        )
