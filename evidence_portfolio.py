"""Deterministic MVP-10 source-family and portfolio policy."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from models import (
    CoverageRating,
    EvidenceRole,
    EvidenceTrailEntry,
    EvidenceTrailOutcome,
    PortfolioCoverageAssessment,
    SourceFamilyIdentity,
    SourceSnapshot,
)


def identify_source_family(snapshot: SourceSnapshot) -> SourceFamilyIdentity:
    """Choose a stable source-family key without treating domain equality as identity."""
    if snapshot.canonical_url:
        key = _normalize_url(snapshot.canonical_url)
        basis = "canonical_primary_url"
    elif snapshot.source_url:
        key = _normalize_url(snapshot.source_url)
        basis = "resolved_source_url"
    else:  # SourceSnapshot currently forbids this branch; retain an explicit safe fallback.
        key = snapshot.snapshot_sha256
        basis = "snapshot_hash"
    return SourceFamilyIdentity(
        source_family_id=uuid5(NAMESPACE_URL, f"mvp10-source-family::{key}"),
        family_key=key,
        identification_basis=basis,
    )


def coverage_rating(
    independent_source_families: int, opposing_or_limitation_families: int
) -> CoverageRating:
    """Return the documented deterministic coverage label."""
    if independent_source_families == 0:
        return CoverageRating.INSUFFICIENT
    if independent_source_families < 3:
        return CoverageRating.LIMITED
    if opposing_or_limitation_families > 0:
        return CoverageRating.STRONG
    return CoverageRating.ADEQUATE


def assess_portfolio(
    run_id: UUID,
    entries: tuple[EvidenceTrailEntry, ...],
    *,
    research_rounds: int,
    stopping_reason: str,
    important_missing_evidence: tuple[str, ...] = (),
    assessed_at: datetime | None = None,
) -> PortfolioCoverageAssessment:
    """Count approved independent families and transparent non-approval outcomes."""
    accepted = tuple(item for item in entries if item.outcome is EvidenceTrailOutcome.ACCEPTED)
    families = {
        item.source_family.source_family_id for item in accepted if item.source_family is not None
    }
    supporting = {
        item.source_family.source_family_id
        for item in accepted
        if item.source_family is not None and item.role is EvidenceRole.SUPPORTING
    }
    opposing_or_limitation = {
        item.source_family.source_family_id
        for item in accepted
        if item.source_family is not None
        and item.role in {EvidenceRole.OPPOSING, EvidenceRole.LIMITATION}
    }
    duplicate_count = sum(item.outcome is EvidenceTrailOutcome.DUPLICATE for item in entries)
    rejected_count = sum(
        item.outcome
        in {
            EvidenceTrailOutcome.ANALYST_REJECTED,
            EvidenceTrailOutcome.REVIEWER_REJECTED,
            EvidenceTrailOutcome.NOT_RELEVANT,
            EvidenceTrailOutcome.EVIDENCE_DENSITY_FAILURE,
            EvidenceTrailOutcome.PASSAGE_SELECTION_FAILED,
            EvidenceTrailOutcome.QUOTE_VALIDATION_FAILED,
        }
        for item in entries
    )
    inaccessible_count = sum(
        item.outcome in {EvidenceTrailOutcome.INACCESSIBLE, EvidenceTrailOutcome.RETRIEVAL_FAILURE}
        for item in entries
    )
    return PortfolioCoverageAssessment(
        run_id=run_id,
        approved_evidence_items=len(accepted),
        independent_source_families=len(families),
        supporting_families=len(supporting),
        opposing_or_limitation_families=len(opposing_or_limitation),
        duplicate_count=duplicate_count,
        rejected_count=rejected_count,
        inaccessible_count=inaccessible_count,
        research_rounds=research_rounds,
        rating=coverage_rating(len(families), len(opposing_or_limitation)),
        stopping_reason=stopping_reason,
        important_missing_evidence=important_missing_evidence,
        assessed_at=assessed_at or datetime.now(UTC),
    )


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))
