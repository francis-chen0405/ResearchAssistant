"""Shared claim coverage, Gap identity and continuity validators."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from researchassistant.contracts.model_contracts import (
    NonEmptyStr,
    StrictModel,
)
from researchassistant.contracts.research_directions import ResearchDirection


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


class V2InitialPlannerClaimComponent(V2ClaimCoverageFocus):
    """Narrow fresh response schema; generic historical coverage stays unchanged."""

    dimension: Literal[
        V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        V2ClaimCoverageDimension.POPULATION_AND_SETTING,
        V2ClaimCoverageDimension.MECHANISM_OR_PATHWAY,
    ]
    kind: Literal[V2ClaimCoverageKind.CLAIM_COMPONENT] = V2ClaimCoverageKind.CLAIM_COMPONENT
    searchable: Literal[True] = True
    unavailable_reason: None = None


class V2GapIdentity(StrictModel):
    """Typed identity fields used to validate Gap continuity across rounds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    claim_dimension: V2ClaimCoverageDimension | None = None
    unsupported_claim_component: NonEmptyStr | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_claim_component(self) -> V2GapIdentity:
        if (self.claim_dimension is None) != (self.unsupported_claim_component is None):
            raise ValueError("Gap identities require a dimension and component together")
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

    @property
    def continuity_identity(self) -> V2GapIdentity:
        return V2GapIdentity(
            gap_id=self.gap_id,
            direction=self.direction,
            claim_dimension=self.claim_dimension,
            unsupported_claim_component=self.unsupported_claim_component,
        )


class V2SourceSelectionGap(StrictModel):
    """Material Gap history available to source prioritization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    missing_evidence: NonEmptyStr
    claim_dimension: V2ClaimCoverageDimension | None = None
    unsupported_claim_component: NonEmptyStr | None = Field(default=None, max_length=500)
    assessed_after_round: Annotated[int, Field(ge=1, le=3)] = 1

    @model_validator(mode="after")
    def validate_claim_component(self) -> V2SourceSelectionGap:
        if (self.claim_dimension is None) != (self.unsupported_claim_component is None):
            raise ValueError("claim-linked source-selection Gaps require a dimension and component")
        return self

    @property
    def continuity_identity(self) -> V2GapIdentity:
        return V2GapIdentity(
            gap_id=self.gap_id,
            direction=self.direction,
            claim_dimension=self.claim_dimension,
            unsupported_claim_component=self.unsupported_claim_component,
        )


class V2GapIdentityCollisionError(ValueError):
    """Gap identity fields conflict or duplicate one semantic gap under another ID."""


def _record_v2_gap_identity(
    identities: dict[str, V2GapIdentity],
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str],
    identity: V2GapIdentity,
    *,
    scope: str,
) -> None:
    existing = identities.get(identity.gap_id)
    if existing is not None and (
        existing.direction is not identity.direction
        or (
            existing.claim_dimension is not None
            and identity.claim_dimension is not None
            and (
                existing.claim_dimension is not identity.claim_dimension
                or existing.unsupported_claim_component != identity.unsupported_claim_component
            )
        )
    ):
        raise V2GapIdentityCollisionError(
            f"{scope} Gap ID {identity.gap_id!r} has conflicting semantic identity"
        )
    if identity.claim_dimension is not None:
        semantic_key = (
            identity.direction,
            identity.claim_dimension,
            identity.unsupported_claim_component,
        )
        existing_gap_id = semantic_identities.get(semantic_key)
        if existing_gap_id is not None and existing_gap_id != identity.gap_id:
            raise V2GapIdentityCollisionError(
                f"{scope} semantic Gap identity is assigned to both "
                f"{existing_gap_id!r} and {identity.gap_id!r}"
            )
        semantic_identities[semantic_key] = identity.gap_id
    if existing is None:
        identities[identity.gap_id] = identity
        return
    if existing.claim_dimension is None and identity.claim_dimension is not None:
        identities[identity.gap_id] = identity


def validate_v2_gap_identity_continuity(
    previous_gaps: tuple[V2MaterialGap, ...],
    current_gaps: tuple[V2MaterialGap, ...],
) -> None:
    """Reject incompatible reused IDs while allowing legacy unknown claim identity."""
    identities: dict[str, V2GapIdentity] = {}
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str] = {}
    for gap in (*previous_gaps, *current_gaps):
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            gap.continuity_identity,
            scope="Gap Analysis",
        )


def validate_v2_source_selection_gap_history(
    gap_history: tuple[V2SourceSelectionGap, ...],
) -> None:
    """Reject incompatible repeated IDs in cross-round source-selection history."""
    identities: dict[str, V2GapIdentity] = {}
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str] = {}
    for gap in gap_history:
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            gap.continuity_identity,
            scope="source-selection history",
        )


def validate_v2_gap_history_against_material_gaps(
    material_gaps: tuple[V2MaterialGap, ...],
    gap_history: tuple[V2SourceSelectionGap, ...],
) -> None:
    """Ensure current reconciliation gaps retain the history's explicit identity fields."""
    identities: dict[str, V2GapIdentity] = {}
    semantic_identities: dict[tuple[ResearchDirection, V2ClaimCoverageDimension, str], str] = {}
    for history_gap in gap_history:
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            history_gap.continuity_identity,
            scope="source-selection history",
        )
    for gap in material_gaps:
        _record_v2_gap_identity(
            identities,
            semantic_identities,
            gap.continuity_identity,
            scope="reconciliation",
        )


# Preserve the historical public class identity for persisted consumers.
V2ClaimCoverageDimension.__module__ = "researchassistant.contracts.model_research"
V2ClaimCoverageKind.__module__ = "researchassistant.contracts.model_research"
V2ClaimCoverageState.__module__ = "researchassistant.contracts.model_research"
V2ClaimCoverageFocus.__module__ = "researchassistant.contracts.model_research"
V2InitialPlannerClaimComponent.__module__ = "researchassistant.contracts.model_research"
V2GapIdentity.__module__ = "researchassistant.contracts.model_research"
V2ClaimCoverageSpecification.__module__ = "researchassistant.contracts.model_research"
V2ClaimCoverageAssessment.__module__ = "researchassistant.contracts.model_research"
V2MaterialGap.__module__ = "researchassistant.contracts.model_research"
V2SourceSelectionGap.__module__ = "researchassistant.contracts.model_research"
V2GapIdentityCollisionError.__module__ = "researchassistant.contracts.model_research"
