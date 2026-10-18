"""Initial and adaptive planning handoffs and query validation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic_core import PydanticCustomError

from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2GraphNeighborAction,
)
from researchassistant.contracts.model_contracts import (
    DiscoveryProvider,
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
    StrictModel,
    _validate_aware_datetime,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageDimension as V2ClaimCoverageDimension,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageFocus as V2ClaimCoverageFocus,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageKind as V2ClaimCoverageKind,
)
from researchassistant.contracts.research_coverage import (
    V2InitialPlannerClaimComponent as V2InitialPlannerClaimComponent,
)
from researchassistant.contracts.research_coverage import (
    V2MaterialGap as V2MaterialGap,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.contracts.research_gaps import (
    V2GapSearchDirection as V2GapSearchDirection,
)
from researchassistant.contracts.research_policy import (
    V2_ADAPTIVE_SEARCH_POLICY_IDENTITY as V2_ADAPTIVE_SEARCH_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_INITIAL_PLANNER_POLICY_IDENTITY as V2_INITIAL_PLANNER_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY as V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
)


class SearchDirectionGapReference(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: NonEmptyStr
    direction: ResearchDirection
    gap_description: NonEmptyStr


class V2PlannedSearch(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    search_id: NonEmptyStr
    direction: ResearchDirection
    query_text: NonEmptyStr
    gap_references: tuple[SearchDirectionGapReference, ...] = ()

    @model_validator(mode="after")
    def validate_gap_directions(self) -> V2PlannedSearch:
        if any(reference.direction is not self.direction for reference in self.gap_references):
            raise ValueError("search gap references must match the search direction")
        return self


class V2InitialResearchPlan(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    searches: tuple[V2PlannedSearch, ...]
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_searches(self) -> V2InitialResearchPlan:
        for search in self.searches:
            self.directions.require_permitted(search.direction)
        return self


class V2SearchRoundPlan(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: PositiveInt
    directions: ResearchDirections
    searches: tuple[V2PlannedSearch, ...]
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_searches(self) -> V2SearchRoundPlan:
        for search in self.searches:
            self.directions.require_permitted(search.direction)
        return self


class V2InitialPlannerSearchLane(StrictModel):
    """One application-owned valid slot in the v2 initial broad-search plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: ResearchDirection
    provider: DiscoveryProvider
    strategy: NonEmptyStr
    round_number: Literal[1] = 1


class V2InitialPlannerPolicy(StrictModel):
    """The single v2 authority for provider eligibility and Round-1 search lanes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_identity: Literal["researchassistant-v2-phase-3-initial-planner-v1"] = (
        V2_INITIAL_PLANNER_POLICY_IDENTITY
    )

    def search_lanes(
        self,
        directions: ResearchDirections,
        providers: tuple[DiscoveryProvider, ...],
    ) -> tuple[V2InitialPlannerSearchLane, ...]:
        """Return the only valid Round-1 slots for enabled directions and providers."""
        _validate_v2_discovery_providers(providers)
        strategies = {
            DiscoveryProvider.SERPSEARCH: ("broad_web", "institutional_coverage"),
            DiscoveryProvider.EXA: ("direct_evidence", "mechanism", "analysis"),
            DiscoveryProvider.OPENALEX: ("academic_studies",),
            DiscoveryProvider.ARXIV: ("preprints",),
            DiscoveryProvider.PUBMED: ("biomedical_studies",),
            DiscoveryProvider.SERPER: ("broad_web",),
        }
        return tuple(
            V2InitialPlannerSearchLane(
                direction=direction,
                provider=provider,
                strategy=strategy,
            )
            for direction in directions.enabled_directions
            for provider in providers
            for strategy in strategies[provider]
        )

    def validate_searches(
        self,
        directions: ResearchDirections,
        providers: tuple[DiscoveryProvider, ...],
        searches: tuple[V2RoundOneSearchQuery, ...],
    ) -> None:
        """Reject every query that is outside a selected application-owned search lane."""
        expected_lanes = self.search_lanes(directions, providers)
        actual_lanes = tuple(
            V2InitialPlannerSearchLane(
                direction=search.direction,
                provider=search.provider,
                strategy=search.strategy,
                round_number=search.round_number,
            )
            for search in searches
        )
        if len({search.query_id for search in searches}) != len(searches):
            raise ValueError("v2 Round-1 query IDs must be unique")
        if len(set(actual_lanes)) != len(actual_lanes):
            raise ValueError("v2 Round-1 search lanes must not contain duplicate queries")
        if set(actual_lanes) != set(expected_lanes):
            raise ValueError("v2 Round-1 queries must exactly fill the enabled policy lanes")
        normalized_lanes: set[tuple[ResearchDirection, DiscoveryProvider, int, str]] = set()
        for search in searches:
            normalized = " ".join(search.query_text.split()).casefold()
            lane = (search.direction, search.provider, search.round_number, normalized)
            if lane in normalized_lanes:
                raise ValueError("v2 Round-1 query text must be unique within its search lane")
            normalized_lanes.add(lane)


def _validate_v2_discovery_providers(value: tuple[DiscoveryProvider, ...]) -> None:
    if not value:
        raise ValueError("at least one v2 discovery provider must be enabled")
    if len(set(value)) != len(value):
        raise ValueError("v2 discovery providers must not contain duplicates")
    canonical = tuple(provider for provider in DiscoveryProvider if provider in value)
    if value != canonical:
        raise ValueError("v2 discovery providers must use canonical provider order")


class V2InitialPlannerInput(StrictModel):
    """Application-owned controls for the only planner call in a fresh v2 startup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    raw_claim: NonEmptyStr
    directions: ResearchDirections
    discovery_providers: tuple[DiscoveryProvider, ...]
    policy_identity: Literal["researchassistant-v2-phase-3-initial-planner-v1"] = (
        V2_INITIAL_PLANNER_POLICY_IDENTITY
    )
    search_lanes: tuple[V2InitialPlannerSearchLane, ...]

    @field_validator("discovery_providers")
    @classmethod
    def validate_discovery_providers(
        cls, value: tuple[DiscoveryProvider, ...]
    ) -> tuple[DiscoveryProvider, ...]:
        _validate_v2_discovery_providers(value)
        return value

    @model_validator(mode="after")
    def validate_policy_lanes(self) -> V2InitialPlannerInput:
        expected = V2InitialPlannerPolicy().search_lanes(self.directions, self.discovery_providers)
        if self.search_lanes != expected:
            raise ValueError("v2 initial planner lanes must be application-owned policy lanes")
        return self


