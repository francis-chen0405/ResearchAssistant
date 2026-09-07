"""Typed v2 discovery, research strategy, gaps and queue contracts."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from model_contracts import (
    DiscoveryProvider,
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
    SourceSnapshot,
    StrictModel,
    _validate_aware_datetime,
)
from money import ExactUSD

V2_PIPELINE_IDENTITY = "researchassistant-v2"

V2_POLICY_IDENTITY = "researchassistant-v2-phase-1"

V2_INITIAL_PLANNER_POLICY_IDENTITY = "researchassistant-v2-phase-3-initial-planner-v1"

V2_DISCOVERY_POLICY_IDENTITY = "researchassistant-v2-phase-4-discovery-scout-v1"

V2_ACQUISITION_PROBE_POLICY_IDENTITY = "researchassistant-v2-phase-5-acquisition-probe-v1"

V2_GAP_ANALYSIS_POLICY_IDENTITY = "researchassistant-v2-phase-6-gap-analysis-v1"

V2_ADAPTIVE_SEARCH_POLICY_IDENTITY = "researchassistant-v2-phase-7-adaptive-search-v1"

V2_POST13_ROUND_FOUR_POLICY_IDENTITY = "researchassistant-v2-post-phase-13-round-four-v1"

V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY = "researchassistant-v2-post-phase-13-gap-analysis-v1"

V2_SOURCE_SELECTION_POLICY_IDENTITY = "researchassistant-v2-phase-8-source-selection-v1"

V2_DEEP_ANALYSIS_QUEUE_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-deep-analysis-queue-analyzer-admission-v1"
)

V2_EVIDENCE_ANALYST_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-luna-evidence-analyst-analyzer-admission-v1"
)

V2_EVIDENCE_ADMISSION_POLICY_IDENTITY = "researchassistant-v2-phase-13-analyzer-admission-v1"

V2_REVIEWER_LEDGER_POLICY_IDENTITY = "researchassistant-v2-phase-10-reviewer-ledger-v2"

V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-deep-analysis-backfill-analyzer-admission-v1"
)

V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP = 60_000

V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP = 3


class ResearchDirection(StrEnum):
    SUPPORT = "support"
    CHALLENGE = "challenge"


class ResearchDirections(StrictModel):
    """The complete, independent direction selection for a fresh v2 run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    support_enabled: bool = True
    challenge_enabled: bool = False

    @model_validator(mode="after")
    def validate_at_least_one_enabled(self) -> ResearchDirections:
        if not self.support_enabled and not self.challenge_enabled:
            raise ValueError("at least one research direction must be enabled")
        return self

    @property
    def enabled_directions(self) -> tuple[ResearchDirection, ...]:
        return tuple(
            direction
            for direction, enabled in (
                (ResearchDirection.SUPPORT, self.support_enabled),
                (ResearchDirection.CHALLENGE, self.challenge_enabled),
            )
            if enabled
        )

    def permits(self, direction: ResearchDirection) -> bool:
        return direction in self.enabled_directions

    def require_permitted(self, direction: ResearchDirection) -> None:
        if not self.permits(direction):
            raise ValueError(
                f"disabled research direction cannot appear in a v2 artifact: {direction}"
            )

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class V2PipelineIdentity(StrictModel):
    """Version and policy identity persisted before a v2 artifact is admitted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pipeline_identity: Literal["researchassistant-v2"] = V2_PIPELINE_IDENTITY
    policy_identity: Literal["researchassistant-v2-phase-1"] = V2_POLICY_IDENTITY

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def canonical_v2_artifact_json(artifact: StrictModel) -> str:
    """Return canonical bytes for a strict v2 artifact at a persistence boundary."""
    return json.dumps(artifact.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def v2_payload_fingerprint(payload_json: str) -> str:
    """Return the SHA-256 identity of canonical v2 payload JSON bytes."""
    return sha256(payload_json.encode("utf-8")).hexdigest()


def v2_artifact_fingerprint(artifact: StrictModel) -> str:
    """Return the SHA-256 identity of a canonical v2 artifact."""
    return v2_payload_fingerprint(canonical_v2_artifact_json(artifact))


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
    claim_coverage_focus: tuple[V2ClaimCoverageFocus, ...] = Field(default=(), max_length=3)
    searches: tuple[V2InitialPlannerSearchResponse, ...]

    @field_validator("claim_coverage_focus")
    @classmethod
    def validate_claim_components(
        cls, value: tuple[V2ClaimCoverageFocus, ...]
    ) -> tuple[V2ClaimCoverageFocus, ...]:
        if any(item.kind is not V2ClaimCoverageKind.CLAIM_COMPONENT for item in value):
            raise ValueError(
                "Planner may select claim components but not evidence-audit dimensions"
            )
        if len({item.dimension for item in value}) != len(value):
            raise ValueError("Planner claim-coverage dimensions must be unique")
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
    policy_identity: Literal["researchassistant-v2-phase-3-initial-planner-v1"] = (
        V2_INITIAL_PLANNER_POLICY_IDENTITY
    )
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


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
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=3)
    strategy: NonEmptyStr
    query_text: NonEmptyStr
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
        return self


class DiscoveryMetadataEntry(StrictModel):
    """One provider-owned metadata value retained as non-evidentiary audit data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: NonEmptyStr
    value_json: NonEmptyStr


class DiscoveryProvenance(StrictModel):
    """The immutable provider/query chain that produced a discovery candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: DiscoveryProvider
    query_id: UUID
    query_text: NonEmptyStr
    direction: ResearchDirection
    round_number: PositiveInt
    provider_rank: PositiveInt
    original_url: NonEmptyStr
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=3)


class CrossrefIdentityMetadata(StrictModel):
    """Optional source-identity metadata. It is never evidence or source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doi: NonEmptyStr | None = None
    canonical_title: NonEmptyStr | None = None
    canonical_authors: tuple[NonEmptyStr, ...] = ()
    publication_date: NonEmptyStr | None = None
    verified: bool = False
    failure_code: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_verification(self) -> CrossrefIdentityMetadata:
        if self.verified and self.failure_code is not None:
            raise ValueError("successful Crossref metadata cannot carry a failure code")
        return self


