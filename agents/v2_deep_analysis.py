"""Source-capped fresh-v2 deep analysis with deterministic survivor backfill."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict

from agents.v2_acquisition import V2AcquisitionProbeOutput
from agents.v2_discovery import V2DiscoveryScoutOutput
from agents.v2_evidence_admission import run_v2_evidence_admission
from agents.v2_evidence_analyst import run_v2_evidence_analyst
from agents.v2_extraction import (
    V2ExactExtractionResult,
    V2ExtractionState,
    run_v2_exact_extraction,
    snapshots_by_source,
)
from agents.v2_source_selection import _source_reservation
from models import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    StrictModel,
    V2DeepAnalysisBackfillResult,
    V2DeepAnalysisBudget,
    V2DeepAnalysisBudgetReason,
    V2DeepAnalysisSourceExecution,
    V2DeepAnalysisSourceExecutionState,
    V2DeepAnalysisSourceReconciliation,
    V2DeepAnalysisSourceStatus,
    V2DeepAnalysisTokenReservation,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionState,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystExtractionFailure,
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2LedgerProvenance,
    V2SourceSelectionCandidate,
    V2SourceSelectionQueueResult,
)
from money import add_usd
from providers.llm import LLMProvider
from providers.v2_budget import (
    V2_PHYSICAL_CALL_ARTIFACT_PREFIX,
    V2_PHYSICAL_CALL_LEGACY_ARTIFACT_PREFIX,
    V2BudgetExceededError,
    V2BudgetSnapshot,
    V2CancellationRequested,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
)
from providers.v2_routing import V2RoutingConfig
from store import insert_v2_artifact, read_v2_artifact

V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY = "phase-13-deep-analysis-backfill-analyzer-admission"


class V2DeepAnalysisWave(StrictModel):
    """All typed phase outputs for one source attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    extraction: V2ExactExtractionResult
    analyst: V2EvidenceAnalystBatchResult
    admission: V2EvidenceAdmissionBatchResult | None = None


