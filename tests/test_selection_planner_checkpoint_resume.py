"""Selection/startup recovery uses generated data and never external providers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from test_bounded_stage_checkpoint_resume import _advancing_clock
from test_v2_phase3_initial_planner import FakeConceptPlanner, FakeInitialPlanner
from test_v2_phase3_initial_planner import _routing as _planner_routing
from test_v2_phase8_source_selection import (
    FakeSourceSelector,
    _budget,
    _candidate,
    _prepare_db,
    _routing,
    _selection_input,
)
from test_v2_resume_integrity import _substitute

from researchassistant.agents import v2_initial_planner as planner
from researchassistant.agents import v2_source_selection as selection
from researchassistant.agents import v2_stage_checkpoint as journal
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirections,
    V2SourceSelectionModelOutput,
    V2SourceSelectionRecommendation,
)
from researchassistant.providers.llm import LLMRequest
from researchassistant.providers.v2_budget import read_v2_physical_call_audit
from researchassistant.storage.store import list_runs, read_v2_artifact


def _prefix(path: str) -> dict[str, tuple[object, ...]]:
    with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)) as connection:
        return {
            row[0]: row[1:]
            for row in connection.execute(
                "SELECT artifact_key,artifact_type,payload_json,payload_sha256,created_at "
                "FROM v2_artifacts"
            )
        }


def _selection_case(
    folder: Path,
) -> tuple[str, FakeSourceSelector, selection.V2SourceSelectionInput]:
    source_id = uuid4()
    value = _selection_input((_candidate(source_id, family="independent", probe_score=12),))
    provider = FakeSourceSelector(
        [
            V2SourceSelectionModelOutput(
                recommendations=(
                    V2SourceSelectionRecommendation(
                        source_id=source_id, rationale="Direct evidence"
                    ),
                )
            )
        ]
    )
    return _prepare_db(folder, value.run_id), provider, value


@pytest.mark.parametrize(
    ("stage", "boundary"),
    [
        (stage, boundary)
        for stage, boundaries in (
            ("selection", ("input", "intent", "outcome", "status", "aggregate")),
            ("planner", ("input", "intent", "outcome", "relational", "aggregate")),
        )
        for boundary in boundaries
    ],
)
@pytest.mark.parametrize("persist_first", (False, True))
def test_interrupted_selection_or_planner_preserves_completed_or_unknown_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    boundary: str,
    persist_first: bool,
) -> None:
    clock = _advancing_clock()
    if stage == "selection":
        path, provider, value = _selection_case(tmp_path)

        def execute() -> object:
            return selection.run_v2_source_selection_and_queue(
                db_path=path,
                selection_input=value,
                llm_provider=provider,
                routing_config=_routing(),
                budget=_budget(),
                clock=clock,
            )

        module = selection
    else:
        path = str(tmp_path / "planner.sqlite3")
        run_id = uuid4()
        provider = FakeConceptPlanner()

        def execute() -> object:
            return planner.run_v2_initial_planner(
                "A public claim.",
                db_path=path,
                directions=ResearchDirections(),
                discovery_providers=(DiscoveryProvider.EXA,),
                llm_provider=provider,
                routing_config=_planner_routing(),
                run_id=run_id,
                clock=clock,
            )

        module = planner
    target = journal if boundary in {"intent", "outcome"} else module
    name = "insert_v2_initial_planner_output" if boundary == "relational" else "insert_v2_artifact"
    original = getattr(target, name)

    def interrupt(*args: Any, **kwargs: Any) -> object:
        key = args[1]
        matches = (
            boundary == "relational"
            or boundary == "input"
            and key in {"selection-checkpoint-v1", "initial-planner-checkpoint-v1"}
            or boundary == "intent"
            and str(key).endswith("/attempt-1")
            or boundary == "outcome"
            and str(key).endswith("/outcome")
            or boundary == "status"
            and key == selection.V2_SOURCE_SELECTION_STATUS_KEY
            or boundary == "aggregate"
            and key
            in {selection.V2_SOURCE_SELECTION_COMPLETION_KEY, "phase-3-initial-round-1-plan"}
        )
        if matches:
            if persist_first:
                original(*args, **kwargs)
            raise KeyboardInterrupt("generated persistence interruption")
        return original(*args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(target, name, interrupt)
        with pytest.raises(KeyboardInterrupt, match="generated persistence"):
            execute()
    before = _prefix(path)
    calls = len(provider.requests)
    unknown = boundary == "intent" and persist_first or boundary == "outcome" and not persist_first
    if unknown:
        for _ in range(2):
            with pytest.raises(RuntimeError, match="unknown outcome"):
                execute()
        assert len(provider.requests) == calls
    else:
        first = execute()
        second = execute()
        assert len(provider.requests) == 1
        if stage == "planner":
            assert first.planner_output == second.planner_output
            assert (
                first.planner_output.planned_at
                == read_v2_artifact(
                    path, first.planner_output.run_id, "phase-3-initial-round-1-plan"
                ).created_at
            )
        else:
            assert first.result == second.result
    after = _prefix(path)
    assert all(after[key] == row for key, row in before.items())


def test_selection_uses_original_budget_once_after_multiple_preaggregate_cuts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, provider, value = _selection_case(tmp_path)
    clock = _advancing_clock()
    original = selection.insert_v2_artifact

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if args[1] == selection.V2_SOURCE_SELECTION_STATUS_KEY:
            raise KeyboardInterrupt("before status")
        return original(*args, **kwargs)

    def execute(budget: selection.V2DeepAnalysisBudget) -> selection.V2SourceSelectionRunResult:
        return selection.run_v2_source_selection_and_queue(
            db_path=path,
            selection_input=value,
            llm_provider=provider,
            routing_config=_routing(),
            budget=budget,
            clock=clock,
        )

    for _ in range(2):
        with monkeypatch.context() as scoped:
            scoped.setattr(selection, "insert_v2_artifact", interrupt)
            with pytest.raises(KeyboardInterrupt):
                execute(_budget())
    result = execute(_budget(physical_calls_used=159, tokens_remaining=0, cost_remaining_usd="0"))
    assert result.initial_budget == _budget()
    assert result.selection_attempts == 1 and result.queued_source_ids
    assert len(provider.requests) == 1
    assert result.result == execute(_budget()).result


@pytest.mark.parametrize("omitted", (False, True))
def test_fresh_shortlist_and_original_estimate_survive_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, omitted: bool
) -> None:
    from test_preview_selection_bounds import BoundedSourceSelector, _large_selection_input

    value = _large_selection_input()
    path = _prepare_db(tmp_path, value.run_id)
    provider = BoundedSourceSelector(estimator_overhead=100_000 if omitted else 0)
    original = selection.insert_v2_artifact

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if args[1] == selection.V2_SOURCE_SELECTION_STATUS_KEY:
            raise KeyboardInterrupt("before status")
        return original(*args, **kwargs)

    def execute() -> selection.V2SourceSelectionRunResult:
        return selection.run_v2_source_selection_and_queue(
            db_path=path,
            selection_input=value,
            llm_provider=provider,
            routing_config=_routing(),
            budget=_budget(),
            clock=_advancing_clock(),
        )

    with monkeypatch.context() as cut:
        cut.setattr(selection, "insert_v2_artifact", interrupt)
        with pytest.raises(KeyboardInterrupt):
            execute()
    checkpoint = journal.read_checkpoint(
        path, value.run_id, "selection-checkpoint-v1", journal.V2SelectionInputCheckpoint
    )
    before = _prefix(path)
    estimates = tuple(provider.estimates)
    assert (checkpoint.input is None) is omitted
    if not omitted:
        assert 0 < len(checkpoint.input.survivors) < len(value.survivors)

    def must_not_recompute(*args: Any, **kwargs: Any) -> object:
        pytest.fail("completed replay recomputed its shortlist/input estimate")

    monkeypatch.setattr(selection, "_bounded_selection_request", must_not_recompute)
    monkeypatch.setattr(provider, "conservative_input_tokens", must_not_recompute)
    result = execute()
    assert len(provider.requests) == (0 if omitted else 1)
    assert tuple(provider.estimates) == estimates
    assert result.used_fallback is omitted
    assert all(_prefix(path)[key] == row for key, row in before.items())


@pytest.mark.parametrize("stage", ("selection", "planner"))
@pytest.mark.parametrize("corruption", ("missing_invocation", "foreign_request", "wrong_type"))
def test_saved_stage_candidate_requires_exact_invocation_and_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, corruption: str
) -> None:
    if stage == "selection":
        path, provider, value = _selection_case(tmp_path)
        run_id = value.run_id
        module = selection
        key = "selection-checkpoint-v1/attempt-1/outcome"

        def execute() -> object:
            return selection.run_v2_source_selection_and_queue(
                db_path=path,
                selection_input=value,
                llm_provider=provider,
                routing_config=_routing(),
                budget=_budget(),
                clock=_advancing_clock(),
            )

    else:
        path = str(tmp_path / "planner.sqlite3")
        provider = FakeConceptPlanner()
        run_id = uuid4()
        module = planner
        key = "initial-planner-checkpoint-v1/attempt-1/outcome"

        def execute() -> object:
            return planner.run_v2_initial_planner(
                "A public claim.",
                db_path=path,
                directions=ResearchDirections(),
                discovery_providers=(DiscoveryProvider.EXA,),
                llm_provider=provider,
                routing_config=_planner_routing(),
                run_id=run_id,
                clock=_advancing_clock(),
            )

    name = "insert_v2_artifact" if stage == "selection" else "insert_v2_initial_planner_output"
    original = getattr(module, name)

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if stage == "planner" or args[1] == selection.V2_SOURCE_SELECTION_STATUS_KEY:
            raise KeyboardInterrupt("before aggregate")
        return original(*args, **kwargs)

    with monkeypatch.context() as cut:
        cut.setattr(module, name, interrupt)
        with pytest.raises(KeyboardInterrupt):
            execute()
    payload = json.loads(read_v2_artifact(path, run_id, key).payload_json)
    if corruption == "missing_invocation":
        payload["invocation"] = None
        message = "requires its completed invocation"
    elif corruption == "foreign_request":
        payload["invocation"]["input_artifact_ids"] = [str(uuid4())]
        message = "differs from its exact request"
    else:
        payload["candidate"] = {"recommendations": []} if stage == "planner" else {"queries": []}
        message = "validation error|wrong output type"
    _substitute(Path(path), run_id, key, payload)
    before = _prefix(path)
    with pytest.raises(ValueError, match=message):
        execute()
    assert len(provider.requests) == 1 and _prefix(path) == before


@pytest.mark.parametrize(
    ("missing", "legacy"), (("generic", True), ("relational", True), ("relational", False))
)
def test_initial_planner_recovers_valid_legacy_projection_without_new_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str, legacy: bool
) -> None:
    path = tmp_path / "legacy.sqlite3"
    provider = FakeInitialPlanner() if legacy else FakeConceptPlanner()
    run_id = uuid4()

    def execute() -> planner.V2InitialPlannerRunResult:
        return planner.run_v2_initial_planner(
            "A public claim.",
            db_path=path,
            directions=ResearchDirections(),
            discovery_providers=(DiscoveryProvider.EXA,),
            llm_provider=provider,
            routing_config=_planner_routing(),
            run_id=run_id,
            legacy_prompt=legacy,
            clock=_advancing_clock(),
        )

    # The original relational-only historical contract predates coverage/compiled fields.
    with monkeypatch.context() as historical:
        if legacy:
            historical.setattr(planner, "claim_component_focus", lambda *args, **kwargs: ())
        original = execute()
    with closing(sqlite3.connect(path)) as connection, connection:
        tables = (
            ("v2_artifacts",)
            if missing == "generic"
            else ("v2_round_one_search_queries", "v2_initial_planner_outputs")
        )
        for table in dict.fromkeys(("v2_artifacts", *tables)):
            trigger_name = f"{table}_immutable_delete"
            trigger = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name=?", (trigger_name,)
            ).fetchone()[0]
            connection.execute(f"DROP TRIGGER {trigger_name}")
            if table == "v2_artifacts":
                connection.execute(
                    "DELETE FROM v2_artifacts WHERE artifact_key LIKE ?",
                    ("initial-planner-checkpoint-v1%",),
                )
                if missing == "generic":
                    connection.execute(
                        "DELETE FROM v2_artifacts WHERE artifact_key='phase-3-initial-round-1-plan'"
                    )
            else:
                connection.execute(f"DELETE FROM {table} WHERE run_id=?", (str(run_id),))
            connection.execute(trigger)
    before = _prefix(str(path))
    resumed = execute()
    assert resumed.resumed and resumed.planner_output == original.planner_output
    assert len(provider.requests) == 1
    assert all(_prefix(str(path))[key] == row for key, row in before.items())


def test_failed_initial_planner_attempt_remains_consumed(tmp_path: Path) -> None:
    class FailingPlanner(FakeConceptPlanner):
        def generate(self, request: LLMRequest) -> object:
            self.requests.append(request)
            raise RuntimeError("known provider failure")

    provider = FailingPlanner()
    path = tmp_path / "failed.sqlite3"
    run_id = uuid4()
    for _ in range(3):
        with pytest.raises(RuntimeError, match="known provider failure"):
            planner.run_v2_initial_planner(
                "A public claim.",
                db_path=path,
                directions=ResearchDirections(),
                discovery_providers=(DiscoveryProvider.EXA,),
                llm_provider=provider,
                routing_config=_planner_routing(),
                run_id=run_id,
                clock=_advancing_clock(),
            )
    assert len(provider.requests) == 1


def test_selection_failed_attempt_cap_and_failure_records_survive_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, provider, value = _selection_case(tmp_path)
    provider.outputs = [RuntimeError("known failure")] * 2
    original = selection.insert_v2_artifact

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if args[1] == selection.V2_SOURCE_SELECTION_STATUS_KEY:
            raise KeyboardInterrupt("before status")
        return original(*args, **kwargs)

    def execute() -> selection.V2SourceSelectionRunResult:
        return selection.run_v2_source_selection_and_queue(
            db_path=path,
            selection_input=value,
            llm_provider=provider,
            routing_config=_routing(),
            budget=_budget(),
            clock=_advancing_clock(),
        )

    for _ in range(2):
        with monkeypatch.context() as scoped:
            scoped.setattr(selection, "insert_v2_artifact", interrupt)
            with pytest.raises(KeyboardInterrupt):
                execute()
    result = execute()
    assert result.used_fallback and result.selection_attempts == 2
    assert all(
        not attempt.succeeded and attempt.failure for attempt in result.selection_attempt_records
    )
    assert len(provider.requests) == 2


@pytest.mark.slow
@pytest.mark.parametrize("stage", ("source_selection", "planner"))
@pytest.mark.parametrize("unknown", (False, True))
def test_actual_production_preserves_calls_audit_and_unknown_reservations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, unknown: bool
) -> None:
    import test_product_discovery_pipeline as product

    original = product.production._ConceptModel.generate
    calls: list[LLMRequest] = []

    def observe(self: object, request: LLMRequest) -> object:
        if request.stage.value == stage:
            calls.append(request)
            if unknown:
                raise KeyboardInterrupt("unknown provider outcome")
        return original(self, request)

    module = selection if stage == "source_selection" else planner
    name = (
        "insert_v2_artifact" if stage == "source_selection" else "insert_v2_initial_planner_output"
    )
    insert = getattr(module, name)

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if stage == "planner" or args[1] == selection.V2_SOURCE_SELECTION_STATUS_KEY:
            raise KeyboardInterrupt("before aggregate")
        return insert(*args, **kwargs)

    path = tmp_path / "production.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    run_id: UUID | None = None
    with monkeypatch.context() as scoped:
        scoped.setattr(product.production._ConceptModel, "generate", observe)
        for _ in range(1 if unknown else 2):
            with monkeypatch.context() as cut:
                if not unknown:
                    cut.setattr(module, name, interrupt)
                with pytest.raises(KeyboardInterrupt):
                    product._run(path, controls, run_id=run_id)
            run_id = list_runs(path)[0].run_id
        before = read_v2_physical_call_audit(path, run_id)
        result, model, search = product._run(path, controls, run_id=run_id)
    after = read_v2_physical_call_audit(path, run_id)
    assert len(calls) == 1
    assert after.starts[: len(before.starts)] == before.starts
    assert after.completions[: len(before.completions)] == before.completions
    if unknown:
        assert result.state.value == "failed" and "unknown outcome" in result.failure_reason
        assert after == before and not model.requests and not search.requests
        assert before.completions[-1] is None
        assert result.budget.token_exposure >= before.starts[-1].reserved_tokens
        assert result.budget.cost_exposure_usd >= before.starts[-1].reserved_cost_usd
    else:
        assert result.state.value == "released", result.failure_reason
        assert all(item is not None for item in before.completions)


def test_selection_checkpoint_rejects_changed_claim_without_another_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, provider, value = _selection_case(tmp_path)
    original = selection.insert_v2_artifact

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if args[1] == selection.V2_SOURCE_SELECTION_STATUS_KEY:
            raise KeyboardInterrupt("before status")
        return original(*args, **kwargs)

    arguments = dict(
        db_path=path,
        selection_input=value,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=_advancing_clock(),
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(selection, "insert_v2_artifact", interrupt)
        with pytest.raises(KeyboardInterrupt):
            selection.run_v2_source_selection_and_queue(**arguments)
    with pytest.raises(ValueError, match="survivor pool"):
        selection.run_v2_source_selection_and_queue(
            **{**arguments, "selection_input": value.model_copy(update={"exact_claim": "Changed"})}
        )
    assert len(provider.requests) == 1