class NormalizedDiscoveryItem(StrictModel):
    """A discovery-only, provider-neutral source candidate before Scout or retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    item_id: UUID
    provider: DiscoveryProvider
    query_id: UUID
    query_text: NonEmptyStr
    direction: ResearchDirection
    round_number: PositiveInt
    provider_rank: PositiveInt
    source_url: NonEmptyStr
    canonical_url: NonEmptyStr
    title: NonEmptyStr | None = None
    snippet: str | None = None
    abstract: str | None = None
    doi: NonEmptyStr | None = None
    authors: tuple[NonEmptyStr, ...] = ()
    publication_date: NonEmptyStr | None = None
    source_type: NonEmptyStr | None = None
    provider_metadata: tuple[DiscoveryMetadataEntry, ...] = ()
    provenance_chain: tuple[DiscoveryProvenance, ...]
    crossref: CrossrefIdentityMetadata | None = None
    discovered_at: datetime

    _discovered_at_is_aware = field_validator("discovered_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_provenance(self) -> NormalizedDiscoveryItem:
        if not self.provenance_chain:
            raise ValueError("discovery provenance chain must not be empty")
        if any(item.direction is not self.direction for item in self.provenance_chain):
            raise ValueError("discovery provenance directions must match the item direction")
        return self


class DiscoveryProviderReference(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: DiscoveryProvider
    item_id: UUID
    provider_rank: PositiveInt


class SourceCluster(StrictModel):
    """A conservative same-source cluster; alternates are retained, never deleted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: UUID
    preferred_url: NonEmptyStr
    canonical_url: NonEmptyStr
    alternate_urls: tuple[NonEmptyStr, ...] = ()
    item_ids: tuple[UUID, ...]
    provider_references: tuple[DiscoveryProviderReference, ...]
    query_references: tuple[UUID, ...]
    metadata_provenance: tuple[DiscoveryProvenance, ...]

    @model_validator(mode="after")
    def validate_alternate_urls(self) -> SourceCluster:
        if self.preferred_url in self.alternate_urls or self.canonical_url in self.alternate_urls:
            raise ValueError("alternate URLs must not repeat the preferred or canonical URL")
        if len(set(self.alternate_urls)) != len(self.alternate_urls):
            raise ValueError("alternate URLs must be unique")
        if not self.item_ids or len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("source clusters require unique member IDs")
        if (
            not self.provider_references
            or not self.query_references
            or not self.metadata_provenance
        ):
            raise ValueError("source clusters require retained discovery provenance")
        return self


class ScoutDecision(StrEnum):
    RETRIEVE = "retrieve"
    MAYBE = "maybe"
    SKIP = "skip"


class ScoutCandidate(StrictModel):
    """Metadata-only Scout input; it intentionally contains no acquired source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: UUID
    direction: ResearchDirection
    title: NonEmptyStr | None = None
    source_url: NonEmptyStr
    snippet: str | None = None
    abstract: str | None = None
    doi: NonEmptyStr | None = None
    authors: tuple[NonEmptyStr, ...] = ()
    publication_date: NonEmptyStr | None = None
    source_type: NonEmptyStr | None = None


class V2ScoutRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    batch_number: PositiveInt
    candidates: tuple[ScoutCandidate, ...] = Field(min_length=1, max_length=30)
    policy_identity: Literal["researchassistant-v2-phase-4-discovery-scout-v1"] = (
        V2_DISCOVERY_POLICY_IDENTITY
    )

    @model_validator(mode="after")
    def validate_candidates(self) -> V2ScoutRequest:
        ids = tuple(item.item_id for item in self.candidates)
        if len(ids) != len(set(ids)):
            raise ValueError("Scout candidate IDs must be unique")
        for item in self.candidates:
            self.directions.require_permitted(item.direction)
        return self


class ScoutItem(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: UUID
    decision: ScoutDecision
    rationale: NonEmptyStr


class ScoutBatch(StrictModel):
    """Strict model-owned response mapped exactly to one application-owned batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    items: tuple[ScoutItem, ...] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_unique_items(self) -> ScoutBatch:
        ids = tuple(item.item_id for item in self.items)
        if len(ids) != len(set(ids)):
            raise ValueError("Scout response IDs must be unique")
        return self


