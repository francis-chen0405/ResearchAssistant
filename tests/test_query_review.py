"""Regression coverage for the Phase-2 production resume boundary."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import test_query_production as fixtures
import test_v2_phase3_initial_planner as planner_fixtures

from agents.v2_initial_planner import run_v2_initial_planner
from providers.llm import LLMRequest
from researchassistant.contracts.discovery_v2 import SearchMode
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import V2InitialPlannerModelOutput
from researchassistant.research.v2_orchestrator import (
    V2ProductionState,
    run_v2_production_pipeline,
)


@pytest.mark.parametrize("mode", (None, "lexical"))
def test_legacy_selector_cannot_bypass_a_completed_fresh_query_binding(
    tmp_path: Path, mode: SearchMode | None
) -> None:
    path = tmp_path / "fresh-legacy-resume.sqlite"
    run_id = uuid4()
    first = fixtures._run_fresh(
        path,
        model=fixtures._ConceptModel(completed_rounds=1),
        search=fixtures.phase12._Search(),
        scraper=fixtures.phase12._Scraper(),
        run_id=run_id,
        providers=(DiscoveryProvider.OPENALEX,),
        query_modes={DiscoveryProvider.OPENALEX: "semantic"},
    )
    assert first.state is V2ProductionState.RELEASED, first.failure_reason
    model = fixtures._ConceptModel(completed_rounds=1)
    search = fixtures.phase12._Search()
    original = path.read_bytes()
    with pytest.raises(ValueError, match="binding requires fresh query planning"):
        run_v2_production_pipeline(
            fixtures.CLAIM,
            db_path=path,
            directions=fixtures.DIRECTIONS,
            discovery_providers=(DiscoveryProvider.OPENALEX,),
            search_providers={DiscoveryProvider.OPENALEX: search},
            wigolo_provider=fixtures.phase12._Scraper(),
            llm_provider=model,
            routing_config=fixtures.phase12._routing(),
            ceilings=fixtures.CEILINGS,
            run_id=run_id,
            query_modes={DiscoveryProvider.OPENALEX: mode} if mode is not None else None,
            legacy_query_planning=True,
            clock=lambda: fixtures.phase12.NOW,
        )
    assert model.requests == []
    assert search.requests == []
    assert path.read_bytes() == original


class _ReorderedLegacyPlanner(planner_fixtures.FakeInitialPlanner):
    def generate(self, request: LLMRequest) -> V2InitialPlannerModelOutput:
        output = super().generate(request)
        return output.model_copy(update={"searches": tuple(reversed(output.searches))})


def test_explicit_legacy_planner_preserves_valid_response_order(tmp_path: Path) -> None:
    planner = _ReorderedLegacyPlanner()
    result = run_v2_initial_planner(
        "A public claim.",
        db_path=tmp_path / "legacy-response-order.sqlite",
        directions=planner_fixtures.ResearchDirections(challenge_enabled=True),
        discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.ARXIV),
        llm_provider=planner,
        routing_config=planner_fixtures._routing(),
        legacy_prompt=True,
        clock=lambda: planner_fixtures.NOW,
    )
    supplied_lanes = planner.requests[0].input_artifact.search_lanes
    expected = tuple(
        (lane.direction, lane.provider, lane.strategy) for lane in reversed(supplied_lanes)
    )
    assert (
        tuple(
            (query.direction, query.provider, query.strategy)
            for query in result.planner_output.searches
        )
        == expected
    )
    assert all(query.compiled_query is None for query in result.planner_output.searches)
