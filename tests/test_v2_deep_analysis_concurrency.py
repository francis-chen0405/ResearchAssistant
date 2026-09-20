from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import UUID, uuid4

import pytest
from test_v2_phase8_source_selection import NOW, _candidate, _prepare_db, _routing
from test_v2_phase12_production import (
    _run,
    _Scraper,
    _Search,
    _V2Model,
)

import agents.v2_deep_analysis as v2_deep_analysis
from agents.v2_deep_analysis import (
    V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
    V2DeepAnalysisSourceEnvelope,
    V2DeepAnalysisWorkerResult,
    _execute_source_batch,
    _execution_with_audit,
    _remaining_source_envelope,
    _safe_wave_prefix,
)
from agents.v2_evidence_admission import V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
from agents.v2_source_selection import V2_SOURCE_SELECTION_COMPLETION_KEY
from models import (
    SelectedSentenceRange,
    V2DeepAnalysisBackfillResult,
    V2DeepAnalysisSourceExecutionState,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2SourceSelectionQueueResult,
    V2VerbatimQuoteSelection,
)
from providers.llm import LLMStage
from providers.v2_budget import (
    V2BudgetSnapshot,
    V2PhysicalCallAudit,
    V2PhysicalCallStart,
    V2RunCeilings,
    read_v2_physical_call_audit,
)
from store import insert_v2_artifact, read_v2_artifact
from v2_orchestrator import V2ProductionPipelineResult, V2ProductionState


class _BlockingDeepModel(_V2Model):
    def __init__(self) -> None:
        super().__init__(completed_rounds=2)
        self.release = Event()
        self.two_sources_started = Event()
        self._deep_lock = Lock()
        self._active = 0
        self.max_active = 0
        self.started_sources: list[UUID] = []

    def generate(self, request: object) -> object:
        output_name = request.requested_output_type.__name__
        if output_name not in {"V2VerbatimQuoteSelection", "VerbatimQuoteSelection"}:
            return super().generate(request)
        source_id = request.source_id
        assert isinstance(source_id, UUID)
        with self._deep_lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            if source_id not in self.started_sources:
                self.started_sources.append(source_id)
            if len(self.started_sources) >= 2:
                self.two_sources_started.set()
        try:
            assert self.release.wait(timeout=5)
            return super().generate(request)
        finally:
            with self._deep_lock:
                self._active -= 1


class _CancellingDeepModel(_V2Model):
    def __init__(self, cancellation: Event) -> None:
        super().__init__(completed_rounds=4, round_four_query_count=2)
        self.cancellation = cancellation
        self.first_deep_call_started = Event()
        self.release = Event()
        self._started_lock = Lock()
        self.started_sources: list[UUID] = []

    def generate(self, request: object) -> object:
        output_name = request.requested_output_type.__name__
        if output_name not in {"V2VerbatimQuoteSelection", "VerbatimQuoteSelection"}:
            return super().generate(request)
        source_id = request.source_id
        assert isinstance(source_id, UUID)
        with self._started_lock:
            if source_id not in self.started_sources:
                self.started_sources.append(source_id)
        self.cancellation.set()
        self.first_deep_call_started.set()
        assert self.release.wait(timeout=5)
        return super().generate(request)


class _OneSourceExtractionFailureModel(_V2Model):
    def __init__(self) -> None:
        super().__init__(completed_rounds=2)
        self._failure_lock = Lock()
        self.failed_source_id: UUID | None = None

    def generate(self, request: object) -> object:
        output_name = request.requested_output_type.__name__
        if output_name not in {"V2VerbatimQuoteSelection", "VerbatimQuoteSelection"}:
            return super().generate(request)
        source_id = request.source_id
        assert isinstance(source_id, UUID)
        with self._failure_lock:
            if self.failed_source_id is None:
                self.failed_source_id = source_id
            should_fail = source_id == self.failed_source_id
        if not should_fail:
            return super().generate(request)
        self.requests.append(request)
        return V2VerbatimQuoteSelection(
            selected_sentence_ranges=(SelectedSentenceRange(start_sentence=99, end_sentence=99),)
        )


