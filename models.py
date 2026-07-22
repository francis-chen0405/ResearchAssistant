from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Score = Annotated[int, Field(ge=1, le=5)]
ApprovedScore = Annotated[int, Field(ge=3, le=5)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonEmptyStr = Annotated[str, Field(min_length=1)]
ApplicationReviewerApprovalId = Annotated[
    str,
    Field(pattern=r"^rappr_v1_[0-9a-f]{64}$"),
]
ReviewerApprovalId = UUID | ApplicationReviewerApprovalId
REQUIRED_QUERY_EXCLUSIONS = (
    "-site:reddit.com",
    "-site:quora.com",
    "-site:youtube.com",
    "-site:tiktok.com",
)


def missing_required_query_exclusions(exclusion_parameters: str) -> tuple[str, ...]:
    """Return required search exclusions absent as exact whitespace-delimited tokens."""
    tokens = set(exclusion_parameters.split())
    return tuple(exclusion for exclusion in REQUIRED_QUERY_EXCLUSIONS if exclusion not in tokens)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CheckpointStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ModelAttemptStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Stage(StrEnum):
    CLAIM_PLANNER = "claim_planner"
    SUPPORTING_RESEARCHER = "supporting_researcher"
    OPPOSING_RESEARCHER = "opposing_researcher"
    EVIDENCE_ANALYST = "evidence_analyst"
    STATEMENT_REVIEWER = "statement_reviewer"
    CLAIM_LEDGER = "claim_ledger"
    DEBATE_SYNTHESIZER = "debate_synthesizer"
    FINAL_RENDERER_VALIDATOR = "final_renderer_validator"


class Stance(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"


class Placement(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUPPORTING = "supporting"
    QUALIFIED_ONLY = "qualified_only"


class Entailment(StrEnum):
    STRONG = "Strong"
    PARTIAL = "Partial"
    WEAK = "Weak"


class RetrievalStatus(StrEnum):
    RETRIEVED = "retrieved"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewerFailureCode(StrEnum):
    NOT_ENTAILED = "not_entailed"
    MISSING_QUALIFICATION = "missing_qualification"
    BIASED_FRAMING = "biased_framing"
    CLAIM_FIT_MISMATCH = "claim_fit_mismatch"


class SectionType(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"
    LIMITATIONS = "limitations"


BRIEF_TITLE = "Research Brief"
CLAIM_LABEL = "Claim under review"
RELEASE_SECTION_ORDER = (
    SectionType.SUPPORTING,
    SectionType.OPPOSING,
    SectionType.LIMITATIONS,
)
RELEASE_SECTION_HEADINGS = {
    SectionType.SUPPORTING: "Supporting Evidence",
    SectionType.OPPOSING: "Opposing Evidence",
    SectionType.LIMITATIONS: "Limitations",
}


class ValidationErrorCode(StrEnum):
    LEDGER_MISMATCH = "ledger_mismatch"
    INVALID_SECTION = "invalid_section"
    INVALID_TEMPLATE = "invalid_template"
    ALTERED_STATEMENT = "altered_statement"
    SCHEMA_ERROR = "schema_error"


def _validate_aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value


def _validate_offsets(
    offsets: list[SegmentOffset] | tuple[SegmentOffset, ...],
) -> list[SegmentOffset] | tuple[SegmentOffset, ...]:
    previous_end: int | None = None
    for offset in offsets:
        if previous_end is not None and offset.start_char < previous_end:
            raise ValueError("segment offsets must be ordered and non-overlapping")
        previous_end = offset.end_char
    return offsets


def _is_ledger_eligible(evidence_quality: int, claim_fit: int) -> bool:
    return evidence_quality >= 2 and claim_fit >= 3 and evidence_quality + claim_fit >= 5


def _derive_ledger_score(evidence_quality: int, claim_fit: int) -> int:
    total_score = evidence_quality + claim_fit
    if total_score <= 6:
        return 3
    if total_score <= 8:
        return 4
    return 5


def _expected_placement(evidence_quality: int, claim_fit: int) -> Placement:
    ledger_score = _derive_ledger_score(evidence_quality, claim_fit)
    if claim_fit == 3:
        return Placement.QUALIFIED_ONLY
    if ledger_score == 5:
        return Placement.PRIMARY
    if ledger_score == 4:
        return Placement.SECONDARY
    return Placement.SUPPORTING


class SegmentOffset(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_char: NonNegativeInt
    end_char: PositiveInt

    @model_validator(mode="after")
    def validate_order(self) -> SegmentOffset:
        if self.start_char >= self.end_char:
            raise ValueError("segment offset start_char must be before end_char")
        return self


class ClaimDefinition(StrictModel):
    run_id: UUID
    claim_text: NonEmptyStr
    population: NonEmptyStr
    jurisdiction: NonEmptyStr
    time_period: NonEmptyStr
    comparison_baseline: NonEmptyStr
    intervention_or_exposure: NonEmptyStr
    causal_or_comparative_meaning: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class AmbiguityRecord(StrictModel):
    run_id: UUID
    ambiguity_id: UUID
    description: NonEmptyStr
    impact: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class SearchQuery(StrictModel):
    run_id: UUID
    query_id: UUID
    stance: Stance
    query_round: Annotated[int, Field(ge=1, le=3)]
    strategy: NonEmptyStr
    query_text: NonEmptyStr
    exclusion_parameters: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class PlannerOutput(StrictModel):
    run_id: UUID
    claim_definition: ClaimDefinition
    ambiguities: list[AmbiguityRecord]
    search_queries: list[SearchQuery]
    planner_prompt_version: NonEmptyStr
    planner_model_name: NonEmptyStr
    planned_at: datetime

    _planned_at_is_aware = field_validator("planned_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_queries(self) -> PlannerOutput:
        if self.claim_definition.run_id != self.run_id:
            raise ValueError("claim definition run_id must match planner run_id")
        for ambiguity in self.ambiguities:
            if ambiguity.run_id != self.run_id:
                raise ValueError("ambiguity run_id must match planner run_id")

        expected_rounds = {
            (Stance.SUPPORTING, 1),
            (Stance.SUPPORTING, 2),
            (Stance.SUPPORTING, 3),
            (Stance.OPPOSING, 1),
            (Stance.OPPOSING, 2),
            (Stance.OPPOSING, 3),
        }
        actual_rounds = {(query.stance, query.query_round) for query in self.search_queries}
        if len(self.search_queries) != 6 or actual_rounds != expected_rounds:
            raise ValueError(
                "planner output must include exactly three supporting and three opposing queries"
            )
        for query in self.search_queries:
            if query.run_id != self.run_id:
                raise ValueError("search query run_id must match planner run_id")
            missing = missing_required_query_exclusions(query.exclusion_parameters)
            if missing:
                raise ValueError("search query is missing required exclusion parameters")
        return self


class RetrievalRecord(StrictModel):
    run_id: UUID
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=3)]
    query_text: NonEmptyStr
    search_rank: Annotated[int, Field(ge=1, le=3)]
    source_url: NonEmptyStr
    resolved_url: NonEmptyStr
    status: RetrievalStatus
    retrieved_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)


class SourceSnapshot(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    retrieval_attempt_id: UUID
    snapshot_id: UUID
    source_url: NonEmptyStr
    retrieved_at: datetime
    normalized_text: NonEmptyStr
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    word_count: NonNegativeInt
    truncated: bool
    created_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)
    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class ProvisionalCandidate(StrictModel):
    run_id: UUID
    stance: Stance
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=3)]
    search_rank: Annotated[int, Field(ge=1, le=3)]
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    extracted_quote_block: NonEmptyStr
    extraction_prompt_version: NonEmptyStr
    extraction_model_name: NonEmptyStr
    extracted_at: datetime

    _extracted_at_is_aware = field_validator("extracted_at")(_validate_aware_datetime)


class CandidateQuoteBlock(StrictModel):
    run_id: UUID
    stance: Stance
    quote_block_id: UUID
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=3)]
    search_rank: Annotated[int, Field(ge=1, le=3)]
    retrieved_at: datetime
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    snapshot_created_at: datetime
    extracted_quote_block: NonEmptyStr
    segment_offsets: Annotated[list[SegmentOffset], Field(min_length=1)]
    raw_segment_word_count: PositiveInt
    has_statistical_markers: bool
    claim_keyword_match_count: PositiveInt
    truncated: bool
    extraction_prompt_version: NonEmptyStr
    extraction_model_name: NonEmptyStr
    extracted_at: datetime
    post_filter_version: NonEmptyStr
    post_filter_validated_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)
    _snapshot_created_at_is_aware = field_validator("snapshot_created_at")(_validate_aware_datetime)
    _extracted_at_is_aware = field_validator("extracted_at")(_validate_aware_datetime)
    _post_filter_validated_at_is_aware = field_validator("post_filter_validated_at")(
        _validate_aware_datetime
    )
    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)


