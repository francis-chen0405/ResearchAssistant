from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.metadata_ranking import MetadataRank, MetadataRankingWeights
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    DiscoveryProvenance,
    NormalizedDiscoveryItem,
    ResearchDirection,
)
from researchassistant.research import metadata_ranking
from researchassistant.research.metadata_ranking import fair_ranked_ids, rank_metadata

NOW = datetime(2026, 10, 7, tzinfo=UTC)
RUN_ID = UUID("9a254ee0-3373-4f7e-8b89-6b2efbb8e9be")
CLAIM = "The camera enforcement intervention reduces traffic injuries."


def _item(
    index: int,
    *,
    title: str | None = "General article",
    abstract: str | None = "A general discussion of transportation policy.",
    provider: DiscoveryProvider = DiscoveryProvider.OPENALEX,
    direction: ResearchDirection = ResearchDirection.SUPPORT,
    doi: str | None = None,
    source_type: str | None = "journal-article",
    provider_rank: int | None = None,
    query_text: str = "traffic enforcement",
    targeted_gap_ids: tuple[str, ...] = (),
) -> NormalizedDiscoveryItem:
    query_id = uuid4()
    item_id = UUID(int=index + 1)
    source_url = f"https://papers.example/{index}"
    provenance = DiscoveryProvenance(
        provider=provider,
        query_id=query_id,
        query_text=query_text,
        direction=direction,
        round_number=1,
        provider_rank=provider_rank or index + 1,
        original_url=source_url,
        targeted_gap_ids=targeted_gap_ids,
    )
    return NormalizedDiscoveryItem(
        run_id=RUN_ID,
        item_id=item_id,
        provider=provider,
        query_id=query_id,
        query_text=query_text,
        direction=direction,
        round_number=1,
        provider_rank=provider_rank or index + 1,
        source_url=source_url,
        canonical_url=source_url,
        title=title,
        abstract=abstract,
        doi=doi,
        source_type=source_type,
        provenance_chain=(provenance,),
        discovered_at=NOW,
    )


def _rank(
    items: tuple[NormalizedDiscoveryItem, ...],
    *,
    known: tuple[str, ...] = (),
    policy: V2MetadataDiscoveryPolicy | None = None,
) -> tuple[MetadataRank, ...]:
    return rank_metadata(
        items,
        exact_claim=CLAIM,
        policy=policy or V2MetadataDiscoveryPolicy(),
        known_work_keys=known,
    )


@pytest.mark.parametrize("provider_rank", [12, 18, 20])
def test_primary_study_below_provider_top_five_ranks_ahead_of_general_articles(
    provider_rank: int,
) -> None:
    general = tuple(
        _item(i, title=f"General policy article {i}", abstract="A broad policy overview.")
        for i in range(20)
    )
    seeded_study = _item(
        100,
        title="Camera enforcement and traffic injury outcomes",
        abstract=(
            "We conducted a randomized controlled cohort study of camera enforcement. "
            "The intervention reduced traffic injuries in the evaluated community."
        ),
        provider_rank=provider_rank,
    )

    ranks = _rank((*general, seeded_study))

    assert ranks[0].item_id == seeded_study.item_id
    assert ranks[0].directness is not None and ranks[0].directness > 0.5
    assert ranks[0].method_fit is not None and ranks[0].method_fit > 0.5
    assert ranks[0].rank == 1


def test_unknown_metadata_is_neutral_and_does_not_become_a_quality_penalty() -> None:
    unknown = _item(0, title=None, abstract=None, source_type=None)
    result = _rank(
        (unknown,),
        policy=V2MetadataDiscoveryPolicy(
            ranking_weights=MetadataRankingWeights(
                directness=1,
                method_fit=1,
                gap_fit=1,
                identity_completeness=1,
                novelty=0,
                diversity=0,
            )
        ),
    )[0]

    assert result.directness is None
    assert result.method_fit is None
    assert result.identity_completeness is None
    assert result.score == pytest.approx(0.5)


def test_support_lane_keeps_a_relevant_contradictory_finding() -> None:
    contradictory = _item(
        1,
        title="Camera enforcement and traffic injury outcomes",
        abstract=(
            "A controlled cohort study found camera enforcement did not reduce traffic injuries."
        ),
        direction=ResearchDirection.SUPPORT,
    )

    ranks = _rank((contradictory,))

    assert ranks[0].item_id == contradictory.item_id
    assert ranks[0].lane_direction is ResearchDirection.SUPPORT
    assert ranks[0].directness is not None and ranks[0].directness > 0


def test_duplicate_doi_is_grouped_conservatively_and_does_not_consume_two_slots() -> None:
    duplicate_one = _item(1, doi="10.1234/TRAFFIC.1")
    duplicate_two = _item(2, doi="doi:10.1234/traffic.1", provider=DiscoveryProvider.EXA)
    independent = _item(3, doi="10.1234/traffic.2")
    ranks = _rank((duplicate_one, duplicate_two, independent))

    selected = fair_ranked_ids(ranks, limit=3)

    assert len(selected) == 2
    assert independent.item_id in selected
    assert len(set(selected) & {duplicate_one.item_id, duplicate_two.item_id}) == 1
    duplicate_ranks = tuple(rank for rank in ranks if rank.work_key.endswith("traffic.1"))
    assert len(duplicate_ranks) == 2
    assert len({rank.work_key for rank in duplicate_ranks}) == 1


def test_lane_fairness_preserves_a_scarce_enabled_provider() -> None:
    common = tuple(_item(i, title=f"Policy article {i}") for i in range(12))
    scarce = _item(50, provider=DiscoveryProvider.PUBMED, title="A medical cohort study")
    ranks = _rank((*common, scarce))

    selected = fair_ranked_ids(ranks, limit=4)

    assert scarce.item_id in selected
    assert len(selected) == 4


def test_stable_ties_and_large_bounded_pool_have_linear_feature_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = tuple(
        _item(
            i,
            title=f"Unrelated policy item {i}",
            abstract="Metadata does not include the claim language.",
            doi=f"10.1234/example.{i}",
        )
        for i in range(300)
    )
    token_calls = 0
    original_tokens = metadata_ranking._tokens

    def counted_tokens(text: str) -> frozenset[str]:
        nonlocal token_calls
        token_calls += 1
        return original_tokens(text)

    monkeypatch.setattr(metadata_ranking, "_tokens", counted_tokens)
    first = _rank(items)
    calls_after_first = token_calls
    second = _rank(items)

    assert first == second
    assert calls_after_first <= 2 * len(items) + 1
    assert token_calls == calls_after_first * 2
    reversed_first = _rank(tuple(reversed(items)))
    assert tuple(item.item_id for item in first) == tuple(item.item_id for item in reversed_first)
    with pytest.raises(ValueError, match="bound"):
        _rank((*items, _item(301)))
