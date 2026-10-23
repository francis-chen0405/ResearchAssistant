"""Adaptive round summaries, survivor merging and terminal checkpoints."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveBudgetState as V2AdaptiveBudgetState,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveContinuationResult as V2AdaptiveContinuationResult,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveRoundExecution as V2AdaptiveRoundExecution,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveStopCode as V2AdaptiveStopCode,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveStoppingDecision as V2AdaptiveStoppingDecision,
)
from researchassistant.agents.adaptive_handoffs import (
    V2MergedSurvivor as V2MergedSurvivor,
)
from researchassistant.agents.adaptive_handoffs import (
    V2MergedSurvivorPool as V2MergedSurvivorPool,
)
from researchassistant.contracts.models import (
    ResearchDirection,
    SourceCluster,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2DiscoveryScoutOutput,
    V2GapAcquisitionFailure,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAttemptedQuery,
    V2GapBudgetState,
    V2GapDuplicatePattern,
    V2GapProbePassage,
    V2GapSourceFamily,
    V2GapSurvivingSourceMetadata,
    V2InitialPlannerOutput,
)
from researchassistant.providers.ranking import canonical_discovery_url
from researchassistant.research.research_governor import (
    V2RoundThreeGovernorDecision,
)
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

V2_ADAPTIVE_COMPLETION_KEY = "phase-7-adaptive-search-completion"


def _round_two_gap_input(
    round_one_gap: V2GapAnalysisOutput,
    plan: V2AdaptiveRoundPlan,
    discovery: V2DiscoveryScoutOutput,
    acquisition: V2AcquisitionProbeOutput,
    budget: V2AdaptiveBudgetState,
) -> V2GapAnalysisInput:
    cluster_by_id = {item.cluster_id: item for item in discovery.clusters}
    item_by_id = {item.item_id: item for item in discovery.items}
    source_by_snapshot = {item.snapshot.snapshot_id: item for item in acquisition.acquisitions}
    new_sources: list[V2GapSurvivingSourceMetadata] = []
    new_passages: list[V2GapProbePassage] = []
    for survivor in acquisition.survivors:
        cluster = cluster_by_id[survivor.cluster_id]
        representative = min(
            (item_by_id[item_id] for item_id in cluster.item_ids),
            key=lambda item: item.provider_rank,
        )
        source = source_by_snapshot[survivor.snapshot_id]
        new_sources.append(
            V2GapSurvivingSourceMetadata(
                source_cluster_id=survivor.cluster_id,
                direction=survivor.direction,
                snapshot_id=survivor.snapshot_id,
                snapshot_sha256=survivor.snapshot_sha256,
                source_url=source.snapshot.source_url,
                title=representative.title,
                source_family_id=f"cluster:{survivor.cluster_id}",
                round_number=2,
            )
        )
        probe = next(
            item for item in acquisition.probes if item.snapshot_id == survivor.snapshot_id
        )
        passages = {item.passage_id: item for item in probe.passages}
        for passage_id in survivor.passage_ids:
            passage = passages[passage_id]
            new_passages.append(
                V2GapProbePassage(
                    passage_id=passage_id,
                    source_cluster_id=survivor.cluster_id,
                    direction=survivor.direction,
                    text=passage.text[:1200],
                    truncated_for_gap_analysis=len(passage.text) > 1200,
                    round_number=2,
                )
            )
    failures = tuple(
        V2GapAcquisitionFailure(
            source_cluster_id=item.cluster_id,
            direction=_cluster_direction(item.cluster_id, discovery),
            provider=item.provider,
            failure_code=item.failure_code or "unspecified",
            round_number=2,
        )
        for item in acquisition.attempts
        if not item.succeeded
    )
    families = tuple(
        V2GapSourceFamily(
            family_id=f"cluster:{item.source_cluster_id}",
            direction=item.direction,
            source_cluster_ids=(item.source_cluster_id,),
            discovery_providers=tuple(
                dict.fromkeys(
                    ref.provider
                    for ref in cluster_by_id[item.source_cluster_id].provider_references
                )
            ),
            round_number=2,
            round_numbers=(2,),
        )
        for item in new_sources
    )
    duplicates = tuple(
        V2GapDuplicatePattern(
            source_cluster_id=cluster.cluster_id,
            direction=_cluster_direction(cluster.cluster_id, discovery),
            duplicate_discovery_count=len(cluster.item_ids),
            pattern="conservatively clustered same-source discovery records",
            round_number=2,
        )
        for cluster in discovery.clusters
        if len(cluster.item_ids) > 1
    )
    prior = round_one_gap.input
    return V2GapAnalysisInput(
        run_id=prior.run_id,
        exact_claim=prior.exact_claim,
        directions=prior.directions,
        completed_round=2,
        assessed_source_findings=prior.assessed_source_findings,
        attempted_queries=(
            *prior.attempted_queries,
            *(
                V2GapAttemptedQuery(
                    query_id=item.query_id,
                    direction=item.direction,
                    provider=item.provider,
                    strategy=item.strategy,
                    query_text=item.query_text,
                    graph_action=item.graph_action,
                    round_number=item.round_number,
                )
                for item in plan.searches
            ),
        ),
        surviving_sources=(*prior.surviving_sources, *new_sources),
        probe_passages=tuple((*new_passages, *prior.probe_passages))[:40],
        source_families=(*prior.source_families, *families),
        discovered_terms=tuple(dict.fromkeys((*prior.discovered_terms, *plan.discovered_terms)))[
            :40
        ],
        duplicate_patterns=tuple((*prior.duplicate_patterns, *duplicates))[:25],
        acquisition_failures=tuple((*prior.acquisition_failures, *failures))[:150],
        previous_gaps=round_one_gap.result.material_gaps if round_one_gap.result else (),
        claim_coverage_focus=prior.claim_coverage_focus,
        policy_identity=prior.policy_identity,
        remaining_budget=V2GapBudgetState(
            model_calls_remaining=max(0, budget.model_calls_remaining - 1),
            tokens_remaining=budget.tokens_remaining,
            cost_remaining_usd=budget.cost_remaining_usd,
        ),
    )


def _merge_survivors(
    run_id: UUID,
    rounds: tuple[tuple[int, V2DiscoveryScoutOutput, V2AcquisitionProbeOutput], ...],
    *,
    deduplicate_papers: bool = False,
) -> V2MergedSurvivorPool:
    merged: list[V2MergedSurvivor] = []
    seen: set[str] = set()
    for round_number, _discovery, acquisition in rounds:
        if _discovery.run_id != run_id or acquisition.run_id != run_id:
            raise ValueError("survivor merge inputs belong to another run")
        by_snapshot = {item.snapshot.snapshot_id: item for item in acquisition.acquisitions}
        for survivor in acquisition.survivors:
            source_url = by_snapshot[survivor.snapshot_id].snapshot.source_url
            identity = canonical_discovery_url(source_url)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(
                V2MergedSurvivor(
                    research_round=round_number, source_url=source_url, survivor=survivor
                )
            )
    if deduplicate_papers:
        merged = _merge_confirmed_papers(merged, rounds)
    return V2MergedSurvivorPool(run_id=run_id, sources=tuple(merged))


def _merge_confirmed_papers(
    sources: list[V2MergedSurvivor],
    rounds: tuple[tuple[int, V2DiscoveryScoutOutput, V2AcquisitionProbeOutput], ...],
) -> list[V2MergedSurvivor]:
    from researchassistant.contracts.paper_identity import ConfirmedPaperLocation
    from researchassistant.evidence.paper_identity import confirmed_paper_anchor, paper_title_key

    snapshots = {
        item.snapshot.snapshot_id: item.snapshot
        for _, _, output in rounds
        for item in output.acquisitions
    }
    items = {item.item_id: item for _, discovery, _ in rounds for item in discovery.items}
    clusters = {
        cluster.cluster_id: cluster for _, discovery, _ in rounds for cluster in discovery.clusters
    }
    groups: dict[
        tuple[str, object, str], list[tuple[V2MergedSurvivor, ConfirmedPaperLocation]]
    ] = {}
    for source in sources:
        cluster = clusters[source.survivor.cluster_id]
        members = tuple(items[item_id] for item_id in cluster.item_ids)
        title = next((item.title for item in members if item.title), None)
        title_key = paper_title_key(title)
        snapshot = snapshots[source.survivor.snapshot_id]
        anchor = confirmed_paper_anchor(
            snapshot, title, tuple(item.doi for item in members if item.doi)
        )
        if anchor is None or len(title_key) < 24:
            continue
        doi, basis = anchor
        location = ConfirmedPaperLocation(
            source_id=source.survivor.cluster_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_sha256,
            source_url=snapshot.source_url,
            research_round=source.research_round,
            direction=source.survivor.direction,
            doi=doi,
            basis=basis,
        )
        groups.setdefault((doi, source.survivor.direction, title_key), []).append(
            (source, location)
        )
    replacements: dict[UUID, V2MergedSurvivor | None] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        # Prefer full readable captures within the earliest round. Later mirrors
        # cannot displace a source whose early assessment may already be saved.
        ordered = sorted(
            group,
            key=lambda pair: (
                pair[0].research_round,
                -snapshots[pair[0].survivor.snapshot_id].word_count,
                str(pair[0].survivor.cluster_id),
            ),
        )
        canonical = ordered[0][0]
        replacements[canonical.survivor.cluster_id] = V2MergedSurvivor(
            research_round=canonical.research_round,
            source_url=canonical.source_url,
            survivor=canonical.survivor,
            paper_locations=tuple(location for _, location in ordered),
        )
        for alias, _ in ordered[1:]:
            replacements[alias.survivor.cluster_id] = None
    return [
        replacements.get(source.survivor.cluster_id, source)
        for source in sources
        if replacements.get(source.survivor.cluster_id, source) is not None
    ]


def _known_urls(outputs: tuple[V2DiscoveryScoutOutput, ...]) -> frozenset[str]:
    return frozenset(
        url for output in outputs for cluster in output.clusters for url in _cluster_urls(cluster)
    )


def _cluster_urls(cluster: SourceCluster) -> frozenset[str]:
    return frozenset(
        canonical_discovery_url(url)
        for url in (cluster.preferred_url, cluster.canonical_url, *cluster.alternate_urls)
    )


def _cluster_direction(cluster_id: UUID, output: V2DiscoveryScoutOutput) -> ResearchDirection:
    cluster = next(item for item in output.clusters if item.cluster_id == cluster_id)
    items = {item.item_id: item for item in output.items}
    return min(
        (items[item_id] for item_id in cluster.item_ids), key=lambda item: item.provider_rank
    ).direction


def _validate_round_one_inputs(
    initial: V2InitialPlannerOutput,
    discovery: V2DiscoveryScoutOutput,
    acquisition: V2AcquisitionProbeOutput,
    gap: V2GapAnalysisOutput,
) -> None:
    if {initial.run_id, discovery.run_id, acquisition.run_id, gap.run_id} != {initial.run_id}:
        raise ValueError("all adaptive continuation inputs must share one run_id")
    if gap.input.completed_round != 1:
        raise ValueError("adaptive continuation must begin from completed Round-1 Gap Analysis")


def _finish(
    path: str,
    run_id: UUID,
    rounds: tuple[V2AdaptiveRoundExecution, ...],
    pool: V2MergedSurvivorPool,
    code: V2AdaptiveStopCode,
    reason: str,
    completed_rounds: int,
    clock: Callable[[], datetime],
    governor: V2RoundThreeGovernorDecision | None = None,
) -> V2AdaptiveContinuationResult:
    try:
        saved_pool = read_v2_artifact(path, run_id, "phase-7-merged-survivor-pool")
    except KeyError:
        saved_pool = None
    # A crash can leave only the pool, or the pool and decision. Rebuild the
    # remaining deterministic checkpoints at the original immutable boundary.
    completed_at = saved_pool.created_at if saved_pool is not None else clock()
    result = V2AdaptiveContinuationResult(
        run_id=run_id,
        rounds=rounds,
        merged_survivors=pool,
        stopping_decision=V2AdaptiveStoppingDecision(
            run_id=run_id,
            completed_rounds=completed_rounds,
            stop_code=code,
            stopping_reason=reason,
            decided_at=completed_at,
        ),
        governor_decision=governor,
        completed_at=completed_at,
    )
    insert_v2_artifact(
        path,
        "phase-7-merged-survivor-pool",
        pool,
        completed_at,
    )
    insert_v2_artifact(
        path,
        "phase-7-stopping-decision",
        result.stopping_decision,
        completed_at,
    )
    insert_v2_artifact(path, V2_ADAPTIVE_COMPLETION_KEY, result, completed_at)
    return result
