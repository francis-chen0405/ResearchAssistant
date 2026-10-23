"""Typed adaptive-search handoffs and shared checkpoint keys."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
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

from researchassistant.contracts.models import (
    StrictModel,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchConceptsOutput,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchQuery,
    V2SearchAgentInput,
    V2SurvivingSource,
)
from researchassistant.contracts.paper_identity import ConfirmedPaperGroup, ConfirmedPaperLocation
from researchassistant.contracts.query_planning import (
    V2NeighborhoodSearchOutput,
)
from researchassistant.contracts.search import SearchResult
from researchassistant.research.research_governor import (
    V2RoundThreeGovernorDecision,
)


class V2AdaptivePlanValidationError(ValueError):
    """A Search Agent proposal failed deterministic semantic plan validation."""

    def __init__(self, message: str, *, code: str = "invalid_plan") -> None:
        super().__init__(message)
        self.code = code


class V2AdaptiveNoEligibleProviderError(LookupError):
    """No enabled provider remains within its application-owned search ceiling."""


class V2AdaptiveBudgetError(LookupError):
    """Adaptive Search Agent work cannot fit the protected application budget."""


class V2AdaptiveNoContinuationError(LookupError):
    """The persisted gap result does not authorize another adaptive search round."""


class V2AdaptiveCancellationError(RuntimeError):
    """Cancellation observed before a planning attempt."""


class V2PlanningAttempt(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    attempt_id: UUID
    round_number: Literal[2, 3]
    attempt_number: int = Field(ge=1, le=2)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str
    started_at: datetime

    @field_validator("started_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware_datetime(value)


class V2PlanningOutcome(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    candidate: (
        V2AdaptiveSearchModelOutput
        | V2AdaptiveSearchConceptsOutput
        | V2NeighborhoodSearchOutput
        | None
    ) = None
    rejection_code: str | None = None
    explanation: str | None = None
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_outcome(self) -> V2PlanningOutcome:
        if self.rejection_code is None:
            if self.candidate is None or self.explanation is not None:
                raise ValueError("Accepted planning outcomes require a candidate and no failure")
        elif self.explanation is None:
            raise ValueError("Rejected planning outcomes require a diagnostic")
        return self


class V2PlanningRepairInput(V2SearchAgentInput):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rejected: V2PlanningOutcome
    instruction: str = (
        "Repair the entire proposal using the validation feedback. All original controls, "
        "Gap IDs, query history and caps still apply. Do not merely add one word or reorder "
        "a rejected query. Return only the requested search output schema."
    )


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("adaptive continuation timestamps must be timezone-aware")
    return value


class V2AdaptiveRoundStatus(StrEnum):
    COMPLETED = "completed"
    DEGRADED = "degraded"
    CANCELLED = "cancelled"


class V2AdaptiveStopCode(StrEnum):
    ROUND_ONE_COMPLETE = "round_one_complete"
    ROUND_TWO_COMPLETE = "round_two_complete"
    ROUND_THREE_COMPLETE = "round_three_complete"
    ROUND_FOUR_COMPLETE = "round_four_complete"
    NO_ELIGIBLE_PROVIDER = "no_eligible_provider"
    NO_NEW_QUERY = "no_materially_new_query"
    BUDGET = "insufficient_budget"
    CANCELLED = "cancelled"
    PROVIDER_FAILURE = "provider_failure"
    INVALID_SEARCH_AGENT_PLAN = "invalid_search_agent_plan"
    GAP_ANALYSIS_DEGRADED = "gap_analysis_degraded"
    GOVERNOR_REJECTED = "governor_rejected"


class V2AdaptiveBudgetState(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls_remaining: int = Field(ge=0)
    tokens_remaining: int | None = Field(default=None, ge=0)
    cost_remaining_usd: Decimal | None = Field(default=None, ge=0)
    protected_downstream_model_calls: int = Field(default=1, ge=0)
    protected_downstream_tokens: int = Field(default=0, ge=0)
    protected_downstream_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)
    round_three_complete_workload_reservable: bool = True


class V2SearchAgentReservation(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(ge=1)
    output_tokens: int = Field(ge=1)
    reserved_tokens: int = Field(ge=1)
    reserved_cost_usd: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self) -> V2SearchAgentReservation:
        if self.input_tokens + self.output_tokens != self.reserved_tokens:
            raise ValueError("Search Agent token reservation must be internally consistent")
        return self


class V2AdaptivePlannedRound(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    plan: V2AdaptiveRoundPlan
    reservation: V2SearchAgentReservation


class V2AdaptiveSearchOutcome(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: V2AdaptiveSearchQuery
    succeeded: bool
    results: tuple[SearchResult, ...] = ()
    failure_code: str | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> V2AdaptiveSearchOutcome:
        if self.succeeded:
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("successful adaptive searches cannot carry a failure")
        elif self.results or self.failure_code is None or self.failure_message is None:
            raise ValueError("failed adaptive searches require paired failure fields")
        return self


class V2AdaptiveSearchResults(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: int = Field(ge=2, le=4)
    outcomes: tuple[V2AdaptiveSearchOutcome, ...]
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware_datetime)


class V2MergedSurvivor(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    research_round: int = Field(ge=1, le=4)
    source_url: str = Field(min_length=1)
    survivor: V2SurvivingSource
    paper_locations: tuple[ConfirmedPaperLocation, ...] = Field(default=(), max_length=240)

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        if not self.paper_locations:
            data.pop("paper_locations", None)
        return data

    @model_validator(mode="after")
    def validate_paper_locations(self) -> V2MergedSurvivor:
        if self.paper_locations:
            ConfirmedPaperGroup(
                canonical_source_id=self.survivor.cluster_id,
                doi=self.paper_locations[0].doi,
                locations=self.paper_locations,
            )
            canonical = next(
                location
                for location in self.paper_locations
                if location.source_id == self.survivor.cluster_id
            )
            if (
                canonical.snapshot_id != self.survivor.snapshot_id
                or canonical.snapshot_hash != self.survivor.snapshot_sha256
                or canonical.source_url != self.source_url
                or canonical.research_round != self.research_round
                or canonical.direction != self.survivor.direction
            ):
                raise ValueError("canonical paper location differs from retained source")
        return self


class V2MergedSurvivorPool(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    sources: tuple[V2MergedSurvivor, ...]

    @model_validator(mode="after")
    def validate_source_ownership(self) -> V2MergedSurvivorPool:
        ids = [source.survivor.cluster_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("merged survivors require unique source IDs")
        members = [
            location.source_id
            for source in self.sources
            for location in source.paper_locations
            if location.source_id != source.survivor.cluster_id
        ]
        if len(members) != len(set(members)) or set(members).intersection(ids):
            raise ValueError("paper mirror belongs to multiple retained identities")
        return self


class V2AdaptiveRoundExecution(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: int = Field(ge=2, le=4)
    targeted_gap_ids: tuple[str, ...]
    status: V2AdaptiveRoundStatus
    planned_query_count: int = Field(ge=0)
    completed_query_count: int = Field(ge=0)
    failed_query_count: int = Field(ge=0)
    new_source_count: int = Field(ge=0)
    duplicate_source_count: int = Field(ge=0)
    survivor_additions: int = Field(ge=0)
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware_datetime)


class V2AdaptiveStoppingDecision(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    completed_rounds: int = Field(ge=1, le=4)
    stop_code: V2AdaptiveStopCode
    stopping_reason: str = Field(min_length=1)
    decided_at: datetime

    _decided_at_is_aware = field_validator("decided_at")(_aware_datetime)


class V2AdaptiveContinuationResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    rounds: tuple[V2AdaptiveRoundExecution, ...]
    merged_survivors: V2MergedSurvivorPool
    stopping_decision: V2AdaptiveStoppingDecision
    governor_decision: V2RoundThreeGovernorDecision | None = None
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware_datetime)


def round_artifact_key(round_number: int, suffix: str) -> str:
    """Return the versioned immutable key for one adaptive round artifact."""
    if round_number == 4:
        return f"post-phase-13-round-4-{suffix}-v1"
    return f"phase-7-round-{round_number}-{suffix}"


def _cancelled(callback: Callable[[], bool] | None) -> bool:
    return bool(callback and callback())


def _utc_now() -> datetime:
    return datetime.now(UTC)


# Preserve the historical public class identity for persisted consumers.
V2AdaptivePlanValidationError.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveNoEligibleProviderError.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveBudgetError.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveNoContinuationError.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveCancellationError.__module__ = "researchassistant.agents.v2_adaptive_search"
V2PlanningAttempt.__module__ = "researchassistant.agents.v2_adaptive_search"
V2PlanningOutcome.__module__ = "researchassistant.agents.v2_adaptive_search"
V2PlanningRepairInput.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveRoundStatus.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveStopCode.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveBudgetState.__module__ = "researchassistant.agents.v2_adaptive_search"
V2SearchAgentReservation.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptivePlannedRound.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveSearchOutcome.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveSearchResults.__module__ = "researchassistant.agents.v2_adaptive_search"
V2MergedSurvivor.__module__ = "researchassistant.agents.v2_adaptive_search"
V2MergedSurvivorPool.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveRoundExecution.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveStoppingDecision.__module__ = "researchassistant.agents.v2_adaptive_search"
V2AdaptiveContinuationResult.__module__ = "researchassistant.agents.v2_adaptive_search"
