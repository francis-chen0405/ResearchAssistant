"""Fail-closed logical model routing for ResearchAssistant v2 Phase 2.

This module is intentionally configuration and identity only.  It does not alter the
historical provider pipeline or start Scout, gap, Analyst, or source-selection work.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from pydantic import ConfigDict, Field, SecretStr, model_validator

from models import ProviderRunContract, StrictModel
from provider_contract import canonical_provider_contract_payload
from providers.config import (
    LunaConfig,
    MimoChoiceConfig,
    MimoRouteConfig,
    OpenAIChoiceConfig,
    ProviderConfigurationError,
)
from providers.llm import V2_LLM_ROUTING, LLMStage, ModelAlias, StageRoute, load_prompt
from providers.model_choices import (
    ACTIVE_MODEL_STAGES,
    StageModelSelections,
    completion_limit_for,
    option_for,
)
from providers.pricing import (
    DIRECT_MIMO_PRICE_CAP,
    ModelPriceCap,
    price_cap_from_environment,
)

V2_ROUTING_FINGERPRINT_VERSION = "researchassistant-v2-phase-2-routing-v1"
V2_ROUTING_POLICY_VERSION = "researchassistant-v2-routing-policy-v1"
V2_ROUTING_PROMPT_VERSION = "researchassistant-v2-routing-unwired-prompt-v1"
V2_ROUTING_SCHEMA_VERSION = "researchassistant-v2-phase-1-contracts-v1"


class V2PhysicalModelRoute(StrictModel):
    """Secret-free physical route selected for one logical model alias."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_alias: ModelAlias
    provider_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    physical_model: str = Field(min_length=1)
    max_completion_tokens: int = Field(ge=1)
    price_cap: ModelPriceCap

    @model_validator(mode="after")
    def validate_pricing_model(self) -> V2PhysicalModelRoute:
        if self.price_cap.model != self.physical_model:
            raise ValueError("route price cap must cover the configured physical model")
        return self


class V2StageConfiguration(StrictModel):
    """One selected stage route with its secret-bearing transport configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: LLMStage
    route: V2PhysicalModelRoute
    config: MimoChoiceConfig | OpenAIChoiceConfig

    @model_validator(mode="after")
    def validate_identity(self) -> V2StageConfiguration:
        if self.route.physical_model != self.config.model:
            raise ValueError("selected stage model and adapter model must agree")
        if self.route.max_completion_tokens != self.config.max_completion_tokens:
            raise ValueError("selected stage allowance and adapter allowance must agree")
        return self


class V2ModelReservation(StrictModel):
    """Deterministic pre-call reservation for one configured v2 physical route."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: LLMStage
    logical_alias: ModelAlias
    physical_model: str = Field(min_length=1)
    input_tokens: int = Field(ge=1)
    output_tokens: int = Field(ge=1)
    reserved_tokens: int = Field(ge=1)
    reserved_cost_usd: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def validate_totals(self) -> V2ModelReservation:
        if self.reserved_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("reserved tokens must equal input plus configured output tokens")
        return self


