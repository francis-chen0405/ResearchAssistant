from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from test_v2_phase3_initial_planner import _routing

from agents.v2_round_four import _build_round_four_search_agent_request
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2GapBudgetState,
    V2GapSearchDirection,
    V2InitialPlannerOutput,
    V2MaterialGap,
    V2ProviderSearchBudget,
    V2RoundOneSearchQuery,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.research.query_compiler import compile_query
from researchassistant.storage.store import init_db

NOW = datetime(2026, 10, 7, tzinfo=UTC)


def _initial_plan(*, compiled: bool) -> V2InitialPlannerOutput:
    run_id = uuid4()
    provider = DiscoveryProvider.PUBMED
    direction = ResearchDirection.SUPPORT
    identity = "round-1/support/pubmed/biomedical_studies"
    conceptual = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", identity),
        identity_key=identity,
        required_concepts=(V2ConceptGroup(concept="maternal health"),),
        purpose="broad",
        direction=direction,
        provider=provider,
        round_number=1,
    )
    action: V2CompiledQueryAction | None = compile_query(conceptual) if compiled else None
    query = V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        direction=direction,
        provider=provider,
        strategy="biomedical_studies",
        query_text=action.query_text if action else "maternal health",
        compiled_query=action,
        created_at=NOW,
    )
    return V2InitialPlannerOutput(
        run_id=run_id,
        raw_claim="Maternal health services improve outcomes.",
        directions=ResearchDirections(),
        discovery_providers=(provider,),
        searches=(query,),
        planner_prompt_version="fixture-v1",
        planned_at=NOW,
    )


def _gap(initial_plan: V2InitialPlannerOutput) -> V2GapAnalysisOutput:
    run_id = initial_plan.run_id
    directions = initial_plan.directions
    gap = V2MaterialGap(
        gap_id="gap-methods",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="A larger controlled study is needed.",
        rationale="Existing evidence is limited.",
    )
    gap_input = V2GapAnalysisInput(
        run_id=run_id,
        exact_claim=initial_plan.raw_claim,
        directions=directions,
        completed_round=3,
        attempted_queries=(),
        surviving_sources=(),
        probe_passages=(),
        source_families=(),
        discovered_terms=(),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=(),
        remaining_budget=V2GapBudgetState(model_calls_remaining=5),
    )
    search_direction = V2GapSearchDirection(
        gap_id=gap.gap_id,
        direction=gap.direction,
        missing_evidence=gap.missing_evidence,
        search_focus="controlled maternal health studies",
    )
    result = V2GapAnalysisResult(
        run_id=run_id,
        directions=directions,
        coverage_summary="A controlled-study gap remains.",
        material_gaps=(gap,),
        continue_research=True,
        new_search_directions=(search_direction,),
        discovered_terms=(),
        analyzed_at=NOW,
    )
    return V2GapAnalysisOutput(
        run_id=run_id,
        input=gap_input,
        state=V2GapAnalysisState.COMPLETED,
        result=result,
        attempts=(),
        stop_adaptive_continuation=False,
        completed_at=NOW,
    )


def _build(tmp_path: Path, *, compiled: bool, remaining_calls: int) -> tuple[object, ...] | None:
    plan = _initial_plan(compiled=compiled)
    path = tmp_path / f"round-four-{compiled}-{remaining_calls}.sqlite3"
    init_db(path)
    eligible = (
        V2ProviderSearchBudget(
            provider=DiscoveryProvider.PUBMED,
            attempted_calls=6 - remaining_calls,
            maximum_calls=6,
        ),
    )
    return _build_round_four_search_agent_request(
        path=str(path),
        initial_plan=plan,
        gap=_gap(plan),
        eligible=eligible,
        routing_config=_routing(),
    )


def test_round_four_converts_three_pubmed_physical_calls_to_one_logical_lane(
    tmp_path: Path,
) -> None:
    built = _build(tmp_path, compiled=True, remaining_calls=3)

    assert built is not None
    request_input, _request, _reservation, lanes, _prior, legacy, _modes = built
    assert not legacy
    assert len(lanes) == 1
    assert lanes[0].provider is DiscoveryProvider.PUBMED
    assert request_input.request.maximum_queries == 1  # type: ignore[union-attr]


def test_round_four_with_only_one_pubmed_physical_call_stops_before_input_creation(
    tmp_path: Path,
) -> None:
    assert _build(tmp_path, compiled=True, remaining_calls=1) is None


def test_legacy_round_four_keeps_single_physical_request_allowance(tmp_path: Path) -> None:
    built = _build(tmp_path, compiled=False, remaining_calls=1)

    assert built is not None
    request_input, _request, _reservation, lanes, _prior, legacy, _modes = built
    assert legacy
    assert lanes == ()
    assert request_input.maximum_queries == 1  # type: ignore[union-attr]
