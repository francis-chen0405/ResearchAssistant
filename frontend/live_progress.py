"""Persisted progress and budget projections for current and historical runs."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection
from typing import Literal
from uuid import UUID

from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY
from agents.v2_evidence_analyst import (
    V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
    V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX,
)
from agents.v2_source_selection import (
    V2_SOURCE_SELECTION_COMPLETION_KEY,
    V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY,
)
from application_runtime import CLIExitCode
from frontend.live_contracts import (
    ResearchProgress,
)
from models import (
    ResearchDirection,
    ResearchDirections,
    RunStatus,
    Stage,
    V2AcquisitionProbeOutput,
    V2EvidenceAnalystSourceResult,
    V2PersistedArtifact,
    V2ResultSource,
    V2ResultSourceStatus,
    V2RunDiagnostics,
    V2SourceSelectionQueueResult,
)
from money import add_usd
from orchestrator import (
    ProviderPipelineResult,
    ProviderRunStatus,
)
from providers.v2_budget import (
    V2BudgetSnapshot,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2RunCeilings,
)
from store import (
    read_v2_artifact,
)
from v2_orchestrator import (
    V2_PRODUCTION_FINGERPRINT_KEY,
    V2_PRODUCTION_LEGACY_FINGERPRINT_KEY,
    V2_PRODUCTION_PHASE13_FINGERPRINT_KEY,
    V2ProductionFingerprint,
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
        retrieval_attempts=len(matching),
        usable_snapshots=len(matching),
        candidates=analyzed,
    )


def _read_v2_directions(db_path: str, run_id: UUID) -> ResearchDirections:
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


def _read_v2_budget_snapshot(db_path: str, run_id: UUID) -> V2BudgetSnapshot:
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

    starts: list[V2PhysicalCallStart] = []
    completions: dict[int, V2PhysicalCallCompletion] = {}
    for sequence in range(1, ceilings.max_physical_calls + 1):
        try:
            start_artifact = _read_first_v2_artifact(
                db_path,
                run_id,
                (
                    f"phase-13-physical-call-{sequence:03d}-start",
                    f"phase-12-physical-call-{sequence:03d}-start",
                ),
            )
        except KeyError:
            break
        start = V2PhysicalCallStart.model_validate_json(start_artifact.payload_json)
        starts.append(start)
        try:
            completion_artifact = _read_first_v2_artifact(
                db_path,
                run_id,
                (
                    f"phase-13-physical-call-{sequence:03d}-completion",
                    f"phase-12-physical-call-{sequence:03d}-completion",
                ),
            )
        except KeyError:
            continue
        completions[sequence] = V2PhysicalCallCompletion.model_validate_json(
            completion_artifact.payload_json
        )

    token_exposure = 0
    cost_exposure = Decimal("0")
    for start in starts:
        completion = completions.get(start.sequence)
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
        physical_calls_used=len(starts),
        token_exposure=token_exposure,
        cost_exposure_usd=cost_exposure,
        physical_calls_remaining=max(0, ceilings.max_physical_calls - len(starts)),
        tokens_remaining=max(0, ceilings.max_total_tokens - token_exposure),
        cost_remaining_usd=max(Decimal("0"), ceilings.max_total_cost_usd - cost_exposure),
    )


def _v2_current_round(db_path: str, run_id: UUID) -> int:
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
    db_path: str,
    run_id: UUID,
    directions: ResearchDirections,
    status: RunStatus,
) -> tuple[ResearchProgress, ResearchProgress]:
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
        output = V2AcquisitionProbeOutput.model_validate_json(artifact.payload_json)
        for source in output.acquisitions:
            acquired[source.direction] += 1
        for survivor in output.survivors:
            survivors[survivor.direction].add(survivor.snapshot_id)

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
        queue = V2SourceSelectionQueueResult.model_validate_json(queue_artifact.payload_json)
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
        return ResearchProgress(
            stance="supporting" if direction is ResearchDirection.SUPPORT else "opposing",
            status=("disabled" if not enabled else "completed" if terminal else "running"),
            model_attempts=analyzed[direction],
            retrieval_attempts=acquired[direction],
            usable_snapshots=len(survivors[direction]),
            candidates=analyzed[direction],
        )

    return build_progress(ResearchDirection.SUPPORT), build_progress(ResearchDirection.CHALLENGE)


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