def run_v2_deep_analysis_with_backfill(
    *,
    db_path: str | Path,
    queue_result: V2SourceSelectionQueueResult,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime] | None = None,
) -> V2DeepAnalysisBackfillResult:
    """Execute the initial queue and backfill terminal source failures in priority order."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    persisted = _read_backfill(path, queue_result.run_id)
    if persisted is not None:
        if persisted.final_queue_result.input != queue_result.input:
            raise ValueError("persisted deep-analysis backfill does not match Phase-8 input")
        return persisted
    if not queue_result.queued_source_ids:
        raise ValueError("deep-analysis backfill requires a non-empty initial queue")

    source_ids = tuple(item.source_id for item in queue_result.input.survivors)
    candidates = {item.source_id: item for item in queue_result.input.survivors}
    priority = queue_result.priority_source_ids or (
        *queue_result.queued_source_ids,
        *(source_id for source_id in source_ids if source_id not in queue_result.queued_source_ids),
    )
    admitted: list[UUID] = []
    attempted: dict[UUID, V2DeepAnalysisWave] = {}
    attempted_source_ids: list[UUID] = []
    executions: dict[UUID, V2DeepAnalysisSourceExecution] = {}
    terminal_reasons: list[str] = []

    for source_id in priority:
        if source_id in attempted:
            continue
        attempted_source_ids.append(source_id)
        try:
            wave = _run_source_wave(
                path=path,
                source_id=source_id,
                queue_result=_single_source_queue(queue_result, source_id, routing_config),
                discovery_outputs=discovery_outputs,
                acquisition_outputs=acquisition_outputs,
                llm_provider=llm_provider,
                routing_config=routing_config,
                clock=now,
            )
            attempted[source_id] = wave
            execution = _execution_from_wave(path, wave)
        except V2CancellationRequested:
            raise
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"[:1000]
            terminal_reasons.append(reason)
            execution = V2DeepAnalysisSourceExecution(
                source_id=source_id,
                state=(
                    V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
                    if isinstance(exc, V2BudgetExceededError)
                    else V2DeepAnalysisSourceExecutionState.ANALYST_FAILED
                ),
                failure_reason=reason,
            )
        executions[source_id] = execution
        if execution.state in {
            V2DeepAnalysisSourceExecutionState.ADMITTED,
            V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED,
        }:
            admitted.append(source_id)
        elif execution.failure_reason is not None:
            terminal_reasons.append(execution.failure_reason)
        if execution.state is V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED:
            break

    final_queue = _final_queue_result(
        queue_result,
        tuple(attempted_source_ids),
        routing_config,
        attempted_source_ids=tuple(attempted_source_ids),
    )
    final_analyst = _final_analyst_result(final_queue, attempted, tuple(attempted_source_ids))
    final_admission = run_v2_evidence_admission(
        db_path=path,
        analyst_result=final_analyst,
        clock=now,
    )
    source_executions = tuple(
        executions.get(
            source_id,
            V2DeepAnalysisSourceExecution(
                source_id=source_id,
                state=V2DeepAnalysisSourceExecutionState.NOT_ATTEMPTED,
            ),
        )
        for source_id in source_ids
    )
    reconciliations = tuple(
        _reconcile_source(
            path=path,
            run_id=queue_result.run_id,
            source_id=source_id,
            source_cost_cap=_source_reservation(routing_config.preflight(), candidates[source_id])[
                1
            ],
        )
        for source_id in source_ids
    )
    remaining = _remaining_budget(llm_provider, queue_result.initial_budget)
    result = V2DeepAnalysisBackfillResult(
        run_id=queue_result.run_id,
        original_queued_source_ids=queue_result.queued_source_ids,
        replacement_source_ids=tuple(
            source_id for source_id in admitted if source_id not in queue_result.queued_source_ids
        ),
        final_execution_order=tuple(attempted_source_ids),
        final_queue_result=final_queue,
        source_executions=source_executions,
        source_reconciliations=reconciliations,
        remaining_run_budget=remaining,
        final_admission_result=final_admission,
        terminal_reasons=tuple(dict.fromkeys(terminal_reasons)),
        completed_at=_aware(now()),
    )
    insert_v2_artifact(path, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY, result, result.completed_at)
    return result


def _run_source_wave(
    *,
    path: str,
    source_id: UUID,
    queue_result: V2SourceSelectionQueueResult,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
) -> V2DeepAnalysisWave:
    suffix = f"source-{source_id}"
    extraction = run_v2_exact_extraction(
        db_path=path,
        queue_result=queue_result,
        discovery_outputs=discovery_outputs,
        acquisition_outputs=acquisition_outputs,
        llm_provider=llm_provider,
        routing_config=routing_config,
        artifact_key=f"phase-13-exact-extraction-{suffix}",
        clock=clock,
    )
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=extraction.analyst_input(snapshots_by_source(acquisition_outputs)),
        llm_provider=llm_provider,
        routing_config=routing_config,
        artifact_key=f"phase-13-luna-evidence-analyst-batch-{suffix}",
        clock=clock,
    )
    admission = run_v2_evidence_admission(
        db_path=path,
        analyst_result=analyst,
        clock=clock,
        artifact_key=f"phase-13-evidence-admission-batch-{suffix}",
    )
    return V2DeepAnalysisWave(
        source_id=source_id,
        extraction=extraction,
        analyst=analyst,
        admission=admission,
    )


def _single_source_queue(
    original: V2SourceSelectionQueueResult,
    source_id: UUID,
    routing_config: V2RoutingConfig,
) -> V2SourceSelectionQueueResult:
    candidate = next(item for item in original.input.survivors if item.source_id == source_id)
    original_status = {item.source_id: item for item in original.source_statuses}
    statuses = tuple(
        _status_for_queue(
            original_status[item.source_id],
            queued=item.source_id == source_id,
            queue_rank=1 if item.source_id == source_id else None,
            replacement=item.source_id != source_id,
        )
        for item in original.input.survivors
    )
    tokens, cost = _queue_reservation((candidate,), routing_config)
    return original.model_copy(
        update={
            "priority_source_ids": original.priority_source_ids,
            "queued_source_ids": (source_id,),
            "source_statuses": statuses,
            "queue_capacity": 1,
            "physical_calls_after_reserve": (
                original.initial_budget.physical_calls_used
                + original.mandatory_synthesis_physical_calls
                + V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
            ),
            "total_reserved_tokens": tokens,
            "total_reserved_cost_usd": cost,
            "token_reservations": (
                V2DeepAnalysisTokenReservation(
                    source_id=source_id,
                    queue_size=1,
                    cumulative_reserved_tokens=tokens,
                    cumulative_reserved_cost_usd=cost,
                ),
            ),
            "limiting_reason": None,
        }
    )


def _final_queue_result(
    original: V2SourceSelectionQueueResult,
    admitted: tuple[UUID, ...],
    routing_config: V2RoutingConfig,
    attempted_source_ids: tuple[UUID, ...],
) -> V2SourceSelectionQueueResult:
    candidate_by_id = {item.source_id: item for item in original.input.survivors}
    candidates = tuple(candidate_by_id[source_id] for source_id in admitted)
    original_status = {item.source_id: item for item in original.source_statuses}
    statuses = tuple(
        _status_for_queue(
            original_status[item.source_id],
            queued=item.source_id in set(admitted),
            queue_rank=(admitted.index(item.source_id) + 1 if item.source_id in admitted else None),
            replacement=(
                item.source_id in set(attempted_source_ids)
                or item.source_id in set(original.queued_source_ids)
            ),
        )
        for item in original.input.survivors
    )
    tokens, cost = _queue_reservation(candidates, routing_config)
    return original.model_copy(
        update={
            "queued_source_ids": admitted,
            "source_statuses": statuses,
            "queue_capacity": len(admitted),
            "physical_calls_after_reserve": (
                original.initial_budget.physical_calls_used
                + original.mandatory_synthesis_physical_calls
                + len(admitted) * V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
            ),
            "total_reserved_tokens": tokens,
            "total_reserved_cost_usd": cost,
            "token_reservations": _reservation_points(candidates, routing_config),
            "limiting_reason": None,
        }
    )


def _status_for_queue(
    status: V2DeepAnalysisSourceStatus,
    *,
    queued: bool,
    queue_rank: int | None,
    replacement: bool = False,
) -> V2DeepAnalysisSourceStatus:
    return status.model_copy(
        update={
            "queued_for_deep_analysis": queued,
            "queue_rank": queue_rank,
            "budget_prevented_reason": (
                None
                if queued
                else V2DeepAnalysisBudgetReason.BACKFILL_REPLACED
                if replacement
                else status.budget_prevented_reason
            ),
        }
    )


def _queue_reservation(
    candidates: tuple[V2SourceSelectionCandidate, ...],
    routing_config: V2RoutingConfig,
) -> tuple[int, Decimal]:
    points = _reservation_points(candidates, routing_config)
    if not points:
        return 0, Decimal("0")
    return points[-1].cumulative_reserved_tokens, points[-1].cumulative_reserved_cost_usd


def _reservation_points(
    candidates: tuple[V2SourceSelectionCandidate, ...],
    routing_config: V2RoutingConfig,
) -> tuple[V2DeepAnalysisTokenReservation, ...]:
    preflight = routing_config.preflight()
    source_tokens = 0
    source_cost = Decimal("0")
    points: list[V2DeepAnalysisTokenReservation] = []
    for candidate in candidates:
        source_token_reserve, source_cost_reserve = _source_reservation(preflight, candidate)
        source_tokens += source_token_reserve
        source_cost = add_usd(source_cost, source_cost_reserve)
        points.append(
            V2DeepAnalysisTokenReservation(
                source_id=candidate.source_id,
                queue_size=len(points) + 1,
                cumulative_reserved_tokens=source_tokens,
                cumulative_reserved_cost_usd=source_cost,
            )
        )
    return tuple(points)


def _execution_from_wave(
    path: str,
    wave: V2DeepAnalysisWave,
) -> V2DeepAnalysisSourceExecution:
    extraction = wave.extraction.sources[0]
    analyst = next(item for item in wave.analyst.source_results if item.source_id == wave.source_id)
    admission = wave.admission
    if admission is None:
        raise ValueError("fresh deep-analysis waves require an evidence admission result")
    admitted = next(item for item in admission.source_results if item.source_id == wave.source_id)
    sequences = _physical_sequences(path, wave.extraction.run_id, wave.source_id)
    if extraction.state is V2ExtractionState.FAILED:
        extraction_failure = extraction.failure or "exact extraction failed"
        return V2DeepAnalysisSourceExecution(
            source_id=wave.source_id,
            state=(
                V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
                if "V2BudgetExceededError" in extraction_failure
                else V2DeepAnalysisSourceExecutionState.EXTRACTION_FAILED
            ),
            physical_call_sequences=sequences,
            failure_reason=extraction_failure,
        )
    if analyst.state is V2EvidenceAnalystState.REJECTED:
        return V2DeepAnalysisSourceExecution(
            source_id=wave.source_id,
            state=V2DeepAnalysisSourceExecutionState.ANALYST_REJECTED,
            physical_call_sequences=sequences,
            failure_reason="Analyst score rejected the source",
        )
    if analyst.state is V2EvidenceAnalystState.FAILED:
        analyst_failure = analyst.failure or "Analyst failed"
        return V2DeepAnalysisSourceExecution(
            source_id=wave.source_id,
            state=(
                V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
                if "V2BudgetExceededError" in analyst_failure
                else V2DeepAnalysisSourceExecutionState.ANALYST_FAILED
            ),
            physical_call_sequences=sequences,
            failure_reason=analyst_failure,
        )
    if admitted.state is V2EvidenceAdmissionState.ANALYZER_ADMITTED:
        return V2DeepAnalysisSourceExecution(
            source_id=wave.source_id,
            state=V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED,
            physical_call_sequences=sequences,
        )
    if admitted.state is V2EvidenceAdmissionState.ANALYST_REJECTED:
        return V2DeepAnalysisSourceExecution(
            source_id=wave.source_id,
            state=V2DeepAnalysisSourceExecutionState.ANALYST_REJECTED,
            physical_call_sequences=sequences,
            failure_reason="Deterministic admission retained the Analyst rejection",
        )
    admission_failure = admitted.failure or "Deterministic admission rejected the source"
    return V2DeepAnalysisSourceExecution(
        source_id=wave.source_id,
        state=(
            V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
            if "V2BudgetExceededError" in admission_failure
            else V2DeepAnalysisSourceExecutionState.ANALYST_FAILED
        ),
        physical_call_sequences=sequences,
        failure_reason=admission_failure,
    )


def _final_analyst_result(
    queue_result: V2SourceSelectionQueueResult,
    waves: dict[UUID, V2DeepAnalysisWave],
    attempted_source_ids: tuple[UUID, ...],
) -> V2EvidenceAnalystBatchResult:
    attempted = set(attempted_source_ids)
    source_results: list[V2EvidenceAnalystSourceResult] = []
    candidate_by_id: dict[UUID, V2EvidenceAnalystCandidateInput] = {}
    extraction_failures: dict[UUID, str] = {}
    for candidate in queue_result.input.survivors:
        if candidate.source_id in attempted:
            wave = waves.get(candidate.source_id)
            source_result = (
                next(
                    item
                    for item in wave.analyst.source_results
                    if item.source_id == candidate.source_id
                )
                if wave is not None
                else V2EvidenceAnalystSourceResult(
                    run_id=queue_result.run_id,
                    source_id=candidate.source_id,
                    direction=candidate.direction,
                    state=V2EvidenceAnalystState.FAILED,
                    failure="Deep analysis stopped before an Analyst result was produced.",
                )
            )
            source_results.append(source_result)
            candidate_input = (
                next(
                    (
                        item
                        for item in wave.analyst.input.queued_candidates
                        if item.source_id == candidate.source_id
                    ),
                    None,
                )
                if wave is not None
                else None
            )
            if candidate_input is not None:
                candidate_by_id[candidate.source_id] = candidate_input
            if wave is not None:
                for failure in wave.analyst.input.extraction_failures:
                    extraction_failures[failure.source_id] = failure.failure
        else:
            source_results.append(
                V2EvidenceAnalystSourceResult(
                    run_id=queue_result.run_id,
                    source_id=candidate.source_id,
                    direction=candidate.direction,
                    state=V2EvidenceAnalystState.NOT_QUEUED,
                )
            )
    return V2EvidenceAnalystBatchResult(
        run_id=queue_result.run_id,
        input=V2EvidenceAnalystBatchInput(
            run_id=queue_result.run_id,
            exact_claim=queue_result.input.exact_claim,
            directions=queue_result.input.directions,
            queue_result=queue_result,
            queued_candidates=tuple(
                candidate_by_id[source_id]
                for source_id in queue_result.queued_source_ids
                if source_id in candidate_by_id
            ),
            extraction_failures=tuple(
                V2EvidenceAnalystExtractionFailure(source_id=source_id, failure=failure)
                for source_id, failure in extraction_failures.items()
                if source_id in set(queue_result.queued_source_ids)
            ),
        ),
        source_results=tuple(source_results),
        completed_at=queue_result.completed_at,
    )


def _provenance(
    candidate: V2SourceSelectionCandidate,
    status: V2DeepAnalysisSourceStatus,
) -> V2LedgerProvenance:
    return V2LedgerProvenance(
        source_id=candidate.source_id,
        research_direction=candidate.direction,
        discovery_round=candidate.research_round,
        source_family_id=candidate.source_family_id,
        recommended=status.recommended,
        relevant_gap_ids=status.gap_ids,
    )


def _physical_sequences(path: str, run_id: UUID, source_id: UUID) -> tuple[int, ...]:
    starts, _completions = _read_source_audit(path, run_id, source_id)
    return tuple(item.sequence for item in starts)


def _reconcile_source(
    *,
    path: str,
    run_id: UUID,
    source_id: UUID,
    source_cost_cap: Decimal,
) -> V2DeepAnalysisSourceReconciliation:
    starts, completions = _read_source_audit(path, run_id, source_id)
    accounted_tokens = sum(
        completion.usage_tokens
        if completion is not None and completion.usage_tokens is not None
        else start.reserved_tokens
        for start, completion in zip(starts, completions, strict=True)
    )
    accounted_cost = add_usd(
        *(
            completion.usage_cost_usd
            if completion is not None and completion.usage_cost_usd is not None
            else start.reserved_cost_usd
            for start, completion in zip(starts, completions, strict=True)
        )
    )
    return V2DeepAnalysisSourceReconciliation(
        source_id=source_id,
        source_cap_cost_usd=source_cost_cap,
        accounted_tokens=accounted_tokens,
        released_tokens=max(0, V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP - accounted_tokens),
        accounted_cost_usd=accounted_cost,
        released_cost_usd=max(Decimal("0"), source_cost_cap - accounted_cost),
        physical_call_sequences=tuple(item.sequence for item in starts),
    )


def _read_source_audit(
    path: str,
    run_id: UUID,
    source_id: UUID,
) -> tuple[list[V2PhysicalCallStart], list[V2PhysicalCallCompletion | None]]:
    starts: list[V2PhysicalCallStart] = []
    completions: list[V2PhysicalCallCompletion | None] = []
    for sequence in range(1, 161):
        row = None
        for prefix in (V2_PHYSICAL_CALL_ARTIFACT_PREFIX, V2_PHYSICAL_CALL_LEGACY_ARTIFACT_PREFIX):
            try:
                row = read_v2_artifact(path, run_id, f"{prefix}-{sequence:03d}-start")
            except KeyError:
                continue
            break
        if row is None:
            break
        start = V2PhysicalCallStart.model_validate_json(row.payload_json)
        if start.source_id != source_id:
            continue
        completion_row = None
        for prefix in (V2_PHYSICAL_CALL_ARTIFACT_PREFIX, V2_PHYSICAL_CALL_LEGACY_ARTIFACT_PREFIX):
            try:
                completion_row = read_v2_artifact(
                    path, run_id, f"{prefix}-{sequence:03d}-completion"
                )
            except KeyError:
                continue
            break
        if completion_row is None:
            completion_row = None
        starts.append(start)
        completions.append(
            V2PhysicalCallCompletion.model_validate_json(completion_row.payload_json)
            if completion_row is not None
            else None
        )
    return starts, completions


def _remaining_budget(
    provider: LLMProvider,
    initial: V2DeepAnalysisBudget,
) -> V2DeepAnalysisBudget:
    snapshot_method = getattr(provider, "snapshot", None)
    snapshot = snapshot_method() if callable(snapshot_method) else None
    if isinstance(snapshot, V2BudgetSnapshot):
        return V2DeepAnalysisBudget(
            physical_call_ceiling=initial.physical_call_ceiling,
            physical_calls_used=snapshot.physical_calls_used,
            tokens_remaining=snapshot.tokens_remaining,
            cost_remaining_usd=snapshot.cost_remaining_usd,
        )
    return initial


def _read_backfill(path: str, run_id: UUID) -> V2DeepAnalysisBackfillResult | None:
    try:
        artifact = read_v2_artifact(path, run_id, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY)
    except KeyError:
        return None
    return V2DeepAnalysisBackfillResult.model_validate_json(artifact.payload_json)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("deep-analysis clock must return a timezone-aware datetime")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
