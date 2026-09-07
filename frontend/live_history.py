"""Read-only persisted history and research-trail projections; no worker ownership."""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection
from typing import Literal
from uuid import UUID

from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY
from agents.v2_discovery import V2_SCOUT_ARTIFACT_KEY
from frontend.live_contracts import (
    AcquiredSourceScoreBreakdown,
    DiscoveryScoreBreakdown,
    LiveHistoryItem,
    ResearchTrail,
    ResearchTrailItem,
)
from frontend.live_progress import (
    _read_first_v2_artifact,
)
from models import (
    RunManifest,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
)
from orchestrator import (
    MVP10_TARGETED_RESEARCHERS_ARTIFACT,
    MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
    MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT,
    PHASE9_RESEARCHERS_ARTIFACT,
    ResearcherPairResult,
)
from store import (
    list_runs,
    open_read_only_store,
    read_run,
    read_stage_artifact,
    read_v2_artifact,
)
from v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    infer_v2_stage,
)


def history(db_path: str | Path, *, limit: int = 100) -> tuple[LiveHistoryItem, ...]:
    path = Path(db_path).resolve()
    if not path.is_file():
        return ()
    with open_read_only_store(path) as store:
        manifests = list_runs(store.connection, limit=limit)
        items: list[LiveHistoryItem] = []
        for manifest in manifests:
            try:
                artifact = _read_first_v2_artifact(
                    store.connection,
                    manifest.run_id,
                    (
                        V2_PRODUCTION_ARTIFACT_KEY,
                        V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
                        V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
                    ),
                )
                result = V2ProductionPipelineResult.model_validate_json(artifact.payload_json)
            except (KeyError, ValueError):
                items.append(_history_item(manifest))
                continue
            items.append(
                LiveHistoryItem(
                    run_id=manifest.run_id,
                    raw_claim=manifest.raw_claim,
                    status=manifest.status.value,
                    stage=infer_v2_stage(
                        str(path),
                        manifest.run_id,
                        result.current_stage,
                        result.final_output is not None,
                    ).value,
                    updated_at=manifest.updated_at.isoformat(),
                    completed_at=(
                        manifest.completed_at.isoformat() if manifest.completed_at else None
                    ),
                )
            )
    return tuple(items)


def research_trail(db_path: str | Path, run_id: UUID) -> ResearchTrail:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise KeyError(f"run {run_id} not found")
    stage_keys = (
        (1, PHASE9_RESEARCHERS_ARTIFACT),
        (2, MVP10_TARGETED_RESEARCHERS_ARTIFACT),
        (2, MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT),
        (3, MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT),
    )
    items: list[ResearchTrailItem] = []
    with open_read_only_store(path) as store:
        # An existing database is not evidence that this particular run exists.
        read_run(store.connection, run_id)
        items.extend(_v2_research_trail_items(store.connection, run_id))
        for research_round, artifact_key in stage_keys:
            try:
                artifact = read_stage_artifact(store.connection, run_id, artifact_key)
            except KeyError:
                continue
            if artifact.artifact_type != ResearcherPairResult.__name__:
                continue
            pair = ResearcherPairResult.model_validate_json(artifact.payload_json)
            for side in (pair.supporting, pair.opposing):
                if side.retrieval_batch is None:
                    continue
                outcomes_by_rank = {
                    outcome.retrieval.search_rank: outcome
                    for outcome in side.retrieval_batch.outcomes
                }
                acquired_by_retrieval = {
                    item.retrieval_attempt_id: item
                    for item in side.retrieval_batch.acquired_source_ranking
                }
                for ranked in side.retrieval_batch.discovery_ranking:
                    components = ranked.components
                    outcome = (
                        outcomes_by_rank.get(ranked.selection_rank)
                        if ranked.selection_rank is not None
                        else None
                    )
                    acquired = (
                        acquired_by_retrieval.get(outcome.retrieval.retrieval_attempt_id)
                        if outcome is not None
                        else None
                    )
                    items.append(
                        ResearchTrailItem(
                            research_round=research_round,
                            stance=side.stance,
                            provider=ranked.query.provider.value,
                            intent=ranked.query.intent.value,
                            query_text=ranked.query.query_text,
                            title=ranked.result.title,
                            url=ranked.canonical_url,
                            score=ranked.score,
                            decision=ranked.decision.value,
                            selection_rank=ranked.selection_rank,
                            breakdown=DiscoveryScoreBreakdown(
                                relevance=components.relevance,
                                intent_match=components.intent_match,
                                directness=components.directness,
                                metadata_completeness=components.metadata_completeness,
                                likely_accessibility=components.likely_accessibility,
                                source_novelty=components.source_novelty,
                                penalties=(
                                    components.generic_homepage_penalty
                                    + components.marketing_or_community_penalty
                                    + components.unrelated_title_penalty
                                ),
                            ),
                            acquired_score=acquired.score if acquired is not None else None,
                            extraction_rank=(
                                acquired.extraction_rank if acquired is not None else None
                            ),
                            acquired_breakdown=(
                                AcquiredSourceScoreBreakdown(
                                    readability=acquired.components.readability,
                                    claim_term_coverage=(acquired.components.claim_term_coverage),
                                    document_specificity=(acquired.components.document_specificity),
                                    evidence_language=acquired.components.evidence_language,
                                    penalties=(acquired.components.generic_or_promotional_penalty),
                                )
                                if acquired is not None
                                else None
                            ),
                        )
                    )
    return ResearchTrail(
        run_id=run_id,
        items=tuple(
            sorted(
                items,
                key=lambda item: (
                    item.research_round,
                    item.stance,
                    item.score is None,
                    -(item.score or 0),
                    item.url,
                ),
            )
        ),
    )


