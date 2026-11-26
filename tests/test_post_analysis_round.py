"""The optional follow-up uses disposable runs and preserves earlier admissions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

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
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2EvidenceRelationship,
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
    post_analysis_budget = captured["budget_snapshot"]()
    assert post_analysis_budget.protected_downstream_model_calls == 0
    assert post_analysis_budget.protected_downstream_tokens == 0
    assert post_analysis_budget.protected_downstream_cost_usd == 0
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


@pytest.mark.parametrize("failure_count", (0, 2))
def test_post_analysis_sample_retains_distinct_assessed_relationships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_count: int
) -> None:
    captured, _model, _search = _admitted_inputs(tmp_path, monkeypatch)
    admission = captured["admission"]
    gap = captured["gaps"][-1]
    template = admission.analyst_result.source_results[0]
    relationships = (
        V2EvidenceRelationship.CHALLENGES,
        V2EvidenceRelationship.CHALLENGES,
        V2EvidenceRelationship.CHALLENGES,
        V2EvidenceRelationship.QUALIFIES,
        V2EvidenceRelationship.QUALIFIES,
        V2EvidenceRelationship.SUPPORTS,
        V2EvidenceRelationship.SUPPORTS,
    )
    reviewed = tuple(
        template.model_copy(
            update={
                "source_id": UUID(int=index + 1),
                "assessment": template.assessment.model_copy(
                    update={"relationship_to_claim": relationship}
                ),
            }
        )
        for index, relationship in enumerate(relationships)
    )
    failed = tuple(
        V2EvidenceAnalystSourceResult(
            run_id=admission.run_id,
            source_id=UUID(int=100 + index),
            direction=template.direction,
            state=V2EvidenceAnalystState.FAILED,
            failure="The acquired text could not be assessed.",
        )
        for index in range(failure_count)
    )
    # Only the sampling projection is under test; retain real typed source
    # assessments and gap metadata without publishing a synthetic admission.
    sources = (*reviewed, *failed)
    admission = admission.model_copy(
        update={
            "analyst_result": admission.analyst_result.model_copy(
                update={"source_results": sources}
            )
        }
    )
    gap = gap.model_copy(
        update={
            "input": gap.input.model_copy(
                update={
                    "surviving_sources": tuple(
                        gap.input.surviving_sources[0].model_copy(
                            update={"source_cluster_id": source.source_id}
                        )
                        for source in sources
                    )
                }
            )
        }
    )
    preferred = frozenset((reviewed[2].source_id, reviewed[-1].source_id))
    findings = post_module._assessed_findings(admission, gap, preferred=preferred)
    reordered = admission.model_copy(
        update={
            "analyst_result": admission.analyst_result.model_copy(
                update={"source_results": tuple(reversed(sources))}
            )
        }
    )
    assert post_module._assessed_findings(reordered, gap, preferred=preferred) == findings
    assert len(findings) == 4
    assert len({item.source_id for item in findings}) == 4
    assert {item.source_id for item in findings} >= preferred
    assert {item.source_id for item in findings if item.failure} == {
        item.source_id for item in failed
    }
    if not failure_count:
        assert {item.relationship_to_claim for item in findings} == {
            "supports",
            "challenges",
            "qualifies",
        }
    by_id = {source.source_id: source for source in sources}
    for finding in findings:
        source = by_id[finding.source_id]
        if source.assessment is not None:
            assert finding.supported_proposition == (
                source.assessment.narrowest_supported_proposition
            )
            assert finding.relationship_to_claim == source.assessment.relationship_to_claim
        else:
            assert finding.supported_proposition is None
    hidden_id = findings[0].source_id
    restricted_gap = gap.model_copy(
        update={
            "input": gap.input.model_copy(
                update={
                    "surviving_sources": tuple(
                        source
                        for source in gap.input.surviving_sources
                        if source.source_cluster_id != hidden_id
                    )
                }
            )
        }
    )
    assert hidden_id not in {
        item.source_id
        for item in post_module._assessed_findings(admission, restricted_gap, preferred=preferred)
    }


@pytest.mark.parametrize("has_eligible_provider", (True, False))
def test_skip_when_admitted_coverage_is_adequate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, has_eligible_provider: bool
) -> None:
    if not has_eligible_provider:
        monkeypatch.setattr(post_module, "available_query_budgets", lambda *_args, **_kwargs: ())
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


def test_unknown_request_does_not_stop_independent_provider_followup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured, _model, search = _admitted_inputs(tmp_path, monkeypatch)
    before = len(search.requests)

    def unknown_states(source: object, run_id: object) -> dict[object, str]:
        return {run_id: "unknown"}

    monkeypatch.setattr(post_module, "query_dispatch_states", unknown_states)
    outcome = run_v2_post_analysis_round(**captured)

    assert (
        outcome.continuation.stopping_decision.stop_code is not V2AdaptiveStopCode.PROVIDER_FAILURE
    )
    assert (
        "One post-analysis evidence round completed"
        in outcome.continuation.stopping_decision.stopping_reason
    )
    assert "unknown outcome" not in outcome.continuation.stopping_decision.stopping_reason
    assert "reservation is retained" in outcome.stop_reason
    assert len(outcome.admission.source_results) >= len(captured["admission"].source_results)
    assert len(search.requests) > before
    assert run_v2_post_analysis_round(**captured) == outcome


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


@pytest.mark.slow
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


@pytest.mark.parametrize(
    ("completed_queries", "survivors", "eligible"),
    [(2, 7, True), (2, 0, False), (0, 0, False)],
)
def test_partial_search_requires_successful_queries_and_usable_results(
    completed_queries: int, survivors: int, eligible: bool
) -> None:
    from datetime import UTC, datetime

    from researchassistant.agents.adaptive_handoffs import V2AdaptiveRoundExecution

    round_summary = V2AdaptiveRoundExecution(
        run_id=uuid4(),
        round_number=3,
        targeted_gap_ids=(),
        status=V2AdaptiveRoundStatus.DEGRADED,
        planned_query_count=3,
        completed_query_count=completed_queries,
        failed_query_count=3 - completed_queries,
        new_source_count=survivors,
        duplicate_source_count=0,
        survivor_additions=survivors,
        completed_at=datetime.now(UTC),
    )
    assert round_summary.usable_for_follow_up is eligible


def test_empty_round_three_skips_another_search_and_retains_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = uuid4()
    model = production._ConceptModel(completed_rounds=4)
    outcomes = []
    reason = "Round 3 found no new usable sources. Remaining gaps are reported in the brief."

    def simulate_empty_round(**kwargs: object) -> V2PostAnalysisRoundOutcome:
        continuation = kwargs["continuation"]
        last_round = continuation.rounds[-1]
        assert last_round.round_number == 3
        assert last_round.status is V2AdaptiveRoundStatus.COMPLETED
        kwargs["continuation"] = continuation.model_copy(
            update={
                "rounds": (
                    *continuation.rounds[:-1],
                    last_round.model_copy(update={"survivor_additions": 0}),
                ),
            }
        )
        model_calls = len(model.requests)
        outcome = run_v2_post_analysis_round(**kwargs)
        assert len(model.requests) == model_calls
        assert outcome.admission == kwargs["admission"]
        assert run_v2_post_analysis_round(**kwargs) == outcome
        outcomes.append(outcome)
        return outcome

    monkeypatch.setattr(orchestrator, "run_v2_post_analysis_round", simulate_empty_round)
    result = production._run_fresh(
        tmp_path / "no-round-four.sqlite",
        model=model,
        search=phase12._Search(unique_results=True),
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert len(outcomes) == 1
    assert outcomes[0].decision.next_round is None
    assert outcomes[0].continuation.stopping_decision.stopping_reason == reason


def test_budget_gate_stops_before_gap_or_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, model, search = _admitted_inputs(tmp_path, monkeypatch)
    kwargs["budget_snapshot"] = lambda: V2AdaptiveBudgetState(
        model_calls_remaining=100,
        tokens_remaining=60_000,
        cost_remaining_usd="10",
        protected_downstream_model_calls=4,
        protected_downstream_tokens=1,
    )
    model_count, provider_count = len(model.requests), len(search.requests)
    outcome = run_v2_post_analysis_round(**kwargs)
    assert outcome.decision.next_round is None
    assert outcome.stop_reason.startswith(
        "Follow-up budget exceeded the remaining allowance for tokens. Tokens: "
    )
    assert "1 protected), 60000 remaining." in outcome.stop_reason
    stopping = outcome.continuation.stopping_decision
    assert stopping.stop_code is V2AdaptiveStopCode.BUDGET
    assert stopping.stopping_reason == outcome.stop_reason
    assert len(model.requests) == model_count
    assert len(search.requests) == provider_count


def test_no_eligible_provider_and_cancellation_stop_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, model, search = _admitted_inputs(tmp_path, monkeypatch)
    kwargs["cancellation_requested"] = lambda: True
    with pytest.raises(V2CancellationRequested):
        run_v2_post_analysis_round(**kwargs)
    kwargs["cancellation_requested"] = lambda: False
    monkeypatch.setattr(post_module, "available_query_budgets", lambda *_args, **_kwargs: ())
    model_count, provider_count = len(model.requests), len(search.requests)
    outcome = run_v2_post_analysis_round(**kwargs)
    assert outcome.decision.next_round is None
    assert "no eligible provider" in outcome.stop_reason
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
