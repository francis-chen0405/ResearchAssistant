"""Read-only persisted history and research-trail projections; no worker ownership."""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection, IntegrityError
from typing import Literal, TypeVar
from uuid import UUID

from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY
from agents.v2_discovery import V2_SCOUT_ARTIFACT_KEY
from agents.v2_source_selection import (
    V2_SOURCE_SELECTION_COMPLETION_KEY,
    V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY,
)
from frontend.live_contracts import (
    AcquiredSourceScoreBreakdown,
    DiscoveryScoreBreakdown,
    LiveHistoryItem,
    ResearchTrail,
    ResearchTrailItem,
)
from researchassistant.contracts.historical import (
    RecordCompatibilityError,
    RecordCompatibilityResult,
)
from researchassistant.contracts.metadata_ranking import MetadataRank, V2MetadataRankingArtifact
from researchassistant.contracts.models import (
    RunManifest,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2SourceSelectionQueueResult,
)
from researchassistant.contracts.source_selection_preview import V2SelectionShortlistAudit
from researchassistant.research.orchestrator import (
    MVP10_TARGETED_RESEARCHERS_ARTIFACT,
    MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
    MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT,
    PHASE9_RESEARCHERS_ARTIFACT,
    ResearcherPairResult,
)
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
    infer_v2_stage,
)
from researchassistant.storage.store import (
    list_runs,
    open_read_only_store,
    read_provider_run_contract,
    read_run,
    read_stage_artifact,
    read_v2_artifact,
)

_InspectionT = TypeVar("_InspectionT", bound=StrictModel)


def _read_v2_inspection_result(
    connection: Connection,
    run_id: UUID,
    artifact_key: str,
    model_type: type[_InspectionT],
    compatibility_issues: list[RecordCompatibilityResult],
) -> tuple[_InspectionT | None, bool]:
    """Distinguish absent records from unsafe envelopes or unsupported payloads."""
    from researchassistant.storage.historical_decode import decode_v2_artifact

    try:
        artifact = read_v2_artifact(connection, run_id, artifact_key)
    except KeyError:
        return None, False
    except (ValueError, IntegrityError):
        compatibility_issues.append(
            RecordCompatibilityResult(
                record_key=artifact_key,
                artifact_type=model_type.__name__,
                message="stored artifact envelope or payload hash is invalid",
            )
        )
        return None, True
    try:
        return decode_v2_artifact(artifact, model_type), False
    except RecordCompatibilityError as exc:
        compatibility_issues.append(exc.result)
        return None, True


