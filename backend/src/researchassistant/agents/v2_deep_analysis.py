"""Source-capped fresh-v2 deep analysis with deterministic survivor backfill."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import (
    CancelledError,
    Future,
    ThreadPoolExecutor,
    as_completed,
)
from contextvars import copy_context
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.agents.pending_source_priority import freeze_pending_priority
from researchassistant.agents.v2_acquisition import V2AcquisitionProbeOutput
from researchassistant.agents.v2_discovery import V2DiscoveryScoutOutput
from researchassistant.agents.v2_evidence_admission import (
    V2_EVIDENCE_ADMISSION_ARTIFACT_KEY,
    V2_EVIDENCE_ADMISSION_SOURCE_ARTIFACT_PREFIX,
    V2_EVIDENCE_ADMISSION_SOURCE_LEGACY_PREFIX,
    run_v2_evidence_admission,
)
from researchassistant.agents.v2_evidence_analyst import (
    V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
    V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX,
    run_v2_evidence_analyst,
)
from researchassistant.agents.v2_extraction import run_v2_exact_extraction, snapshots_by_source
from researchassistant.agents.v2_source_selection import _source_reservation
from researchassistant.agents.v2_stage_checkpoint import checkpoint_hash, read_checkpoint
from researchassistant.common.money import add_usd, nonnegative_difference_usd
from researchassistant.contracts.extraction import V2ExactExtractionResult, V2ExtractionState
from researchassistant.contracts.models import (
    V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    SourceSnapshot,
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
    V2GapAnalysisOutput,
    V2LedgerProvenance,
    V2SourceSelectionCandidate,
    V2SourceSelectionQueueResult,
)
from researchassistant.evidence.evidence_core import validate_snapshot_integrity
from researchassistant.providers.llm import LLMProvider, LLMStage
from researchassistant.providers.run_scheduler import POLICY, RunScheduler
from researchassistant.providers.v2_budget import (
    V2BudgetExceededError,
    V2BudgetSnapshot,
    V2CancellationRequested,
    V2PhysicalCallAudit,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2SourceBudgetExceededError,
    read_v2_physical_call_audit,
)
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.storage.sqlite_policy import overlapping_database_writes
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY = "phase-13-deep-analysis-backfill-analyzer-admission"
V2_DEEP_ANALYSIS_MAX_WORKERS = POLICY.analysis.maximum
EXACT_BODY_MIRROR_POLICY_KEY = "exact-body-mirror-scheduling-v1"


class V2ExactBodyMirrorPolicy(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    enabled: bool


def exact_body_mirror_policy(path: str, run_id: UUID, now: datetime) -> bool:
    """Freeze new-run behavior before either early assessment or final backfill."""
    try:
        stored = read_v2_artifact(path, run_id, EXACT_BODY_MIRROR_POLICY_KEY)
    except KeyError:
        stored = None
    if stored is not None:
        return V2ExactBodyMirrorPolicy.model_validate_json(stored.payload_json).enabled
    audit = read_v2_physical_call_audit(path, run_id)
    enabled = not any(
        start.stage in {LLMStage.EXTRACTOR.value, LLMStage.ANALYST.value} for start in audit.starts
    )
    insert_v2_artifact(
        path,
        EXACT_BODY_MIRROR_POLICY_KEY,
        V2ExactBodyMirrorPolicy(run_id=run_id, enabled=enabled),
        now,
    )
    return enabled


class V2ExactBodyMirror(StrictModel):
    """An unmodified source location whose complete captured body is already queued."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    retained_source_id: UUID
    snapshot_sha256: str

    @model_validator(mode="after")
    def validate_distinct_locations(self) -> V2ExactBodyMirror:
        if self.source_id == self.retained_source_id:
            raise ValueError("a source cannot be its own exact-body mirror")
        return self


