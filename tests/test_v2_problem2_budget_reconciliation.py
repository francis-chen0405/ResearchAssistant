from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from models import V2DeepAnalysisSourceReconciliation
from providers.v2_budget import (
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2RunCeilings,
    _snapshot,
)

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def test_source_reconciliation_releases_only_unused_allowance() -> None:
    reconciliation = V2DeepAnalysisSourceReconciliation(
        source_id=uuid4(),
        source_cap_cost_usd=Decimal("1.00"),
        accounted_tokens=12_500,
        released_tokens=47_500,
        accounted_cost_usd=Decimal("0.25"),
        released_cost_usd=Decimal("0.75"),
    )

    assert reconciliation.released_tokens == 47_500
    assert reconciliation.accounted_tokens + reconciliation.released_tokens == 60_000


def test_missing_provider_usage_remains_conservative_reservation() -> None:
    run_id = uuid4()
    start = V2PhysicalCallStart(
        run_id=run_id,
        sequence=1,
        stage="analyst",
        model_alias="gpt-5.6-luna-high",
        reserved_tokens=12_500,
        reserved_cost_usd=Decimal("0.25"),
        source_id=uuid4(),
        started_at=NOW,
    )
    completion = V2PhysicalCallCompletion(
        run_id=run_id,
        sequence=1,
        succeeded=True,
        completed_at=NOW,
    )

    snapshot = _snapshot(
        [start],
        {1: completion},
        V2RunCeilings(max_total_tokens=500_000, max_total_cost_usd=Decimal("1.00")),
    )

    assert snapshot.token_exposure == 12_500
    assert snapshot.cost_exposure_usd == Decimal("0.25")
    assert snapshot.tokens_remaining == 487_500
