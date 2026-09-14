"""Offline regressions; rejected historical query text was not retained."""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_v2_phase3_initial_planner import FakeInitialPlanner, _environment
from test_v2_phase7_adaptive_search import FakeAdaptiveLLM, FakeSearch, _luna_stop, _proposal, _run

from agents.v2_adaptive_search import (
    V2AdaptiveBudgetError,
    V2AdaptiveBudgetState,
    V2AdaptivePlannedRound,
    V2AdaptivePlanValidationError,
    V2AdaptiveStopCode,
    _plan_round,
)
from agents.v2_initial_planner import run_v2_initial_planner
from models import DiscoveryProvider, ResearchDirections
from providers.v2_routing import V2RoutingConfig


def _planning_fixture(
    tmp_path: Path,
    llm: FakeAdaptiveLLM,
    *,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState] | None = None,
    cancellation: Callable[[], bool] | None = None,
) -> tuple[Callable[[], V2AdaptivePlannedRound], UUID, str]:
    from test_v2_phase7_adaptive_search import NOW, _db, _gap, _initial_plan, _routing

    run_id = uuid4()
    plan = _initial_plan(run_id)
    path = _db(tmp_path, run_id)

    def invoke() -> V2AdaptivePlannedRound:
        return _plan_round(
            path=str(path),
            round_number=2,
            initial_plan=plan,
            gap_output=_gap(plan, continue_research=True),
            previous_queries=tuple(query.query_text for query in plan.searches),
            provider_attempts={},
            search_providers={DiscoveryProvider.EXA: FakeSearch()},
            llm_provider=llm,
            routing_config=_routing(),
            budget=V2AdaptiveBudgetState(model_calls_remaining=20),
            budget_snapshot=budget_snapshot,
            cancellation_requested=cancellation,
            clock=lambda: NOW,
        )

    return invoke, run_id, str(path)


def test_fresh_empty_focus_gets_exact_claim_default(tmp_path: Path) -> None:
    claim = "Genetic enhancement is ableism"
    result = run_v2_initial_planner(
        claim,
        db_path=tmp_path / "focus.sqlite3",
        directions=ResearchDirections(),
        discovery_providers=(DiscoveryProvider.EXA,),
        llm_provider=FakeInitialPlanner(),
        routing_config=V2RoutingConfig.from_environment(
            _environment(), repository_revision="reliability-test"
        ),
    )
    assert len(result.planner_output.claim_coverage_focus) == 1
    assert result.planner_output.claim_coverage_focus[0].claim_component == claim


def test_duplicate_proposals_get_two_bounded_attempts(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("broad round one direct evidence")] * 2,
        gap_outputs=[],
    )
    search = FakeSearch()
    result = _run(tmp_path, initial_gap_continue=True, llm=llm, search=search)
    assert result.stopping_decision.stop_code is V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN
    assert len(llm.requests) == 2
    assert search.requests == []


def test_valid_repair_executes_only_replacement(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal("broad round one direct evidence"),
            _proposal("independent cohort outcome instrument evaluation"),
        ],
        gap_outputs=[_luna_stop()],
    )
    search = FakeSearch()
    result = _run(tmp_path, initial_gap_continue=True, llm=llm, search=search)
    assert result.stopping_decision.completed_rounds == 2
    assert len(search.requests) == 1
    assert "matched query 1" in llm.requests[1].rendered_prompt
    assert "Repair the entire proposal" in llm.requests[1].rendered_prompt


def test_relevance_does_not_resolve_gap_and_legacy_is_preserved(tmp_path: Path) -> None:
    from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved
    from test_v2_phase10_reviewer_ledger import _run as evidence_run

    from agents.v2_final_output import _unresolved_gaps
    from models import ResearchDirection, V2SourceSelectionGap

    _, evidence = evidence_run(tmp_path, Phase10Provider([_approved()]))
    source = evidence.source_results[0].model_copy(
        update={
            "provenance": evidence.source_results[0].provenance.model_copy(
                update={"relevant_gap_ids": ("gap-direct",)}
            )
        }
    )
    evidence = evidence.model_copy(update={"source_results": (source,)})
    assert source.provenance.relevant_gap_ids
    gap = V2SourceSelectionGap(
        gap_id=source.provenance.relevant_gap_ids[0],
        direction=ResearchDirection.SUPPORT,
        missing_evidence="Direct evidence establishing the exact claim",
        assessed_after_round=1,
    )
    assert _unresolved_gaps((gap,), evidence) == ()
    selection = evidence.analyst_result.input.queue_result
    fresh_selection = selection.model_copy(
        update={
            "input": selection.input.model_copy(update={"gap_reporting_policy": "conservative-v1"})
        }
    )
    fresh_input = evidence.analyst_result.input.model_copy(update={"queue_result": fresh_selection})
    fresh = evidence.model_copy(
        update={"analyst_result": evidence.analyst_result.model_copy(update={"input": fresh_input})}
    )
    assert _unresolved_gaps((gap,), fresh) == (gap,)