class V2ExactBodyMirrorPlan(StrictModel):
    """Freeze scheduling exclusions while retaining every acquisition and source ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input_sha256: str
    enabled: bool
    mirrors: tuple[V2ExactBodyMirror, ...]


def _exact_body_mirror_plan(
    queue_result: V2SourceSelectionQueueResult,
    priority: tuple[UUID, ...],
    snapshots: dict[UUID, SourceSnapshot],
    *,
    enabled: bool,
    assessed_source_ids: frozenset[UUID] = frozenset(),
) -> V2ExactBodyMirrorPlan:
    candidates = {item.source_id: item for item in queue_result.input.survivors}
    seen: dict[tuple[object, str], UUID] = {}
    mirrors: list[V2ExactBodyMirror] = []
    identities = []
    # Existing assessed ownership wins over later ranking. Historical assessed
    # sources keep their own records even if another assessed body is identical.
    comparison_order = tuple(
        source_id for source_id in priority if source_id in assessed_source_ids
    )
    comparison_order += tuple(
        source_id for source_id in priority if source_id not in assessed_source_ids
    )
    for source_id in comparison_order:
        candidate = candidates[source_id]
        snapshot = snapshots[source_id]
        validate_snapshot_integrity(snapshot)
        identities.append(
            (
                str(source_id),
                candidate.direction.value,
                str(snapshot.snapshot_id),
                snapshot.snapshot_sha256,
                snapshot.truncated,
            )
        )
        if not enabled or snapshot.truncated:
            continue
        key = (candidate.direction, snapshot.snapshot_sha256)
        retained = seen.get(key)
        if retained is None:
            seen[key] = source_id
        elif (
            source_id not in assessed_source_ids
            and snapshots[retained].normalized_text == snapshot.normalized_text
        ):
            mirrors.append(
                V2ExactBodyMirror(
                    source_id=source_id,
                    retained_source_id=retained,
                    snapshot_sha256=snapshot.snapshot_sha256,
                )
            )
    return V2ExactBodyMirrorPlan(
        run_id=queue_result.run_id,
        input_sha256=checkpoint_hash(identities),
        enabled=enabled,
        mirrors=tuple(mirrors),
    )


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
    prior_waves: tuple[V2DeepAnalysisWave, ...] = (),
    gap_outputs: tuple[V2GapAnalysisOutput, ...] = (),
    artifact_key: str = V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
    admission_artifact_key: str | None = None,
) -> V2DeepAnalysisBackfillResult:
    """Execute the initial queue and backfill terminal source failures in priority order."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    persisted = _read_backfill(path, queue_result.run_id, artifact_key)
    if persisted is not None:
        if persisted.final_queue_result.input != queue_result.input:
            raise ValueError("persisted deep-analysis backfill does not match Phase-8 input")
        return persisted
    if not queue_result.queued_source_ids and not prior_waves:
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
    current_snapshots = snapshots_by_source(acquisition_outputs)
    for wave in prior_waves:
        original_source = next(
            (
                s
                for s in wave.extraction.queue_result.input.survivors
                if s.source_id == wave.source_id
            ),
            None,
        )
        quote = wave.extraction.sources[0].candidate
        snapshot = current_snapshots.get(wave.source_id)
        if (
            wave.source_id not in candidates
            or wave.analyst.run_id != queue_result.run_id
            or wave.analyst.input.exact_claim != queue_result.input.exact_claim
            or wave.analyst.input.directions != queue_result.input.directions
            or wave.admission is not None
            or original_source is None
            or original_source.source_url != candidates[wave.source_id].source_url
            or snapshot is None
            or (
                quote is not None
                and (
                    quote.snapshot_id != snapshot.snapshot_id
                    or quote.snapshot_sha256 != snapshot.snapshot_sha256
                    or quote.run_id != queue_result.run_id
                )
            )
        ):
            raise ValueError("evidence checkpoint does not match this run and survivor pool")
        if wave.source_id in attempted:
            raise ValueError("evidence checkpoint contains duplicate sources")
        attempted[wave.source_id] = wave
        attempted_source_ids.append(wave.source_id)

    initial_audit = read_v2_physical_call_audit(path, queue_result.run_id)
    mirror_key = f"{artifact_key}-exact-body-mirrors-v1"
    try:
        saved_mirrors = read_v2_artifact(path, queue_result.run_id, mirror_key)
    except KeyError:
        saved_mirrors = None
    # An interrupted historical run must retain the scheduling policy under
    # which it already made physical calls. New runs freeze this plan before
    # their first deep-analysis wave, including plans with no duplicate bodies.
    enabled = exact_body_mirror_policy(path, queue_result.run_id, _aware(now()))
    if saved_mirrors is not None:
        saved_plan = V2ExactBodyMirrorPlan.model_validate_json(saved_mirrors.payload_json)
        enabled = saved_plan.enabled
    mirror_plan = _exact_body_mirror_plan(
        queue_result,
        priority,
        current_snapshots,
        enabled=enabled,
        assessed_source_ids=frozenset(wave.source_id for wave in prior_waves),
    )
    if saved_mirrors is not None:
        if mirror_plan != saved_plan:
            raise ValueError("persisted exact-body mirror plan differs from source snapshots")
    else:
        insert_v2_artifact(path, mirror_key, mirror_plan, _aware(now()))
    mirror_ids = {mirror.source_id for mirror in mirror_plan.mirrors}
    pending_baseline = tuple(
        source_id
        for source_id in priority
        if source_id not in attempted and source_id not in mirror_ids
    )
    for source_id in pending_baseline:
        preview = candidates[source_id].preview
        if preview is not None:
            preview.require_snapshot(current_snapshots[source_id])
    pending_priority = freeze_pending_priority(
        path=path,
        key=f"{artifact_key}-pending-gap-preference-v1",
        queue=queue_result,
        baseline=pending_baseline,
        gap_outputs=gap_outputs,
        already_started=any(
            start.source_id in pending_baseline
            and start.stage in {LLMStage.EXTRACTOR.value, LLMStage.ANALYST.value}
            for start in initial_audit.starts
        ),
        now=_aware(now()),
    )
    pending = tuple(
        _remaining_source_envelope(
            path=path,
            run_id=queue_result.run_id,
            candidate=candidates[source_id],
            routing_config=routing_config,
            audit=initial_audit,
        )
        for source_id in pending_priority
    )
    dispatch_identity = checkpoint_hash(
        {
            "queue": V2SourceSelectionQueueResult.model_validate(
                queue_result.model_dump(include=set(V2SourceSelectionQueueResult.model_fields))
            ).model_dump(mode="json"),
            "discovery": [output.model_dump(mode="json") for output in discovery_outputs],
            "acquisition": [output.model_dump(mode="json") for output in acquisition_outputs],
            "pending": tuple(map(str, pending_priority)),
        }
    )
    baseline_snapshot = _provider_snapshot(llm_provider)
    baseline_sequence = len(initial_audit.starts)
    dispatched: list[UUID] = []
    results: dict[UUID, V2DeepAnalysisWorkerResult] = {}
    active: dict[Future[V2DeepAnalysisWorkerResult], V2DeepAnalysisSourceEnvelope] = {}
    extracting: dict[Future[V2ExactExtractionResult], V2DeepAnalysisSourceEnvelope] = {}
    extracted: dict[UUID, V2ExactExtractionResult] = {}
    owned: dict[UUID, V2DeepAnalysisSourceEnvelope] = {}
    scheduler = getattr(llm_provider, "scheduler", None) or RunScheduler(cancellation_requested)
    cursor = 0
    stop_dispatch = False

    def check_cancelled() -> None:
        _raise_if_cancelled(cancellation_requested, "v2 cancellation during deep analysis")

    def worker(source_id: UUID, extraction: V2ExactExtractionResult) -> V2DeepAnalysisWorkerResult:
        check_cancelled()
        try:
            source_wave = _run_extracted_source(
                path=path,
                source_id=source_id,
                extraction=extraction,
                acquisition_outputs=acquisition_outputs,
                llm_provider=llm_provider,
                routing_config=routing_config,
                clock=now,
                journal_early_attempts=True,
                check_cancelled=check_cancelled,
            )
        except V2CancellationRequested:
            raise
        except Exception as exc:
            result = _worker_failure(source_id, exc)
        else:
            result = V2DeepAnalysisWorkerResult(source_id=source_id, wave=source_wave)
        # A settled future includes its durable result write. An interruption
        # before aggregate persistence can recover failures as well as successes.
        insert_v2_artifact(
            path,
            f"{artifact_key}/rolling-v1/result/{source_id}",
            V2DeepAnalysisTaskCheckpoint(
                run_id=queue_result.run_id, input_sha256=dispatch_identity, result=result
            ),
            _aware(now()),
        )
        return result

    with (
        scheduler.stage_scope("extraction", "analysis"),
        overlapping_database_writes(path),
        ThreadPoolExecutor(
            max_workers=POLICY.analysis.maximum, thread_name_prefix="v2-analysis"
        ) as executor,
        ThreadPoolExecutor(
            max_workers=POLICY.extraction.maximum, thread_name_prefix="v2-extraction"
        ) as extraction_executor,
    ):
        try:
            while cursor < len(pending) or owned:
                check_cancelled()
                # Consume every settled task before refilling. Iterate dispatch
                # order when several finish together; never wait on a running one.
                for future, envelope in tuple(active.items()):
                    if not future.done():
                        continue
                    result = future.result()
                    source_id = envelope.candidate.source_id
                    if result.source_id != source_id:
                        raise ValueError("deep-analysis worker returned a foreign source result")
                    results[source_id] = result
                    del active[future]
                    del owned[source_id]
                    if _result_exhausted_budget(result):
                        stop_dispatch = True

                for future, envelope in tuple(extracting.items()):
                    if not future.done():
                        continue
                    source_id = envelope.candidate.source_id
                    try:
                        extraction = future.result()
                        if any(
                            item.state is V2ExtractionState.EXTRACTED for item in extraction.sources
                        ):
                            extracted[source_id] = extraction
                        else:
                            result = worker(source_id, extraction)
                            results[source_id] = result
                            del owned[source_id]
                            stop_dispatch = stop_dispatch or _result_exhausted_budget(result)
                    except V2CancellationRequested:
                        raise
                    except Exception as exc:
                        failure = _worker_failure(source_id, exc)
                        insert_v2_artifact(
                            path,
                            f"{artifact_key}/rolling-v1/result/{source_id}",
                            V2DeepAnalysisTaskCheckpoint(
                                run_id=queue_result.run_id,
                                input_sha256=dispatch_identity,
                                result=failure,
                            ),
                            _aware(now()),
                        )
                        results[source_id] = failure
                        del owned[source_id]
                        stop_dispatch = stop_dispatch or _result_exhausted_budget(failure)
                    del extracting[future]
                capacity = getattr(llm_provider, "stage_capacity_available", None)
                analysis_target = scheduler.update_stage(
                    "analysis",
                    ready=len(extracted),
                    running=len(active),
                    capacity=capacity(LLMStage.ANALYST) if callable(capacity) else True,
                )
                for source_id in dispatched:
                    if len(active) >= analysis_target:
                        break
                    if source_id in extracted:
                        check_cancelled()
                        future = executor.submit(
                            copy_context().run, worker, source_id, extracted.pop(source_id)
                        )
                        active[future] = owned[source_id]
                        future.add_done_callback(lambda _future: scheduler.notify())
                available = _rolling_available_budget(
                    baseline=baseline_snapshot,
                    baseline_sequence=baseline_sequence,
                    audit=read_v2_physical_call_audit(path, queue_result.run_id),
                    settled=frozenset(results),
                    active=tuple(owned.values()),
                    current=_provider_snapshot(llm_provider),
                )
                reservable = bool(
                    cursor < len(pending)
                    and _safe_wave_prefix(
                        envelopes=(pending[cursor],),
                        snapshot=available,
                        max_workers=1,
                        protected_physical_calls=queue_result.mandatory_synthesis_physical_calls,
                    )
                )
                extraction_target = scheduler.update_stage(
                    "extraction",
                    ready=len(pending) - cursor,
                    running=len(extracting),
                    downstream=len(extracted) + scheduler.model_waiting(LLMStage.ANALYST.value),
                    reservable=reservable,
                    capacity=capacity(LLMStage.EXTRACTOR) if callable(capacity) else True,
                )
                while cursor < len(pending) and len(extracting) < extraction_target:
                    check_cancelled()
                    envelope = pending[cursor]
                    source_id = envelope.candidate.source_id
                    snapshot = current_snapshots[source_id]
                    dispatch = V2DeepAnalysisDispatch(
                        run_id=queue_result.run_id,
                        source_id=source_id,
                        input_sha256=dispatch_identity,
                        snapshot_id=snapshot.snapshot_id,
                        snapshot_sha256=snapshot.snapshot_sha256,
                    )
                    key = f"{artifact_key}/rolling-v1/dispatch-{cursor + 1}"
                    saved = read_checkpoint(path, queue_result.run_id, key, V2DeepAnalysisDispatch)
                    if saved is not None and saved != dispatch:
                        raise ValueError("saved deep-analysis dispatch identity changed")
                    if saved is None and stop_dispatch:
                        break
                    recovered = read_checkpoint(
                        path,
                        queue_result.run_id,
                        f"{artifact_key}/rolling-v1/result/{source_id}",
                        V2DeepAnalysisTaskCheckpoint,
                    )
                    if recovered is not None:
                        if (
                            saved is None
                            or recovered.input_sha256 != dispatch_identity
                            or recovered.result.source_id != source_id
                        ):
                            raise ValueError("deep-analysis result has no matching dispatch")
                        dispatched.append(source_id)
                        results[source_id] = recovered.result
                        cursor += 1
                        stop_dispatch = stop_dispatch or _result_exhausted_budget(recovered.result)
                        # Later saved dispatches may already exist even when an
                        # earlier worker exhausted its budget. Replay them first.
                        continue

                    available = _rolling_available_budget(
                        baseline=baseline_snapshot,
                        baseline_sequence=baseline_sequence,
                        audit=read_v2_physical_call_audit(path, queue_result.run_id),
                        settled=frozenset(results),
                        active=tuple(owned.values()),
                        current=_provider_snapshot(llm_provider),
                    )
                    fits = _safe_wave_prefix(
                        envelopes=(envelope,),
                        snapshot=available,
                        max_workers=1,
                        protected_physical_calls=queue_result.mandatory_synthesis_physical_calls,
                    )
                    if not fits:
                        if owned and envelope.source_cap_reservable:
                            # A settling task may release unused allowance. Keep
                            # priority fixed rather than skipping to cheaper work.
                            break
                        state = (
                            V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
                            if not envelope.source_cap_reservable
                            else V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
                        )
                        reason = (
                            "V2SourceBudgetExceededError: source cap prevents further calls"
                            if not envelope.source_cap_reservable
                            else (
                                "V2BudgetExceededError: remaining budget cannot cover "
                                "the next source envelope"
                            )
                        )
                        blocked = V2DeepAnalysisWorkerResult(
                            source_id=source_id, failure_state=state, failure_reason=reason
                        )
                        # Freeze terminal scheduling decisions too, so restart
                        # cannot create gaps or reconsider a consumed prefix.
                        if saved is None:
                            insert_v2_artifact(path, key, dispatch, _aware(now()))
                        insert_v2_artifact(
                            path,
                            f"{artifact_key}/rolling-v1/result/{source_id}",
                            V2DeepAnalysisTaskCheckpoint(
                                run_id=queue_result.run_id,
                                input_sha256=dispatch_identity,
                                result=blocked,
                            ),
                            _aware(now()),
                        )
                        results[source_id] = blocked
                        dispatched.append(source_id)
                        cursor += 1
                        stop_dispatch = stop_dispatch or (
                            state is V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
                        )
                        continue
                    if saved is None:
                        # Once a budget failure settles, only already frozen work
                        # is eligible for recovery; never authorize a new prefix.
                        if any(_result_exhausted_budget(item) for item in results.values()):
                            stop_dispatch = True
                            break
                        insert_v2_artifact(path, key, dispatch, _aware(now()))
                    dispatched.append(source_id)
                    cursor += 1
                    owned[source_id] = envelope
                    future = extraction_executor.submit(
                        copy_context().run,
                        _run_source_extraction,
                        path=path,
                        source_id=source_id,
                        queue_result=_single_source_queue(queue_result, source_id, routing_config),
                        discovery_outputs=discovery_outputs,
                        acquisition_outputs=acquisition_outputs,
                        llm_provider=llm_provider,
                        routing_config=routing_config,
                        clock=now,
                        journal_early_attempts=True,
                    )
                    extracting[future] = envelope
                    future.add_done_callback(lambda _future: scheduler.notify())
                if active or extracting:
                    scheduler.wait_for_change()
                elif stop_dispatch and not owned:
                    break
        except BaseException:
            scheduler.stop_admission()
            raise
        finally:
            # Executor exit drains running tasks and their durable writes. Queued
            # work is cancelled; cancellation never writes aggregate completion.
            for future in (*active, *extracting):
                future.cancel()
    check_cancelled()
    for source_id in dispatched:
        worker_result = results[source_id]
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

    audit = read_v2_physical_call_audit(path, queue_result.run_id)
    final_queue = _final_queue_result(
        queue_result,
        tuple(attempted_source_ids),
        audit,
        attempted_source_ids=tuple(attempted_source_ids),
        prior_source_ids=frozenset(wave.source_id for wave in prior_waves),
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
        artifact_key=admission_artifact_key or V2_EVIDENCE_ADMISSION_ARTIFACT_KEY,
    )
    _raise_if_cancelled(
        cancellation_requested,
        "v2 cancellation was observed after final evidence admission",
    )
    for wave in prior_waves:
        execution = _execution_from_wave(wave.model_copy(update={"admission": final_admission}), ())
        executions[wave.source_id] = execution
        if execution.state is V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED:
            admitted.append(wave.source_id)
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
    insert_v2_artifact(path, artifact_key, result, result.completed_at)
    return result


