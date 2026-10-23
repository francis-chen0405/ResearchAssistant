"""Confirmed retained-paper locations; never a citation or inherited judgment."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.research_directions import ResearchDirection


class ConfirmedPaperLocation(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: UUID
    snapshot_id: UUID
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: str
    research_round: int = Field(ge=1, le=4)
    direction: ResearchDirection
    doi: str
    basis: Literal["metadata", "publisher_url", "pmc_header"]


class ConfirmedPaperGroup(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    canonical_source_id: UUID
    doi: str
    locations: tuple[ConfirmedPaperLocation, ...] = Field(min_length=2, max_length=240)

    @model_validator(mode="after")
    def consistent_locations(self) -> ConfirmedPaperGroup:
        ids = tuple(location.source_id for location in self.locations)
        if len(set(ids)) != len(ids) or ids.count(self.canonical_source_id) != 1:
            raise ValueError("paper group requires distinct locations and its canonical source")
        if any(location.doi != self.doi for location in self.locations):
            raise ValueError("paper group DOI must match every location")
        if len({location.direction for location in self.locations}) != 1:
            raise ValueError("paper group must preserve its search direction")
        return self


class V2PaperIdentityAudit(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: UUID
    policy: Literal["retained-paper-identity-v1"] = "retained-paper-identity-v1"
    groups: tuple[ConfirmedPaperGroup, ...] = Field(default=(), max_length=120)

    @model_validator(mode="after")
    def unique_membership(self) -> V2PaperIdentityAudit:
        ids = tuple(location.source_id for group in self.groups for location in group.locations)
        if len(set(ids)) != len(ids):
            raise ValueError("paper location belongs to multiple identity groups")
        return self