class ScoutBatchAudit(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_number: PositiveInt
    attempted_calls: PositiveInt
    fallback_used: bool = False
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_fallback(self) -> ScoutBatchAudit:
        if self.fallback_used != (self.failure is not None):
            raise ValueError("Scout fallback and failure audit fields must agree")
        return self


class V2DiscoveryScoutOutput(StrictModel):
    """Persistable Phase-4 output preserving discovery, clusters, Scout, and failures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    items: tuple[NormalizedDiscoveryItem, ...]
    clusters: tuple[SourceCluster, ...]
    scout_batches: tuple[ScoutBatch, ...]
    scout_audits: tuple[ScoutBatchAudit, ...]
    policy_identity: Literal["researchassistant-v2-phase-4-discovery-scout-v1"] = (
        V2_DISCOVERY_POLICY_IDENTITY
    )
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_phase_four_output(self) -> V2DiscoveryScoutOutput:
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("normalized discovery IDs must be unique")
        if len({cluster.cluster_id for cluster in self.clusters}) != len(self.clusters):
            raise ValueError("source cluster IDs must be unique")
        for item in self.items:
            self.directions.require_permitted(item.direction)
        if len(self.scout_batches) != len(self.scout_audits):
            raise ValueError("every Scout batch requires one audit record")
        return self


class V2AcquisitionProvider(StrEnum):
    """The bounded acquisition routes available to the fresh-v2 pipeline."""

    WIGOLO = "wigolo"
    FIRECRAWL = "firecrawl"


class V2AcquisitionPolicy(StrictModel):
    """Application-owned acquisition bounds; Firecrawl is always optional."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_clusters: Annotated[int, Field(ge=1, le=25)] = 25
    max_urls_per_cluster: Annotated[int, Field(ge=1, le=10)] = 6
    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 20.0
    allow_firecrawl_fallback: bool = True
    policy_identity: Literal["researchassistant-v2-phase-5-acquisition-probe-v1"] = (
        V2_ACQUISITION_PROBE_POLICY_IDENTITY
    )


class V2AcquisitionAttempt(StrictModel):
    """One auditable, bounded provider attempt. It contains no inferred evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: UUID
    url: NonEmptyStr
    provider: V2AcquisitionProvider
    succeeded: bool
    failure_code: NonEmptyStr | None = None
    failure_message: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> V2AcquisitionAttempt:
        failed = self.failure_code is not None or self.failure_message is not None
        if self.succeeded == failed:
            raise ValueError("acquisition attempt success and failure fields must agree")
        if (self.failure_code is None) != (self.failure_message is None):
            raise ValueError("acquisition failure code and message must be paired")
        return self


class V2AcquiredSource(StrictModel):
    """A successful immutable snapshot bound to its conservative source cluster."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: UUID
    direction: ResearchDirection
    snapshot: SourceSnapshot
    provider: V2AcquisitionProvider


class V2ProbePassage(StrictModel):
    """Exact deterministic snapshot window for later analysis, never a factual claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: NonEmptyStr
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_cluster_id: UUID
    start_char: NonNegativeInt
    end_char: PositiveInt
    text: NonEmptyStr
    score: NonNegativeInt
    signals: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_exact_span(self) -> V2ProbePassage:
        if self.start_char >= self.end_char or self.end_char - self.start_char != len(self.text):
            raise ValueError("Probe passage offsets must exactly match passage text")
        return self


class V2ProbeResult(StrictModel):
    """Deterministic Probe result tied to one immutable snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    succeeded: bool
    passages: tuple[V2ProbePassage, ...] = Field(default=(), max_length=5)
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_probe_shape(self) -> V2ProbeResult:
        if self.succeeded:
            if self.failure is not None:
                raise ValueError("successful Probe results cannot carry a failure")
        elif self.passages or self.failure is None:
            raise ValueError("failed Probe results require a failure and no passages")
        if any(
            passage.snapshot_id != self.snapshot_id
            or passage.snapshot_sha256 != self.snapshot_sha256
            or passage.source_cluster_id != self.cluster_id
            for passage in self.passages
        ):
            raise ValueError("Probe passages must match their snapshot and source cluster")
        return self


class V2SurvivingSource(StrictModel):
    """A source retained for later Gap Analysis; it is not a recommendation or Ledger item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: UUID
    direction: ResearchDirection
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    passage_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=5)


class V2AcquisitionProbeOutput(StrictModel):
    """Immutable Phase-5 handoff: acquisition audit, snapshots, Probe, and all survivors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    acquisitions: tuple[V2AcquiredSource, ...]
    attempts: tuple[V2AcquisitionAttempt, ...]
    probes: tuple[V2ProbeResult, ...]
    survivors: tuple[V2SurvivingSource, ...]
    policy_identity: Literal["researchassistant-v2-phase-5-acquisition-probe-v1"] = (
        V2_ACQUISITION_PROBE_POLICY_IDENTITY
    )
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_acquisition_probe_output(self) -> V2AcquisitionProbeOutput:
        snapshot_ids = {source.snapshot.snapshot_id for source in self.acquisitions}
        if len(snapshot_ids) != len(self.acquisitions):
            raise ValueError("acquired snapshots must be unique")
        probe_by_snapshot = {probe.snapshot_id: probe for probe in self.probes}
        if len(probe_by_snapshot) != len(self.probes):
            raise ValueError("each acquired snapshot requires one Probe result")
        if set(probe_by_snapshot) != snapshot_ids:
            raise ValueError("Probe results must cover exactly the acquired snapshots")
        for source in self.acquisitions:
            self.directions.require_permitted(source.direction)
            if source.snapshot.run_id != self.run_id:
                raise ValueError("acquired snapshot run_id must match output run_id")
        passage_ids = {passage.passage_id for probe in self.probes for passage in probe.passages}
        if len(passage_ids) != sum(len(probe.passages) for probe in self.probes):
            raise ValueError("Probe passage IDs must be unique")
        for survivor in self.survivors:
            self.directions.require_permitted(survivor.direction)
            probe = probe_by_snapshot.get(survivor.snapshot_id)
            if probe is None or not probe.succeeded:
                raise ValueError("survivors require a successful Probe result")
            if survivor.snapshot_sha256 != probe.snapshot_sha256:
                raise ValueError("survivor snapshot hash must match Probe")
            if not set(survivor.passage_ids).issubset(
                {passage.passage_id for passage in probe.passages}
            ):
                raise ValueError("survivors may reference only their own Probe passages")
        return self


class V2GapBudgetState(StrictModel):
    """The bounded, remaining budget view supplied to Gap Analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls_remaining: NonNegativeInt
    tokens_remaining: NonNegativeInt | None = None
    cost_remaining_usd: ExactUSD | None = None


class V2GapAttemptedQuery(StrictModel):
    """One already-executed Round-1 query, never a proposal for a later round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: UUID
    direction: ResearchDirection
    provider: DiscoveryProvider
    strategy: NonEmptyStr
    query_text: NonEmptyStr
    round_number: Literal[1, 2, 3] = 1


class V2GapSurvivingSourceMetadata(StrictModel):
    """Compact source identity available to research strategy, without source documents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_cluster_id: UUID
    direction: ResearchDirection
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_url: NonEmptyStr
    title: NonEmptyStr | None = None
    source_family_id: NonEmptyStr
    round_number: Literal[1, 2, 3] = 1


class V2GapProbePassage(StrictModel):
    """A bounded Probe excerpt for strategy only, never a quotation or Ledger input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: NonEmptyStr
    source_cluster_id: UUID
    direction: ResearchDirection
    text: NonEmptyStr = Field(max_length=1200)
    truncated_for_gap_analysis: bool = False
    round_number: Literal[1, 2, 3] = 1


class V2GapSourceFamily(StrictModel):
    """Conservative cluster-family information used to avoid duplicate research."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    family_id: NonEmptyStr
    direction: ResearchDirection
    source_cluster_ids: tuple[UUID, ...] = Field(min_length=1, max_length=25)
    discovery_providers: tuple[DiscoveryProvider, ...] = Field(min_length=1, max_length=6)
    round_number: Literal[1, 2, 3] = 1
    round_numbers: tuple[Literal[1, 2, 3], ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def validate_round_provenance(self) -> V2GapSourceFamily:
        if self.round_numbers and self.round_number not in self.round_numbers:
            raise ValueError("source-family primary round must appear in its round provenance")
        if len(self.round_numbers) != len(set(self.round_numbers)):
            raise ValueError("source-family round provenance must be unique")
        return self


class V2GapDuplicatePattern(StrictModel):
    """Observed duplicate-family pattern, not a conclusion about source quality."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_cluster_id: UUID
    direction: ResearchDirection
    duplicate_discovery_count: PositiveInt
    pattern: NonEmptyStr
    round_number: Literal[1, 2, 3] = 1


class V2GapAcquisitionFailure(StrictModel):
    """A compact failed-acquisition audit record for research strategy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_cluster_id: UUID
    direction: ResearchDirection
    provider: V2AcquisitionProvider
    failure_code: NonEmptyStr
    round_number: Literal[1, 2, 3] = 1


class V2GapSearchDirection(StrictModel):
    """A specific, typed possible later-search direction tied to one material gap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    missing_evidence: NonEmptyStr
    search_focus: NonEmptyStr
    claim_dimension: V2ClaimCoverageDimension | None = None
    resolving_evidence_kind: NonEmptyStr | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_claim_coverage_link(self) -> V2GapSearchDirection:
        if (self.claim_dimension is None) != (self.resolving_evidence_kind is None):
            raise ValueError(
                "claim-linked search directions require both a dimension and resolving evidence"
            )
        return self


class V2ClaimCoverageDimension(StrEnum):
    EFFECT_OR_ASSOCIATION = "effect_or_association"
    POPULATION_AND_SETTING = "population_and_setting"
    MECHANISM_OR_PATHWAY = "mechanism_or_pathway"
    LIMITATIONS_AND_BOUNDARIES = "limitations_and_boundaries"
    COUNTEREVIDENCE_OR_ALTERNATIVES = "counterevidence_or_alternatives"
    REPLICATION_OR_GENERALIZABILITY = "replication_or_generalizability"


class V2ClaimCoverageKind(StrEnum):
    """Whether a coverage dimension describes the claim or audits its evidence boundary."""

    CLAIM_COMPONENT = "claim_component"
    EVIDENCE_AUDIT = "evidence_audit"


class V2ClaimCoverageState(StrEnum):
    COVERED = "covered"
    PARTIAL = "partial"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"


class V2ClaimCoverageFocus(StrictModel):
    """An application-derived exact-claim component that must be assessed after Round 3."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: V2ClaimCoverageDimension
    claim_component: NonEmptyStr = Field(max_length=500)
    kind: V2ClaimCoverageKind | None = None
    searchable: bool = True
    unavailable_reason: NonEmptyStr | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_availability(self) -> V2ClaimCoverageFocus:
        expected_kind = (
            V2ClaimCoverageKind.CLAIM_COMPONENT
            if self.dimension
            in {
                V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
                V2ClaimCoverageDimension.POPULATION_AND_SETTING,
                V2ClaimCoverageDimension.MECHANISM_OR_PATHWAY,
            }
            else V2ClaimCoverageKind.EVIDENCE_AUDIT
        )
        if self.kind is not None and self.kind is not expected_kind:
            raise ValueError("claim-coverage dimension must use its defined kind")
        if self.searchable == (self.unavailable_reason is not None):
            raise ValueError("claim-coverage availability and unavailable reason must agree")
        return self


class V2GapIdentity(StrictModel):
    """Typed identity fields used to validate Gap continuity across rounds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    claim_dimension: V2ClaimCoverageDimension | None = None
    unsupported_claim_component: NonEmptyStr | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_claim_component(self) -> V2GapIdentity:
        if (self.claim_dimension is None) != (self.unsupported_claim_component is None):
            raise ValueError("Gap identities require a dimension and component together")
        return self


class V2ClaimCoverageSpecification(StrictModel):
    """Application-owned, explicit dimensions for one post-Round-3 coverage audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    focus: tuple[V2ClaimCoverageFocus, ...] = Field(min_length=1, max_length=6)

    @field_validator("focus")
    @classmethod
    def validate_unique_dimensions(
        cls, value: tuple[V2ClaimCoverageFocus, ...]
    ) -> tuple[V2ClaimCoverageFocus, ...]:
        if len({item.dimension for item in value}) != len(value):
            raise ValueError("claim-coverage specification dimensions must be unique")
        return value


class V2ClaimCoverageAssessment(V2ClaimCoverageFocus):
    """Luna's bounded coverage assessment; it cannot decide whether the claim is true."""

    coverage_state: V2ClaimCoverageState
    evidence_summary: NonEmptyStr = Field(max_length=1000)


class V2MaterialGap(StrictModel):
    """One specific missing-evidence condition, in an enabled research direction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    missing_evidence: NonEmptyStr
    rationale: NonEmptyStr
    claim_dimension: V2ClaimCoverageDimension | None = None
    unsupported_claim_component: NonEmptyStr | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_claim_component(self) -> V2MaterialGap:
        if (self.claim_dimension is None) != (self.unsupported_claim_component is None):
            raise ValueError("claim-linked material gaps require a dimension and exact component")
        return self

    @property
    def continuity_identity(self) -> V2GapIdentity:
        return V2GapIdentity(
            gap_id=self.gap_id,
            direction=self.direction,
            claim_dimension=self.claim_dimension,
            unsupported_claim_component=self.unsupported_claim_component,
        )


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


class V2GapAnalysisInput(StrictModel):
    """Strict, bounded Round-1 strategy input; acquired documents are intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    completed_round: Literal[1, 2, 3] = 1
    attempted_queries: tuple[V2GapAttemptedQuery, ...] = Field(max_length=48)
    surviving_sources: tuple[V2GapSurvivingSourceMetadata, ...] = Field(max_length=75)
    probe_passages: tuple[V2GapProbePassage, ...] = Field(max_length=40)
    source_families: tuple[V2GapSourceFamily, ...] = Field(max_length=75)
    discovered_terms: tuple[NonEmptyStr, ...] = Field(max_length=40)
    duplicate_patterns: tuple[V2GapDuplicatePattern, ...] = Field(max_length=25)
    acquisition_failures: tuple[V2GapAcquisitionFailure, ...] = Field(max_length=150)
    previous_gaps: tuple[V2MaterialGap, ...] = Field(max_length=6)
    claim_coverage_focus: tuple[V2ClaimCoverageFocus, ...] = Field(default=(), max_length=6)
    claim_coverage_specification: V2ClaimCoverageSpecification | None = None
    remaining_budget: V2GapBudgetState
    policy_identity: Literal[
        "researchassistant-v2-phase-6-gap-analysis-v1",
        "researchassistant-v2-post-phase-13-gap-analysis-v1",
    ] = V2_GAP_ANALYSIS_POLICY_IDENTITY

    @model_validator(mode="after")
    def validate_strategy_scope(self) -> V2GapAnalysisInput:
        for item in (
            *self.attempted_queries,
            *self.surviving_sources,
            *self.probe_passages,
            *self.source_families,
            *self.duplicate_patterns,
            *self.acquisition_failures,
            *self.previous_gaps,
        ):
            self.directions.require_permitted(item.direction)
        source_ids = {source.source_cluster_id for source in self.surviving_sources}
        if any(passage.source_cluster_id not in source_ids for passage in self.probe_passages):
            raise ValueError("Gap Analysis passages must belong to surviving sources")
        if len({item.dimension for item in self.claim_coverage_focus}) != len(
            self.claim_coverage_focus
        ):
            raise ValueError("claim-coverage dimensions must be unique")
        if self.policy_identity == V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY and (
            not self.claim_coverage_focus
            or self.claim_coverage_specification is None
            or self.claim_coverage_focus != self.claim_coverage_specification.focus
        ):
            raise ValueError("post-Round-3 Gap Analysis requires one claim-coverage specification")
        return self


class V2GapAnalysisModelOutput(StrictModel):
    """Narrow Luna response before application-owned run identity is attached."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage_summary: NonEmptyStr = Field(max_length=2000)
    claim_coverage_map: tuple[V2ClaimCoverageAssessment, ...] = Field(default=(), max_length=6)
    material_gaps: tuple[V2MaterialGap, ...] = Field(max_length=6)
    continue_research: bool
    stop_reason: NonEmptyStr | None = Field(default=None, max_length=1000)
    new_search_directions: tuple[V2GapSearchDirection, ...] = Field(max_length=6)
    discovered_terms: tuple[NonEmptyStr, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_strategy_decision(self) -> V2GapAnalysisModelOutput:
        gap_ids = tuple(gap.gap_id for gap in self.material_gaps)
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Gap Analysis gap IDs must be unique")
        if any(gap_ids.count(item.gap_id) > 3 for item in self.material_gaps):
            raise ValueError("Gap Analysis has too many gaps with one ID")
        if self.continue_research:
            if (
                not self.material_gaps
                or not self.new_search_directions
                or self.stop_reason is not None
            ):
                raise ValueError(
                    "continuing research requires gaps and search directions without a stop reason"
                )
        elif self.material_gaps or self.new_search_directions or self.stop_reason is None:
            raise ValueError("stopping research requires a stop reason and no invented gaps")
        if any(item.gap_id not in gap_ids for item in self.new_search_directions):
            raise ValueError("new search directions must reference a material gap")
        return self


class V2GapAnalysisResult(V2GapAnalysisModelOutput):
    """Validated Gap Analysis decision bound to exactly one completed Round 1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    analyzed_at: datetime

    _analyzed_at_is_aware = field_validator("analyzed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_gap_directions(self) -> V2GapAnalysisResult:
        for gap in self.material_gaps:
            self.directions.require_permitted(gap.direction)
        for search in self.new_search_directions:
            self.directions.require_permitted(search.direction)
            matching_gap = next(gap for gap in self.material_gaps if gap.gap_id == search.gap_id)
            if matching_gap.direction is not search.direction:
                raise ValueError("new search direction must match its gap direction")
        per_direction = {direction: 0 for direction in self.directions.enabled_directions}
        for gap in self.material_gaps:
            per_direction[gap.direction] += 1
        if any(count > 3 for count in per_direction.values()):
            raise ValueError("Gap Analysis permits at most three gaps per enabled direction")
        return self


class V2GapAnalysisState(StrEnum):
    COMPLETED = "completed"
    DEGRADED = "degraded"


class V2GapReservation(StrictModel):
    """Secret-free conservative reservation recorded for a Luna strategy attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: PositiveInt
    output_tokens: PositiveInt
    reserved_tokens: PositiveInt
    reserved_cost_usd: ExactUSD

    @model_validator(mode="after")
    def validate_total(self) -> V2GapReservation:
        if self.reserved_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("Gap Analysis reserved tokens must equal input plus output tokens")
        return self


class V2GapAnalysisAttempt(StrictModel):
    """One bounded Luna attempt, including its conservative reservation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: PositiveInt
    reservation: V2GapReservation
    succeeded: bool
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> V2GapAnalysisAttempt:
        if self.succeeded == (self.failure is not None):
            raise ValueError("Gap Analysis attempt success and failure must agree")
        return self


class V2GapAnalysisOutput(StrictModel):
    """Persisted Phase-6 state. Degraded output always stops adaptive continuation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input: V2GapAnalysisInput
    state: V2GapAnalysisState
    result: V2GapAnalysisResult | None = None
    attempts: tuple[V2GapAnalysisAttempt, ...] = Field(max_length=2)
    stop_adaptive_continuation: bool
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_output(self) -> V2GapAnalysisOutput:
        if self.input.run_id != self.run_id:
            raise ValueError("Gap Analysis input run_id must match output")
        if self.result is not None and self.result.run_id != self.run_id:
            raise ValueError("Gap Analysis result run_id must match output")
        if self.result is not None:
            validate_v2_gap_identity_continuity(
                self.input.previous_gaps,
                self.result.material_gaps,
            )
        if self.state is V2GapAnalysisState.COMPLETED:
            if self.result is None or self.stop_adaptive_continuation != (
                not self.result.continue_research
            ):
                raise ValueError("completed Gap Analysis state must agree with its decision")
            if self.input.policy_identity == V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY:
                expected_dimensions = tuple(
                    item.dimension for item in self.input.claim_coverage_focus
                )
                actual_dimensions = tuple(item.dimension for item in self.result.claim_coverage_map)
                if actual_dimensions != expected_dimensions:
                    raise ValueError(
                        "post-Round-3 coverage map must exactly cover application focus dimensions"
                    )
                coverage_by_dimension = {
                    item.dimension: item for item in self.result.claim_coverage_map
                }
                focus_by_dimension = {
                    item.dimension: item for item in self.input.claim_coverage_focus
                }
                for assessment in self.result.claim_coverage_map:
                    focus = focus_by_dimension[assessment.dimension]
                    if (
                        assessment.claim_component != focus.claim_component
                        or assessment.kind != focus.kind
                        or assessment.searchable != focus.searchable
                        or assessment.unavailable_reason != focus.unavailable_reason
                    ):
                        raise ValueError(
                            "post-Round-3 coverage assessments must exactly match the specification"
                        )
                    if (not focus.searchable) != (
                        assessment.coverage_state is V2ClaimCoverageState.UNAVAILABLE
                    ):
                        raise ValueError(
                            "unsearchable coverage dimensions must be disclosed as unavailable"
                        )
                for gap in self.result.material_gaps:
                    if (
                        gap.claim_dimension is None
                        or gap.unsupported_claim_component is None
                        or gap.claim_dimension not in focus_by_dimension
                        or gap.unsupported_claim_component
                        != focus_by_dimension[gap.claim_dimension].claim_component
                        or coverage_by_dimension[gap.claim_dimension].coverage_state
                        not in {
                            V2ClaimCoverageState.PARTIAL,
                            V2ClaimCoverageState.MISSING,
                            V2ClaimCoverageState.CONFLICTING,
                        }
                    ):
                        raise ValueError(
                            "post-Round-3 gaps must name an unsupported claim component"
                        )
                for direction in self.result.new_search_directions:
                    if (
                        direction.claim_dimension is None
                        or direction.resolving_evidence_kind is None
                    ):
                        raise ValueError(
                            "post-Round-3 search directions must name the claim component "
                            "and resolving evidence"
                        )
                    related_gap = next(
                        (
                            gap
                            for gap in self.result.material_gaps
                            if gap.gap_id == direction.gap_id
                        ),
                        None,
                    )
                    if (
                        related_gap is None
                        or related_gap.claim_dimension != direction.claim_dimension
                    ):
                        raise ValueError(
                            "post-Round-3 search directions must resolve their matching claim gap"
                        )
        elif self.result is not None or not self.stop_adaptive_continuation:
            raise ValueError(
                "degraded Gap Analysis must not invent a result and must stop continuation"
            )
        return self


class V2RoundFourDecisionCode(StrEnum):
    """Stable fail-closed outcomes for the one permitted post-Round-3 continuation."""

    AUTHORIZED = "authorized"
    NO_MATERIAL_GAPS = "no_material_gaps"
    GAP_ANALYSIS_UNUSABLE = "gap_analysis_unusable"
    NO_NOVEL_QUERY = "no_novel_query"
    NO_ELIGIBLE_PROVIDER = "no_eligible_provider"
    DUPLICATE_HEAVY = "duplicate_heavy"
    UNPRODUCTIVE = "unproductive"
    INSUFFICIENT_RESERVATION = "insufficient_reservation"
    CANCELLED = "cancelled"
    TERMINAL_FAILURE = "terminal_failure"


class V2RoundFourTerminalOutcome(StrictModel):
    """Append-only terminal outcome after an already persisted Round-4 authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    reason_code: Literal[V2RoundFourDecisionCode.TERMINAL_FAILURE]
    failed_stage: NonEmptyStr
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)


class V2RoundFourReservation(StrictModel):
    """Auditable conservative envelope that keeps optional work out of downstream reserve."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protected_downstream_calls: NonNegativeInt
    protected_downstream_tokens: NonNegativeInt
    protected_downstream_cost_usd: ExactUSD
    gap_attempt_calls: NonNegativeInt
    search_agent_calls: NonNegativeInt
    scout_calls: NonNegativeInt
    provider_search_calls: NonNegativeInt
    acquisition_cluster_capacity: NonNegativeInt
    optional_calls: NonNegativeInt
    optional_tokens: NonNegativeInt
    optional_cost_usd: ExactUSD
    available_calls: NonNegativeInt
    available_tokens: NonNegativeInt | None = None
    available_cost_usd: ExactUSD | None = None
    consumed_gap_attempt_calls: NonNegativeInt = 0
    future_optional_calls: NonNegativeInt = 0
    future_optional_tokens: NonNegativeInt = 0
    future_optional_cost_usd: ExactUSD = Decimal("0")
    post_gap_available_calls: NonNegativeInt | None = None
    post_gap_available_tokens: NonNegativeInt | None = None
    post_gap_available_cost_usd: ExactUSD | None = None

    @model_validator(mode="after")
    def validate_reservation(self) -> V2RoundFourReservation:
        if self.optional_calls != (
            self.gap_attempt_calls + self.search_agent_calls + self.scout_calls
        ):
            raise ValueError("Round-4 optional calls must equal its LLM workload components")
        if self.consumed_gap_attempt_calls > self.gap_attempt_calls:
            raise ValueError("consumed Gap attempts cannot exceed the reserved Gap attempts")
        if self.post_gap_available_calls is not None and self.future_optional_calls != (
            self.search_agent_calls + self.scout_calls
        ):
            raise ValueError("future Round-4 calls must exclude consumed Gap Analysis attempts")
        if self.available_calls < self.protected_downstream_calls + self.optional_calls:
            raise ValueError("Round-4 reservation exceeds available physical-call capacity")
        if (
            self.available_tokens is not None
            and self.available_tokens < self.protected_downstream_tokens + self.optional_tokens
        ):
            raise ValueError("Round-4 reservation exceeds available token capacity")
        if (
            self.available_cost_usd is not None
            and self.available_cost_usd
            < self.protected_downstream_cost_usd + self.optional_cost_usd
        ):
            raise ValueError("Round-4 reservation exceeds available cost capacity")
        post_gap_values = (
            self.post_gap_available_calls,
            self.post_gap_available_tokens,
            self.post_gap_available_cost_usd,
        )
        if (
            any(value is not None for value in post_gap_values)
            and self.post_gap_available_calls is None
        ):
            raise ValueError("post-Gap reservation requires an actual call snapshot")
        if (
            self.post_gap_available_calls is not None
            and self.post_gap_available_calls
            < self.protected_downstream_calls + self.future_optional_calls
        ):
            raise ValueError("post-Gap reservation exceeds available physical-call capacity")
        if (
            self.post_gap_available_tokens is not None
            and self.post_gap_available_tokens
            < self.protected_downstream_tokens + self.future_optional_tokens
        ):
            raise ValueError("post-Gap reservation exceeds available token capacity")
        if (
            self.post_gap_available_cost_usd is not None
            and self.post_gap_available_cost_usd
            < self.protected_downstream_cost_usd + self.future_optional_cost_usd
        ):
            raise ValueError("post-Gap reservation exceeds available cost capacity")
        return self


class V2RoundFourGovernorDecision(StrictModel):
    """Application-owned authorization for the one bounded fourth research round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    authorized: bool
    authorization_kind: Literal["preauthorization"] = "preauthorization"
    reason_code: V2RoundFourDecisionCode
    explanation: NonEmptyStr
    reservation: V2RoundFourReservation | None = None
    policy_identity: Literal["researchassistant-v2-post-phase-13-round-four-v1"] = (
        V2_POST13_ROUND_FOUR_POLICY_IDENTITY
    )
    decided_at: datetime

    _decided_at_is_aware = field_validator("decided_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_decision(self) -> V2RoundFourGovernorDecision:
        if self.authorized != (self.reason_code is V2RoundFourDecisionCode.AUTHORIZED):
            raise ValueError("Round-4 authorization must agree with its reason code")
        if self.authorized != (self.reservation is not None):
            raise ValueError("only an authorized Round 4 may carry a reservation")
        return self


class V2GapCoverageState(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    COVERED = "covered"
    UNRESOLVED = "unresolved"
    UNAVAILABLE = "unavailable"


class V2GapCoverageRecord(StrictModel):
    """One post-Round-3 gap and the exact analyzer-admitted evidence that can cover it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap: V2MaterialGap
    state: V2GapCoverageState
    source_id: UUID | None = None
    query_id: UUID | None = None
    ledger_claim_id: UUID | None = None

    @model_validator(mode="after")
    def validate_coverage(self) -> V2GapCoverageRecord:
        evidence_ids = (self.source_id, self.query_id, self.ledger_claim_id)
        if self.state is V2GapCoverageState.COVERED:
            if any(value is None for value in evidence_ids):
                raise ValueError("covered gaps require source, query, and admitted evidence IDs")
        elif any(value is not None for value in evidence_ids):
            raise ValueError("only covered gaps may carry evidence linkage")
        return self


class V2GapCoverageReconciliation(StrictModel):
    """Deterministic post-admission reconciliation; it never makes another model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    post_round_three_gap_artifact_key: NonEmptyStr
    round_four_attempted: bool
    records: tuple[V2GapCoverageRecord, ...]
    claim_coverage_map: tuple[V2ClaimCoverageAssessment, ...] = Field(default=(), max_length=6)
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_records(self) -> V2GapCoverageReconciliation:
        gap_ids = tuple(item.gap.gap_id for item in self.records)
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Gap reconciliation must retain each post-Round-3 gap once")
        if not self.round_four_attempted and any(
            item.state is V2GapCoverageState.COVERED for item in self.records
        ):
            raise ValueError("unattempted Round 4 cannot cover a Gap")
        return self


class V2SourceSelectionProbePassage(StrictModel):
    """Exact Probe text supplied for prioritization, not approved evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: NonEmptyStr
    text: NonEmptyStr = Field(max_length=1200)
    score: NonNegativeInt


class V2SourceSelectionSearchProvenance(StrictModel):
    """The round/query lane through which a survivor was discovered."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: UUID
    provider: DiscoveryProvider
    round_number: Annotated[int, Field(ge=1, le=4)]
    query_text: NonEmptyStr
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(max_length=6)


class V2SourceSelectionGap(StrictModel):
    """Material Gap history available to source prioritization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    missing_evidence: NonEmptyStr
    claim_dimension: V2ClaimCoverageDimension | None = None
    unsupported_claim_component: NonEmptyStr | None = Field(default=None, max_length=500)
    assessed_after_round: Annotated[int, Field(ge=1, le=3)] = 1

    @model_validator(mode="after")
    def validate_claim_component(self) -> V2SourceSelectionGap:
        if (self.claim_dimension is None) != (self.unsupported_claim_component is None):
            raise ValueError("claim-linked source-selection Gaps require a dimension and component")
        return self

    @property
    def continuity_identity(self) -> V2GapIdentity:
        return V2GapIdentity(
            gap_id=self.gap_id,
            direction=self.direction,
            claim_dimension=self.claim_dimension,
            unsupported_claim_component=self.unsupported_claim_component,
        )


class V2GapIdentityCollisionError(ValueError):
    """Gap identity fields conflict or duplicate one semantic gap under another ID."""


def _record_v2_gap_identity(
    identities: dict[str, V2GapIdentity],
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str],
    identity: V2GapIdentity,
    *,
    scope: str,
) -> None:
    existing = identities.get(identity.gap_id)
    if existing is not None and (
        existing.direction is not identity.direction
        or (
            existing.claim_dimension is not None
            and identity.claim_dimension is not None
            and (
                existing.claim_dimension is not identity.claim_dimension
                or existing.unsupported_claim_component != identity.unsupported_claim_component
            )
        )
    ):
        raise V2GapIdentityCollisionError(
            f"{scope} Gap ID {identity.gap_id!r} has conflicting semantic identity"
        )
    if identity.claim_dimension is not None:
        semantic_key = (
            identity.direction,
            identity.claim_dimension,
            identity.unsupported_claim_component,
        )
        existing_gap_id = semantic_identities.get(semantic_key)
        if existing_gap_id is not None and existing_gap_id != identity.gap_id:
            raise V2GapIdentityCollisionError(
                f"{scope} semantic Gap identity is assigned to both "
                f"{existing_gap_id!r} and {identity.gap_id!r}"
            )
        semantic_identities[semantic_key] = identity.gap_id
    if existing is None:
        identities[identity.gap_id] = identity
        return
    if existing.claim_dimension is None and identity.claim_dimension is not None:
        identities[identity.gap_id] = identity


def validate_v2_gap_identity_continuity(
    previous_gaps: tuple[V2MaterialGap, ...],
    current_gaps: tuple[V2MaterialGap, ...],
) -> None:
    """Reject incompatible reused IDs while allowing legacy unknown claim identity."""
    identities: dict[str, V2GapIdentity] = {}
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str] = {}
    for gap in (*previous_gaps, *current_gaps):
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            gap.continuity_identity,
            scope="Gap Analysis",
        )


def validate_v2_source_selection_gap_history(
    gap_history: tuple[V2SourceSelectionGap, ...],
) -> None:
    """Reject incompatible repeated IDs in cross-round source-selection history."""
    identities: dict[str, V2GapIdentity] = {}
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str] = {}
    for gap in gap_history:
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            gap.continuity_identity,
            scope="source-selection history",
        )


def validate_v2_gap_history_against_material_gaps(
    material_gaps: tuple[V2MaterialGap, ...],
    gap_history: tuple[V2SourceSelectionGap, ...],
) -> None:
    """Ensure current reconciliation gaps retain the history's explicit identity fields."""
    identities: dict[str, V2GapIdentity] = {}
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str] = {}
    for history_gap in gap_history:
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            history_gap.continuity_identity,
            scope="source-selection history",
        )
    for gap in material_gaps:
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            gap.continuity_identity,
            scope="reconciliation",
        )