class V2DeepAnalysisDispatch(StrictModel):
    """One immutable rolling slot, bound before the worker can make a request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    input_sha256: str
    snapshot_id: UUID
    snapshot_sha256: str


class V2DeepAnalysisTaskCheckpoint(StrictModel):
    """A durable terminal worker outcome under its frozen dispatch input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input_sha256: str
    result: V2DeepAnalysisWorkerResult


def _result_exhausted_budget(result: V2DeepAnalysisWorkerResult) -> bool:
    if result.failure_state is V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED:
        return True
    return (
        result.wave is not None
        and _execution_from_wave(result.wave, ()).state
        is V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
    )


def _rolling_available_budget(
    *,
    baseline: V2BudgetSnapshot,
    baseline_sequence: int,
    audit: V2PhysicalCallAudit,
    settled: frozenset[UUID],
    active: tuple[V2DeepAnalysisSourceEnvelope, ...],
    current: V2BudgetSnapshot,
) -> V2BudgetSnapshot:
    """Keep whole active envelopes in a coordinator ledger until durable settlement.

    The baseline already charges historical/unknown attempts. Only new calls of
    settled sources are charged here; active physical calls are covered by their
    whole envelope, including stages not dispatched yet. This avoids both racing
    audit/snapshot refunds and subtracting active physical exposure twice. A live
    provider snapshot also bounds availability; physical reservations remain atomic
    under the existing provider owner. This owner has no concurrent unrelated model
    callers (the round/selection owners have settled before final backfill).
    """
    charged = tuple(
        (start, completion)
        for start, completion in zip(audit.starts, audit.completions, strict=True)
        if start.sequence > baseline_sequence and start.source_id in settled
    )
    calls = len(charged) + sum(item.physical_calls for item in active)
    tokens = sum(
        completion.usage_tokens
        if completion is not None and completion.usage_tokens is not None
        else start.reserved_tokens
        for start, completion in charged
    ) + sum(item.reserved_tokens for item in active)
    cost = add_usd(
        *(
            completion.usage_cost_usd
            if completion is not None and completion.usage_cost_usd is not None
            else start.reserved_cost_usd
            for start, completion in charged
        ),
        *(item.reserved_cost_usd for item in active),
    )
    return baseline.model_copy(
        update={
            "physical_calls_remaining": min(
                current.physical_calls_remaining, max(0, baseline.physical_calls_remaining - calls)
            ),
            "tokens_remaining": min(
                current.tokens_remaining, max(0, baseline.tokens_remaining - tokens)
            ),
            "cost_remaining_usd": min(
                current.cost_remaining_usd,
                nonnegative_difference_usd(baseline.cost_remaining_usd, cost),
            ),
        }
    )


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
        raise ValueError("deep-analysis worker count exceeds scheduling policy")
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
        raise ValueError("deep-analysis worker count exceeds scheduling policy")
    if len(source_ids) > max_workers:
        raise ValueError("a deep-analysis wave cannot exceed its worker bound")
    results: dict[UUID, V2DeepAnalysisWorkerResult] = {}
    cancellation: V2CancellationRequested | None = None
    with ThreadPoolExecutor(
        max_workers=min(max_workers, len(source_ids)),
        thread_name_prefix="v2-deep-analysis",
    ) as executor:
        futures: dict[Future[V2DeepAnalysisWorkerResult], UUID] = {
            executor.submit(copy_context().run, worker, source_id): source_id
            for source_id in source_ids
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
    budget_failure = _budget_failure(exc)
    return V2DeepAnalysisWorkerResult(
        source_id=source_id,
        failure_state=(
            V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
            if isinstance(budget_failure, V2SourceBudgetExceededError)
            else V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
            if budget_failure is not None
            else V2DeepAnalysisSourceExecutionState.ANALYST_FAILED
        ),
        failure_reason=reason,
    )


def _budget_failure(exc: BaseException) -> V2BudgetExceededError | None:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, V2BudgetExceededError):
            return current
        current = current.__cause__
    return None


