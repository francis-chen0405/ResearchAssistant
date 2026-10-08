"""Common bounded discovery signals and fair ordering, never evidence assessment."""

from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from uuid import UUID

from researchassistant.contracts.discovery_v2 import V2DiscoveryPolicy, normalize_doi
from researchassistant.contracts.metadata_ranking import MetadataRank, MetadataRankingWeights
from researchassistant.contracts.models import NormalizedDiscoveryItem
from researchassistant.research.discovery_policy import stable_work_key

RANKING_IDENTITY = "source-candidate-ranking-v2"
_WORDS = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    (
        "a an the and or of to in on for with by is are was were be been that this it as at from "
        "does do can may will would should claim reduce reduces increase increases changes change"
    ).split()
)
_METHODS = frozenset(
    (
        "trial experiment experimental randomized randomised controlled cohort longitudinal survey "
        "evaluation empirical methods results study regression quasi systematic meta analysis "
        "primary report audit records"
    ).split()
)
_PRIMARY_TYPES = frozenset(
    {
        "article",
        "journal-article",
        "research-article",
        "preprint",
        "report",
        "clinical-trial",
        "study",
    }
)
_GENERAL_TYPES = frozenset({"news", "blog", "magazine", "general", "opinion"})


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        word.rstrip("s") if len(word) > 4 else word
        for word in _WORDS.findall(text.casefold())
        if word not in _STOP
    )


def _work_key(item: NormalizedDiscoveryItem) -> str:
    doi = item.doi
    if doi:
        try:
            doi = normalize_doi(doi)
        except ValueError:
            doi = None
    return stable_work_key(doi=doi, canonical_url=item.canonical_url)


def rank_metadata(
    items: Sequence[NormalizedDiscoveryItem],
    *,
    exact_claim: str,
    policy: V2DiscoveryPolicy,
    known_work_keys: Sequence[str] = (),
) -> tuple[MetadataRank, ...]:
    """Score common features, with unknowns neutral and no cross-engine score use.

    Input text inspected per candidate is capped at 8,000 characters. Counting and
    identity grouping are linear; the only superlinear operation is stable sorting.
    Search direction and the sign of a finding never alter relevance scores.
    """
    if len(items) > policy.max_raw_per_round:
        raise ValueError("metadata ranking input exceeds frozen retained-record bound")
    if len({item.item_id for item in items}) != len(items):
        raise ValueError("metadata ranking requires unique candidate IDs")
    if len({item.run_id for item in items}) > 1:
        raise ValueError("metadata ranking cannot mix runs")
    weights = getattr(policy, "ranking_weights", MetadataRankingWeights())
    claim = _tokens(exact_claim[:8000])
    known = frozenset(known_work_keys)
    keys = {item.item_id: _work_key(item) for item in items}
    frequencies = Counter(keys.values())
    types = Counter((item.source_type or "unknown").casefold() for item in items)
    lanes = Counter((item.direction, item.provider) for item in items)
    scored: list[tuple[NormalizedDiscoveryItem, dict[str, float | None], float]] = []
    for item in items:
        text = " ".join(value for value in (item.title, item.abstract, item.snippet) if value)[
            :8000
        ]
        words = _tokens(text)
        directness = len(claim & words) / len(claim) if text and claim else None
        source_type = (item.source_type or "").casefold()
        method_hits = len(words & _METHODS)
        method = (
            min(1.0, 0.4 + 0.2 * method_hits)
            if method_hits
            else (
                0.65
                if source_type in _PRIMARY_TYPES
                else 0.3
                if source_type in _GENERAL_TYPES
                else None
            )
        )
        gap_tokens = _tokens(item.query_text[:4000]) - claim
        targeted = any(p.targeted_gap_ids for p in item.provenance_chain)
        gap = (
            len(gap_tokens & words) / len(gap_tokens) if targeted and gap_tokens and text else None
        )
        completeness = (
            int(keys[item.item_id].startswith("doi:"))
            + int(bool(item.title))
            + int(bool(item.authors))
            + int(bool(item.publication_date))
            + int(bool(item.abstract))
        ) / 5
        novelty = 0.0 if keys[item.item_id] in known else 1.0 / frequencies[keys[item.item_id]]
        diversity = (
            1.0 / lanes[(item.direction, item.provider)] + 1.0 / types[source_type or "unknown"]
        ) / 2
        signals = dict(
            directness=directness,
            method_fit=method,
            gap_fit=gap,
            identity_completeness=0.5 + 0.5 * completeness if completeness else None,
            novelty=novelty,
            diversity=diversity,
        )
        total_weight = sum(getattr(weights, name) for name in signals)
        score = (
            sum(
                getattr(weights, name) * (0.5 if value is None else value)
                for name, value in signals.items()
            )
            / total_weight
            if total_weight
            else 0.5
        )
        scored.append((item, signals, round(score, 12)))
    scored.sort(
        key=lambda row: (
            -row[2],
            keys[row[0].item_id],
            row[0].direction.value,
            row[0].provider.value,
            row[0].canonical_url,
            str(row[0].item_id),
        )
    )
    return tuple(
        MetadataRank(
            item_id=item.item_id,
            rank=index,
            score=score,
            work_key=keys[item.item_id],
            lane_direction=item.direction,
            lane_provider=item.provider,
            rationale=tuple(
                f"{name}: unknown; neutral 0.5"
                if value is None
                else f"{name}: {value:.4f}; weight {getattr(weights, name):g}"
                for name, value in signals.items()
            ),
            **signals,
        )
        for index, (item, signals, score) in enumerate(scored, 1)
    )


def fair_ranked_ids(ranks: Sequence[MetadataRank], limit: int) -> tuple[UUID, ...]:
    """Round-robin enabled lanes after retaining each work's best-ranked record."""
    if type(limit) is not int or limit < 0:
        raise ValueError("ranked allocation limit must be a nonnegative integer")
    best_by_work: dict[str, MetadataRank] = {}
    for rank in sorted(ranks, key=lambda item: (item.rank, str(item.item_id))):
        best_by_work.setdefault(rank.work_key, rank)

    queues: dict[tuple[str, str], deque[MetadataRank]] = defaultdict(deque)
    for rank in best_by_work.values():
        queues[(rank.lane_direction.value, rank.lane_provider.value)].append(rank)
    lanes = sorted(queues)
    chosen: list[UUID] = []
    seen: set[str] = set()
    while lanes and len(chosen) < limit:
        active = []
        for lane in lanes:
            queue = queues[lane]
            while queue and queue[0].work_key in seen:
                queue.popleft()
            if queue and len(chosen) < limit:
                rank = queue.popleft()
                chosen.append(rank.item_id)
                seen.add(rank.work_key)
            if queue:
                active.append(lane)
        lanes = active
    return tuple(chosen)
