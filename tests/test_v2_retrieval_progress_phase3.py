from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from frontend.live_progress import _read_v2_directional_progress, snapshot_from_v2_progress
from providers.v2_budget import V2RunCeilings
from researchassistant.contracts.models import (
    DiscoveryProvenance,
    DiscoveryProvider,
    DiscoveryProviderReference,
    NormalizedDiscoveryItem,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    SourceCluster,
    SourceSnapshot,
    Stage,
    V2AcquiredSource,
    V2AcquisitionAttempt,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
    V2DiscoveryScoutOutput,
    V2PipelineIdentity,
    V2ProbeResult,
)
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_FINGERPRINT_KEY,
    V2ProductionFingerprint,
)
from researchassistant.storage.store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
)

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _init_run(db_path: str, run_id: UUID, status: RunStatus = RunStatus.RUNNING) -> None:
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=status,
            raw_claim="The regional program improves outcomes.",
            current_stage=Stage.ACQUISITION,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def _round_keys(round_number: int) -> tuple[str, str]:
    if round_number == 1:
        return "phase-4-discovery-scout", "phase-5-acquisition-probe"
    if round_number == 4:
        return (
            "post-phase-13-round-4-discovery-scout-v1",
            "post-phase-13-round-4-acquisition-probe-v1",
        )
    return (
        f"phase-7-round-{round_number}-discovery-scout",
        f"phase-7-round-{round_number}-acquisition-probe",
    )


def _discovery(
    run_id: UUID,
    round_number: int,
    directions: ResearchDirections,
    clusters: tuple[tuple[UUID, ResearchDirection | tuple[ResearchDirection, ...]], ...],
) -> V2DiscoveryScoutOutput:
    items = []
    source_clusters = []
    for index, (cluster_id, cluster_direction) in enumerate(clusters, start=1):
        member_directions = (
            cluster_direction if isinstance(cluster_direction, tuple) else (cluster_direction,)
        )
        item_ids = []
        query_ids = []
        provenance_chain = []
        for member_index, direction in enumerate(member_directions, start=1):
            item_id = uuid4()
            query_id = uuid4()
            url = f"https://example.test/{round_number}/{index}/{member_index}"
            provenance = DiscoveryProvenance(
                provider=DiscoveryProvider.EXA,
                query_id=query_id,
                query_text=f"round {round_number} query {index}/{member_index}",
                direction=direction,
                round_number=round_number,
                provider_rank=1,
                original_url=url,
            )
            items.append(
                NormalizedDiscoveryItem(
                    run_id=run_id,
                    item_id=item_id,
                    provider=DiscoveryProvider.EXA,
                    query_id=query_id,
                    query_text=provenance.query_text,
                    direction=direction,
                    round_number=round_number,
                    provider_rank=1,
                    source_url=url,
                    canonical_url=url,
                    provenance_chain=(provenance,),
                    discovered_at=NOW,
                )
            )
            item_ids.append(item_id)
            query_ids.append(query_id)
            provenance_chain.append(provenance)
        source_clusters.append(
            SourceCluster(
                cluster_id=cluster_id,
                preferred_url=f"https://example.test/{round_number}/{index}/1",
                canonical_url=f"https://example.test/{round_number}/{index}/1",
                item_ids=tuple(item_ids),
                provider_references=tuple(
                    DiscoveryProviderReference(
                        provider=DiscoveryProvider.EXA,
                        item_id=item_id,
                        provider_rank=1,
                    )
                    for item_id in item_ids
                ),
                query_references=tuple(query_ids),
                metadata_provenance=tuple(provenance_chain),
            )
        )
    return V2DiscoveryScoutOutput(
        run_id=run_id,
        directions=directions,
        items=tuple(items),
        clusters=tuple(source_clusters),
        scout_batches=(),
        scout_audits=(),
        completed_at=NOW,
    )


def _attempt(
    cluster_id: UUID,
    *,
    succeeded: bool,
    provider: V2AcquisitionProvider,
) -> V2AcquisitionAttempt:
    return V2AcquisitionAttempt(
        cluster_id=cluster_id,
        url=f"https://example.test/{cluster_id}",
        provider=provider,
        succeeded=succeeded,
        failure_code=None if succeeded else "provider_failure",
        failure_message=None if succeeded else "fixture failure",
    )


