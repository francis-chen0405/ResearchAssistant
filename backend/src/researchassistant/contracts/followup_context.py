"""Bounded strategy observations; none of these records admits evidence."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.research_directions import ResearchDirection


class FollowupRetrievalAttempt(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str = Field(max_length=300)
    location: str | None = Field(default=None, max_length=512)
    location_omitted: bool = False
    provider: str = Field(max_length=100)
    outcome: str = Field(max_length=100)


class FollowupExample(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["query", "source"]
    reference: str = Field(min_length=1, max_length=300)
    query_id: UUID | None = None
    provider: str | None = Field(default=None, max_length=100)
    mode: str | None = Field(default=None, max_length=100)
    result_count: int | None = Field(default=None, ge=0)
    captured_source_count: int | None = Field(default=None, ge=0)
    attempt_ids: tuple[UUID, ...] = Field(default=(), max_length=3)
    omitted_attempt_ids: int = Field(default=0, ge=0)
    source_id: UUID | None = None
    snapshot_id: UUID | None = None
    link: Literal[
        "query_target", "discovery_lead", "assessed_gap", "explicit_source_reference", "unassigned"
    ]
    status: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=500)
    location: str | None = Field(default=None, max_length=512)
    location_omitted: bool = False
    findings: str | None = Field(default=None, max_length=500)
    relationship_to_claim: str | None = Field(default=None, max_length=100)
    assessment_failure: str | None = Field(default=None, max_length=300)
    limitations: tuple[str, ...] = Field(default=(), max_length=2)
    excerpts_clipped: bool = False
    retrieval_attempts: tuple[FollowupRetrievalAttempt, ...] = Field(default=(), max_length=3)
    omitted_retrieval_attempts: int = Field(default=0, ge=0)


class GapFollowupContext(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: str
    direction: ResearchDirection
    needed_evidence: str = Field(max_length=500)
    assessment_explanation: str = Field(max_length=500)
    coverage_state: str | None = None
    coverage_explanation: str | None = Field(default=None, max_length=500)
    causes: tuple[
        Literal["not_found", "access_failed", "insufficient_assessed", "conflicting", "unknown"],
        ...,
    ] = Field(max_length=5)
    search_state: Literal["not_searched_yet", "no_explicit_query_link", "observed", "unknown"]
    query_outcome_counts: dict[str, int] = Field(max_length=12)
    source_count: int = Field(ge=0)
    pending_assessment_lead_count: int = Field(ge=0)
    examples: tuple[FollowupExample, ...] = Field(default=(), max_length=3)
    omitted_examples: int = Field(ge=0)
    excerpts_clipped: bool = False


class FollowupContext(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: Literal["gap-followup-context-v1"] = "gap-followup-context-v1"
    gap_assessment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    gaps: tuple[GapFollowupContext, ...] = Field(min_length=1, max_length=6)
    unassigned_queries: int = Field(ge=0)
    unassigned_sources: int = Field(ge=0)
    unassigned_findings: int = Field(ge=0)
    unassigned_assessed_examples: tuple[FollowupExample, ...] = Field(default=(), max_length=3)
    omitted_unassigned_findings: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def unique_gaps(self) -> FollowupContext:
        if len({gap.gap_id for gap in self.gaps}) != len(self.gaps):
            raise ValueError("follow-up context requires unique gaps")
        if any(
            len(text) > 300
            for example in (
                *self.unassigned_assessed_examples,
                *(example for gap in self.gaps for example in gap.examples),
            )
            for text in example.limitations
        ):
            raise ValueError("follow-up limitation excerpt exceeds 300 characters")
        return self
