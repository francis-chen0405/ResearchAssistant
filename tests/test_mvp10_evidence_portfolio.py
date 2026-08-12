"""Offline regression coverage for deterministic MVP-10 portfolio policy."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from evidence_portfolio import assess_portfolio, coverage_rating
from models import (
    CoverageRating,
    EvidenceRole,
    EvidenceTrailEntry,
    EvidenceTrailOutcome,
    ResearchRound,
    SourceFamilyIdentity,
)

RUN_ID = UUID("71000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 11, tzinfo=UTC)


def _entry(
    index: int,
    outcome: EvidenceTrailOutcome,
    role: EvidenceRole,
    family_index: int | None,
) -> EvidenceTrailEntry:
    family = (
        SourceFamilyIdentity(
            source_family_id=uuid5(NAMESPACE_URL, f"family-{family_index}"),
            family_key=f"https://example{family_index}.test/source",
            identification_basis="canonical_primary_url",
        )
        if family_index is not None
        else None
    )
    return EvidenceTrailEntry(
        trail_entry_id=uuid5(NAMESPACE_URL, f"trail-{index}"),
        run_id=RUN_ID,
        retrieval_attempt_id=uuid5(NAMESPACE_URL, f"retrieval-{index}"),
        research_round=ResearchRound.INITIAL,
        role=role,
        source_title=f"Source {index}",
        source_domain="example.test",
        original_url=f"https://example.test/{index}",
        resolved_url=f"https://example.test/{index}",
        source_family=family,
        retrieval_method="mocked acquisition",
        snapshot_status="snapshotted",
        outcome=outcome,
        explanation="Recorded for deterministic test coverage.",
        created_at=NOW,
    )


def test_three_independent_families_need_no_expansion_and_are_strong() -> None:
    assessment = assess_portfolio(
        RUN_ID,
        (
            _entry(1, EvidenceTrailOutcome.ACCEPTED, EvidenceRole.SUPPORTING, 1),
            _entry(2, EvidenceTrailOutcome.ACCEPTED, EvidenceRole.SUPPORTING, 2),
            _entry(3, EvidenceTrailOutcome.ACCEPTED, EvidenceRole.OPPOSING, 3),
        ),
        research_rounds=1,
        stopping_reason="Coverage target met in the initial round.",
        assessed_at=NOW,
    )

    assert assessment.independent_source_families == 3
    assert assessment.rating is CoverageRating.STRONG


def test_duplicate_is_auditable_but_excluded_from_independent_coverage() -> None:
    assessment = assess_portfolio(
        RUN_ID,
        (
            _entry(1, EvidenceTrailOutcome.ACCEPTED, EvidenceRole.SUPPORTING, 1),
            _entry(2, EvidenceTrailOutcome.DUPLICATE, EvidenceRole.SUPPORTING, 1),
        ),
        research_rounds=2,
        stopping_reason="The one permitted targeted round completed.",
        assessed_at=NOW,
    )

    assert assessment.approved_evidence_items == 1
    assert assessment.independent_source_families == 1
    assert assessment.duplicate_count == 1
    assert assessment.rating is CoverageRating.LIMITED


def test_zero_approved_families_is_insufficient() -> None:
    assert coverage_rating(0, 0) is CoverageRating.INSUFFICIENT