class V2SourceSelectionCandidate(StrictModel):
    """One retained survivor and its bounded non-evidentiary selection context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    source_family_id: NonEmptyStr
    research_round: Annotated[int, Field(ge=1, le=4)]
    source_url: NonEmptyStr
    title: NonEmptyStr | None = None
    source_type: NonEmptyStr | None = None
    doi: NonEmptyStr | None = None
    authors: tuple[NonEmptyStr, ...] = ()
    publication_date: NonEmptyStr | None = None
    discovery_providers: tuple[DiscoveryProvider, ...] = Field(min_length=1, max_length=6)
    probe_passages: tuple[V2SourceSelectionProbePassage, ...] = Field(min_length=1, max_length=5)
    search_provenance: tuple[V2SourceSelectionSearchProvenance, ...] = Field(
        min_length=1, max_length=20
    )
    snapshot_word_count: PositiveInt
    deep_analysis_input_tokens: PositiveInt

    @model_validator(mode="after")
    def validate_candidate_provenance(self) -> V2SourceSelectionCandidate:
        if len(set(self.discovery_providers)) != len(self.discovery_providers):
            raise ValueError("source-selection discovery providers must be unique")
        if any(item.round_number > self.research_round for item in self.search_provenance):
            raise ValueError("source-selection provenance cannot postdate survivor discovery")
        return self


class V2SourceSelectionInput(StrictModel):
    """Complete useful survivor pool supplied to Final Source Selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    survivors: tuple[V2SourceSelectionCandidate, ...] = Field(min_length=1, max_length=75)
    gap_history: tuple[V2SourceSelectionGap, ...] = Field(max_length=18)
    policy_identity: Literal["researchassistant-v2-phase-8-source-selection-v1"] = (
        V2_SOURCE_SELECTION_POLICY_IDENTITY
    )

    @model_validator(mode="after")
    def validate_complete_pool(self) -> V2SourceSelectionInput:
        source_ids = tuple(item.source_id for item in self.survivors)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source-selection survivor IDs must be unique")
        gap_keys = tuple((item.assessed_after_round, item.gap_id) for item in self.gap_history)
        if len(gap_keys) != len(set(gap_keys)):
            raise ValueError("source-selection Gap history entries must be unique per round")
        validate_v2_source_selection_gap_history(self.gap_history)
        for item in (*self.survivors, *self.gap_history):
            self.directions.require_permitted(item.direction)
        return self


