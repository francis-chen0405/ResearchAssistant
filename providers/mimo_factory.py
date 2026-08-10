"""Strict MVP-3B factory for Wigolo plus direct Xiaomi MiMo."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from uuid import UUID

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
from providers.acquisition import ACQUISITION_VERSION, WigoloAcquisitionAdapter
from providers.config import ExaConfig, FirecrawlConfig, MimoConfig, RunCeilings, WigoloConfig
from providers.exa import ExaSearchAdapter
from providers.factory import ProviderFactoryClients
from providers.firecrawl import FallbackAcquisitionAdapter, FirecrawlAcquisitionAdapter
from providers.llm import DIRECT_MIMO_ROUTING, LLMStage, ModelAlias, load_prompt
from providers.mimo import XiaomiMimoAdapter
from providers.normalization import NORMALIZATION_VERSION, PDF_POLICY_VERSION
from providers.pricing import (
    DIRECT_MIMO_PRICE_CAP,
    DIRECT_MIMO_PRICING_POLICY_VERSION,
    ModelPriceCap,
)

MIMO_FACTORY_VERSION = "mvp3b-direct-mimo-factory-v1"
MIMO_RETRY_POLICY_VERSION = "mvp3b-direct-mimo-one-retry-v1"
MIMO_BUDGET_POLICY_VERSION = "mvp3b-direct-mimo-reserve-reconcile-v1"
MIMO_FINGERPRINT_VERSION = "mvp6.3-public-acquisition-fingerprint-v2"


class MimoProviderFactoryConfig(StrictModel):
    """Immutable direct-MiMo configuration validated before a run exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    wigolo: WigoloConfig = WigoloConfig()
    exa: ExaConfig
    firecrawl: FirecrawlConfig | None = None
    mimo: MimoConfig
    ceilings: RunCeilings = RunCeilings()
    acquisition: AcquisitionPolicy = MVP3A_ACQUISITION_POLICY
    repository_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exact_route(self) -> MimoProviderFactoryConfig:
        if self.wigolo.provider_name != "wigolo" or self.wigolo.provider_version != "0.2.1":
            raise ValueError("MVP-3B requires Wigolo 0.2.1")
        if self.exa.provider_name != "exa" or self.exa.search_type != "auto":
            raise ValueError("new live runs require Exa auto discovery")
        if self.mimo.provider_name != "xiaomi-mimo" or self.mimo.model != "mimo-v2.5-pro":
            raise ValueError("MVP-3B requires direct Xiaomi mimo-v2.5-pro")
        if self.acquisition != MVP3A_ACQUISITION_POLICY:
            raise ValueError("MVP-3B requires rank-five/keep-three acquisition")
        for stage in LLMStage:
            route = DIRECT_MIMO_ROUTING.for_stage(stage)
            if route.primary is not ModelAlias.MIMO_V25_PRO or route.fallbacks:
                raise ValueError(f"{stage.value} must use only direct MiMo Pro")
        return self

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        repository_revision: str,
        wigolo: WigoloConfig | None = None,
        ceilings: RunCeilings | None = None,
    ) -> MimoProviderFactoryConfig:
        mimo = MimoConfig.from_environment(environment)
        exa = ExaConfig.from_environment(environment)
        return cls(
            wigolo=wigolo or WigoloConfig(),
            exa=exa,
            firecrawl=FirecrawlConfig.from_environment(environment),
            mimo=mimo,
            ceilings=ceilings or RunCeilings(),
            repository_revision=repository_revision,
        )