class V2ScopeInterpretation(StrictModel):
    """A material scope reading or ambiguity that could affect Round-1 discovery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: NonEmptyStr
    impact: NonEmptyStr


class V2InitialPlannerSearchResponse(StrictModel):
    """Narrow model-owned semantic content for one application-owned search lane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: ResearchDirection
    provider: DiscoveryProvider
    strategy: NonEmptyStr
    query_text: NonEmptyStr


class V2InitialPlannerModelOutput(StrictModel):
    """Model response without application IDs, timestamps, policy, or future planning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_interpretations: tuple[V2ScopeInterpretation, ...] = Field(default=(), max_length=4)
    claim_coverage_focus: tuple[V2InitialPlannerClaimComponent, ...] = Field(
        default=(), max_length=3
    )
    searches: tuple[V2InitialPlannerSearchResponse, ...]

    @field_validator("claim_coverage_focus")
    @classmethod
    def validate_claim_components(
        cls, value: tuple[V2InitialPlannerClaimComponent, ...]
    ) -> tuple[V2InitialPlannerClaimComponent, ...]:
        if len({item.dimension for item in value}) != len(value):
            raise PydanticCustomError(
                "planner_duplicate_coverage_dimension",
                "Planner claim-coverage dimensions must be unique",
            )
        return value


class V2RoundOneSearchQuery(StrictModel):
    """A persisted fresh-v2 broad discovery query, constrained to actual Round 1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    query_id: UUID
    direction: ResearchDirection
    provider: DiscoveryProvider
    round_number: Literal[1] = 1
    strategy: NonEmptyStr
    query_text: NonEmptyStr
    compiled_query: V2CompiledQueryAction | None = None
    policy_identity: Literal["researchassistant-v2-phase-3-initial-planner-v1"] = (
        V2_INITIAL_PLANNER_POLICY_IDENTITY
    )
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_compiled_lane(self) -> V2RoundOneSearchQuery:
        if self.compiled_query is not None:
            concepts = self.compiled_query.conceptual_query
            if (
                concepts.run_id != self.run_id
                or concepts.provider != self.provider
                or concepts.direction != self.direction
                or concepts.round_number != self.round_number
                or self.compiled_query.query_text != self.query_text
                or concepts.target_gap_ids != ()
            ):
                raise ValueError(
                    "compiled query must preserve its application-owned lane and Gap IDs"
                )
        return self


