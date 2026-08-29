from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.v2_gap_analysis import (
    V2_GAP_ANALYSIS_ARTIFACT_KEY,
    run_v2_gap_analysis,
)
from models import (
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    Stage,
    V2GapAnalysisInput,
    V2GapAnalysisModelOutput,
    V2GapBudgetState,
    V2GapProbePassage,
    V2GapSearchDirection,
    V2GapSurvivingSourceMetadata,
    V2MaterialGap,
    V2PipelineIdentity,
)
from providers.llm import LLMProviderCapabilities, LLMProviderExecutionError, ModelAlias
from providers.mimo import MimoFailureCode, MimoProviderError
from providers.v2_routing import V2RoutingConfig
from store import init_db, insert_run, insert_v2_pipeline_identity, read_v2_artifact

NOW = datetime(2026, 8, 20, tzinfo=UTC)


class FakeLuna:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self, responses: list[V2GapAnalysisModelOutput | Exception]) -> None:
        self.responses = responses
        self.requests: list[object] = []

    def generate(self, request: object) -> V2GapAnalysisModelOutput:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _routing() -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        {
            "MIMO_API_KEY": "mimo-secret",
            "MIMO_V25_MODEL": "mimo-v2.5",
            "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
            "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
            "LUNA_API_KEY": "luna-secret",
            "LUNA_BASE_URL": "https://luna.example.test/v1",
            "LUNA_MODEL": "deployment-owned-luna-model",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="v2-phase6-tests",
    )


def _input(directions: ResearchDirections | None = None) -> V2GapAnalysisInput:
    directions = directions or ResearchDirections()
    run_id = uuid4()
    direction = directions.enabled_directions[0]
    cluster_id = uuid4()
    return V2GapAnalysisInput(
        run_id=run_id,
        exact_claim="A public claim.",
        directions=directions,
        attempted_queries=(),
        surviving_sources=(
            V2GapSurvivingSourceMetadata(
                source_cluster_id=cluster_id,
                direction=direction,
                snapshot_id=uuid4(),
                snapshot_sha256="a" * 64,
                source_url="https://example.org/source",
                source_family_id=f"cluster:{cluster_id}",
            ),
        ),
        probe_passages=(
            V2GapProbePassage(
                passage_id="probe-1",
                source_cluster_id=cluster_id,
                direction=direction,
                text="Round-one Probe context, not a complete source document.",
            ),
        ),
        source_families=(),
        discovered_terms=("terminology",),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=(),
        remaining_budget=V2GapBudgetState(model_calls_remaining=2),
    )


def _continue(direction: ResearchDirection) -> V2GapAnalysisModelOutput:
    gap = V2MaterialGap(
        gap_id="gap-independent-outcome",
        direction=direction,
        missing_evidence="Independent outcome evidence for the stated population",
        rationale="The current Probe pool contains only one source family.",
    )
    return V2GapAnalysisModelOutput(
        coverage_summary="Round one has a narrow but usable source pool.",
        material_gaps=(gap,),
        continue_research=True,
        new_search_directions=(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=direction,
                missing_evidence=gap.missing_evidence,
                search_focus="Independent evaluations reporting the outcome for that population",
            ),
        ),
        discovered_terms=("evaluation",),
    )


def _stop() -> V2GapAnalysisModelOutput:
    return V2GapAnalysisModelOutput(
        coverage_summary="Round one has enough varied material for later use.",
        material_gaps=(),
        continue_research=False,
        stop_reason="Additional searches are likely to duplicate the existing source families.",
        new_search_directions=(),
        discovered_terms=("evaluation",),
    )


def _prepare_db(path: Path, run_id: object) -> None:
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim="A public claim.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), NOW)


