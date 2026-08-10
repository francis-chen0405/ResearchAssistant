"""Strict MVP-3A construction boundary for the approved provider stack.

Thread strategy: immutable configuration and thread-safe ``httpx.Client`` instances are
shared. Wigolo Search locks its one health-state mutation, OpenRouter stores request
metadata in thread-local state, acquisition keeps no mutable request state, and the
orchestrator continues to use short-lived worker-local SQLite connections.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID

import httpx
from pydantic import ConfigDict, Field, model_validator

from agents.analyst import AnalystLLMInput
from agents.researcher import EVIDENCE_POLICY_VERSION
from agents.reviewer import ReviewerDecision
from agents.supportingresearcher import MVP3A_ACQUISITION_POLICY, AcquisitionPolicy
from agents.synthesizer import SynthesizerLLMInput
from models import (
    PlannerOutput,
    ProviderRunContract,
    ProvisionalCandidate,
    ScoreDecision,
    StatementDraft,
    StrictModel,
    SynthesisOutput,
)
from provider_contract import canonical_provider_contract_payload, parse_provider_contract_payload
from providers.acquisition import ACQUISITION_VERSION, WigoloAcquisitionAdapter
from providers.config import OpenRouterConfig, ProviderConfigurationError, RunCeilings, WigoloConfig
from providers.llm import DEFAULT_LLM_ROUTING, LLMStage, ModelAlias, load_prompt
from providers.normalization import NORMALIZATION_VERSION, PDF_POLICY_VERSION
from providers.openrouter import OpenRouterAdapter
from providers.pricing import DEFAULT_PRICE_CAPS, PRICING_POLICY_VERSION, ModelPriceCap
from providers.wigolo import WigoloSearchAdapter

PROVIDER_FACTORY_VERSION = "mvp3a-provider-factory-v1"
RETRY_POLICY_VERSION = "mvp3a-objective-retry-v1"
BUDGET_POLICY_VERSION = "mvp6.8-exact-decimal-reserve-reconcile-v1"
FINGERPRINT_VERSION = "mvp6.9-acquisition-configuration-integrity-v1"


class ApprovedRoleMapping(StrictModel):
    """The sole model mapping approved for MVP-3A."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planner_primary: Literal[ModelAlias.MIMO_V25_PRO] = ModelAlias.MIMO_V25_PRO
    extractor_primary: Literal[ModelAlias.MIMO_V25_PRO] = ModelAlias.MIMO_V25_PRO
    analyst_primary: Literal[ModelAlias.MIMO_V25_PRO] = ModelAlias.MIMO_V25_PRO
    reviewer_primary: Literal[ModelAlias.MIMO_V25_PRO] = ModelAlias.MIMO_V25_PRO
    synthesizer_primary: Literal[ModelAlias.MIMO_V25_PRO] = ModelAlias.MIMO_V25_PRO
    sole_fallback: Literal[ModelAlias.MINIMAX_M3] = ModelAlias.MINIMAX_M3