def _snapshot(run_id: UUID, cluster_id: UUID) -> SourceSnapshot:
    text = "A sufficiently long evidence source text for a successful provider acquisition."
    return SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url=f"https://example.test/{cluster_id}",
        retrieved_at=NOW,
        normalized_text=text,
        snapshot_sha256=sha256(text.encode()).hexdigest(),
        word_count=len(text.split()),
        truncated=False,
        created_at=NOW,
    )


def _acquisition(
    run_id: UUID,
    directions: ResearchDirections,
    attempts: tuple[V2AcquisitionAttempt, ...],
    successful_clusters: tuple[UUID, ...] = (),
) -> V2AcquisitionProbeOutput:
    sources = tuple(
        V2AcquiredSource(
            cluster_id=cluster_id,
            direction=(
                ResearchDirection.SUPPORT
                if directions.support_enabled
                else ResearchDirection.CHALLENGE
            ),
            snapshot=_snapshot(run_id, cluster_id),
            provider=V2AcquisitionProvider.FIRECRAWL,
        )
        for cluster_id in successful_clusters
    )
    probes = tuple(
        V2ProbeResult(
            cluster_id=source.cluster_id,
            snapshot_id=source.snapshot.snapshot_id,
            snapshot_sha256=source.snapshot.snapshot_sha256,
            succeeded=True,
        )
        for source in sources
    )
    return V2AcquisitionProbeOutput(
        run_id=run_id,
        directions=directions,
        acquisitions=sources,
        attempts=attempts,
        probes=probes,
        survivors=(),
        completed_at=NOW,
    )


def _persist_round(
    db_path: str,
    run_id: UUID,
    round_number: int,
    directions: ResearchDirections,
    cluster_directions: tuple[tuple[UUID, ResearchDirection | tuple[ResearchDirection, ...]], ...],
    attempts: tuple[V2AcquisitionAttempt, ...],
    successful_clusters: tuple[UUID, ...] = (),
) -> None:
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)
    discovery_key, acquisition_key = _round_keys(round_number)
    insert_v2_artifact(
        db_path,
        discovery_key,
        _discovery(run_id, round_number, directions, cluster_directions),
        NOW,
    )
    insert_v2_artifact(
        db_path,
        acquisition_key,
        _acquisition(run_id, directions, attempts, successful_clusters),
        NOW,
    )


