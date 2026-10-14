"""Read-only result and evidence display contracts."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from researchassistant.agents.v2_post_analysis import V2PostAnalysisAssessment
from researchassistant.contracts.models import StrictModel, V2EvidenceRelationship
from researchassistant.evidence.study_lineage import StudyLineageNotice


class V2EvidenceDisplayItem(StrictModel):
    """Read-only evidence detail suitable for the v2 result page."""

    source_id: UUID
    ledger_claim_id: UUID
    title: str | None = None
    source_url: str = Field(min_length=1)
    source_type: str | None = None
    claim_fit: int | None = Field(default=None, ge=1, le=5)
    source_context_notice: str | None = None
    source_family: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    relationship_to_claim: V2EvidenceRelationship
    approved_factual_statement: str = Field(min_length=1)
    recommendation_status: str = Field(min_length=1)
    selection_rationale: str | None = None
    gap_ids: tuple[str, ...] = ()
    evidence_summary: str = Field(min_length=1)
    supporting_proposition: str = Field(min_length=1)
    quote_passage: str = Field(min_length=1)
    limitations: tuple[str, ...] = ()
    validation_status: str = Field(min_length=1)


class V2ResearchStatusDisplay(StrictModel):
    """Read-only current governor/coverage summary alongside the frozen brief."""

    reason_code: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    actionable_gap_count: int = Field(ge=0)
    partial_coverage_count: int = Field(ge=0)
    unavailable_coverage_count: int = Field(ge=0)
    source: Literal["persisted_governor", "final_output"]


class V2SourceBudgetOutcomeDisplay(StrictModel):
    """Read-only source-local budget outcome from persisted execution evidence."""

    source_id: UUID
    outcome: Literal["source_budget_blocked", "token_cap_blocked", "physical_call_cap_blocked"]


class V2SharedWebsiteGroup(StrictModel):
    """Admitted sources sharing a website host, without implying source identity."""

    host: str = Field(min_length=1)
    source_ids: tuple[UUID, ...] = Field(min_length=2)
    explanation: str = Field(min_length=1)


class V2SourceTitleDisplay(StrictModel):
    """Readable source heading plus the captured title for expanded provenance."""

    source_id: UUID
    display_title: str = Field(min_length=1)
    captured_title: str | None = None


class V2EvidenceDisplay(StrictModel):
    run_id: UUID
    items: tuple[V2EvidenceDisplayItem, ...]
    source_titles: tuple[V2SourceTitleDisplay, ...] = ()
    study_lineage: tuple[StudyLineageNotice, ...] = ()
    source_budget_outcomes: tuple[V2SourceBudgetOutcomeDisplay, ...] = ()
    shared_website_groups: tuple[V2SharedWebsiteGroup, ...] = ()
    research_status: V2ResearchStatusDisplay
    post_analysis_assessment: V2PostAnalysisAssessment | None = None