class V2RoutingPreflight(StrictModel):
    """Validated route coverage for a fresh v2 run, safe to fingerprint or display."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    routing: tuple[tuple[LLMStage, V2PhysicalModelRoute], ...]

    @model_validator(mode="after")
    def validate_coverage(self) -> V2RoutingPreflight:
        stages = tuple(stage for stage, _ in self.routing)
        if len(stages) != len(set(stages)):
            raise ValueError("v2 routing preflight cannot contain duplicate stages")
        if set(stages) not in (set(LLMStage), set(ACTIVE_MODEL_STAGES)):
            raise ValueError("v2 routing preflight must cover every enabled v2 stage")
        return self

    def for_stage(self, stage: LLMStage) -> V2PhysicalModelRoute:
        for candidate_stage, route in self.routing:
            if candidate_stage is stage:
                return route
        raise ValueError(f"no v2 route is configured for {stage.value}")

    def reserve(self, stage: LLMStage, input_tokens: int) -> V2ModelReservation:
        """Calculate the exact conservative reservation without contacting a provider."""
        if input_tokens < 1:
            raise ValueError("input_tokens must be at least one")
        route = self.for_stage(stage)
        output_tokens = route.max_completion_tokens
        return V2ModelReservation(
            stage=stage,
            logical_alias=route.logical_alias,
            physical_model=route.physical_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reserved_tokens=input_tokens + output_tokens,
            reserved_cost_usd=route.price_cap.upper_bound(input_tokens, output_tokens),
        )


class V2RoutingConfig(StrictModel):
    """All v2 logical aliases, physical routes, prices, and fingerprint inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mimo_v25: MimoRouteConfig | None = None
    mimo_v25_pro: MimoRouteConfig | None = None
    luna: LunaConfig | None = None
    mimo_v25_price_cap: ModelPriceCap | None = None
    mimo_v25_pro_price_cap: ModelPriceCap | None = None
    luna_price_cap: ModelPriceCap | None = None
    stage_models: StageModelSelections | None = None
    stage_configurations: tuple[V2StageConfiguration, ...] = ()
    repository_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_routes(self) -> V2RoutingConfig:
        if self.stage_models is not None:
            stages = tuple(item.stage for item in self.stage_configurations)
            if len(stages) != len(set(stages)) or set(stages) != set(ACTIVE_MODEL_STAGES):
                raise ValueError("selected routes must cover each active v2 stage once")
            if any(
                item.route.logical_alias.value != self.stage_models.for_stage(item.stage).value
                for item in self.stage_configurations
            ):
                raise ValueError("selected route identity must match its stage choice")
            return self
        if any(
            value is None
            for value in (
                self.mimo_v25,
                self.mimo_v25_pro,
                self.luna,
                self.mimo_v25_price_cap,
                self.mimo_v25_pro_price_cap,
                self.luna_price_cap,
            )
        ):
            raise ValueError("legacy v2 routing requires all three configured routes")
        assert self.mimo_v25 is not None
        assert self.mimo_v25_pro is not None
        assert self.luna is not None
        assert self.mimo_v25_price_cap is not None
        assert self.mimo_v25_pro_price_cap is not None
        assert self.luna_price_cap is not None
        if self.mimo_v25.model == self.mimo_v25_pro.model:
            raise ValueError("MiMo-v2.5 and MiMo-v2.5-Pro must use distinct physical models")
        expected = (
            (self.mimo_v25.model, self.mimo_v25_price_cap),
            (self.mimo_v25_pro.model, self.mimo_v25_pro_price_cap),
            (self.luna.model, self.luna_price_cap),
        )
        if any(model != price_cap.model for model, price_cap in expected):
            raise ValueError("each v2 physical model must have an exact price cap")
        return self

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        repository_revision: str,
        stage_models: StageModelSelections | None = None,
    ) -> V2RoutingConfig:
        if stage_models is not None:
            return cls(
                stage_models=stage_models,
                stage_configurations=_selected_stage_configurations(environment, stage_models),
                repository_revision=repository_revision,
            )
        try:
            mimo_v25 = MimoRouteConfig.from_environment(
                environment,
                model_environment_name="MIMO_V25_MODEL",
                default_model="mimo-v2.5",
            )
            mimo_v25_pro = MimoRouteConfig.from_environment(
                environment,
                model_environment_name="MIMO_V25_PRO_MODEL",
                default_model="mimo-v2.5-pro",
            )
            luna = LunaConfig.from_environment(environment)
            normal_price = price_cap_from_environment(
                environment,
                model=mimo_v25.model,
                environment_prefix="MIMO_V25",
            )
            pro_price = (
                DIRECT_MIMO_PRICE_CAP
                if mimo_v25_pro.model == DIRECT_MIMO_PRICE_CAP.model
                else price_cap_from_environment(
                    environment,
                    model=mimo_v25_pro.model,
                    environment_prefix="MIMO_V25_PRO",
                )
            )
            luna_price = price_cap_from_environment(
                environment,
                model=luna.model,
                environment_prefix="LUNA",
            )
        except ValueError as exc:
            raise ProviderConfigurationError(str(exc)) from exc
        return cls(
            mimo_v25=mimo_v25,
            mimo_v25_pro=mimo_v25_pro,
            luna=luna,
            mimo_v25_price_cap=normal_price,
            mimo_v25_pro_price_cap=pro_price,
            luna_price_cap=luna_price,
            repository_revision=repository_revision,
        )

    def preflight(self) -> V2RoutingPreflight:
        """Verify all enabled target stages resolve before any provider work starts."""
        if self.stage_models is not None:
            return V2RoutingPreflight(
                routing=tuple((item.stage, item.route) for item in self.stage_configurations)
            )
        routes = tuple(
            (stage, self.route_for_alias(V2_LLM_ROUTING.for_stage(stage))) for stage in LLMStage
        )
        return V2RoutingPreflight(routing=routes)

    def route_for_alias(self, stage_route: StageRoute) -> V2PhysicalModelRoute:
        if self.stage_models is not None:
            raise ProviderConfigurationError("selected routes must be resolved by stage")
        alias = stage_route.primary
        if alias is ModelAlias.MIMO_V25:
            assert self.mimo_v25 is not None and self.mimo_v25_price_cap is not None
            return _mimo_route(alias, self.mimo_v25, self.mimo_v25_price_cap)
        if alias is ModelAlias.MIMO_V25_PRO:
            assert self.mimo_v25_pro is not None and self.mimo_v25_pro_price_cap is not None
            return _mimo_route(alias, self.mimo_v25_pro, self.mimo_v25_pro_price_cap)
        if alias is ModelAlias.GPT_5_6_LUNA_HIGH:
            assert self.luna is not None and self.luna_price_cap is not None
            return V2PhysicalModelRoute(
                logical_alias=alias,
                provider_name=self.luna.provider_name,
                adapter_version=self.luna.adapter_version,
                base_url=self.luna.base_url,
                physical_model=self.luna.model,
                max_completion_tokens=self.luna.max_completion_tokens,
                price_cap=self.luna_price_cap,
            )
        raise ProviderConfigurationError(f"unsupported v2 logical model alias: {alias.value}")

    def configuration_for_stage(self, stage: LLMStage) -> V2StageConfiguration:
        for item in self.stage_configurations:
            if item.stage is stage:
                return item
        raise ProviderConfigurationError(f"no selected adapter for {stage.value}")

    def fingerprint_payload(self) -> dict[str, str]:
        """Return canonical contract fields without serializing credentials."""
        preflight = self.preflight()
        route_json = json.dumps(
            [
                {
                    "stage": stage.value,
                    **route.model_dump(mode="json"),
                }
                for stage, route in preflight.routing
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        routing_json = json.dumps(
            (
                self.stage_models.model_dump(mode="json")
                if self.stage_models is not None
                else {
                    stage.value: V2_LLM_ROUTING.for_stage(stage).model_dump(mode="json")
                    for stage in LLMStage
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        prompt_json = json.dumps(
            {
                stage.value: {
                    "version": load_prompt(stage).version,
                    "sha256": load_prompt(stage).sha256,
                }
                for stage in LLMStage
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "fingerprint_version": V2_ROUTING_FINGERPRINT_VERSION,
            "provider_identity": "|".join(
                f"{stage.value}:{route.provider_name}:{route.base_url}"
                for stage, route in preflight.routing
            ),
            "adapter_identity": "|".join(
                f"{stage.value}:{route.adapter_version}" for stage, route in preflight.routing
            ),
            "model_identity": "|".join(
                f"{stage.value}:{route.logical_alias.value}:{route.physical_model}"
                for stage, route in preflight.routing
            ),
            "prompt_identity": (
                f"{V2_ROUTING_PROMPT_VERSION}|{sha256(prompt_json.encode()).hexdigest()}"
            ),
            "schema_identity": V2_ROUTING_SCHEMA_VERSION,
            "normalization_identity": "v2-routing-unwired",
            "policy_identity": (
                f"{V2_ROUTING_POLICY_VERSION}|routing:{sha256(routing_json.encode()).hexdigest()}"
                f"|routes:{sha256(route_json.encode()).hexdigest()}"
            ),
            "repository_revision": self.repository_revision,
        }

    def contract(self, run_id: UUID, created_at: datetime) -> ProviderRunContract:
        """Build the immutable, secret-free provider contract for a fresh v2 run."""
        payload_json = canonical_provider_contract_payload(self.fingerprint_payload())
        payload = self.fingerprint_payload()
        return ProviderRunContract(
            run_id=run_id,
            fingerprint_sha256=sha256(payload_json.encode("utf-8")).hexdigest(),
            provider_identity=payload["provider_identity"],
            adapter_identity=payload["adapter_identity"],
            model_identity=payload["model_identity"],
            prompt_identity=payload["prompt_identity"],
            schema_identity=payload["schema_identity"],
            normalization_identity=payload["normalization_identity"],
            policy_identity=payload["policy_identity"],
            repository_revision=self.repository_revision,
            payload_json=payload_json,
            created_at=created_at,
        )


def _mimo_route(
    alias: ModelAlias,
    config: MimoRouteConfig,
    price_cap: ModelPriceCap,
) -> V2PhysicalModelRoute:
    return V2PhysicalModelRoute(
        logical_alias=alias,
        provider_name=config.provider_name,
        adapter_version=config.adapter_version,
        base_url=config.base_url,
        physical_model=config.model,
        max_completion_tokens=config.max_completion_tokens,
        price_cap=price_cap,
    )


def _selected_stage_configurations(
    environment: Mapping[str, str], stage_models: StageModelSelections
) -> tuple[V2StageConfiguration, ...]:
    selected = tuple(option_for(stage_models.for_stage(stage)) for stage in ACTIVE_MODEL_STAGES)
    needs_openai = any(option.provider == "openai" for option in selected)
    needs_mimo = any(option.provider == "mimo" for option in selected)
    openai_key = environment.get("LUNA_API_KEY", "").strip()
    mimo_key = environment.get("MIMO_API_KEY", "").strip()
    if needs_openai and not openai_key:
        raise ProviderConfigurationError("OpenAI API key is required by the selected model steps")
    if needs_mimo and not mimo_key:
        raise ProviderConfigurationError("MiMo API key is required by the selected model steps")
    if (
        needs_openai
        and environment.get("LUNA_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        != "https://api.openai.com/v1"
    ):
        raise ProviderConfigurationError("Selected OpenAI models require the official API endpoint")
    if (
        needs_mimo
        and environment.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
        != "https://api.xiaomimimo.com/v1"
    ):
        raise ProviderConfigurationError("Selected MiMo models require the official API endpoint")
    if needs_openai and environment.get("LUNA_MODEL", "gpt-5.6-luna") != "gpt-5.6-luna":
        raise ProviderConfigurationError("Restore the standard OpenAI model override first")
    configurations: list[V2StageConfiguration] = []
    for stage, option in zip(ACTIVE_MODEL_STAGES, selected, strict=True):
        allowance = completion_limit_for(stage)
        price_cap = ModelPriceCap(
            model=option.model,
            input_usd_per_token=option.input_cap_per_million / Decimal(1_000_000),
            output_usd_per_token=option.output_cap_per_million / Decimal(1_000_000),
        )
        if option.provider == "openai":
            config: MimoChoiceConfig | OpenAIChoiceConfig = OpenAIChoiceConfig(
                api_key=SecretStr(openai_key),
                model=option.model,
                max_completion_tokens=allowance,
            )
        else:
            config = MimoChoiceConfig(
                api_key=SecretStr(mimo_key),
                model=option.model,
                max_completion_tokens=allowance,
            )
        route = V2PhysicalModelRoute(
            logical_alias=ModelAlias(option.id.value),
            provider_name=config.provider_name,
            adapter_version=config.adapter_version,
            base_url=config.base_url,
            physical_model=option.model,
            max_completion_tokens=allowance,
            price_cap=price_cap,
        )
        configurations.append(V2StageConfiguration(stage=stage, route=route, config=config))
    return tuple(configurations)