class V2SourceSelectionRecommendation(StrictModel):
    """Model recommendation only; it conveys no evidence or Ledger approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    rationale: NonEmptyStr = Field(max_length=1000)
    gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=6)


class V2SourceSelectionModelOutput(StrictModel):
    """Narrow MiMo response before survivor IDs are checked by the application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendations: tuple[V2SourceSelectionRecommendation, ...] = Field(
        min_length=1, max_length=20
    )

    @model_validator(mode="after")
    def validate_unique_recommendations(self) -> V2SourceSelectionModelOutput:
        source_ids = tuple(item.source_id for item in self.recommendations)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("recommended source IDs must be unique")
        return self


class V2DeepAnalysisBudget(StrictModel):
    """Remaining run budget immediately before Final Source Selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    physical_call_ceiling: Annotated[int, Field(ge=1, le=160)] = 160
    physical_calls_used: Annotated[int, Field(ge=0, le=160)]
    tokens_remaining: NonNegativeInt
    cost_remaining_usd: ExactUSD


class V2DeepAnalysisBudgetReason(StrEnum):
    PHYSICAL_CALL_CEILING = "physical_call_ceiling"
    TOKEN_RESERVE = "token_reserve"
    COST_RESERVE = "cost_reserve"
    BACKFILL_REPLACED = "backfill_replaced"


class V2DeepAnalysisSourceStatus(StrictModel):
    """Persistent recommendation and queue status for exactly one survivor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    recommended: bool
    recommendation_rank: PositiveInt | None = None
    selection_rationale: NonEmptyStr | None = None
    gap_ids: tuple[NonEmptyStr, ...] = ()
    queued_for_deep_analysis: bool
    queue_rank: PositiveInt | None = None
    budget_prevented_reason: V2DeepAnalysisBudgetReason | None = None

    @model_validator(mode="after")
    def validate_status(self) -> V2DeepAnalysisSourceStatus:
        if self.recommended != (self.recommendation_rank is not None):
            raise ValueError("recommendation state and rank must agree")
        if self.recommended != (self.selection_rationale is not None):
            raise ValueError("recommended sources require a selection rationale")
        if self.queued_for_deep_analysis != (self.queue_rank is not None):
            raise ValueError("deep-analysis queue state and rank must agree")
        if self.queued_for_deep_analysis == (self.budget_prevented_reason is not None):
            raise ValueError("only non-queued survivors may have a budget-prevented reason")
        return self


