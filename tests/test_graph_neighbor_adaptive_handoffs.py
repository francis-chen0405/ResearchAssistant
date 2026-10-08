from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from agents.v2_discovery import V2DiscoveryResponse, normalize_discovery_responses
from providers.search import SearchResult
from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryPolicy,
    V2GraphNeighborAction,
    V2ProviderCapabilities,
    V2SeedEligibility,
    V2WorkIdentity,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    DiscoveryProvenance,
    ResearchDirection,
    ResearchDirections,
    V2AdaptiveSearchQuery,
    V2GapAttemptedQuery,
)

RUN = UUID("8eaf232a-c20b-4c93-a579-112ac61dc2f4")
NOW = datetime(2026, 10, 7, tzinfo=UTC)


def _graph_action() -> V2GraphNeighborAction:
    provider = DiscoveryProvider.OPENALEX
    capability = V2ProviderCapabilities(
        provider=provider,
        search_modes=("lexical",),
        max_metadata_per_page=20,
        max_metadata_per_operation=20,
        pagination="none",
        identity_lookup=True,
        executable_identity_lookup=True,
        relationships=("references", "citing", "related"),
        executable_relationships=("references", "citing", "related"),
        executable_search_modes=("lexical",),
        documentation_urls=("https://docs.openalex.org/api-entities/works/search-works",),
    )
    seed = V2SeedEligibility(
        run_id=RUN,
        artifact_id=discovery_id(RUN, "V2SeedEligibility", "seed"),
        identity_key="seed",
        candidate_id=UUID(int=11),
        source_id=UUID(int=12),
        snapshot_id=UUID(int=13),
        work=V2WorkIdentity(
            grouping_key="doi:10.5555/seed",
            doi="10.5555/seed",
            provider_work_id="https://openalex.org/W1",
            resolution="verified_identifiers",
        ),
        eligible=True,
        reason="resolved seed",
    )
    return V2GraphNeighborAction(
        run_id=RUN,
        artifact_id=discovery_id(RUN, "V2GraphNeighborAction", "neighbors"),
        identity_key="neighbors",
        seed=seed,
        relationship="citing",
        provider=provider,
        direction=ResearchDirection.SUPPORT,
        round_number=3,
        target_gap_ids=("gap-a",),
        requested_depth=3,
        policy=V2DiscoveryPolicy(),
        capabilities=capability,
    )


def _query(action: V2GraphNeighborAction) -> V2AdaptiveSearchQuery:
    return V2AdaptiveSearchQuery(
        run_id=RUN,
        query_id=action.artifact_id,
        round_number=3,
        direction=action.direction,
        provider=action.provider,
        targeted_gap_ids=action.target_gap_ids,
        strategy="follow citations around a verified seed",
        query_text=None,
        graph_action=action,
        created_at=NOW,
    )


def test_graph_action_is_a_query_lane_and_normalizes_with_honest_provenance() -> None:
    action = _graph_action()
    query = _query(action)
    (item,) = normalize_discovery_responses(
        run_id=RUN,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        responses=(
            V2DiscoveryResponse(
                query=query,
                results=(SearchResult(original_url="https://example.test/paper", rank=1),),
            ),
        ),
        discovered_at=NOW,
    )

    assert item.query_id == action.artifact_id
    assert item.query_text is None
    assert item.graph_action == action
    assert item.provenance_chain[0].query_text is None
    assert item.provenance_chain[0].graph_action == action


def test_graph_action_rejects_forged_text_and_mismatched_lane_identity() -> None:
    action = _graph_action()
    base = _query(action).model_dump()

    with pytest.raises(ValidationError, match="cannot carry text"):
        V2AdaptiveSearchQuery.model_validate({**base, "query_text": "invented query"})
    with pytest.raises(ValidationError, match="action identity"):
        V2AdaptiveSearchQuery.model_validate({**base, "query_id": UUID(int=99)})
    with pytest.raises(ValidationError, match="forged query text"):
        DiscoveryProvenance(
            provider=action.provider,
            query_id=action.artifact_id,
            query_text="invented query",
            graph_action=action,
            direction=action.direction,
            round_number=action.round_number,
            provider_rank=1,
            original_url="https://example.test/paper",
            targeted_gap_ids=action.target_gap_ids,
        )


def test_legacy_text_serialization_omits_new_graph_action_fields() -> None:
    action = _graph_action()
    text_query = V2AdaptiveSearchQuery(
        run_id=RUN,
        query_id=UUID(int=101),
        round_number=2,
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        targeted_gap_ids=("gap-a",),
        strategy="search outcomes",
        query_text="cohort outcome evidence",
        created_at=NOW,
    )
    provenance = DiscoveryProvenance(
        provider=text_query.provider,
        query_id=text_query.query_id,
        query_text=text_query.query_text,
        direction=text_query.direction,
        round_number=text_query.round_number,
        provider_rank=1,
        original_url="https://example.test/paper",
        targeted_gap_ids=text_query.targeted_gap_ids,
    )
    attempted = V2GapAttemptedQuery(
        query_id=text_query.query_id,
        direction=text_query.direction,
        provider=text_query.provider,
        strategy=text_query.strategy,
        query_text=text_query.query_text,
        round_number=text_query.round_number,
    )

    assert "graph_action" not in text_query.model_dump(mode="json")
    assert "graph_action" not in provenance.model_dump(mode="json")
    assert "graph_action" not in attempted.model_dump(mode="json")
    assert text_query.model_dump(mode="json")["query_text"] == "cohort outcome evidence"
    assert action.artifact_id != text_query.query_id