def _failed_worker_result(source_id: UUID) -> V2DeepAnalysisWorkerResult:
    return V2DeepAnalysisWorkerResult(
        source_id=source_id,
        failure_state=V2DeepAnalysisSourceExecutionState.ANALYST_FAILED,
        failure_reason="controlled worker result",
    )


def test_source_batch_is_bounded_and_returns_priority_order() -> None:
    source_ids = tuple(uuid4() for _ in range(2))
    release = Event()
    all_started = Event()
    lock = Lock()
    active = 0
    max_active = 0
    started: list[UUID] = []

    def worker(source_id: UUID) -> V2DeepAnalysisWorkerResult:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            started.append(source_id)
            if len(started) == 2:
                all_started.set()
        assert release.wait(timeout=5)
        with lock:
            active -= 1
        return _failed_worker_result(source_id)

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as controller:
        future = controller.submit(
            _execute_source_batch,
            source_ids=source_ids,
            worker=worker,
            max_workers=2,
        )
        assert all_started.wait(timeout=5)
        with lock:
            assert len(started) == 2
        release.set()
        results = future.result(timeout=5)

    assert max_active == 2
    assert tuple(item.source_id for item in results) == source_ids


def test_reversed_completion_still_returns_priority_order() -> None:
    source_ids = tuple(uuid4() for _ in range(2))
    second_done = Event()

    def worker(source_id: UUID) -> V2DeepAnalysisWorkerResult:
        if source_id == source_ids[0]:
            assert second_done.wait(timeout=5)
        else:
            second_done.set()
        return _failed_worker_result(source_id)

    results = _execute_source_batch(
        source_ids=source_ids,
        worker=worker,
        max_workers=2,
    )

    assert tuple(item.source_id for item in results) == source_ids


def test_safe_wave_is_largest_complete_priority_prefix() -> None:
    source_ids = tuple(uuid4() for _ in range(4))
    candidates = tuple(
        _candidate(source_id, family=f"family-{index}", probe_score=10 - index)
        for index, source_id in enumerate(source_ids)
    )
    routing = _routing()
    source_cost = routing.preflight().reserve(LLMStage.EXTRACTOR, 1600).reserved_cost_usd * 2
    source_cost += routing.preflight().reserve(LLMStage.ANALYST, 1600).reserved_cost_usd
    snapshot = V2BudgetSnapshot(
        physical_calls_used=10,
        token_exposure=1,
        cost_exposure_usd=Decimal("0"),
        physical_calls_remaining=6,
        tokens_remaining=120_000,
        cost_remaining_usd=source_cost * 2,
    )

    envelopes = tuple(
        V2DeepAnalysisSourceEnvelope(
            candidate=candidate,
            physical_calls=3,
            reserved_tokens=60_000,
            reserved_cost_usd=source_cost,
        )
        for candidate in candidates
    )
    selected = _safe_wave_prefix(
        envelopes=envelopes,
        snapshot=snapshot,
        max_workers=4,
        protected_physical_calls=0,
    )

    assert tuple(item.source_id for item in selected) == source_ids[:2]


def test_completed_source_checkpoint_needs_no_new_budget(tmp_path: Path) -> None:
    source_id = uuid4()
    candidate = _candidate(source_id, family="restart-family", probe_score=10)
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    insert_v2_artifact(
        path,
        f"phase-13-luna-evidence-analyst-source-v2-{source_id}",
        V2EvidenceAnalystSourceResult(
            run_id=run_id,
            source_id=source_id,
            direction=candidate.direction,
            state=V2EvidenceAnalystState.FAILED,
            failure="persisted restart fixture",
        ),
        NOW,
    )

    envelope = _remaining_source_envelope(
        path=path,
        run_id=run_id,
        candidate=candidate,
        routing_config=_routing(),
    )
    selected = _safe_wave_prefix(
        envelopes=(envelope,),
        snapshot=V2BudgetSnapshot(
            physical_calls_used=160,
            token_exposure=500_000,
            cost_exposure_usd=Decimal("5"),
            physical_calls_remaining=0,
            tokens_remaining=0,
            cost_remaining_usd=Decimal("0"),
        ),
        max_workers=4,
        protected_physical_calls=0,
    )

    assert envelope.physical_calls == 0
    assert selected == (candidate,)


