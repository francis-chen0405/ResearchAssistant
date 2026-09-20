"""Source-capped fresh-v2 deep analysis with deterministic survivor backfill."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from agents.v2_acquisition import V2AcquisitionProbeOutput
from agents.v2_discovery import V2DiscoveryScoutOutput
from agents.v2_evidence_admission import (
    V2_EVIDENCE_ADMISSION_SOURCE_ARTIFACT_PREFIX,
    V2_EVIDENCE_ADMISSION_SOURCE_LEGACY_PREFIX,
    run_v2_evidence_admission,
)
from agents.v2_evidence_analyst import (
    V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
    V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX,
    run_v2_evidence_analyst,
)
from agents.v2_extraction import (
    V2ExactExtractionResult,
    V2ExtractionState,
    run_v2_exact_extraction,
    snapshots_by_source,
)
from agents.v2_source_selection import _source_reservation
from models import (
    V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
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
from providers.llm import LLMProvider, LLMStage
from providers.v2_budget import (
    V2BudgetExceededError,
    V2BudgetSnapshot,
    V2CancellationRequested,
    V2PhysicalCallAudit,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    read_v2_physical_call_audit,
)
from providers.v2_routing import V2RoutingConfig
from store import insert_v2_artifact, read_v2_artifact

V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY = "phase-13-deep-analysis-backfill-analyzer-admission"
V2_DEEP_ANALYSIS_MAX_WORKERS = 4


class V2DeepAnalysisWave(StrictModel):
    """All typed phase outputs for one source attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    extraction: V2ExactExtractionResult
    analyst: V2EvidenceAnalystBatchResult
    admission: V2EvidenceAdmissionBatchResult | None = None


class V2DeepAnalysisWorkerResult(StrictModel):
    """Typed coordinator handoff from one source worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    wave: V2DeepAnalysisWave | None = None
    failure_state: V2DeepAnalysisSourceExecutionState | None = None
    failure_reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_outcome(self) -> V2DeepAnalysisWorkerResult:
        if self.wave is not None:
            if self.wave.source_id != self.source_id:
                raise ValueError("deep-analysis worker result must match its source")
            if self.failure_state is not None or self.failure_reason is not None:
                raise ValueError("successful deep-analysis workers cannot carry failure fields")
            return self
        if self.failure_state is None or self.failure_reason is None:
            raise ValueError("failed deep-analysis workers require a state and reason")
        return self


class V2DeepAnalysisSourceEnvelope(StrictModel):
    """Remaining conservative work for one restart-aware source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: V2SourceSelectionCandidate
    physical_calls: int = Field(ge=0, le=V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP)
    reserved_tokens: int = Field(ge=0, le=V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP)
    reserved_cost_usd: Decimal = Field(ge=0)
    source_cap_reservable: bool = True


