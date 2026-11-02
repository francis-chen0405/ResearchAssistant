"""Explicit, provenance-bound editorial review for study-level report openings.

This optional artifact records an accountable review, never guesses study identity
from a title or computes a conclusion from counts. Saved admissions stay immutable.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field

from researchassistant.contracts.models import SourceSnapshot, StrictModel
from researchassistant.evidence.evidence_core import validate_snapshot_integrity

if TYPE_CHECKING:
    from researchassistant.api.inspection_contracts import V2EvidenceDisplay

REPORT_REVIEW_KEY = "report-study-review-v1"


class PublicationReview(StrictModel):
    source_ids: tuple[UUID, ...] = Field(min_length=1)
    identifier: str = Field(min_length=3)
    authority: SourceSnapshot
    title: str = Field(min_length=1)
    authors: tuple[str, ...] = ()
    date: str | None = None
    venue: str | None = None


class OpeningAssertion(StrictModel):
    ledger_claim_id: UUID
    study_identifier: str = Field(min_length=3)
    role: str = Field(pattern="^(main|contrast|limitation)$")
    text: str = Field(min_length=1, max_length=900)
    design: str = Field(min_length=1)
    intervention: str = Field(min_length=1)
    outcome: str = Field(min_length=1)


class V2ReportStudyReview(StrictModel):
    run_id: UUID
    reviewer: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    reviewed_at: datetime
    publications: tuple[PublicationReview, ...] = ()
    assertions: tuple[OpeningAssertion, ...] = Field(default=(), max_length=3)


def _contains_identifier(text: str, identifier: str) -> bool:
    return re.search(r"(?<![\w/-])" + re.escape(identifier) + r"(?![\w/-])", text) is not None


def apply_review(display: V2EvidenceDisplay, review: V2ReportStudyReview) -> V2EvidenceDisplay:
    """Fail closed on conflicting identities, altered assertions or missing context."""
    from researchassistant.api.inspection_contracts import V2VerifiedPublication

    if display.run_id != review.run_id or review.reviewed_at.utcoffset() is None:
        raise ValueError("review ownership or timestamp is invalid")
    by_claim = {item.ledger_claim_id: item for item in display.items}
    by_source = {item.source_id: item for item in display.items}
    publications = {}
    identity_urls = {}
    identity_metadata = {}
    for publication in review.publications:
        validate_snapshot_integrity(publication.authority)
        url = urlsplit(publication.authority.source_url)
        if (
            publication.authority.run_id != review.run_id
            or url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            raise ValueError("authoritative capture ownership or URL is invalid")
        text = publication.authority.normalized_text
        for value in (
            publication.identifier,
            publication.title,
            *publication.authors,
            *tuple(value for value in (publication.date, publication.venue) if value),
        ):
            if value not in text or (
                value == publication.identifier and not _contains_identifier(text, value)
            ):
                raise ValueError("publication metadata is absent from authoritative capture")
        prior_url = identity_urls.setdefault(
            publication.identifier, publication.authority.source_url
        )
        if prior_url != publication.authority.source_url:
            raise ValueError("conflicting canonical locations for publication identity")
        signature = (publication.title, publication.authors, publication.date, publication.venue)
        if identity_metadata.setdefault(publication.identifier, signature) != signature:
            raise ValueError("conflicting metadata for publication identity")
        for source_id in publication.source_ids:
            item = by_source.get(source_id)
            if item is None or not _contains_identifier(item.quote_passage, publication.identifier):
                raise ValueError("publication identifier is absent from admitted reading passage")
            existing = item.verified_publication
            if existing and (
                existing.canonical_url != publication.authority.source_url
                or (existing.title and existing.title != publication.title)
            ):
                raise ValueError("conflicting existing verified publication identity")
            if source_id in publications:
                raise ValueError("conflicting publication verification records")
            publications[source_id] = V2VerifiedPublication(
                canonical_url=publication.authority.source_url,
                title=publication.title,
                authors=publication.authors,
                publication_date=publication.date,
                venue=publication.venue,
                verification="authority_identifier",
            )
    roles = {assertion.role for assertion in review.assertions}
    if review.assertions and (
        "main" not in roles or "limitation" not in roles or len(roles) != len(review.assertions)
    ):
        raise ValueError("opening needs unique main and limitation roles")
    for assertion in review.assertions:
        item = by_claim.get(assertion.ledger_claim_id)
        if item is None or not _contains_identifier(item.quote_passage, assertion.study_identifier):
            raise ValueError("study identity is not anchored in admitted text")
        verified_identifier = any(
            item.source_id in publication.source_ids
            and publication.identifier == assertion.study_identifier
            for publication in review.publications
        ) or bool(
            item.verified_publication
            and item.verified_publication.doi == assertion.study_identifier
        )
        if not verified_identifier:
            raise ValueError("study identity lacks verified publication provenance")
        if any(
            value not in item.approved_factual_statement
            for value in (assertion.design, assertion.intervention, assertion.outcome)
        ):
            raise ValueError("study context is not retained in the admitted statement")
        allowed = (item.approved_factual_statement, *item.limitations)
        if assertion.text not in allowed:
            raise ValueError("opening assertion is not exact admitted or assessed text")
        if assertion.role == "contrast" and item.relationship_to_claim.value not in {
            "supports",
            "challenges",
        }:
            raise ValueError("contrasting assertion must cite supporting or challenging evidence")
        if assertion.role == "limitation" and assertion.text not in item.limitations:
            raise ValueError("principal limitation must be recorded in the assessment")
        if not assertion.text.endswith((".", "!", "?")):
            raise ValueError("opening assertion is incomplete")
    items = tuple(
        item.model_copy(update={"verified_publication": publications[item.source_id]})
        if item.source_id in publications
        else item
        for item in display.items
    )
    return display.model_copy(
        update={
            "items": items,
            "study_opening": review.assertions,
            "reading_aid_markdown": None,
            "publication_opening": (),
            "study_review_rationale": review.rationale,
        }
    )


def record_review(
    db_path: str | Path, display: V2EvidenceDisplay, review: V2ReportStudyReview
) -> V2EvidenceDisplay:
    """Validate before immutably recording a reviewed opening through normal storage."""
    from researchassistant.api.application_services.result_reads import read_evidence
    from researchassistant.storage.store import insert_v2_artifact, read_snapshot

    for publication in review.publications:
        if read_snapshot(db_path, publication.authority.snapshot_id) != publication.authority:
            raise ValueError("authoritative capture differs from persisted acquisition")
    actual = read_evidence(db_path, review.run_id)
    if display.items != actual.items:
        raise ValueError("review input differs from persisted admitted evidence")
    result = apply_review(actual, review)
    insert_v2_artifact(db_path, REPORT_REVIEW_KEY, review, review.reviewed_at)
    return result


def build_publication_opening(display: V2EvidenceDisplay) -> V2EvidenceDisplay:
    """Extract a short complete overview only when every relevant publication fits.

    This is deliberately exhaustive, not a ranking heuristic. DOI identity groups
    publications; it never proves that different publications are independent
    experiments. Longer/mixed/uncertain bodies of evidence need editorial review.
    No sentence or qualification is truncated to make it fit.
    """
    from researchassistant.api.inspection_contracts import PublicationOpeningSentence

    display = display.model_copy(update={"publication_opening": (), "reading_aid_markdown": None})
    if display.study_opening:
        return display
    relevant = [item for item in display.items if item.relationship_to_claim.value != "unrelated"]
    groups = {}
    for item in relevant:
        publication = item.verified_publication
        if publication is None:
            return display
        groups.setdefault(publication.canonical_url, []).append(item)
    if not 1 <= len(groups) <= 2:
        return display
    sentences = []
    for key in sorted(groups):
        items = groups[key]
        statements = {item.approved_factual_statement.strip() for item in items}
        relationships = {item.relationship_to_claim for item in items}
        if len(statements) != 1 or len(relationships) != 1:
            return display
        text = next(iter(statements))
        # Conservative sentence check: uncertain punctuation takes the full-text fallback.
        if len(text) > 600 or not re.fullmatch(r"[^.!?]+[.!?]", text):
            return display
        sentences.append(
            PublicationOpeningSentence(
                text=text, ledger_claim_ids=tuple(item.ledger_claim_id for item in items)
            )
        )
    limitations = sorted(
        {limitation.strip() for item in relevant for limitation in item.limitations}
    )
    if not limitations or any(not re.fullmatch(r"[^.!?]+[.!?]", value) for value in limitations):
        return display
    limitation_text = (
        "Recorded limitations: " + "; ".join(value[:-1] for value in limitations) + "."
    )
    if len(limitation_text) > 900:
        return display
    sentences.append(
        PublicationOpeningSentence(
            text=limitation_text,
            ledger_claim_ids=tuple(item.ledger_claim_id for item in relevant if item.limitations),
        )
    )
    return display.model_copy(update={"publication_opening": tuple(sentences)})