class V2InitialPlannerOutput(StrictModel):
    """Complete persisted output of the single broad Round-1 v2 planner call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    raw_claim: NonEmptyStr
    directions: ResearchDirections
    discovery_providers: tuple[DiscoveryProvider, ...]
    policy_identity: Literal["researchassistant-v2-phase-3-initial-planner-v1"] = (
        V2_INITIAL_PLANNER_POLICY_IDENTITY
    )
    scope_interpretations: tuple[V2ScopeInterpretation, ...] = Field(default=(), max_length=4)
    claim_coverage_focus: tuple[V2ClaimCoverageFocus, ...] = Field(default=(), max_length=3)
    searches: tuple[V2RoundOneSearchQuery, ...]
    planner_prompt_version: NonEmptyStr
    planner_model_name: Literal["mimo-v2.5-pro"] = "mimo-v2.5-pro"
    planned_at: datetime

    _planned_at_is_aware = field_validator("planned_at")(_validate_aware_datetime)

    @field_validator("claim_coverage_focus")
    @classmethod
    def validate_persisted_claim_components(
        cls, value: tuple[V2ClaimCoverageFocus, ...]
    ) -> tuple[V2ClaimCoverageFocus, ...]:
        permitted = {
            V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            V2ClaimCoverageDimension.POPULATION_AND_SETTING,
            V2ClaimCoverageDimension.MECHANISM_OR_PATHWAY,
        }
        if any(
            item.dimension not in permitted
            or item.kind is not V2ClaimCoverageKind.CLAIM_COMPONENT
            or not item.searchable
            or item.unavailable_reason is not None
            for item in value
        ):
            raise ValueError("Planner coverage focus may contain only searchable claim components")
        if len({item.dimension for item in value}) != len(value):
            raise ValueError("Planner claim-coverage dimensions must be unique")
        return value

    @field_validator("discovery_providers")
    @classmethod
    def validate_discovery_providers(
        cls, value: tuple[DiscoveryProvider, ...]
    ) -> tuple[DiscoveryProvider, ...]:
        _validate_v2_discovery_providers(value)
        return value

    @model_validator(mode="after")
    def validate_round_one_plan(self) -> V2InitialPlannerOutput:
        if any(search.run_id != self.run_id for search in self.searches):
            raise ValueError("v2 Round-1 query run_id must match the planner output")
        if any(search.policy_identity != self.policy_identity for search in self.searches):
            raise ValueError("v2 Round-1 query policy must match the planner output")
        V2InitialPlannerPolicy().validate_searches(
            self.directions, self.discovery_providers, self.searches
        )
        return self


class V2ProviderSearchBudget(StrictModel):
    """Application-owned cumulative provider ceiling visible to adaptive planning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: DiscoveryProvider
    attempted_calls: NonNegativeInt
    maximum_calls: PositiveInt

    @model_validator(mode="after")
    def validate_usage(self) -> V2ProviderSearchBudget:
        if self.attempted_calls > self.maximum_calls:
            raise ValueError("provider attempted calls cannot exceed its hard ceiling")
        return self

    @property
    def remaining_calls(self) -> int:
        return self.maximum_calls - self.attempted_calls


class V2AdaptiveSearchProposal(StrictModel):
    """Model-owned semantic query proposal without IDs, timestamps, or authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: ResearchDirection
    provider: DiscoveryProvider
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=3)
    strategy: NonEmptyStr
    query_text: NonEmptyStr

    @field_validator("targeted_gap_ids")
    @classmethod
    def validate_unique_gap_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("adaptive query Gap IDs must be unique")
        return value


class V2AdaptiveSearchModelOutput(StrictModel):
    """Strict Search-Agent response validated again by deterministic application policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    searches: tuple[V2AdaptiveSearchProposal, ...] = Field(min_length=1, max_length=12)


