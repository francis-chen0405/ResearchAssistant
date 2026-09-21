from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import cli
import frontend.live_service as live_service
from cli import CLIExitCode
from frontend.live_contracts import LiveRunRequest
from model_evidence import V2ProviderRunDiagnostics, V2RunDiagnostics
from models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirections,
    Stage,
)
from orchestrator import ProviderPipelineResult, ProviderRunStatus
from providers.config import RunCeilings
from providers.mimo_factory import MimoProviderFactoryConfig
from providers.v2_budget import V2BudgetSnapshot
from providers.v2_factory import V2ProductionFactoryConfig
from v2_orchestrator import (
    V2ProductionPipelineResult,
    V2ProductionState,
)

CLAIM = "The offline selection fixture is deterministic."
IDENTITY = "source-sha256:" + "a" * 64
NOW = datetime(2026, 9, 20, tzinfo=UTC)


def _environment() -> dict[str, str]:
    return {
        "MIMO_API_KEY": "mimo-test-secret",
        "MIMO_BASE_URL": "https://mimo.example.test/v1",
        "MIMO_MODEL": "mimo-v2.5-pro",
        "MIMO_V25_MODEL": "mimo-v2.5",
        "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
        "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
        "MIMO_V25_PRO_MODEL": "mimo-v2.5-pro",
        "MIMO_V25_PRO_INPUT_USD_PER_TOKEN": "0.000001",
        "MIMO_V25_PRO_OUTPUT_USD_PER_TOKEN": "0.000002",
        "LUNA_API_KEY": "luna-test-secret",
        "LUNA_BASE_URL": "https://luna.example.test/v1",
        "LUNA_MODEL": "luna-test-model",
        "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
        "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        "EXA_API_KEY": "exa-test-secret",
        "OPENALEX_API_KEY": "openalex-test-secret",
    }


def _cli_argv(db_path: Path, run_id: UUID) -> list[str]:
    return [
        "run",
        CLAIM,
        "--db-path",
        str(db_path),
        "--run-id",
        str(run_id),
        "--max-tokens",
        "100000",
        "--max-cost-usd",
        "0.20",
    ]


def _v2_result(db_path: str, run_id: UUID, raw_claim: str) -> V2ProductionPipelineResult:
    providers = (DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX)
    diagnostics = V2RunDiagnostics(
        configured_providers=providers,
        provider_outcomes=tuple(V2ProviderRunDiagnostics(provider=item) for item in providers),
    )
    return V2ProductionPipelineResult(
        run_id=run_id,
        db_path=db_path,
        raw_claim=raw_claim,
        state=V2ProductionState.FAILED,
        current_stage=Stage.CLAIM_PLANNER,
        failure_reason="offline selection regression",
        diagnostics=diagnostics,
        budget=V2BudgetSnapshot(
            physical_calls_used=0,
            token_exposure=0,
            cost_exposure_usd=Decimal("0"),
            physical_calls_remaining=160,
            tokens_remaining=500_000,
            cost_remaining_usd=Decimal("0.20"),
        ),
        completed_at=NOW,
    )


def _legacy_result(db_path: str | Path, run_id: UUID, raw_claim: str) -> ProviderPipelineResult:
    return ProviderPipelineResult(
        run_id=run_id,
        status=ProviderRunStatus.FAILED,
        raw_claim=raw_claim,
        db_path=str(db_path),
        current_stage=Stage.CLAIM_PLANNER,
        failure_reason="offline selection regression",
    )


def _request(tmp_path: Path, run_id: UUID) -> LiveRunRequest:
    return LiveRunRequest(
        raw_claim=CLAIM,
        db_path=str(tmp_path / "live.sqlite3"),
        run_id=run_id,
        max_tokens=100_000,
        max_cost_usd=Decimal("0.20"),
        research_controls=ResearchControls(
            discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX)
        ),
    )


def test_cli_defaults_to_v2_even_when_legacy_compatibility_name_is_rebound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _environment()
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    legacy_calls: list[object] = []

    def historical_trap(*args: object, **kwargs: object) -> ProviderPipelineResult:
        legacy_calls.append((args, kwargs))
        raise AssertionError("historical runner rebinding must not select the pipeline")

    monkeypatch.setattr(cli, "run_mvp3b_pipeline", historical_trap)
    bundle_calls: list[V2ProductionFactoryConfig] = []
    pipeline_calls: list[tuple[str, dict[str, object]]] = []
    bundle = SimpleNamespace(
        search_providers={DiscoveryProvider.EXA: object(), DiscoveryProvider.OPENALEX: object()},
        wigolo=object(),
        firecrawl=None,
        crossref_resolver=None,
        llm=object(),
    )

    def build_bundle(config: V2ProductionFactoryConfig) -> SimpleNamespace:
        bundle_calls.append(config)
        return bundle

    def run_v2(raw_claim: str, **kwargs: object) -> V2ProductionPipelineResult:
        pipeline_calls.append((raw_claim, kwargs))
        return _v2_result(str(kwargs["db_path"]), UUID(str(kwargs["run_id"])), raw_claim)

    monkeypatch.setattr(cli, "build_v2_production_bundle", build_bundle)
    monkeypatch.setattr(cli, "run_v2_production_pipeline", run_v2)

    run_id = uuid4()
    result = cli.main(
        _cli_argv(tmp_path / "cli.sqlite3", run_id),
        identity_provider=lambda: IDENTITY,
    )

    assert result == CLIExitCode.FAILED
    assert legacy_calls == []
    assert len(bundle_calls) == 1
    assert bundle_calls[0].routing.repository_revision == IDENTITY
    assert len(pipeline_calls) == 1
    raw_claim, kwargs = pipeline_calls[0]
    assert raw_claim == CLAIM
    assert kwargs["run_id"] == run_id
    assert kwargs["directions"] == ResearchDirections(support_enabled=True, challenge_enabled=False)
    assert kwargs["discovery_providers"] == (DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX)
    assert kwargs["ceilings"] == bundle_calls[0].ceilings