def test_full_pipeline_overlaps_sources_and_persists_priority_order(tmp_path: Path) -> None:
    model = _BlockingDeepModel()
    results: list[V2ProductionPipelineResult] = []

    def run_pipeline() -> None:
        results.append(
            _run(
                tmp_path / "concurrent-deep.sqlite3",
                model,
                _Search(unique_results=True),
                _Scraper(),
                ceilings=V2RunCeilings(
                    max_physical_calls=80,
                    max_total_tokens=500_000,
                    max_total_cost_usd=Decimal("5"),
                ),
            )
        )

    thread = Thread(target=run_pipeline)
    thread.start()
    assert model.two_sources_started.wait(timeout=5)
    assert 2 <= model.max_active <= 4
    model.release.set()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert len(results) == 1
    result = results[0]
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    backfill = V2DeepAnalysisBackfillResult.model_validate_json(
        read_v2_artifact(
            result.db_path,
            result.run_id,
            "phase-13-deep-analysis-backfill-analyzer-admission",
        ).payload_json
    )
    assert backfill.final_execution_order == backfill.final_queue_result.queued_source_ids
    priority = backfill.final_queue_result.priority_source_ids
    assert backfill.final_execution_order == priority[: len(backfill.final_execution_order)]
    assert tuple(item.source_id for item in backfill.source_executions) == priority
    assert tuple(item.source_id for item in backfill.source_reconciliations) == priority
    assert len(
        {
            sequence
            for item in backfill.source_executions
            for sequence in item.physical_call_sequences
        }
    ) == sum(len(item.physical_call_sequences) for item in backfill.source_executions)
    audit = read_v2_physical_call_audit(result.db_path, result.run_id)
    for source_id in priority:
        assert sum(item.source_id == source_id for item in audit.starts) <= 3
    assert len(audit.starts) <= 80
    assert result.budget.token_exposure <= 500_000
    assert result.budget.cost_exposure_usd <= Decimal("5")

    resumed_model = _V2Model(completed_rounds=2)
    resumed = _run(
        Path(result.db_path),
        resumed_model,
        _Search(unique_results=True),
        _Scraper(),
        run_id=result.run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )
    assert resumed == result
    assert resumed_model.requests == []
    connection = sqlite3.connect(result.db_path)
    try:
        aggregate_count = connection.execute(
            "SELECT COUNT(*) FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
            (str(result.run_id), V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY),
        ).fetchone()[0]
    finally:
        connection.close()
    assert aggregate_count == 1


def test_worker_bound_rejects_oversized_submitted_wave() -> None:
    source_ids = tuple(uuid4() for _ in range(3))
    with pytest.raises(ValueError, match="cannot exceed"):
        _execute_source_batch(
            source_ids=source_ids,
            worker=_failed_worker_result,
            max_workers=2,
        )


def test_cancellation_drains_in_flight_work_and_writes_no_aggregate(tmp_path: Path) -> None:
    cancellation = Event()
    model = _CancellingDeepModel(cancellation)
    results: list[V2ProductionPipelineResult] = []

    def run_pipeline() -> None:
        results.append(
            _run(
                tmp_path / "cancelled-concurrent-deep.sqlite3",
                model,
                _Search(unique_results=True),
                _Scraper(),
                ceilings=V2RunCeilings(
                    max_physical_calls=100,
                    max_total_tokens=500_000,
                    max_total_cost_usd=Decimal("5"),
                ),
                cancellation_requested=cancellation.is_set,
            )
        )

    thread = Thread(target=run_pipeline)
    thread.start()
    assert model.first_deep_call_started.wait(timeout=5)
    model.release.set()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert len(results) == 1
    result = results[0]
    assert result.state is V2ProductionState.CANCELLED
    selection = V2SourceSelectionQueueResult.model_validate_json(
        read_v2_artifact(
            result.db_path, result.run_id, V2_SOURCE_SELECTION_COMPLETION_KEY
        ).payload_json
    )
    assert len(model.started_sources) <= 4
    assert set(model.started_sources).issubset(set(selection.priority_source_ids[:4]))
    with pytest.raises(KeyError):
        read_v2_artifact(
            result.db_path,
            result.run_id,
            V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
        )
    audit = read_v2_physical_call_audit(result.db_path, result.run_id)
    assert len(audit.starts) == result.budget.physical_calls_used
    assert all(
        completion is not None or start.reserved_tokens > 0
        for start, completion in zip(audit.starts, audit.completions, strict=True)
    )


