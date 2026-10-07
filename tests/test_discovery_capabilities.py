"""Regression tests for the versioned, non-activating provider capability catalog."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from researchassistant.contracts.discovery_v2 import V2ProviderCapabilities
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.research.discovery_capabilities import (
    PROVIDER_CAPABILITIES,
    get_provider_capabilities,
    validate_relationship_capability,
    validate_search_capability,
)


def test_catalog_covers_only_enabled_fresh_v2_providers() -> None:
    assert set(PROVIDER_CAPABILITIES) == {
        DiscoveryProvider.OPENALEX,
        DiscoveryProvider.ARXIV,
        DiscoveryProvider.PUBMED,
        DiscoveryProvider.EXA,
        DiscoveryProvider.SERPSEARCH,
    }
    with pytest.raises(TypeError):
        PROVIDER_CAPABILITIES[DiscoveryProvider.SERPER] = next(iter(PROVIDER_CAPABILITIES.values()))  # type: ignore[index]
    with pytest.raises(ValueError, match="no fresh-v2"):
        get_provider_capabilities(DiscoveryProvider.SERPER)


@pytest.mark.parametrize("capability", PROVIDER_CAPABILITIES.values())
def test_entries_are_immutable_and_round_trip(capability: V2ProviderCapabilities) -> None:
    assert capability == V2ProviderCapabilities.model_validate_json(capability.model_dump_json())
    with pytest.raises(ValidationError):
        capability.provider = DiscoveryProvider.SERPER  # type: ignore[misc]
    assert capability.documentation_urls
    assert capability.max_metadata_per_page <= capability.max_metadata_per_operation


def test_native_capabilities_do_not_imply_executable_transport_features() -> None:
    openalex = get_provider_capabilities(DiscoveryProvider.OPENALEX)
    assert openalex.search_modes == ("lexical", "semantic")
    assert openalex.executable_search_modes == ("lexical", "semantic")
    assert openalex.relationships == ("references", "citing", "related")
    assert openalex.executable_relationships == ()
    assert openalex.pagination == "cursor"

    pubmed = get_provider_capabilities(DiscoveryProvider.PUBMED)
    assert pubmed.relationships == ("references", "citing", "related")
    assert pubmed.executable_relationships == ()

    arxiv = get_provider_capabilities(DiscoveryProvider.ARXIV)
    assert arxiv.identity_lookup is True  # native id_list; adapter uses search only
    assert "adapter fixes start=0" in " ".join(arxiv.unsupported_features)

    serpsearch = get_provider_capabilities(DiscoveryProvider.SERPSEARCH)
    assert serpsearch.pagination == "page"
    assert "page=1" in " ".join(serpsearch.unsupported_features)


def test_search_mode_rejection_distinguishes_native_and_executable_support() -> None:
    validate_search_capability(DiscoveryProvider.OPENALEX, "semantic")
    validate_search_capability(DiscoveryProvider.EXA, "provider_default", executable=True)
    with pytest.raises(ValueError, match="unsupported search mode"):
        validate_search_capability(DiscoveryProvider.ARXIV, "semantic")
    with pytest.raises(ValueError, match="unsupported search mode"):
        validate_search_capability(DiscoveryProvider.EXA, "semantic", executable=True)


def test_native_relationships_are_rejected_for_current_adapters() -> None:
    validate_relationship_capability(DiscoveryProvider.PUBMED, "related")
    with pytest.raises(ValueError, match="unsupported relationship"):
        validate_relationship_capability(DiscoveryProvider.PUBMED, "related", executable=True)
    with pytest.raises(ValueError, match="unsupported relationship"):
        validate_relationship_capability(DiscoveryProvider.EXA, "references")