def run_v2_deep_analysis_with_backfill(
    *,
    db_path: str | Path,
    queue_result: V2SourceSelectionQueueResult,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    cancellation_requested: Callable[[], bool] | None = None,
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

    initial_audit = read_v2_physical_call_audit(path, queue_result.run_id)
    pending = tuple(
        _remaining_source_envelope(
            path=path,
            run_id=queue_result.run_id,
            candidate=candidates[source_id],
            routing_config=routing_config,
            audit=initial_audit,
        )
        for source_id in priority
    )
    cursor = 0
    stop_after_wave = False
    while cursor < len(pending) and not stop_after_wave:
        if cancellation_requested is not None and cancellation_requested():
            raise V2CancellationRequested(
                "v2 cancellation was observed before a deep-analysis wave"
            )
        snapshot = _provider_snapshot(llm_provider)
        wave_candidates = _safe_wave_prefix(
            envelopes=pending[cursor:],
            snapshot=snapshot,
            max_workers=V2_DEEP_ANALYSIS_MAX_WORKERS,
            protected_physical_calls=queue_result.mandatory_synthesis_physical_calls,
            protected_tokens=0,
            protected_cost_usd=Decimal("0"),
        )
        if not wave_candidates:
            source_id = pending[cursor].candidate.source_id
            reason = "V2BudgetExceededError: remaining budget cannot cover the next source envelope"
            attempted_source_ids.append(source_id)
            executions[source_id] = V2DeepAnalysisSourceExecution(
                source_id=source_id,
                state=V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED,
                failure_reason=reason,
            )
            terminal_reasons.append(reason)
            break

        wave_source_ids = tuple(item.source_id for item in wave_candidates)

        def worker(source_id: UUID) -> V2DeepAnalysisWorkerResult:
            if cancellation_requested is not None and cancellation_requested():
                raise V2CancellationRequested(
                    "v2 cancellation was observed before source deep analysis"
                )
            try:
                source_wave = _run_source_wave(
                    path=path,
                    source_id=source_id,
                    queue_result=_single_source_queue(queue_result, source_id, routing_config),
                    discovery_outputs=discovery_outputs,
                    acquisition_outputs=acquisition_outputs,
                    llm_provider=llm_provider,
                    routing_config=routing_config,
                    clock=now,
                )
            except V2CancellationRequested:
                raise
            except Exception as exc:
                return _worker_failure(source_id, exc)
            return V2DeepAnalysisWorkerResult(source_id=source_id, wave=source_wave)

        worker_results = _execute_source_batch(
            source_ids=wave_source_ids,
            worker=worker,
            max_workers=V2_DEEP_ANALYSIS_MAX_WORKERS,
        )
        _raise_if_cancelled(
            cancellation_requested,
            "v2 cancellation was observed after a deep-analysis wave",
        )
        for worker_result in worker_results:
            source_id = worker_result.source_id
            attempted_source_ids.append(source_id)
            if worker_result.wave is not None:
                attempted[source_id] = worker_result.wave
                execution = _execution_from_wave(worker_result.wave, ())
            else:
                if worker_result.failure_state is None or worker_result.failure_reason is None:
                    raise AssertionError("validated worker failure lost its terminal fields")
                execution = V2DeepAnalysisSourceExecution(
                    source_id=source_id,
                    state=worker_result.failure_state,
                    failure_reason=worker_result.failure_reason,
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
                stop_after_wave = True
        cursor += len(wave_candidates)

    final_queue = _final_queue_result(
        queue_result,
        tuple(attempted_source_ids),
        routing_config,
        attempted_source_ids=tuple(attempted_source_ids),
    )
    final_analyst = _final_analyst_result(final_queue, attempted, tuple(attempted_source_ids))
    _raise_if_cancelled(
        cancellation_requested,
        "v2 cancellation was observed before final evidence admission",
    )
    final_admission = run_v2_evidence_admission(
        db_path=path,
        analyst_result=final_analyst,
        clock=now,
    )
    _raise_if_cancelled(
        cancellation_requested,
        "v2 cancellation was observed after final evidence admission",
    )
    audit = read_v2_physical_call_audit(path, queue_result.run_id)
    source_executions = tuple(
        executions.get(
            source_id,
            V2DeepAnalysisSourceExecution(
                source_id=source_id,
                state=V2DeepAnalysisSourceExecutionState.NOT_ATTEMPTED,
            ),
        )
        if source_id not in executions
        else _execution_with_audit(executions[source_id], audit)
        for source_id in priority
    )
    reconciliations = tuple(
        _reconcile_source(
            audit=audit,
            source_id=source_id,
            source_cost_cap=_source_reservation(routing_config.preflight(), candidates[source_id])[
                1
            ],
        )
        for source_id in priority
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
    _raise_if_cancelled(
        cancellation_requested,
        "v2 cancellation was observed before deep-analysis completion",
    )
    insert_v2_artifact(path, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY, result, result.completed_at)
    return result


def _provider_snapshot(provider: LLMProvider) -> V2BudgetSnapshot:
    snapshot_method = getattr(provider, "snapshot", None)
    snapshot = snapshot_method() if callable(snapshot_method) else None
    if not isinstance(snapshot, V2BudgetSnapshot):
        raise TypeError("concurrent deep analysis requires a budget snapshot provider")
    return snapshot


def _raise_if_cancelled(
    cancellation_requested: Callable[[], bool] | None,
    message: str,
) -> None:
    if cancellation_requested is not None and cancellation_requested():
        raise V2CancellationRequested(message)


def _safe_wave_prefix(
    *,
    envelopes: tuple[V2DeepAnalysisSourceEnvelope, ...],
    snapshot: V2BudgetSnapshot,
    max_workers: int,
    protected_physical_calls: int,
    protected_tokens: int = 0,
    protected_cost_usd: Decimal = Decimal("0"),
) -> tuple[V2SourceSelectionCandidate, ...]:
    """Return the largest bounded priority prefix whose complete envelopes fit."""
    if not 1 <= max_workers <= V2_DEEP_ANALYSIS_MAX_WORKERS:
        raise ValueError("deep-analysis worker count must be between one and four")
    if protected_physical_calls < 0 or protected_tokens < 0 or protected_cost_usd < 0:
        raise ValueError("protected downstream capacity cannot be negative")
    selected: list[V2SourceSelectionCandidate] = []
    reserved_calls = protected_physical_calls
    reserved_tokens = protected_tokens
    reserved_cost = protected_cost_usd
    for envelope in envelopes[:max_workers]:
        if not envelope.source_cap_reservable:
            break
        next_calls = reserved_calls + envelope.physical_calls
        next_tokens = reserved_tokens + envelope.reserved_tokens
        next_cost = add_usd(reserved_cost, envelope.reserved_cost_usd)
        if (
            next_calls > snapshot.physical_calls_remaining
            or next_tokens > snapshot.tokens_remaining
            or next_cost > snapshot.cost_remaining_usd
        ):
            break
        selected.append(envelope.candidate)
        reserved_calls = next_calls
        reserved_tokens = next_tokens
        reserved_cost = next_cost
    return tuple(selected)


def _remaining_source_envelope(
    *,
    path: str,
    run_id: UUID,
    candidate: V2SourceSelectionCandidate,
    routing_config: V2RoutingConfig,
    audit: V2PhysicalCallAudit | None = None,
) -> V2DeepAnalysisSourceEnvelope:
    source_id = candidate.source_id
    source_starts, source_completions = _source_audit(
        audit or V2PhysicalCallAudit(starts=(), completions=()), source_id
    )
    source_token_exposure = sum(
        completion.usage_tokens
        if completion is not None and completion.usage_tokens is not None
        else start.reserved_tokens
        for start, completion in zip(source_starts, source_completions, strict=True)
    )

    def envelope(
        *,
        physical_calls: int,
        reserved_tokens: int,
        reserved_cost_usd: Decimal,
    ) -> V2DeepAnalysisSourceEnvelope:
        return V2DeepAnalysisSourceEnvelope(
            candidate=candidate,
            physical_calls=physical_calls,
            reserved_tokens=reserved_tokens,
            reserved_cost_usd=reserved_cost_usd,
            source_cap_reservable=(
                len(source_starts) + physical_calls <= V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
                and source_token_exposure + reserved_tokens <= V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP
            ),
        )

    completed_model_keys = (
        f"{V2_EVIDENCE_ADMISSION_SOURCE_ARTIFACT_PREFIX}-{source_id}",
        f"{V2_EVIDENCE_ADMISSION_SOURCE_LEGACY_PREFIX}-{source_id}",
        f"{V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX}-{source_id}",
        f"{V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX}-{source_id}",
        f"phase-13-luna-evidence-analyst-batch-source-{source_id}",
    )
    if any(_artifact_exists(path, run_id, key) for key in completed_model_keys):
        return envelope(
            physical_calls=0,
            reserved_tokens=0,
            reserved_cost_usd=Decimal("0"),
        )
    extraction_key = f"phase-13-exact-extraction-source-{source_id}"
    if _artifact_exists(path, run_id, extraction_key):
        reservation = routing_config.preflight().reserve(
            LLMStage.ANALYST,
            candidate.deep_analysis_input_tokens,
        )
        return envelope(
            physical_calls=1,
            reserved_tokens=reservation.reserved_tokens,
            reserved_cost_usd=reservation.reserved_cost_usd,
        )
    source_tokens, source_cost = _source_reservation(routing_config.preflight(), candidate)
    return envelope(
        physical_calls=V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
        reserved_tokens=source_tokens,
        reserved_cost_usd=source_cost,
    )


def _artifact_exists(path: str, run_id: UUID, artifact_key: str) -> bool:
    try:
        read_v2_artifact(path, run_id, artifact_key)
    except KeyError:
        return False
    return True


def _execute_source_batch(
    *,
    source_ids: tuple[UUID, ...],
    worker: Callable[[UUID], V2DeepAnalysisWorkerResult],
    max_workers: int,
) -> tuple[V2DeepAnalysisWorkerResult, ...]:
    """Run one already-budgeted wave and return typed results in priority order."""
    if not source_ids:
        return ()
    if not 1 <= max_workers <= V2_DEEP_ANALYSIS_MAX_WORKERS:
        raise ValueError("deep-analysis worker count must be between one and four")
    if len(source_ids) > max_workers:
        raise ValueError("a deep-analysis wave cannot exceed its worker bound")
    results: dict[UUID, V2DeepAnalysisWorkerResult] = {}
    cancellation: V2CancellationRequested | None = None
    with ThreadPoolExecutor(
        max_workers=min(max_workers, len(source_ids)),
        thread_name_prefix="v2-deep-analysis",
    ) as executor:
        futures: dict[Future[V2DeepAnalysisWorkerResult], UUID] = {
            executor.submit(worker, source_id): source_id for source_id in source_ids
        }
        for future in as_completed(futures):
            source_id = futures[future]
            try:
                result = future.result()
            except CancelledError:
                continue
            except V2CancellationRequested as exc:
                if cancellation is None:
                    cancellation = exc
                    for pending in futures:
                        if pending is not future:
                            pending.cancel()
                continue
            except Exception as exc:
                result = _worker_failure(source_id, exc)
            if result.source_id != source_id:
                raise ValueError("deep-analysis worker returned a foreign source result")
            results[source_id] = result
    if cancellation is not None:
        raise cancellation
    if set(results) != set(source_ids):
        raise RuntimeError("deep-analysis wave ended without every source result")
    return tuple(results[source_id] for source_id in source_ids)


def _worker_failure(source_id: UUID, exc: Exception) -> V2DeepAnalysisWorkerResult:
    reason = f"{type(exc).__name__}: {exc}"[:1000]
    return V2DeepAnalysisWorkerResult(
        source_id=source_id,
        failure_state=(
            V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
            if isinstance(exc, V2BudgetExceededError)
            else V2DeepAnalysisSourceExecutionState.ANALYST_FAILED
        ),
        failure_reason=reason,
    )


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
    wave: V2DeepAnalysisWave,
    sequences: tuple[int, ...],
) -> V2DeepAnalysisSourceExecution:
    extraction = wave.extraction.sources[0]
    analyst = next(item for item in wave.analyst.source_results if item.source_id == wave.source_id)
    admission = wave.admission
    if admission is None:
        raise ValueError("fresh deep-analysis waves require an evidence admission result")
    admitted = next(item for item in admission.source_results if item.source_id == wave.source_id)
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


def _physical_sequences(audit: V2PhysicalCallAudit, source_id: UUID) -> tuple[int, ...]:
    return tuple(item.sequence for item in audit.starts if item.source_id == source_id)


def _execution_with_audit(
    execution: V2DeepAnalysisSourceExecution,
    audit: V2PhysicalCallAudit,
) -> V2DeepAnalysisSourceExecution:
    if execution.state is V2DeepAnalysisSourceExecutionState.NOT_ATTEMPTED:
        return execution
    return execution.model_copy(
        update={"physical_call_sequences": _physical_sequences(audit, execution.source_id)}
    )


def _reconcile_source(
    *,
    audit: V2PhysicalCallAudit,
    source_id: UUID,
    source_cost_cap: Decimal,
) -> V2DeepAnalysisSourceReconciliation:
    starts, completions = _source_audit(audit, source_id)
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


def _source_audit(
    audit: V2PhysicalCallAudit,
    source_id: UUID,
) -> tuple[tuple[V2PhysicalCallStart, ...], tuple[V2PhysicalCallCompletion | None, ...]]:
    starts: list[V2PhysicalCallStart] = []
    completions: list[V2PhysicalCallCompletion | None] = []
    for start, completion in zip(audit.starts, audit.completions, strict=True):
        if start.source_id != source_id:
            continue
        starts.append(start)
        completions.append(completion)
    return tuple(starts), tuple(completions)


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
    result = V2DeepAnalysisBackfillResult.model_validate_json(artifact.payload_json)
    if result.policy_identity != V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY:
        raise ValueError("persisted deep-analysis backfill uses an incompatible execution policy")
    return result


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("deep-analysis clock must return a timezone-aware datetime")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