def test_planning_resume_reuses_accepted_repair(tmp_path: Path) -> None:
    from agents.v2_adaptive_search import V2PlanningOutcome
    from store import read_v2_artifact

    llm = FakeAdaptiveLLM(
        search_outputs=[
            _proposal("broad round one direct evidence"),
            _proposal("independent cohort outcome instrument evaluation"),
        ],
        gap_outputs=[],
    )
    invoke, run_id, path = _planning_fixture(tmp_path, llm)
    first = invoke()
    assert invoke() == first
    assert len(llm.requests) == 2
    rejected = V2PlanningOutcome.model_validate_json(
        read_v2_artifact(
            path, run_id, "adaptive-reliability-round-2-attempt-1-outcome"
        ).payload_json
    )
    assert rejected.rejection_code == "repeated_query"
    assert rejected.candidate == _proposal("broad round one direct evidence")


def test_repair_refreshes_budget_and_preserves_reserve(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("broad round one direct evidence")], gap_outputs=[]
    )
    snapshots = iter(
        (
            V2AdaptiveBudgetState(model_calls_remaining=20),
            V2AdaptiveBudgetState(model_calls_remaining=1),
        )
    )
    invoke, _, _ = _planning_fixture(tmp_path, llm, budget_snapshot=lambda: next(snapshots))
    with pytest.raises(V2AdaptiveBudgetError):
        invoke()
    assert len(llm.requests) == 1


@pytest.mark.parametrize("resource", ["tokens", "cost"])
def test_downstream_token_and_cost_reserves_are_protected(tmp_path: Path, resource: str) -> None:
    from agents.v2_adaptive_search import _require_budget

    del tmp_path
    budget = V2AdaptiveBudgetState(
        model_calls_remaining=20,
        tokens_remaining=100,
        cost_remaining_usd=Decimal("1"),
        protected_downstream_tokens=90,
        protected_downstream_cost_usd=Decimal("0.9"),
    )
    with pytest.raises(V2AdaptiveBudgetError):
        _require_budget(
            budget,
            11 if resource == "tokens" else 1,
            Decimal("0.01") if resource == "tokens" else Decimal("0.11"),
        )


def test_cancel_before_repair_does_not_call_again(tmp_path: Path) -> None:
    from agents.v2_adaptive_search import V2AdaptiveCancellationError

    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("broad round one direct evidence")], gap_outputs=[]
    )
    invoke, _, _ = _planning_fixture(tmp_path, llm, cancellation=lambda: bool(llm.requests))
    with pytest.raises(V2AdaptiveCancellationError):
        invoke()
    assert len(llm.requests) == 1


@pytest.mark.parametrize("persist_outcome", [False, True])
def test_crash_after_call_never_reissues_the_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    persist_outcome: bool,
) -> None:
    from datetime import datetime

    import agents.v2_adaptive_search as adaptive
    from models import StrictModel, V2PersistedArtifact

    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("independent cohort outcome instrument evaluation")],
        gap_outputs=[],
    )
    invoke, _, _ = _planning_fixture(tmp_path, llm)
    original = adaptive.insert_v2_artifact

    def crash(path: str, key: str, artifact: StrictModel, at: datetime) -> V2PersistedArtifact:
        if key.endswith("-outcome"):
            if persist_outcome:
                original(path, key, artifact, at)
            raise RuntimeError("simulated process crash")
        return original(path, key, artifact, at)

    monkeypatch.setattr(adaptive, "insert_v2_artifact", crash)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        invoke()
    monkeypatch.setattr(adaptive, "insert_v2_artifact", original)
    if persist_outcome:
        assert invoke().plan.searches
    else:
        with pytest.raises(V2AdaptivePlanValidationError, match="unknown outcome"):
            invoke()
    assert len(llm.requests) == 1


def test_exhausted_attempts_stay_exhausted_on_restart(tmp_path: Path) -> None:
    llm = FakeAdaptiveLLM(
        search_outputs=[_proposal("broad round one direct evidence")] * 2, gap_outputs=[]
    )
    invoke, _, _ = _planning_fixture(tmp_path, llm)
    for _ in range(2):
        with pytest.raises(V2AdaptivePlanValidationError, match="two invalid plans"):
            invoke()
    assert len(llm.requests) == 2


