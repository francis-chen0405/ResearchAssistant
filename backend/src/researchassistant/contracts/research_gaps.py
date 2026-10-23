"""Gap Analysis requests, attempts and bounded results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from researchassistant.common.money import ExactUSD
from researchassistant.contracts.discovery_v2 import (
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
from researchassistant.contracts.research_acquisition import (
    V2AcquisitionProvider as V2AcquisitionProvider,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageAssessment as V2ClaimCoverageAssessment,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageDimension as V2ClaimCoverageDimension,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageFocus as V2ClaimCoverageFocus,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageSpecification as V2ClaimCoverageSpecification,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageState as V2ClaimCoverageState,
)
from researchassistant.contracts.research_coverage import (
    V2MaterialGap as V2MaterialGap,
)
from researchassistant.contracts.research_coverage import (
    validate_v2_gap_identity_continuity as validate_v2_gap_identity_continuity,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.contracts.research_policy import (
    V2_GAP_ANALYSIS_POLICY_IDENTITY as V2_GAP_ANALYSIS_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY as V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
)


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
    query_text: NonEmptyStr | None
    graph_action: V2GraphNeighborAction | None = None
    round_number: Literal[1, 2, 3, 4] = 1

    @model_validator(mode="after")
    def validate_graph_reference(self) -> V2GapAttemptedQuery:
        if self.graph_action is None:
            if self.query_text is None:
                raise ValueError("text attempted queries require query_text")
        elif (
            self.query_text is not None
            or self.query_id != self.graph_action.artifact_id
            or self.direction is not self.graph_action.direction
            or self.provider != self.graph_action.provider
            or self.round_number != self.graph_action.round_number
        ):
            raise ValueError("graph attempted query must preserve its action without query text")
        return self

    @model_serializer(mode="wrap")
    def omit_absent_graph_action(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value = handler(self)
        if self.graph_action is None:
            value.pop("graph_action", None)
        return value


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


class V2GapAnalysisInput(StrictModel):
    """Strict, bounded Round-1 strategy input; acquired documents are intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    completed_round: Literal[1, 2, 3] = 1
    attempted_queries: tuple[V2GapAttemptedQuery, ...] = Field(max_length=48)
    surviving_sources: tuple[V2GapSurvivingSourceMetadata, ...] = Field(max_length=180)
    probe_passages: tuple[V2GapProbePassage, ...] = Field(max_length=40)
    source_families: tuple[V2GapSourceFamily, ...] = Field(max_length=180)
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
        "researchassistant-v2-adaptive-gap-analysis-v2",
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
            if self.input.policy_identity in {
                V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
                "researchassistant-v2-adaptive-gap-analysis-v2",
            }:
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


# Preserve the historical public class identity for persisted consumers.
V2GapBudgetState.__module__ = "researchassistant.contracts.model_research"
V2GapAttemptedQuery.__module__ = "researchassistant.contracts.model_research"
V2GapSurvivingSourceMetadata.__module__ = "researchassistant.contracts.model_research"
V2GapProbePassage.__module__ = "researchassistant.contracts.model_research"
V2GapSourceFamily.__module__ = "researchassistant.contracts.model_research"
V2GapDuplicatePattern.__module__ = "researchassistant.contracts.model_research"
V2GapAcquisitionFailure.__module__ = "researchassistant.contracts.model_research"
V2GapSearchDirection.__module__ = "researchassistant.contracts.model_research"
V2GapAnalysisInput.__module__ = "researchassistant.contracts.model_research"
V2GapAnalysisModelOutput.__module__ = "researchassistant.contracts.model_research"
V2GapAnalysisResult.__module__ = "researchassistant.contracts.model_research"
V2GapAnalysisState.__module__ = "researchassistant.contracts.model_research"
V2GapReservation.__module__ = "researchassistant.contracts.model_research"
V2GapAnalysisAttempt.__module__ = "researchassistant.contracts.model_research"
V2GapAnalysisOutput.__module__ = "researchassistant.contracts.model_research"
