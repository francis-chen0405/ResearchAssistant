"""Exact resume verifies cached release content and tolerates consumed stage budgets."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import test_product_discovery_pipeline as product
import test_v2_phase6_gap_analysis as gap_fixture
import test_v2_phase8_source_selection as selection_fixture
import test_v2_phase10_reviewer_ledger as reviewer
import test_v2_phase11_final_output as final_fixture

import researchassistant.agents.post_analysis_round as post_analysis_round
import researchassistant.research.v2_orchestrator as coordinator
from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
    V2FinalOutputRunResult,
    build_v2_final_research_output,
    run_v2_final_research_output,
)
from researchassistant.agents.v2_gap_analysis import run_v2_gap_analysis
from researchassistant.agents.v2_source_selection import run_v2_source_selection_and_queue
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    V2GapBudgetState,
    V2SourceSelectionModelOutput,
    V2SourceSelectionRecommendation,
    v2_payload_fingerprint,
)
from researchassistant.providers.v2_budget import read_v2_physical_call_audit
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
)
from researchassistant.storage.store import (
    insert_v2_artifact,
    list_runs,
    read_run,
    read_v2_artifact,
)


@pytest.fixture(scope="module")
def released_product(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ResearchControls]:
    path = tmp_path_factory.mktemp("resume-product") / "generated.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    result, _, _ = product._run(path, controls)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    return path, controls


def _substitute(path: Path, run_id: UUID, key: str, payload: dict[str, Any]) -> None:
    """Change only a generated artifact, preserving its original immutability trigger."""
    encoded = json.dumps(payload)
    with sqlite3.connect(path) as connection:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='v2_artifacts_immutable_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER v2_artifacts_immutable_update")
        changed = connection.execute(
            "UPDATE v2_artifacts SET payload_json=?,payload_sha256=? "
            "WHERE run_id=? AND artifact_key=?",
            (encoded, v2_payload_fingerprint(encoded), str(run_id), key),
        )
        assert changed.rowcount == 1
        connection.execute(trigger)


@pytest.mark.parametrize(
    "key",
    [
        V2_PRODUCTION_ARTIFACT_KEY,
        V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
        V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    ],
)
@pytest.mark.parametrize("change", [None, "hash", "claim"])
def test_terminal_resume_checks_original_release_before_returning_or_writing(
    tmp_path: Path,
    released_product: tuple[Path, ResearchControls],
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    change: str | None,
) -> None:
    source, controls = released_product
    path = tmp_path / "copy.sqlite3"
    shutil.copyfile(source, path)
    run_id = list_runs(path)[0].run_id
    stored = read_v2_artifact(path, run_id, V2_PRODUCTION_ARTIFACT_KEY)
    result = V2ProductionPipelineResult.model_validate_json(stored.payload_json)
    if key != V2_PRODUCTION_ARTIFACT_KEY:
        insert_v2_artifact(str(path), key, result, result.completed_at)
    if change is not None:
        values = result.model_dump(mode="json")
        if change == "hash":
            values["final_output"]["release_validation"]["rendered_output_hash"] = "f" * 64
        else:
            values["final_output"]["exact_claim"] = "A different saved claim."
        _substitute(path, run_id, key, values)
    before = path.read_bytes(), path.stat().st_mtime_ns
    # Historical terminal keys retain their existing non-product entry point.
    if key != V2_PRODUCTION_ARTIFACT_KEY:
        original = product.run_v2_production_pipeline

        def historical_entry(*args: Any, **kwargs: Any) -> V2ProductionPipelineResult:
            kwargs.pop("research_controls")
            return original(*args, **kwargs)

        monkeypatch.setattr(product, "run_v2_production_pipeline", historical_entry)
    if change is not None:
        with pytest.raises(ValueError, match="claim|hash"):
            product._run(path, controls, run_id=run_id)
    else:
        resumed, model, search = product._run(path, controls, run_id=run_id)
        assert resumed == result.model_copy(update={"db_path": str(path)})
        assert not model.requests and not search.requests
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "key",
    [
        V2_FINAL_OUTPUT_ARTIFACT_KEY,
        V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
        V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    ],
)
@pytest.mark.parametrize("valid", [True, False])
def test_cached_final_stage_verifies_hash_for_current_and_historical_keys(
    tmp_path: Path, key: str, valid: bool
) -> None:
    path, admitted = reviewer._run(tmp_path, reviewer.Phase10Provider([reviewer._approved()]))
    continuation = final_fixture._continuation(admitted.run_id)
    output = build_v2_final_research_output(
        reviewer_result=admitted,
        continuation=continuation,
        synthesis=final_fixture._synthesis(admitted),
        created_at=admitted.completed_at,
    )
    if not valid:
        output = output.model_copy(
            update={
                "release_validation": output.release_validation.model_copy(
                    update={"rendered_output_hash": "f" * 64}
                )
            }
        )
    insert_v2_artifact(path, key, output, output.created_at)
    database = Path(path)
    before = database.read_bytes(), database.stat().st_mtime_ns
    provider = final_fixture._SynthesizerProvider()

    def resume() -> V2FinalOutputRunResult:
        return run_v2_final_research_output(
            db_path=path,
            reviewer_result=admitted,
            continuation=continuation,
            llm_provider=provider,
            routing_config=final_fixture._routing(),
        )

    if valid:
        result = resume()
        assert result.resumed and result.final_output == output
    else:
        with pytest.raises(ValueError, match="hash"):
            resume()
    assert not provider.requests
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "stage",
    [
        "run_v2_gap_analysis",
        "run_v2_adaptive_search_continuation",
        "run_v2_round_four_continuation",
        "run_v2_source_selection_and_queue",
        "run_v2_deep_analysis_with_backfill",
        "run_v2_final_research_output",
    ],
)
def test_completed_stage_interruption_resumes_without_repeating_saved_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    path = tmp_path / "partial.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    stage_owner = post_analysis_round if stage == "run_v2_round_four_continuation" else coordinator
    original: Callable[..., Any] = getattr(stage_owner, stage)
    captured: dict[str, Any] = {}

    def interrupt_after_commit(**kwargs: Any) -> object:
        captured["stage"] = original(**kwargs)
        captured["model"] = kwargs["llm_provider"]._provider
        raise KeyboardInterrupt("generated interruption after completed stage")

    monkeypatch.setattr(stage_owner, stage, interrupt_after_commit)
    with pytest.raises(KeyboardInterrupt):
        product._run(path, controls)
    monkeypatch.setattr(stage_owner, stage, original)
    partial = list_runs(path)[0]
    assert partial.status.value == "running"
    previous_requests = list(captured["model"].requests)
    resumed, model, _ = product._run(path, controls, run_id=partial.run_id)
    assert resumed.state is V2ProductionState.RELEASED, resumed.failure_reason
    # Every original physical request remains consumed, and each new request is
    # owned only once. Deterministic completion needs no additional provider call.
    assert resumed.budget.physical_calls_used == len(previous_requests) + len(model.requests)
    if stage == "run_v2_final_research_output":
        assert not model.requests
        assert resumed.final_output == captured["stage"].final_output
    assert read_run(path, partial.run_id).status.value == "completed"


def test_gap_replay_preserves_saved_budget_but_rejects_changed_research(tmp_path: Path) -> None:
    request = gap_fixture._input()
    path = tmp_path / "gap.sqlite3"
    gap_fixture._prepare_db(path, request.run_id)
    provider = gap_fixture.FakeLuna([gap_fixture._stop()])
    first = run_v2_gap_analysis(
        db_path=path,
        gap_input=request,
        llm_provider=provider,
        routing_config=gap_fixture._routing(),
        clock=lambda: gap_fixture.NOW,
    )
    current = request.model_copy(
        update={
            "remaining_budget": V2GapBudgetState(
                model_calls_remaining=0, tokens_remaining=0, cost_remaining_usd=Decimal("0")
            )
        }
    )
    before = path.read_bytes(), path.stat().st_mtime_ns
    resumed = run_v2_gap_analysis(
        db_path=path,
        gap_input=current,
        llm_provider=provider,
        routing_config=gap_fixture._routing(),
        clock=lambda: gap_fixture.NOW + timedelta(days=1),
    )
    assert resumed.resumed
    assert resumed.model_dump(exclude={"invocations", "resumed"}) == first.model_dump(
        exclude={"invocations", "resumed"}
    )
    assert resumed.input.remaining_budget == request.remaining_budget
    with pytest.raises(ValueError, match="input does not match"):
        run_v2_gap_analysis(
            db_path=path,
            gap_input=current.model_copy(update={"exact_claim": "Changed claim."}),
            llm_provider=provider,
            routing_config=gap_fixture._routing(),
        )
    assert len(provider.requests) == 1
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_partial_production_resume_rejects_cached_final_hash_without_new_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "partial-final.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    original = coordinator.run_v2_final_research_output

    def interrupt(**kwargs: Any) -> object:
        original(**kwargs)
        raise KeyboardInterrupt("generated interruption before terminal commit")

    monkeypatch.setattr(coordinator, "run_v2_final_research_output", interrupt)
    with pytest.raises(KeyboardInterrupt):
        product._run(path, controls)
    monkeypatch.setattr(coordinator, "run_v2_final_research_output", original)
    run_id = list_runs(path)[0].run_id
    stored = read_v2_artifact(path, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY)
    values = json.loads(stored.payload_json)
    values["release_validation"]["rendered_output_hash"] = "f" * 64
    _substitute(path, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY, values)
    final_before = read_v2_artifact(path, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY)
    audit_before = read_v2_physical_call_audit(path, run_id)
    result, model, search = product._run(path, controls, run_id=run_id)
    assert result.state is V2ProductionState.FAILED
    assert "hash" in result.failure_reason
    assert result.final_output is None and not model.requests and not search.requests
    assert read_v2_artifact(path, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY) == final_before
    assert read_v2_physical_call_audit(path, run_id) == audit_before


def test_budget_replay_never_refunds_an_unknown_physical_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "unknown.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    original = coordinator.run_v2_source_selection_and_queue
    captured: dict[str, Any] = {}

    def interrupt(**kwargs: Any) -> object:
        original(**kwargs)
        budgeted = kwargs["llm_provider"]
        provider = budgeted._provider
        request = provider.requests[-1]
        # Exercise the real reservation owner; interruption happens after its
        # durable start, before the generated provider can return usage.
        with monkeypatch.context() as context:

            def interrupted_transport(request: object) -> object:
                raise KeyboardInterrupt("generated unknown model outcome")

            context.setattr(provider, "generate", interrupted_transport)
            try:
                budgeted.generate(request)
            finally:
                captured["budget"] = budgeted.snapshot()
        raise AssertionError("interrupted transport must propagate")

    monkeypatch.setattr(coordinator, "run_v2_source_selection_and_queue", interrupt)
    with pytest.raises(KeyboardInterrupt):
        product._run(path, controls)
    monkeypatch.setattr(coordinator, "run_v2_source_selection_and_queue", original)
    run_id = list_runs(path)[0].run_id
    before = read_v2_physical_call_audit(path, run_id)
    unknown = before.starts[-1]
    assert before.completions[-1] is None
    result, model, _ = product._run(path, controls, run_id=run_id)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    after = read_v2_physical_call_audit(path, run_id)
    assert after.starts[: len(before.starts)] == before.starts
    assert after.completions[: len(before.completions)] == before.completions
    assert result.budget.physical_calls_used == len(before.starts) + len(model.requests)
    assert result.budget.token_exposure >= unknown.reserved_tokens
    assert result.budget.cost_exposure_usd >= unknown.reserved_cost_usd
    assert result.budget.token_exposure >= captured["budget"].token_exposure


def test_selection_replay_retains_original_snapshot_without_replenishing_budget(
    tmp_path: Path,
) -> None:
    from uuid import uuid4

    source_id = uuid4()
    request = selection_fixture._selection_input(
        (
            selection_fixture._candidate(
                source_id,
                family="generated",
                probe_score=10,
            ),
        )
    )
    provider = selection_fixture.FakeSourceSelector(
        [
            V2SourceSelectionModelOutput(
                recommendations=(
                    V2SourceSelectionRecommendation.model_validate(
                        selection_fixture._recommendation(source_id, gap_ids=("gap-1",))
                    ),
                ),
            )
        ]
    )
    path = Path(selection_fixture._prepare_db(tmp_path, request.run_id))
    original_budget = selection_fixture._budget()
    first = run_v2_source_selection_and_queue(
        db_path=path,
        selection_input=request,
        llm_provider=provider,
        routing_config=selection_fixture._routing(),
        budget=original_budget,
        clock=lambda: selection_fixture.NOW,
    )
    exhausted = original_budget.model_copy(
        update={
            "physical_calls_used": original_budget.physical_call_ceiling,
            "tokens_remaining": 0,
            "cost_remaining_usd": Decimal("0"),
        }
    )
    before = path.read_bytes(), path.stat().st_mtime_ns
    resumed = run_v2_source_selection_and_queue(
        db_path=path,
        selection_input=request,
        llm_provider=provider,
        routing_config=selection_fixture._routing(),
        budget=exhausted,
    )
    assert resumed.resumed and resumed.result == first.result
    assert resumed.initial_budget == original_budget and exhausted.tokens_remaining == 0
    for changed_request, budget in (
        (request.model_copy(update={"exact_claim": "Changed claim."}), exhausted),
        (request, exhausted.model_copy(update={"physical_call_ceiling": 159})),
    ):
        with pytest.raises(ValueError, match="persisted source-selection state"):
            run_v2_source_selection_and_queue(
                db_path=path,
                selection_input=changed_request,
                llm_provider=provider,
                routing_config=selection_fixture._routing(),
                budget=budget,
            )
    assert len(provider.requests) == 1
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
