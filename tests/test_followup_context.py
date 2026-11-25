"""Frozen follow-up inputs preserve their variant, context and prompt on replay."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_v2_phase7_adaptive_search import NOW, _gap, _initial_plan
from test_v2_phase8_source_selection import _prepare_db

from researchassistant.agents.adaptive_handoffs import (
    V2AdaptivePlannedRound,
    V2AdaptiveSearchOutcome,
    V2AdaptiveSearchResults,
    V2SearchAgentReservation,
    round_artifact_key,
)
from researchassistant.agents.followup_context import (
    FOLLOWUP_GUIDANCE,
    V2FollowupPlanningInput,
    build_followup_context,
    freeze_planning_input,
    read_planning_input,
)
from researchassistant.contracts.models import (
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchQuery,
    V2ProviderSearchBudget,
    V2SearchAgentInput,
)
from researchassistant.contracts.query_planning import (
    V2ConceptualAdaptiveLane,
    V2ConceptualSearchAgentInput,
    V2NeighborhoodSearchAgentInput,
)
from researchassistant.providers.llm import LLMStage, load_prompt
from researchassistant.storage.store import insert_v2_artifact


@pytest.mark.parametrize("variant", ("legacy", "conceptual", "neighborhood"))
def test_frozen_followup_replays_same_input_variant_and_exact_bytes(
    tmp_path: Path, variant: str
) -> None:
    initial = _initial_plan(uuid4())
    path = _prepare_db(tmp_path, initial.run_id)
    gap = _gap(initial, continue_research=True)
    context = build_followup_context(path, initial, gap)
    assert context.gaps[0].causes == ("unknown",)
    assert context.gaps[0].search_state == "not_searched_yet"
    assert context.gaps[0].query_outcome_counts == {}
    request = V2SearchAgentInput(
        run_id=initial.run_id,
        exact_claim=initial.raw_claim,
        round_number=2,
        directions=initial.directions,
        eligible_providers=initial.discovery_providers,
        material_gaps=gap.result.material_gaps,
        search_directions=gap.result.new_search_directions,
        discovered_terms=(),
        previous_queries=(),
        provider_budgets=tuple(
            V2ProviderSearchBudget(provider=provider, maximum_calls=4, attempted_calls=0)
            for provider in initial.discovery_providers
        ),
        maximum_queries=2,
        followup_context=context,
    )
    lane = V2ConceptualAdaptiveLane(
        direction=gap.result.material_gaps[0].direction,
        provider=initial.discovery_providers[0],
        strategy="direct_evidence",
        target_gap_ids=(gap.result.material_gaps[0].gap_id,),
    )
    planner_input = (
        request
        if variant == "legacy"
        else V2ConceptualSearchAgentInput(request=request, lanes=(lane,))
        if variant == "conceptual"
        else V2NeighborhoodSearchAgentInput(request=request, lanes=(lane,), offered_expansions=())
    )
    frozen = freeze_planning_input(
        path, planner_input, load_prompt(LLMStage.SEARCH_AGENT), {}, (), lambda: NOW
    )
    encoded = frozen.model_dump_json()
    restored = read_planning_input(path, initial.run_id, 2)
    assert restored == frozen
    assert type(restored.input) is type(planner_input)
    assert restored.model_dump_json() == encoded
    assert FOLLOWUP_GUIDANCE in restored.prompt.text
    # Even a checksum-valid envelope must reject changed planning data.
    changed = frozen.model_dump(mode="json")
    changed["input_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="identity changed"):
        V2FollowupPlanningInput.model_validate(changed)


def test_followup_context_requires_explicit_continuation(tmp_path: Path) -> None:
    initial = _initial_plan(uuid4())
    path = _prepare_db(tmp_path, initial.run_id)
    with pytest.raises(ValueError, match="authorized material gaps"):
        build_followup_context(path, initial, _gap(initial, continue_research=False))


@pytest.mark.parametrize("succeeded", [False, True])
def test_saved_query_failure_is_not_empty_research(tmp_path: Path, succeeded: bool) -> None:
    initial = _initial_plan(uuid4())
    path = _prepare_db(tmp_path, initial.run_id)
    gap = _gap(initial, continue_research=True)
    material = gap.result.material_gaps[0]
    query = V2AdaptiveSearchQuery(
        run_id=initial.run_id,
        query_id=uuid4(),
        round_number=2,
        direction=material.direction,
        provider=initial.discovery_providers[0],
        targeted_gap_ids=(material.gap_id,),
        strategy="direct_evidence",
        query_text="independent outcome evidence",
        created_at=NOW,
    )
    plan = V2AdaptivePlannedRound(
        run_id=initial.run_id,
        plan=V2AdaptiveRoundPlan(
            run_id=initial.run_id,
            round_number=2,
            directions=initial.directions,
            enabled_providers=initial.discovery_providers,
            targeted_gap_ids=(material.gap_id,),
            discovered_terms=(),
            searches=(query,),
            search_agent_prompt_version="fixture",
            planned_at=NOW,
        ),
        reservation=V2SearchAgentReservation(
            input_tokens=1, output_tokens=1, reserved_tokens=2, reserved_cost_usd=Decimal("0")
        ),
    )
    results = V2AdaptiveSearchResults(
        run_id=initial.run_id,
        round_number=2,
        outcomes=(
            V2AdaptiveSearchOutcome(
                query=query,
                succeeded=succeeded,
                failure_code=None if succeeded else "provider_error",
                failure_message=None if succeeded else "provider unavailable",
            ),
        ),
        completed_at=NOW,
    )
    insert_v2_artifact(path, round_artifact_key(2, "plan"), plan, NOW)
    insert_v2_artifact(path, round_artifact_key(2, "search-results"), results, NOW)
    gap = gap.model_copy(update={"input": gap.input.model_copy(update={"completed_round": 2})})
    context = build_followup_context(path, initial, gap)
    observed = context.gaps[0]
    assert observed.causes == (("not_found",) if succeeded else ("unknown",))
    assert observed.query_outcome_counts == {
        "success_empty" if succeeded else "failed_or_not_dispatched": 1
    }
    assert observed.examples[0].query_id == query.query_id
    assert observed.examples[0].link == "query_target"
