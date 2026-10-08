from __future__ import annotations

from uuid import UUID

from researchassistant.contracts.metadata_ranking import MetadataRank
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import ResearchDirection
from researchassistant.research.metadata_ranking import fair_ranked_ids


def _rank(
    item_number: int,
    rank_number: int,
    work_key: str,
    direction: ResearchDirection,
    provider: DiscoveryProvider,
) -> MetadataRank:
    return MetadataRank(
        item_id=UUID(int=item_number),
        rank=rank_number,
        score=1.0 - rank_number / 100,
        work_key=work_key,
        lane_direction=direction,
        lane_provider=provider,
    )


def test_cross_lane_duplicate_keeps_best_ranked_representative_with_one_slot() -> None:
    best = _rank(
        1,
        1,
        "doi:10.1234/shared",
        ResearchDirection.SUPPORT,
        DiscoveryProvider.OPENALEX,
    )
    lower_ranked_duplicate = _rank(
        2,
        2,
        "doi:10.1234/shared",
        ResearchDirection.CHALLENGE,
        DiscoveryProvider.EXA,
    )

    assert fair_ranked_ids((best, lower_ranked_duplicate), limit=1) == (best.item_id,)


def test_best_representatives_preserve_scarce_lane_and_input_order_stability() -> None:
    ranks = (
        _rank(
            1,
            1,
            "doi:10.1234/shared",
            ResearchDirection.SUPPORT,
            DiscoveryProvider.OPENALEX,
        ),
        _rank(
            2,
            2,
            "doi:10.1234/shared",
            ResearchDirection.CHALLENGE,
            DiscoveryProvider.EXA,
        ),
        _rank(
            3,
            3,
            "doi:10.1234/common",
            ResearchDirection.SUPPORT,
            DiscoveryProvider.OPENALEX,
        ),
        _rank(
            4,
            4,
            "doi:10.1234/scarce",
            ResearchDirection.CHALLENGE,
            DiscoveryProvider.EXA,
        ),
    )

    selected = fair_ranked_ids(ranks, limit=3)

    assert set(selected) == {ranks[0].item_id, ranks[2].item_id, ranks[3].item_id}
    assert selected == fair_ranked_ids(tuple(reversed(ranks)), limit=3)