def _failure_is_source_budget_blocked(failure: str) -> bool:
    return failure.startswith("V2SourceBudgetExceededError:")


def _failure_is_run_budget_exhausted(failure: str) -> bool:
    return failure.startswith("V2BudgetExceededError:")


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
    admit: bool = True,
    journal_early_attempts: bool = False,
    check_cancelled: Callable[[], None] | None = None,
) -> V2DeepAnalysisWave:
    if check_cancelled is not None:
        check_cancelled()
    extraction = _run_source_extraction(
        path=path,
        source_id=source_id,
        queue_result=queue_result,
        discovery_outputs=discovery_outputs,
        acquisition_outputs=acquisition_outputs,
        llm_provider=llm_provider,
        routing_config=routing_config,
        clock=clock,
        journal_early_attempts=journal_early_attempts,
    )
    return _run_extracted_source(
        path=path,
        source_id=source_id,
        extraction=extraction,
        acquisition_outputs=acquisition_outputs,
        llm_provider=llm_provider,
        routing_config=routing_config,
        clock=clock,
        admit=admit,
        journal_early_attempts=journal_early_attempts,
        check_cancelled=check_cancelled,
    )


def _run_source_extraction(
    *,
    path: str,
    source_id: UUID,
    queue_result: V2SourceSelectionQueueResult,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
    journal_early_attempts: bool = False,
) -> V2ExactExtractionResult:
    suffix = f"source-{source_id}"
    return run_v2_exact_extraction(
        db_path=path,
        queue_result=queue_result,
        discovery_outputs=discovery_outputs,
        acquisition_outputs=acquisition_outputs,
        llm_provider=llm_provider,
        routing_config=routing_config,
        artifact_key=f"phase-13-exact-extraction-{suffix}",
        clock=clock,
        journal_attempts=journal_early_attempts,
    )


