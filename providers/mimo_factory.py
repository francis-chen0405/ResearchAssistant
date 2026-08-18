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
from agents.supportingresearcher import AcquisitionPolicy
from agents.synthesizer import SynthesizerLLMInput
from models import (
    DEFAULT_RESEARCH_CONTROLS,
    DiscoveryProvider,
    PlannerOutput,
    ProviderRunContract,
    ProvisionalCandidate,
    ResearchControls,
    ResearchDepth,
    ScoreDecision,
    StatementDraft,
    StrictModel,
    SynthesisOutput,
    VerbatimQuoteSelection,
)
from provider_contract import canonical_provider_contract_payload, parse_provider_contract_payload
from providers.acquisition import ACQUISITION_VERSION, WigoloAcquisitionAdapter
from providers.clients import ProviderClients
from providers.composite_search import CompositeSearchProvider
from providers.config import (
    ExaConfig,
    FirecrawlConfig,
    MimoConfig,
    OpenAlexConfig,
    RunCeilings,
    SerpSearchConfig,
    WigoloConfig,
)
from providers.exa import ExaSearchAdapter
from providers.firecrawl import FallbackAcquisitionAdapter, FirecrawlAcquisitionAdapter
from providers.llm import DIRECT_MIMO_ROUTING, LLMStage, ModelAlias, load_prompt
from providers.mimo import XiaomiMimoAdapter
from providers.normalization import NORMALIZATION_VERSION, PDF_POLICY_VERSION
from providers.openalex import OpenAlexSearchAdapter
from providers.pricing import (
    DIRECT_MIMO_PRICE_CAP,
    DIRECT_MIMO_PRICING_POLICY_VERSION,
    ModelPriceCap,
)
from providers.ranking import DISCOVERY_POLICY_VERSION
from providers.serpsearch import SerpSearchAdapter

MIMO_FACTORY_VERSION = "mlp5-provider-selection-factory-v1"
MIMO_RETRY_POLICY_VERSION = "mvp9-nonretryable-exact-selection-v1"
MIMO_BUDGET_POLICY_VERSION = "mvp6.8-exact-decimal-reserve-reconcile-v1"
MIMO_FINGERPRINT_VERSION = "mlp5-provider-selection-v1"
RESEARCH_GOVERNOR_POLICY_VERSION = "mvp11-research-governor-v1"
MLP4_DEFAULT_ACQUISITION = AcquisitionPolicy(
    discovery_results_per_query=10,
    usable_snapshots_per_query=10,
    source_target_per_stance=10,
)


