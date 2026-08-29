from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from money import ExactUSD
from provider_contract import parse_provider_contract_payload, provider_contract_fingerprint

Score = Annotated[int, Field(ge=1, le=5)]
ApprovedScore = Annotated[int, Field(ge=3, le=5)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonEmptyStr = Annotated[str, Field(min_length=1)]
ApplicationReviewerApprovalId = Annotated[
    str,
    Field(pattern=r"^rappr_v1_[0-9a-f]{64}$"),
]
ReviewerApprovalId = UUID | ApplicationReviewerApprovalId
REQUIRED_QUERY_EXCLUSIONS = (
    "-site:reddit.com",
    "-site:quora.com",
    "-site:youtube.com",
    "-site:tiktok.com",
)


def missing_required_query_exclusions(exclusion_parameters: str) -> tuple[str, ...]:
    """Return required search exclusions absent as exact whitespace-delimited tokens."""
    tokens = set(exclusion_parameters.split())
    return tuple(exclusion for exclusion in REQUIRED_QUERY_EXCLUSIONS if exclusion not in tokens)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value


class ResearchDepth(StrEnum):
    FOCUSED = "focused"
    STANDARD = "standard"


class ResearchMode(StrEnum):
    FOCUSED = "focused"
    BALANCED = "balanced"


class DiscoveryProvider(StrEnum):
    SERPSEARCH = "serpsearch"
    EXA = "exa"
    OPENALEX = "openalex"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    SERPER = "serper"


class SearchIntent(StrEnum):
    BROAD_WEB = "broad_web"
    ACADEMIC_STUDY = "academic_study"
    GOVERNMENT_INSTITUTIONAL = "government_institutional"
    NEWS_CURRENT = "news_current"
    LIMITATIONS_COUNTEREVIDENCE = "limitations_counterevidence"


class ReportLength(StrEnum):
    BRIEF = "brief"
    REPORT = "report"


class PresentationTone(StrEnum):
    NEUTRAL = "neutral"
    EXECUTIVE = "executive"
    ACADEMIC = "academic"
    PLAIN_LANGUAGE = "plain_language"


class ResearchFocus(StrictModel):
    """Explicit optional planner constraints; never inferred from the claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    geographic_area: NonEmptyStr | None = None
    timeframe: NonEmptyStr | None = None
    population: NonEmptyStr | None = None
    analytical_lens: NonEmptyStr | None = None

    @field_validator("geographic_area", "timeframe", "population", "analytical_lens")
    @classmethod
    def validate_trimmed(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("focus values must not have leading or trailing whitespace")
        return value

    @model_validator(mode="after")
    def validate_present(self) -> ResearchFocus:
        if not any((self.geographic_area, self.timeframe, self.population, self.analytical_lens)):
            raise ValueError("focus must include at least one explicit constraint")
        return self


class ResearchControls(StrictModel):
    """Frozen operator choices whose canonical JSON is part of run compatibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    depth: ResearchDepth = ResearchDepth.STANDARD
    length: ReportLength = ReportLength.REPORT
    tone: PresentationTone = PresentationTone.NEUTRAL
    focus: ResearchFocus | None = None
    research_mode: ResearchMode = ResearchMode.FOCUSED
    sources_per_stance_per_round: Literal[5, 7, 10, 15, 20] = 10
    discovery_providers: tuple[DiscoveryProvider, ...] = (
        DiscoveryProvider.SERPSEARCH,
        DiscoveryProvider.EXA,
        DiscoveryProvider.OPENALEX,
    )

    @field_validator("discovery_providers")
    @classmethod
    def validate_discovery_providers(
        cls, value: tuple[DiscoveryProvider, ...]
    ) -> tuple[DiscoveryProvider, ...]:
        if not value:
            raise ValueError("at least one discovery provider must be enabled")
        if len(set(value)) != len(value):
            raise ValueError("discovery providers must not contain duplicates")
        canonical = tuple(provider for provider in DiscoveryProvider if provider in value)
        if value != canonical:
            raise ValueError("discovery providers must use canonical provider order")
        return value

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_policy_identity(cls, policy_identity: str) -> ResearchControls:
        """Recover controls from an immutable policy identity with later policy segments."""
        marker = "|controls:"
        if marker not in policy_identity:
            return DEFAULT_RESEARCH_CONTROLS
        try:
            encoded = policy_identity.split(marker, 1)[1]
            payload, end = json.JSONDecoder().raw_decode(encoded)
            suffix = encoded[end:]
            if suffix and not suffix.startswith("|"):
                raise ValueError("controls JSON must end before a policy segment boundary")
            return cls.model_validate(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("provider contract has no valid persisted research controls") from exc


DEFAULT_RESEARCH_CONTROLS = ResearchControls()


# v2 contracts are intentionally separate from the historical focused/balanced
# controls above.  Existing persisted contracts must continue to parse exactly as
# they were written.
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


def v2_artifact_fingerprint(artifact: StrictModel) -> str:
    """Return the SHA-256 identity of a canonical v2 artifact."""
    return sha256(canonical_v2_artifact_json(artifact).encode("utf-8")).hexdigest()


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
    assessed_after_round: Annotated[int, Field(ge=1, le=3)] = 1


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


class RunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CheckpointStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ModelAttemptStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Stage(StrEnum):
    CLAIM_PLANNER = "claim_planner"
    DISCOVERY = "discovery"
    ACQUISITION = "acquisition"
    GAP_ANALYSIS = "gap_analysis"
    ADAPTIVE_SEARCH = "adaptive_search"
    SOURCE_SELECTION = "source_selection"
    DEEP_ANALYSIS = "deep_analysis"
    REVIEW = "review"
    SYNTHESIS = "synthesis"
    SUPPORTING_RESEARCHER = "supporting_researcher"
    OPPOSING_RESEARCHER = "opposing_researcher"
    EVIDENCE_ANALYST = "evidence_analyst"
    EVIDENCE_ADMISSION = "evidence_admission"
    GAP_RECONCILIATION = "gap_reconciliation"
    STATEMENT_REVIEWER = "statement_reviewer"
    CLAIM_LEDGER = "claim_ledger"
    DEBATE_SYNTHESIZER = "debate_synthesizer"
    FINAL_RENDERER_VALIDATOR = "final_renderer_validator"


class Stance(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"


class ResearchRound(StrEnum):
    INITIAL = "initial"
    TARGETED = "targeted"


class EvidenceRole(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"
    LIMITATION = "limitation"


class EvidenceTrailOutcome(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    INACCESSIBLE = "inaccessible"
    UNSUPPORTED_CONTENT = "unsupported_content"
    RETRIEVAL_FAILURE = "retrieval_failure"
    PASSAGE_SELECTION_FAILED = "passage_selection_failed"
    QUOTE_VALIDATION_FAILED = "quote_validation_failed"
    EVIDENCE_DENSITY_FAILURE = "evidence_density_failure"
    ANALYST_REJECTED = "analyst_rejected"
    REVIEWER_REJECTED = "reviewer_rejected"
    NOT_RELEVANT = "not_relevant"
    BUDGET_PREVENTED = "budget_prevented"


class CoverageRating(StrEnum):
    STRONG = "strong"
    ADEQUATE = "adequate"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class Placement(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUPPORTING = "supporting"
    QUALIFIED_ONLY = "qualified_only"


class Entailment(StrEnum):
    STRONG = "Strong"
    PARTIAL = "Partial"
    WEAK = "Weak"


def entailment_for_claim_fit(claim_fit: int) -> Entailment:
    """Return the single application-owned entailment label for a Ledger-eligible fit."""
    try:
        return {
            2: Entailment.WEAK,
            3: Entailment.PARTIAL,
            4: Entailment.PARTIAL,
            5: Entailment.STRONG,
        }[claim_fit]
    except KeyError as exc:
        raise ValueError("Ledger Claim Fit must be 2, 3, 4, or 5") from exc


class RetrievalStatus(StrEnum):
    RETRIEVED = "retrieved"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewerFailureCode(StrEnum):
    NOT_ENTAILED = "not_entailed"
    MISSING_QUALIFICATION = "missing_qualification"
    BIASED_FRAMING = "biased_framing"
    CLAIM_FIT_MISMATCH = "claim_fit_mismatch"


class SectionType(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"
    LIMITATIONS = "limitations"


BRIEF_TITLE = "Research Brief"
CLAIM_LABEL = "Claim under review"
RELEASE_SECTION_ORDER = (
    SectionType.SUPPORTING,
    SectionType.OPPOSING,
    SectionType.LIMITATIONS,
)
RELEASE_SECTION_HEADINGS = {
    SectionType.SUPPORTING: "Supporting Evidence",
    SectionType.OPPOSING: "Opposing Evidence",
    SectionType.LIMITATIONS: "Limitations",
}


class ValidationErrorCode(StrEnum):
    LEDGER_MISMATCH = "ledger_mismatch"
    INVALID_SECTION = "invalid_section"
    INVALID_TEMPLATE = "invalid_template"
    ALTERED_STATEMENT = "altered_statement"
    SCHEMA_ERROR = "schema_error"


def _validate_offsets(
    offsets: list[SegmentOffset] | tuple[SegmentOffset, ...],
) -> list[SegmentOffset] | tuple[SegmentOffset, ...]:
    previous_end: int | None = None
    for offset in offsets:
        if previous_end is not None and offset.start_char < previous_end:
            raise ValueError("segment offsets must be ordered and non-overlapping")
        previous_end = offset.end_char
    return offsets


def _is_ledger_eligible(evidence_quality: int, claim_fit: int) -> bool:
    return evidence_quality >= 2 and claim_fit >= 2


def _derive_ledger_score(evidence_quality: int, claim_fit: int) -> int:
    total_score = evidence_quality + claim_fit
    if total_score <= 6:
        return 3
    if total_score <= 8:
        return 4
    return 5


def _expected_placement(evidence_quality: int, claim_fit: int) -> Placement:
    ledger_score = _derive_ledger_score(evidence_quality, claim_fit)
    if claim_fit == 2:
        return Placement.QUALIFIED_ONLY
    if ledger_score == 5:
        return Placement.PRIMARY
    if ledger_score == 4:
        return Placement.SECONDARY
    return Placement.SUPPORTING


def _placement_matches_score_policy(
    evidence_quality: int,
    claim_fit: int,
    placement: Placement,
) -> bool:
    """Accept the prior Claim Fit 3 placement while reading historical artifacts."""
    return placement is _expected_placement(evidence_quality, claim_fit) or (
        claim_fit == 3 and placement is Placement.QUALIFIED_ONLY
    )


class SegmentOffset(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_char: NonNegativeInt
    end_char: PositiveInt

    @model_validator(mode="after")
    def validate_order(self) -> SegmentOffset:
        if self.start_char >= self.end_char:
            raise ValueError("segment offset start_char must be before end_char")
        return self


class ClaimDefinition(StrictModel):
    run_id: UUID
    claim_text: NonEmptyStr
    population: NonEmptyStr
    jurisdiction: NonEmptyStr
    time_period: NonEmptyStr
    comparison_baseline: NonEmptyStr
    intervention_or_exposure: NonEmptyStr
    causal_or_comparative_meaning: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class AmbiguityRecord(StrictModel):
    run_id: UUID
    ambiguity_id: UUID
    description: NonEmptyStr
    impact: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class SearchQuery(StrictModel):
    run_id: UUID
    query_id: UUID
    stance: Stance
    provider: DiscoveryProvider = DiscoveryProvider.EXA
    intent: SearchIntent = SearchIntent.BROAD_WEB
    query_round: Annotated[int, Field(ge=1, le=4)]
    strategy: NonEmptyStr
    query_text: NonEmptyStr
    exclusion_parameters: str
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_provider_query(self) -> SearchQuery:
        if self.provider in {DiscoveryProvider.EXA, DiscoveryProvider.SERPSEARCH}:
            missing = missing_required_query_exclusions(self.exclusion_parameters)
            if missing:
                raise ValueError(
                    f"{self.provider.value} query is missing required exclusion parameters"
                )
            if self.intent is SearchIntent.ACADEMIC_STUDY:
                raise ValueError("web queries cannot use academic-study intent")
        else:
            if self.intent is not SearchIntent.ACADEMIC_STUDY:
                raise ValueError("OpenAlex queries must use academic-study intent")
            if self.exclusion_parameters:
                raise ValueError("OpenAlex queries cannot contain web exclusion syntax")
        return self


class PlannerOutput(StrictModel):
    run_id: UUID
    claim_definition: ClaimDefinition
    ambiguities: list[AmbiguityRecord]
    search_queries: list[SearchQuery]
    planner_prompt_version: NonEmptyStr
    planner_model_name: NonEmptyStr
    planned_at: datetime

    _planned_at_is_aware = field_validator("planned_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_queries(self) -> PlannerOutput:
        if self.claim_definition.run_id != self.run_id:
            raise ValueError("claim definition run_id must match planner run_id")
        for ambiguity in self.ambiguities:
            if ambiguity.run_id != self.run_id:
                raise ValueError("ambiguity run_id must match planner run_id")

        if len({query.query_id for query in self.search_queries}) != len(self.search_queries):
            raise ValueError("planner search query IDs must be unique")
        self._validate_provider_specific_queries()
        for query in self.search_queries:
            if query.run_id != self.run_id:
                raise ValueError("search query run_id must match planner run_id")
        return self

    def _validate_provider_specific_queries(self) -> None:
        stances = {query.stance for query in self.search_queries}
        if Stance.SUPPORTING not in stances:
            raise ValueError("provider-specific Planner output requires supporting queries")
        for stance in stances:
            for provider, expected_rounds in (
                (DiscoveryProvider.SERPSEARCH, {1, 2}),
                (DiscoveryProvider.EXA, {1, 2, 3}),
                (DiscoveryProvider.OPENALEX, {1}),
            ):
                rounds = {
                    query.query_round
                    for query in self.search_queries
                    if query.stance is stance and query.provider is provider
                }
                count = sum(
                    query.stance is stance and query.provider is provider
                    for query in self.search_queries
                )
                if rounds and (rounds != expected_rounds or count != len(expected_rounds)):
                    raise ValueError("provider query rounds do not match its discovery contract")
        supporting_providers = {
            query.provider for query in self.search_queries if query.stance is Stance.SUPPORTING
        }
        for stance in stances:
            providers = {query.provider for query in self.search_queries if query.stance is stance}
            if providers != supporting_providers:
                raise ValueError("each active stance must use the same discovery providers")

    @property
    def research_mode(self) -> ResearchMode:
        if any(query.stance is Stance.OPPOSING for query in self.search_queries):
            return ResearchMode.BALANCED
        return ResearchMode.FOCUSED

    def queries_for_provider(self, provider: DiscoveryProvider) -> tuple[SearchQuery, ...]:
        return tuple(query for query in self.search_queries if query.provider is provider)


def validate_planner_provider_selection(planner: PlannerOutput, controls: ResearchControls) -> None:
    """Require a new plan to exactly match the frozen source selection."""
    actual = {query.provider for query in planner.search_queries}
    expected = set(controls.discovery_providers)
    if actual != expected:
        raise ValueError("Planner providers must exactly match the selected discovery providers")
    expected_counts = {
        DiscoveryProvider.SERPSEARCH: 2,
        DiscoveryProvider.EXA: 3,
        DiscoveryProvider.OPENALEX: 1,
    }
    for stance in {query.stance for query in planner.search_queries}:
        for provider in controls.discovery_providers:
            count = sum(
                query.stance is stance and query.provider is provider
                for query in planner.search_queries
            )
            if count != expected_counts[provider]:
                raise ValueError(
                    "Planner query counts do not match the selected discovery providers"
                )


class RetrievalRecord(StrictModel):
    run_id: UUID
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=4)]
    query_text: NonEmptyStr
    search_rank: Annotated[int, Field(ge=1, le=25)]
    source_url: NonEmptyStr
    resolved_url: NonEmptyStr
    status: RetrievalStatus
    retrieved_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)


SupportedOriginMediaType = Literal["text/html", "text/plain", "application/pdf"]


class MediaTypeProvenance(StrictModel):
    """Keep verified origin evidence separate from provider-declared metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verified_media_type: SupportedOriginMediaType | None = None
    verified_source_url: str | None = None
    provider_declared_media_type: SupportedOriginMediaType | None = None

    @model_validator(mode="after")
    def validate_verified_pair(self) -> MediaTypeProvenance:
        if (self.verified_media_type is None) != (self.verified_source_url is None):
            raise ValueError("verified media type and source URL must be present together")
        if self.verified_source_url is not None and not self.verified_source_url.strip():
            raise ValueError("verified source URL cannot be blank")
        return self


class SourceSnapshot(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    retrieval_attempt_id: UUID
    snapshot_id: UUID
    source_url: NonEmptyStr
    original_url: NonEmptyStr | None = None
    canonical_url: NonEmptyStr | None = None
    retrieved_at: datetime
    normalized_text: NonEmptyStr
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    word_count: NonNegativeInt
    truncated: bool
    normalization_version: NonEmptyStr | None = None
    acquisition_version: NonEmptyStr | None = None
    provider_name: NonEmptyStr | None = None
    provider_version: NonEmptyStr | None = None
    media_type_provenance: MediaTypeProvenance = MediaTypeProvenance()
    created_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)
    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class SelectedSentenceRange(StrictModel):
    """One inclusive, source-owned sentence range selected by the Extractor."""

    start_sentence: Annotated[int, Field(ge=1)]
    end_sentence: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def validate_order(self) -> SelectedSentenceRange:
        if self.end_sentence < self.start_sentence:
            raise ValueError("sentence range end must not precede its start")
        return self


class VerbatimQuoteSelection(StrictModel):
    """Minimal model-owned Extractor result; application code owns quote assembly."""

    selected_segments: tuple[NonEmptyStr, ...] = ()
    selected_sentence_ranges: tuple[SelectedSentenceRange, ...] = ()

    @field_validator("selected_segments")
    @classmethod
    def validate_exact_segments(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(segment != segment.strip() for segment in value):
            raise ValueError("selected quote segments cannot have surrounding whitespace")
        if any(not segment.strip() for segment in value):
            raise ValueError("selected quote segments must contain visible text")
        return value

    @model_validator(mode="after")
    def validate_selection_shape(self) -> VerbatimQuoteSelection:
        if bool(self.selected_segments) == bool(self.selected_sentence_ranges):
            raise ValueError("select either exact segments or source sentence ranges")
        previous_end = 0
        for selection_range in self.selected_sentence_ranges:
            if selection_range.start_sentence <= previous_end:
                raise ValueError("sentence ranges must be ordered and non-overlapping")
            previous_end = selection_range.end_sentence
        return self


class V2VerbatimQuoteSelection(StrictModel):
    """V2 Extractor output narrowed to application-owned sentence ranges."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_sentence_ranges: tuple[SelectedSentenceRange, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_selection_shape(self) -> V2VerbatimQuoteSelection:
        previous_end = 0
        for selection_range in self.selected_sentence_ranges:
            if selection_range.start_sentence <= previous_end:
                raise ValueError("sentence ranges must be ordered and non-overlapping")
            previous_end = selection_range.end_sentence
        return self


class ProvisionalCandidate(StrictModel):
    run_id: UUID
    stance: Stance
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=4)]
    search_rank: Annotated[int, Field(ge=1, le=25)]
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    extracted_quote_block: NonEmptyStr
    extraction_prompt_version: NonEmptyStr
    extraction_model_name: NonEmptyStr
    extracted_at: datetime

    _extracted_at_is_aware = field_validator("extracted_at")(_validate_aware_datetime)


class CandidateQuoteBlock(StrictModel):
    run_id: UUID
    stance: Stance
    quote_block_id: UUID
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=4)]
    search_rank: Annotated[int, Field(ge=1, le=25)]
    retrieved_at: datetime
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    snapshot_created_at: datetime
    extracted_quote_block: NonEmptyStr
    segment_offsets: Annotated[list[SegmentOffset], Field(min_length=1)]
    raw_segment_word_count: PositiveInt
    has_statistical_markers: bool
    claim_keyword_match_count: NonNegativeInt
    truncated: bool
    extraction_prompt_version: NonEmptyStr
    extraction_model_name: NonEmptyStr
    extracted_at: datetime
    post_filter_version: NonEmptyStr
    post_filter_validated_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)
    _snapshot_created_at_is_aware = field_validator("snapshot_created_at")(_validate_aware_datetime)
    _extracted_at_is_aware = field_validator("extracted_at")(_validate_aware_datetime)
    _post_filter_validated_at_is_aware = field_validator("post_filter_validated_at")(
        _validate_aware_datetime
    )
    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)


