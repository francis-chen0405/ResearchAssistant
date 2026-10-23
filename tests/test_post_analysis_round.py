"""The optional follow-up uses disposable runs and preserves earlier admissions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_query_production as production
import test_v2_phase12_production as phase12

import researchassistant.agents.post_analysis_round as post_module
import researchassistant.research.v2_orchestrator as orchestrator
from researchassistant.agents.post_analysis_round import (
    POST_ANALYSIS_COMBINED_KEY,
    POST_ANALYSIS_COMPLETION_KEY,
    POST_ANALYSIS_DECISION_KEY,
    POST_ANALYSIS_GAP_KEY,
    V2PostAnalysisRoundOutcome,
    run_v2_post_analysis_round,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveRoundStatus,
    V2AdaptiveStopCode,
)
from researchassistant.agents.v2_evidence_admission import (
    V2_EVIDENCE_ADMISSION_ARTIFACT_KEY,
)
from researchassistant.agents.v2_round_four import V2_POST13_GAP_AFTER_ROUND_THREE_KEY
from researchassistant.api.application_services.result_reads import read_evidence
from researchassistant.contracts.model_evidence import (
    V2EvidenceAdmissionBatchResult,
)
from researchassistant.contracts.models import (
    V2ClaimCoverageAssessment,
    V2ClaimCoverageState,
    V2GapAnalysisModelOutput,
    V2GapAnalysisOutput,
)
from researchassistant.providers.llm import LLMRequest
from researchassistant.providers.v2_budget import V2CancellationRequested
from researchassistant.research.v2_orchestrator import V2ProductionState
from researchassistant.storage.source_leads import read_source_leads
from researchassistant.storage.store import read_v2_artifact


class _MissingAfterInitialAssessment(production._ConceptModel):
    def generate(self, request: LLMRequest) -> object:
        if (
            request.requested_output_type.__name__ == "V2GapAnalysisModelOutput"
            and self.gap_attempts == 0
        ):
            self.requests.append(request)
            self.gap_attempts += 1
            self.successful_gaps += 1
            coverage = tuple(
                V2ClaimCoverageAssessment(
                    dimension=item.dimension,
                    claim_component=item.claim_component,
                    coverage_state=V2ClaimCoverageState.MISSING,
                    evidence_summary="The initial source has not resolved this component.",
                    kind=item.kind,
                    searchable=item.searchable,
                    unavailable_reason=item.unavailable_reason,
                )
                for item in request.input_artifact.claim_coverage_focus
            )
            return V2GapAnalysisModelOutput(
                coverage_summary="A claim component remains unresolved.",
                claim_coverage_map=coverage,
                material_gaps=(),
                continue_research=False,
                stop_reason="Initial search has no justified new action yet.",
                new_search_directions=(),
                discovered_terms=("completion",),
            )
        if request.requested_output_type.__name__ == "V2GapAnalysisModelOutput":
            self.completed_rounds = 3
        return super().generate(request)


class _NoUsefulPostGap(_MissingAfterInitialAssessment):
    def generate(self, request: LLMRequest) -> object:
        if (
            request.requested_output_type.__name__ == "V2GapAnalysisModelOutput"
            and self.gap_attempts > 0
        ):
            self.completed_rounds = 1
            return production._ConceptModel.generate(self, request)
        return super().generate(request)


def test_one_post_analysis_round_reuses_prior_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "post-analysis-disposable.sqlite"
    run_id = uuid4()
    model = _MissingAfterInitialAssessment(completed_rounds=1)
    search = phase12._Search(unique_results=True)
    captured: dict[str, object] = {}
    original = orchestrator.run_v2_post_analysis_round

    def tracked(**kwargs: object) -> V2PostAnalysisRoundOutcome:
        captured.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(orchestrator, "run_v2_post_analysis_round", tracked)
    result = production._run_fresh(
        path,
        model=model,
        search=search,
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    outcome = V2PostAnalysisRoundOutcome.model_validate_json(
        read_v2_artifact(path, run_id, POST_ANALYSIS_COMPLETION_KEY).payload_json
    )
    assert outcome.decision.next_round == 2
    assessed_gap = V2GapAnalysisOutput.model_validate_json(
        read_v2_artifact(path, run_id, POST_ANALYSIS_GAP_KEY).payload_json
    )
    assert assessed_gap.input.assessed_source_findings
    assert outcome.decision.assessed_source_ids == tuple(
        item.source_id for item in assessed_gap.input.assessed_source_findings
    )
    assert outcome.continuation.stopping_decision.completed_rounds == 2
    assert outcome.new_source_ids
    assert read_v2_artifact(path, run_id, POST_ANALYSIS_DECISION_KEY)
    assert result.final_output is not None
    assert len(result.final_output.all_surviving_sources) > 1
    display = read_evidence(path, run_id)
    assert {item.source_id for item in display.items} == {
        item.source_id
        for item in outcome.admission.source_results
        if item.evidence_record is not None
    }
    assert read_source_leads(path, run_id).items
    original_admission = V2EvidenceAdmissionBatchResult.model_validate_json(
        read_v2_artifact(path, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY).payload_json
    )
    assert outcome.admission.source_results[: len(original_admission.source_results)] == (
        original_admission.source_results
    )
    assert (
        outcome.admission.analyst_result.source_results[
            : len(original_admission.analyst_result.source_results)
        ]
        == original_admission.analyst_result.source_results
    )
    for source in outcome.admission.source_results:
        record = source.evidence_record
        if record is None:
            continue
        context = next(
            item
            for item in outcome.admission.analyst_result.input.queued_candidates
            if item.candidate.quote_block_id == record.quote_block_id
        )
        snapshot, quote = context.snapshot, context.candidate
        assert snapshot.snapshot_sha256 == record.snapshot_sha256
        assert quote.snapshot_id == record.snapshot_id
        assert quote.segment_offsets == list(record.segment_offsets)
        assert all(
            snapshot.normalized_text[span.start_char : span.end_char] in quote.extracted_quote_block
            for span in record.segment_offsets
        )
    request_count = len(model.requests)
    provider_count = len(search.requests)
    assert run_v2_post_analysis_round(**captured) == outcome
    assert len(model.requests) == request_count
    assert len(search.requests) == provider_count


def _admitted_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], _MissingAfterInitialAssessment, phase12._Search]:
    path = tmp_path / "post-analysis-gate-disposable.sqlite"
    model = _MissingAfterInitialAssessment(completed_rounds=1)
    search = phase12._Search(unique_results=True)
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            continuation=kwargs["continuation"],
            admission=kwargs["admission"],
            round_four_gap=None,
        )

    monkeypatch.setattr(orchestrator, "run_v2_post_analysis_round", capture)
    result = production._run_fresh(
        path, model=model, search=search, scraper=phase12._Scraper(), run_id=uuid4()
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    return captured, model, search


def test_skip_when_admitted_coverage_is_adequate(tmp_path: Path) -> None:
    path = tmp_path / "post-analysis-adequate-disposable.sqlite"
    run_id = uuid4()
    model = production._ConceptModel(completed_rounds=1)
    search = phase12._Search(unique_results=True)
    result = production._run_fresh(
        path, model=model, search=search, scraper=phase12._Scraper(), run_id=run_id
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    outcome = V2PostAnalysisRoundOutcome.model_validate_json(
        read_v2_artifact(path, run_id, POST_ANALYSIS_COMPLETION_KEY).payload_json
    )
    assert outcome.decision.next_round is None
    assert "adequate" in outcome.stop_reason
    assert outcome.admission.source_results


def test_missing_coverage_without_useful_new_action_stops(tmp_path: Path) -> None:
    path = tmp_path / "post-analysis-no-action-disposable.sqlite"
    run_id = uuid4()
    search = phase12._Search(unique_results=True)
    result = production._run_fresh(
        path,
        model=_NoUsefulPostGap(completed_rounds=1),
        search=search,
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    outcome = V2PostAnalysisRoundOutcome.model_validate_json(
        read_v2_artifact(path, run_id, POST_ANALYSIS_COMPLETION_KEY).payload_json
    )
    assert outcome.decision.next_round is None
    assert "no useful novel" in outcome.stop_reason
    assert outcome.continuation.stopping_decision.completed_rounds == 1
    assert search.requests
    assert all(
        request.compiled_query is not None
        and request.compiled_query.conceptual_query.round_number == 1
        for request in search.requests
    )


def test_duplicate_follow_up_retains_only_earlier_evidence(tmp_path: Path) -> None:
    path = tmp_path / "post-analysis-duplicate-disposable.sqlite"
    run_id = uuid4()
    result = production._run_fresh(
        path,
        model=_MissingAfterInitialAssessment(completed_rounds=1),
        search=phase12._Search(unique_results=False),
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    outcome = V2PostAnalysisRoundOutcome.model_validate_json(
        read_v2_artifact(path, run_id, POST_ANALYSIS_COMPLETION_KEY).payload_json
    )
    original_admission = V2EvidenceAdmissionBatchResult.model_validate_json(
        read_v2_artifact(path, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY).payload_json
    )
    assert outcome.decision.next_round == 2
    assert outcome.new_source_ids == ()
    assert outcome.admission.source_results == original_admission.source_results
    assert outcome.admission.analyst_result.source_results == (
        original_admission.analyst_result.source_results
    )
    assert outcome.admission.analyst_result.input.queue_result.input.gap_history
    assert "no novel" in outcome.stop_reason


def test_round_four_slot_waits_for_admitted_source_assessments(tmp_path: Path) -> None:
    path = tmp_path / "post-analysis-round-four-disposable.sqlite"
    run_id = uuid4()
    result = production._run_fresh(
        path,
        model=production._ConceptModel(completed_rounds=4),
        search=phase12._Search(unique_results=True),
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    outcome = V2PostAnalysisRoundOutcome.model_validate_json(
        read_v2_artifact(path, run_id, POST_ANALYSIS_COMPLETION_KEY).payload_json
    )
    gap = outcome.round_four_gap
    assert outcome.decision.next_round == 4
    assert gap is not None
    assert gap.input.assessed_source_findings
    assert gap == type(gap).model_validate_json(
        read_v2_artifact(path, run_id, V2_POST13_GAP_AFTER_ROUND_THREE_KEY).payload_json
    )
    assert outcome.continuation.stopping_decision.completed_rounds == 4
    assert outcome.new_source_ids
    original_admission = V2EvidenceAdmissionBatchResult.model_validate_json(
        read_v2_artifact(path, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY).payload_json
    )
    assert outcome.admission.source_results[: len(original_admission.source_results)] == (
        original_admission.source_results
    )


def test_budget_gate_stops_before_gap_or_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, model, search = _admitted_inputs(tmp_path, monkeypatch)
    kwargs["budget_snapshot"] = lambda: V2AdaptiveBudgetState(
        model_calls_remaining=6,
        tokens_remaining=60_000,
        cost_remaining_usd=0,
        protected_downstream_model_calls=4,
        protected_downstream_tokens=1,
    )
    model_count, provider_count = len(model.requests), len(search.requests)
    outcome = run_v2_post_analysis_round(**kwargs)
    assert outcome.decision.next_round is None
    assert "budget" in outcome.stop_reason
    assert len(model.requests) == model_count
    assert len(search.requests) == provider_count


def test_unknown_reservation_and_cancellation_stop_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, model, search = _admitted_inputs(tmp_path, monkeypatch)
    kwargs["cancellation_requested"] = lambda: True
    with pytest.raises(V2CancellationRequested):
        run_v2_post_analysis_round(**kwargs)
    kwargs["cancellation_requested"] = lambda: False
    monkeypatch.setattr(post_module, "query_dispatch_states", lambda *_: {uuid4(): "unknown"})
    model_count, provider_count = len(model.requests), len(search.requests)
    outcome = run_v2_post_analysis_round(**kwargs)
    assert outcome.decision.next_round is None
    assert "unknown request" in outcome.stop_reason
    assert len(model.requests) == model_count
    assert len(search.requests) == provider_count


def test_partial_replay_keeps_saved_queue_and_provider_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, model, search = _admitted_inputs(tmp_path, monkeypatch)
    real_deep = post_module.run_v2_deep_analysis_with_backfill

    def interrupted(**_kwargs: object) -> object:
        raise RuntimeError("fixture interruption after queue")

    monkeypatch.setattr(post_module, "run_v2_deep_analysis_with_backfill", interrupted)
    with pytest.raises(RuntimeError, match="fixture interruption"):
        run_v2_post_analysis_round(**kwargs)
    provider_count = len(search.requests)
    model_count = len(model.requests)
    monkeypatch.setattr(post_module, "run_v2_deep_analysis_with_backfill", real_deep)
    outcome = run_v2_post_analysis_round(**kwargs)
    assert outcome.new_source_ids
    assert len(search.requests) == provider_count
    assert len(model.requests) > model_count


def test_replay_after_combined_admission_write_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, model, search = _admitted_inputs(tmp_path, monkeypatch)
    path = kwargs["db_path"]
    run_id = kwargs["initial_plan"].run_id
    original_insert = post_module.insert_v2_artifact

    def interrupt_after_write(*args: object) -> object:
        result = original_insert(*args)
        if args[1] == POST_ANALYSIS_COMBINED_KEY:
            raise RuntimeError("fixture interruption after combined admission")
        return result

    monkeypatch.setattr(post_module, "insert_v2_artifact", interrupt_after_write)
    with pytest.raises(RuntimeError, match="fixture interruption"):
        run_v2_post_analysis_round(**kwargs)
    combined_before = read_v2_artifact(path, run_id, POST_ANALYSIS_COMBINED_KEY)
    provider_count, model_count = len(search.requests), len(model.requests)
    monkeypatch.setattr(post_module, "insert_v2_artifact", original_insert)
    outcome = run_v2_post_analysis_round(**kwargs)
    assert outcome.admission == V2EvidenceAdmissionBatchResult.model_validate_json(
        combined_before.payload_json
    )
    assert read_v2_artifact(path, run_id, POST_ANALYSIS_COMBINED_KEY) == combined_before
    assert len(search.requests) == provider_count
    assert len(model.requests) == model_count


class _FailsFollowupSearch(phase12._Search):
    def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
        if "round 2" in request.query_text:
            self.requests.append(request)
            raise RuntimeError("fixture follow-up provider failure")
        return super().search(request)


def test_degraded_follow_up_records_failure_and_preserves_admission(
    tmp_path: Path,
) -> None:
    path = tmp_path / "post-analysis-failed-follow-up-disposable.sqlite"
    run_id = uuid4()
    search = _FailsFollowupSearch(unique_results=True)
    result = production._run_fresh(
        path,
        model=_MissingAfterInitialAssessment(completed_rounds=1),
        search=search,
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    outcome = V2PostAnalysisRoundOutcome.model_validate_json(
        read_v2_artifact(path, run_id, POST_ANALYSIS_COMPLETION_KEY).payload_json
    )
    prior = V2EvidenceAdmissionBatchResult.model_validate_json(
        read_v2_artifact(path, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY).payload_json
    )
    assert outcome.admission.source_results == prior.source_results
    assert outcome.admission.analyst_result.source_results == (prior.analyst_result.source_results)
    assert outcome.admission.analyst_result.input.queue_result.input.gap_history
    assert outcome.continuation.rounds[-1].status is V2AdaptiveRoundStatus.DEGRADED
    assert outcome.continuation.stopping_decision.stop_code is V2AdaptiveStopCode.PROVIDER_FAILURE
    assert "failed searches" in outcome.continuation.stopping_decision.stopping_reason
    assert outcome.continuation.stopping_decision.completed_rounds == 2
