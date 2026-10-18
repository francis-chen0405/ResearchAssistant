"""Immutable local request and outcome checkpoints for bounded model stages."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal, TypeVar
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ConfigDict, Field, field_validator, model_validator

from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
from researchassistant.contracts.models import (
    NormalizedDiscoveryItem,
    ScoutBatch,
    SourceCluster,
    StrictModel,
    V2DeepAnalysisBudget,
    V2GapAnalysisInput,
    V2GapAnalysisModelOutput,
    V2InitialPlannerConceptsOutput,
    V2InitialPlannerModelOutput,
    V2SourceSelectionInput,
    V2SourceSelectionModelOutput,
)
from researchassistant.contracts.source_selection_preview import V2SelectionShortlistAudit
from researchassistant.providers.llm import InvocationStatus, LLMInvocationRecord, LLMRequest
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

Checkpoint = TypeVar("Checkpoint", bound=StrictModel)


def _aware_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("stage checkpoint timestamps must be timezone-aware")
    return value


class V2ScoutRoundCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    policy: Literal["scout-round-checkpoint-v1"] = "scout-round-checkpoint-v1"
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[NormalizedDiscoveryItem, ...]
    clusters: tuple[SourceCluster, ...]
    scout_item_ids: tuple[UUID, ...]
    ranking_artifact: V2MetadataRankingArtifact | None
    created_at: datetime

    _created_is_aware = field_validator("created_at")(_aware_timestamp)

    @model_validator(mode="after")
    def validate_ownership(self) -> V2ScoutRoundCheckpoint:
        ids = {item.item_id for item in self.items}
        if len(ids) != len(self.items) or len(set(self.scout_item_ids)) != len(self.scout_item_ids):
            raise ValueError("Scout checkpoint item identities must be unique")
        if not set(self.scout_item_ids).issubset(ids):
            raise ValueError("Scout checkpoint selection contains an unknown item")
        if any(item.run_id != self.run_id for item in self.items):
            raise ValueError("Scout checkpoint contains a foreign item")
        if self.ranking_artifact is not None and self.ranking_artifact.run_id != self.run_id:
            raise ValueError("Scout checkpoint contains a foreign ranking")
        return self


class V2GapInputCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    policy: Literal["gap-input-checkpoint-v1"] = "gap-input-checkpoint-v1"
    input: V2GapAnalysisInput
    routing_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime

    _created_is_aware = field_validator("created_at")(_aware_timestamp)

    @model_validator(mode="after")
    def validate_ownership(self) -> V2GapInputCheckpoint:
        if self.input.run_id != self.run_id:
            raise ValueError("Gap checkpoint input belongs to another run")
        return self


class V2StageAttemptCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    attempt_id: UUID
    stage_key: str
    attempt_number: int = Field(ge=1, le=2)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime

    _started_is_aware = field_validator("started_at")(_aware_timestamp)


class V2SelectionInputCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    policy: Literal["selection-input-checkpoint-v1"] = "selection-input-checkpoint-v1"
    full_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input: V2SourceSelectionInput | None
    shortlist: V2SelectionShortlistAudit | None
    budget: V2DeepAnalysisBudget
    input_tokens: int = Field(ge=0)
    routing_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime

    _created_is_aware = field_validator("created_at")(_aware_timestamp)

    @model_validator(mode="after")
    def validate_ownership(self) -> V2SelectionInputCheckpoint:
        if self.input is not None and self.input.run_id != self.run_id:
            raise ValueError("selection checkpoint input belongs to another run")
        if self.shortlist is not None:
            if self.shortlist.run_id != self.run_id:
                raise ValueError("selection checkpoint shortlist belongs to another run")
            included = tuple(item.source_id for item in self.input.survivors) if self.input else ()
            if self.shortlist.included_source_ids != included:
                raise ValueError("selection checkpoint input differs from its shortlist")
            if self.shortlist.rendered_input_tokens != self.input_tokens:
                raise ValueError("selection checkpoint estimate differs from its shortlist")
        if self.input is None and self.input_tokens != 0:
            raise ValueError("omitted selection request cannot reserve input tokens")
        return self


class V2PlannerInputCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    policy: Literal["initial-planner-input-checkpoint-v1"] = "initial-planner-input-checkpoint-v1"
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    planned_at: datetime

    _planned_is_aware = field_validator("planned_at")(_aware_timestamp)


class V2StageOutcomeCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    attempt_id: UUID
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate: (
        ScoutBatch
        | V2GapAnalysisModelOutput
        | V2SourceSelectionModelOutput
        | V2InitialPlannerModelOutput
        | V2InitialPlannerConceptsOutput
        | None
    ) = None
    invocation: LLMInvocationRecord | None = None
    failure: str | None = None
    terminal_provider_failure: bool = False
    completed_at: datetime

    _completed_is_aware = field_validator("completed_at")(_aware_timestamp)

    @model_validator(mode="after")
    def validate_result(self) -> V2StageOutcomeCheckpoint:
        if (self.candidate is None) == (self.failure is None):
            raise ValueError("stage outcome requires exactly one candidate or failure")
        if self.candidate is not None and (
            self.invocation is None or self.invocation.status != InvocationStatus.COMPLETED
        ):
            raise ValueError("stage candidate requires its completed invocation")
        if isinstance(self.candidate, ScoutBatch) and self.candidate.run_id != self.run_id:
            raise ValueError("stage outcome candidate belongs to another run")
        if self.invocation is not None and self.invocation.run_id != self.run_id:
            raise ValueError("stage outcome invocation belongs to another run")
        if self.terminal_provider_failure and (self.failure is None or self.invocation is None):
            raise ValueError("terminal stage failure requires its invocation failure")
        return self


def checkpoint_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def read_checkpoint(
    path: str, run_id: UUID, key: str, model: type[Checkpoint]
) -> Checkpoint | None:
    try:
        envelope = read_v2_artifact(path, run_id, key)
    except KeyError:
        return None
    if envelope.artifact_type != model.__name__:
        raise ValueError("stage checkpoint has an unexpected artifact type")
    value = model.model_validate_json(envelope.payload_json)
    if getattr(value, "run_id", None) != run_id:
        raise ValueError("stage checkpoint belongs to another run")
    return value


def stage_attempt(
    *, path: str, key: str, number: int, request: LLMRequest, started_at: datetime
) -> tuple[V2StageAttemptCheckpoint, V2StageOutcomeCheckpoint | None, bool]:
    """Record intent before dispatch; a previous intent without outcome cannot repeat."""
    digest = checkpoint_hash(
        {
            "request": request.model_dump(
                mode="json", exclude={"requested_output_type", "input_artifact"}
            ),
            "input": request.input_artifact.model_dump(mode="json"),
            "output_type": request.requested_output_type.__name__,
            "output_schema": request.requested_output_type.model_json_schema(),
        }
    )
    attempt_key = f"{key}/attempt-{number}"
    attempt_id = uuid5(NAMESPACE_URL, f"bounded-stage-v1::{request.run_id}::{attempt_key}")
    previous = read_checkpoint(path, request.run_id, attempt_key, V2StageAttemptCheckpoint)
    if previous is not None:
        if (
            previous.stage_key != key
            or previous.attempt_number != number
            or previous.attempt_id != attempt_id
            or previous.request_hash != digest
        ):
            raise ValueError("persisted bounded stage request identity changed")
        outcome = read_checkpoint(
            path, request.run_id, attempt_key + "/outcome", V2StageOutcomeCheckpoint
        )
        if outcome is None:
            raise RuntimeError("bounded stage has an unknown outcome; its attempt remains consumed")
        if outcome.attempt_id != attempt_id or outcome.request_hash != digest:
            raise ValueError("stage outcome does not belong to its exact attempt")
        invocation = outcome.invocation
        if invocation is not None and (
            invocation.stage != request.stage
            or invocation.model_alias != request.model_alias
            or invocation.prompt_hash != request.prompt.sha256
            or invocation.prompt_version != request.prompt.version
            or invocation.requested_output_type != request.requested_output_type.__name__
            or invocation.input_artifact_ids != (*request.input_artifact_ids, attempt_id)
            or invocation.started_at < previous.started_at
            or invocation.ended_at > outcome.completed_at
        ):
            raise ValueError("saved stage invocation differs from its exact request")
        if outcome.completed_at < previous.started_at:
            raise ValueError("stage outcome precedes its owning attempt")
        return previous, outcome, False
    if (
        read_checkpoint(path, request.run_id, attempt_key + "/outcome", V2StageOutcomeCheckpoint)
        is not None
    ):
        raise ValueError("stage outcome has no owning attempt")
    attempt = V2StageAttemptCheckpoint(
        run_id=request.run_id,
        attempt_id=attempt_id,
        stage_key=key,
        attempt_number=number,
        request_hash=digest,
        started_at=started_at,
    )
    insert_v2_artifact(path, attempt_key, attempt, started_at)
    return attempt, None, True


def save_stage_outcome(
    path: str, attempt: V2StageAttemptCheckpoint, outcome: V2StageOutcomeCheckpoint
) -> None:
    if (outcome.run_id, outcome.attempt_id, outcome.request_hash) != (
        attempt.run_id,
        attempt.attempt_id,
        attempt.request_hash,
    ):
        raise ValueError("stage outcome does not belong to its exact attempt")
    insert_v2_artifact(
        path,
        f"{attempt.stage_key}/attempt-{attempt.attempt_number}/outcome",
        outcome,
        outcome.completed_at,
    )
