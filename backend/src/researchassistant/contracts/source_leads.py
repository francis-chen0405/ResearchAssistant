"""Provider-neutral, non-evidentiary read-only discovery projections."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from researchassistant.contracts.model_contracts import StrictModel


class SourceLeadStage(StrictModel):
    stage: str
    status: str
    reason: str | None


class SourceLead(StrictModel):
    lead_id: str
    source_id: UUID | None
    title: str | None
    url: str
    work_id: str | None
    source_family: str | None = None
    providers: tuple[str, ...]
    search_directions: tuple[str, ...]
    rounds: tuple[int, ...]
    capture_status: Literal["unknown", "attempted", "failed", "captured", "readable", "unusable"]
    readable_alternate_url: str | None = None
    disposition: str
    reason: str
    confidence: Literal["recorded", "unknown"]
    unknowns: tuple[str, ...]
    history: tuple[SourceLeadStage, ...]


class SourceLeadsPage(StrictModel):
    projection_identity: Literal["source-leads-view-v1"] = "source-leads-view-v1"
    run_id: UUID
    items: tuple[SourceLead, ...] = Field(max_length=100)
    total: int = Field(ge=0, le=6000)
    offset: int = Field(ge=0, le=6000)
    limit: int = Field(ge=1, le=100)
    has_more: bool
    notice: str


class LiveSourceCard(StrictModel):
    work_id: UUID
    title: str | None
    url: str
    readable_url: str | None
    first_round: int = Field(ge=1, le=4)
    state: Literal["lead", "screened", "captured", "full_text", "assessed", "admitted"]
    note: str | None = Field(max_length=440)
    note_kind: Literal["metadata", "scout", "analyst"] | None
    angle: str | None


class LiveSourcesPage(StrictModel):
    run_id: UUID
    revision: str
    unchanged: bool = False
    items: tuple[LiveSourceCard, ...] = Field(max_length=25)
    total: int = Field(ge=0, le=1200)
