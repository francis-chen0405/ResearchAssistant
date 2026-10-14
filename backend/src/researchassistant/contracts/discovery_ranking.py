"""Stable discovery/acquisition scores, distinct from factual evidence."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import SearchQuery, StrictModel
from researchassistant.contracts.search import SearchResult

DISCARD_SCORE_FLOOR = 5


class DiscoveryDecision(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"
    DISCARDED = "discarded"


class DiscoveryScoreComponents(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relevance: int = Field(ge=0, le=35)
    intent_match: int = Field(ge=0, le=20)
    directness: int = Field(ge=0, le=15)
    metadata_completeness: int = Field(ge=0, le=10)
    likely_accessibility: int = Field(ge=0, le=10)
    source_novelty: int = Field(ge=0, le=10)
    generic_homepage_penalty: int = Field(default=0, ge=-15, le=0)
    marketing_or_community_penalty: int = Field(default=0, ge=-20, le=0)
    unrelated_title_penalty: int = Field(default=0, ge=-10, le=0)

    @property
    def total(self) -> int:
        return max(
            0,
            self.relevance
            + self.intent_match
            + self.directness
            + self.metadata_completeness
            + self.likely_accessibility
            + self.source_novelty
            + self.generic_homepage_penalty
            + self.marketing_or_community_penalty
            + self.unrelated_title_penalty,
        )


class RankedDiscoveryResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: SearchQuery
    result: SearchResult
    canonical_url: str = Field(min_length=1)
    components: DiscoveryScoreComponents
    score: int = Field(ge=0, le=100)
    decision: DiscoveryDecision
    selection_rank: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def validate_score_and_selection(self) -> RankedDiscoveryResult:
        if self.score != self.components.total:
            raise ValueError("discovery score must equal its deterministic components")
        if (self.decision is DiscoveryDecision.SELECTED) != (self.selection_rank is not None):
            raise ValueError("only selected discovery results may have a selection rank")
        if self.decision is DiscoveryDecision.DISCARDED and self.score >= DISCARD_SCORE_FLOOR:
            raise ValueError("only scores below the discard floor may be discarded")
        return self


class AcquiredSourceScoreComponents(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    readability: int = Field(ge=0, le=25)
    claim_term_coverage: int = Field(ge=0, le=35)
    document_specificity: int = Field(ge=0, le=25)
    evidence_language: int = Field(ge=0, le=15)
    generic_or_promotional_penalty: int = Field(default=0, ge=-20, le=0)

    @property
    def total(self) -> int:
        return max(
            0,
            self.readability
            + self.claim_term_coverage
            + self.document_specificity
            + self.evidence_language
            + self.generic_or_promotional_penalty,
        )


class RankedAcquiredSource(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    retrieval_attempt_id: UUID
    components: AcquiredSourceScoreComponents
    score: int = Field(ge=0, le=100)
    extraction_rank: int = Field(ge=1, le=25)

    @model_validator(mode="after")
    def validate_score(self) -> RankedAcquiredSource:
        if self.score != self.components.total:
            raise ValueError("acquired-source score must equal its deterministic components")
        return self
