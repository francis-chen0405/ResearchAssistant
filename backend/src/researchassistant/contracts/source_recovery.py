"""Non-evidentiary research leads and assessed-source feedback."""

from __future__ import annotations

from uuid import UUID

from pydantic import ConfigDict, Field

from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.research_directions import ResearchDirection


class AssessedSourceFinding(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    outcome: str = Field(min_length=1, max_length=100)
    supported_proposition: str | None = Field(default=None, max_length=2000)
    relationship_to_claim: str | None = Field(default=None, max_length=100)
    limitations: tuple[str, ...] = Field(default=(), max_length=12)
    failure: str | None = Field(default=None, max_length=1000)


class SavedSourceLead(StrictModel):
    """Prior source metadata only; prior judgments and citations are never carried over."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin_run_id: UUID
    origin_source_id: UUID
    title: str = Field(min_length=1, max_length=2000)
    source_url: str = Field(min_length=1, max_length=4000)
    doi: str | None = Field(default=None, max_length=512)


class V2SavedSourceSuggestions(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: UUID
    exact_claim: str
    leads: tuple[SavedSourceLead, ...] = Field(default=(), max_length=12)
