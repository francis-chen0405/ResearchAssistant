"""Discovery metadata, source clusters and Scout handoffs."""

from __future__ import annotations

from datetime import datetime
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

from researchassistant.contracts.discovery_v2 import (
    V2GraphNeighborAction,
)
from researchassistant.contracts.model_contracts import (
    DiscoveryProvider,
    NonEmptyStr,
    PositiveInt,
    StrictModel,
    _validate_aware_datetime,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.contracts.research_policy import (
    V2_DISCOVERY_POLICY_IDENTITY as V2_DISCOVERY_POLICY_IDENTITY,
)


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
    query_text: NonEmptyStr | None
    graph_action: V2GraphNeighborAction | None = None
    direction: ResearchDirection
    round_number: PositiveInt
    provider_rank: PositiveInt
    original_url: NonEmptyStr
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def validate_graph_reference(self) -> DiscoveryProvenance:
        if self.graph_action is None:
            if self.query_text is None:
                raise ValueError("text discovery provenance requires query_text")
        elif (
            self.query_text is not None
            or self.query_id != self.graph_action.artifact_id
            or self.provider != self.graph_action.provider
            or self.direction is not self.graph_action.direction
            or self.round_number != self.graph_action.round_number
            or self.targeted_gap_ids != self.graph_action.target_gap_ids
        ):
            raise ValueError("graph provenance must preserve its action without forged query text")
        return self

    @model_serializer(mode="wrap")
    def omit_absent_graph_action(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value = handler(self)
        if self.graph_action is None:
            value.pop("graph_action", None)
        return value


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
    query_text: NonEmptyStr | None
    graph_action: V2GraphNeighborAction | None = None
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
        if self.graph_action is None:
            if self.query_text is None:
                raise ValueError("text discovery items require query_text")
        elif (
            self.query_text is not None
            or self.query_id != self.graph_action.artifact_id
            or self.graph_action.run_id != self.run_id
            or self.graph_action.provider != self.provider
            or self.graph_action.direction is not self.direction
            or self.graph_action.round_number != self.round_number
        ):
            raise ValueError(
                "graph discovery item must preserve its action reference without query text"
            )
        if self.graph_action is not None and any(
            provenance.query_id != self.query_id
            or provenance.query_text is not None
            or provenance.graph_action != self.graph_action
            for provenance in self.provenance_chain
        ):
            raise ValueError("graph item provenance must preserve its action without query text")
        return self

    @model_serializer(mode="wrap")
    def omit_absent_graph_action(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value = handler(self)
        if self.graph_action is None:
            value.pop("graph_action", None)
        return value


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
    attempted_calls: int = Field(ge=0)
    fallback_used: bool = False
    failure: NonEmptyStr | None = None
    recovery_policy: Literal["partial-ranking-recovery-v1"] | None = None

    @model_validator(mode="after")
    def validate_fallback(self) -> ScoutBatchAudit:
        if self.attempted_calls == 0 and self.recovery_policy is None:
            raise ValueError("zero Scout calls require explicit interrupted-checkpoint recovery")
        if self.recovery_policy is not None and (
            self.attempted_calls != 0 or not self.fallback_used
        ):
            raise ValueError("ranking recovery cannot claim new Scout attempts or model decisions")
        if self.fallback_used != (self.failure is not None):
            raise ValueError("Scout fallback and failure audit fields must agree")
        return self

    @model_serializer(mode="wrap")
    def historical_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        if self.recovery_policy is None:
            data.pop("recovery_policy", None)
        return data


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


# Preserve the historical public class identity for persisted consumers.
DiscoveryMetadataEntry.__module__ = "researchassistant.contracts.model_research"
DiscoveryProvenance.__module__ = "researchassistant.contracts.model_research"
CrossrefIdentityMetadata.__module__ = "researchassistant.contracts.model_research"
NormalizedDiscoveryItem.__module__ = "researchassistant.contracts.model_research"
DiscoveryProviderReference.__module__ = "researchassistant.contracts.model_research"
SourceCluster.__module__ = "researchassistant.contracts.model_research"
ScoutDecision.__module__ = "researchassistant.contracts.model_research"
ScoutCandidate.__module__ = "researchassistant.contracts.model_research"
V2ScoutRequest.__module__ = "researchassistant.contracts.model_research"
ScoutItem.__module__ = "researchassistant.contracts.model_research"
ScoutBatch.__module__ = "researchassistant.contracts.model_research"
ScoutBatchAudit.__module__ = "researchassistant.contracts.model_research"
V2DiscoveryScoutOutput.__module__ = "researchassistant.contracts.model_research"