def test_cli_explicit_legacy_runner_receives_legacy_configuration_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _environment()
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    run_id = uuid4()
    received: dict[str, object] = {}

    def legacy_runner(
        raw_claim: str,
        *,
        db_path: str | Path,
        factory_config: MimoProviderFactoryConfig,
        run_id: UUID,
        research_controls: ResearchControls,
    ) -> ProviderPipelineResult:
        received.update(
            raw_claim=raw_claim,
            db_path=db_path,
            factory_config=factory_config,
            run_id=run_id,
            research_controls=research_controls,
        )
        return _legacy_result(db_path, run_id, raw_claim)

    monkeypatch.setattr(
        cli,
        "run_v2_production_pipeline",
        lambda *args: pytest.fail("explicit legacy selection must not invoke v2"),
    )
    result = cli.main(
        _cli_argv(tmp_path / "legacy.sqlite3", run_id),
        legacy_runner=legacy_runner,
        identity_provider=lambda: IDENTITY,
    )

    assert result == CLIExitCode.FAILED
    assert received["raw_claim"] == CLAIM
    assert received["run_id"] == run_id
    assert received["db_path"] == (tmp_path / "legacy.sqlite3").resolve()
    config = received["factory_config"]
    assert isinstance(config, MimoProviderFactoryConfig)
    assert config.repository_revision == IDENTITY
    assert config.ceilings == RunCeilings(max_tokens=100_000, max_cost_usd=Decimal("0.20"))
    assert received["research_controls"] == ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX)
    )


def test_live_controller_default_configures_and_starts_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _environment()
    bundle_calls: list[V2ProductionFactoryConfig] = []
    pipeline_calls: list[dict[str, object]] = []
    bundle = SimpleNamespace(
        search_providers={DiscoveryProvider.EXA: object(), DiscoveryProvider.OPENALEX: object()},
        wigolo=object(),
        firecrawl=None,
        crossref_resolver=None,
        llm=object(),
    )

    def build_bundle(config: V2ProductionFactoryConfig) -> SimpleNamespace:
        bundle_calls.append(config)
        return bundle

    def run_v2(raw_claim: str, **kwargs: object) -> V2ProductionPipelineResult:
        pipeline_calls.append({"raw_claim": raw_claim, **kwargs})
        return _v2_result(str(kwargs["db_path"]), UUID(str(kwargs["run_id"])), raw_claim)

    monkeypatch.setattr(live_service, "build_v2_production_bundle", build_bundle)
    monkeypatch.setattr(live_service, "run_v2_production_pipeline", run_v2)
    monkeypatch.setattr(live_service, "repository_identity", lambda: IDENTITY)

    controller = live_service.LiveResearchController(environment=environment)
    try:
        request = _request(tmp_path, uuid4())
        assert (
            controller.configuration_message(
                discovery_providers=request.research_controls.discovery_providers
            )
            is None
        )
        start = controller.start(request)
        assert start.started is True
        assert len(bundle_calls) == 1
        assert len(pipeline_calls) == 1
        call = pipeline_calls[0]
        assert call["raw_claim"] == CLAIM
        assert call["run_id"] == start.run_id
        assert call["directions"] == request.directions
        assert call["discovery_providers"] == request.research_controls.discovery_providers
        assert call["ceilings"] == bundle_calls[0].ceilings
    finally:
        assert controller.shutdown(timeout=5)


@pytest.mark.parametrize("keyword", ["legacy_runner", "runner"])
def test_live_controller_legacy_runner_selection_and_alias(tmp_path: Path, keyword: str) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def legacy_runner(raw_claim: str, **kwargs: object) -> ProviderPipelineResult:
        calls.append((raw_claim, kwargs))
        return _legacy_result(kwargs["db_path"], UUID(str(kwargs["run_id"])), raw_claim)

    controller = live_service.LiveResearchController(
        environment=_environment(),
        **{keyword: legacy_runner},
    )
    try:
        request = _request(tmp_path, uuid4())
        start = controller.start(request)
        assert start.started is True
        assert calls
        assert calls[0][0] == CLAIM
        assert calls[0][1]["run_id"] == start.run_id
        assert isinstance(calls[0][1]["factory_config"], MimoProviderFactoryConfig)
        assert calls[0][1]["research_controls"] == request.research_controls
    finally:
        assert controller.shutdown(timeout=5)


def test_live_controller_rejects_legacy_runner_alias_conflict_before_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = False

    class ExecutorTrap:
        def __init__(self, *args: object, **kwargs: object) -> None:
            nonlocal created
            created = True

    monkeypatch.setattr(live_service, "ThreadPoolExecutor", ExecutorTrap)

    def runner(*args: object, **kwargs: object) -> ProviderPipelineResult:
        raise AssertionError("runner should never be invoked")

    with pytest.raises(TypeError, match="either legacy_runner or its runner alias"):
        live_service.LiveResearchController(
            environment={},
            legacy_runner=runner,
            runner=runner,
        )
    assert created is False