class CandidateBatch(StrictModel):
    run_id: UUID
    stance: Stance
    query_round: Annotated[int, Field(ge=1, le=3)]
    candidates: list[CandidateQuoteBlock]
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_batch_members(self) -> CandidateBatch:
        for candidate in self.candidates:
            if candidate.run_id != self.run_id:
                raise ValueError("candidate run_id must match batch run_id")
            if candidate.stance is not self.stance:
                raise ValueError("candidate stance must match batch stance")
            if candidate.query_round != self.query_round:
                raise ValueError("candidate query_round must match batch query_round")
        return self


class ScoreDecision(StrictModel):
    run_id: UUID
    quote_block_id: UUID
    evidence_quality: Score
    claim_fit: Score
    ledger_score: ApprovedScore | None = None
    placement: Placement | None = None
    approved: bool
    rationale: NonEmptyStr
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    scored_at: datetime

    _scored_at_is_aware = field_validator("scored_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_approval_and_placement(self) -> ScoreDecision:
        eligible = _is_ledger_eligible(self.evidence_quality, self.claim_fit)
        if not eligible:
            if self.approved:
                raise ValueError("ineligible score combinations cannot be approved")
            if self.ledger_score is not None or self.placement is not None:
                raise ValueError("ineligible score decisions must not assign Ledger fields")
            return self

        if self.approved:
            expected_score = _derive_ledger_score(self.evidence_quality, self.claim_fit)
            if self.ledger_score != expected_score:
                raise ValueError("approved score decisions require the derived Ledger score")
            if not _placement_matches_score_policy(
                self.evidence_quality, self.claim_fit, self.placement
            ):
                raise ValueError("approved score decisions require the derived placement")
        elif self.ledger_score is not None or self.placement is not None:
            raise ValueError("rejected score decisions must not assign Ledger fields")
        return self


class StatementDraft(StrictModel):
    run_id: UUID
    statement_draft_id: UUID
    quote_block_id: UUID
    stance: Stance
    draft_statement: NonEmptyStr
    claim_fit: Score
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    drafted_at: datetime

    _drafted_at_is_aware = field_validator("drafted_at")(_validate_aware_datetime)


class V2EvidenceRelationship(StrEnum):
    """How a source-supported proposition relates to the requested claim."""

    SUPPORTS = "supports"
    CHALLENGES = "challenges"
    QUALIFIES = "qualifies"
    UNRELATED = "unrelated"


class V2EvidenceAnalystModelOutput(StrictModel):
    """Luna's compact assessment and final factual statement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    narrowest_supported_proposition: NonEmptyStr = Field(max_length=2000)
    canonical_factual_statement: NonEmptyStr | None = Field(default=None, max_length=2000)
    relationship_to_claim: V2EvidenceRelationship
    material_limitations: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    inferential_boundaries: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    evidence_quality: Score
    claim_fit: Score
    reasoning: NonEmptyStr = Field(max_length=3000)
    addressed_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def validate_relationship_score(self) -> V2EvidenceAnalystModelOutput:
        if self.relationship_to_claim is V2EvidenceRelationship.UNRELATED and self.claim_fit > 2:
            raise ValueError("unrelated evidence cannot receive Claim Fit above 2")
        if len(self.addressed_gap_ids) != len(set(self.addressed_gap_ids)):
            raise ValueError("Analyst addressed Gap IDs must be unique")
        return self


class V2CanonicalStatementModelOutput(StrictModel):
    """Luna's narrow statement draft, kept separate from its source assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    narrowest_supported_proposition: NonEmptyStr = Field(max_length=2000)
    canonical_factual_statement: NonEmptyStr = Field(max_length=2000)
    reasoning: NonEmptyStr = Field(max_length=2000)


class V2EvidenceAnalystCandidateInput(StrictModel):
    """One exact, application-assembled candidate assigned to a queued survivor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    snapshot: SourceSnapshot

    @model_validator(mode="after")
    def validate_exact_candidate_provenance(self) -> V2EvidenceAnalystCandidateInput:
        if self.candidate.run_id != self.snapshot.run_id:
            raise ValueError("Phase-9 candidate and snapshot must share a run_id")
        if self.candidate.snapshot_id != self.snapshot.snapshot_id:
            raise ValueError("Phase-9 candidate and snapshot IDs must match")
        if self.candidate.snapshot_sha256 != self.snapshot.snapshot_sha256:
            raise ValueError("Phase-9 candidate and snapshot hashes must match")
        expected_stance = (
            Stance.SUPPORTING if self.direction is ResearchDirection.SUPPORT else Stance.OPPOSING
        )
        if self.candidate.stance is not expected_stance:
            raise ValueError("candidate stance must preserve its queued research direction")
        return self


class V2EvidenceAnalystSnapshotContext(StrictModel):
    """Small source envelope supplied to Luna instead of the complete snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: NonEmptyStr
    word_count: NonNegativeInt
    truncated: bool
    preceding_context: NonEmptyStr
    following_context: NonEmptyStr


class V2EvidenceAnalystExtractionFailure(StrictModel):
    """Exact Phase-8 extraction failure retained for the Phase-9 handoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    failure: NonEmptyStr


class V2EvidenceAnalystBatchInput(StrictModel):
    """Complete Phase-8 queue plus the exact candidates available for Analyst work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    queue_result: V2SourceSelectionQueueResult
    queued_candidates: tuple[V2EvidenceAnalystCandidateInput, ...]
    extraction_failures: tuple[V2EvidenceAnalystExtractionFailure, ...] = ()
    policy_identity: str = V2_EVIDENCE_ANALYST_POLICY_IDENTITY

    @model_validator(mode="after")
    def validate_complete_queue(self) -> V2EvidenceAnalystBatchInput:
        if self.queue_result.run_id != self.run_id:
            raise ValueError("Phase-9 input must match the Phase-8 run")
        if self.queue_result.input.exact_claim != self.exact_claim:
            raise ValueError("Phase-9 exact claim must match Phase-8")
        if self.queue_result.input.directions != self.directions:
            raise ValueError("Phase-9 directions must match Phase-8")
        source_ids = tuple(item.source_id for item in self.queued_candidates)
        expected_order = tuple(
            source_id
            for source_id in self.queue_result.queued_source_ids
            if source_id in set(source_ids)
        )
        if source_ids != expected_order or len(source_ids) != len(set(source_ids)):
            raise ValueError(
                "Phase-9 candidates must be a unique order-preserving subset of the queue"
            )
        extraction_failure_ids = tuple(item.source_id for item in self.extraction_failures)
        queued_ids = set(self.queue_result.queued_source_ids)
        if len(extraction_failure_ids) != len(set(extraction_failure_ids)):
            raise ValueError("Phase-9 extraction failures must identify unique sources")
        if not set(extraction_failure_ids).issubset(queued_ids):
            raise ValueError("Phase-9 extraction failures must belong to the queued sources")
        for item in self.queued_candidates:
            if item.candidate.run_id != self.run_id:
                raise ValueError("Phase-9 candidates must match the run")
            self.directions.require_permitted(item.direction)
        return self


class V2EvidenceAnalystLLMInput(StrictModel):
    """Bounded semantic input with source, proposition, and relationship kept distinct."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    snapshot_context: V2EvidenceAnalystSnapshotContext
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=3)


class V2CanonicalStatementLLMInput(StrictModel):
    """Application-approved score context for one canonical factual statement draft."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    assessment: V2EvidenceAnalystModelOutput
    score_decision: ScoreDecision


class V2CanonicalStatementRevisionLLMInput(StrictModel):
    """One bounded Reviewer-directed revision without changing the proposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    assessment: V2EvidenceAnalystModelOutput
    score_decision: ScoreDecision
    current_statement: StatementDraft
    reviewer_rationale: NonEmptyStr = Field(max_length=3000)
    revision_number: Literal[1] = 1


class V2EvidenceAnalystRevisionResult(StrictModel):
    """Typed post-Reviewer Analyst revision; it still grants no Ledger admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    previous_statement_draft_id: UUID
    revised_statement: StatementDraft
    analyst_attempt_ids: tuple[UUID, ...] = Field(min_length=1, max_length=2)


class V2EvidenceAnalystState(StrEnum):
    NOT_QUEUED = "not_queued"
    READY_FOR_ADMISSION = "ready_for_admission"
    READY_FOR_REVIEWER = "ready_for_reviewer"
    REJECTED = "rejected"
    FAILED = "failed"


class V2EvidenceAnalystSourceResult(StrictModel):
    """Deep-analysis status for one survivor; no state grants Ledger admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    state: V2EvidenceAnalystState
    candidate: CandidateQuoteBlock | None = None
    assessment: V2EvidenceAnalystModelOutput | None = None
    score_decision: ScoreDecision | None = None
    statement_draft: StatementDraft | None = None
    analyst_attempt_ids: tuple[UUID, ...] = ()
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_state(self) -> V2EvidenceAnalystSourceResult:
        semantic_values = (self.assessment, self.score_decision, self.statement_draft)
        if self.state is V2EvidenceAnalystState.NOT_QUEUED:
            if self.candidate is not None or any(value is not None for value in semantic_values):
                raise ValueError("non-queued survivors cannot carry deep-analysis artifacts")
            if self.analyst_attempt_ids or self.failure is not None:
                raise ValueError("non-queued survivors cannot carry Analyst attempt state")
            return self
        if self.state is V2EvidenceAnalystState.FAILED:
            if self.failure is None:
                raise ValueError("failed Analyst results require a failure reason")
            if self.statement_draft is not None:
                raise ValueError("failed Analyst results cannot be Reviewer-ready")
            if self.candidate is None and any(value is not None for value in semantic_values):
                raise ValueError("failed extraction cannot carry Analyst semantic artifacts")
            return self
        if self.candidate is None:
            raise ValueError("completed queued results must retain their exact candidate")
        if self.failure is not None or self.assessment is None or self.score_decision is None:
            raise ValueError("completed Analyst results require assessment and score decision")
        if self.state is V2EvidenceAnalystState.REJECTED:
            if self.score_decision.approved or self.statement_draft is not None:
                raise ValueError("rejected Analyst results cannot carry a statement draft")
        elif not self.score_decision.approved or self.statement_draft is None:
            raise ValueError("Reviewer-ready results require an approved score and draft")
        return self


class V2EvidenceAnalystBatchResult(StrictModel):
    """Restartable Phase-9 output covering every survivor and containing no Ledger records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input: V2EvidenceAnalystBatchInput
    source_results: tuple[V2EvidenceAnalystSourceResult, ...]
    completed_at: datetime
    policy_identity: str = V2_EVIDENCE_ANALYST_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_complete_survivor_output(self) -> V2EvidenceAnalystBatchResult:
        if self.input.run_id != self.run_id:
            raise ValueError("Phase-9 result must match its input run")
        expected = tuple(item.source_id for item in self.input.queue_result.input.survivors)
        actual = tuple(item.source_id for item in self.source_results)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("Phase-9 output must retain every survivor in Phase-8 order")
        directions = {
            item.source_id: item.direction for item in self.input.queue_result.input.survivors
        }
        queued = set(self.input.queue_result.queued_source_ids)
        for item in self.source_results:
            if item.run_id != self.run_id:
                raise ValueError("Phase-9 source results must match the run")
            if item.direction is not directions[item.source_id]:
                raise ValueError("Phase-9 survivor direction cannot change")
            if (item.source_id in queued) == (item.state is V2EvidenceAnalystState.NOT_QUEUED):
                raise ValueError("Phase-9 queued state must match Phase-8")
        return self


class V2LedgerProvenance(StrictModel):
    """Immutable v2 discovery context attached to, but never used to relax, Ledger admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    research_direction: ResearchDirection
    discovery_round: Annotated[int, Field(ge=1, le=4)]
    source_family_id: NonEmptyStr
    recommended: bool
    relevant_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=18)


class V2AdmissionMethod(StrEnum):
    """Semantic boundary that admitted a v2 evidence record."""

    ANALYZER_ADMITTED = "analyzer_admitted"
    REVIEWER_APPROVED = "reviewer_approved"


class V2EvidenceAdmissionRecord(StrictModel):
    """Analyzer-admitted evidence; Reviewer metadata is retained only for compatibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    ledger_claim_id: UUID
    quote_block_id: UUID
    stance: Stance
    approved_factual_statement: NonEmptyStr
    approved_claim_text: NonEmptyStr
    evidence_quality: Score
    claim_fit: Score
    ledger_score: ApprovedScore
    placement: Placement
    entailment: Entailment
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    segment_offsets: Annotated[tuple[SegmentOffset, ...], Field(min_length=1)]
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    analyst_completed_at: datetime
    admission_method: V2AdmissionMethod
    admission_policy_identity: NonEmptyStr
    admitted_at: datetime
    reviewer_prompt_version: NonEmptyStr | None = None
    reviewer_model_name: NonEmptyStr | None = None
    reviewed_at: datetime | None = None
    reviewer_approval_id: ReviewerApprovalId | None = None
    ledger_validated_at: datetime

    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)
    _analyst_completed_at_is_aware = field_validator("analyst_completed_at")(
        _validate_aware_datetime
    )
    _admitted_at_is_aware = field_validator("admitted_at")(_validate_aware_datetime)
    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)
    _ledger_validated_at_is_aware = field_validator("ledger_validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_score_and_admission(self) -> V2EvidenceAdmissionRecord:
        if not _is_ledger_eligible(self.evidence_quality, self.claim_fit):
            raise ValueError("evidence admission requires eligible two-axis scores")
        if self.ledger_score != _derive_ledger_score(self.evidence_quality, self.claim_fit):
            raise ValueError("evidence admission requires the derived Ledger score")
        if not _placement_matches_score_policy(
            self.evidence_quality, self.claim_fit, self.placement
        ):
            raise ValueError("evidence admission requires the derived placement")
        if self.entailment is not entailment_for_claim_fit(self.claim_fit):
            raise ValueError("evidence admission entailment must be derived from Claim Fit")
        reviewer_values = (
            self.reviewer_prompt_version,
            self.reviewer_model_name,
            self.reviewed_at,
            self.reviewer_approval_id,
        )
        if self.admission_method is V2AdmissionMethod.ANALYZER_ADMITTED and any(
            value is not None for value in reviewer_values
        ):
            raise ValueError("analyzer-admitted evidence cannot carry Reviewer metadata")
        if self.admission_method is V2AdmissionMethod.REVIEWER_APPROVED and any(
            value is None for value in reviewer_values
        ):
            raise ValueError("Reviewer-approved evidence requires complete Reviewer metadata")
        return self


class V2EvidenceAdmissionState(StrEnum):
    NOT_QUEUED = "not_queued"
    ANALYST_REJECTED = "analyst_rejected"
    ANALYST_FAILED = "analyst_failed"
    ANALYZER_ADMITTED = "analyzer_admitted"


class V2EvidenceAdmissionSourceResult(StrictModel):
    """Deterministic admission outcome for one analyzed survivor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    state: V2EvidenceAdmissionState
    provenance: V2LedgerProvenance
    evidence_record: V2EvidenceAdmissionRecord | None = None
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_admission_shape(self) -> V2EvidenceAdmissionSourceResult:
        if self.provenance.source_id != self.source_id:
            raise ValueError("admission provenance source_id must match the source result")
        if self.provenance.research_direction is not self.direction:
            raise ValueError("admission provenance direction must match the source result")
        if self.state is V2EvidenceAdmissionState.ANALYZER_ADMITTED:
            if self.evidence_record is None or self.failure is not None:
                raise ValueError("analyzer-admitted results require an evidence record")
            if self.evidence_record.admission_method is not V2AdmissionMethod.ANALYZER_ADMITTED:
                raise ValueError("fresh evidence records must be analyzer-admitted")
            if self.evidence_record.run_id != self.run_id:
                raise ValueError("evidence record run_id must match the source result")
            return self
        if self.evidence_record is not None:
            raise ValueError("only analyzer-admitted results may carry an evidence record")
        if self.state is V2EvidenceAdmissionState.ANALYST_FAILED and self.failure is None:
            raise ValueError("failed admission results require a failure reason")
        if self.state is not V2EvidenceAdmissionState.ANALYST_FAILED and self.failure is not None:
            raise ValueError("only failed admission results may carry a failure reason")
        return self


class V2EvidenceAdmissionBatchResult(StrictModel):
    """Restartable deterministic bridge from the Analyst to final synthesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    analyst_result: V2EvidenceAnalystBatchResult
    source_results: tuple[V2EvidenceAdmissionSourceResult, ...]
    completed_at: datetime
    policy_identity: str = V2_EVIDENCE_ADMISSION_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_complete_results(self) -> V2EvidenceAdmissionBatchResult:
        if self.analyst_result.run_id != self.run_id:
            raise ValueError("evidence admission must match its Analyst result")
        expected = tuple(item.source_id for item in self.analyst_result.source_results)
        actual = tuple(item.source_id for item in self.source_results)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("evidence admission must retain every survivor in order")
        return self


class V2ReviewerLedgerState(StrEnum):
    NOT_QUEUED = "not_queued"
    ANALYST_REJECTED = "analyst_rejected"
    ANALYST_FAILED = "analyst_failed"
    REVIEWER_REJECTED = "reviewer_rejected"
    REVIEWER_FAILED = "reviewer_failed"
    ADMITTED = "admitted"


class V2ReviewerLedgerSourceResult(StrictModel):
    """Complete downstream outcome for one Phase-9 survivor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    state: V2ReviewerLedgerState
    provenance: V2LedgerProvenance
    review_results: tuple[StatementReviewResult, ...] = Field(max_length=1)
    ledger_record: LedgerRecord | None = None
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> V2ReviewerLedgerSourceResult:
        if self.provenance.source_id != self.source_id:
            raise ValueError("Ledger provenance source_id must match the source result")
        if self.provenance.research_direction is not self.direction:
            raise ValueError("Ledger provenance direction must match the source result")
        if self.state is V2ReviewerLedgerState.ADMITTED:
            if self.ledger_record is None or not self.review_results or self.failure is not None:
                raise ValueError(
                    "admitted source results require a Ledger record and approval history"
                )
            return self
        if self.ledger_record is not None:
            raise ValueError("only admitted source results may carry a Ledger record")
        if (
            self.state
            in {
                V2ReviewerLedgerState.NOT_QUEUED,
                V2ReviewerLedgerState.ANALYST_REJECTED,
                V2ReviewerLedgerState.ANALYST_FAILED,
            }
            and self.review_results
        ):
            raise ValueError("non-Reviewer source results cannot carry Reviewer decisions")
        if self.state is V2ReviewerLedgerState.REVIEWER_REJECTED and not self.review_results:
            raise ValueError("Reviewer rejection requires the retained Reviewer decisions")
        if self.state is V2ReviewerLedgerState.REVIEWER_FAILED and self.failure is None:
            raise ValueError("Reviewer failure requires an explicit failure reason")
        return self


class V2ReviewerLedgerBatchResult(StrictModel):
    """Restartable Phase-10 bridge from Analyst survivors to immutable Ledger admissions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    analyst_result: V2EvidenceAnalystBatchResult
    source_results: tuple[V2ReviewerLedgerSourceResult, ...]
    completed_at: datetime
    policy_identity: Literal["researchassistant-v2-phase-10-reviewer-ledger-v2"] = (
        V2_REVIEWER_LEDGER_POLICY_IDENTITY
    )

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_complete_results(self) -> V2ReviewerLedgerBatchResult:
        if self.analyst_result.run_id != self.run_id:
            raise ValueError("Phase-10 result must match its Phase-9 input")
        expected = tuple(item.source_id for item in self.analyst_result.source_results)
        actual = tuple(item.source_id for item in self.source_results)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("Phase-10 output must retain every Phase-9 survivor in order")
        return self


class V2DeepAnalysisSourceExecutionState(StrEnum):
    ADMITTED = "admitted"
    ANALYZER_ADMITTED = "analyzer_admitted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXTRACTION_FAILED = "extraction_failed"
    ANALYST_REJECTED = "analyst_rejected"
    ANALYST_FAILED = "analyst_failed"
    REVIEWER_REJECTED = "reviewer_rejected"
    REVIEWER_FAILED = "reviewer_failed"
    NOT_ATTEMPTED = "not_attempted"


class V2DeepAnalysisSourceExecution(StrictModel):
    """Typed terminal outcome retained by the source backfill controller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    state: V2DeepAnalysisSourceExecutionState
    physical_call_sequences: tuple[PositiveInt, ...] = ()
    failure_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_execution(self) -> V2DeepAnalysisSourceExecution:
        if self.state is V2DeepAnalysisSourceExecutionState.NOT_ATTEMPTED:
            if self.physical_call_sequences or self.failure_reason is not None:
                raise ValueError("unattempted sources cannot carry execution evidence")
        elif self.state in {
            V2DeepAnalysisSourceExecutionState.ADMITTED,
            V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED,
        }:
            if self.failure_reason is not None:
                raise ValueError("admitted sources cannot carry a failure reason")
        elif self.failure_reason is None:
            raise ValueError("terminal source failures require an explicit reason")
        return self


class V2DeepAnalysisSourceReconciliation(StrictModel):
    """Per-source conservative exposure reconciliation, independent of run totals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    source_cap_tokens: Literal[60000] = V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP
    source_cap_cost_usd: ExactUSD
    accounted_tokens: NonNegativeInt
    released_tokens: NonNegativeInt
    accounted_cost_usd: ExactUSD
    released_cost_usd: ExactUSD
    physical_call_sequences: tuple[PositiveInt, ...] = ()

    @model_validator(mode="after")
    def validate_reconciliation(self) -> V2DeepAnalysisSourceReconciliation:
        expected_release = max(0, self.source_cap_tokens - self.accounted_tokens)
        if self.released_tokens != expected_release:
            raise ValueError("source token release must reconcile exactly to its cap")
        expected_cost_release = max(
            Decimal("0"), self.source_cap_cost_usd - self.accounted_cost_usd
        )
        if self.released_cost_usd != expected_cost_release:
            raise ValueError("source cost release must reconcile exactly to its cap")
        return self


class V2DeepAnalysisBackfillResult(StrictModel):
    """Versioned final deep-analysis execution consumed by downstream synthesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    original_queued_source_ids: tuple[UUID, ...]
    replacement_source_ids: tuple[UUID, ...]
    final_execution_order: tuple[UUID, ...]
    final_queue_result: V2SourceSelectionQueueResult
    source_executions: tuple[V2DeepAnalysisSourceExecution, ...]
    source_reconciliations: tuple[V2DeepAnalysisSourceReconciliation, ...]
    remaining_run_budget: V2DeepAnalysisBudget
    final_admission_result: V2EvidenceAdmissionBatchResult | None = None
    final_reviewer_result: V2ReviewerLedgerBatchResult | None = None
    terminal_reasons: tuple[NonEmptyStr, ...] = ()
    completed_at: datetime
    policy_identity: str = V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_backfill(self) -> V2DeepAnalysisBackfillResult:
        if self.run_id != self.final_queue_result.run_id:
            raise ValueError("backfill and final queue must share the run")
        if self.final_admission_result is None and self.final_reviewer_result is None:
            raise ValueError("backfill must retain an admission or historical Reviewer result")
        if self.final_admission_result is not None and (
            self.final_admission_result.run_id != self.run_id
        ):
            raise ValueError("backfill and final admission result must share the run")
        if (
            self.final_reviewer_result is not None
            and self.final_reviewer_result.run_id != self.run_id
        ):
            raise ValueError("backfill and historical Reviewer result must share the run")
        if len(self.final_execution_order) != len(set(self.final_execution_order)):
            raise ValueError("final execution order cannot contain duplicates")
        if self.final_queue_result.queued_source_ids != self.final_execution_order:
            raise ValueError("final queue must reproduce the final execution order")
        if len(self.replacement_source_ids) != len(set(self.replacement_source_ids)):
            raise ValueError("replacement source IDs must be unique")
        if set(self.replacement_source_ids) & set(self.original_queued_source_ids):
            raise ValueError("replacement source IDs cannot repeat original queued sources")
        if not set(self.original_queued_source_ids).issubset(
            set(self.final_execution_order) | set(item.source_id for item in self.source_executions)
        ):
            raise ValueError("backfill must retain every original queued source outcome")
        if tuple(item.source_id for item in self.source_executions) != tuple(
            item.source_id for item in self.source_reconciliations
        ):
            raise ValueError("source execution and reconciliation order must match")
        return self


class V2SynthesizerLedgerItem(StrictModel):
    """The only evidence projection available to the v2 Synthesizer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    ledger_claim_id: UUID
    reviewer_approval_id: ReviewerApprovalId | None = None
    admission_method: V2AdmissionMethod = V2AdmissionMethod.REVIEWER_APPROVED
    stance: Stance
    placement: Placement
    entailment: Entailment
    approved_factual_statement: NonEmptyStr


class V2SynthesizerRecommendationMetadata(StrictModel):
    """Non-evidentiary source-selection state retained for the v2 synthesizer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    recommended: bool
    queued_for_deep_analysis: bool
    budget_prevented_reason: V2DeepAnalysisBudgetReason | None = None


class V2SynthesizerInput(StrictModel):
    """Bounded v2 synthesis projection with no raw-source text or unreviewed claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    approved_ledger_items: tuple[V2SynthesizerLedgerItem, ...] = Field(min_length=1)
    qualifications: tuple[V2SynthesizerLedgerItem, ...]
    unresolved_material_gaps: tuple[V2SourceSelectionGap, ...]
    stopping_reason: NonEmptyStr
    recommendation_metadata: tuple[V2SynthesizerRecommendationMetadata, ...]

    @model_validator(mode="after")
    def validate_v2_synthesis_input(self) -> V2SynthesizerInput:
        item_ids = tuple(item.ledger_claim_id for item in self.approved_ledger_items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("v2 synthesis Ledger claim IDs must be unique")
        if any(not self.directions.permits(item.direction) for item in self.approved_ledger_items):
            raise ValueError("v2 synthesis cannot include disabled-direction evidence")
        if any(
            item.placement is not Placement.QUALIFIED_ONLY for item in self.qualifications
        ) or not set(self.qualifications).issubset(set(self.approved_ledger_items)):
            raise ValueError("v2 synthesis qualifications must be approved qualified-only evidence")
        source_ids = tuple(item.source_id for item in self.recommendation_metadata)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("v2 synthesis recommendation metadata must have unique source IDs")
        if any(
            not self.directions.permits(item.direction) for item in self.recommendation_metadata
        ):
            raise ValueError("v2 synthesis cannot include disabled-direction recommendations")
        if any(not self.directions.permits(gap.direction) for gap in self.unresolved_material_gaps):
            raise ValueError("v2 synthesis cannot include disabled-direction gaps")
        return self


class StatementReviewResult(StrictModel):
    run_id: UUID
    statement_draft_id: UUID
    quote_block_id: UUID
    approved: bool
    reviewer_approval_id: ReviewerApprovalId | None = None
    approved_factual_statement: NonEmptyStr | None = None
    failure_code: ReviewerFailureCode | None = None
    rationale: NonEmptyStr
    reviewer_prompt_version: NonEmptyStr
    reviewer_model_name: NonEmptyStr
    reviewed_at: datetime

    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_result_shape(self) -> StatementReviewResult:
        if self.approved:
            if self.reviewer_approval_id is None:
                raise ValueError("approved review results require reviewer_approval_id")
            if self.approved_factual_statement is None:
                raise ValueError("approved review results require an approved factual statement")
            if self.failure_code is not None:
                raise ValueError("approved review results cannot include a failure code")
        else:
            if self.failure_code is None:
                raise ValueError("rejected review results require a failure code")
            if self.reviewer_approval_id is not None:
                raise ValueError("rejected review results cannot include reviewer_approval_id")
            if self.approved_factual_statement is not None:
                raise ValueError("rejected review results cannot include an approved statement")
        return self


class LedgerRecord(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    ledger_claim_id: UUID
    quote_block_id: UUID
    stance: Stance
    approved_factual_statement: NonEmptyStr
    approved_claim_text: NonEmptyStr
    evidence_quality: Score
    claim_fit: Score
    ledger_score: ApprovedScore
    placement: Placement
    entailment: Entailment
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    segment_offsets: Annotated[tuple[SegmentOffset, ...], Field(min_length=1)]
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    analyst_completed_at: datetime
    reviewer_prompt_version: NonEmptyStr
    reviewer_model_name: NonEmptyStr
    reviewed_at: datetime
    reviewer_approval_id: ReviewerApprovalId
    ledger_validated_at: datetime

    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)
    _analyst_completed_at_is_aware = field_validator("analyst_completed_at")(
        _validate_aware_datetime
    )
    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)
    _ledger_validated_at_is_aware = field_validator("ledger_validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_score_contract(self) -> LedgerRecord:
        if not _is_ledger_eligible(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require eligible two-axis scores")
        if self.ledger_score != _derive_ledger_score(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require the derived Ledger score")
        if not _placement_matches_score_policy(
            self.evidence_quality, self.claim_fit, self.placement
        ):
            raise ValueError("Ledger records require the derived placement")
        expected_entailment = entailment_for_claim_fit(self.claim_fit)
        legacy_entailment = (
            self.claim_fit == 3
            and self.placement is Placement.QUALIFIED_ONLY
            and self.entailment is Entailment.WEAK
        )
        if self.entailment is not expected_entailment and not legacy_entailment:
            raise ValueError("Ledger entailment must be derived from Claim Fit")
        return self


class SourceFamilyIdentity(StrictModel):
    """Deterministic audit identity for one underlying source family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_family_id: UUID
    family_key: NonEmptyStr
    identification_basis: NonEmptyStr


class EvidenceTrailEntry(StrictModel):
    """Append-only, plain-language outcome for one discovered source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trail_entry_id: UUID
    run_id: UUID
    retrieval_attempt_id: UUID
    research_round: ResearchRound
    role: EvidenceRole
    source_title: NonEmptyStr
    source_domain: NonEmptyStr
    original_url: NonEmptyStr
    resolved_url: NonEmptyStr
    source_family: SourceFamilyIdentity | None = None
    retrieval_method: NonEmptyStr
    snapshot_status: NonEmptyStr
    outcome: EvidenceTrailOutcome
    explanation: NonEmptyStr
    technical_failure_code: str | None = None
    model_attempt_ids: tuple[UUID, ...] = ()
    accepted_statement: str | None = None
    accepted_quote: str | None = None
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    cost_incurred: bool = False
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class PortfolioItem(StrictModel):
    """One approved Ledger statement included in an evidence portfolio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    ledger_claim_id: UUID
    source_family_id: UUID
    role: EvidenceRole
    research_round: ResearchRound
    added_at: datetime

    _added_at_is_aware = field_validator("added_at")(_validate_aware_datetime)


class PortfolioCoverageAssessment(StrictModel):
    """Deterministic source-family coverage, never a claim of factual certainty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    approved_evidence_items: NonNegativeInt
    independent_source_families: NonNegativeInt
    supporting_families: NonNegativeInt
    opposing_or_limitation_families: NonNegativeInt
    duplicate_count: NonNegativeInt
    rejected_count: NonNegativeInt
    inaccessible_count: NonNegativeInt
    research_rounds: NonNegativeInt
    rating: CoverageRating
    stopping_reason: NonEmptyStr
    important_missing_evidence: tuple[str, ...] = ()
    assessed_at: datetime

    _assessed_at_is_aware = field_validator("assessed_at")(_validate_aware_datetime)


class PortfolioExpansionRequest(StrictModel):
    """Typed context that directs the one permitted targeted Planner round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    original_claim: NonEmptyStr
    approved_source_families: tuple[SourceFamilyIdentity, ...]
    supporting_coverage: NonNegativeInt
    opposing_or_limitation_coverage: NonNegativeInt
    rejected_sources: tuple[NonEmptyStr, ...]
    inaccessible_domains: tuple[NonEmptyStr, ...]
    duplicate_source_families: tuple[SourceFamilyIdentity, ...]
    attempted_queries: tuple[NonEmptyStr, ...]
    evidence_gaps: tuple[NonEmptyStr, ...]


class ResearchRoundStatus(StrEnum):
    """Persisted lifecycle state for one bounded MVP-11 research round."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    CEILING_STOPPED = "ceiling_stopped"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ResearchGovernorDecisionOutcome(StrEnum):
    """The only deterministic outcomes of the post-Round-2 Governor."""

    BEGIN_ROUND_THREE = "begin_round_three"
    FINALIZE = "finalize"


class ResearchGovernorReasonCode(StrEnum):
    """Stable, application-owned explanation code for an authorization decision."""

    ROUND_THREE_AUTHORIZED = "round_three_authorized"
    PORTFOLIO_COMPLETE = "portfolio_complete"
    DUPLICATE_HEAVY_ROUND_TWO = "duplicate_heavy_round_two"
    CONSECUTIVE_UNPRODUCTIVE_SOURCES = "consecutive_unproductive_sources"
    NO_MEANINGFUL_SEARCH_ANGLE = "no_meaningful_search_angle"
    INSUFFICIENT_RESERVED_BUDGET = "insufficient_reserved_budget"
    RUN_CANCELLED = "run_cancelled"
    TERMINAL_PROVIDER_FAILURE = "terminal_provider_failure"
    ROUND_LIMIT_REACHED = "round_limit_reached"


class ResearchTerminalOutcome(StrEnum):
    """The permitted terminal evidence outcomes after the final research round."""

    COMPLETE = "complete"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ResearchRoundRecord(StrictModel):
    """Append-only plan and terminal state for exactly one permitted research round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    research_round: Annotated[int, Field(ge=1, le=3)]
    status: ResearchRoundStatus
    planned_query_count: NonNegativeInt
    planned_discovery_count: NonNegativeInt
    completed_query_count: NonNegativeInt = 0
    completed_discovery_count: NonNegativeInt = 0
    started_at: datetime
    completed_at: datetime | None = None
    stopping_reason: NonEmptyStr

    _started_at_is_aware = field_validator("started_at")(_validate_aware_datetime)
    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_terminal_timestamp(self) -> ResearchRoundRecord:
        terminal = {
            ResearchRoundStatus.COMPLETED,
            ResearchRoundStatus.CEILING_STOPPED,
            ResearchRoundStatus.CANCELLED,
            ResearchRoundStatus.FAILED,
        }
        if self.status in terminal and self.completed_at is None:
            raise ValueError("terminal research rounds require completed_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("research round completion cannot precede its start")
        if self.completed_query_count > self.planned_query_count:
            raise ValueError("completed queries cannot exceed the planned workload")
        if self.completed_discovery_count > self.planned_discovery_count:
            raise ValueError("completed discoveries cannot exceed the planned workload")
        return self


class ResearchGovernorBudgetState(StrictModel):
    """Cumulative accounted usage and conservative Round-3 reservation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls_used: NonNegativeInt
    model_calls_remaining: NonNegativeInt
    retrievals_used: NonNegativeInt
    retrievals_remaining: NonNegativeInt
    conservative_tokens_used: NonNegativeInt | None = None
    tokens_remaining: NonNegativeInt | None = None
    conservative_cost_used_usd: ExactUSD | None = None
    cost_remaining_usd: ExactUSD | None = None
    round_three_model_calls_required: NonNegativeInt
    round_three_retrievals_required: NonNegativeInt
    round_three_tokens_required: NonNegativeInt | None = None
    round_three_cost_required_usd: ExactUSD | None = None
    full_round_three_reserved: bool


class ResearchGovernorPolicy(StrictModel):
    """Versioned fixed application policy; callers cannot raise the three-round cap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["mvp11-research-governor-v1"] = "mvp11-research-governor-v1"
    required_independent_families: Literal[3] = 3
    duplicate_heavy_rate: Annotated[float, Field(ge=0, le=1)] = 0.70
    consecutive_unproductive_source_limit: Literal[3] = 3
    maximum_research_rounds: Literal[3] = 3


class ResearchGovernorEvaluationInput(StrictModel):
    """Typed facts used by deterministic application logic after completed Round 2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    current_round: Literal[2] = 2
    independent_approved_family_count: NonNegativeInt
    round_two_duplicate_count: NonNegativeInt
    round_two_result_count: NonNegativeInt
    consecutive_unproductive_source_count: NonNegativeInt
    remaining_search_angles: tuple[NonEmptyStr, ...]
    cumulative_budget: ResearchGovernorBudgetState
    cancelled: bool = False
    terminal_provider_or_infrastructure_failure: bool = False
    decided_at: datetime

    _decided_at_is_aware = field_validator("decided_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_duplicate_count(self) -> ResearchGovernorEvaluationInput:
        if self.round_two_duplicate_count > self.round_two_result_count:
            raise ValueError("duplicate count cannot exceed completed Round-2 results")
        return self


class ResearchGovernorDecision(StrictModel):
    """Strict deterministic post-Round-2 authorization artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    current_round: Annotated[int, Field(ge=1, le=3)]
    independent_approved_family_count: NonNegativeInt
    portfolio_complete: bool
    round_two_duplicate_count: NonNegativeInt
    round_two_result_count: NonNegativeInt
    round_two_duplicate_rate: Annotated[float, Field(ge=0, le=1)]
    consecutive_unproductive_source_count: NonNegativeInt
    remaining_search_angles: tuple[NonEmptyStr, ...]
    cumulative_budget: ResearchGovernorBudgetState
    decision: ResearchGovernorDecisionOutcome
    reason_code: ResearchGovernorReasonCode
    explanation: NonEmptyStr
    policy_version: NonEmptyStr
    decided_at: datetime

    _decided_at_is_aware = field_validator("decided_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_decision_contract(self) -> ResearchGovernorDecision:
        if self.current_round != 2:
            raise ValueError("Research Governor authorization is evaluated only after Round 2")
        if self.round_two_result_count == 0 and self.round_two_duplicate_rate != 0:
            raise ValueError("an empty Round 2 must have a zero duplicate rate")
        if self.decision is ResearchGovernorDecisionOutcome.BEGIN_ROUND_THREE:
            if self.reason_code is not ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED:
                raise ValueError("Round 3 authorization requires its stable reason code")
            if not self.cumulative_budget.full_round_three_reserved:
                raise ValueError("Round 3 authorization requires a full conservative reservation")
        elif self.reason_code is ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED:
            raise ValueError("finalization cannot use the authorization reason code")
        return self


class ResearchTerminalResult(StrictModel):
    """Terminal Governor summary that explains the permitted stopping point."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    outcome: ResearchTerminalOutcome
    completed_rounds: Annotated[int, Field(ge=1, le=3)]
    independent_approved_family_count: NonNegativeInt
    explanation: NonEmptyStr
    finalized_at: datetime

    _finalized_at_is_aware = field_validator("finalized_at")(_validate_aware_datetime)


class SynthesisItem(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connective_template_id: NonEmptyStr
    ledger_claim_id: UUID
    reviewer_approval_id: ReviewerApprovalId | None = None
    admission_method: V2AdmissionMethod = V2AdmissionMethod.REVIEWER_APPROVED
    stance: Stance
    placement: Placement
    entailment: Entailment
    approved_factual_statement: NonEmptyStr


class SynthesisSection(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_type: SectionType
    items: tuple[SynthesisItem, ...]

    @model_validator(mode="after")
    def validate_item_compatibility(self) -> SynthesisSection:
        if self.section_type is SectionType.SUPPORTING:
            required_stance = Stance.SUPPORTING
        elif self.section_type is SectionType.OPPOSING:
            required_stance = Stance.OPPOSING
        else:
            return self

        for item in self.items:
            if item.stance is not required_stance:
                raise ValueError("section items must use a compatible stance")
        return self


class SynthesisOutput(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    synthesizer_prompt_version: NonEmptyStr
    synthesizer_model_name: NonEmptyStr
    created_at: datetime
    sections: tuple[SynthesisSection, ...]

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class V2ProviderRunDiagnostics(StrictModel):
    """Persisted, non-evidentiary outcome counts for one discovery provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: DiscoveryProvider
    query_attempts: NonNegativeInt = 0
    non_empty_queries: NonNegativeInt = 0
    empty_queries: NonNegativeInt = 0
    timeout_queries: NonNegativeInt = 0
    failed_queries: NonNegativeInt = 0
    search_results: NonNegativeInt = 0
    surviving_sources: NonNegativeInt = 0

    @model_validator(mode="after")
    def validate_query_counts(self) -> V2ProviderRunDiagnostics:
        counted_attempts = (
            self.non_empty_queries + self.empty_queries + self.timeout_queries + self.failed_queries
        )
        if counted_attempts != self.query_attempts:
            raise ValueError("provider query outcome counts must reconcile to query attempts")
        return self


class V2RunDiagnostics(StrictModel):
    """Persisted v2 execution facts used by the live result page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configured_providers: tuple[DiscoveryProvider, ...] = Field(min_length=1, max_length=6)
    provider_outcomes: tuple[V2ProviderRunDiagnostics, ...]
    search_attempts: NonNegativeInt = 0
    search_results: NonNegativeInt = 0
    acquisition_attempts: NonNegativeInt = 0
    sources_acquired: NonNegativeInt = 0
    sources_survived_probe: NonNegativeInt = 0
    sources_queued_for_analysis: NonNegativeInt = 0
    sources_analyzed: NonNegativeInt = 0
    approved_evidence_records: NonNegativeInt = 0

    @model_validator(mode="after")
    def validate_diagnostics(self) -> V2RunDiagnostics:
        configured = self.configured_providers
        outcome_providers = tuple(item.provider for item in self.provider_outcomes)
        if len(set(configured)) != len(configured):
            raise ValueError("configured discovery providers must be unique")
        if outcome_providers != configured:
            raise ValueError("provider diagnostics must preserve configured provider order")
        if self.search_attempts != sum(item.query_attempts for item in self.provider_outcomes):
            raise ValueError("search attempts must reconcile to provider diagnostics")
        if self.search_results != sum(item.search_results for item in self.provider_outcomes):
            raise ValueError("search results must reconcile to provider diagnostics")
        return self


class V2ResultSourceStatus(StrEnum):
    RECOMMENDED_ANALYZED = "recommended_analyzed"
    RECOMMENDED_ANALYZER_ADMITTED = "recommended_analyzer_admitted"
    RECOMMENDED_ANALYZER_REJECTED = "recommended_analyzer_rejected"
    RECOMMENDED_ANALYZER_FAILED = "recommended_analyzer_failed"
    RECOMMENDED_NO_LEDGER_EVIDENCE = "recommended_no_ledger_evidence"
    SURVIVING_ANALYZED = "surviving_analyzed"
    SURVIVING_ANALYZER_ADMITTED = "surviving_analyzer_admitted"
    SURVIVING_ANALYZER_REJECTED = "surviving_analyzer_rejected"
    SURVIVING_ANALYZER_FAILED = "surviving_analyzer_failed"
    SURVIVING_NOT_DEEPLY_ANALYZED = "surviving_not_deeply_analyzed"
    BUDGET_PREVENTED_ANALYSIS = "budget_prevented_analysis"


class V2ResultSource(StrictModel):
    """Presentation-safe source metadata; it contains no source-derived factual prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    source_url: NonEmptyStr
    title: NonEmptyStr | None = None
    source_type: NonEmptyStr | None = None
    publication_date: NonEmptyStr | None = None
    discovery_providers: tuple[DiscoveryProvider, ...]
    discovery_round: Annotated[int, Field(ge=1, le=4)]
    recommended: bool
    recommendation_rank: PositiveInt | None = None
    queue_rank: PositiveInt | None = None
    status: V2ResultSourceStatus
    ledger_claim_ids: tuple[UUID, ...] = ()
    budget_prevented_reason: V2DeepAnalysisBudgetReason | None = None

    @model_validator(mode="after")
    def validate_source_status(self) -> V2ResultSource:
        if self.recommended != (self.recommendation_rank is not None):
            raise ValueError("v2 result recommendation state and rank must agree")
        if self.status is V2ResultSourceStatus.BUDGET_PREVENTED_ANALYSIS:
            if self.budget_prevented_reason is None or self.ledger_claim_ids:
                raise ValueError("budget-prevented sources cannot have Ledger evidence")
        elif self.budget_prevented_reason is not None:
            raise ValueError("only budget-prevented sources may carry a budget reason")
        if self.status is V2ResultSourceStatus.RECOMMENDED_ANALYZED:
            if not self.recommended or not self.ledger_claim_ids:
                raise ValueError("recommended analyzed sources require Ledger evidence")
        if self.status is V2ResultSourceStatus.RECOMMENDED_ANALYZER_ADMITTED:
            if not self.recommended or not self.ledger_claim_ids:
                raise ValueError("recommended analyzer-admitted sources require evidence")
        if self.status in {
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_REJECTED,
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_FAILED,
        }:
            if not self.recommended or self.ledger_claim_ids:
                raise ValueError("recommended analyzer-terminal sources cannot carry evidence")
        if self.status is V2ResultSourceStatus.RECOMMENDED_NO_LEDGER_EVIDENCE:
            if not self.recommended or self.ledger_claim_ids:
                raise ValueError("recommended no-Ledger sources cannot carry Ledger evidence")
        if self.status is V2ResultSourceStatus.SURVIVING_ANALYZED:
            if self.recommended or not self.ledger_claim_ids:
                raise ValueError(
                    "surviving analyzed sources require nonrecommended Ledger evidence"
                )
        if self.status is V2ResultSourceStatus.SURVIVING_ANALYZER_ADMITTED:
            if self.recommended or not self.ledger_claim_ids:
                raise ValueError(
                    "surviving analyzer-admitted sources require nonrecommended evidence"
                )
        if self.status in {
            V2ResultSourceStatus.SURVIVING_ANALYZER_REJECTED,
            V2ResultSourceStatus.SURVIVING_ANALYZER_FAILED,
        }:
            if self.recommended or self.ledger_claim_ids:
                raise ValueError("surviving analyzer-terminal sources cannot carry evidence")
        if self.status is V2ResultSourceStatus.SURVIVING_NOT_DEEPLY_ANALYZED:
            if self.recommended or self.ledger_claim_ids:
                raise ValueError("unanalysed surviving sources cannot carry Ledger evidence")
        return self


class V2UnresolvedMaterialGap(StrictModel):
    """A persisted strategy gap, disclosed without inventing an answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    missing_evidence: NonEmptyStr
    assessed_after_round: Annotated[int, Field(ge=1, le=3)]


class V2ResearchStoppingReason(StrEnum):
    SUFFICIENT_SOURCE_POOL = "sufficient_source_pool"
    NO_USEFUL_NEW_DIRECTION = "no_useful_new_direction"
    DUPLICATE_HEAVY = "duplicate_heavy"
    PROVIDER_ELIGIBILITY_EXHAUSTED = "provider_eligibility_exhausted"
    BUDGET = "budget"
    HARD_ROUND_LIMIT = "hard_round_limit"
    DEGRADED_GAP_SEARCH_AGENT = "degraded_gap_search_agent"
    INVALID_SEARCH_AGENT_PLAN = "invalid_search_agent_plan"


class V2ResearchStoppingDisclosure(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: V2ResearchStoppingReason
    explanation: NonEmptyStr
    completed_rounds: Annotated[int, Field(ge=1, le=4)]


class V2ReleaseValidation(StrictModel):
    """The v2 release decision hashes the complete rendered output, not just evidence text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_validation: ValidationResult
    valid: bool
    errors: tuple[ValidationError, ...]
    validator_config_version: NonEmptyStr
    validated_at: datetime
    rendered_output_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    _validated_at_is_aware = field_validator("validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_release_state(self) -> V2ReleaseValidation:
        if self.valid and not self.evidence_validation.valid:
            raise ValueError("a v2 release cannot bypass failed evidence validation")
        if self.valid:
            if self.errors or self.rendered_output_hash is None:
                raise ValueError("valid v2 releases require no errors and a complete output hash")
        elif not self.errors or self.rendered_output_hash is not None:
            raise ValueError("invalid v2 releases require errors and no output hash")
        return self


class V2FinalResearchOutput(StrictModel):
    """Complete v2 result envelope, separating Ledger facts from research disclosures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    synthesis: SynthesisOutput
    recommended_source_ids: tuple[UUID, ...]
    recommended_sources: tuple[V2ResultSource, ...]
    all_surviving_sources: tuple[V2ResultSource, ...]
    unresolved_material_gaps: tuple[V2UnresolvedMaterialGap, ...]
    claim_coverage_map: tuple[V2ClaimCoverageAssessment, ...] = Field(default=(), max_length=6)
    gap_reconciliation: V2GapCoverageReconciliation | None = None
    stopping: V2ResearchStoppingDisclosure
    created_at: datetime
    release_validation: V2ReleaseValidation

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_final_output(self) -> V2FinalResearchOutput:
        if self.synthesis.run_id != self.run_id:
            raise ValueError("v2 final output synthesis must match the run")
        all_ids = tuple(item.source_id for item in self.all_surviving_sources)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("v2 final output sources must be unique")
        if any(not self.directions.permits(item.direction) for item in self.all_surviving_sources):
            raise ValueError("v2 final output cannot expose disabled-direction sources")
        if any(
            not self.directions.permits(item.direction) for item in self.unresolved_material_gaps
        ):
            raise ValueError("v2 final output cannot expose disabled-direction gaps")
        recommended_ids = tuple(item.source_id for item in self.recommended_sources)
        if recommended_ids != self.recommended_source_ids:
            raise ValueError("recommended source list must reproduce recommendation IDs")
        if any(not item.recommended for item in self.recommended_sources):
            raise ValueError("recommended source list may contain only recommended sources")
        if set(recommended_ids) - set(all_ids):
            raise ValueError("recommended source IDs must exist in surviving source list")
        if self.gap_reconciliation is not None:
            if self.gap_reconciliation.run_id != self.run_id:
                raise ValueError("Gap reconciliation must match the final-output run")
            if self.claim_coverage_map != self.gap_reconciliation.claim_coverage_map:
                raise ValueError("final claim coverage must match the Gap reconciliation")
            unresolved_ids = tuple(item.gap_id for item in self.unresolved_material_gaps)
            expected_ids = tuple(
                item.gap.gap_id
                for item in self.gap_reconciliation.records
                if item.state is not V2GapCoverageState.COVERED
            )
            if unresolved_ids != expected_ids:
                raise ValueError(
                    "final unresolved gaps must exactly reproduce non-covered reconciliation gaps"
                )
        return self


class ValidationError(StrictModel):
    code: ValidationErrorCode
    location: NonEmptyStr
    message: NonEmptyStr


class ValidationResult(StrictModel):
    run_id: UUID
    valid: bool
    errors: list[ValidationError]
    validator_config_version: NonEmptyStr
    validated_at: datetime
    rendered_brief_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    _validated_at_is_aware = field_validator("validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_result(self) -> ValidationResult:
        if self.valid and self.errors:
            raise ValueError("valid results cannot include errors")
        if self.valid and self.rendered_brief_hash is None:
            raise ValueError("valid results require rendered_brief_hash")
        if not self.valid and not self.errors:
            raise ValueError("invalid results require at least one validation error")
        if not self.valid and self.rendered_brief_hash is not None:
            raise ValueError("invalid results cannot include rendered_brief_hash")
        return self


class RunManifest(StrictModel):
    run_id: UUID
    status: RunStatus
    raw_claim: NonEmptyStr
    current_stage: Stage
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)
    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)
    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_completion(self) -> RunManifest:
        if self.status is RunStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed runs require completed_at")
        return self


class OrchestrationCheckpoint(StrictModel):
    run_id: UUID
    stage_key: NonEmptyStr
    status: CheckpointStatus
    failure_reason: NonEmptyStr | None = None
    updated_at: datetime

    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_status_shape(self) -> OrchestrationCheckpoint:
        if self.status is CheckpointStatus.FAILED and self.failure_reason is None:
            raise ValueError("failed checkpoints require a failure reason")
        if self.status is not CheckpointStatus.FAILED and self.failure_reason is not None:
            raise ValueError("only failed checkpoints may carry a failure reason")
        return self


class PersistedStageArtifact(StrictModel):
    run_id: UUID
    artifact_key: NonEmptyStr
    artifact_type: NonEmptyStr
    payload_json: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class ProviderRunContract(StrictModel):
    """Immutable compatibility identity required to create or resume a provider run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    fingerprint_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    provider_identity: NonEmptyStr
    adapter_identity: NonEmptyStr
    model_identity: NonEmptyStr
    prompt_identity: NonEmptyStr
    schema_identity: NonEmptyStr
    normalization_identity: NonEmptyStr
    policy_identity: NonEmptyStr
    repository_revision: NonEmptyStr
    payload_json: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_canonical_identity(self) -> ProviderRunContract:
        payload = parse_provider_contract_payload(self.payload_json)
        for field_name in (
            "provider_identity",
            "adapter_identity",
            "model_identity",
            "prompt_identity",
            "schema_identity",
            "normalization_identity",
            "policy_identity",
            "repository_revision",
        ):
            if payload[field_name] != getattr(self, field_name):
                raise ValueError(f"payload_json {field_name} does not match duplicated field")
        expected_fingerprint = provider_contract_fingerprint(self.payload_json)
        if self.fingerprint_sha256 != expected_fingerprint:
            raise ValueError(
                "fingerprint_sha256 does not match the canonical provider contract payload"
            )
        return self


class ModelUsageAccounting(StrictModel):
    """Exact totals, known subtotals, and conservative exposure for model attempts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exact_total_tokens: NonNegativeInt | None
    exact_total_cost_usd: ExactUSD | None
    known_token_subtotal: NonNegativeInt
    known_cost_subtotal_usd: ExactUSD
    token_complete: bool
    cost_complete: bool
    missing_token_attempt_ids: tuple[UUID, ...] = ()
    missing_cost_attempt_ids: tuple[UUID, ...] = ()
    conservative_reserved_tokens: NonNegativeInt | None
    conservative_reserved_cost_usd: ExactUSD | None

    @model_validator(mode="after")
    def validate_completeness(self) -> ModelUsageAccounting:
        if self.token_complete != (not self.missing_token_attempt_ids):
            raise ValueError("token completeness must match missing token attempts")
        if self.cost_complete != (not self.missing_cost_attempt_ids):
            raise ValueError("cost completeness must match missing cost attempts")
        if self.token_complete:
            if self.exact_total_tokens != self.known_token_subtotal:
                raise ValueError("complete token accounting requires its exact known subtotal")
        elif self.exact_total_tokens is not None:
            raise ValueError("incomplete token accounting cannot carry an exact total")
        if self.cost_complete:
            if self.exact_total_cost_usd != self.known_cost_subtotal_usd:
                raise ValueError("complete cost accounting requires its exact known subtotal")
        elif self.exact_total_cost_usd is not None:
            raise ValueError("incomplete cost accounting cannot carry an exact total")
        return self


class ModelUsageMetadata(StrictModel):
    input_tokens: NonNegativeInt | None = None
    cached_input_tokens: NonNegativeInt | None = None
    uncached_input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    total_tokens: NonNegativeInt | None = None
    cost_usd: ExactUSD | None = None

    @model_validator(mode="after")
    def validate_token_total(self) -> ModelUsageMetadata:
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        if self.cached_input_tokens is not None or self.uncached_input_tokens is not None:
            if (
                self.input_tokens is None
                or self.cached_input_tokens is None
                or self.uncached_input_tokens is None
                or self.cached_input_tokens + self.uncached_input_tokens != self.input_tokens
            ):
                raise ValueError(
                    "cached and uncached input tokens must exactly partition input_tokens"
                )
        return self


class ModelRouteAttempt(StrictModel):
    run_id: UUID
    operation_id: UUID
    attempt_id: UUID
    stage: NonEmptyStr
    output_type: NonEmptyStr
    model_alias: NonEmptyStr
    pinned_model_snapshot: NonEmptyStr | None = None
    route_index: NonNegativeInt
    attempt_number: PositiveInt
    input_artifact_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    status: ModelAttemptStatus
    retry_reason: NonEmptyStr | None = None
    escalation_reason: NonEmptyStr | None = None
    failure_code: NonEmptyStr | None = None
    failure_reason: NonEmptyStr | None = None
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: Annotated[float, Field(ge=0.0)] | None = None
    reserved_tokens: NonNegativeInt | None = None
    reserved_cost_usd: ExactUSD | None = None
    usage: ModelUsageMetadata | None = None
    output_json: str | None = None

    _started_at_is_aware = field_validator("started_at")(_validate_aware_datetime)
    _ended_at_is_aware = field_validator("ended_at")(_validate_aware_datetime)

    @field_validator("input_artifact_ids")
    @classmethod
    def validate_input_artifact_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("input_artifact_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_attempt_shape(self) -> ModelRouteAttempt:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("attempt ended_at cannot precede started_at")
        if self.status is ModelAttemptStatus.RUNNING:
            if any(
                value is not None
                for value in (
                    self.ended_at,
                    self.latency_ms,
                    self.failure_code,
                    self.failure_reason,
                    self.output_json,
                )
            ):
                raise ValueError("running attempts cannot carry completion fields")
            return self
        if self.ended_at is None or self.latency_ms is None:
            raise ValueError("finished attempts require end time and latency")
        if self.status is ModelAttemptStatus.COMPLETED:
            if self.output_json is None:
                raise ValueError("completed attempts require serialized typed output")
            if self.failure_code is not None or self.failure_reason is not None:
                raise ValueError("completed attempts cannot carry failure metadata")
        else:
            if self.failure_code is None or self.failure_reason is None:
                raise ValueError("failed attempts require failure code and reason")
        return self


class RunCancellationRequest(StrictModel):
    run_id: UUID
    requested_at: datetime
    reason: NonEmptyStr

    _requested_at_is_aware = field_validator("requested_at")(_validate_aware_datetime)


class ModelInvocationRecord(StrictModel):
    run_id: UUID
    invocation_id: UUID
    stage: Stage
    prompt_version: NonEmptyStr
    model_name: NonEmptyStr
    input_artifact_id: UUID
    output_artifact_id: UUID | None = None
    status: Literal["completed", "failed"]
    invoked_at: datetime

    _invoked_at_is_aware = field_validator("invoked_at")(_validate_aware_datetime)
