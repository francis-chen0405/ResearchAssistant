"""Strict model-owned semantic content for provider-neutral search planning."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from researchassistant.contracts.discovery_v2 import SearchMode
from researchassistant.contracts.model_contracts import DiscoveryProvider, StrictModel
from researchassistant.contracts.model_research import (
    V2InitialPlannerClaimComponent,
    V2ScopeInterpretation,
    V2SearchAgentInput,
)
from researchassistant.contracts.research_directions import ResearchDirection


class V2QueryConceptGroup(StrictModel):
    """One required concept and a few practical aliases supplied by the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    concept: str = Field(min_length=1, max_length=240)
    aliases: tuple[str, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def unique_aliases(self) -> V2QueryConceptGroup:
        values = tuple(item.strip().casefold() for item in (self.concept, *self.aliases))
        if any(not item for item in values) or len(values) != len(set(values)):
            raise ValueError("query concepts and aliases must be non-empty and unique")
        return self


class V2QueryConcepts(StrictModel):
    """Model response content; all routing, IDs, modes, and limits stay application-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_concepts: tuple[V2QueryConceptGroup, ...] = Field(min_length=1, max_length=8)
    methods: tuple[str, ...] = Field(default=(), max_length=5)
    outcomes: tuple[str, ...] = Field(default=(), max_length=5)
    purpose: Literal["broad", "methods", "outcomes", "limitations", "gap"]

    @model_validator(mode="after")
    def non_empty_context_terms(self) -> V2QueryConcepts:
        for label, terms in (("methods", self.methods), ("outcomes", self.outcomes)):
            if any(not value.strip() for value in terms):
                raise ValueError(f"{label} terms must be non-empty")
            if len({value.strip().casefold() for value in terms}) != len(terms):
                raise ValueError(f"{label} terms must be unique")
        return self


class V2InitialPlannerConceptsOutput(StrictModel):
    """Ordered conceptual suggestions, aligned to application-owned Round-1 lanes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_interpretations: tuple[V2ScopeInterpretation, ...] = Field(default=(), max_length=4)
    claim_coverage_focus: tuple[V2InitialPlannerClaimComponent, ...] = Field(
        default=(), max_length=3
    )
    queries: tuple[V2QueryConcepts, ...] = Field(min_length=1, max_length=24)

    @field_validator("claim_coverage_focus")
    @classmethod
    def unique_claim_dimensions(
        cls, value: tuple[V2InitialPlannerClaimComponent, ...]
    ) -> tuple[V2InitialPlannerClaimComponent, ...]:
        if len({item.dimension for item in value}) != len(value):
            raise PydanticCustomError(
                "planner_duplicate_coverage_dimension",
                "Planner claim-coverage dimensions must be unique",
            )
        return value


class V2ConceptualAdaptiveLane(StrictModel):
    """An application-assigned route and gap set for one adaptive concept slot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: ResearchDirection
    provider: DiscoveryProvider
    strategy: str = Field(min_length=1, max_length=240)
    target_gap_ids: tuple[str, ...] = Field(min_length=1, max_length=6)
    mode: SearchMode | None = None

    @model_validator(mode="after")
    def unique_gaps(self) -> V2ConceptualAdaptiveLane:
        if len(set(self.target_gap_ids)) != len(self.target_gap_ids):
            raise ValueError("adaptive lane Gap IDs must be unique")
        return self


class V2ConceptualSearchAgentInput(StrictModel):
    """Context plus application-owned ordered slots; the model cannot alter slot routing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: V2SearchAgentInput
    lanes: tuple[V2ConceptualAdaptiveLane, ...] = Field(min_length=1, max_length=12)
    rejected_feedback: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_application_slots(self) -> V2ConceptualSearchAgentInput:
        if not self.lanes:
            raise ValueError("adaptive conceptual input must include an eligible lane")
        gap_ids = {gap.gap_id: gap for gap in self.request.material_gaps}
        for lane in self.lanes:
            self.request.directions.require_permitted(lane.direction)
            if lane.provider not in self.request.eligible_providers:
                raise ValueError("adaptive conceptual lane uses an ineligible provider")
            if any(gap_id not in gap_ids for gap_id in lane.target_gap_ids):
                raise ValueError("adaptive conceptual lane references an unknown Gap ID")
            if any(
                gap_ids[gap_id].direction is not lane.direction for gap_id in lane.target_gap_ids
            ):
                raise ValueError("adaptive conceptual lane Gap direction mismatch")
        return self


class V2AdaptiveSearchConceptProposal(StrictModel):
    """Concepts assigned to one bounded application lane by its zero-based index."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane_index: int = Field(strict=True, ge=0, le=11)
    concepts: V2QueryConcepts


class V2AdaptiveSearchConceptsOutput(StrictModel):
    """Concepts for application-owned adaptive lanes and persisted Gap IDs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    searches: tuple[V2AdaptiveSearchConceptProposal, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def require_gap_purpose(self) -> V2AdaptiveSearchConceptsOutput:
        if any(item.concepts.purpose != "gap" for item in self.searches):
            raise ValueError("adaptive Search Agent concepts must use gap purpose")
        if len({item.lane_index for item in self.searches}) != len(self.searches):
            raise ValueError("adaptive proposals must use each application lane at most once")
        return self
