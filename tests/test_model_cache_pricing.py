"""Real-adapter regressions for route-aware cache costs and persisted budgets."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import BaseModel, ConfigDict
from test_v2_phase7_adaptive_search import _db

from models import (
    DiscoveryProvider,
    ScoutBatch,
    ScoutDecision,
    ScoutItem,
    StrictModel,
    V2GapAnalysisModelOutput,
    V2InitialPlannerModelOutput,
)
from providers.clients import ProviderClients
from providers.llm import V2_LLM_ROUTING, LLMRequest, LLMStage, PromptTemplate
from providers.mimo import MimoProviderError
from providers.model_profiles import profile_environment
from providers.v2_budget import BudgetedV2LLMProvider, V2RunCeilings
from providers.v2_factory import V2ProductionFactoryConfig, build_v2_production_bundle


class PricingFixture(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: str


def _config() -> V2ProductionFactoryConfig:
    return V2ProductionFactoryConfig.from_environment(
        profile_environment(
            {"MIMO_API_KEY": "fake-mimo", "LUNA_API_KEY": "fake-luna", "EXA_API_KEY": "fake-exa"},
            "standard-2026-09",
        ),
        repository_revision="pricing-regression",
        discovery_providers=(DiscoveryProvider.EXA,),
    )


def _output(stage: LLMStage, run_id: UUID) -> BaseModel:
    if stage is LLMStage.SCOUT:
        return ScoutBatch(
            run_id=run_id,
            items=(
                ScoutItem(
                    item_id=UUID(int=1), decision=ScoutDecision.RETRIEVE, rationale="Relevant."
                ),
            ),
        )
    if stage is LLMStage.PLANNER:
        return V2InitialPlannerModelOutput(searches=())
    return V2GapAnalysisModelOutput(
        coverage_summary="Enough",
        material_gaps=(),
        continue_research=False,
        stop_reason="Enough",
        new_search_directions=(),
        discovered_terms=(),
    )


def _request(stage: LLMStage, run_id: UUID) -> LLMRequest:
    route = V2_LLM_ROUTING.for_stage(stage)
    return LLMRequest(
        run_id=run_id,
        stage=stage,
        prompt=PromptTemplate(stage=stage, version="pricing-test", sha256="0" * 64, text="Test"),
        rendered_prompt="Test",
        input_artifact=PricingFixture(value="test"),
        input_artifact_ids=(uuid4(),),
        requested_output_type=type(_output(stage, run_id)),
        model_alias=route.primary,
        generation=route.generation,
    )


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        (LLMStage.SCOUT, "0.000058240"),
        (LLMStage.PLANNER, "0.000176880"),
        # Uncached Luna tokens conservatively include possible cache writes (1.25x).
        (LLMStage.GAP_ANALYSIS, "0.000186000"),
    ],
)
@pytest.mark.parametrize("failure", [False, True])
def test_real_routes_persist_their_own_cache_cost(
    tmp_path: Path, stage: LLMStage, expected: str, failure: bool
) -> None:
    config = _config()
    run_id = uuid4()
    path = _db(tmp_path, run_id)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if stage is LLMStage.GAP_ANALYSIS:
            assert payload["reasoning_effort"] == "high"
            assert payload["max_completion_tokens"] == 16384
        else:
            assert "reasoning_effort" not in payload
            assert payload["max_completion_tokens"] == (4096 if stage is LLMStage.SCOUT else 8192)
        return httpx.Response(
            200,
            json={
                "model": payload["model"],
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "bad json"
                            if failure
                            else _output(stage, run_id).model_dump_json()
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "total_tokens": 1100,
                    "prompt_tokens_details": {"cached_tokens": 800},
                },
            },
        )

    client = httpx.Client(base_url="https://fixture.test", transport=httpx.MockTransport(handler))
    bundle = build_v2_production_bundle(config, clients=ProviderClients(llm=client))
    budget = BudgetedV2LLMProvider(
        db_path=path,
        run_id=run_id,
        provider=bundle.llm,
        routing_config=config.routing,
        ceilings=V2RunCeilings(),
    )
    if failure:
        with pytest.raises(MimoProviderError):
            budget.generate(_request(stage, run_id))
    else:
        assert budget.generate(_request(stage, run_id)) == _output(stage, run_id)
    assert budget.snapshot().cost_exposure_usd == Decimal(expected)
    assert budget.snapshot().physical_calls_used == 1
    restored = BudgetedV2LLMProvider(
        db_path=path,
        run_id=run_id,
        provider=bundle.llm,
        routing_config=config.routing,
        ceilings=V2RunCeilings(),
    )
    assert restored.snapshot() == budget.snapshot()


@pytest.mark.parametrize("cached", [None, -1, True, 1001, "800"])
def test_missing_or_invalid_cache_metadata_retains_model_cap(cached: object) -> None:
    config = _config()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gpt-5.6-luna",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": _output(LLMStage.GAP_ANALYSIS, uuid4()).model_dump_json()
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "total_tokens": 1100,
                    "prompt_tokens_details": {"cached_tokens": cached},
                },
            },
        )

    bundle = build_v2_production_bundle(
        config,
        clients=ProviderClients(
            llm=httpx.Client(
                base_url="https://fixture.test", transport=httpx.MockTransport(handler)
            )
        ),
    )
    request = _request(LLMStage.GAP_ANALYSIS, uuid4())
    output = bundle.llm.generate(request)
    usage = bundle.llm.usage_for(request, output, None)
    assert usage is not None
    assert usage.cost_usd == Decimal("0.000680000")
    assert usage.cached_input_tokens is None


@pytest.mark.parametrize(("prompt", "expected"), [(272000, "0.012920000"), (272001, "0.025780500")])
def test_luna_long_context_threshold_uses_full_input_including_cached(
    prompt: int, expected: str
) -> None:
    config = _config()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gpt-5.6-luna",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": _output(LLMStage.GAP_ANALYSIS, uuid4()).model_dump_json()
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt,
                    "completion_tokens": 100,
                    "total_tokens": prompt + 100,
                    "prompt_tokens_details": {"cached_tokens": 240000},
                },
            },
        )

    bundle = build_v2_production_bundle(
        config,
        clients=ProviderClients(
            llm=httpx.Client(
                base_url="https://fixture.test", transport=httpx.MockTransport(handler)
            )
        ),
    )
    request = _request(LLMStage.GAP_ANALYSIS, uuid4())
    output = bundle.llm.generate(request)
    usage = bundle.llm.usage_for(request, output, None)
    assert usage is not None
    assert usage.cost_usd == Decimal(expected)


@pytest.mark.parametrize(
    ("cached", "writes", "expected"),
    [
        (800, 0, "0.000176000"),
        (800, 100, "0.000181000"),
        (800, 200, "0.000186000"),
        (0, 0, "0.000320000"),
        (0, 1000, "0.000370000"),
        (800, -1, "0.000186000"),
        (800, True, "0.000186000"),
        (800, 201, "0.000186000"),
    ],
)
def test_luna_cache_writes_are_disjoint_and_missing_counts_are_conservative(
    cached: int, writes: object, expected: str
) -> None:
    from providers.mimo import _usage
    from providers.pricing import cache_prices_for_route

    config = _config().routing
    usage = _usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "total_tokens": 1100,
            "prompt_tokens_details": {"cached_tokens": cached, "cache_write_tokens": writes},
        },
        config.luna_price_cap,
        cache_prices=cache_prices_for_route(config.luna.base_url, config.luna.model),
    )
    assert usage.cost_usd == Decimal(expected)


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://custom.test/v1", "gpt-5.6-luna"),
        ("https://api.openai.com/v1", "custom-model"),
        ("https://api.xiaomimimo.com/v1", "gpt-5.6-luna"),
    ],
)
def test_custom_route_never_inherits_another_models_cache_discount(
    base_url: str, model: str
) -> None:
    from providers.mimo import _usage
    from providers.pricing import ModelPriceCap, cache_prices_for_route

    cap = ModelPriceCap(
        model=model, input_usd_per_token=Decimal("0.00001"), output_usd_per_token=Decimal("0.00002")
    )
    usage = _usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "total_tokens": 1100,
            "prompt_tokens_details": {"cached_tokens": 800},
        },
        cap,
        cache_prices=cache_prices_for_route(base_url, model),
    )
    assert usage.cost_usd == Decimal("0.012")


def test_unknown_usage_retains_reservation_after_restart(tmp_path: Path) -> None:
    config = _config()
    run_id = uuid4()
    path = _db(tmp_path, run_id)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic unknown outcome", request=request)

    bundle = build_v2_production_bundle(
        config,
        clients=ProviderClients(
            llm=httpx.Client(
                base_url="https://fixture.test", transport=httpx.MockTransport(handler)
            )
        ),
    )
    budget = BudgetedV2LLMProvider(
        db_path=path,
        run_id=run_id,
        provider=bundle.llm,
        routing_config=config.routing,
        ceilings=V2RunCeilings(),
    )
    with pytest.raises(MimoProviderError):
        budget.generate(_request(LLMStage.GAP_ANALYSIS, run_id))
    reservation = config.routing.preflight().reserve(LLMStage.GAP_ANALYSIS, 4)
    assert budget.snapshot().cost_exposure_usd == reservation.reserved_cost_usd
    restored = BudgetedV2LLMProvider(
        db_path=path,
        run_id=run_id,
        provider=bundle.llm,
        routing_config=config.routing,
        ceilings=V2RunCeilings(),
    )
    assert restored.snapshot() == budget.snapshot()
