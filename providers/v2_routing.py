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

from pydantic import ConfigDict, Field, model_validator

from models import ProviderRunContract, StrictModel
from provider_contract import canonical_provider_contract_payload
from providers.config import LunaConfig, MimoRouteConfig, ProviderConfigurationError
from providers.llm import V2_LLM_ROUTING, LLMStage, ModelAlias, StageRoute, load_prompt
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
        if set(stages) != set(LLMStage):
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

    mimo_v25: MimoRouteConfig
    mimo_v25_pro: MimoRouteConfig
    luna: LunaConfig
    mimo_v25_price_cap: ModelPriceCap
    mimo_v25_pro_price_cap: ModelPriceCap
    luna_price_cap: ModelPriceCap
    repository_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_routes(self) -> V2RoutingConfig:
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
    ) -> V2RoutingConfig:
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
        routes = tuple(
            (stage, self.route_for_alias(V2_LLM_ROUTING.for_stage(stage))) for stage in LLMStage
        )
        return V2RoutingPreflight(routing=routes)

    def route_for_alias(self, stage_route: StageRoute) -> V2PhysicalModelRoute:
        alias = stage_route.primary
        if alias is ModelAlias.MIMO_V25:
            return _mimo_route(alias, self.mimo_v25, self.mimo_v25_price_cap)
        if alias is ModelAlias.MIMO_V25_PRO:
            return _mimo_route(alias, self.mimo_v25_pro, self.mimo_v25_pro_price_cap)
        if alias is ModelAlias.GPT_5_6_LUNA_HIGH:
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
            {
                stage.value: V2_LLM_ROUTING.for_stage(stage).model_dump(mode="json")
                for stage in LLMStage
            },
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
