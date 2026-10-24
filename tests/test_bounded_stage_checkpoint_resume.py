"""Real stage boundaries, generated SQLite fixtures, no external provider calls."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_v2_phase4_discovery_scout import NOW, RecallScout, _routing, _single_scout_run
from test_v2_phase6_gap_analysis import FakeLuna, _input, _prepare_db, _stop

from researchassistant.agents import v2_discovery as scout
from researchassistant.agents import v2_gap_analysis as gap
from researchassistant.agents import v2_stage_checkpoint as journal
from researchassistant.contracts.models import StrictModel, V2GapBudgetState
from researchassistant.storage.store import read_v2_artifact


def _advancing_clock() -> Callable[[], datetime]:
    value = NOW

    def now() -> datetime:
        nonlocal value
        value += timedelta(seconds=1)
        return value

    return now


@pytest.mark.parametrize("stage", ("scout", "gap"))
@pytest.mark.parametrize("boundary", ("intent", "outcome", "aggregate"))
@pytest.mark.parametrize("persist_first", (False, True))
def test_interrupted_bounded_stage_never_repeats_known_or_unknown_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    boundary: str,
    persist_first: bool,
) -> None:
    clock = _advancing_clock()
    module = scout if stage == "scout" else gap
    if stage == "scout":
        path, plan, response = _single_scout_run(tmp_path)
        provider = RecallScout()

        def execute() -> object:
            return scout.run_v2_discovery_and_scout(
                db_path=path,
                planner_output=plan,
                responses=(response,),
                llm_provider=provider,
                routing_config=_routing(),
                clock=clock,
            )
    else:
        path = str(tmp_path / "gap.sqlite3")
        gap_input = _input()
        _prepare_db(Path(path), gap_input.run_id)
        provider = FakeLuna([_stop()])

        def execute() -> object:
            return gap.run_v2_gap_analysis(
                db_path=path,
                gap_input=gap_input,
                llm_provider=provider,
                routing_config=_routing(),
                clock=clock,
            )

    target = journal if boundary in {"intent", "outcome"} else module
    function_name = (
        "insert_v2_artifact_batch"
        if stage == "scout" and boundary == "aggregate"
        else "insert_v2_artifact"
    )
    original = getattr(target, function_name)

    def interrupt(*args: Any, **kwargs: Any) -> object:
        key = args[1]
        matches = (
            boundary == "aggregate"
            and (stage == "scout" or isinstance(args[2], gap.V2GapAnalysisOutput))
            or boundary == "intent"
            and str(key).endswith("/attempt-1")
            or boundary == "outcome"
            and str(key).endswith("/outcome")
        )
        if matches:
            if persist_first:
                original(*args, **kwargs)
            raise KeyboardInterrupt("generated stage interruption")
        return original(*args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(target, function_name, interrupt)
        with pytest.raises(KeyboardInterrupt, match="generated stage"):
            execute()
    calls = len(provider.requests)
    unknown = boundary == "intent" and persist_first or boundary == "outcome" and not persist_first
    if unknown:
        for _ in range(2):
            with pytest.raises(RuntimeError, match="unknown outcome"):
                execute()
        assert len(provider.requests) == calls
    else:
        execute()
        execute()
        assert len(provider.requests) == 1


@pytest.mark.parametrize("stage", ("scout", "gap"))
def test_failed_attempt_cap_survives_preaggregate_interruptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    if stage == "scout":
        path, plan, response = _single_scout_run(tmp_path)
        provider = RecallScout(malformed=True)

        def execute() -> object:
            return scout.run_v2_discovery_and_scout(
                db_path=path,
                planner_output=plan,
                responses=(response,),
                llm_provider=provider,
                routing_config=_routing(),
                clock=_advancing_clock(),
            )

        target, name = scout, "insert_v2_artifact_batch"
    else:
        path = str(tmp_path / "gap.sqlite3")
        gap_input = _input()
        _prepare_db(Path(path), gap_input.run_id)
        provider = FakeLuna([RuntimeError("offline retryable failure")] * 2)

        def execute() -> object:
            return gap.run_v2_gap_analysis(
                db_path=path,
                gap_input=gap_input,
                llm_provider=provider,
                routing_config=_routing(),
                clock=_advancing_clock(),
            )

        target, name = gap, "insert_v2_artifact"
    original = getattr(target, name)

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if stage == "scout" or isinstance(args[2], gap.V2GapAnalysisOutput):
            raise KeyboardInterrupt("before aggregate")
        return original(*args, **kwargs)

    for _ in range(2):
        with monkeypatch.context() as patcher:
            patcher.setattr(target, name, interrupt)
            with pytest.raises(KeyboardInterrupt):
                execute()
    execute()
    assert len(provider.requests) == 2


def test_gap_resume_keeps_original_budget_and_rejects_changed_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = str(tmp_path / "gap.sqlite3")
    original_input = _input()
    _prepare_db(Path(path), original_input.run_id)
    provider = FakeLuna([_stop()])
    original_insert = gap.insert_v2_artifact

    def interrupt(path: str, key: str, value: StrictModel, at: datetime) -> object:
        if isinstance(value, gap.V2GapAnalysisOutput):
            raise KeyboardInterrupt("before aggregate")
        return original_insert(path, key, value, at)

    with monkeypatch.context() as patcher:
        patcher.setattr(gap, "insert_v2_artifact", interrupt)
        with pytest.raises(KeyboardInterrupt):
            gap.run_v2_gap_analysis(
                db_path=path,
                gap_input=original_input,
                llm_provider=provider,
                routing_config=_routing(),
                clock=_advancing_clock(),
            )
    with pytest.raises(ValueError, match="input identity changed"):
        gap.run_v2_gap_analysis(
            db_path=path,
            gap_input=original_input.model_copy(update={"exact_claim": "Changed claim"}),
            llm_provider=provider,
            routing_config=_routing(),
            clock=_advancing_clock(),
        )
    resumed = gap.run_v2_gap_analysis(
        db_path=path,
        gap_input=original_input.model_copy(
            update={
                "remaining_budget": V2GapBudgetState(model_calls_remaining=0, tokens_remaining=0)
            }
        ),
        llm_provider=provider,
        routing_config=_routing(),
        clock=_advancing_clock(),
    )
    assert resumed.input.remaining_budget == original_input.remaining_budget
    assert resumed.state.value == "completed" and len(provider.requests) == 1
    assert read_v2_artifact(path, original_input.run_id, gap.V2_GAP_ANALYSIS_ARTIFACT_KEY)


@pytest.mark.core
@pytest.mark.slow
@pytest.mark.parametrize("stage", ("scout", "gap_analysis"))
def test_production_unknown_stage_keeps_the_original_physical_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    import test_product_discovery_pipeline as product

    from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
    from researchassistant.providers.llm import LLMRequest
    from researchassistant.providers.v2_budget import read_v2_physical_call_audit
    from researchassistant.storage.store import list_runs

    original = product.production._ConceptModel.generate
    calls: list[LLMRequest] = []

    def interrupt(self: object, request: LLMRequest) -> object:
        if request.stage.value == stage:
            calls.append(request)
            raise KeyboardInterrupt("provider outcome unknown")
        return original(self, request)

    path = tmp_path / "production.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    with monkeypatch.context() as patcher:
        patcher.setattr(product.production._ConceptModel, "generate", interrupt)
        with pytest.raises(KeyboardInterrupt, match="unknown"):
            product._run(path, controls)
    run_id = list_runs(path)[0].run_id
    before = read_v2_physical_call_audit(path, run_id)
    assert before.starts[-1].stage == stage and before.completions[-1] is None
    result, model, search = product._run(path, controls, run_id=run_id)
    assert result.state.value == "failed" and "unknown outcome" in result.failure_reason
    assert read_v2_physical_call_audit(path, run_id) == before
    assert not model.requests and not search.requests
    assert len(calls) == 1
    assert result.budget.token_exposure >= before.starts[-1].reserved_tokens
    assert result.budget.cost_exposure_usd >= before.starts[-1].reserved_cost_usd
