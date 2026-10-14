"""Acquisition, exact Probe passages and survivor handoffs."""

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

from researchassistant.contracts.discovery_v2 import (
    V2PreviewResult,
)
from researchassistant.contracts.model_contracts import (
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
    SourceSnapshot,
    StrictModel,
    _validate_aware_datetime,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.contracts.research_policy import (
    V2_ACQUISITION_PROBE_POLICY_IDENTITY as V2_ACQUISITION_PROBE_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY as V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY as V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
)


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
    policy_identity: Literal[
        "researchassistant-v2-phase-5-acquisition-probe-v1",
        "researchassistant-v2-phase-5-acquisition-probe-v2",
        "researchassistant-v2-phase-5-acquisition-probe-v3",
        "researchassistant-v2-phase-5-acquisition-probe-v4",
    ] = V2_ACQUISITION_PROBE_POLICY_IDENTITY


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

    preview: V2PreviewResult | None = None

    @model_serializer(mode="wrap")
    def historical_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        if self.preview is None:
            data.pop("preview", None)
        return data

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
        if self.preview is not None and (
            self.preview.request.source_id != self.cluster_id
            or self.preview.request.snapshot_id != self.snapshot_id
            or self.preview.request.snapshot_hash != self.snapshot_sha256
        ):
            raise ValueError("Probe preview must match its source and snapshot")
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
    policy_identity: Literal[
        "researchassistant-v2-phase-5-acquisition-probe-v1",
        "researchassistant-v2-phase-5-acquisition-probe-v2",
        "researchassistant-v2-phase-5-acquisition-probe-v3",
        "researchassistant-v2-phase-5-acquisition-probe-v4",
    ] = V2_ACQUISITION_PROBE_POLICY_IDENTITY
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
            probe = probe_by_snapshot[source.snapshot.snapshot_id]
            if (
                probe.cluster_id != source.cluster_id
                or probe.snapshot_sha256 != source.snapshot.snapshot_sha256
            ):
                raise ValueError("Probe must match acquired source identity/hash")
            if self.policy_identity in {
                V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
                V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
            } and (
                probe.preview is None
                or probe.preview.request.preview_identity != "source-claim-preview-v2"
            ):
                raise ValueError("current Probe requires its exact versioned preview")
            if probe.preview is not None:
                probe.preview.require_snapshot(source.snapshot)
                if (
                    probe.preview.request.directions != self.directions
                    or probe.preview.request.direction != source.direction
                ):
                    raise ValueError("Probe preview lane differs from acquisition")
            for passage in probe.passages:
                if (
                    source.snapshot.normalized_text[passage.start_char : passage.end_char]
                    != passage.text
                ):
                    raise ValueError("Probe text differs from immutable snapshot")
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
            source = next(
                x for x in self.acquisitions if x.snapshot.snapshot_id == survivor.snapshot_id
            )
            if survivor.cluster_id != probe.cluster_id or survivor.direction != source.direction:
                raise ValueError("survivor source/lane must match acquired Probe")
            if survivor.snapshot_sha256 != probe.snapshot_sha256:
                raise ValueError("survivor snapshot hash must match Probe")
            if not set(survivor.passage_ids).issubset(
                {passage.passage_id for passage in probe.passages}
            ):
                raise ValueError("survivors may reference only their own Probe passages")
        return self


# Preserve the historical public class identity for persisted consumers.
V2AcquisitionProvider.__module__ = "researchassistant.contracts.model_research"
V2AcquisitionPolicy.__module__ = "researchassistant.contracts.model_research"
V2AcquisitionAttempt.__module__ = "researchassistant.contracts.model_research"
V2AcquiredSource.__module__ = "researchassistant.contracts.model_research"
V2ProbePassage.__module__ = "researchassistant.contracts.model_research"
V2ProbeResult.__module__ = "researchassistant.contracts.model_research"
V2SurvivingSource.__module__ = "researchassistant.contracts.model_research"
V2AcquisitionProbeOutput.__module__ = "researchassistant.contracts.model_research"
