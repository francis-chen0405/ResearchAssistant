"""Offline regression coverage for the post-Phase-13 bounded fourth-round contract."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.v2_adaptive_search import round_artifact_key
from models import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    DiscoveryProvider,
    ResearchDirection,
    V2AdaptiveSearchQuery,
    V2GapCoverageReconciliation,
    V2GapCoverageRecord,
    V2GapCoverageState,
    V2MaterialGap,
    V2RoundFourReservation,
)

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
