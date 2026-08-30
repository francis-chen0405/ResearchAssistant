"""Offline regression coverage for the post-Phase-13 bounded fourth-round contract."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import get_type_hints
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.v2_adaptive_search import (
    V2AdaptivePlannedRound,
    V2SearchAgentReservation,
    _validate_and_assemble_plan,
    round_artifact_key,
)
from agents.v2_round_four import (
    _build_round_four_search_agent_request,
    _claim_coverage_specification,
    _plan_round_four,
    _representative_families,
    _representative_round_rows,
)
from models import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchProposal,
    V2AdaptiveSearchQuery,
    V2ClaimCoverageAssessment,
    V2ClaimCoverageDimension,
    V2ClaimCoverageFocus,
    V2ClaimCoverageKind,
    V2ClaimCoverageState,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2GapAttemptedQuery,
    V2GapBudgetState,
    V2GapCoverageReconciliation,
    V2GapCoverageRecord,
    V2GapCoverageState,
    V2GapSearchDirection,
    V2GapSourceFamily,
    V2MaterialGap,
    V2ProviderSearchBudget,
    V2RoundFourReservation,
    V2SearchAgentInput,
    V2SourceSelectionCandidate,
    V2SourceSelectionInput,
    V2SourceSelectionProbePassage,
    V2SourceSelectionSearchProvenance,
)
from research_governor import V2RoundFourGovernorInput, evaluate_v2_round_four_authorization

NOW = datetime(2026, 8, 28, tzinfo=UTC)


def _gap() -> V2MaterialGap:
    return V2MaterialGap(
        gap_id="gap-round-four",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="A directly relevant longitudinal study is still missing.",
        rationale="Existing sources are cross-sectional.",
    )


def _identity_gap(
    *,
    gap_id: str = "stable-gap",
    direction: ResearchDirection = ResearchDirection.SUPPORT,
    dimension: V2ClaimCoverageDimension = V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
    component: str = "the intervention effect",
    rationale: str = "The direct effect remains unresolved.",
) -> V2MaterialGap:
    return V2MaterialGap(
        gap_id=gap_id,
        direction=direction,
        missing_evidence="Direct evidence remains missing.",
        rationale=rationale,
        claim_dimension=dimension,
        unsupported_claim_component=component,
    )


def _continuity_output(
    previous_gaps: tuple[V2MaterialGap, ...],
    current_gap: V2MaterialGap,
) -> V2GapAnalysisOutput:
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=True)
    gap_input = V2GapAnalysisInput(
        run_id=run_id,
        exact_claim="The intervention improves the outcome.",
        directions=directions,
        completed_round=2,
        attempted_queries=(),
        surviving_sources=(),
        probe_passages=(),
        source_families=(),
        discovered_terms=(),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=previous_gaps,
        remaining_budget=V2GapBudgetState(model_calls_remaining=5),
    )
    search_direction = V2GapSearchDirection(
        gap_id=current_gap.gap_id,
        direction=current_gap.direction,
        missing_evidence=current_gap.missing_evidence,
        search_focus="direct evidence",
        claim_dimension=current_gap.claim_dimension,
        resolving_evidence_kind=(
            "direct comparative evidence" if current_gap.claim_dimension is not None else None
        ),
    )
    result = V2GapAnalysisResult(
        run_id=run_id,
        directions=directions,
        coverage_summary="A material gap remains.",
        material_gaps=(current_gap,),
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


def test_gap_identity_persists_across_rounds_while_rationale_evolves() -> None:
    prior = _identity_gap(rationale="Initial analysis identified an unresolved effect.")
    current = prior.model_copy(
        update={
            "missing_evidence": "A larger direct comparison remains missing.",
            "rationale": "Additional evidence narrowed the unresolved effect boundary.",
        }
    )

    output = _continuity_output((prior,), current)

    assert output.result is not None
    assert output.result.material_gaps[0].gap_id == prior.gap_id


def test_genuinely_new_gap_uses_a_new_id() -> None:
    output = _continuity_output(
        (_identity_gap(),),
        _identity_gap(gap_id="new-gap", component="the population boundary"),
    )

    assert output.result is not None
    assert output.result.material_gaps[0].gap_id == "new-gap"


def test_semantically_duplicate_gap_cannot_use_a_new_id() -> None:
    prior = _identity_gap()
    current = _identity_gap(gap_id="new-gap")

    with pytest.raises(ValidationError, match="semantic Gap identity"):
        _continuity_output((prior,), current)


def test_reusing_gap_id_with_different_direction_is_rejected() -> None:
    prior = _identity_gap()
    current = _identity_gap(direction=ResearchDirection.CHALLENGE)

    with pytest.raises(ValidationError, match="conflicting semantic identity"):
        _continuity_output((prior,), current)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dimension", V2ClaimCoverageDimension.POPULATION_AND_SETTING),
        ("component", "a different unsupported effect component"),
    ],
)
def test_reusing_gap_id_with_different_claim_identity_is_rejected(
    field: str, value: object
) -> None:
    prior = _identity_gap()
    current = _identity_gap(**{field: value})

    with pytest.raises(ValidationError, match="conflicting semantic identity"):
        _continuity_output((prior,), current)


def test_legacy_gap_without_claim_identity_remains_readable() -> None:
    prior = _gap()
    current = _identity_gap(gap_id=prior.gap_id)

    output = _continuity_output((prior,), current)

    assert output.result is not None
    assert output.result.material_gaps[0].gap_id == prior.gap_id


def test_source_selection_history_rejects_semantic_gap_collision() -> None:
    history = (
        {
            "gap_id": "stable-gap",
            "direction": ResearchDirection.SUPPORT,
            "missing_evidence": "The effect remains unresolved.",
            "claim_dimension": V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            "unsupported_claim_component": "the intervention effect",
            "assessed_after_round": 2,
        },
        {
            "gap_id": "stable-gap",
            "direction": ResearchDirection.SUPPORT,
            "missing_evidence": "The effect remains unresolved.",
            "claim_dimension": V2ClaimCoverageDimension.POPULATION_AND_SETTING,
            "unsupported_claim_component": "the population boundary",
            "assessed_after_round": 3,
        },
    )
    candidate = V2SourceSelectionCandidate(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        source_family_id="family-1",
        research_round=1,
        source_url="https://example.test/source",
        discovery_providers=(DiscoveryProvider.EXA,),
        probe_passages=(
            V2SourceSelectionProbePassage(
                passage_id="passage-1",
                text="A bounded source passage.",
                score=1,
            ),
        ),
        search_provenance=(
            V2SourceSelectionSearchProvenance(
                query_id=uuid4(),
                provider=DiscoveryProvider.EXA,
                round_number=1,
                query_text="bounded source query",
                targeted_gap_ids=(),
            ),
        ),
        snapshot_word_count=1,
        deep_analysis_input_tokens=1,
    )

    with pytest.raises(ValidationError, match="conflicting semantic identity"):
        V2SourceSelectionInput(
            run_id=uuid4(),
            exact_claim="The intervention improves the outcome.",
            directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
            survivors=(candidate,),
            gap_history=history,
        )


def test_source_selection_history_rejects_duplicate_semantic_gap_under_new_id() -> None:
    history = (
        {
            "gap_id": "stable-gap",
            "direction": ResearchDirection.SUPPORT,
            "missing_evidence": "The effect remains unresolved.",
            "claim_dimension": V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            "unsupported_claim_component": "the intervention effect",
            "assessed_after_round": 2,
        },
        {
            "gap_id": "renamed-gap",
            "direction": ResearchDirection.SUPPORT,
            "missing_evidence": "The effect remains unresolved with new wording.",
            "claim_dimension": V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            "unsupported_claim_component": "the intervention effect",
            "assessed_after_round": 3,
        },
    )
    candidate = V2SourceSelectionCandidate(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        source_family_id="family-1",
        research_round=1,
        source_url="https://example.test/source",
        discovery_providers=(DiscoveryProvider.EXA,),
        probe_passages=(
            V2SourceSelectionProbePassage(
                passage_id="passage-1",
                text="A bounded source passage.",
                score=1,
            ),
        ),
        search_provenance=(
            V2SourceSelectionSearchProvenance(
                query_id=uuid4(),
                provider=DiscoveryProvider.EXA,
                round_number=1,
                query_text="bounded source query",
                targeted_gap_ids=(),
            ),
        ),
        snapshot_word_count=1,
        deep_analysis_input_tokens=1,
    )

    with pytest.raises(ValidationError, match="semantic Gap identity"):
        V2SourceSelectionInput(
            run_id=uuid4(),
            exact_claim="The intervention improves the outcome.",
            directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
            survivors=(candidate,),
            gap_history=history,
        )


def test_legacy_unknown_history_cannot_erase_known_gap_identity() -> None:
    history = (
        {
            "gap_id": "stable-gap",
            "direction": ResearchDirection.SUPPORT,
            "missing_evidence": "The effect remains unresolved.",
            "claim_dimension": V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            "unsupported_claim_component": "the intervention effect",
            "assessed_after_round": 1,
        },
        {
            "gap_id": "stable-gap",
            "direction": ResearchDirection.SUPPORT,
            "missing_evidence": "Legacy wording omitted the claim link.",
            "assessed_after_round": 2,
        },
        {
            "gap_id": "stable-gap",
            "direction": ResearchDirection.SUPPORT,
            "missing_evidence": "A different component is now claimed missing.",
            "claim_dimension": V2ClaimCoverageDimension.POPULATION_AND_SETTING,
            "unsupported_claim_component": "the population boundary",
            "assessed_after_round": 3,
        },
    )
    candidate = V2SourceSelectionCandidate(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        source_family_id="family-1",
        research_round=1,
        source_url="https://example.test/source",
        discovery_providers=(DiscoveryProvider.EXA,),
        probe_passages=(
            V2SourceSelectionProbePassage(
                passage_id="passage-1",
                text="A bounded source passage.",
                score=1,
            ),
        ),
        search_provenance=(
            V2SourceSelectionSearchProvenance(
                query_id=uuid4(),
                provider=DiscoveryProvider.EXA,
                round_number=1,
                query_text="bounded source query",
                targeted_gap_ids=(),
            ),
        ),
        snapshot_word_count=1,
        deep_analysis_input_tokens=1,
    )

    with pytest.raises(ValidationError, match="conflicting semantic identity"):
        V2SourceSelectionInput(
            run_id=uuid4(),
            exact_claim="The intervention improves the outcome.",
            directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
            survivors=(candidate,),
            gap_history=history,
        )


def test_round_four_query_requires_the_new_policy_and_uses_new_artifact_keys() -> None:
    query = V2AdaptiveSearchQuery(
        run_id=uuid4(),
        query_id=uuid4(),
        round_number=4,
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.EXA,
        targeted_gap_ids=("gap-round-four",),
        strategy="find a longitudinal study",
        query_text="longitudinal evidence on the claim",
        policy_identity=V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
        created_at=NOW,
    )

    assert query.round_number == 4
    assert round_artifact_key(4, "plan") == "post-phase-13-round-4-plan-v1"
    assert round_artifact_key(3, "plan") == "phase-7-round-3-plan"


def test_round_four_reservation_cannot_consume_the_protected_downstream_capacity() -> None:
    with pytest.raises(ValidationError, match="physical-call"):
        V2RoundFourReservation(
            protected_downstream_calls=8,
            protected_downstream_tokens=100,
            protected_downstream_cost_usd=Decimal("0.10"),
            gap_attempt_calls=2,
            search_agent_calls=1,
            scout_calls=2,
            provider_search_calls=4,
            acquisition_cluster_capacity=20,
            optional_calls=5,
            optional_tokens=100,
            optional_cost_usd=Decimal("0.10"),
            available_calls=12,
            available_tokens=200,
            available_cost_usd=Decimal("0.20"),
        )


def test_round_four_helpers_use_concrete_provider_budget_annotations() -> None:
    expected = tuple[V2ProviderSearchBudget, ...]

    assert get_type_hints(_build_round_four_search_agent_request)["eligible"] == expected
    assert get_type_hints(_plan_round_four)["eligible"] == expected


def test_round_four_planned_round_keeps_typed_reservation_and_strict_rejection() -> None:
    run_id = uuid4()
    query = V2AdaptiveSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        round_number=4,
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.EXA,
        targeted_gap_ids=("gap-round-four",),
        strategy="narrow evidence",
        query_text="longitudinal evidence on the claim",
        policy_identity=V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
        created_at=NOW,
    )
    plan = V2AdaptiveRoundPlan(
        run_id=run_id,
        round_number=4,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        enabled_providers=(DiscoveryProvider.EXA,),
        targeted_gap_ids=("gap-round-four",),
        discovered_terms=(),
        searches=(query,),
        search_agent_prompt_version="test-round-four",
        policy_identity=V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
        planned_at=NOW,
    )
    reservation = V2SearchAgentReservation(
        input_tokens=100,
        output_tokens=50,
        reserved_tokens=150,
        reserved_cost_usd=Decimal("0.01"),
    )
    planned = V2AdaptivePlannedRound(run_id=run_id, plan=plan, reservation=reservation)

    assert planned.reservation is reservation
    restored = V2AdaptivePlannedRound.model_validate_json(planned.model_dump_json())
    assert isinstance(restored.reservation, V2SearchAgentReservation)

    with pytest.raises(ValidationError, match="internally consistent"):
        V2AdaptivePlannedRound.model_validate(
            {
                "run_id": run_id,
                "plan": plan,
                "reservation": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "reserved_tokens": 149,
                    "reserved_cost_usd": "0.01",
                },
            }
        )


def test_reconciliation_requires_admitted_evidence_links_for_covered_gap() -> None:
    with pytest.raises(ValidationError, match="covered gaps require"):
        V2GapCoverageRecord(gap=_gap(), state=V2GapCoverageState.COVERED)

    reconciliation = V2GapCoverageReconciliation(
        run_id=uuid4(),
        post_round_three_gap_artifact_key="post-phase-13-gap-analysis-after-round-3-v1",
        round_four_attempted=True,
        records=(V2GapCoverageRecord(gap=_gap(), state=V2GapCoverageState.UNRESOLVED),),
        completed_at=NOW,
    )

    assert reconciliation.records[0].state is V2GapCoverageState.UNRESOLVED


def _reservation() -> V2RoundFourReservation:
    return V2RoundFourReservation(
        protected_downstream_calls=1,
        protected_downstream_tokens=0,
        protected_downstream_cost_usd=Decimal("0"),
        gap_attempt_calls=2,
        search_agent_calls=1,
        scout_calls=0,
        provider_search_calls=1,
        acquisition_cluster_capacity=5,
        optional_calls=3,
        optional_tokens=3,
        optional_cost_usd=Decimal("0"),
        available_calls=10,
        consumed_gap_attempt_calls=2,
        future_optional_calls=1,
        future_optional_tokens=1,
        future_optional_cost_usd=Decimal("0"),
        post_gap_available_calls=8,
    )


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({}, "authorized"),
        ({"gap_analysis_usable": False}, "gap_analysis_unusable"),
        ({"material_gap_remains": False}, "no_material_gaps"),
        ({"eligible_provider_exists": False}, "no_eligible_provider"),
        ({"round_three_duplicate_rate": 0.70}, "duplicate_heavy"),
        ({"productive_opportunity": False}, "unproductive"),
        ({"novel_query_opportunity": False}, "no_novel_query"),
        ({"complete_workload_reservable": False}, "insufficient_reservation"),
        ({"cancelled": True}, "cancelled"),
        ({"terminal_provider_failure": True}, "terminal_failure"),
    ],
)
def test_governor_reaches_every_round_four_decision(
    updates: dict[str, bool | float], expected: str
) -> None:
    evaluation = V2RoundFourGovernorInput(
        run_id=uuid4(),
        gap_analysis_usable=True,
        material_gap_remains=True,
        luna_recommends_continue=True,
        eligible_provider_exists=True,
        novel_query_opportunity=True,
        round_three_duplicate_rate=0.0,
        decided_at=NOW,
    ).model_copy(update=updates)
    decision = evaluate_v2_round_four_authorization(
        evaluation, reservation=_reservation() if expected == "authorized" else None
    )

    assert decision.reason_code.value == expected


def test_claim_coverage_focus_and_representative_quotas_keep_round_three_context() -> None:
    focus = _claim_coverage_specification(
        "Among adults in rural settings, the intervention causes outcome across regions.",
        ResearchDirections(support_enabled=True, challenge_enabled=True),
    ).focus
    assert tuple(item.dimension for item in focus) == (
        V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        V2ClaimCoverageDimension.LIMITATIONS_AND_BOUNDARIES,
        V2ClaimCoverageDimension.COUNTEREVIDENCE_OR_ALTERNATIVES,
        V2ClaimCoverageDimension.REPLICATION_OR_GENERALIZABILITY,
    )
    rows = {
        round_number: [
            V2GapAttemptedQuery(
                query_id=uuid4(),
                direction=ResearchDirection.SUPPORT,
                provider=DiscoveryProvider.EXA,
                strategy="coverage test",
                query_text=f"round {round_number} support",
                round_number=round_number,
            ),
            V2GapAttemptedQuery(
                query_id=uuid4(),
                direction=ResearchDirection.CHALLENGE,
                provider=DiscoveryProvider.EXA,
                strategy="coverage test",
                query_text=f"round {round_number} challenge",
                round_number=round_number,
            ),
        ]
        for round_number in (1, 2, 3)
    }

    selected = _representative_round_rows(rows, 3)

    assert len(selected) == 3
    assert {item.query_text.split()[1] for item in selected} == {"1", "2", "3"}
    assert {item.round_number for item in selected} == {1, 2, 3}


def test_post_round_three_rejects_mismatched_claim_component() -> None:
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    specification = _claim_coverage_specification("The program improves outcomes.", directions)
    gap_input = V2GapAnalysisInput(
        run_id=uuid4(),
        exact_claim="The program improves outcomes.",
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
        claim_coverage_focus=specification.focus,
        claim_coverage_specification=specification,
        remaining_budget=V2GapBudgetState(model_calls_remaining=5),
        policy_identity="researchassistant-v2-post-phase-13-gap-analysis-v1",
    )
    coverage = tuple(
        V2ClaimCoverageAssessment(
            dimension=item.dimension,
            claim_component=item.claim_component,
            coverage_state=(
                V2ClaimCoverageState.UNAVAILABLE
                if not item.searchable
                else V2ClaimCoverageState.MISSING
                if item.dimension is V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION
                else V2ClaimCoverageState.COVERED
            ),
            evidence_summary="Fixture assessment.",
            kind=item.kind,
            searchable=item.searchable,
            unavailable_reason=item.unavailable_reason,
        )
        for item in specification.focus
    )
    gap = V2MaterialGap(
        gap_id="effect-gap",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="Direct evidence remains missing.",
        rationale="The effect component has not been covered.",
        claim_dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        unsupported_claim_component="a deliberately mismatched component",
    )
    result = V2GapAnalysisResult(
        run_id=gap_input.run_id,
        directions=directions,
        coverage_summary="An effect gap remains.",
        claim_coverage_map=coverage,
        material_gaps=(gap,),
        continue_research=True,
        new_search_directions=(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=gap.direction,
                missing_evidence=gap.missing_evidence,
                search_focus="direct effect evidence",
                claim_dimension=gap.claim_dimension,
                resolving_evidence_kind="controlled comparative study",
            ),
        ),
        discovered_terms=(),
        analyzed_at=NOW,
    )

    with pytest.raises(ValidationError, match="unsupported claim component"):
        V2GapAnalysisOutput(
            run_id=gap_input.run_id,
            input=gap_input,
            state=V2GapAnalysisState.COMPLETED,
            result=result,
            attempts=(),
            stop_adaptive_continuation=False,
            completed_at=NOW,
        )


def test_planner_selected_population_and_mechanism_are_explicit_coverage_components() -> None:
    specification = _claim_coverage_specification(
        "The intervention causes improved outcomes among rural adults.",
        ResearchDirections(support_enabled=True, challenge_enabled=False),
        (
            V2ClaimCoverageFocus(
                dimension=V2ClaimCoverageDimension.POPULATION_AND_SETTING,
                claim_component="among rural adults",
                kind=V2ClaimCoverageKind.CLAIM_COMPONENT,
            ),
            V2ClaimCoverageFocus(
                dimension=V2ClaimCoverageDimension.MECHANISM_OR_PATHWAY,
                claim_component="causes improved outcomes",
                kind=V2ClaimCoverageKind.CLAIM_COMPONENT,
            ),
        ),
    )

    by_dimension = {item.dimension: item for item in specification.focus}
    assert by_dimension[V2ClaimCoverageDimension.POPULATION_AND_SETTING].claim_component == (
        "among rural adults"
    )
    assert by_dimension[V2ClaimCoverageDimension.MECHANISM_OR_PATHWAY].claim_component == (
        "causes improved outcomes"
    )
    counterevidence = by_dimension[V2ClaimCoverageDimension.COUNTEREVIDENCE_OR_ALTERNATIVES]
    assert not counterevidence.searchable
    assert counterevidence.unavailable_reason is not None


def test_source_family_retains_every_completed_round_in_its_provenance() -> None:
    family = V2GapSourceFamily(
        family_id="family-1",
        direction=ResearchDirection.SUPPORT,
        source_cluster_ids=(uuid4(), uuid4()),
        discovery_providers=(DiscoveryProvider.EXA,),
        round_number=1,
        round_numbers=(1, 3),
    )

    selected = _representative_families({family.family_id: family}, {family.family_id: 1}, 3)

    assert selected == (family,)
    assert selected[0].round_numbers == (1, 3)


def test_round_four_caps_provider_lanes_deterministically() -> None:
    gap = _gap()
    request = V2SearchAgentInput(
        run_id=uuid4(),
        exact_claim="A claim.",
        round_number=4,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        eligible_providers=(
            DiscoveryProvider.EXA,
            DiscoveryProvider.OPENALEX,
            DiscoveryProvider.SERPER,
        ),
        material_gaps=(gap,),
        search_directions=(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=gap.direction,
                missing_evidence=gap.missing_evidence,
                search_focus="narrow evidence",
            ),
        ),
        discovered_terms=(),
        previous_queries=(),
        provider_budgets=tuple(
            V2ProviderSearchBudget(provider=provider, attempted_calls=0, maximum_calls=8)
            for provider in (
                DiscoveryProvider.EXA,
                DiscoveryProvider.OPENALEX,
                DiscoveryProvider.SERPER,
            )
        ),
        maximum_queries=5,
        policy_identity=V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    )
    response = V2AdaptiveSearchModelOutput(
        searches=tuple(
            V2AdaptiveSearchProposal(
                direction=ResearchDirection.SUPPORT,
                provider=provider,
                targeted_gap_ids=(gap.gap_id,),
                strategy="narrow evidence",
                query_text=f"distinct query {index} for provider {provider.value}",
            )
            for index, provider in enumerate(
                (
                    DiscoveryProvider.EXA,
                    DiscoveryProvider.OPENALEX,
                    DiscoveryProvider.SERPER,
                    DiscoveryProvider.EXA,
                    DiscoveryProvider.OPENALEX,
                ),
                start=1,
            )
        )
    )

    plan = _validate_and_assemble_plan(request, response, "test", NOW)

    assert len(plan.searches) == 4
    assert {query.provider for query in plan.searches} == {
        DiscoveryProvider.EXA,
        DiscoveryProvider.OPENALEX,
    }