class V2AdaptiveSearchQuery(StrictModel):
    """Application-owned persisted Round-2 or Round-3 query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    query_id: UUID
    round_number: Literal[2, 3, 4]
    direction: ResearchDirection
    provider: DiscoveryProvider
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(max_length=6)
    strategy: NonEmptyStr
    query_text: NonEmptyStr | None
    compiled_query: V2CompiledQueryAction | None = None
    graph_action: V2GraphNeighborAction | None = None
    policy_identity: Literal[
        "researchassistant-v2-phase-7-adaptive-search-v1",
        "researchassistant-v2-post-phase-13-round-four-v1",
    ] = V2_ADAPTIVE_SEARCH_POLICY_IDENTITY
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_round_policy(self) -> V2AdaptiveSearchQuery:
        if self.round_number == 4 and self.policy_identity != V2_POST13_ROUND_FOUR_POLICY_IDENTITY:
            raise ValueError("Phase-7 adaptive queries permit only rounds 2 or 3")
        if self.round_number < 4 and self.policy_identity != V2_ADAPTIVE_SEARCH_POLICY_IDENTITY:
            raise ValueError("Rounds 2 and 3 require the Phase-7 policy")
        return self

    @model_validator(mode="after")
    def validate_compiled_lane(self) -> V2AdaptiveSearchQuery:
        if self.graph_action is not None:
            action = self.graph_action
            if self.query_text is not None or self.compiled_query is not None:
                raise ValueError("graph neighbor lanes cannot carry text or compiled queries")
            if (
                self.query_id != action.artifact_id
                or self.run_id != action.run_id
                or self.provider != action.provider
                or self.direction != action.direction
                or self.round_number != action.round_number
                or self.targeted_gap_ids != action.target_gap_ids
            ):
                raise ValueError("graph neighbor lane must preserve its action identity and fields")
            return self
        if self.query_text is None:
            raise ValueError("text search lanes require query_text")
        if not self.targeted_gap_ids:
            raise ValueError("text search lanes require targeted Gap IDs")
        if self.compiled_query is not None:
            concepts = self.compiled_query.conceptual_query
            if (
                concepts.run_id != self.run_id
                or concepts.provider != self.provider
                or concepts.direction != self.direction
                or concepts.round_number != self.round_number
                or self.compiled_query.query_text != self.query_text
                or concepts.target_gap_ids != self.targeted_gap_ids
            ):
                raise ValueError(
                    "compiled query must preserve its application-owned lane and Gap IDs"
                )
        return self

    @model_serializer(mode="wrap")
    def omit_absent_graph_action(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value = handler(self)
        if self.graph_action is None:
            value.pop("graph_action", None)
        return value


class V2AdaptiveRoundPlan(StrictModel):
    """Complete immutable plan for one permitted adaptive round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: Literal[2, 3, 4]
    directions: ResearchDirections
    enabled_providers: tuple[DiscoveryProvider, ...]
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=6)
    discovered_terms: tuple[NonEmptyStr, ...] = Field(max_length=40)
    searches: tuple[V2AdaptiveSearchQuery, ...] = Field(min_length=1, max_length=12)
    search_agent_prompt_version: NonEmptyStr
    search_agent_model_name: Literal["mimo-v2.5-pro"] = "mimo-v2.5-pro"
    policy_identity: Literal[
        "researchassistant-v2-phase-7-adaptive-search-v1",
        "researchassistant-v2-post-phase-13-round-four-v1",
    ] = V2_ADAPTIVE_SEARCH_POLICY_IDENTITY
    planned_at: datetime

    _planned_at_is_aware = field_validator("planned_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_adaptive_round(self) -> V2AdaptiveRoundPlan:
        if self.round_number == 4 and self.policy_identity != V2_POST13_ROUND_FOUR_POLICY_IDENTITY:
            raise ValueError("Round 4 plans require the post-Phase-13 policy")
        if self.round_number < 4 and self.policy_identity != V2_ADAPTIVE_SEARCH_POLICY_IDENTITY:
            raise ValueError("Rounds 2 and 3 require the Phase-7 policy")
        if len(set(self.targeted_gap_ids)) != len(self.targeted_gap_ids):
            raise ValueError("adaptive round targeted Gap IDs must be unique")
        if len({query.query_id for query in self.searches}) != len(self.searches):
            raise ValueError("adaptive round query IDs must be unique")
        for query in self.searches:
            if query.run_id != self.run_id or query.round_number != self.round_number:
                raise ValueError("adaptive queries must match their round and run")
            self.directions.require_permitted(query.direction)
            if query.provider not in self.enabled_providers:
                raise ValueError("adaptive query provider must be enabled")
            if not set(query.targeted_gap_ids).issubset(set(self.targeted_gap_ids)):
                raise ValueError("adaptive queries must target persisted round Gap IDs")
        graph_queries = [query for query in self.searches if query.graph_action is not None]
        if graph_queries:
            from collections import Counter

            lane_counts = Counter((query.direction, query.provider) for query in graph_queries)
            providers_by_direction: dict[ResearchDirection, set[DiscoveryProvider]] = {}
            for query in graph_queries:
                providers_by_direction.setdefault(query.direction, set()).add(query.provider)
            if self.round_number == 3 and (
                len(graph_queries) > 3 or any(count > 1 for count in lane_counts.values())
            ):
                raise ValueError(
                    "Round-3 graph actions allow at most three lanes, one per direction/provider"
                )
            if self.round_number == 4:
                if any(count > 2 for count in lane_counts.values()):
                    raise ValueError(
                        "Round-4 graph actions allow at most two per direction/provider lane"
                    )
                if any(len(providers) > 2 for providers in providers_by_direction.values()):
                    raise ValueError(
                        "Round-4 graph actions allow at most two providers per direction"
                    )
        return self


class V2SearchAgentInput(StrictModel):
    """Narrow Search-Agent context; application policy owns every allowed lane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    round_number: Literal[2, 3, 4]
    directions: ResearchDirections
    eligible_providers: tuple[DiscoveryProvider, ...]
    material_gaps: tuple[V2MaterialGap, ...] = Field(min_length=1, max_length=6)
    search_directions: tuple[V2GapSearchDirection, ...] = Field(min_length=1, max_length=6)
    discovered_terms: tuple[NonEmptyStr, ...] = Field(max_length=40)
    previous_queries: tuple[NonEmptyStr, ...] = Field(max_length=48)
    provider_budgets: tuple[V2ProviderSearchBudget, ...]
    maximum_queries: PositiveInt
    policy_identity: Literal[
        "researchassistant-v2-phase-7-adaptive-search-v1",
        "researchassistant-v2-post-phase-13-round-four-v1",
    ] = V2_ADAPTIVE_SEARCH_POLICY_IDENTITY

    @model_validator(mode="after")
    def validate_search_context(self) -> V2SearchAgentInput:
        if self.round_number == 4 and self.policy_identity != V2_POST13_ROUND_FOUR_POLICY_IDENTITY:
            raise ValueError("Round 4 Search Agent input requires the post-Phase-13 policy")
        if self.round_number < 4 and self.policy_identity != V2_ADAPTIVE_SEARCH_POLICY_IDENTITY:
            raise ValueError("Rounds 2 and 3 Search Agent input requires the Phase-7 policy")
        if not self.eligible_providers:
            raise ValueError("adaptive Search Agent requires an eligible provider")
        if len(set(self.eligible_providers)) != len(self.eligible_providers):
            raise ValueError("eligible adaptive providers must be unique")
        budget_by_provider = {item.provider: item for item in self.provider_budgets}
        if set(budget_by_provider) != set(self.eligible_providers):
            raise ValueError("provider budgets must exactly cover eligible providers")
        if any(item.remaining_calls < 1 for item in self.provider_budgets):
            raise ValueError("eligible providers must have remaining search capacity")
        gap_ids = {gap.gap_id for gap in self.material_gaps}
        for gap in self.material_gaps:
            self.directions.require_permitted(gap.direction)
        for item in self.search_directions:
            self.directions.require_permitted(item.direction)
            if item.gap_id not in gap_ids:
                raise ValueError("adaptive search directions must reference persisted gaps")
        return self


# Preserve the historical public class identity for persisted consumers.
SearchDirectionGapReference.__module__ = "researchassistant.contracts.model_research"
V2PlannedSearch.__module__ = "researchassistant.contracts.model_research"
V2InitialResearchPlan.__module__ = "researchassistant.contracts.model_research"
V2SearchRoundPlan.__module__ = "researchassistant.contracts.model_research"
V2InitialPlannerSearchLane.__module__ = "researchassistant.contracts.model_research"
V2InitialPlannerPolicy.__module__ = "researchassistant.contracts.model_research"
V2InitialPlannerInput.__module__ = "researchassistant.contracts.model_research"
V2ScopeInterpretation.__module__ = "researchassistant.contracts.model_research"
V2InitialPlannerSearchResponse.__module__ = "researchassistant.contracts.model_research"
V2InitialPlannerModelOutput.__module__ = "researchassistant.contracts.model_research"
V2RoundOneSearchQuery.__module__ = "researchassistant.contracts.model_research"
V2InitialPlannerOutput.__module__ = "researchassistant.contracts.model_research"
V2ProviderSearchBudget.__module__ = "researchassistant.contracts.model_research"
V2AdaptiveSearchProposal.__module__ = "researchassistant.contracts.model_research"
V2AdaptiveSearchModelOutput.__module__ = "researchassistant.contracts.model_research"
V2AdaptiveSearchQuery.__module__ = "researchassistant.contracts.model_research"
V2AdaptiveRoundPlan.__module__ = "researchassistant.contracts.model_research"
V2SearchAgentInput.__module__ = "researchassistant.contracts.model_research"