def test_cancellation_after_final_admission_writes_no_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancellation = Event()
    original_admission = v2_deep_analysis.run_v2_evidence_admission

    def cancelling_admission(
        *,
        db_path: str | Path,
        analyst_result: V2EvidenceAnalystBatchResult,
        clock: Callable[[], datetime] | None = None,
        artifact_key: str = V2_EVIDENCE_ADMISSION_ARTIFACT_KEY,
    ) -> V2EvidenceAdmissionBatchResult:
        result = original_admission(
            db_path=db_path,
            analyst_result=analyst_result,
            clock=clock,
            artifact_key=artifact_key,
        )
        if artifact_key == V2_EVIDENCE_ADMISSION_ARTIFACT_KEY:
            cancellation.set()
        return result

    monkeypatch.setattr(v2_deep_analysis, "run_v2_evidence_admission", cancelling_admission)
    result = _run(
        tmp_path / "cancel-after-final-admission.sqlite3",
        _V2Model(),
        _Search(),
        _Scraper(),
        cancellation_requested=cancellation.is_set,
    )

    assert result.state is V2ProductionState.CANCELLED
    with pytest.raises(KeyError):
        read_v2_artifact(
            result.db_path,
            result.run_id,
            V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
        )


def test_not_attempted_execution_does_not_claim_partial_audit_sequences() -> None:
    run_id = uuid4()
    source_id = uuid4()
    execution = v2_deep_analysis.V2DeepAnalysisSourceExecution(
        source_id=source_id,
        state=V2DeepAnalysisSourceExecutionState.NOT_ATTEMPTED,
    )
    audit = V2PhysicalCallAudit(
        starts=(
            V2PhysicalCallStart(
                run_id=run_id,
                sequence=1,
                stage="extractor",
                model_alias="mimo-v2.5-pro",
                reserved_tokens=100,
                reserved_cost_usd=Decimal("0.01"),
                source_id=source_id,
                started_at=NOW,
            ),
        ),
        completions=(None,),
    )

    restored = _execution_with_audit(execution, audit)

    assert restored == execution
    assert restored.physical_call_sequences == ()


def test_one_source_failure_does_not_corrupt_parallel_source_audit(tmp_path: Path) -> None:
    model = _OneSourceExtractionFailureModel()
    result = _run(
        tmp_path / "one-source-failure.sqlite3",
        model,
        _Search(unique_results=True),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert model.failed_source_id is not None
    backfill = V2DeepAnalysisBackfillResult.model_validate_json(
        read_v2_artifact(
            result.db_path,
            result.run_id,
            V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
        ).payload_json
    )
    failed = next(
        item for item in backfill.source_executions if item.source_id == model.failed_source_id
    )
    assert failed.state is V2DeepAnalysisSourceExecutionState.EXTRACTION_FAILED
    assert any(
        item.state is V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED
        for item in backfill.source_executions
        if item.source_id != model.failed_source_id
    )
    all_sequences = tuple(
        sequence for item in backfill.source_executions for sequence in item.physical_call_sequences
    )
    assert len(all_sequences) == len(set(all_sequences))
    audit = read_v2_physical_call_audit(result.db_path, result.run_id)
    assert tuple(item.sequence for item in audit.starts) == tuple(range(1, len(audit.starts) + 1))
