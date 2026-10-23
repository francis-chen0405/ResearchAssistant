"""Source selection and budget-aware deep-analysis queue handoffs."""

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
    V2PreviewResult,
)
from researchassistant.contracts.metadata_ranking import MetadataRank
from researchassistant.contracts.model_contracts import (
    DiscoveryProvider,
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
    StrictModel,
    _validate_aware_datetime,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageAssessment as V2ClaimCoverageAssessment,
)
from researchassistant.contracts.research_coverage import (
    V2SourceSelectionGap as V2SourceSelectionGap,
)
from researchassistant.contracts.research_coverage import (
    validate_v2_source_selection_gap_history as validate_v2_source_selection_gap_history,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.contracts.research_policy import (
    V2_DEEP_ANALYSIS_QUEUE_POLICY_IDENTITY as V2_DEEP_ANALYSIS_QUEUE_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP as V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
)
from researchassistant.contracts.research_policy import (
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP as V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
)
from researchassistant.contracts.research_policy import (
    V2_FOUR_ROUND_SURVIVOR_LIMIT,
    V2_PREVIEW_SELECTION_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_SOURCE_SELECTION_POLICY_IDENTITY as V2_SOURCE_SELECTION_POLICY_IDENTITY,
)


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
    query_text: NonEmptyStr | None
    graph_action: V2GraphNeighborAction | None = None
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(max_length=6)
    provenance_version: Literal[1, 2] = 1
    direction: ResearchDirection | None = None

    @model_validator(mode="after")
    def validate_discovery_action(self) -> V2SourceSelectionSearchProvenance:
        if (self.provenance_version == 2) != (self.direction is not None):
            raise ValueError("query-direction provenance v2 requires its original direction")
        if self.graph_action is None:
            if self.query_text is None:
                raise ValueError("text discovery requires its query")
        elif (
            self.query_text is not None
            or self.query_id != self.graph_action.artifact_id
            or self.provider != self.graph_action.provider
            or self.round_number != self.graph_action.round_number
            or self.targeted_gap_ids != self.graph_action.target_gap_ids
            or (self.direction is not None and self.direction is not self.graph_action.direction)
        ):
            raise ValueError("selection provenance differs from graph action")
        return self

    @model_serializer(mode="wrap")
    def omit_absent_graph_action(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value = handler(self)
        if self.graph_action is None:
            value.pop("graph_action", None)
        if self.provenance_version == 1:
            value.pop("provenance_version", None)
            value.pop("direction", None)
        return value


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
    probe_passages: tuple[V2SourceSelectionProbePassage, ...] = Field(max_length=5)
    search_provenance: tuple[V2SourceSelectionSearchProvenance, ...] = Field(
        min_length=1, max_length=20
    )
    snapshot_word_count: PositiveInt
    deep_analysis_input_tokens: PositiveInt

    preview: V2PreviewResult | None = None
    metadata_ranks: tuple[MetadataRank, ...] = Field(default=(), max_length=300)
    alternate_source_urls: tuple[str, ...] = Field(default=(), max_length=240)

    @model_serializer(mode="wrap")
    def historical_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        if self.preview is None:
            data.pop("preview", None)
        if not self.metadata_ranks:
            data.pop("metadata_ranks", None)
        if not self.alternate_source_urls:
            data.pop("alternate_source_urls", None)
        return data

    @model_validator(mode="after")
    def validate_candidate_provenance(self) -> V2SourceSelectionCandidate:
        if not self.probe_passages and (
            self.preview is None
            or self.preview.request.preview_identity != "source-claim-preview-v2"
        ):
            raise ValueError("historical selection candidates require Probe passages")
        if self.preview is not None and (
            self.preview.request.source_id != self.source_id
            or self.preview.request.direction != self.direction
        ):
            raise ValueError("selection preview source/lane mismatch")
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
    survivors: tuple[V2SourceSelectionCandidate, ...] = Field(
        min_length=1, max_length=V2_FOUR_ROUND_SURVIVOR_LIMIT
    )
    gap_history: tuple[V2SourceSelectionGap, ...] = Field(max_length=18)
    gap_reporting_policy: Literal["legacy", "conservative-v1"] = "legacy"
    latest_gap_coverage: tuple[V2ClaimCoverageAssessment, ...] = Field(default=(), max_length=6)
    model_view_policy: Literal["compact-selection-v1"] | None = None
    policy_identity: Literal[
        "researchassistant-v2-phase-8-source-selection-v1",
        "researchassistant-v2-phase-8-source-selection-v2",
        "researchassistant-v2-phase-8-source-selection-v3",
    ] = V2_SOURCE_SELECTION_POLICY_IDENTITY

    @model_serializer(mode="wrap")
    def omit_legacy_view_policy(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        if self.model_view_policy is None:
            data.pop("model_view_policy", None)
        return data

    @model_validator(mode="after")
    def validate_complete_pool(self) -> V2SourceSelectionInput:
        if (
            self.policy_identity != V2_PREVIEW_SELECTION_POLICY_IDENTITY
            and len(self.survivors) > 75
        ):
            raise ValueError("historical source-selection policies permit at most 75 survivors")
        for candidate in self.survivors:
            if candidate.preview is not None and (
                candidate.preview.run_id != self.run_id
                or candidate.preview.request.exact_claim != self.exact_claim
                or candidate.preview.request.directions != self.directions
            ):
                raise ValueError("selection preview run/claim/directions mismatch")
        source_ids = tuple(item.source_id for item in self.survivors)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source-selection survivor IDs must be unique")
        gap_keys = tuple((item.assessed_after_round, item.gap_id) for item in self.gap_history)
        if len(gap_keys) != len(set(gap_keys)):
            raise ValueError("source-selection Gap history entries must be unique per round")
        validate_v2_source_selection_gap_history(self.gap_history)
        for item in (*self.survivors, *self.gap_history):
            self.directions.require_permitted(item.direction)
        gap_directions = {gap.gap_id: gap.direction for gap in self.gap_history}
        for source in self.survivors:
            for provenance in source.search_provenance:
                if provenance.direction is None:
                    continue  # Preserve recorded v1 interpretation for historical reads.
                self.directions.require_permitted(provenance.direction)
                if any(
                    gap_directions.get(gap_id) is not provenance.direction
                    for gap_id in provenance.targeted_gap_ids
                ):
                    raise ValueError("search provenance Gap IDs differ from their query direction")
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


# Preserve the historical public class identity for persisted consumers.
V2SourceSelectionProbePassage.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionSearchProvenance.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionCandidate.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionInput.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionRecommendation.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionModelOutput.__module__ = "researchassistant.contracts.model_research"
V2DeepAnalysisBudget.__module__ = "researchassistant.contracts.model_research"
V2DeepAnalysisBudgetReason.__module__ = "researchassistant.contracts.model_research"
V2DeepAnalysisSourceStatus.__module__ = "researchassistant.contracts.model_research"
V2DeepAnalysisTokenReservation.__module__ = "researchassistant.contracts.model_research"
V2DeepAnalysisQueuePlan.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionAttempt.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionQueueResult.__module__ = "researchassistant.contracts.model_research"