class MimoProviderBundle(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    config: MimoProviderFactoryConfig
    search: ExaSearchAdapter
    acquisition: FallbackAcquisitionAdapter
    llm: XiaomiMimoAdapter
    fingerprint_payload_json: str
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def contract(self, run_id: UUID, created_at: datetime) -> ProviderRunContract:
        payload = json.loads(self.fingerprint_payload_json)
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


def build_mimo_provider_bundle(
    config: MimoProviderFactoryConfig,
    *,
    clients: ProviderFactoryClients | None = None,
    price_cap: ModelPriceCap = DIRECT_MIMO_PRICE_CAP,
) -> MimoProviderBundle:
    if not isinstance(config, MimoProviderFactoryConfig):
        raise TypeError("direct MiMo factory requires MimoProviderFactoryConfig")
    injected = clients or ProviderFactoryClients()
    search = ExaSearchAdapter(
        config.exa,
        client=injected.search,
    )
    primary_acquisition = WigoloAcquisitionAdapter(
        config.wigolo,
        source_client=injected.source,
        wigolo_client=injected.acquisition,
        host_resolver=injected.host_resolver,
    )
    fallback = (
        FirecrawlAcquisitionAdapter(
            config.firecrawl,
            client=injected.fallback_acquisition,
            host_resolver=injected.host_resolver,
        )
        if config.firecrawl is not None
        else None
    )
    acquisition = FallbackAcquisitionAdapter(primary=primary_acquisition, fallback=fallback)
    llm = XiaomiMimoAdapter(
        config.mimo,
        client=injected.llm,
        price_cap=price_cap,
        max_call_cost_usd=config.ceilings.max_cost_usd,
        max_call_tokens=config.ceilings.max_tokens,
    )
    payload = _fingerprint_payload(config, price_cap)
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return MimoProviderBundle(
        config=config,
        search=search,
        acquisition=acquisition,
        llm=llm,
        fingerprint_payload_json=payload_json,
        fingerprint_sha256=sha256(payload_json.encode("utf-8")).hexdigest(),
    )


def _fingerprint_payload(
    config: MimoProviderFactoryConfig,
    price_cap: ModelPriceCap,
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
    pricing_json = price_cap.model_dump_json()
    operational_policy_json = json.dumps(
        {
            "wigolo": config.wigolo.model_dump(mode="json"),
            "exa": config.exa.model_dump(mode="json", exclude={"api_key"}),
            "firecrawl": (
                config.firecrawl.model_dump(mode="json", exclude={"api_key"})
                if config.firecrawl is not None
                else {"enabled": False}
            ),
            "mimo": {
                "max_completion_tokens": config.mimo.max_completion_tokens,
                "deadlines": config.mimo.deadlines.model_dump(mode="json"),
            },
            "ceilings": config.ceilings.model_dump(mode="json"),
            "acquisition": config.acquisition.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "fingerprint_version": MIMO_FINGERPRINT_VERSION,
        "provider_identity": (
            f"exa:{config.exa.base_url}|wigolo:{config.wigolo.provider_version}|"
            f"firecrawl:{config.firecrawl.base_url if config.firecrawl else 'disabled'}|"
            f"xiaomi-mimo:{config.mimo.base_url}"
        ),
        "adapter_identity": (
            f"{config.exa.adapter_version}|{config.wigolo.adapter_version}|"
            f"{config.firecrawl.adapter_version if config.firecrawl else 'firecrawl-disabled'}|"
            f"{config.mimo.adapter_version}|{MIMO_FACTORY_VERSION}"
        ),
        "model_identity": config.mimo.model,
        "prompt_identity": sha256(json.dumps(prompts, sort_keys=True).encode("utf-8")).hexdigest(),
        "schema_identity": sha256(schema_json.encode("utf-8")).hexdigest(),
        "normalization_identity": (
            f"{NORMALIZATION_VERSION}|{PDF_POLICY_VERSION}|{ACQUISITION_VERSION}"
        ),
        "policy_identity": (
            f"{MIMO_RETRY_POLICY_VERSION}|{MIMO_BUDGET_POLICY_VERSION}|"
            f"{DIRECT_MIMO_PRICING_POLICY_VERSION}|"
            f"{sha256(pricing_json.encode('utf-8')).hexdigest()}|"
            f"{sha256(operational_policy_json.encode('utf-8')).hexdigest()}|rank5-keep3"
            f"|{EVIDENCE_POLICY_VERSION}"
        ),
        "repository_revision": config.repository_revision,
    }
