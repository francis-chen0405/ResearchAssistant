"""Round-4 authorization, reservation and coverage reconciliation contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from researchassistant.common.money import ExactUSD
from researchassistant.contracts.model_contracts import (
    NonEmptyStr,
    NonNegativeInt,
    StrictModel,
    _validate_aware_datetime,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageAssessment as V2ClaimCoverageAssessment,
)
from researchassistant.contracts.research_coverage import (
    V2MaterialGap as V2MaterialGap,
)
from researchassistant.contracts.research_policy import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY as V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
)


class V2RoundFourDecisionCode(StrEnum):
    """Stable fail-closed outcomes for the one permitted post-Round-3 continuation."""

    AUTHORIZED = "authorized"
    NO_MATERIAL_GAPS = "no_material_gaps"
    NO_PRODUCTIVE_SEARCH = "no_productive_search"
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
    round_four_governor_decision: V2RoundFourGovernorDecision | None = None
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
        if self.round_four_governor_decision is not None:
            if self.round_four_governor_decision.run_id != self.run_id:
                raise ValueError("Round-4 Governor decision must match the reconciliation run")
            if self.round_four_governor_decision.authorized and not self.round_four_attempted:
                raise ValueError("authorized Round 4 must be recorded as attempted")
        return self


# Preserve the historical public class identity for persisted consumers.
V2RoundFourDecisionCode.__module__ = "researchassistant.contracts.model_research"
V2RoundFourTerminalOutcome.__module__ = "researchassistant.contracts.model_research"
V2RoundFourReservation.__module__ = "researchassistant.contracts.model_research"
V2RoundFourGovernorDecision.__module__ = "researchassistant.contracts.model_research"
V2GapCoverageState.__module__ = "researchassistant.contracts.model_research"
V2GapCoverageRecord.__module__ = "researchassistant.contracts.model_research"
V2GapCoverageReconciliation.__module__ = "researchassistant.contracts.model_research"
