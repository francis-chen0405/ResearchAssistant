"""Focused planning and execution checks for graph-neighbor search lanes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from test_query_round_four_review import _gap, _initial_plan
from test_seed_expansion_runtime import (
    NOW,
    RUN,
    _action,
    _adapter,
    _binding,
    _clock,
    _identity,
    _install_gap_analysis,
    _install_round_one,
    _json_response,
    _openalex_work,
    select_seeds,
)
from test_v2_phase3_initial_planner import _routing

from agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptivePlanValidationError,
    _execute_searches,
    _round_two_gap_input,
    _validate_and_assemble_plan,
)
from agents.v2_round_four import (
    V2RoundFourAuthorizationError,
    _build_round_four_search_agent_request,
    _plan_round_four,
)
from researchassistant.contracts.discovery_v2 import V2GraphNeighborAction
from researchassistant.contracts.model_evidence import V2ProviderRunDiagnostics, V2RunDiagnostics
from researchassistant.contracts.model_research import (
    V2AcquisitionProbeOutput,
    V2AdaptiveSearchQuery,
    V2DiscoveryScoutOutput,
    V2GapSearchDirection,
    V2MaterialGap,
    V2ProviderSearchBudget,
    V2SearchAgentInput,
)
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
)
from researchassistant.contracts.query_planning import (
    V2ConceptualAdaptiveLane,
    V2NeighborhoodConceptProposal,
    V2NeighborhoodSearchAgentInput,
    V2NeighborhoodSearchOutput,
    V2QueryConceptGroup,
    V2QueryConcepts,
)
from researchassistant.research.v2_orchestrator import build_v2_run_diagnostics
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

ROUND_AT = datetime(2026, 10, 8, tzinfo=UTC)


def _request(
    *,
    round_number: int = 2,
    providers: tuple[DiscoveryProvider, ...] = (DiscoveryProvider.OPENALEX,),
    maximum_queries: int = 2,
    gap_ids: tuple[str, ...] = ("gap-outcome",),
) -> V2SearchAgentInput:
    gaps = tuple(
        V2MaterialGap(
            gap_id=gap_id,
            direction=ResearchDirection.SUPPORT,
            missing_evidence=f"Missing evidence for {gap_id}.",
            rationale="The persisted analysis identifies a material gap.",
        )
        for gap_id in gap_ids
    )
    return V2SearchAgentInput(
        run_id=RUN,
        exact_claim="The intervention improves the measured outcome.",
        round_number=round_number,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        eligible_providers=providers,
        material_gaps=gaps,
        search_directions=tuple(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=gap.direction,
                missing_evidence=gap.missing_evidence,
                search_focus=f"Evidence for {gap.gap_id}",
            )
            for gap in gaps
        ),
        discovered_terms=("outcome",),
        previous_queries=(),
        provider_budgets=tuple(
            V2ProviderSearchBudget(provider=provider, attempted_calls=0, maximum_calls=8)
            for provider in providers
        ),
        maximum_queries=maximum_queries,
    )


def _lanes(
    request: V2SearchAgentInput,
    providers: tuple[DiscoveryProvider, ...] | None = None,
) -> tuple[V2ConceptualAdaptiveLane, ...]:
    selected = providers or request.eligible_providers
    gap = request.material_gaps[0]
    return tuple(
        V2ConceptualAdaptiveLane(
            direction=gap.direction,
            provider=provider,
            strategy=f"Narrow search for {gap.gap_id}",
            target_gap_ids=(gap.gap_id,),
            mode="lexical",
        )
        for provider in selected
    )


def _text_concepts(concept: str) -> V2QueryConcepts:
    return V2QueryConcepts(required_concepts=(V2QueryConceptGroup(concept=concept),), purpose="gap")


def _copy_round_one_sources(path: Path, round_number: int) -> None:
    discovery = V2DiscoveryScoutOutput.model_validate_json(
        read_v2_artifact(str(path), RUN, "phase-4-discovery-scout").payload_json
    )
    acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(str(path), RUN, "phase-5-acquisition-probe").payload_json
    )
    items = tuple(
        item.model_copy(
            update={
                "round_number": round_number,
                "provenance_chain": tuple(
                    provenance.model_copy(update={"round_number": round_number})
                    for provenance in item.provenance_chain
                ),
            }
        )
        for item in discovery.items
    )
    provenance_by_item = {
        item_id: item.provenance_chain[0] for item in items for item_id in (item.item_id,)
    }
    clusters = tuple(
        cluster.model_copy(
            update={
                "metadata_provenance": tuple(
                    provenance_by_item[item_id] for item_id in cluster.item_ids
                )
            }
        )
        for cluster in discovery.clusters
    )
    discovery = discovery.model_copy(update={"items": items, "clusters": clusters})
    insert_v2_artifact(str(path), f"phase-7-round-{round_number}-discovery-scout", discovery, NOW)
    insert_v2_artifact(
        str(path), f"phase-7-round-{round_number}-acquisition-probe", acquisition, NOW
    )


def _graph_proposal(
    action: V2GraphNeighborAction, lane_index: int = 0
) -> V2NeighborhoodConceptProposal:
    return V2NeighborhoodConceptProposal(lane_index=lane_index, graph_action_id=action.artifact_id)


def test_text_and_graph_actions_compete_for_lane_slots_and_preserve_both_identities(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mixed-lanes.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _action(path, 2)
    request = _request(providers=(DiscoveryProvider.OPENALEX, DiscoveryProvider.ARXIV))
    lanes = _lanes(request)
    agent_input = V2NeighborhoodSearchAgentInput(
        request=request, lanes=lanes, offered_expansions=(action,)
    )
    assert len(agent_input.lanes) == request.maximum_queries

    response = V2NeighborhoodSearchOutput(
        searches=(
            _graph_proposal(action),
            V2NeighborhoodConceptProposal(lane_index=1, concepts=_text_concepts("outcome study")),
        )
    )
    plan = _validate_and_assemble_plan(
        request,
        response,
        "neighborhood-test-v1",
        ROUND_AT,
        lanes=lanes,
        query_modes={DiscoveryProvider.OPENALEX: "lexical", DiscoveryProvider.ARXIV: "lexical"},
        offered_expansions=agent_input.offered_expansions,
    )

    assert len(plan.searches) == 2
    graph_query, text_query = plan.searches
    assert graph_query.graph_action == action
    assert graph_query.query_text is None
    assert graph_query.query_id == action.artifact_id
    assert text_query.graph_action is None
    assert text_query.query_text


def test_neighborhood_plan_rejects_forged_action_ids_and_mismatched_action_lanes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reject-lanes.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _action(path)
    request = _request()
    lanes = _lanes(request)
    forged = V2NeighborhoodSearchOutput(
        searches=(V2NeighborhoodConceptProposal(lane_index=0, graph_action_id=uuid4()),)
    )
    with pytest.raises(V2AdaptivePlanValidationError, match="Unknown or mismatched graph action"):
        _validate_and_assemble_plan(
            request,
            forged,
            "neighborhood-test-v1",
            ROUND_AT,
            lanes=lanes,
            offered_expansions=(action,),
        )

    for change in (
        {"target_gap_ids": ("other-gap",)},
        {"direction": ResearchDirection.CHALLENGE},
        {"provider": DiscoveryProvider.EXA},
    ):
        mismatched = action.model_copy(update=change)
        response = V2NeighborhoodSearchOutput(searches=(_graph_proposal(mismatched),))
        with pytest.raises(
            V2AdaptivePlanValidationError, match="Unknown or mismatched graph action"
        ):
            _validate_and_assemble_plan(
                request,
                response,
                "neighborhood-test-v1",
                ROUND_AT,
                lanes=lanes,
                offered_expansions=(mismatched,),
            )


def test_round_three_keeps_three_actions_and_one_action_per_lane(tmp_path: Path) -> None:
    path = tmp_path / "round-three-cap.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    select_seeds(str(path), RUN, 1, _clock)
    _copy_round_one_sources(path, 2)
    action = _action(path, 3)
    providers = (
        DiscoveryProvider.OPENALEX,
        DiscoveryProvider.ARXIV,
        DiscoveryProvider.PUBMED,
        DiscoveryProvider.SERPSEARCH,
    )
    request = _request(round_number=3, providers=providers, maximum_queries=4)
    lanes = _lanes(request)
    response = V2NeighborhoodSearchOutput(
        searches=(
            _graph_proposal(action, 0),
            V2NeighborhoodConceptProposal(lane_index=1, concepts=_text_concepts("outcome study")),
            V2NeighborhoodConceptProposal(
                lane_index=2, concepts=_text_concepts("controlled trial")
            ),
            V2NeighborhoodConceptProposal(lane_index=3, concepts=_text_concepts("follow up")),
        )
    )

    plan = _validate_and_assemble_plan(
        request,
        response,
        "neighborhood-test-v1",
        ROUND_AT,
        lanes=lanes,
        query_modes={provider: "lexical" for provider in providers},
        offered_expansions=(action,),
    )

    assert len(plan.searches) == 3
    assert plan.searches[0].query_id == action.artifact_id
    assert [query.provider for query in plan.searches] == list(providers[:3])
    assert len({query.query_id for query in plan.searches}) == 3


def test_round_two_gap_handoff_preserves_graph_action_identity_and_round(
    tmp_path: Path,
) -> None:
    path = tmp_path / "round-two-gap-graph-action.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _action(path, 2)
    request = _request(round_number=2, gap_ids=action.target_gap_ids)
    lane = _lanes(request)[0]
    plan = _validate_and_assemble_plan(
        request,
        V2NeighborhoodSearchOutput(searches=(_graph_proposal(action),)),
        "neighborhood-test-v1",
        ROUND_AT,
        lanes=(lane,),
        query_modes={lane.provider: "lexical"},
        offered_expansions=(action,),
    )
    discovery = V2DiscoveryScoutOutput(
        run_id=RUN,
        directions=request.directions,
        items=(),
        clusters=(),
        scout_batches=(),
        scout_audits=(),
        completed_at=ROUND_AT,
    )
    acquisition = V2AcquisitionProbeOutput(
        run_id=RUN,
        directions=request.directions,
        acquisitions=(),
        attempts=(),
        probes=(),
        survivors=(),
        completed_at=ROUND_AT,
    )
    initial_plan = _initial_plan(compiled=True).model_copy(update={"run_id": RUN})
    gap = _gap(initial_plan)

    handed_off = _round_two_gap_input(
        gap,
        plan,
        discovery,
        acquisition,
        V2AdaptiveBudgetState(model_calls_remaining=2),
    )

    attempted = handed_off.attempted_queries[-1]
    assert attempted.graph_action == action
    assert attempted.query_id == action.artifact_id
    assert attempted.round_number == 2


def test_round_four_builder_requests_neighborhood_schema_and_stops_at_round_four(
    tmp_path: Path,
) -> None:
    path = tmp_path / "round-four-neighborhood.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    select_seeds(str(path), RUN, 1, _clock)
    _copy_round_one_sources(path, 3)
    for completed_round in (1, 2, 3):
        _install_gap_analysis(path, completed_round)
    initial_plan = _initial_plan(compiled=True).model_copy(update={"run_id": RUN})
    eligible = tuple(
        V2ProviderSearchBudget(provider=provider, attempted_calls=0, maximum_calls=8)
        for provider in (DiscoveryProvider.OPENALEX, DiscoveryProvider.PUBMED)
    )
    built = _build_round_four_search_agent_request(
        path=str(path),
        initial_plan=initial_plan,
        gap=_gap(initial_plan),
        eligible=eligible,
        routing_config=_routing(),
    )

    assert built is not None
    agent_input, llm_request, _reservation, lanes, _prior, legacy, modes = built
    assert not legacy
    assert isinstance(agent_input, V2NeighborhoodSearchAgentInput)
    assert llm_request.requested_output_type is V2NeighborhoodSearchOutput
    assert agent_input.request.round_number == 4
    assert agent_input.offered_expansions
    action = agent_input.offered_expansions[0]
    response = V2NeighborhoodSearchOutput(
        searches=(
            _graph_proposal(action),
            V2NeighborhoodConceptProposal(lane_index=1, concepts=_text_concepts("outcome study")),
        )
    )
    plan = _validate_and_assemble_plan(
        agent_input.request,
        response,
        "neighborhood-round-four-v1",
        ROUND_AT,
        lanes=lanes,
        query_modes=modes,
        offered_expansions=agent_input.offered_expansions,
    )
    assert plan.round_number == 4
    assert all(query.round_number == 4 for query in plan.searches)
    with pytest.raises(ValidationError):
        V2AdaptiveSearchQuery(
            run_id=RUN,
            query_id=uuid4(),
            round_number=5,
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.OPENALEX,
            targeted_gap_ids=("gap-outcome",),
            strategy="forbidden fifth round",
            query_text=None,
            graph_action=action,
            policy_identity=agent_input.request.policy_identity,
            created_at=ROUND_AT,
        )


def test_round_four_planner_requires_governor_authorization(tmp_path: Path) -> None:
    path = tmp_path / "round-four-governor.sqlite"
    _binding(path)
    initial_plan = _initial_plan(compiled=True).model_copy(update={"run_id": RUN})
    eligible = (
        V2ProviderSearchBudget(
            provider=DiscoveryProvider.PUBMED, attempted_calls=0, maximum_calls=6
        ),
    )

    with pytest.raises(V2RoundFourAuthorizationError, match="persisted Governor authorization"):
        _plan_round_four(
            path=str(path),
            initial_plan=initial_plan,
            gap=_gap(initial_plan),
            eligible=eligible,
            attempts={},
            llm_provider=None,  # type: ignore[arg-type]
            routing_config=_routing(),
            clock=lambda: ROUND_AT,
        )


def test_execute_searches_routes_graph_plan_to_adapter_with_frozen_action(
    tmp_path: Path,
) -> None:
    path = tmp_path / "execute-neighborhood.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _action(path)
    request = _request()
    lanes = _lanes(request)
    plan = _validate_and_assemble_plan(
        request,
        V2NeighborhoodSearchOutput(searches=(_graph_proposal(action),)),
        "neighborhood-runtime-v1",
        ROUND_AT,
        lanes=lanes,
        offered_expansions=(action,),
    )
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = (
            _identity(action.seed)
            if request.url.path.endswith("/W1")
            else {
                "results": [
                    _openalex_work(
                        "W2",
                        doi="10.5555/runtime-neighbor",
                        title="Runtime neighbor",
                        references=("W1",),
                    )
                ]
            }
        )
        return _json_response(request, body)

    adapter, client = _adapter(handler)
    try:
        result = _execute_searches(
            str(path),
            plan,
            {DiscoveryProvider.OPENALEX: SimpleNamespace(neighborhood_adapter=adapter)},
            None,
            lambda: NOW,
        )
    finally:
        client.close()

    assert len(requests) == 2
    assert len(result.outcomes) == 1
    assert result.outcomes[0].succeeded
    assert result.outcomes[0].query.graph_action == action
    assert result.outcomes[0].results[0].title == "Runtime neighbor"
    before = path.read_bytes(), path.stat().st_mtime_ns
    diagnostics = build_v2_run_diagnostics(str(path), RUN, (DiscoveryProvider.OPENALEX,))
    provider_result = diagnostics.provider_outcomes[0]
    assert diagnostics.search_attempts == 0
    assert diagnostics.search_results == 1
    assert diagnostics.graph_actions == 1
    assert provider_result.query_attempts == 0
    assert provider_result.non_empty_queries == 0
    assert provider_result.empty_queries == 0
    assert provider_result.timeout_queries == 0
    assert provider_result.failed_queries == 0
    assert provider_result.search_results == 1
    assert provider_result.graph_actions == 1
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_historical_diagnostics_serialization_omits_absent_graph_action_counts() -> None:
    provider = V2ProviderRunDiagnostics(provider=DiscoveryProvider.OPENALEX)
    diagnostics = V2RunDiagnostics(
        configured_providers=(DiscoveryProvider.OPENALEX,),
        provider_outcomes=(provider,),
    )

    assert "graph_actions" not in provider.model_dump(mode="json")
    assert "graph_actions" not in diagnostics.model_dump(mode="json")
