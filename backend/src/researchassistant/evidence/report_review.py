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
    """Build a bounded extractive opening from admissions, without a second model call.

    DOI/authority identity groups publications; otherwise group only the reading
    URL. Ranking selects examples, never estimates effect sizes or study balance.
    Preserve entire admitted statements and keep every source in the evidence list.
    """
    from researchassistant.api.inspection_contracts import PublicationOpeningSentence
    from researchassistant.evidence.report_presentation import citation, source_labels
    from urllib.parse import urldefrag

    display = display.model_copy(
        update={
            "publication_opening": (),
            "opening_notice": None,
            "reading_aid_markdown": None,
        }
    )
    if display.study_opening:
        return display
    groups = {}
    for item in display.items:
        if item.relationship_to_claim.value == "unrelated":
            continue
        key = (
            item.verified_publication.canonical_url
            if item.verified_publication
            else urldefrag(item.source_url).url
        )
        groups.setdefault(key, []).append(item)
    if not groups:
        return display

    def rank(item):
        # Prioritize experimental evidence, then recorded relevance. The final
        # keys make the opening stable across database iteration orders.
        return (
            source_labels(item)[1] != "Randomized trial",
            -(item.claim_fit or 0),
            item.relationship_to_claim.value != "challenges",
            str(item.ledger_claim_id),
        )

    # Coalesce display text only when entire finding sets match. A shared
    # headline finding does not make the remaining findings interchangeable.
    equivalent = {}
    for group in groups.values():
        signature = frozenset(
            (item.approved_factual_statement, item.relationship_to_claim) for item in group
        )
        equivalent.setdefault(signature, []).extend(group)
    by_claim = {item.ledger_claim_id: group for group in equivalent.values() for item in group}
    representatives = sorted((min(group, key=rank) for group in equivalent.values()), key=rank)
    chosen = representatives[:3]

    def has_relationship(item, relationship):
        return any(
            member.relationship_to_claim.value == relationship
            for member in by_claim[item.ledger_claim_id]
        )

    # Include a contrast even when a publication's highest-ranked item has a
    # different relationship from its other admitted findings.
    for relationship in ("supports", "challenges"):
        if any(has_relationship(item, relationship) for item in representatives) and not any(
            has_relationship(item, relationship) for item in chosen
        ):
            # Keep any already-selected contrast when making room.
            replacement = next(
                index
                for index in reversed(range(len(chosen)))
                if all(
                    other_relationship == relationship
                    or not has_relationship(chosen[index], other_relationship)
                    or any(
                        has_relationship(other, other_relationship)
                        for other_index, other in enumerate(chosen)
                        if other_index != index
                    )
                    for other_relationship in ("supports", "challenges")
                )
            )
            chosen[replacement] = next(
                item for item in representatives if has_relationship(item, relationship)
            )
    sentences = []
    for item in chosen:
        linked = sorted(by_claim[item.ledger_claim_id], key=rank)
        statements = dict.fromkeys(
            other.approved_factual_statement for other in sorted(linked, key=rank)
        )
        citations = dict.fromkeys(citation(other) for other in linked)
        sentences.append(
            PublicationOpeningSentence(
                text=f"{'; '.join(citations)}: {' '.join(statements)}",
                ledger_claim_ids=tuple(other.ledger_claim_id for other in linked),
            )
        )
    if len(chosen) < 3:
        limitations = sorted(
            {
                value.strip()
                for item in chosen
                for member in by_claim[item.ledger_claim_id]
                for value in member.limitations
            }
        )
        if limitations:
            sentences.append(
                PublicationOpeningSentence(
                    text="Recorded limitations: " + " ".join(limitations),
                    ledger_claim_ids=tuple(
                        member.ledger_claim_id
                        for item in chosen
                        for member in by_claim[item.ledger_claim_id]
                        if member.limitations
                    ),
                )
            )
    unverified = any(not item.verified_publication for items in groups.values() for item in items)
    notice = (
        f"Selected {len(chosen)} finding groups across {len(groups)} publication or reading-location groups, "
        "prioritizing randomized designs and recorded claim relevance, with supporting and challenging findings included when available. "
        "This selection does not measure the overall balance or independence of studies. "
        "Full findings and limitations appear below."
    )
    if unverified:
        notice += " Some publication identities are unverified; those findings are grouped only by reading location."
    return display.model_copy(
        update={"publication_opening": tuple(sentences), "opening_notice": notice}
    )
