from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from agents.planner import PlannerLLMInput
from models import PlannerOutput
from providers.config import MimoRouteConfig, ProviderConfigurationError
from providers.llm import (
    DIRECT_MIMO_ROUTING,
    V2_LLM_ROUTING,
    LLMRequest,
    LLMStage,
    ModelAlias,
    PromptTemplate,
)
from providers.mimo import MimoFailureCode, MimoProviderError, XiaomiMimoAdapter
from providers.pricing import ModelPriceCap
from providers.v2_routing import V2RoutingConfig


def _environment() -> dict[str, str]:
    return {
        "MIMO_API_KEY": "mimo-secret-value",
        "MIMO_V25_MODEL": "mimo-v2.5",
        "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
        "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
        "LUNA_API_KEY": "luna-secret-value",
        "LUNA_BASE_URL": "https://luna.example.test/v1",
        "LUNA_MODEL": "deployment-owned-luna-model",
        "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
        "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
    }


def _config(environment: dict[str, str] | None = None) -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        environment or _environment(),
        repository_revision="v2-phase2-test-revision",
    )


def test_v2_stage_to_logical_alias_routing_is_complete() -> None:
    expected = {
        LLMStage.PLANNER: ModelAlias.MIMO_V25_PRO,
        LLMStage.SEARCH_AGENT: ModelAlias.MIMO_V25_PRO,
        LLMStage.SCOUT: ModelAlias.MIMO_V25,
        LLMStage.GAP_ANALYSIS: ModelAlias.GPT_5_6_LUNA_HIGH,
        LLMStage.SOURCE_SELECTION: ModelAlias.MIMO_V25_PRO,
        LLMStage.EXTRACTOR: ModelAlias.MIMO_V25_PRO,
        LLMStage.ANALYST: ModelAlias.GPT_5_6_LUNA_HIGH,
        LLMStage.REVIEWER: ModelAlias.MIMO_V25_PRO,
        LLMStage.SYNTHESIZER: ModelAlias.MIMO_V25_PRO,
    }

    assert {stage: V2_LLM_ROUTING.for_stage(stage).primary for stage in LLMStage} == expected


def test_v2_mimo_normal_and_pro_routes_are_independent() -> None:
    config = _config()

    normal = config.preflight().for_stage(LLMStage.SCOUT)
    pro = config.preflight().for_stage(LLMStage.PLANNER)

    assert normal.logical_alias is ModelAlias.MIMO_V25
    assert normal.physical_model == "mimo-v2.5"
    assert pro.logical_alias is ModelAlias.MIMO_V25_PRO
    assert pro.physical_model == "mimo-v2.5-pro"
    assert normal.price_cap != pro.price_cap


def test_luna_route_requires_explicit_deployment_configuration() -> None:
    route = _config().preflight().for_stage(LLMStage.GAP_ANALYSIS)

    assert route.logical_alias is ModelAlias.GPT_5_6_LUNA_HIGH
    assert route.provider_name == "luna"
    assert route.physical_model == "deployment-owned-luna-model"

    environment = _environment()
    del environment["LUNA_MODEL"]
    with pytest.raises(ProviderConfigurationError, match="LUNA_MODEL"):
        _config(environment)


def test_v2_preflight_rejects_unknown_normal_route_pricing() -> None:
    environment = _environment()
    del environment["MIMO_V25_INPUT_USD_PER_TOKEN"]

    with pytest.raises(ProviderConfigurationError, match="MIMO_V25_INPUT_USD_PER_TOKEN"):
        _config(environment)


def test_mimo_normal_route_rejects_returned_model_mismatch() -> None:
    config = MimoRouteConfig(api_key=SecretStr("mimo-secret"), model="mimo-v2.5")
    adapter = XiaomiMimoAdapter(
        config,
        expected_model_alias=ModelAlias.MIMO_V25,
        price_cap=ModelPriceCap(
            model="mimo-v2.5",
            input_usd_per_token=Decimal("0.000001"),
            output_usd_per_token=Decimal("0.000002"),
        ),
        client=httpx.Client(
            base_url=config.base_url,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "id": "response-id",
                        "model": "mimo-v2.5-pro",
                        "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                    },
                    request=request,
                )
            ),
        ),
    )
    run_id = uuid4()
    request = LLMRequest(
        run_id=run_id,
        stage=LLMStage.PLANNER,
        prompt=PromptTemplate(
            stage=LLMStage.PLANNER,
            version="v2-test",
            sha256="0" * 64,
            text="test prompt",
        ),
        rendered_prompt="test prompt",
        input_artifact=PlannerLLMInput(run_id=run_id, raw_claim="Public claim."),
        input_artifact_ids=(uuid4(),),
        requested_output_type=PlannerOutput,
        model_alias=ModelAlias.MIMO_V25,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.SCOUT).generation,
    )

    with pytest.raises(MimoProviderError) as exc_info:
        adapter.generate(request)
    assert exc_info.value.code is MimoFailureCode.MODEL_MISMATCH


def test_v2_route_configuration_and_contract_redact_credentials() -> None:
    config = _config()
    contract = config.contract(uuid4(), datetime(2026, 8, 20, tzinfo=UTC))

    for secret in ("mimo-secret-value", "luna-secret-value"):
        assert secret not in repr(config)
        assert secret not in contract.payload_json


def test_v2_fingerprint_changes_for_routing_and_pricing() -> None:
    first = _config().contract(uuid4(), datetime(2026, 8, 20, tzinfo=UTC))
    changed = _environment()
    changed["LUNA_MODEL"] = "another-deployment-owned-luna-model"
    changed["LUNA_INPUT_USD_PER_TOKEN"] = "0.000005"
    second = _config(changed).contract(uuid4(), datetime(2026, 8, 20, tzinfo=UTC))

    assert first.fingerprint_sha256 != second.fingerprint_sha256
    assert first.model_identity != second.model_identity
    assert first.policy_identity != second.policy_identity


def test_v2_preflight_has_a_positive_reservation_price_for_every_stage() -> None:
    preflight = _config().preflight()

    for stage in LLMStage:
        route = preflight.for_stage(stage)
        reservation = preflight.reserve(stage, input_tokens=1)
        assert reservation.reserved_tokens == 1 + route.max_completion_tokens
        assert reservation.reserved_cost_usd == route.price_cap.upper_bound(
            1, route.max_completion_tokens
        )


def test_historical_direct_mimo_routes_remain_readable_and_unchanged() -> None:
    for stage in LLMStage:
        route = DIRECT_MIMO_ROUTING.for_stage(stage)
        assert route.primary is ModelAlias.MIMO_V25_PRO
        assert route.fallbacks == ()