def history(db_path: str | Path, *, limit: int = 100) -> tuple[LiveHistoryItem, ...]:
    path = Path(db_path).resolve()
    if not path.is_file():
        return ()
    with open_read_only_store(path) as store:
        manifests = list_runs(store.connection, limit=limit)
        items: list[LiveHistoryItem] = []
        for manifest in manifests:
            compatibility_issues: list[RecordCompatibilityResult] = []
            result = None
            for artifact_key in (
                V2_PRODUCTION_ARTIFACT_KEY,
                V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
                V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
            ):
                result, incompatible = _read_v2_inspection_result(
                    store.connection,
                    manifest.run_id,
                    artifact_key,
                    V2ProductionPipelineResult,
                    compatibility_issues,
                )
                if result is not None or incompatible:
                    break
            if result is None:
                items.append(_history_item(manifest, tuple(compatibility_issues)))
                continue
            # A saved terminal result is authoritative even if the old writer crashed
            # before updating its manifest. Inspection must not require compatible resume.
            terminal_status = (
                "completed" if result.state is V2ProductionState.RELEASED else result.state.value
            )
            manifest_complete = (
                manifest.status.value == terminal_status and manifest.completed_at is not None
            )
            updated_at = manifest.updated_at if manifest_complete else result.completed_at
            completed_at = manifest.completed_at if manifest_complete else result.completed_at
            try:
                stage = infer_v2_stage(
                    store.connection,
                    manifest.run_id,
                    result.current_stage,
                    result.final_output is not None,
                )
            except (ValueError, IntegrityError):
                stage = result.current_stage
                compatibility_issues.append(
                    RecordCompatibilityResult(
                        record_key=str(manifest.run_id),
                        artifact_type=V2ProductionPipelineResult.__name__,
                        message="persisted artifacts do not permit safe stage reconstruction",
                    )
                )
            items.append(
                LiveHistoryItem(
                    run_id=manifest.run_id,
                    raw_claim=manifest.raw_claim,
                    status=terminal_status,
                    stage=stage.value,
                    updated_at=updated_at.isoformat(),
                    completed_at=completed_at.isoformat() if completed_at is not None else None,
                    compatibility_issues=tuple(compatibility_issues),
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
    compatibility_issues: list[RecordCompatibilityResult] = []
    with open_read_only_store(path) as store:
        # An existing database is not evidence that this particular run exists.
        read_run(store.connection, run_id)
        items.extend(_v2_research_trail_items(store.connection, run_id, compatibility_issues))
        for research_round, artifact_key in stage_keys:
            try:
                artifact = read_stage_artifact(store.connection, run_id, artifact_key)
            except KeyError:
                continue
            from researchassistant.storage.historical_decode import decode_native_artifact

            try:
                contract = read_provider_run_contract(store.connection, run_id)
            except KeyError:
                contract = None
            try:
                pair = decode_native_artifact(artifact, ResearcherPairResult, contract)
            except RecordCompatibilityError as exc:
                compatibility_issues.append(exc.result)
                continue
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
        compatibility_issues=tuple(compatibility_issues),
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


def _v2_research_trail_items(
    connection: Connection,
    run_id: UUID,
    compatibility_issues: list[RecordCompatibilityResult],
) -> tuple[ResearchTrailItem, ...]:
    """Project persisted v2 discovery and acquisition artifacts into the trail contract."""
    items: list[ResearchTrailItem] = []
    decision_map = {
        "retrieve": "selected",
        "maybe": "deferred",
        "skip": "discarded",
    }
    selection_result = _read_v2_selection_result(connection, run_id, compatibility_issues)
    selection_candidates = (
        {candidate.source_id: candidate for candidate in selection_result.input.survivors}
        if selection_result is not None
        else {}
    )
    selection_statuses = (
        {status.source_id: status for status in selection_result.source_statuses}
        if selection_result is not None
        else {}
    )
    shortlist, _ = _read_v2_inspection_result(
        connection,
        run_id,
        "source-selection-preview-shortlist-v2",
        V2SelectionShortlistAudit,
        compatibility_issues,
    )
    omitted = {row.source_id: row.reason for row in shortlist.omitted} if shortlist else {}
    included = set(shortlist.included_source_ids) if shortlist else set()
    invalid_selection_previews: set[UUID] = set()
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
        discovery, _ = _read_v2_inspection_result(
            connection, run_id, discovery_key, V2DiscoveryScoutOutput, compatibility_issues
        )
        acquisition, acquisition_incompatible = _read_v2_inspection_result(
            connection, run_id, acquisition_key, V2AcquisitionProbeOutput, compatibility_issues
        )
        metadata_ranking = _read_v2_metadata_ranking(
            connection, run_id, research_round, compatibility_issues
        )
        if discovery is None:
            continue
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
        probes_by_cluster = (
            {probe.cluster_id: probe for probe in acquisition.probes}
            if acquisition is not None
            else {}
        )
        for discovery_item in discovery.items:
            decision = decisions.get(discovery_item.item_id)
            if decision is None:
                continue
            cluster_id = cluster_by_item.get(discovery_item.item_id)
            candidate = selection_candidates.get(cluster_id) if cluster_id is not None else None
            selection_status = (
                selection_statuses.get(cluster_id) if cluster_id is not None else None
            )
            probe = probes_by_cluster.get(cluster_id) if cluster_id is not None else None
            selection_preview = candidate.preview if candidate is not None else None
            if selection_preview is not None:
                acquired_source = next(
                    (
                        source
                        for source in (acquisition.acquisitions if acquisition is not None else ())
                        if source.snapshot.snapshot_id == selection_preview.request.snapshot_id
                    ),
                    None,
                )
                try:
                    if acquired_source is None:
                        raise ValueError("selection preview has no matching acquired snapshot")
                    if (
                        acquisition is None
                        or acquired_source.cluster_id != selection_preview.request.source_id
                        or acquired_source.direction != selection_preview.request.direction
                        or acquisition.directions != selection_preview.request.directions
                    ):
                        raise ValueError("selection preview source/lane differs from acquisition")
                    selection_preview.require_snapshot(acquired_source.snapshot)
                except ValueError:
                    selection_preview = None
                    if cluster_id not in invalid_selection_previews:
                        compatibility_issues.append(
                            RecordCompatibilityResult(
                                record_key=V2_SOURCE_SELECTION_COMPLETION_KEY,
                                artifact_type=V2SourceSelectionQueueResult.__name__,
                                message="selection preview does not match its persisted snapshot",
                            )
                        )
                        invalid_selection_previews.add(cluster_id)
            preview = (
                selection_preview
                if selection_preview is not None
                else probe.preview
                if probe is not None
                else None
            )
            metadata_rank = (
                metadata_ranking.get(discovery_item.item_id)
                if metadata_ranking is not None
                else None
            )
            if metadata_rank is None and candidate is not None:
                metadata_rank = next(
                    (
                        rank
                        for rank in candidate.metadata_ranks
                        if rank.item_id == discovery_item.item_id
                    ),
                    None,
                )
            acquisition_state: Literal["acquired", "attempted", "not_attempted"] | None
            if acquisition_incompatible:
                acquisition_state = None
            elif cluster_id in acquired_clusters:
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
                    preview=preview,
                    selection_input_disposition="omitted_input_cap"
                    if cluster_id in omitted
                    else "included"
                    if cluster_id in included
                    else None,
                    selection_input_reason=omitted.get(cluster_id),
                    metadata_rank=metadata_rank,
                    selection_rationale=(
                        selection_status.selection_rationale
                        if selection_status is not None
                        else None
                    ),
                    source_selection_rank=(
                        selection_status.recommendation_rank
                        if selection_status is not None
                        else None
                    ),
                    source_selection_status=(
                        ("recommended" if selection_status.recommended else "not_recommended")
                        if selection_status is not None
                        else None
                    ),
                )
            )
    return tuple(items)