@pytest.mark.parametrize("recover", [True, False])
def test_support_only_production_preserves_gaps_and_audits_physical_attempts(
    tmp_path: Path,
    recover: bool,
) -> None:
    from test_v2_phase12_production import _run as production_run
    from test_v2_phase12_production import _Scraper, _Search, _V2Model

    from agents.v2_adaptive_search import V2PlanningAttempt
    from agents.v2_final_output import render_v2_final_output
    from providers.llm import LLMRequest, LLMStage
    from providers.v2_budget import V2PhysicalCallStart, V2RunCeilings
    from store import read_v2_artifact

    class RepairModel(_V2Model):
        def generate(self, request: LLMRequest) -> object:
            output = super().generate(request)
            if request.stage is LLMStage.SEARCH_AGENT and (
                self.search_agent_calls == 1 or not recover
            ):
                return _proposal(
                    request.input_artifact.previous_queries[0],
                    targeted_gap_ids=(request.input_artifact.material_gaps[0].gap_id,),
                )
            return output

    model = RepairModel(completed_rounds=2)
    path = tmp_path / "production.sqlite3"
    result = production_run(
        path,
        model,
        _Search(unique_results=True),
        _Scraper(),
        ceilings=V2RunCeilings(max_total_cost_usd=Decimal("5")),
    )
    assert result.state.value == "released", result.failure_reason
    output = result.final_output
    assert output is not None
    assert output.stopping.completed_rounds == (2 if recover else 1)
    assert model.search_agent_calls == 2
    assert output.directions.challenge_enabled is False
    assert [gap.gap_id for gap in output.unresolved_material_gaps] == ["gap-round-3"]
    assert output.claim_coverage_map
    assert "Independent replication evidence remains missing." in render_v2_final_output(output)
    from agents.v2_adaptive_search import V2_ADAPTIVE_COMPLETION_KEY, V2AdaptiveContinuationResult
    from agents.v2_deep_analysis import V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY
    from agents.v2_final_output import _v2_integrity_errors, _validate_persisted_output
    from models import V2DeepAnalysisBackfillResult

    backfill = V2DeepAnalysisBackfillResult.model_validate_json(
        read_v2_artifact(
            str(path), result.run_id, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY
        ).payload_json
    )
    admission = backfill.final_admission_result
    assert admission is not None
    continuation = V2AdaptiveContinuationResult.model_validate_json(
        read_v2_artifact(str(path), result.run_id, V2_ADAPTIVE_COMPLETION_KEY).payload_json
    )
    _validate_persisted_output(output, admission, continuation, gap_reconciliation=None)
    fields = {name: getattr(output, name) for name in type(output).model_fields}
    fields["unresolved_material_gaps"] = ()
    errors = _v2_integrity_errors(output.synthesis, admission, continuation, fields)
    assert any("Known gaps require" in error.message for error in errors)
    starts = [
        V2PhysicalCallStart.model_validate_json(
            read_v2_artifact(
                str(path), result.run_id, f"phase-13-physical-call-{sequence:03d}-start"
            ).payload_json
        )
        for sequence in range(1, result.budget.physical_calls_used + 1)
    ]
    search_calls = [item for item in starts if item.stage == "search_agent"]
    assert len(search_calls) == 2
    for number, physical in enumerate(search_calls, 1):
        attempt = V2PlanningAttempt.model_validate_json(
            read_v2_artifact(
                str(path), result.run_id, f"adaptive-reliability-round-2-attempt-{number}"
            ).payload_json
        )
        assert attempt.attempt_id in physical.input_artifact_ids


def test_schema_failure_gets_one_repair(tmp_path: Path) -> None:
    from providers.llm import LLMRequest

    class MalformedOnce(FakeAdaptiveLLM):
        def generate(self, request: LLMRequest) -> object:
            if not self.requests:
                self.requests.append(request)
                return "not a typed model"
            return super().generate(request)

    llm = MalformedOnce(
        search_outputs=[_proposal("independent cohort outcome instrument evaluation")],
        gap_outputs=[],
    )
    invoke, _, _ = _planning_fixture(tmp_path, llm)
    assert invoke().plan.searches
    assert len(llm.requests) == 2
    assert "schema_failure" in llm.requests[1].rendered_prompt


@pytest.mark.parametrize("code", ["schema_validation_failure", "authentication_failure"])
def test_real_adapter_error_classification(tmp_path: Path, code: str) -> None:
    from providers.llm import LLMInvocationError, LLMRequest
    from providers.mimo import MimoFailureCode, MimoProviderError

    class AdapterErrorOnce(FakeAdaptiveLLM):
        def generate(self, request: LLMRequest) -> object:
            if not self.requests:
                self.requests.append(request)
                raise MimoProviderError(
                    MimoFailureCode(code), "Synthetic adapter failure", retryable=False
                )
            return super().generate(request)

    llm = AdapterErrorOnce(
        search_outputs=[_proposal("independent cohort outcome instrument evaluation")],
        gap_outputs=[],
    )
    invoke, _, _ = _planning_fixture(tmp_path, llm)
    if code == "authentication_failure":
        with pytest.raises(LLMInvocationError):
            invoke()
        assert len(llm.requests) == 1
    else:
        assert invoke().plan.searches
        assert len(llm.requests) == 2