class V2DeepAnalysisTokenReservation(StrictModel):
    """Cumulative reserve if the deterministic queue prefix includes this source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    queue_size: PositiveInt
    cumulative_reserved_tokens: PositiveInt
    cumulative_reserved_cost_usd: ExactUSD


class V2DeepAnalysisQueuePlan(StrictModel):
    """Safe bounded queue and representative worst-case workload math."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    queued_source_ids: tuple[UUID, ...]
    source_statuses: tuple[V2DeepAnalysisSourceStatus, ...]
    queue_capacity: NonNegativeInt
    # Legacy Phase-8 plans used two attempts for every logical operation. Fresh
    # Phase-13 work has one Analyst operation; extraction keeps its own retry cap.
    attempts_per_logical_operation: Literal[1, 2] = 1
    extractor_attempts_per_source: Literal[2] = 2
    extractor_logical_calls_per_source: Literal[1] = 1
    analyst_logical_calls_per_source: Literal[1, 2] = 1
    reviewer_logical_calls_per_source: Literal[0, 1] = 0
    physical_calls_per_source: Literal[3, 7] = 3
    source_token_cap: Literal[60000] = V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP
    source_physical_call_cap: Literal[3, 7] = V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
    # Historical Phase-8/12 plans may still carry two model synthesis attempts;
    # fresh Phase-13 synthesis is deterministic and therefore reserves none.
    mandatory_synthesis_physical_calls: Literal[0, 2] = 0
    mandatory_synthesis_reservable: bool
    physical_calls_after_reserve: Annotated[int, Field(ge=0, le=160)]
    total_reserved_tokens: NonNegativeInt
    total_reserved_cost_usd: ExactUSD
    token_reservations: tuple[V2DeepAnalysisTokenReservation, ...]
    limiting_reason: V2DeepAnalysisBudgetReason | None = None
    policy_identity: str = V2_DEEP_ANALYSIS_QUEUE_POLICY_IDENTITY

    @model_validator(mode="after")
    def validate_queue_plan(self) -> V2DeepAnalysisQueuePlan:
        queued = tuple(self.queued_source_ids)
        status_ids = tuple(item.source_id for item in self.source_statuses)
        if len(status_ids) != len(set(status_ids)):
            raise ValueError("deep-analysis queue requires one status per survivor")
        if len(queued) != len(set(queued)) or self.queue_capacity != len(queued):
            raise ValueError("deep-analysis queue capacity must match unique queued sources")
        ranked = tuple(
            item.source_id
            for item in sorted(
                (status for status in self.source_statuses if status.queued_for_deep_analysis),
                key=lambda status: status.queue_rank or 0,
            )
        )
        if ranked != queued:
            raise ValueError("deep-analysis statuses must reproduce persisted queue order")
        if tuple(item.source_id for item in self.token_reservations) != queued:
            raise ValueError("token reservations must cover the queued prefix in order")
        return self


