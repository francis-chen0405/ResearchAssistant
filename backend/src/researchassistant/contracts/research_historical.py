"""Retained historical research-stage contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import (
    ConfigDict,
    field_validator,
    model_validator,
)

from researchassistant.contracts.model_contracts import (
    NonEmptyStr,
    StrictModel,
    _validate_aware_datetime,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.contracts.research_discovery import (
    SourceCluster as SourceCluster,
)
from researchassistant.contracts.research_planning import (
    SearchDirectionGapReference as SearchDirectionGapReference,
)


class ProbePassage(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: NonEmptyStr
    direction: ResearchDirection
    source_cluster_id: NonEmptyStr
    text: NonEmptyStr
    source_url: NonEmptyStr


class ProbeResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    passage: ProbePassage
    accepted: bool
    reason: NonEmptyStr
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> ProbeResult:
        self.directions.require_permitted(self.passage.direction)
        return self


class GapAnalysisResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    gaps: tuple[SearchDirectionGapReference, ...]
    analyzed_at: datetime

    _analyzed_at_is_aware = field_validator("analyzed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_gaps(self) -> GapAnalysisResult:
        for gap in self.gaps:
            self.directions.require_permitted(gap.direction)
        return self


class SurvivingSourceRecord(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    direction: ResearchDirection
    source_cluster: SourceCluster
    reason: NonEmptyStr
    recorded_at: datetime

    _recorded_at_is_aware = field_validator("recorded_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> SurvivingSourceRecord:
        self.directions.require_permitted(self.direction)
        return self


class SourceRecommendationResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    direction: ResearchDirection
    recommended_source_cluster_id: NonEmptyStr | None
    rationale: NonEmptyStr
    recommended_at: datetime

    _recommended_at_is_aware = field_validator("recommended_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> SourceRecommendationResult:
        self.directions.require_permitted(self.direction)
        return self


class DeepAnalysisState(StrEnum):
    NOT_STARTED = "not_started"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class DeepAnalysisStatus(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    directions: ResearchDirections
    direction: ResearchDirection
    state: DeepAnalysisState
    updated_at: datetime

    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_enabled_direction(self) -> DeepAnalysisStatus:
        self.directions.require_permitted(self.direction)
        return self


# Preserve the historical public class identity for persisted consumers.
ProbePassage.__module__ = "researchassistant.contracts.model_research"
ProbeResult.__module__ = "researchassistant.contracts.model_research"
GapAnalysisResult.__module__ = "researchassistant.contracts.model_research"
SurvivingSourceRecord.__module__ = "researchassistant.contracts.model_research"
SourceRecommendationResult.__module__ = "researchassistant.contracts.model_research"
DeepAnalysisState.__module__ = "researchassistant.contracts.model_research"
DeepAnalysisStatus.__module__ = "researchassistant.contracts.model_research"
