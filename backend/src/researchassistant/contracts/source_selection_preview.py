"""Audited bounded model shortlist; omitted sources remain in the acquired pool."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.research_policy import V2_FOUR_ROUND_SURVIVOR_LIMIT


class V2SelectionOmission(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    disposition: Literal["input_cap"] = "input_cap"
    reason: str = Field(min_length=1, max_length=256)


class V2SelectionShortlistAudit(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    policy_identity: Literal["source-selection-shortlist-v2", "source-selection-shortlist-v3"] = (
        "source-selection-shortlist-v2"
    )
    input_token_cap: Literal[24000] = 24000
    total_sources: int = Field(strict=True, ge=1, le=V2_FOUR_ROUND_SURVIVOR_LIMIT)
    included_source_ids: tuple[UUID, ...] = Field(max_length=V2_FOUR_ROUND_SURVIVOR_LIMIT)
    omitted: tuple[V2SelectionOmission, ...] = Field(max_length=V2_FOUR_ROUND_SURVIVOR_LIMIT)
    rendered_input_tokens: int = Field(strict=True, ge=0, le=24000)

    @model_validator(mode="after")
    def complete_dispositions(self) -> V2SelectionShortlistAudit:
        if self.policy_identity == "source-selection-shortlist-v2" and self.total_sources > 75:
            raise ValueError("historical selection shortlists permit at most 75 sources")
        ids = (*self.included_source_ids, *(row.source_id for row in self.omitted))
        if len(ids) != self.total_sources or len(set(ids)) != len(ids):
            raise ValueError("selection shortlist must disposition every source exactly once")
        return self
