"""Offline regression coverage for the post-Phase-13 bounded fourth-round contract."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.v2_adaptive_search import _validate_and_assemble_plan, round_artifact_key
from agents.v2_round_four import _claim_coverage_focus, _representative_round_rows
from models import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchProposal,
    V2AdaptiveSearchQuery,
    V2ClaimCoverageDimension,
    V2GapAttemptedQuery,
    V2GapCoverageReconciliation,
    V2GapCoverageRecord,
    V2GapCoverageState,
    V2GapSearchDirection,
    V2MaterialGap,
    V2ProviderSearchBudget,
    V2RoundFourReservation,
    V2SearchAgentInput,
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
        ({"round_four_productive": False}, "unproductive"),
        ({"materially_new_queries": False}, "no_novel_query"),
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
        materially_new_queries=True,
        round_three_duplicate_rate=0.0,
        decided_at=NOW,
    ).model_copy(update=updates)
    decision = evaluate_v2_round_four_authorization(
        evaluation, reservation=_reservation() if expected == "authorized" else None
    )

    assert decision.reason_code.value == expected


def test_claim_coverage_focus_and_representative_quotas_keep_round_three_context() -> None:
    focus = _claim_coverage_focus(
        "Among adults in rural settings, the intervention causes outcome across regions.",
        ResearchDirections(support_enabled=True, challenge_enabled=True),
    )
    assert tuple(item.dimension for item in focus) == (
        V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        V2ClaimCoverageDimension.POPULATION_AND_SETTING,
        V2ClaimCoverageDimension.MECHANISM_OR_PATHWAY,
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
            ),
            V2GapAttemptedQuery(
                query_id=uuid4(),
                direction=ResearchDirection.CHALLENGE,
                provider=DiscoveryProvider.EXA,
                strategy="coverage test",
                query_text=f"round {round_number} challenge",
            ),
        ]
        for round_number in (1, 2, 3)
    }

    selected = _representative_round_rows(rows, 3)

    assert len(selected) == 3
    assert {item.query_text.split()[1] for item in selected} == {"1", "2", "3"}


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
