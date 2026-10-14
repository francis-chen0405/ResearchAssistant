"""Immutable exact-extraction handoffs and recorded policy validation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from researchassistant.contracts.models import (
    CandidateQuoteBlock,
    ResearchDirection,
    SourceSnapshot,
    StrictModel,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystExtractionFailure,
    V2SourceSelectionQueueResult,
)

V2_EXTRACTION_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-exact-extraction-analyzer-admission-v3"
)


V2_EXTRACTION_MAX_ATTEMPTS = 2


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 extraction timestamps must be timezone-aware")
    return value


class V2ExtractionState(StrEnum):
    EXTRACTED = "extracted"
    FAILED = "failed"
    SOURCE_BUDGET_BLOCKED = "source_budget_blocked"
    BUDGET_EXHAUSTED = "budget_exhausted"


class V2ExtractionLLMInput(StrictModel):
    """Exact immutable source surface exposed to the selection-only Extractor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    exact_claim: str = Field(min_length=1)
    snapshot_id: UUID
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truncated: bool
    untrusted_source_text: str = Field(min_length=1)
    selectable_source_text: str = Field(min_length=1)


class V2NumberedUntrustedSource(StrictModel):
    """One complete numbered source, treated as data rather than instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    selectable_source_text: str = Field(min_length=1)


class V2ExtractionPromptInput(StrictModel):
    """Render the full source once while retaining its immutable identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    exact_claim: str = Field(min_length=1)
    snapshot_id: UUID
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truncated: bool
    UNTRUSTED_SOURCE_TEXT: V2NumberedUntrustedSource


class V2ExtractionSourceResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    state: V2ExtractionState
    attempts: int = Field(ge=1, le=V2_EXTRACTION_MAX_ATTEMPTS)
    candidate: CandidateQuoteBlock | None = None
    failure: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> V2ExtractionSourceResult:
        if self.state is V2ExtractionState.EXTRACTED:
            if self.candidate is None or self.failure is not None:
                raise ValueError("successful extraction requires one candidate and no failure")
        elif self.candidate is not None or self.failure is None:
            raise ValueError("failed extraction requires a failure and no candidate")
        return self


class V2ExactExtractionResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    queue_result: V2SourceSelectionQueueResult
    sources: tuple[V2ExtractionSourceResult, ...]
    completed_at: datetime
    policy_identity: str = V2_EXTRACTION_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_aware)

    @model_validator(mode="after")
    def validate_queue_order(self) -> V2ExactExtractionResult:
        if self.queue_result.run_id != self.run_id:
            raise ValueError("extraction queue must match the run")
        if tuple(item.source_id for item in self.sources) != self.queue_result.queued_source_ids:
            raise ValueError("extraction results must reproduce the complete queue order")
        return self

    def analyst_input(
        self,
        snapshots: dict[UUID, SourceSnapshot],
    ) -> V2EvidenceAnalystBatchInput:
        """Project only deterministically valid candidates into Luna analysis."""
        direction_by_id = {
            item.source_id: item.direction for item in self.queue_result.input.survivors
        }
        candidates = tuple(
            V2EvidenceAnalystCandidateInput(
                source_id=item.source_id,
                direction=direction_by_id[item.source_id],
                candidate=item.candidate,
                snapshot=snapshots[item.source_id],
            )
            for item in self.sources
            if item.candidate is not None
        )
        return V2EvidenceAnalystBatchInput(
            run_id=self.run_id,
            exact_claim=self.queue_result.input.exact_claim,
            directions=self.queue_result.input.directions,
            queue_result=self.queue_result,
            queued_candidates=candidates,
            extraction_failures=tuple(
                V2EvidenceAnalystExtractionFailure(
                    source_id=item.source_id,
                    failure=item.failure,
                )
                for item in self.sources
                if item.candidate is None and item.failure is not None
            ),
        )


class V2ExtractionInputBinding(StrictModel):
    """Bind resumable source checkpoints to the exact extraction inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class V2ExtractionSourceCheckpoint(StrictModel):
    """Persist one completed source so a resumed batch does not repeat paid calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: V2ExtractionSourceResult