@pytest.mark.parametrize(
    "directions",
    (
        ResearchDirections(support_enabled=True, challenge_enabled=False),
        ResearchDirections(support_enabled=False, challenge_enabled=True),
        ResearchDirections(support_enabled=True, challenge_enabled=True),
    ),
)
def test_gap_result_accepts_only_enabled_directions(directions: ResearchDirections) -> None:
    gap_input = _input(directions)
    direction = directions.enabled_directions[0]
    result = _continue(direction)
    assert result.material_gaps[0].direction is direction
    disabled = (
        ResearchDirection.CHALLENGE
        if direction is ResearchDirection.SUPPORT
        else ResearchDirection.SUPPORT
    )
    if len(directions.enabled_directions) == 2:
        return
    with pytest.raises(ValidationError, match="disabled research direction"):
        from models import V2GapAnalysisResult

        payload = result.model_dump()
        payload["material_gaps"] = (
            result.material_gaps[0].model_copy(update={"direction": disabled}),
        )
        payload["new_search_directions"] = (
            result.new_search_directions[0].model_copy(update={"direction": disabled}),
        )
        V2GapAnalysisResult(
            **payload,
            run_id=gap_input.run_id,
            directions=directions,
            analyzed_at=NOW,
        )


def test_gap_analysis_stops_after_round_one_and_routes_luna_with_reservation(
    tmp_path: Path,
) -> None:
    gap_input = _input()
    db_path = tmp_path / "gap.sqlite3"
    _prepare_db(db_path, gap_input.run_id)
    provider = FakeLuna([_stop()])

    result = run_v2_gap_analysis(
        db_path=db_path,
        gap_input=gap_input,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert result.state.value == "completed"
    assert result.result is not None and result.result.continue_research is False
    assert result.stop_adaptive_continuation is True
    assert len(provider.requests) == 1
    assert provider.requests[0].model_alias is ModelAlias.GPT_5_6_LUNA_HIGH
    assert (
        result.attempts[0].reservation.reserved_tokens > result.attempts[0].reservation.input_tokens
    )
    assert read_v2_artifact(str(db_path), gap_input.run_id, V2_GAP_ANALYSIS_ARTIFACT_KEY)


def test_gap_analysis_retries_once_degrades_and_restart_reuses_state(tmp_path: Path) -> None:
    gap_input = _input()
    db_path = tmp_path / "retry.sqlite3"
    _prepare_db(db_path, gap_input.run_id)
    provider = FakeLuna([RuntimeError("temporary"), RuntimeError("temporary")])
    first = run_v2_gap_analysis(
        db_path=db_path,
        gap_input=gap_input,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    resumed = run_v2_gap_analysis(
        db_path=db_path,
        gap_input=gap_input,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    assert first.state.value == "degraded"
    assert first.result is None and first.stop_adaptive_continuation is True
    assert len(first.attempts) == len(provider.requests) == 2
    assert resumed.resumed and len(provider.requests) == 2


def test_gap_analysis_does_not_retry_terminal_provider_authentication(
    tmp_path: Path,
) -> None:
    gap_input = _input()
    db_path = tmp_path / "auth.sqlite3"
    _prepare_db(db_path, gap_input.run_id)
    provider = FakeLuna(
        [
            MimoProviderError(
                MimoFailureCode.AUTHENTICATION,
                "Luna authentication failed",
                retryable=False,
            )
        ]
    )

    with pytest.raises(LLMProviderExecutionError, match="Luna authentication failed"):
        run_v2_gap_analysis(
            db_path=db_path,
            gap_input=gap_input,
            llm_provider=provider,
            routing_config=_routing(),
            clock=lambda: NOW,
        )

    assert len(provider.requests) == 1


def test_gap_input_limits_probe_data_and_requires_specific_typed_search_direction() -> None:
    gap_input = _input()
    with pytest.raises(ValidationError, match="at most 1200"):
        V2GapProbePassage(
            passage_id="too-long",
            source_cluster_id=gap_input.probe_passages[0].source_cluster_id,
            direction=ResearchDirection.SUPPORT,
            text="x" * 1201,
        )
    with pytest.raises(ValidationError, match="reference a material gap"):
        V2GapAnalysisModelOutput(
            coverage_summary="A coverage summary.",
            material_gaps=(_continue(ResearchDirection.SUPPORT).material_gaps[0],),
            continue_research=True,
            new_search_directions=(
                V2GapSearchDirection(
                    gap_id="unknown-gap",
                    direction=ResearchDirection.SUPPORT,
                    missing_evidence="Specific missing evidence",
                    search_focus="Specific source type and population",
                ),
            ),
            discovered_terms=(),
        )
