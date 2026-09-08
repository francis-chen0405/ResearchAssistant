"""Typed application requests and presentation contracts shared by local interfaces."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from models import (
    DEFAULT_RESEARCH_CONTROLS,
    DiscoveryProvider,
    ResearchControls,
    ResearchDirections,
    StrictModel,
    V2RunDiagnostics,
)
from money import ExactUSD
from providers.model_profiles import ProfileId

LEGACY_LIVE_RESEARCH_CONTROLS = ResearchControls(
    discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX)
)

LiveClassification = Literal[
    "starting",
    "running",
    "released",
    "blocked",
    "failed",
    "cancelled",
    "configuration_error",
    "invalid_input",
    "duplicate_active",
]


class LiveRunRequest(StrictModel):
    model_profile: ProfileId | None = None
    raw_claim: str = Field(min_length=1)
    db_path: str = Field(min_length=1)
    run_id: UUID | None = None
    max_tokens: int = Field(ge=1, le=500_000)
    max_cost_usd: Decimal = Field(default=Decimal("0.20"), gt=0, le=Decimal("1.00"))
    max_llm_calls: int = Field(default=160, ge=1, le=160)
    research_controls: ResearchControls = LEGACY_LIVE_RESEARCH_CONTROLS
    directions: ResearchDirections = ResearchDirections()
    crossref_enabled: bool = False

    @field_validator("raw_claim")
    @classmethod
    def validate_exact_claim(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("claim must not contain leading or trailing whitespace")
        return value

    @field_validator("db_path")
    @classmethod
    def validate_database_path(cls, value: str) -> str:
        path = Path(value).expanduser().resolve()
        if path.exists() and not path.is_file():
            raise ValueError("database location must be a file")
        if not path.parent.is_dir():
            raise ValueError("database parent directory does not exist")
        if not os.access(path.parent, os.W_OK):
            raise ValueError("database parent directory is not writable")
        if path.exists() and path.stat().st_size > 0:
            with path.open("rb") as handle:
                if handle.read(16) != b"SQLite format 3\x00":
                    raise ValueError("existing database location is not a SQLite file")
        return str(path)


class ResearchProgress(StrictModel):
    stance: Literal["supporting", "opposing"]
    status: str = Field(min_length=1)
    model_attempts: int = Field(ge=0)
    retrieval_attempts: int = Field(ge=0)
    usable_snapshots: int = Field(ge=0)
    candidates: int = Field(ge=0)


class LiveRunSnapshot(StrictModel):
    run_id: UUID
    db_path: str = Field(min_length=1)
    raw_claim: str = Field(min_length=1)
    classification: LiveClassification
    exit_code: int | None = None
    stage: str = Field(min_length=1)
    latest_checkpoint: str | None = None
    completed_checkpoints: int = Field(default=0, ge=0)
    total_checkpoints: int = Field(default=5, ge=1)
    current_research_round: int = Field(default=1, ge=1, le=4)
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: str = Field(min_length=1)
    diagnostic_component: str = Field(min_length=1)
    model_calls_used: int = Field(ge=0)
    retrieval_attempts_used: int = Field(ge=0)
    total_tokens: int | None = Field(default=0, ge=0)
    total_cost_usd: ExactUSD | None = Decimal("0")
    known_token_subtotal: int = Field(default=0, ge=0)
    known_cost_subtotal_usd: ExactUSD = Decimal("0")
    token_usage_complete: bool = True
    cost_usage_complete: bool = True
    conservative_reserved_tokens: int | None = Field(default=0, ge=0)
    conservative_reserved_cost_usd: ExactUSD | None = Decimal("0")
    supporting: ResearchProgress
    opposing: ResearchProgress
    validation_errors: tuple[str, ...] = ()
    final_brief: str | None = None
    rendered_brief_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_identity: str | None = None
    model_identity: str | None = None
    fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    research_controls: ResearchControls = DEFAULT_RESEARCH_CONTROLS
    v2_diagnostics: V2RunDiagnostics | None = None


class LiveHistoryItem(StrictModel):
    run_id: UUID
    raw_claim: str = Field(min_length=1)
    status: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    completed_at: str | None = None


class DiscoveryScoreBreakdown(StrictModel):
    relevance: int = Field(ge=0, le=35)
    intent_match: int = Field(ge=0, le=20)
    directness: int = Field(ge=0, le=15)
    metadata_completeness: int = Field(ge=0, le=10)
    likely_accessibility: int = Field(ge=0, le=10)
    source_novelty: int = Field(ge=0, le=10)
    penalties: int = Field(ge=-45, le=0)


class AcquiredSourceScoreBreakdown(StrictModel):
    readability: int = Field(ge=0, le=25)
    claim_term_coverage: int = Field(ge=0, le=35)
    document_specificity: int = Field(ge=0, le=25)
    evidence_language: int = Field(ge=0, le=15)
    penalties: int = Field(ge=-20, le=0)


class ResearchTrailItem(StrictModel):
    research_round: int = Field(ge=1, le=4)
    stance: Literal["supporting", "opposing"]
    provider: DiscoveryProvider
    intent: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    title: str
    url: str = Field(min_length=1)
    score: int | None = Field(default=None, ge=0, le=100)
    decision: Literal["selected", "deferred", "discarded"]
    selection_rank: int | None = Field(default=None, ge=1, le=20)
    breakdown: DiscoveryScoreBreakdown | None = None
    acquired_score: int | None = Field(default=None, ge=0, le=100)
    extraction_rank: int | None = Field(default=None, ge=1, le=25)
    acquired_breakdown: AcquiredSourceScoreBreakdown | None = None
    acquisition_state: Literal["acquired", "attempted", "not_attempted"] | None = None


class ResearchTrail(StrictModel):
    run_id: UUID
    items: tuple[ResearchTrailItem, ...]


class LiveStartResult(StrictModel):
    started: bool
    run_id: UUID
    classification: LiveClassification
    message: str = Field(min_length=1)