class V2SourceSelectionAttempt(StrictModel):
    """One conservatively reserved Final Source Selection attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: Annotated[int, Field(ge=1, le=2)]
    reserved_tokens: PositiveInt
    reserved_cost_usd: ExactUSD
    succeeded: bool
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> V2SourceSelectionAttempt:
        if self.succeeded == (self.failure is not None):
            raise ValueError("source-selection attempt success and failure must agree")
        return self


class V2SourceSelectionQueueResult(StrictModel):
    """Persisted Final Source Selection result plus the safe deep-analysis queue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input: V2SourceSelectionInput
    initial_budget: V2DeepAnalysisBudget
    recommended_source_ids: tuple[UUID, ...]
    recommendation_rationales: tuple[V2SourceSelectionRecommendation, ...]
    used_fallback: bool
    selection_attempts: NonNegativeInt
    selection_attempt_records: tuple[V2SourceSelectionAttempt, ...] = Field(max_length=2)
    selection_stage: Literal["source_selection"] = "source_selection"
    priority_source_ids: tuple[UUID, ...] = ()
    queued_source_ids: tuple[UUID, ...]
    source_statuses: tuple[V2DeepAnalysisSourceStatus, ...]
    queue_capacity: NonNegativeInt
    physical_calls_per_source: Literal[3, 7] = 3
    source_token_cap: Literal[60000] = V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP
    source_physical_call_cap: Literal[3, 7] = V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
    # Historical Phase-8/12 queue results may still carry two model synthesis attempts;
    # fresh Phase-13 synthesis is deterministic and therefore reserves none.
    mandatory_synthesis_physical_calls: Literal[0, 2] = 0
    mandatory_synthesis_reservable: bool
    physical_calls_after_reserve: Annotated[int, Field(ge=0, le=160)]
    total_reserved_tokens: NonNegativeInt
    total_reserved_cost_usd: ExactUSD
    token_reservations: tuple[V2DeepAnalysisTokenReservation, ...]
    limiting_reason: V2DeepAnalysisBudgetReason | None = None
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_result(self) -> V2SourceSelectionQueueResult:
        if self.run_id != self.input.run_id:
            raise ValueError("source-selection result must match its input run")
        source_ids = {item.source_id for item in self.input.survivors}
        status_ids = tuple(item.source_id for item in self.source_statuses)
        if len(status_ids) != len(source_ids) or set(status_ids) != source_ids:
            raise ValueError("every survivor requires exactly one persisted selection status")
        if len(self.recommended_source_ids) != len(set(self.recommended_source_ids)):
            raise ValueError("recommended source IDs must be unique")
        if not set(self.recommended_source_ids).issubset(source_ids):
            raise ValueError("recommendations cannot invent sources")
        if tuple(item.source_id for item in self.recommendation_rationales) != (
            self.recommended_source_ids
        ):
            raise ValueError("recommendation rationales must reproduce recommendation order")
        if len(self.queued_source_ids) != len(set(self.queued_source_ids)):
            raise ValueError("queued source IDs must be unique")
        if not set(self.queued_source_ids).issubset(source_ids):
            raise ValueError("deep-analysis queue cannot invent sources")
        if self.priority_source_ids and (
            len(self.priority_source_ids) != len(source_ids)
            or set(self.priority_source_ids) != source_ids
            or len(set(self.priority_source_ids)) != len(self.priority_source_ids)
        ):
            raise ValueError("persisted deep-analysis priority must retain every survivor once")
        if self.queue_capacity != len(self.queued_source_ids):
            raise ValueError("queue capacity must match queued source count")
        status_by_id = {item.source_id: item for item in self.source_statuses}
        recommended_status_ids = tuple(
            source_id
            for source_id, _status in sorted(
                (
                    (source_id, status)
                    for source_id, status in status_by_id.items()
                    if status.recommended
                ),
                key=lambda item: item[1].recommendation_rank or 0,
            )
        )
        queued_status_ids = tuple(
            source_id
            for source_id, _status in sorted(
                (
                    (source_id, status)
                    for source_id, status in status_by_id.items()
                    if status.queued_for_deep_analysis
                ),
                key=lambda item: item[1].queue_rank or 0,
            )
        )
        if recommended_status_ids != self.recommended_source_ids:
            raise ValueError("source statuses must reproduce recommendation order")
        if queued_status_ids != self.queued_source_ids:
            raise ValueError("source statuses must reproduce deep-analysis queue order")
        if self.selection_attempts != len(self.selection_attempt_records):
            raise ValueError("selection attempt count must match its audit records")
        return self