def _run_extracted_source(
    *,
    path: str,
    source_id: UUID,
    extraction: V2ExactExtractionResult,
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
    admit: bool = True,
    journal_early_attempts: bool = False,
    check_cancelled: Callable[[], None] | None = None,
) -> V2DeepAnalysisWave:
    if check_cancelled is not None:
        check_cancelled()
    suffix = f"source-{source_id}"
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=extraction.analyst_input(snapshots_by_source(acquisition_outputs)),
        llm_provider=llm_provider,
        routing_config=routing_config,
        artifact_key=f"phase-13-luna-evidence-analyst-batch-{suffix}",
        clock=clock,
        stop_on_unknown_attempt=journal_early_attempts,
    )
    if check_cancelled is not None:
        check_cancelled()
    admission = (
        run_v2_evidence_admission(
            db_path=path,
            analyst_result=analyst,
            clock=clock,
            artifact_key=f"phase-13-evidence-admission-batch-{suffix}",
        )
        if admit
        else None
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
    audit: V2PhysicalCallAudit,
    attempted_source_ids: tuple[UUID, ...],
    prior_source_ids: frozenset[UUID],
) -> V2SourceSelectionQueueResult:
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
    # Backfill may attempt more sources than the initial worst-case reservation
    # admitted. Its final queue is an execution record: account measured usage
    # (or the consumed reservation for an unknown completion), not 60k per source.
    exposure: dict[UUID, tuple[int, Decimal]] = {}
    attempted = set(admitted)
    for start, completion in zip(audit.starts, audit.completions, strict=True):
        if start.source_id not in attempted:
            continue
        source_id = start.source_id
        old_tokens, old_cost = exposure.get(source_id, (0, Decimal("0")))
        used_tokens = (
            completion.usage_tokens
            if completion is not None and completion.usage_tokens is not None
            else start.reserved_tokens
        )
        used_cost = (
            completion.usage_cost_usd
            if completion is not None and completion.usage_cost_usd is not None
            else start.reserved_cost_usd
        )
        exposure[source_id] = (
            old_tokens + used_tokens,
            add_usd(old_cost, used_cost),
        )
    tokens = 0
    cost = Decimal("0")
    new_tokens = 0
    new_cost = Decimal("0")
    points: list[V2DeepAnalysisTokenReservation] = []
    for index, source_id in enumerate(admitted, 1):
        source_tokens, source_cost = exposure.get(source_id, (0, Decimal("0")))
        tokens += source_tokens
        cost = add_usd(cost, source_cost)
        if source_id not in prior_source_ids:
            new_tokens += source_tokens
            new_cost = add_usd(new_cost, source_cost)
        if tokens:
            points.append(
                V2DeepAnalysisTokenReservation(
                    source_id=source_id,
                    queue_size=index,
                    cumulative_reserved_tokens=tokens,
                    cumulative_reserved_cost_usd=cost,
                )
            )
    if (
        len(audit.starts) > original.initial_budget.physical_call_ceiling
        or new_tokens > original.initial_budget.tokens_remaining
        or new_cost > original.initial_budget.cost_remaining_usd
    ):
        raise ValueError("backfill accounting exceeds the original run ceiling")
    return V2SourceSelectionQueueResult.model_validate(
        original.model_copy(
            update={
                "queued_source_ids": admitted,
                "source_statuses": statuses,
                "queue_capacity": len(admitted),
                "physical_calls_after_reserve": len(audit.starts),
                "total_reserved_tokens": tokens,
                "total_reserved_cost_usd": cost,
                "token_reservations": tuple(points),
                "limiting_reason": None,
            }
        ).model_dump()
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
    if extraction.state in {
        V2ExtractionState.FAILED,
        V2ExtractionState.SOURCE_BUDGET_BLOCKED,
        V2ExtractionState.BUDGET_EXHAUSTED,
    }:
        extraction_failure = extraction.failure or "exact extraction failed"
        if extraction.state is V2ExtractionState.SOURCE_BUDGET_BLOCKED:
            execution_state = V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
        elif extraction.state is V2ExtractionState.BUDGET_EXHAUSTED:
            execution_state = V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
        else:
            execution_state = V2DeepAnalysisSourceExecutionState.EXTRACTION_FAILED
        return V2DeepAnalysisSourceExecution(
            source_id=wave.source_id,
            state=execution_state,
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
        if _failure_is_source_budget_blocked(analyst_failure):
            return V2DeepAnalysisSourceExecution(
                source_id=wave.source_id,
                state=V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED,
                physical_call_sequences=sequences,
                failure_reason=analyst_failure,
            )
        return V2DeepAnalysisSourceExecution(
            source_id=wave.source_id,
            state=(
                V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
                if _failure_is_run_budget_exhausted(analyst_failure)
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
            V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
            if _failure_is_source_budget_blocked(admission_failure)
            else V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
            if _failure_is_run_budget_exhausted(admission_failure)
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
        released_cost_usd=nonnegative_difference_usd(source_cost_cap, accounted_cost),
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


def _read_backfill(
    path: str, run_id: UUID, artifact_key: str = V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY
) -> V2DeepAnalysisBackfillResult | None:
    try:
        artifact = read_v2_artifact(path, run_id, artifact_key)
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
