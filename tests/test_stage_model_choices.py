"""Offline contracts for every supported fresh-v2 stage and model choice."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import ConfigDict, ValidationError

from cli import _build_parser, _parse_run_ceilings, _parse_stage_models
from desktop_settings import InterfaceSettings
from models import DiscoveryProvider, StrictModel
from providers.clients import ProviderClients
from providers.config import ProviderConfigurationError
from providers.llm import (
    V2_LLM_ROUTING,
    LLMRequest,
    LLMStage,
    PromptTemplate,
    _allowed_output_types,
)
from providers.mimo import MimoProviderError, _request_payload
from providers.model_choices import (
    ACTIVE_MODEL_STAGES,
    DEFAULT_STAGE_MODELS,
    MODEL_OPTIONS,
    ModelChoice,
    StageModelSelections,
    completion_limit_for,
    option_for,
)
from providers.pricing import cache_prices_for_route
from providers.v2_budget import V2RunCeilings
from providers.v2_factory import V2ProductionFactoryConfig, build_v2_production_bundle
from providers.v2_routing import V2RoutingConfig


class ChoiceFixture(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = "test"


def _selections(stage: LLMStage, choice: ModelChoice) -> StageModelSelections:
    values = DEFAULT_STAGE_MODELS.model_dump(mode="json")
    values[stage.value] = choice.value
    return StageModelSelections.model_validate(values)


def _request(stage: LLMStage, alias: ModelChoice) -> LLMRequest:
    return LLMRequest(
        run_id=uuid4(),
        stage=stage,
        prompt=PromptTemplate(stage=stage, version="choice-test", sha256="0" * 64, text="Test"),
        rendered_prompt="Test",
        input_artifact=ChoiceFixture(),
        input_artifact_ids=(uuid4(),),
        requested_output_type=_allowed_output_types(stage)[0],
        model_alias=alias.value,
        generation=V2_LLM_ROUTING.for_stage(stage).generation,
    )


@pytest.mark.parametrize("stage", ACTIVE_MODEL_STAGES)
@pytest.mark.parametrize("choice", tuple(ModelChoice))
def test_every_stage_choice_has_exact_route_payload_and_reservation(
    stage: LLMStage, choice: ModelChoice
) -> None:
    selections = _selections(stage, choice)
    routing = V2RoutingConfig.from_environment(
        {"LUNA_API_KEY": "test-openai", "MIMO_API_KEY": "test-mimo"},
        repository_revision="choice-test",
        stage_models=selections,
    )
    option = option_for(choice)
    configured = routing.configuration_for_stage(stage)
    route = routing.preflight().for_stage(stage)
    assert configured.route == route
    assert route.logical_alias.value == choice.value
    assert route.physical_model == option.model
    assert route.provider_name == ("openai" if option.provider == "openai" else "xiaomi-mimo")
    assert route.max_completion_tokens == completion_limit_for(stage)
    reservation = routing.preflight().reserve(stage, 1000)
    assert reservation.output_tokens == completion_limit_for(stage)
    assert reservation.reserved_cost_usd == route.price_cap.upper_bound(
        1000, completion_limit_for(stage)
    )
    payload = _request_payload(_request(stage, choice), configured.config)
    assert payload["model"] == option.model
    assert payload["max_completion_tokens"] == completion_limit_for(stage)
    assert payload["response_format"] == {"type": "json_object"}
    if option.provider == "openai":
        assert payload["reasoning_effort"] == option.reasoning_effort
        assert payload["service_tier"] == "default"
        assert "thinking" not in payload
    else:
        assert payload["thinking"] == {"type": "enabled"}
        assert "temperature" not in payload
        assert "reasoning_effort" not in payload


@pytest.mark.parametrize("stage", ACTIVE_MODEL_STAGES)
@pytest.mark.parametrize("choice", tuple(ModelChoice))
def test_every_stage_choice_uses_its_selected_mock_transport(
    stage: LLMStage, choice: ModelChoice
) -> None:
    observed: list[tuple[str, httpx.Request]] = []

    def response_for(provider: str) -> httpx.MockTransport:
        def respond(request: httpx.Request) -> httpx.Response:
            observed.append((provider, request))
            return httpx.Response(401, json={"error": {"message": "test rejection"}})

        return httpx.MockTransport(respond)

    selections = _selections(stage, choice)
    config = V2ProductionFactoryConfig.from_environment(
        {
            "LUNA_API_KEY": "test-openai",
            "MIMO_API_KEY": "test-mimo",
            "EXA_API_KEY": "test-exa",
        },
        repository_revision="choice-transport-test",
        discovery_providers=(DiscoveryProvider.EXA,),
        stage_models=selections,
        ceilings=V2RunCeilings(max_total_cost_usd=Decimal("20")),
    )
    with (
        httpx.Client(
            base_url="https://api.openai.com/v1", transport=response_for("openai")
        ) as openai_client,
        httpx.Client(
            base_url="https://api.xiaomimimo.com/v1", transport=response_for("mimo")
        ) as mimo_client,
    ):
        bundle = build_v2_production_bundle(
            config,
            clients=ProviderClients(luna_llm=openai_client, mimo_v25_pro_llm=mimo_client),
        )
        with pytest.raises(MimoProviderError):
            bundle.llm.generate(_request(stage, choice))
    assert len(observed) == 1
    provider, sent = observed[0]
    option = option_for(choice)
    assert provider == option.provider
    assert sent.url.path == "/v1/chat/completions"
    assert json.loads(sent.content)["model"] == option.model
    if provider == "openai":
        assert sent.headers["authorization"] == "Bearer test-openai"
        assert "api-key" not in sent.headers
    else:
        assert sent.headers["api-key"] == "test-mimo"
        assert "authorization" not in sent.headers


def test_default_selections_and_catalog_are_exact() -> None:
    assert len(MODEL_OPTIONS) == 6
    assert {option.id for option in MODEL_OPTIONS} == set(ModelChoice)
    assert DEFAULT_STAGE_MODELS.scout is ModelChoice.GPT_6_LUNA_HIGH
    assert DEFAULT_STAGE_MODELS.extractor is ModelChoice.GPT_6_LUNA_HIGH
    for stage in ACTIVE_MODEL_STAGES:
        if stage not in (LLMStage.SCOUT, LLMStage.EXTRACTOR):
            assert DEFAULT_STAGE_MODELS.for_stage(stage) is ModelChoice.GPT_6_LUNA_XHIGH
    assert "gpt-5.6-luna-high" not in {choice.value for choice in ModelChoice}
    assert "gpt-5.6-luna-xhigh" not in {choice.value for choice in ModelChoice}
    for choice, effort in (
        (ModelChoice.GPT_6_LUNA_HIGH, "high"),
        (ModelChoice.GPT_6_LUNA_XHIGH, "xhigh"),
    ):
        option = option_for(choice)
        assert option.model == "gpt-6-luna"
        assert option.reasoning_effort == effort
        assert option.input_per_million == Decimal("0.10")
        assert option.cached_input_per_million == Decimal("0.01")
        assert option.output_per_million == Decimal("0.50")
        assert option.input_cap_per_million == Decimal("0.25")
        assert option.output_cap_per_million == Decimal("0.75")
    with pytest.raises(ValidationError):
        StageModelSelections(planner="unknown")
    with pytest.raises(ValidationError):
        StageModelSelections(unexpected="model")


def test_credentials_are_required_only_for_selected_providers() -> None:
    environment = {"LUNA_API_KEY": "openai-only"}
    V2RoutingConfig.from_environment(
        environment, repository_revision="test", stage_models=DEFAULT_STAGE_MODELS
    )
    mixed = _selections(LLMStage.ANALYST, ModelChoice.MIMO_V26_PRO)
    with pytest.raises(ProviderConfigurationError, match="MiMo API key"):
        V2RoutingConfig.from_environment(
            environment, repository_revision="test", stage_models=mixed
        )
    mimo_only = StageModelSelections.model_validate(
        {stage.value: ModelChoice.MIMO_V26_FLASH.value for stage in ACTIVE_MODEL_STAGES}
    )
    V2RoutingConfig.from_environment(
        {"MIMO_API_KEY": "mimo-only"}, repository_revision="test", stage_models=mimo_only
    )
    with pytest.raises(ProviderConfigurationError, match="OpenAI API key"):
        V2RoutingConfig.from_environment({}, repository_revision="test", stage_models=mixed)


def test_selected_openai_route_accepts_luna6_marker_and_legacy_luna5_marker() -> None:
    for marker in ("gpt-6-luna", "gpt-5.6-luna"):
        routing = V2RoutingConfig.from_environment(
            {"LUNA_API_KEY": "test-openai", "LUNA_MODEL": marker},
            repository_revision="test",
            stage_models=DEFAULT_STAGE_MODELS,
        )
        assert routing.configuration_for_stage(LLMStage.SCOUT).route.physical_model == "gpt-6-luna"
    with pytest.raises(ProviderConfigurationError, match="standard OpenAI model override"):
        V2RoutingConfig.from_environment(
            {"LUNA_API_KEY": "test-openai", "LUNA_MODEL": "custom-model"},
            repository_revision="test",
            stage_models=DEFAULT_STAGE_MODELS,
        )


def test_choice_fingerprint_and_price_catalog_are_model_specific() -> None:
    environment = {
        "LUNA_API_KEY": "secret-openai-credential",
        "MIMO_API_KEY": "secret-mimo-credential",
    }
    default = V2RoutingConfig.from_environment(
        environment, repository_revision="test", stage_models=DEFAULT_STAGE_MODELS
    )
    changed = V2RoutingConfig.from_environment(
        environment,
        repository_revision="test",
        stage_models=_selections(LLMStage.ANALYST, ModelChoice.MIMO_V26_PRO),
    )
    assert default.fingerprint_payload() != changed.fingerprint_payload()
    assert all(secret not in str(default.fingerprint_payload()) for secret in environment.values())
    for option in MODEL_OPTIONS:
        url = (
            "https://api.openai.com/v1"
            if option.provider == "openai"
            else "https://api.xiaomimimo.com/v1"
        )
        prices = cache_prices_for_route(url, option.model)
        assert prices is not None
        assert prices.input_per_million == option.input_per_million
        assert prices.cached_per_million == option.cached_input_per_million
        assert prices.output_per_million == option.output_per_million
        assert prices.cache_write_multiplier == (
            Decimal("1.25") if option.provider == "openai" else Decimal("1")
        )
        assert cache_prices_for_route("https://example.test/v1", option.model) is None


def test_cli_model_overrides_and_rejections() -> None:
    selected = _parse_stage_models(
        [
            "planner=gpt-6-luna-xhigh",
            "scout=gpt-6-luna-high",
            "source_selection=gpt-6-sol-high",
            "analyst=mimo-v2.6-pro",
        ]
    )
    assert selected.planner is ModelChoice.GPT_6_LUNA_XHIGH
    assert selected.scout is ModelChoice.GPT_6_LUNA_HIGH
    assert selected.source_selection is ModelChoice.GPT_6_SOL_HIGH
    assert selected.analyst is ModelChoice.MIMO_V26_PRO
    assert selected.extractor is ModelChoice.GPT_6_LUNA_HIGH
    with pytest.raises(ValueError, match="repeated"):
        _parse_stage_models(["planner=gpt-6-sol-high", "planner=mimo-v2.6-pro"])
    with pytest.raises(ValueError, match="unsupported"):
        _parse_stage_models(["planner=unknown"])


def test_budget_limit_accepts_twenty_dollars_and_rejects_more() -> None:
    parsed = _parse_run_ceilings(max_tokens=500_000, max_cost_usd="20.00", max_llm_calls=160)
    assert parsed.max_cost_usd == Decimal("20.00")
    assert V2RunCeilings(max_total_cost_usd=parsed.max_cost_usd).max_total_cost_usd == Decimal(
        "20.00"
    )
    with pytest.raises(ValidationError):
        _parse_run_ceilings(max_tokens=500_000, max_cost_usd="20.01", max_llm_calls=160)
    with pytest.raises(ValidationError):
        V2RunCeilings(max_total_cost_usd=Decimal("20.01"))


def test_ordinary_cli_defaults_to_twenty_cent_model_budget() -> None:
    args = _build_parser().parse_args(
        ["run", "A public claim", "--db-path", "/tmp/research.sqlite3", "--max-tokens", "500000"]
    )
    assert args.max_cost_usd == "0.20"
    assert args.model == []


def test_desktop_model_budget_is_positive_and_at_most_twenty_dollars() -> None:
    assert InterfaceSettings(maxCost="20.00").maxCost == "20.00"
    with pytest.raises(ValidationError):
        InterfaceSettings(maxCost="0")
    with pytest.raises(ValidationError):
        InterfaceSettings(maxCost="20.01")
