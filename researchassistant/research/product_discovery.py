"""Resolve public controls into one supported, bounded fresh discovery policy."""

from researchassistant.contracts.discovery_v2 import SearchMode, V2ProductDiscoveryPolicy
from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
from researchassistant.research.discovery_capabilities import get_query_capabilities


def resolve_product_discovery(
    controls: ResearchControls, providers: tuple[DiscoveryProvider, ...]
) -> tuple[V2ProductDiscoveryPolicy, dict[DiscoveryProvider, SearchMode]]:
    if controls.discovery_providers != providers:
        raise ValueError("discovery controls must match the selected research sources")
    mode = controls.scholarly_search_mode or "lexical"
    if mode == "semantic" and DiscoveryProvider.OPENALEX not in providers:
        raise ValueError("Semantic scholarly search requires OpenAlex to be selected.")
    modes: dict[DiscoveryProvider, SearchMode] = {}
    for provider in providers:
        # Automatic is deterministic lexical: it performs no second attempt.
        selected: SearchMode = (
            "provider_default"
            if provider is DiscoveryProvider.EXA
            else "semantic"
            if provider is DiscoveryProvider.OPENALEX and mode == "semantic"
            else "lexical"
        )
        get_query_capabilities(provider).require_search(selected, executable=True)
        modes[provider] = selected
    return V2ProductDiscoveryPolicy(
        metadata_depth=controls.metadata_depth or 20,
        seed_expansion_enabled=controls.seed_expansion_enabled
        if controls.seed_expansion_enabled is not None
        else True,
        scholarly_search_mode=mode,
        sources_per_direction_per_round=controls.sources_per_stance_per_round,
    ), modes