class MimoProviderFactoryConfig(StrictModel):
    """Immutable direct-MiMo configuration validated before a run exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    wigolo: WigoloConfig = WigoloConfig()
    exa: ExaConfig | None = None
    openalex: OpenAlexConfig | None = None
    serpsearch: SerpSearchConfig | None = None
    firecrawl: FirecrawlConfig | None = None
    mimo: MimoConfig
    ceilings: RunCeilings = RunCeilings()
    acquisition: AcquisitionPolicy = MLP4_DEFAULT_ACQUISITION
    research_controls: ResearchControls = DEFAULT_RESEARCH_CONTROLS
    repository_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exact_route(self) -> MimoProviderFactoryConfig:
        if self.wigolo.provider_name != "wigolo" or self.wigolo.provider_version != "0.2.1":
            raise ValueError("MVP-3B requires Wigolo 0.2.1")
        enabled = set(self.research_controls.discovery_providers)
        if (DiscoveryProvider.EXA in enabled) != (self.exa is not None):
            raise ValueError("Exa configuration must match the selected discovery providers")
        if self.exa is not None and (
            self.exa.provider_name != "exa" or self.exa.search_type != "auto"
        ):
            raise ValueError("new live runs require Exa auto discovery")
        if (DiscoveryProvider.OPENALEX in enabled) != (self.openalex is not None):
            raise ValueError("OpenAlex configuration must match the selected discovery providers")
        if self.openalex is not None and self.openalex.provider_name != "openalex":
            raise ValueError("MLP-4 requires the OpenAlex Works API")
        if (DiscoveryProvider.SERPSEARCH in enabled) != (self.serpsearch is not None):
            raise ValueError(
                "SERP Search configuration must match the selected discovery providers"
            )
        if self.serpsearch is not None and self.serpsearch.provider_name != "serpsearch":
            raise ValueError("SERP Search requires the Google Search API")
        if self.mimo.provider_name != "xiaomi-mimo" or self.mimo.model != "mimo-v2.5-pro":
            raise ValueError("MVP-3B requires direct Xiaomi mimo-v2.5-pro")
        if self.acquisition != _acquisition_for_controls(self.research_controls):
            raise ValueError("acquisition policy must exactly match research depth")
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
        research_controls: ResearchControls = DEFAULT_RESEARCH_CONTROLS,
    ) -> MimoProviderFactoryConfig:
        mimo = MimoConfig.from_environment(environment)
        enabled = set(research_controls.discovery_providers)
        exa = ExaConfig.from_environment(environment) if DiscoveryProvider.EXA in enabled else None
        openalex = (
            OpenAlexConfig.from_environment(environment)
            if DiscoveryProvider.OPENALEX in enabled
            else None
        )
        serpsearch = (
            SerpSearchConfig.from_environment(environment)
            if DiscoveryProvider.SERPSEARCH in enabled
            else None
        )
        return cls(
            wigolo=wigolo or WigoloConfig(),
            exa=exa,
            openalex=openalex,
            serpsearch=serpsearch,
            firecrawl=FirecrawlConfig.from_environment(environment),
            mimo=mimo,
            ceilings=ceilings or RunCeilings(),
            acquisition=_acquisition_for_controls(research_controls),
            research_controls=research_controls,
            repository_revision=repository_revision,
        )


class MimoProviderBundle(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    config: MimoProviderFactoryConfig
    search: CompositeSearchProvider
    acquisition: FallbackAcquisitionAdapter
    llm: XiaomiMimoAdapter
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


def build_mimo_provider_bundle(
    config: MimoProviderFactoryConfig,
    *,
    clients: ProviderClients | None = None,
    price_cap: ModelPriceCap = DIRECT_MIMO_PRICE_CAP,
) -> MimoProviderBundle:
    if not isinstance(config, MimoProviderFactoryConfig):
        raise TypeError("direct MiMo factory requires MimoProviderFactoryConfig")
    injected = clients or ProviderClients()
    search = CompositeSearchProvider(
        exa=(ExaSearchAdapter(config.exa, client=injected.search) if config.exa else None),
        openalex=(
            OpenAlexSearchAdapter(config.openalex, client=injected.openalex_search)
            if config.openalex
            else None
        ),
        serpsearch=(
            SerpSearchAdapter(config.serpsearch, client=injected.serpsearch)
            if config.serpsearch
            else None
        ),
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
    payload_json = canonical_provider_contract_payload(payload)
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
        VerbatimQuoteSelection,
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
            "exa": (
                config.exa.model_dump(mode="json", exclude={"api_key"})
                if config.exa is not None
                else {"enabled": False}
            ),
            "openalex": (
                config.openalex.model_dump(mode="json", exclude={"api_key"})
                if config.openalex is not None
                else {"enabled": False}
            ),
            "serpsearch": (
                config.serpsearch.model_dump(mode="json", exclude={"api_key"})
                if config.serpsearch is not None
                else {"enabled": False}
            ),
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
            "research_controls": config.research_controls.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "fingerprint_version": MIMO_FINGERPRINT_VERSION,
        "provider_identity": (
            f"exa:{config.exa.base_url if config.exa else 'disabled'}|"
            f"serpsearch:{config.serpsearch.base_url if config.serpsearch else 'disabled'}|"
            f"wigolo:{config.wigolo.provider_version}|"
            f"openalex:{config.openalex.base_url if config.openalex else 'disabled'}|"
            f"firecrawl:{config.firecrawl.base_url if config.firecrawl else 'disabled'}|"
            f"xiaomi-mimo:{config.mimo.base_url}"
        ),
        "adapter_identity": (
            f"{config.exa.adapter_version if config.exa else 'exa-disabled'}|"
            f"{config.serpsearch.adapter_version if config.serpsearch else 'serpsearch-disabled'}|"
            f"{config.wigolo.adapter_version}|"
            f"{config.openalex.adapter_version if config.openalex else 'openalex-disabled'}|"
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
            f"{sha256(operational_policy_json.encode('utf-8')).hexdigest()}"
            f"|controls:{config.research_controls.canonical_json()}"
            f"|{EVIDENCE_POLICY_VERSION}|{DISCOVERY_POLICY_VERSION}"
            f"|{RESEARCH_GOVERNOR_POLICY_VERSION}"
        ),
        "repository_revision": config.repository_revision,
    }


def _acquisition_for_controls(controls: ResearchControls) -> AcquisitionPolicy:
    """Use one ranked provider pool and the operator's bounded top-N target."""
    if controls.depth not in {ResearchDepth.FOCUSED, ResearchDepth.STANDARD}:
        raise ValueError(f"unsupported research depth: {controls.depth!r}")
    return AcquisitionPolicy(
        discovery_results_per_query=10,
        usable_snapshots_per_query=10,
        source_target_per_stance=controls.sources_per_stance_per_round,
    )