def _v2_research_trail_items(connection: Connection, run_id: UUID) -> tuple[ResearchTrailItem, ...]:
    """Project persisted v2 discovery and acquisition artifacts into the trail contract."""
    items: list[ResearchTrailItem] = []
    decision_map = {
        "retrieve": "selected",
        "maybe": "deferred",
        "skip": "discarded",
    }
    for research_round in (1, 2, 3, 4):
        discovery_key = (
            V2_SCOUT_ARTIFACT_KEY
            if research_round == 1
            else (
                "post-phase-13-round-4-discovery-scout-v1"
                if research_round == 4
                else f"phase-7-round-{research_round}-discovery-scout"
            )
        )
        acquisition_key = (
            V2_ACQUISITION_PROBE_ARTIFACT_KEY
            if research_round == 1
            else (
                "post-phase-13-round-4-acquisition-probe-v1"
                if research_round == 4
                else f"phase-7-round-{research_round}-acquisition-probe"
            )
        )
        try:
            artifact = read_v2_artifact(connection, run_id, discovery_key)
        except KeyError:
            continue
        discovery = V2DiscoveryScoutOutput.model_validate_json(artifact.payload_json)
        try:
            acquisition_artifact = read_v2_artifact(connection, run_id, acquisition_key)
        except KeyError:
            acquisition = None
        else:
            acquisition = V2AcquisitionProbeOutput.model_validate_json(
                acquisition_artifact.payload_json
            )
        decisions = {
            scout_item.item_id: scout_item.decision.value
            for batch in discovery.scout_batches
            for scout_item in batch.items
        }
        cluster_by_item = {
            item_id: cluster.cluster_id
            for cluster in discovery.clusters
            for item_id in cluster.item_ids
        }
        acquired_clusters = (
            {source.cluster_id for source in acquisition.acquisitions}
            if acquisition is not None
            else set()
        )
        attempted_clusters = (
            {attempt.cluster_id for attempt in acquisition.attempts}
            if acquisition is not None
            else set()
        )
        for discovery_item in discovery.items:
            decision = decisions.get(discovery_item.item_id)
            if decision is None:
                continue
            cluster_id = cluster_by_item.get(discovery_item.item_id)
            acquisition_state: Literal["acquired", "attempted", "not_attempted"]
            if cluster_id in acquired_clusters:
                acquisition_state = "acquired"
            elif cluster_id in attempted_clusters:
                acquisition_state = "attempted"
            else:
                acquisition_state = "not_attempted"
            items.append(
                ResearchTrailItem(
                    research_round=research_round,
                    stance=(
                        "supporting" if discovery_item.direction.value == "support" else "opposing"
                    ),
                    provider=discovery_item.provider,
                    intent="v2 discovery",
                    query_text=discovery_item.query_text,
                    title=discovery_item.title or "",
                    url=discovery_item.canonical_url,
                    decision=decision_map[decision],
                    acquisition_state=acquisition_state,
                )
            )
    return tuple(items)


def _history_item(manifest: RunManifest) -> LiveHistoryItem:
    return LiveHistoryItem(
        run_id=manifest.run_id,
        raw_claim=manifest.raw_claim,
        status=manifest.status.value,
        stage=manifest.current_stage.value,
        updated_at=manifest.updated_at.isoformat(),
        completed_at=manifest.completed_at.isoformat() if manifest.completed_at else None,
    )
