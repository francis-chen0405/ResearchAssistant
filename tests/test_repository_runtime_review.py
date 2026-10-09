"""Regression checks for repository review findings at runtime boundaries."""

from pathlib import Path
from uuid import uuid4

import pytest
import test_v2_phase12_production as phase12

from providers.model_choices import ModelChoice, StageModelSelections
from providers.v2_factory import V2ProductionFactoryConfig
from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
    _prepare_identity,
    run_v2_production_pipeline,
)
from researchassistant.runtime.cli import _print_v2_launch_summary
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact


@pytest.mark.parametrize("planner", [ModelChoice.GPT_6_LUNA_XHIGH, ModelChoice.MIMO_V26_PRO])
def test_cli_launch_displays_selected_stage_routes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, planner: ModelChoice
) -> None:
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    config = V2ProductionFactoryConfig.from_environment(
        {"LUNA_API_KEY": "test", "MIMO_API_KEY": "test", "EXA_API_KEY": "test"},
        repository_revision="test",
        discovery_providers=controls.discovery_providers,
        stage_models=StageModelSelections(planner=planner),
        research_controls=controls,
    )
    _print_v2_launch_summary(tmp_path / "run.sqlite", uuid4(), "Claim", config, controls)
    summary = capsys.readouterr().out
    for stage, route in config.routing.preflight().routing:
        assert f"{stage.value}: {route.logical_alias.value} ({route.physical_model})" in summary
    assert "MiMo-v2.5" not in summary


@pytest.mark.parametrize(
    "artifact_key", [V2_PRODUCTION_LEGACY_ARTIFACT_KEY, V2_PRODUCTION_PHASE13_ARTIFACT_KEY]
)
def test_historical_terminal_resume_rejects_a_different_claim(
    tmp_path: Path, artifact_key: str
) -> None:
    path = str(tmp_path / "historical.sqlite")
    run_id = uuid4()
    routing = phase12._routing()
    _prepare_identity(path, run_id, "Original claim", routing, lambda: phase12.NOW)
    terminal = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=path,
        raw_claim="Original claim",
        state=V2ProductionState.FAILED,
        failure_reason="Historical terminal failure",
        budget=phase12.V2BudgetSnapshot(
            physical_calls_used=0,
            token_exposure=0,
            cost_exposure_usd="0",
            physical_calls_remaining=160,
            tokens_remaining=500_000,
            cost_remaining_usd="0.20",
        ),
        completed_at=phase12.NOW,
    )
    insert_v2_artifact(path, artifact_key, terminal, phase12.NOW)
    model, search = phase12._V2Model(), phase12._Search()
    arguments = dict(
        db_path=path,
        directions=phase12.ResearchDirections(support_enabled=True, challenge_enabled=False),
        discovery_providers=(DiscoveryProvider.EXA,),
        search_providers={DiscoveryProvider.EXA: search},
        wigolo_provider=phase12._Scraper(),
        llm_provider=model,
        routing_config=routing,
        run_id=run_id,
        clock=lambda: phase12.NOW,
    )
    assert run_v2_production_pipeline("Original claim", **arguments) == terminal
    with pytest.raises(ValueError, match="cross-claim"):
        run_v2_production_pipeline("Different claim", **arguments)
    relocated = tmp_path / "imported.sqlite"
    Path(path).rename(relocated)
    arguments["db_path"] = str(relocated)
    resumed = run_v2_production_pipeline("Original claim", **arguments)
    assert resumed == terminal.model_copy(update={"db_path": str(relocated)})
    saved = read_v2_artifact(str(relocated), run_id, artifact_key)
    assert V2ProductionPipelineResult.model_validate_json(saved.payload_json) == terminal
    assert not model.requests and not search.requests


def test_current_terminal_resume_reports_relocated_database(tmp_path: Path) -> None:
    original, relocated = tmp_path / "original.sqlite", tmp_path / "imported.sqlite"
    terminal = phase12._run(original, phase12._V2Model(), phase12._Search(), phase12._Scraper())
    original.rename(relocated)
    model, search = phase12._V2Model(), phase12._Search()
    resumed = phase12._run(relocated, model, search, phase12._Scraper(), run_id=terminal.run_id)
    assert resumed == terminal.model_copy(update={"db_path": str(relocated)})
    assert not model.requests and not search.requests
