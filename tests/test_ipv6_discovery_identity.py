"""Fresh IPv6 URL identities remain valid without relabeling historical ranking."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from test_metadata_ranking import CLAIM, _item
from test_v2_phase4_discovery_scout import NOW, _response

from researchassistant.agents.v2_discovery import normalize_discovery_responses
from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.models import DiscoveryProvider, ResearchDirections
from researchassistant.providers.acquisition import _validate_public_url
from researchassistant.providers.ranking import canonical_discovery_url
from researchassistant.research.discovery_policy import stable_work_key
from researchassistant.research.metadata_ranking import rank_metadata


@pytest.mark.parametrize("port", ["", ":8443"])
def test_public_ipv6_survives_canonicalization_and_fresh_ranking(port: str) -> None:
    url = f"https://[2606:4700:4700::1111]{port}/paper/?utm_source=fixture&study=1#section"
    canonical = canonical_discovery_url(url)
    assert canonical == f"https://[2606:4700:4700::1111]{port}/paper?study=1"
    assert canonical_discovery_url(canonical) == canonical
    assert urlsplit(canonical).port == (8443 if port else None)
    assert _validate_public_url(canonical) == ("2606:4700:4700::1111",)
    item = _item(0).model_copy(update={"source_url": url, "canonical_url": canonical})
    ranked = rank_metadata((item,), exact_claim=CLAIM, policy=V2MetadataDiscoveryPolicy())
    assert ranked[0].item_id == item.item_id
    assert ranked[0].work_key == stable_work_key(doi=None, canonical_url=canonical)
    historical = stable_work_key(doi=None, canonical_url=canonical, url_identity_version=1)
    assert ranked[0].work_key != historical
    for identity in ("source-candidate-ranking-v2", "source-candidate-ranking-v3"):
        legacy_ranked = rank_metadata(
            (item,),
            exact_claim=CLAIM,
            policy=V2MetadataDiscoveryPolicy(),
            ranking_identity=identity,
        )
        assert legacy_ranked[0].work_key == historical


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://Example.org/Study/?b=2&utm_source=fixture&a=1#part",
            "https://example.org/Study?a=1&b=2",
        ),
        ("https://93.184.216.34:8443/paper/", "https://93.184.216.34:8443/paper"),
        ("https://EXAMPLE.org/", "https://example.org/"),
    ],
)
def test_existing_hostname_ipv4_and_tracking_identity_is_preserved(
    version: Literal[1, 2], url: str, expected: str
) -> None:
    assert canonical_discovery_url(url, version=version) == expected
    assert canonical_discovery_url(expected, version=version) == expected


def test_historical_ipv6_authority_is_available_only_by_explicit_version() -> None:
    url = "https://[2606:4700:4700::1111]:8443/paper"
    assert canonical_discovery_url(url, version=1) == "https://2606:4700:4700::1111:8443/paper"
    assert canonical_discovery_url(url) == url


def test_fresh_normalization_versions_only_changed_ipv6_item_identity() -> None:
    run_id = uuid4()
    for url in ("https://example.org/paper", "https://[2606:4700:4700::1111]/paper"):
        response = _response(run_id, DiscoveryProvider.EXA, url=url, doi=None)
        options = {
            "run_id": run_id,
            "directions": ResearchDirections(),
            "responses": (response,),
            "discovered_at": NOW,
        }
        current = normalize_discovery_responses(**options)[0]
        historical = normalize_discovery_responses(**options, url_identity_version=1)[0]
        if "[" in url:
            assert current.item_id != historical.item_id
            assert current.canonical_url == url
        else:
            assert current == historical
