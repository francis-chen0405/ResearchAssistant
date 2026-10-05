"""Persisted progress and budget projections for current and historical runs."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection
from typing import Literal
from uuid import UUID

from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY
from agents.v2_adaptive_search import V2PlanningAttempt
from agents.v2_discovery import V2_SCOUT_ARTIFACT_KEY
from agents.v2_evidence_analyst import (
    V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
    V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX,
)
from agents.v2_final_output import render_v2_final_output
from agents.v2_source_selection import (
    V2_SOURCE_SELECTION_COMPLETION_KEY,
    V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY,
)
from frontend.live_contracts import (
    LiveClassification,
    LiveCostBasisCount,
    LiveModelUsageDetails,
    LiveRunSnapshot,
    LiveTokenCount,
    ResearchProgress,
)
from providers.v2_budget import (
    V2BudgetSnapshot,
    V2RunCeilings,
    read_v2_physical_call_audit,
)
from researchassistant.common.money import add_usd
from researchassistant.contracts.models import (
    DEFAULT_RESEARCH_CONTROLS,
    DiscoveryProvider,
    ModelUsageCostBasis,
    ResearchControls,
    ResearchDirection,
    ResearchDirections,
    ResearchMode,
    RunStatus,
    Stage,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2EvidenceAnalystSourceResult,
    V2PersistedArtifact,
    V2ResultSource,
    V2ResultSourceStatus,
    V2RunDiagnostics,
    V2SourceSelectionQueueResult,
)
from researchassistant.research.orchestrator import (
    ProviderPipelineResult,
    ProviderRunStatus,
)
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_FINGERPRINT_KEY,
    V2_PRODUCTION_LEGACY_FINGERPRINT_KEY,
    V2_PRODUCTION_PHASE13_FINGERPRINT_KEY,
    V2ProductionFingerprint,
    V2ProductionPipelineResult,
    V2ProductionState,
    build_v2_run_diagnostics_or_empty,
    configured_v2_providers,
    infer_v2_stage,
)
from researchassistant.runtime.application_runtime import CLIExitCode
from researchassistant.storage.store import (
    read_provider_run_contract,
    read_run,
    read_v2_artifact,
)


class V2LiveUsageSummary(StrictModel):
    """Exact known usage and conservative exposure from one physical-call audit."""

    physical_calls_used: int
    total_tokens: int | None
    total_cost_usd: Decimal | None
    known_token_subtotal: int
    known_cost_subtotal_usd: Decimal
    token_usage_complete: bool
    cost_usage_complete: bool
    conservative_reserved_tokens: int
    conservative_reserved_cost_usd: Decimal
    model_usage_details: LiveModelUsageDetails


def _live_token_count(subtotal: int, complete: bool) -> LiveTokenCount:
    return LiveTokenCount(
        total=subtotal if complete else None,
        known_subtotal=subtotal,
        complete=complete,
    )


def _read_first_v2_artifact(
    db_path: str | Path | Connection,
    run_id: UUID,
    artifact_keys: tuple[str, ...],
) -> V2PersistedArtifact:
    """Read the newest key first while preserving access to historical v2 artifacts."""
    for artifact_key in artifact_keys:
        try:
            return read_v2_artifact(db_path, run_id, artifact_key)
        except KeyError:
            continue
    raise KeyError(f"none of the v2 artifacts exist for run {run_id}: {artifact_keys}")


def exit_code_for_status(status: ProviderRunStatus) -> CLIExitCode:
    if status is ProviderRunStatus.RELEASED:
        return CLIExitCode.RELEASED
    if status is ProviderRunStatus.BLOCKED:
        return CLIExitCode.BLOCKED
    if status is ProviderRunStatus.FAILED:
        return CLIExitCode.FAILED
    if status is ProviderRunStatus.CANCELLED:
        return CLIExitCode.CANCELLED
    if status is ProviderRunStatus.RUNNING:
        return CLIExitCode.RUNNING
    raise ValueError(f"unsupported provider run status: {status!r}")


def _research_progress(
    result: ProviderPipelineResult,
    stance: Literal["supporting", "opposing"],
) -> ResearchProgress:
    if result.researcher_result is None:
        status = "running" if result.status is ProviderRunStatus.RUNNING else "not available"
        return ResearchProgress(
            stance=stance,
            status=status,
            model_attempts=0,
            retrieval_attempts=0,
            usable_snapshots=0,
            candidates=0,
        )
    side = getattr(result.researcher_result, stance)
    outcomes = side.retrieval_batch.outcomes if side.retrieval_batch is not None else ()
    usable = sum(1 for outcome in outcomes if outcome.snapshot_id is not None)
    stance_artifact_ids = {candidate.quote_block_id for candidate in side.candidates}
    if side.retrieval_batch is not None:
        stance_artifact_ids.update(
            snapshot.snapshot_id for snapshot in side.retrieval_batch.snapshots
        )
    attempts = sum(
        1
        for attempt in result.model_attempts
        if any(artifact_id in stance_artifact_ids for artifact_id in attempt.input_artifact_ids)
    )
    return ResearchProgress(
        stance=stance,
        status=side.status.value,
        model_attempts=attempts,
        retrieval_attempts=len(outcomes),
        usable_snapshots=usable,
        candidates=len(side.candidates),
    )


def _empty_progress(stance: Literal["supporting", "opposing"]) -> ResearchProgress:
    return ResearchProgress(
        stance=stance,
        status="not started",
        model_attempts=0,
        retrieval_attempts=0,
        usable_snapshots=0,
        candidates=0,
    )


def _v2_research_progress(
    sources: tuple[V2ResultSource, ...],
    stance: Literal["supporting", "opposing"],
    enabled: bool,
) -> ResearchProgress:
    direction = "support" if stance == "supporting" else "challenge"
    matching = tuple(source for source in sources if source.direction.value == direction)
    analyzed_statuses = {
        V2ResultSourceStatus.RECOMMENDED_ANALYZED,
        V2ResultSourceStatus.RECOMMENDED_ANALYZER_ADMITTED,
        V2ResultSourceStatus.RECOMMENDED_ANALYZER_REJECTED,
        V2ResultSourceStatus.RECOMMENDED_ANALYZER_FAILED,
        V2ResultSourceStatus.SURVIVING_ANALYZED,
        V2ResultSourceStatus.SURVIVING_ANALYZER_ADMITTED,
        V2ResultSourceStatus.SURVIVING_ANALYZER_REJECTED,
        V2ResultSourceStatus.SURVIVING_ANALYZER_FAILED,
    }
    analyzed = sum(source.status in analyzed_statuses for source in matching)
    return ResearchProgress(
        stance=stance,
        status="completed" if enabled else "disabled",
        model_attempts=analyzed,
        retrieval_attempts=0,
        usable_snapshots=len(matching),
        candidates=analyzed,
    )


def _read_v2_directions(db_path: str | Path | Connection, run_id: UUID) -> ResearchDirections:
    try:
        artifact = _read_first_v2_artifact(
            db_path,
            run_id,
            (
                V2_PRODUCTION_FINGERPRINT_KEY,
                V2_PRODUCTION_PHASE13_FINGERPRINT_KEY,
                V2_PRODUCTION_LEGACY_FINGERPRINT_KEY,
            ),
        )
        fingerprint = V2ProductionFingerprint.model_validate_json(artifact.payload_json)
        payload = json.loads(fingerprint.canonical_payload_json)
        return ResearchDirections.model_validate(payload["directions"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ResearchDirections()


def _read_v2_budget_snapshot(
    db_path: str | Path | Connection,
    run_id: UUID,
) -> V2BudgetSnapshot:
    """Return conservative budget exposure from the authoritative call audit."""
    ceilings = _read_v2_ceilings(db_path, run_id)
    audit = read_v2_physical_call_audit(db_path, run_id)
    token_exposure = 0
    cost_exposure = Decimal("0")
    for start, completion in zip(audit.starts, audit.completions, strict=True):
        token_exposure += (
            completion.usage_tokens
            if completion is not None and completion.usage_tokens is not None
            else start.reserved_tokens
        )
        cost_exposure = add_usd(
            cost_exposure,
            (
                completion.usage_cost_usd
                if completion is not None and completion.usage_cost_usd is not None
                else start.reserved_cost_usd
            ),
        )
    return V2BudgetSnapshot(
        physical_calls_used=len(audit.starts),
        token_exposure=token_exposure,
        cost_exposure_usd=cost_exposure,
        physical_calls_remaining=max(0, ceilings.max_physical_calls - len(audit.starts)),
        tokens_remaining=max(0, ceilings.max_total_tokens - token_exposure),
        cost_remaining_usd=max(Decimal("0"), ceilings.max_total_cost_usd - cost_exposure),
    )


def _read_v2_usage_summary(
    db_path: str | Path | Connection,
    run_id: UUID,
    *,
    terminal: bool,
) -> V2LiveUsageSummary:
    """Summarize known usage separately from reserved exposure for live presentation."""
    audit = read_v2_physical_call_audit(db_path, run_id)
    known_tokens = 0
    known_cost = Decimal("0")
    token_complete = True
    cost_complete = True
    token_exposure = 0
    cost_exposure = Decimal("0")
    detail_subtotals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
    }
    detail_complete = {field: True for field in detail_subtotals}
    basis_counts: dict[ModelUsageCostBasis | None, int] = {}
    for start, completion in zip(audit.starts, audit.completions, strict=True):
        basis = completion.usage_cost_basis if completion is not None else None
        basis_counts[basis] = basis_counts.get(basis, 0) + 1
        for field in detail_subtotals:
            value = getattr(completion, field) if completion is not None else None
            if value is None:
                detail_complete[field] = False
            else:
                detail_subtotals[field] += value
        if completion is None or completion.usage_tokens is None:
            token_complete = False
            token_exposure += start.reserved_tokens
        else:
            known_tokens += completion.usage_tokens
            token_exposure += completion.usage_tokens
        if completion is None or completion.usage_cost_usd is None:
            cost_complete = False
            cost_exposure = add_usd(cost_exposure, start.reserved_cost_usd)
        else:
            known_cost = add_usd(known_cost, completion.usage_cost_usd)
            cost_exposure = add_usd(cost_exposure, completion.usage_cost_usd)
    token_complete = token_complete and terminal
    cost_complete = cost_complete and terminal
    details = LiveModelUsageDetails(
        input_tokens=_live_token_count(
            detail_subtotals["input_tokens"], terminal and detail_complete["input_tokens"]
        ),
        output_tokens=_live_token_count(
            detail_subtotals["output_tokens"], terminal and detail_complete["output_tokens"]
        ),
        cached_input_tokens=_live_token_count(
            detail_subtotals["cached_input_tokens"],
            terminal and detail_complete["cached_input_tokens"],
        ),
        cache_write_tokens=_live_token_count(
            detail_subtotals["cache_write_tokens"],
            terminal and detail_complete["cache_write_tokens"],
        ),
        cost_basis_counts=tuple(
            LiveCostBasisCount(basis=basis, physical_calls=count)
            for basis, count in sorted(
                basis_counts.items(),
                key=lambda item: (item[0] is not None, item[0].value if item[0] else ""),
            )
        ),
    )
    return V2LiveUsageSummary(
        physical_calls_used=len(audit.starts),
        total_tokens=known_tokens if token_complete else None,
        total_cost_usd=known_cost if cost_complete else None,
        known_token_subtotal=known_tokens,
        known_cost_subtotal_usd=known_cost,
        token_usage_complete=token_complete,
        cost_usage_complete=cost_complete,
        conservative_reserved_tokens=token_exposure,
        conservative_reserved_cost_usd=cost_exposure,
        model_usage_details=details,
    )


def _read_v2_ceilings(
    db_path: str | Path | Connection,
    run_id: UUID,
) -> V2RunCeilings:
    ceilings = V2RunCeilings()
    try:
        artifact = _read_first_v2_artifact(
            db_path,
            run_id,
            (
                V2_PRODUCTION_FINGERPRINT_KEY,
                V2_PRODUCTION_PHASE13_FINGERPRINT_KEY,
                V2_PRODUCTION_LEGACY_FINGERPRINT_KEY,
            ),
        )
        fingerprint = V2ProductionFingerprint.model_validate_json(artifact.payload_json)
        payload = json.loads(fingerprint.canonical_payload_json)
        ceilings = V2RunCeilings.model_validate(payload["ceilings"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return ceilings


def _v2_current_round(db_path: str | Path | Connection, run_id: UUID) -> int:
    for round_number in (4, 3, 2):
        for suffix in ("search-results", "discovery-scout", "acquisition-probe"):
            try:
                read_v2_artifact(
                    db_path,
                    run_id,
                    (
                        f"post-phase-13-round-4-{suffix}-v1"
                        if round_number == 4
                        else f"phase-7-round-{round_number}-{suffix}"
                    ),
                )
            except KeyError:
                continue
            return round_number
    return 1


def _read_v2_directional_progress(
    db_path: str | Path | Connection,
    run_id: UUID,
    directions: ResearchDirections,
    status: RunStatus,
    terminal_status: str | None = None,
    historical_attempt_count: int = 0,
) -> tuple[ResearchProgress, ResearchProgress, int]:
    attempts = dict.fromkeys((ResearchDirection.SUPPORT, ResearchDirection.CHALLENGE), 0)
    unassigned = 0
    acquisition_present = False
    acquired: dict[ResearchDirection, int] = {
        ResearchDirection.SUPPORT: 0,
        ResearchDirection.CHALLENGE: 0,
    }
    survivors: dict[ResearchDirection, set[UUID]] = {
        ResearchDirection.SUPPORT: set(),
        ResearchDirection.CHALLENGE: set(),
    }
    for round_number in (1, 2, 3, 4):
        artifact_key = (
            V2_ACQUISITION_PROBE_ARTIFACT_KEY
            if round_number == 1
            else "post-phase-13-round-4-acquisition-probe-v1"
            if round_number == 4
            else f"phase-7-round-{round_number}-acquisition-probe"
        )
        try:
            artifact = read_v2_artifact(db_path, run_id, artifact_key)
        except KeyError:
            continue
        acquisition_present = True
        output = V2AcquisitionProbeOutput.model_validate_json(artifact.payload_json)
        discovery_key = (
            V2_SCOUT_ARTIFACT_KEY
            if round_number == 1
            else "post-phase-13-round-4-discovery-scout-v1"
            if round_number == 4
            else f"phase-7-round-{round_number}-discovery-scout"
        )
        cluster_directions: dict[UUID, set[ResearchDirection]] = {}
        try:
            discovery_artifact = read_v2_artifact(db_path, run_id, discovery_key)
        except KeyError:
            pass
        else:
            discovery = V2DiscoveryScoutOutput.model_validate_json(discovery_artifact.payload_json)
            items = {item.item_id: item.direction for item in discovery.items}
            for cluster in discovery.clusters:
                # Missing members or mixed directions do not establish ownership.
                cluster_directions[cluster.cluster_id] = (
                    {items[item_id] for item_id in cluster.item_ids}
                    if cluster.item_ids and all(item_id in items for item_id in cluster.item_ids)
                    else set()
                )
        for source in output.acquisitions:
            acquired[source.direction] += 1
            if source.cluster_id not in cluster_directions:
                cluster_directions[source.cluster_id] = {source.direction}
            elif cluster_directions[source.cluster_id] != {source.direction}:
                cluster_directions[source.cluster_id] = set()
        # Count list entries, not unique clusters: fallback/retries are actual calls.
        for attempt in output.attempts:
            mapped = cluster_directions.get(attempt.cluster_id, set())
            if len(mapped) == 1:
                attempts[next(iter(mapped))] += 1
            else:
                unassigned += 1
        for survivor in output.survivors:
            survivors[survivor.direction].add(survivor.snapshot_id)

    # Some earlier terminal histories retain only their aggregate diagnostics.
    # Preserve that recorded count without inventing direction/round ownership.
    if not acquisition_present:
        unassigned = historical_attempt_count

    survivor_ids: dict[ResearchDirection, tuple[UUID, ...]] = {
        ResearchDirection.SUPPORT: (),
        ResearchDirection.CHALLENGE: (),
    }
    try:
        queue_artifact = _read_first_v2_artifact(
            db_path,
            run_id,
            (V2_SOURCE_SELECTION_COMPLETION_KEY, V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY),
        )
    except KeyError:
        pass
    else:
        from researchassistant.storage.historical_decode import decode_v2_artifact

        queue = decode_v2_artifact(queue_artifact, V2SourceSelectionQueueResult)
        survivor_ids = {
            direction: tuple(
                item.source_id for item in queue.input.survivors if item.direction is direction
            )
            for direction in (ResearchDirection.SUPPORT, ResearchDirection.CHALLENGE)
        }
    analyzed: dict[ResearchDirection, int] = {
        ResearchDirection.SUPPORT: 0,
        ResearchDirection.CHALLENGE: 0,
    }
    source_prefixes = (
        V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
        V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX,
        "phase-9-luna-evidence-analyst-source",
    )
    for direction, source_ids in survivor_ids.items():
        for source_id in source_ids:
            source_artifact = None
            for prefix in source_prefixes:
                try:
                    source_artifact = read_v2_artifact(
                        db_path,
                        run_id,
                        f"{prefix}-{source_id}",
                    )
                except KeyError:
                    continue
                break
            if source_artifact is None:
                continue
            source_result = V2EvidenceAnalystSourceResult.model_validate_json(
                source_artifact.payload_json
            )
            if source_result.state.value != "not_queued":
                analyzed[direction] += 1

    def build_progress(direction: ResearchDirection) -> ResearchProgress:
        enabled = directions.permits(direction)
        terminal = status is not RunStatus.RUNNING
        direction_status = (
            terminal_status
            if terminal and terminal_status is not None
            else ("completed" if terminal else "running")
        )
        return ResearchProgress(
            stance="supporting" if direction is ResearchDirection.SUPPORT else "opposing",
            status="disabled" if not enabled else direction_status,
            model_attempts=analyzed[direction],
            retrieval_attempts=attempts[direction],
            acquired_sources=acquired[direction],
            usable_snapshots=len(survivors[direction]),
            candidates=analyzed[direction],
        )

    return (
        build_progress(ResearchDirection.SUPPORT),
        build_progress(ResearchDirection.CHALLENGE),
        unassigned,
    )


def _v2_progress_percent(
    stage: Stage,
    current_round: int,
    diagnostics: V2RunDiagnostics,
    budget: V2BudgetSnapshot,
    supporting: ResearchProgress,
    opposing: ResearchProgress,
) -> int:
    stage_value = stage.value
    base = {
        "claim_planner": 4,
        "discovery": 12,
        "acquisition": 25,
        "gap_analysis": 39,
        "adaptive_search": 50,
        "source_selection": 63,
        "deep_analysis": 70,
        "evidence_analyst": 70,
        "evidence_admission": 85,
        "review": 85,
        "statement_reviewer": 85,
        "claim_ledger": 87,
        "debate_synthesizer": 92,
        "synthesis": 92,
        "final_renderer_validator": 97,
    }.get(stage_value, 5)
    analyzed = supporting.candidates + opposing.candidates
    if stage_value in {"adaptive_search", "source_selection"}:
        activity = min(9, budget.physical_calls_used // 2)
        return min(69 if stage_value == "source_selection" else 61, base + activity)
    if stage_value in {"deep_analysis", "evidence_analyst"}:
        queued = max(1, diagnostics.sources_queued_for_analysis)
        return min(84, base + round(14 * min(1.0, analyzed / queued)))
    if stage_value in {"evidence_admission", "statement_reviewer", "claim_ledger"}:
        return min(90, base + min(3, diagnostics.approved_evidence_records))
    if current_round > 1:
        return min(87, base + (current_round - 1) * 2)
    return base


def _research_round_and_progress(result: ProviderPipelineResult) -> tuple[int, int]:
    checkpoint_keys = {checkpoint.stage_key for checkpoint in result.checkpoints}
    if any(key.startswith("mvp11-round-three") for key in checkpoint_keys):
        current_round = 3
    elif any(key.startswith("mvp11-round-two") for key in checkpoint_keys):
        current_round = 2
    else:
        current_round = 1
    if result.status is not ProviderRunStatus.RUNNING:
        return current_round, 100
    if result.current_stage.value in {"debate_synthesizer", "final_renderer_validator"}:
        return current_round, 88 if result.current_stage.value == "debate_synthesizer" else 96
    stage_progress = {
        "claim_planner": 10,
        "supporting_researcher": 28,
        "opposing_researcher": 34,
        "evidence_analyst": 52,
        "evidence_admission": 58,
        "statement_reviewer": 58,
        "claim_ledger": 62,
    }.get(result.current_stage.value, 5)
    round_floor = {1: 0, 2: 62, 3: 76}[current_round]
    round_span = {1: 1.0, 2: 0.18, 3: 0.12}[current_round]
    return current_round, min(
        87, max(round_floor, round_floor + round(stage_progress * round_span))
    )


def _result_message(result: ProviderPipelineResult) -> str:
    if result.status is ProviderRunStatus.RELEASED:
        return "Released after deterministic validation. Human review is still required."
    if result.status is ProviderRunStatus.BLOCKED:
        return "Blocked by the deterministic final validator; no brief or hash was released."
    if result.status is ProviderRunStatus.CANCELLED:
        return (
            f"Cancelled at the cooperative {result.current_stage.value} boundary. "
            "An already active request was allowed to finish or reach its deadline."
        )
    if result.status is ProviderRunStatus.FAILED:
        return f"Failed in {result.current_stage.value}: {result.failure_reason}"
    if result.status is ProviderRunStatus.RUNNING:
        return f"Research is running in {result.current_stage.value}."
    raise ValueError(f"unsupported provider run status: {result.status!r}")


def adaptive_planning_message(
    db_path: str | Path | Connection,
    run_id: UUID,
    stage: Stage,
) -> str:
    """Expose bounded repair activity without query text or provider errors."""
    if stage is Stage.ADAPTIVE_SEARCH:
        for round_number in (3, 2):
            key = f"adaptive-reliability-round-{round_number}-attempt-2"
            try:
                started = read_v2_artifact(db_path, run_id, key)
            except KeyError:
                continue
            V2PlanningAttempt.model_validate_json(started.payload_json)
            try:
                read_v2_artifact(db_path, run_id, key + "-outcome")
            except KeyError:
                return "Refining follow-up searches."
    return f"Research is running in {stage.value}."


def _diagnostic_component(result: ProviderPipelineResult) -> str:
    if result.status is ProviderRunStatus.BLOCKED:
        return "validation"
    reason = (result.failure_reason or "").lower()
    if "searxng" in reason:
        return "searxng"
    if "wigolo" in reason:
        return "wigolo"
    if any(term in reason for term in ("retrieval", "acquisition", "source", "scrape")):
        return "retrieval"
    if any(term in reason for term in ("mimo", "xiaomi", "model", "llm")):
        return "mimo"
    if "validat" in reason:
        return "validation"
    return result.current_stage.value


def snapshot_from_v2_progress(
    db_path: str,
    run_id: UUID,
    providers: tuple[DiscoveryProvider, ...],
    *,
    source: str | Path | Connection | None = None,
) -> LiveRunSnapshot:
    """Build a v2 live snapshot using only persisted run data."""
    read_source = source if source is not None else db_path
    from researchassistant.storage.store import open_read_only_store, read_snapshot_connection

    if not isinstance(read_source, Connection):
        with open_read_only_store(read_source) as store:
            return snapshot_from_v2_progress(db_path, run_id, providers, source=store.connection)
    if not read_source.in_transaction:
        with read_snapshot_connection(read_source):
            return snapshot_from_v2_progress(db_path, run_id, providers, source=read_source)
    manifest = read_run(read_source, run_id)
    directions = _read_v2_directions(read_source, run_id)
    diagnostics = build_v2_run_diagnostics_or_empty(read_source, run_id, providers)
    budget = _read_v2_budget_snapshot(read_source, run_id)
    terminal = manifest.status is not RunStatus.RUNNING
    usage = _read_v2_usage_summary(read_source, run_id, terminal=terminal)
    stage = infer_v2_stage(read_source, run_id, manifest.current_stage, False)
    current_round = _v2_current_round(read_source, run_id)
    contract = None
    try:
        contract = read_provider_run_contract(read_source, run_id)
    except KeyError:
        pass
    classification: LiveClassification = {
        RunStatus.PLANNED: "starting",
        RunStatus.RUNNING: "running",
        RunStatus.COMPLETED: "released",
        RunStatus.BLOCKED: "blocked",
        RunStatus.CANCELLED: "cancelled",
        RunStatus.FAILED: "failed",
    }[manifest.status]
    exit_code = CLIExitCode.RUNNING if manifest.status is RunStatus.RUNNING else None
    if manifest.status is RunStatus.FAILED:
        exit_code = CLIExitCode.FAILED
    elif manifest.status is RunStatus.BLOCKED:
        exit_code = CLIExitCode.BLOCKED
    elif manifest.status is RunStatus.CANCELLED:
        exit_code = CLIExitCode.CANCELLED
    elif manifest.status is RunStatus.COMPLETED:
        exit_code = CLIExitCode.RELEASED
    supporting, opposing, unassigned = _read_v2_directional_progress(
        read_source,
        run_id,
        directions,
        manifest.status,
        terminal_status=classification if terminal else None,
    )
    return LiveRunSnapshot(
        run_id=run_id,
        db_path=db_path,
        raw_claim=manifest.raw_claim,
        classification=classification,
        exit_code=int(exit_code) if exit_code is not None else None,
        stage=stage.value,
        latest_checkpoint=stage.value,
        completed_checkpoints=0,
        total_checkpoints=10,
        current_research_round=current_round,
        progress_percent=_v2_progress_percent(
            stage, current_round, diagnostics, budget, supporting, opposing
        ),
        message=(
            adaptive_planning_message(read_source, run_id, stage)
            if manifest.status is RunStatus.RUNNING
            else f"Research is {classification}."
        ),
        diagnostic_component="v2-production",
        model_calls_used=usage.physical_calls_used,
        retrieval_attempts_used=supporting.retrieval_attempts
        + opposing.retrieval_attempts
        + unassigned,
        unassigned_retrieval_attempts_used=unassigned,
        total_tokens=usage.total_tokens,
        total_cost_usd=usage.total_cost_usd,
        known_token_subtotal=usage.known_token_subtotal,
        known_cost_subtotal_usd=usage.known_cost_subtotal_usd,
        token_usage_complete=usage.token_usage_complete,
        cost_usage_complete=usage.cost_usage_complete,
        conservative_reserved_tokens=usage.conservative_reserved_tokens,
        conservative_reserved_cost_usd=usage.conservative_reserved_cost_usd,
        model_usage_details=usage.model_usage_details,
        supporting=supporting,
        opposing=opposing,
        provider_identity=contract.provider_identity if contract is not None else None,
        model_identity=contract.model_identity if contract is not None else None,
        fingerprint=contract.fingerprint_sha256 if contract is not None else None,
        research_controls=ResearchControls(
            research_mode=(
                ResearchMode.BALANCED if directions.challenge_enabled else ResearchMode.FOCUSED
            ),
            discovery_providers=providers,
        ),
    )


def snapshot_from_v2_result(
    result: V2ProductionPipelineResult,
    *,
    source: str | Path | Connection | None = None,
    db_path: str | None = None,
) -> LiveRunSnapshot:
    """Build a terminal v2 live snapshot without constructing runtime services."""
    read_source = source if source is not None else result.db_path
    from researchassistant.storage.store import open_read_only_store, read_snapshot_connection

    if not isinstance(read_source, Connection):
        with open_read_only_store(read_source) as store:
            return snapshot_from_v2_result(result, source=store.connection, db_path=db_path)
    if not read_source.in_transaction:
        with read_snapshot_connection(read_source):
            return snapshot_from_v2_result(result, source=read_source, db_path=db_path)
    displayed_db_path = db_path if db_path is not None else result.db_path
    output = result.final_output
    directions = (
        output.directions if output is not None else _read_v2_directions(read_source, result.run_id)
    )
    sources = output.all_surviving_sources if output is not None else ()
    terminal_status = {
        V2ProductionState.RELEASED: RunStatus.COMPLETED,
        V2ProductionState.BLOCKED: RunStatus.BLOCKED,
        V2ProductionState.FAILED: RunStatus.FAILED,
        V2ProductionState.CANCELLED: RunStatus.CANCELLED,
    }[result.state]
    classification: LiveClassification = result.state.value
    usage = _read_v2_usage_summary(read_source, result.run_id, terminal=True)
    diagnostics = result.diagnostics
    if diagnostics is None:
        providers = configured_v2_providers(read_source, result.run_id)
        if providers:
            diagnostics = build_v2_run_diagnostics_or_empty(
                read_source, result.run_id, providers, final_output=output
            )
    stage = infer_v2_stage(read_source, result.run_id, result.current_stage, output is not None)
    supporting, opposing, unassigned = _read_v2_directional_progress(
        read_source,
        result.run_id,
        directions,
        terminal_status,
        terminal_status=classification,
        historical_attempt_count=diagnostics.acquisition_attempts if diagnostics else 0,
    )
    if output is not None:
        # Final evidence supplies analyzed/usable metrics; provider attempts still
        # come from persisted acquisition rounds, including failed-only clusters.
        for stance in ("supporting", "opposing"):
            final_progress = _v2_research_progress(
                sources,
                stance,
                directions.support_enabled
                if stance == "supporting"
                else directions.challenge_enabled,
            )
            persisted = supporting if stance == "supporting" else opposing
            final_progress = final_progress.model_copy(
                update={
                    "retrieval_attempts": persisted.retrieval_attempts,
                    "acquired_sources": persisted.acquired_sources,
                }
            )
            if stance == "supporting":
                supporting = final_progress
            else:
                opposing = final_progress
    exit_code = {
        V2ProductionState.RELEASED: CLIExitCode.RELEASED,
        V2ProductionState.BLOCKED: CLIExitCode.BLOCKED,
        V2ProductionState.FAILED: CLIExitCode.FAILED,
        V2ProductionState.CANCELLED: CLIExitCode.CANCELLED,
    }[result.state]
    return LiveRunSnapshot(
        run_id=result.run_id,
        db_path=displayed_db_path,
        raw_claim=result.raw_claim,
        classification=classification,
        exit_code=int(exit_code),
        stage=stage.value,
        latest_checkpoint=V2_PRODUCTION_ARTIFACT_KEY,
        completed_checkpoints=10,
        total_checkpoints=10,
        current_research_round=(
            output.stopping.completed_rounds
            if output is not None
            else _v2_current_round(read_source, result.run_id)
        ),
        progress_percent=100,
        message=(
            "Research completed and passed release validation."
            if result.state is V2ProductionState.RELEASED
            else result.failure_reason or "Research stopped before release."
        ),
        diagnostic_component="v2-production",
        model_calls_used=usage.physical_calls_used,
        retrieval_attempts_used=supporting.retrieval_attempts
        + opposing.retrieval_attempts
        + unassigned,
        unassigned_retrieval_attempts_used=unassigned,
        total_tokens=usage.total_tokens,
        total_cost_usd=usage.total_cost_usd,
        known_token_subtotal=usage.known_token_subtotal,
        known_cost_subtotal_usd=usage.known_cost_subtotal_usd,
        token_usage_complete=usage.token_usage_complete,
        cost_usage_complete=usage.cost_usage_complete,
        conservative_reserved_tokens=usage.conservative_reserved_tokens,
        conservative_reserved_cost_usd=usage.conservative_reserved_cost_usd,
        model_usage_details=usage.model_usage_details,
        supporting=supporting,
        opposing=opposing,
        validation_errors=(
            tuple(error.message for error in output.release_validation.errors)
            if output is not None
            else ()
        ),
        final_brief=(
            render_v2_final_output(output)
            if output is not None and output.release_validation.valid
            else None
        ),
        rendered_brief_hash=(
            output.release_validation.rendered_output_hash if output is not None else None
        ),
        research_controls=ResearchControls(
            research_mode=(
                ResearchMode.BALANCED if directions.challenge_enabled else ResearchMode.FOCUSED
            ),
            discovery_providers=(
                diagnostics.configured_providers
                if diagnostics is not None
                else DEFAULT_RESEARCH_CONTROLS.discovery_providers
            ),
        ),
        v2_diagnostics=diagnostics,
    )