class RequiredProviderCapabilities(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    structured_output: Literal[True] = True
    temperature: Literal[True] = True
    usage: Literal[True] = True
    pricing: Literal[True] = True


class ProviderFactoryConfig(StrictModel):
    """Immutable, secret-safe configuration validated before a run is created."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    wigolo: WigoloConfig = WigoloConfig()
    openrouter: OpenRouterConfig
    ceilings: RunCeilings = RunCeilings()
    acquisition: AcquisitionPolicy = MVP3A_ACQUISITION_POLICY
    roles: ApprovedRoleMapping = ApprovedRoleMapping()
    required_capabilities: RequiredProviderCapabilities = RequiredProviderCapabilities()
    repository_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exact_approved_stack(self) -> ProviderFactoryConfig:
        if self.wigolo.provider_name != "wigolo" or self.wigolo.provider_version != "0.2.1":
            raise ValueError("MVP-3A requires Wigolo 0.2.1")
        if self.openrouter.provider_name != "openrouter":
            raise ValueError("MVP-3A requires OpenRouter")
        if self.openrouter.primary_model != "xiaomi/mimo-v2.5-pro":
            raise ValueError("MVP-3A primary model must be xiaomi/mimo-v2.5-pro")
        if self.openrouter.fallback_model != "minimax/minimax-m3":
            raise ValueError("MVP-3A fallback model must be minimax/minimax-m3")
        if self.acquisition != MVP3A_ACQUISITION_POLICY:
            raise ValueError("MVP-3A requires rank-five/keep-three acquisition")
        for stage in LLMStage:
            route = DEFAULT_LLM_ROUTING.for_stage(stage)
            if route.primary is not ModelAlias.MIMO_V25_PRO:
                raise ValueError(f"{stage.value} primary route is not approved")
            if route.fallbacks != (ModelAlias.MINIMAX_M3,):
                raise ValueError(f"{stage.value} fallback route is not approved")
            if route.generation.temperature is None:
                raise ValueError(f"{stage.value} requires an explicit temperature")
            if not route.generation.use_structured_output_control:
                raise ValueError(f"{stage.value} requires strict structured output")
        return self

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        repository_revision: str,
        wigolo: WigoloConfig | None = None,
    ) -> ProviderFactoryConfig:
        return cls(
            wigolo=wigolo or WigoloConfig(),
            openrouter=OpenRouterConfig.from_environment(environment),
            repository_revision=repository_revision,
        )


class ProviderFactoryClients(StrictModel):
    """Optional injected clients used by offline mocked integration tests."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    search: httpx.Client | None = None
    source: httpx.Client | None = None
    acquisition: httpx.Client | None = None
    fallback_acquisition: httpx.Client | None = None
    llm: httpx.Client | None = None
    health_verified: bool = False
    host_resolver: Callable[[str], Sequence[str]] | None = None


class ProviderBundle(StrictModel):
    """Constructed approved adapters plus immutable compatibility identity."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    config: ProviderFactoryConfig
    search: WigoloSearchAdapter
    acquisition: WigoloAcquisitionAdapter
    llm: OpenRouterAdapter
    fingerprint_payload_json: str
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def contract(self, run_id: UUID, created_at: datetime) -> ProviderRunContract:
        payload = parse_provider_contract_payload(self.fingerprint_payload_json)
        return ProviderRunContract(
            run_id=run_id,
            fingerprint_sha256=self.fingerprint_sha256,
            provider_identity=payload["provider_identity"],
            adapter_identity=payload["adapter_identity"],
            model_identity=payload["model_identity"],
            prompt_identity=payload["prompt_identity"],
            schema_identity=payload["schema_identity"],
            normalization_identity=payload["normalization_identity"],
            policy_identity=payload["policy_identity"],
            repository_revision=self.config.repository_revision,
            payload_json=self.fingerprint_payload_json,
            created_at=created_at,
        )


def build_provider_bundle(
    config: ProviderFactoryConfig,
    *,
    clients: ProviderFactoryClients | None = None,
    price_caps: Mapping[str, ModelPriceCap] | None = None,
) -> ProviderBundle:
    """Validate and construct only Wigolo and OpenRouter adapters."""
    if not isinstance(config, ProviderFactoryConfig):
        raise TypeError("provider factory requires ProviderFactoryConfig")
    injected = clients or ProviderFactoryClients()
    caps = dict(DEFAULT_PRICE_CAPS if price_caps is None else price_caps)
    expected_models = {config.openrouter.primary_model, config.openrouter.fallback_model}
    if set(caps) != expected_models or any(cap.model != model for model, cap in caps.items()):
        raise ProviderConfigurationError(
            "pricing must cover exactly the approved primary and fallback routes"
        )
    search = WigoloSearchAdapter(
        config.wigolo,
        client=injected.search,
        health_verified=injected.health_verified,
    )
    acquisition = WigoloAcquisitionAdapter(
        config.wigolo,
        source_client=injected.source,
        wigolo_client=injected.acquisition,
        host_resolver=injected.host_resolver,
    )
    llm = OpenRouterAdapter(
        config.openrouter,
        client=injected.llm,
        price_caps=caps,
        max_call_cost_usd=config.ceilings.max_cost_usd,
        max_call_tokens=config.ceilings.max_tokens,
    )
    capabilities = llm.capabilities
    if not capabilities.supports_temperature:
        raise ProviderConfigurationError("OpenRouter adapter must support temperature")
    if not capabilities.supports_structured_output_control:
        raise ProviderConfigurationError("OpenRouter adapter must support structured output")
    if not callable(getattr(llm, "usage_for", None)):
        raise ProviderConfigurationError("OpenRouter adapter must expose exact usage")
    payload = _fingerprint_payload(config, caps)
    payload_json = canonical_provider_contract_payload(payload)
    return ProviderBundle(
        config=config,
        search=search,
        acquisition=acquisition,
        llm=llm,
        fingerprint_payload_json=payload_json,
        fingerprint_sha256=sha256(payload_json.encode("utf-8")).hexdigest(),
    )


def _fingerprint_payload(
    config: ProviderFactoryConfig,
    caps: Mapping[str, ModelPriceCap],
) -> dict[str, str]:
    prompts = {stage.value: load_prompt(stage).sha256 for stage in LLMStage}
    schemas = (
        PlannerOutput,
        ProvisionalCandidate,
        ScoreDecision,
        StatementDraft,
        ReviewerDecision,
        SynthesisOutput,
        AnalystLLMInput,
        SynthesizerLLMInput,
    )
    schema_json = json.dumps(
        {item.__name__: item.model_json_schema() for item in schemas},
        sort_keys=True,
        separators=(",", ":"),
    )
    pricing_json = json.dumps(
        {model: cap.model_dump(mode="json") for model, cap in sorted(caps.items())},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "fingerprint_version": FINGERPRINT_VERSION,
        "provider_identity": (
            f"wigolo:{config.wigolo.provider_version}|openrouter:{config.openrouter.base_url}"
        ),
        "adapter_identity": (
            f"{config.wigolo.adapter_version}|{config.openrouter.adapter_version}|"
            f"{PROVIDER_FACTORY_VERSION}"
        ),
        "model_identity": (f"{config.openrouter.primary_model}|{config.openrouter.fallback_model}"),
        "prompt_identity": sha256(json.dumps(prompts, sort_keys=True).encode("utf-8")).hexdigest(),
        "schema_identity": sha256(schema_json.encode("utf-8")).hexdigest(),
        "normalization_identity": (
            f"{NORMALIZATION_VERSION}|{PDF_POLICY_VERSION}|{ACQUISITION_VERSION}"
        ),
        "policy_identity": (
            f"{RETRY_POLICY_VERSION}|{BUDGET_POLICY_VERSION}|{PRICING_POLICY_VERSION}|"
            f"{sha256(pricing_json.encode('utf-8')).hexdigest()}|rank5-keep3|"
            f"{EVIDENCE_POLICY_VERSION}"
        ),
        "repository_revision": config.repository_revision,
    }


def secret_safe_configuration_error(exc: Exception) -> ProviderConfigurationError:
    """Normalize construction errors without ever embedding a supplied secret."""
    return ProviderConfigurationError(f"provider configuration is invalid: {type(exc).__name__}")