def _persist_fingerprint(db_path: str, run_id: UUID, directions: ResearchDirections) -> None:
    canonical_payload = json.dumps(
        {
            "directions": directions.model_dump(mode="json"),
            "ceilings": V2RunCeilings().model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    insert_v2_artifact(
        db_path,
        V2_PRODUCTION_FINGERPRINT_KEY,
        V2ProductionFingerprint(
            run_id=run_id,
            sha256=sha256(canonical_payload.encode()).hexdigest(),
            canonical_payload_json=canonical_payload,
            created_at=NOW,
        ),
        NOW,
    )


def test_progress_counts_failed_only_and_primary_plus_fallback_attempts(tmp_path: Path) -> None:
    db_path = str(tmp_path / "attempts.sqlite3")
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    failed_only_cluster = uuid4()
    fallback_cluster = uuid4()
    _init_run(db_path, run_id)
    _persist_round(
        db_path,
        run_id,
        1,
        directions,
        (
            (failed_only_cluster, ResearchDirection.SUPPORT),
            (fallback_cluster, ResearchDirection.SUPPORT),
        ),
        (
            _attempt(failed_only_cluster, succeeded=False, provider=V2AcquisitionProvider.WIGOLO),
            _attempt(fallback_cluster, succeeded=False, provider=V2AcquisitionProvider.WIGOLO),
            _attempt(fallback_cluster, succeeded=True, provider=V2AcquisitionProvider.FIRECRAWL),
        ),
        (fallback_cluster,),
    )

    supporting, opposing, unassigned = _read_v2_directional_progress(
        db_path, run_id, directions, RunStatus.RUNNING
    )

    assert supporting.retrieval_attempts == 3
    assert supporting.acquired_sources == 1
    assert supporting.usable_snapshots == 0
    assert supporting.status == "running"
    assert opposing.retrieval_attempts == 0
    assert opposing.status == "disabled"
    assert unassigned == 0


def test_progress_replays_rounds_one_through_four_without_direction_leakage(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "rounds.sqlite3")
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=True)
    _init_run(db_path, run_id)
    for round_number, direction in enumerate(
        (
            ResearchDirection.SUPPORT,
            ResearchDirection.CHALLENGE,
            ResearchDirection.SUPPORT,
            ResearchDirection.CHALLENGE,
        ),
        start=1,
    ):
        cluster_id = uuid4()
        attempt = _attempt(cluster_id, succeeded=False, provider=V2AcquisitionProvider.WIGOLO)
        _persist_round(
            db_path,
            run_id,
            round_number,
            directions,
            ((cluster_id, direction),),
            (attempt,),
        )

    first = _read_v2_directional_progress(db_path, run_id, directions, RunStatus.RUNNING)
    replay = _read_v2_directional_progress(db_path, run_id, directions, RunStatus.RUNNING)

    assert first == replay
    assert first[0].retrieval_attempts == 2
    assert first[1].retrieval_attempts == 2
    assert first[2] == 0
    terminal = _read_v2_directional_progress(
        db_path, run_id, directions, RunStatus.FAILED, terminal_status="failed"
    )
    assert terminal[0].status == "failed"
    assert terminal[1].status == "failed"
    assert terminal[0].retrieval_attempts == first[0].retrieval_attempts
    assert terminal[1].retrieval_attempts == first[1].retrieval_attempts


def test_unmappable_attempt_is_reported_unassigned_and_never_guessed(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "unassigned.sqlite3")
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    unknown_cluster = uuid4()
    _init_run(db_path, run_id)
    _persist_round(
        db_path,
        run_id,
        1,
        directions,
        (),
        (_attempt(unknown_cluster, succeeded=False, provider=V2AcquisitionProvider.WIGOLO),),
    )

    supporting, opposing, unassigned = _read_v2_directional_progress(
        db_path, run_id, directions, RunStatus.RUNNING
    )

    assert supporting.retrieval_attempts == 0
    assert opposing.retrieval_attempts == 0
    assert unassigned == 1


def test_acquired_source_direction_recovers_attempt_when_discovery_artifact_is_missing(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "acquisition-direction-fallback.sqlite3")
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    cluster_id = uuid4()
    _init_run(db_path, run_id)
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)
    _, acquisition_key = _round_keys(1)
    insert_v2_artifact(
        db_path,
        acquisition_key,
        _acquisition(
            run_id,
            directions,
            (_attempt(cluster_id, succeeded=True, provider=V2AcquisitionProvider.WIGOLO),),
            (cluster_id,),
        ),
        NOW,
    )

    supporting, opposing, unassigned = _read_v2_directional_progress(
        db_path, run_id, directions, RunStatus.RUNNING
    )

    assert supporting.retrieval_attempts == 1
    assert supporting.acquired_sources == 1
    assert opposing.retrieval_attempts == 0
    assert unassigned == 0


def test_mixed_cluster_directions_remain_unassigned_even_with_acquisition_source(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "mixed-directions.sqlite3")
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=True)
    cluster_id = uuid4()
    _init_run(db_path, run_id)
    _persist_round(
        db_path,
        run_id,
        1,
        directions,
        ((cluster_id, (ResearchDirection.SUPPORT, ResearchDirection.CHALLENGE)),),
        (_attempt(cluster_id, succeeded=True, provider=V2AcquisitionProvider.WIGOLO),),
        (cluster_id,),
    )

    supporting, opposing, unassigned = _read_v2_directional_progress(
        db_path, run_id, directions, RunStatus.RUNNING
    )

    assert supporting.retrieval_attempts == 0
    assert opposing.retrieval_attempts == 0
    assert supporting.acquired_sources == 1
    assert unassigned == 1


def test_snapshot_reports_unassigned_attempts_for_running_and_terminal_runs(
    tmp_path: Path,
) -> None:
    for status, expected_directional_status in (
        (RunStatus.RUNNING, "running"),
        (RunStatus.FAILED, "failed"),
    ):
        db_path = str(tmp_path / f"{status.value}.sqlite3")
        run_id = uuid4()
        directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
        unknown_cluster = uuid4()
        _init_run(db_path, run_id, status)
        _persist_round(
            db_path,
            run_id,
            1,
            directions,
            (),
            (_attempt(unknown_cluster, succeeded=False, provider=V2AcquisitionProvider.WIGOLO),),
        )
        _persist_fingerprint(db_path, run_id, directions)

        snapshot = snapshot_from_v2_progress(db_path, run_id, (DiscoveryProvider.EXA,))

        assert snapshot.retrieval_attempts_used == 1
        assert snapshot.unassigned_retrieval_attempts_used == 1
        assert snapshot.supporting.retrieval_attempts == 0
        assert snapshot.supporting.status == expected_directional_status
        assert snapshot.opposing.retrieval_attempts == 0
        assert snapshot.opposing.status == "disabled"
