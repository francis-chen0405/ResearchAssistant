"""Production provider construction for fresh ResearchAssistant v2 runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from pydantic import ConfigDict, model_validator

from models import DiscoveryProvider, StrictModel
from providers.acquisition import WigoloAcquisitionAdapter
from providers.clients import ProviderClients
from providers.composite_search import CompositeSearchProvider
from providers.config import (
    ExaConfig,
    FirecrawlConfig,
    OpenAlexConfig,
    SerpSearchConfig,
    WigoloConfig,
)
from providers.exa import ExaSearchAdapter
from providers.firecrawl import FirecrawlAcquisitionAdapter
from providers.llm import ModelAlias
from providers.mimo import XiaomiMimoAdapter
from providers.openalex import OpenAlexSearchAdapter
from providers.scraper import ScraperProvider
from providers.search import SearchProvider
from providers.serpsearch import SerpSearchAdapter
from providers.v2_budget import RoutedV2LLMProvider, V2RunCeilings
from providers.v2_routing import V2RoutingConfig


class V2ProductionFactoryConfig(StrictModel):
    """Validated, immutable fresh-v2 provider configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    routing: V2RoutingConfig
    ceilings: V2RunCeilings = V2RunCeilings()
    discovery_providers: tuple[DiscoveryProvider, ...]
    wigolo: WigoloConfig = WigoloConfig()
    exa: ExaConfig | None = None
    openalex: OpenAlexConfig | None = None
    serpsearch: SerpSearchConfig | None = None
    firecrawl: FirecrawlConfig | None = None

    @model_validator(mode="after")
    def validate_discovery_routes(self) -> V2ProductionFactoryConfig:
        enabled = set(self.discovery_providers)
        if not enabled or len(enabled) != len(self.discovery_providers):
            raise ValueError("fresh v2 discovery providers must be unique and non-empty")
        configured = {
            provider
            for provider, value in (
                (DiscoveryProvider.EXA, self.exa),
                (DiscoveryProvider.OPENALEX, self.openalex),
                (DiscoveryProvider.SERPSEARCH, self.serpsearch),
            )
            if value is not None
        }
        if configured != enabled:
            raise ValueError("fresh v2 discovery configuration must match enabled providers")
        return self

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        repository_revision: str,
        discovery_providers: tuple[DiscoveryProvider, ...],
        ceilings: V2RunCeilings | None = None,
        wigolo: WigoloConfig | None = None,
    ) -> V2ProductionFactoryConfig:
        enabled = set(discovery_providers)
        return cls(
            routing=V2RoutingConfig.from_environment(
                environment,
                repository_revision=repository_revision,
            ),
            ceilings=ceilings or V2RunCeilings(),
            discovery_providers=discovery_providers,
            wigolo=wigolo or WigoloConfig(),
            exa=(
                ExaConfig.from_environment(environment)
                if DiscoveryProvider.EXA in enabled
                else None
            ),
            openalex=(
                OpenAlexConfig.from_environment(environment)
                if DiscoveryProvider.OPENALEX in enabled
                else None
            ),
            serpsearch=(
                SerpSearchConfig.from_environment(environment)
                if DiscoveryProvider.SERPSEARCH in enabled
                else None
            ),
            firecrawl=FirecrawlConfig.from_environment(environment),
        )

    def semantic_fingerprint_sha256(self) -> str:
        payload = {
            "discovery_providers": [item.value for item in self.discovery_providers],
            "wigolo": self.wigolo.model_dump(mode="json"),
            "exa": self.exa.model_dump(mode="json", exclude={"api_key"}) if self.exa else None,
            "openalex": (
                self.openalex.model_dump(mode="json", exclude={"api_key"})
                if self.openalex
                else None
            ),
            "serpsearch": (
                self.serpsearch.model_dump(mode="json", exclude={"api_key"})
                if self.serpsearch
                else None
            ),
            "firecrawl": (
                self.firecrawl.model_dump(mode="json", exclude={"api_key"})
                if self.firecrawl
                else None
            ),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class V2ProductionProviderBundle(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    search_providers: Mapping[DiscoveryProvider, SearchProvider]
    wigolo: ScraperProvider
    firecrawl: ScraperProvider | None
    llm: RoutedV2LLMProvider


def build_v2_production_bundle(
    config: V2ProductionFactoryConfig,
    *,
    clients: ProviderClients | None = None,
) -> V2ProductionProviderBundle:
    """Build explicitly routed search, acquisition, and three-model adapters."""
    injected = clients or ProviderClients()
    composite = CompositeSearchProvider(
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
    wigolo = WigoloAcquisitionAdapter(
        config.wigolo,
        source_client=injected.source,
        wigolo_client=injected.acquisition,
        host_resolver=injected.host_resolver,
    )
    firecrawl = (
        FirecrawlAcquisitionAdapter(
            config.firecrawl,
            client=injected.fallback_acquisition,
            host_resolver=injected.host_resolver,
        )
        if config.firecrawl is not None
        else None
    )
    per_call_tokens = config.ceilings.max_total_tokens
    per_call_cost = config.ceilings.max_total_cost_usd
    llm = RoutedV2LLMProvider(
        {
            ModelAlias.MIMO_V25: XiaomiMimoAdapter(
                config.routing.mimo_v25,
                client=injected.mimo_v25_llm or injected.llm,
                price_cap=config.routing.mimo_v25_price_cap,
                max_call_cost_usd=per_call_cost,
                max_call_tokens=per_call_tokens,
                expected_model_alias=ModelAlias.MIMO_V25,
            ),
            ModelAlias.MIMO_V25_PRO: XiaomiMimoAdapter(
                config.routing.mimo_v25_pro,
                client=injected.mimo_v25_pro_llm or injected.llm,
                price_cap=config.routing.mimo_v25_pro_price_cap,
                max_call_cost_usd=per_call_cost,
                max_call_tokens=per_call_tokens,
                expected_model_alias=ModelAlias.MIMO_V25_PRO,
            ),
            ModelAlias.GPT_5_6_LUNA_HIGH: XiaomiMimoAdapter(
                config.routing.luna,
                client=injected.luna_llm or injected.llm,
                price_cap=config.routing.luna_price_cap,
                max_call_cost_usd=per_call_cost,
                max_call_tokens=per_call_tokens,
                expected_model_alias=ModelAlias.GPT_5_6_LUNA_HIGH,
            ),
        }
    )
    return V2ProductionProviderBundle(
        search_providers={provider: composite for provider in config.discovery_providers},
        wigolo=wigolo,
        firecrawl=firecrawl,
        llm=llm,
    )