class CandidateBatch(StrictModel):
    run_id: UUID
    stance: Stance
    query_round: Annotated[int, Field(ge=1, le=3)]
    candidates: list[CandidateQuoteBlock]
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_batch_members(self) -> CandidateBatch:
        for candidate in self.candidates:
            if candidate.run_id != self.run_id:
                raise ValueError("candidate run_id must match batch run_id")
            if candidate.stance is not self.stance:
                raise ValueError("candidate stance must match batch stance")
            if candidate.query_round != self.query_round:
                raise ValueError("candidate query_round must match batch query_round")
        return self


class ScoreDecision(StrictModel):
    run_id: UUID
    quote_block_id: UUID
    evidence_quality: Score
    claim_fit: Score
    ledger_score: ApprovedScore | None = None
    placement: Placement | None = None
    approved: bool
    rationale: NonEmptyStr
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    scored_at: datetime

    _scored_at_is_aware = field_validator("scored_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_approval_and_placement(self) -> ScoreDecision:
        eligible = _is_ledger_eligible(self.evidence_quality, self.claim_fit)
        if not eligible:
            if self.approved:
                raise ValueError("ineligible score combinations cannot be approved")
            if self.ledger_score is not None or self.placement is not None:
                raise ValueError("ineligible score decisions must not assign Ledger fields")
            return self

        if self.approved:
            expected_score = _derive_ledger_score(self.evidence_quality, self.claim_fit)
            expected_placement = _expected_placement(self.evidence_quality, self.claim_fit)
            if self.ledger_score != expected_score:
                raise ValueError("approved score decisions require the derived Ledger score")
            if self.placement is not expected_placement:
                raise ValueError("approved score decisions require the derived placement")
        elif self.ledger_score is not None or self.placement is not None:
            raise ValueError("rejected score decisions must not assign Ledger fields")
        return self


class StatementDraft(StrictModel):
    run_id: UUID
    statement_draft_id: UUID
    quote_block_id: UUID
    stance: Stance
    draft_statement: NonEmptyStr
    claim_fit: Score
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    drafted_at: datetime

    _drafted_at_is_aware = field_validator("drafted_at")(_validate_aware_datetime)


class StatementReviewResult(StrictModel):
    run_id: UUID
    statement_draft_id: UUID
    quote_block_id: UUID
    approved: bool
    reviewer_approval_id: ReviewerApprovalId | None = None
    approved_factual_statement: NonEmptyStr | None = None
    failure_code: ReviewerFailureCode | None = None
    rationale: NonEmptyStr
    reviewer_prompt_version: NonEmptyStr
    reviewer_model_name: NonEmptyStr
    reviewed_at: datetime

    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_result_shape(self) -> StatementReviewResult:
        if self.approved:
            if self.reviewer_approval_id is None:
                raise ValueError("approved review results require reviewer_approval_id")
            if self.approved_factual_statement is None:
                raise ValueError("approved review results require an approved factual statement")
            if self.failure_code is not None:
                raise ValueError("approved review results cannot include a failure code")
        else:
            if self.failure_code is None:
                raise ValueError("rejected review results require a failure code")
            if self.reviewer_approval_id is not None:
                raise ValueError("rejected review results cannot include reviewer_approval_id")
            if self.approved_factual_statement is not None:
                raise ValueError("rejected review results cannot include an approved statement")
        return self


class LedgerRecord(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    ledger_claim_id: UUID
    quote_block_id: UUID
    stance: Stance
    approved_factual_statement: NonEmptyStr
    approved_claim_text: NonEmptyStr
    evidence_quality: Score
    claim_fit: Score
    ledger_score: ApprovedScore
    placement: Placement
    entailment: Entailment
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    segment_offsets: Annotated[tuple[SegmentOffset, ...], Field(min_length=1)]
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    analyst_completed_at: datetime
    reviewer_prompt_version: NonEmptyStr
    reviewer_model_name: NonEmptyStr
    reviewed_at: datetime
    reviewer_approval_id: ReviewerApprovalId
    ledger_validated_at: datetime

    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)
    _analyst_completed_at_is_aware = field_validator("analyst_completed_at")(
        _validate_aware_datetime
    )
    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)
    _ledger_validated_at_is_aware = field_validator("ledger_validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_score_contract(self) -> LedgerRecord:
        if not _is_ledger_eligible(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require eligible two-axis scores")
        if self.ledger_score != _derive_ledger_score(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require the derived Ledger score")
        if self.placement is not _expected_placement(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require the derived placement")
        return self


class SynthesisItem(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connective_template_id: NonEmptyStr
    ledger_claim_id: UUID
    reviewer_approval_id: ReviewerApprovalId
    stance: Stance
    placement: Placement
    entailment: Entailment
    approved_factual_statement: NonEmptyStr


class SynthesisSection(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_type: SectionType
    items: tuple[SynthesisItem, ...]

    @model_validator(mode="after")
    def validate_item_compatibility(self) -> SynthesisSection:
        if self.section_type is SectionType.SUPPORTING:
            required_stance = Stance.SUPPORTING
        elif self.section_type is SectionType.OPPOSING:
            required_stance = Stance.OPPOSING
        else:
            return self

        for item in self.items:
            if item.stance is not required_stance:
                raise ValueError("section items must use a compatible stance")
        return self


class SynthesisOutput(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    synthesizer_prompt_version: NonEmptyStr
    synthesizer_model_name: NonEmptyStr
    created_at: datetime
    sections: tuple[SynthesisSection, ...]

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class ValidationError(StrictModel):
    code: ValidationErrorCode
    location: NonEmptyStr
    message: NonEmptyStr


class ValidationResult(StrictModel):
    run_id: UUID
    valid: bool
    errors: list[ValidationError]
    validator_config_version: NonEmptyStr
    validated_at: datetime
    rendered_brief_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    _validated_at_is_aware = field_validator("validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_result(self) -> ValidationResult:
        if self.valid and self.errors:
            raise ValueError("valid results cannot include errors")
        if self.valid and self.rendered_brief_hash is None:
            raise ValueError("valid results require rendered_brief_hash")
        if not self.valid and not self.errors:
            raise ValueError("invalid results require at least one validation error")
        if not self.valid and self.rendered_brief_hash is not None:
            raise ValueError("invalid results cannot include rendered_brief_hash")
        return self


class RunManifest(StrictModel):
    run_id: UUID
    status: RunStatus
    raw_claim: NonEmptyStr
    current_stage: Stage
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)
    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)
    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_completion(self) -> RunManifest:
        if self.status is RunStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed runs require completed_at")
        return self


class OrchestrationCheckpoint(StrictModel):
    run_id: UUID
    stage_key: NonEmptyStr
    status: CheckpointStatus
    failure_reason: NonEmptyStr | None = None
    updated_at: datetime

    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_status_shape(self) -> OrchestrationCheckpoint:
        if self.status is CheckpointStatus.FAILED and self.failure_reason is None:
            raise ValueError("failed checkpoints require a failure reason")
        if self.status is not CheckpointStatus.FAILED and self.failure_reason is not None:
            raise ValueError("only failed checkpoints may carry a failure reason")
        return self


class PersistedStageArtifact(StrictModel):
    run_id: UUID
    artifact_key: NonEmptyStr
    artifact_type: NonEmptyStr
    payload_json: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class ModelUsageMetadata(StrictModel):
    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    total_tokens: NonNegativeInt | None = None
    cost_usd: Annotated[float, Field(ge=0.0)] | None = None

    @model_validator(mode="after")
    def validate_token_total(self) -> ModelUsageMetadata:
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        return self


class ModelRouteAttempt(StrictModel):
    run_id: UUID
    operation_id: UUID
    attempt_id: UUID
    stage: NonEmptyStr
    output_type: NonEmptyStr
    model_alias: NonEmptyStr
    pinned_model_snapshot: NonEmptyStr | None = None
    route_index: NonNegativeInt
    attempt_number: PositiveInt
    input_artifact_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    status: ModelAttemptStatus
    retry_reason: NonEmptyStr | None = None
    escalation_reason: NonEmptyStr | None = None
    failure_code: NonEmptyStr | None = None
    failure_reason: NonEmptyStr | None = None
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: Annotated[float, Field(ge=0.0)] | None = None
    usage: ModelUsageMetadata | None = None
    output_json: str | None = None

    _started_at_is_aware = field_validator("started_at")(_validate_aware_datetime)
    _ended_at_is_aware = field_validator("ended_at")(_validate_aware_datetime)

    @field_validator("input_artifact_ids")
    @classmethod
    def validate_input_artifact_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("input_artifact_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_attempt_shape(self) -> ModelRouteAttempt:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("attempt ended_at cannot precede started_at")
        if self.status is ModelAttemptStatus.RUNNING:
            if any(
                value is not None
                for value in (
                    self.ended_at,
                    self.latency_ms,
                    self.failure_code,
                    self.failure_reason,
                    self.output_json,
                )
            ):
                raise ValueError("running attempts cannot carry completion fields")
            return self
        if self.ended_at is None or self.latency_ms is None:
            raise ValueError("finished attempts require end time and latency")
        if self.status is ModelAttemptStatus.COMPLETED:
            if self.output_json is None:
                raise ValueError("completed attempts require serialized typed output")
            if self.failure_code is not None or self.failure_reason is not None:
                raise ValueError("completed attempts cannot carry failure metadata")
        else:
            if self.failure_code is None or self.failure_reason is None:
                raise ValueError("failed attempts require failure code and reason")
        return self


class RunCancellationRequest(StrictModel):
    run_id: UUID
    requested_at: datetime
    reason: NonEmptyStr

    _requested_at_is_aware = field_validator("requested_at")(_validate_aware_datetime)


class ModelInvocationRecord(StrictModel):
    run_id: UUID
    invocation_id: UUID
    stage: Stage
    prompt_version: NonEmptyStr
    model_name: NonEmptyStr
    input_artifact_id: UUID
    output_artifact_id: UUID | None = None
    status: Literal["completed", "failed"]
    invoked_at: datetime

    _invoked_at_is_aware = field_validator("invoked_at")(_validate_aware_datetime)
