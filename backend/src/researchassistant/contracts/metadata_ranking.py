"""Typed audit contracts for fresh-v2 metadata ranking and Scout disposition."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import DiscoveryProvider, StrictModel
from researchassistant.contracts.research_directions import ResearchDirection


class MetadataRankingWeights(StrictModel):
    """Bounded, frozen contribution weights for common metadata signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    directness: float = Field(default=5.0, ge=0.0, le=10.0, allow_inf_nan=False)
    method_fit: float = Field(default=3.0, ge=0.0, le=10.0, allow_inf_nan=False)
    gap_fit: float = Field(default=2.0, ge=0.0, le=10.0, allow_inf_nan=False)
    identity_completeness: float = Field(default=1.0, ge=0.0, le=10.0, allow_inf_nan=False)
    novelty: float = Field(default=1.0, ge=0.0, le=10.0, allow_inf_nan=False)
    diversity: float = Field(default=1.0, ge=0.0, le=10.0, allow_inf_nan=False)


class MetadataRank(StrictModel):
    """Deterministic, metadata-only rank; scores never represent evidence quality."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: UUID
    rank: int = Field(strict=True, ge=1, le=300)
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    directness: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    method_fit: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    gap_fit: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    identity_completeness: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    novelty: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    diversity: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    work_key: str = Field(min_length=1, max_length=512)
    lane_direction: ResearchDirection
    lane_provider: DiscoveryProvider
    rationale: tuple[str, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def bounded_rationale(self) -> MetadataRank:
        if any(not text.strip() or len(text) > 256 for text in self.rationale):
            raise ValueError("metadata rank rationale entries must be 1 to 256 characters")
        return self


class V2ScoutDisposition(StrictModel):
    """Whether one retained discovery item was actually sent to Scout."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: UUID
    disposition: Literal["scouted", "not_scouted_cap", "not_scouted_budget"]


class MetadataIdentityConflict(StrictModel):
    """Visible metadata disagreement; it makes no claim about study independence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["same_location_distinct_doi", "same_doi_distinct_titles"]
    item_ids: tuple[UUID, ...] = Field(min_length=2, max_length=300)
    values: tuple[str, ...] = Field(min_length=2, max_length=300)

    @model_validator(mode="after")
    def unique_bounded_values(self) -> MetadataIdentityConflict:
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("identity conflict item IDs must be unique")
        if len(set(self.values)) != len(self.values) or any(
            not value.strip() or len(value) > 512 for value in self.values
        ):
            raise ValueError("identity conflict values must be distinct and bounded")
        return self


class V2MetadataRankingArtifact(StrictModel):
    """Immutable round sidecar for rank provenance and bounded Scout coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: int = Field(strict=True, ge=1, le=4)
    ranking_identity: Literal["source-candidate-ranking-v2"] = "source-candidate-ranking-v2"
    ranks: tuple[MetadataRank, ...] = Field(max_length=300)
    scout_dispositions: tuple[V2ScoutDisposition, ...] = Field(max_length=300)
    identity_conflicts: tuple[MetadataIdentityConflict, ...] = Field(default=(), max_length=600)
    retained_count: int = Field(strict=True, ge=0, le=300)
    scouted_count: int = Field(strict=True, ge=0, le=60)
    cap_limited_count: int = Field(strict=True, ge=0, le=300)
    budget_limited_count: int = Field(strict=True, ge=0, le=300)

    @model_validator(mode="after")
    def coherent_membership(self) -> V2MetadataRankingArtifact:
        ranked = {item.item_id for item in self.ranks}
        disposed = {item.item_id for item in self.scout_dispositions}
        if len(ranked) != len(self.ranks) or len(disposed) != len(self.scout_dispositions):
            raise ValueError("metadata ranking sidecar item IDs must be unique")
        if ranked != disposed:
            raise ValueError("every ranked item requires exactly one Scout disposition")
        if sorted(item.rank for item in self.ranks) != list(range(1, len(self.ranks) + 1)):
            raise ValueError("metadata ranks must form a dense unique sequence")
        if any(not set(conflict.item_ids) <= ranked for conflict in self.identity_conflicts):
            raise ValueError("identity conflict refers to an unranked item")
        if self.retained_count != len(self.ranks):
            raise ValueError("retained count must match rank membership")
        counts = {
            "scouted": sum(x.disposition == "scouted" for x in self.scout_dispositions),
            "cap": sum(x.disposition == "not_scouted_cap" for x in self.scout_dispositions),
            "budget": sum(x.disposition == "not_scouted_budget" for x in self.scout_dispositions),
        }
        if (self.scouted_count, self.cap_limited_count, self.budget_limited_count) != (
            counts["scouted"],
            counts["cap"],
            counts["budget"],
        ):
            raise ValueError("Scout disposition counters must match the sidecar decisions")
        return self