def _read_v2_metadata_ranking(
    connection: Connection,
    run_id: UUID,
    research_round: int,
    compatibility_issues: list[RecordCompatibilityResult],
) -> dict[UUID, MetadataRank] | None:
    """Read the optional per-round metadata rationale sidecar."""
    artifact, _incompatible = _read_v2_inspection_result(
        connection,
        run_id,
        f"phase-3-metadata-ranking-round-{research_round}",
        V2MetadataRankingArtifact,
        compatibility_issues,
    )
    if artifact is None:
        return None
    return {rank.item_id: rank for rank in artifact.ranks}


def _read_v2_selection_result(
    connection: Connection,
    run_id: UUID,
    compatibility_issues: list[RecordCompatibilityResult],
) -> V2SourceSelectionQueueResult | None:
    """Read current then historical completion keys without changing old artifacts."""
    for artifact_key in (
        V2_SOURCE_SELECTION_COMPLETION_KEY,
        V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY,
    ):
        result, incompatible = _read_v2_inspection_result(
            connection,
            run_id,
            artifact_key,
            V2SourceSelectionQueueResult,
            compatibility_issues,
        )
        if result is not None or incompatible:
            return result
    return None


def _history_item(
    manifest: RunManifest,
    compatibility_issues: tuple[RecordCompatibilityResult, ...] = (),
) -> LiveHistoryItem:
    return LiveHistoryItem(
        run_id=manifest.run_id,
        raw_claim=manifest.raw_claim,
        status=manifest.status.value,
        stage=manifest.current_stage.value,
        updated_at=manifest.updated_at.isoformat(),
        completed_at=manifest.completed_at.isoformat() if manifest.completed_at else None,
        compatibility_issues=compatibility_issues,
    )
