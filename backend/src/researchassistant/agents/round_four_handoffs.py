"""Typed Round-4 state, durable checkpoint keys and shared read helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveContinuationResult,
    V2AdaptiveRoundStatus,
)
from researchassistant.contracts.models import (
    StrictModel,
    V2GapAnalysisOutput,
    V2RoundFourGovernorDecision,
)
from researchassistant.providers.v2_budget import V2CancellationRequested
from researchassistant.storage.store import read_v2_artifact

V2_POST13_GAP_AFTER_ROUND_THREE_KEY = "post-phase-13-gap-analysis-after-round-3-v1"


V2_POST13_ROUND_FOUR_GOVERNOR_KEY = "post-phase-13-round-4-governor-decision-v1"


V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY = "post-phase-13-round-4-terminal-outcome-v1"


V2_POST13_ROUND_FOUR_PLAN_KEY = "post-phase-13-round-4-plan-v1"


V2_POST13_ROUND_FOUR_POST_PLAN_FACTS_KEY = "post-phase-13-round-4-post-plan-facts-v1"


V2_POST13_ROUND_FOUR_COMPLETION_KEY = "post-phase-13-round-4-completion-v1"


V2_POST13_GAP_RECONCILIATION_KEY = "post-phase-13-gap-coverage-reconciliation-v1"


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Round-4 post-plan timestamps must be timezone-aware")
    return value


class V2RoundFourBudgetError(LookupError):
    """The bounded fourth-round workload cannot preserve the downstream reserve."""


class V2RoundFourAuthorizationError(LookupError):
    """Round-4 Search Agent work requires a persisted application authorization."""


class V2RoundFourPostPlanFacts(StrictModel):
    """Actual accepted-query and execution facts recorded after Round-4 planning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    accepted_novel_query_ids: tuple[UUID, ...] = Field(min_length=1, max_length=8)
    accepted_query_count: int = Field(ge=1, le=8)
    executed_query_count: int = Field(ge=0)
    successful_query_count: int = Field(ge=0)
    new_source_count: int = Field(ge=0)
    survivor_additions: int = Field(ge=0)
    productive_execution: bool
    round_status: V2AdaptiveRoundStatus
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware_datetime)

    @model_validator(mode="after")
    def validate_execution_facts(self) -> V2RoundFourPostPlanFacts:
        if self.accepted_query_count != len(self.accepted_novel_query_ids):
            raise ValueError("post-plan accepted query count must match its query IDs")
        if len(set(self.accepted_novel_query_ids)) != self.accepted_query_count:
            raise ValueError("post-plan accepted query IDs must be unique")
        if self.executed_query_count > self.accepted_query_count:
            raise ValueError("executed queries cannot exceed accepted queries")
        if self.successful_query_count > self.executed_query_count:
            raise ValueError("successful queries cannot exceed executed queries")
        if self.productive_execution != (self.survivor_additions > 0):
            raise ValueError("post-plan productivity must reflect survivor additions")
        return self


class V2RoundFourRunResult(StrictModel):
    """Restart-safe post-Round-3 outcome, including the immutable Gap checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    continuation: V2AdaptiveContinuationResult
    post_round_three_gap: V2GapAnalysisOutput
    governor_decision: V2RoundFourGovernorDecision
    post_plan_facts: V2RoundFourPostPlanFacts | None = None
    resumed: bool = False


def _read(path: str, run_id: UUID, key: str) -> str | None:
    try:
        return read_v2_artifact(path, run_id, key).payload_json
    except KeyError:
        return None


def _cancelled(callback: Callable[[], bool] | None) -> bool:
    return callback is not None and callback()


def _cancellation_from_error(error: BaseException) -> V2CancellationRequested | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, V2CancellationRequested):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


# Preserve the historical public class identity for persisted consumers.
V2RoundFourBudgetError.__module__ = "researchassistant.agents.v2_round_four"
V2RoundFourAuthorizationError.__module__ = "researchassistant.agents.v2_round_four"
V2RoundFourPostPlanFacts.__module__ = "researchassistant.agents.v2_round_four"
V2RoundFourRunResult.__module__ = "researchassistant.agents.v2_round_four"