class ProbePassage(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: NonEmptyStr
    direction: ResearchDirection
    source_cluster_id: NonEmptyStr
    text: NonEmptyStr
    source_url: NonEmptyStr


class ProbeResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    passage: ProbePassage
    accepted: bool
    reason: NonEmptyStr
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> ProbeResult:
        self.directions.require_permitted(self.passage.direction)
        return self


class GapAnalysisResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    gaps: tuple[SearchDirectionGapReference, ...]
    analyzed_at: datetime

    _analyzed_at_is_aware = field_validator("analyzed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_gaps(self) -> GapAnalysisResult:
        for gap in self.gaps:
            self.directions.require_permitted(gap.direction)
        return self


class SurvivingSourceRecord(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    direction: ResearchDirection
    source_cluster: SourceCluster
    reason: NonEmptyStr
    recorded_at: datetime

    _recorded_at_is_aware = field_validator("recorded_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> SurvivingSourceRecord:
        self.directions.require_permitted(self.direction)
        return self


class SourceRecommendationResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    direction: ResearchDirection
    recommended_source_cluster_id: NonEmptyStr | None
    rationale: NonEmptyStr
    recommended_at: datetime

    _recommended_at_is_aware = field_validator("recommended_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> SourceRecommendationResult:
        self.directions.require_permitted(self.direction)
        return self


class DeepAnalysisState(StrEnum):
    NOT_STARTED = "not_started"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class DeepAnalysisStatus(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    direction: ResearchDirection
    state: DeepAnalysisState
    updated_at: datetime

    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> DeepAnalysisStatus:
        self.directions.require_permitted(self.direction)
        return self


class V2PersistedArtifact(StrictModel):
    """Canonical persistence envelope for a typed v2 artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    artifact_key: NonEmptyStr
    artifact_type: NonEmptyStr
    payload_json: NonEmptyStr
    payload_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)
