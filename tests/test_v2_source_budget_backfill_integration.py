from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import cast
from uuid import UUID

import pytest
from test_v2_phase12_production import (
    SOURCE_TEXT,
    _run,
    _Scraper,
    _Search,
    _V2Model,
)

import agents.v2_deep_analysis as v2_deep_analysis
from agents.v2_deep_analysis import (
    V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
    V2DeepAnalysisSourceEnvelope,
    _remaining_source_envelope,
)
from agents.v2_extraction import V2ExtractionLLMInput
from providers.llm import LLMRequest
from providers.v2_budget import (
    V2BudgetExceededError,
    V2SourceBudgetExceededError,
)
from researchassistant.contracts.models import (
    V2DeepAnalysisBackfillResult,
    V2DeepAnalysisSourceExecutionState,
    V2EvidenceAnalystModelOutput,
    V2VerbatimQuoteSelection,
)
from researchassistant.storage.store import read_v2_artifact


class _BudgetCauseModel(_V2Model):
    def __init__(self, failure: V2BudgetExceededError) -> None:
        super().__init__(completed_rounds=2)
        self.failure = failure
        self.blocked_source_id: UUID | None = None
        self.extractor_source_ids: list[UUID] = []
        self._lock = Lock()
        self._raised = False

    def generate(self, request: LLMRequest) -> object:
        if request.requested_output_type is V2VerbatimQuoteSelection:
            source_id = request.source_id
            assert isinstance(source_id, UUID)
            with self._lock:
                self.extractor_source_ids.append(source_id)
                if self.blocked_source_id is None:
                    self.blocked_source_id = source_id
                should_fail = source_id == self.blocked_source_id and not self._raised
                if should_fail:
                    self._raised = True
            if should_fail:
                raise RuntimeError("wrapped preflight rejection") from self.failure
        return super().generate(request)


class _AnalystBudgetCauseModel(_BudgetCauseModel):
    def generate(self, request: LLMRequest) -> object:
        if request.requested_output_type is V2EvidenceAnalystModelOutput:
            source_id = request.source_id
            assert isinstance(source_id, UUID)
            with self._lock:
                if self.blocked_source_id is None:
                    self.blocked_source_id = source_id
                should_fail = source_id == self.blocked_source_id and not self._raised
                if should_fail:
                    self._raised = True
            if should_fail:
                raise RuntimeError("wrapped analyst preflight rejection") from self.failure
        return super().generate(request)


def _backfill(path: str, run_id: UUID) -> V2DeepAnalysisBackfillResult:
    artifact = read_v2_artifact(path, run_id, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY)
    return V2DeepAnalysisBackfillResult.model_validate_json(artifact.payload_json)


def test_source_cap_rejection_is_one_call_and_backfill_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(v2_deep_analysis, "V2_DEEP_ANALYSIS_MAX_WORKERS", 1)
    model = _BudgetCauseModel(V2SourceBudgetExceededError("source physical-call cap is exhausted"))

    result = _run(
        tmp_path / "source-budget-backfill.sqlite3",
        model,
        _Search(unique_results=True),
        _Scraper(),
    )

    backfill = _backfill(result.db_path, result.run_id)
    executions = {item.source_id: item for item in backfill.source_executions}
    assert model.blocked_source_id is not None
    assert executions[model.blocked_source_id].state is (
        V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
    )
    assert executions[model.blocked_source_id].failure_reason is not None
    assert "V2SourceBudgetExceededError" in executions[model.blocked_source_id].failure_reason
    blocked_position = backfill.final_execution_order.index(model.blocked_source_id)
    assert len(backfill.final_execution_order) > blocked_position + 1
    assert model.extractor_source_ids.count(model.blocked_source_id) == 1
    assert any(
        item.state is V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED
        for item in backfill.source_executions
        if item.source_id != model.blocked_source_id
    )

    later_extraction_request = next(
        request
        for request in model.requests
        if request.requested_output_type is V2VerbatimQuoteSelection
        and request.source_id != model.blocked_source_id
    )
    original_input = cast(V2ExtractionLLMInput, later_extraction_request.input_artifact)
    assert original_input.untrusted_source_text == SOURCE_TEXT
    assert original_input.selectable_source_text.count("62 percent reported") == 1
    assert later_extraction_request.rendered_prompt.count("62 percent reported") == 1
    assert "[1]" in later_extraction_request.rendered_prompt


def test_unreservable_source_envelope_skips_only_that_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(v2_deep_analysis, "V2_DEEP_ANALYSIS_MAX_WORKERS", 1)
    original_remaining_source_envelope = _remaining_source_envelope
    blocked_source_id: UUID | None = None

    def block_only_first_source(
        *,
        path: str,
        run_id: UUID,
        candidate: object,
        routing_config: object,
        audit: object = None,
    ) -> V2DeepAnalysisSourceEnvelope:
        nonlocal blocked_source_id
        envelope = original_remaining_source_envelope(
            path=path,
            run_id=run_id,
            candidate=candidate,
            routing_config=routing_config,
            audit=audit,
        )
        if blocked_source_id is None:
            blocked_source_id = envelope.candidate.source_id
        if envelope.candidate.source_id == blocked_source_id:
            return envelope.model_copy(update={"source_cap_reservable": False})
        return envelope

    monkeypatch.setattr(
        v2_deep_analysis,
        "_remaining_source_envelope",
        block_only_first_source,
    )
    result = _run(
        tmp_path / "source-envelope-backfill.sqlite3",
        _V2Model(completed_rounds=2),
        _Search(unique_results=True),
        _Scraper(),
    )

    backfill = _backfill(result.db_path, result.run_id)
    assert blocked_source_id is not None
    executions = {item.source_id: item for item in backfill.source_executions}
    assert executions[blocked_source_id].state is (
        V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
    )
    assert len(backfill.final_execution_order) > 1
    assert any(
        item.state is V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED
        for item in backfill.source_executions
        if item.source_id != blocked_source_id
    )


def test_source_cap_cause_from_analyst_is_typed_and_backfilled(tmp_path: Path) -> None:
    model = _AnalystBudgetCauseModel(
        V2SourceBudgetExceededError("source token cap cannot cover Analyst call")
    )
    result = _run(
        tmp_path / "analyst-source-budget-backfill.sqlite3",
        model,
        _Search(unique_results=True),
        _Scraper(),
    )

    backfill = _backfill(result.db_path, result.run_id)
    assert model.blocked_source_id is not None
    executions = {item.source_id: item for item in backfill.source_executions}
    assert executions[model.blocked_source_id].state is (
        V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
    )
    assert executions[model.blocked_source_id].failure_reason is not None
    assert executions[model.blocked_source_id].failure_reason.startswith(
        "V2SourceBudgetExceededError:"
    )
    assert any(
        item.state is V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED
        for item in backfill.source_executions
        if item.source_id != model.blocked_source_id
    )


def test_run_budget_rejection_stops_source_backfill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(v2_deep_analysis, "V2_DEEP_ANALYSIS_MAX_WORKERS", 1)
    model = _BudgetCauseModel(V2BudgetExceededError("run-wide token ceiling exhausted"))

    result = _run(
        tmp_path / "run-budget-stops-backfill.sqlite3",
        model,
        _Search(unique_results=True),
        _Scraper(),
    )

    backfill = _backfill(result.db_path, result.run_id)
    execution_by_id = {item.source_id: item for item in backfill.source_executions}
    assert model.blocked_source_id is not None
    assert execution_by_id[model.blocked_source_id].state is (
        V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
    )
    assert model.extractor_source_ids == [model.blocked_source_id]
    later_source_ids = set(backfill.final_queue_result.priority_source_ids) - {
        model.blocked_source_id
    }
    assert later_source_ids
    assert all(
        execution_by_id[source_id].state is V2DeepAnalysisSourceExecutionState.NOT_ATTEMPTED
        for source_id in later_source_ids
    )


def test_worker_failure_traverses_budget_exception_causes() -> None:
    from agents.v2_deep_analysis import _worker_failure

    source_id = UUID(int=1)
    source_error = V2SourceBudgetExceededError("source cap exhausted")
    run_error = V2BudgetExceededError("run cap exhausted")
    try:
        raise RuntimeError("wrapped") from source_error
    except RuntimeError as source_wrapper:
        source_result = _worker_failure(source_id, source_wrapper)
    try:
        raise RuntimeError("wrapped") from run_error
    except RuntimeError as run_wrapper:
        run_result = _worker_failure(source_id, run_wrapper)

    assert source_result.failure_state is V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED
    assert run_result.failure_state is V2DeepAnalysisSourceExecutionState.BUDGET_EXHAUSTED
