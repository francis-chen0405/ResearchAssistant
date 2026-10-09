"""Typed v2 analysis, admission and final-result contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from model_contracts import (
    ApprovedScore,
    CandidateQuoteBlock,
    DiscoveryProvider,
    Entailment,
    LedgerRecord,
    NonEmptyStr,
    NonNegativeInt,
    Placement,
    PositiveInt,
    ReviewerApprovalId,
    Score,
    ScoreDecision,
    SegmentOffset,
    SelectedSentenceRange,
    SourceSnapshot,
    Stance,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
    SynthesisOutput,
    V2AdmissionMethod,
    ValidationError,
    ValidationResult,
    _derive_ledger_score,
    _is_ledger_eligible,
    _placement_matches_score_policy,
    _validate_aware_datetime,
    _validate_offsets,
    entailment_for_claim_fit,
)
from model_research import (
    V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
    V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
    V2_REVIEWER_LEDGER_POLICY_IDENTITY,
    ResearchDirection,
    ResearchDirections,
    V2ClaimCoverageAssessment,
    V2DeepAnalysisBudget,
    V2DeepAnalysisBudgetReason,
    V2GapCoverageReconciliation,
    V2GapCoverageState,
    V2SourceSelectionGap,
    V2SourceSelectionQueueResult,
)
from money import ExactUSD


class V2VerbatimQuoteSelection(StrictModel):
    """V2 Extractor output narrowed to application-owned sentence ranges."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_sentence_ranges: tuple[SelectedSentenceRange, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_selection_shape(self) -> V2VerbatimQuoteSelection:
        previous_end = 0
        for selection_range in self.selected_sentence_ranges:
            if selection_range.start_sentence <= previous_end:
                raise ValueError("sentence ranges must be ordered and non-overlapping")
            previous_end = selection_range.end_sentence
        return self


class V2EvidenceRelationship(StrEnum):
    """How a source-supported proposition relates to the requested claim."""

    SUPPORTS = "supports"
    CHALLENGES = "challenges"
    QUALIFIES = "qualifies"
    UNRELATED = "unrelated"


class V2EvidenceAnalystModelOutput(StrictModel):
    """Luna's compact assessment and final factual statement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    narrowest_supported_proposition: NonEmptyStr = Field(max_length=2000)
    canonical_factual_statement: NonEmptyStr | None = Field(default=None, max_length=2000)
    relationship_to_claim: V2EvidenceRelationship
    material_limitations: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    inferential_boundaries: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    evidence_quality: Score
    claim_fit: Score
    reasoning: NonEmptyStr = Field(max_length=3000)
    addressed_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def validate_relationship_score(self) -> V2EvidenceAnalystModelOutput:
        if self.relationship_to_claim is V2EvidenceRelationship.UNRELATED and self.claim_fit > 2:
            raise ValueError("unrelated evidence cannot receive Claim Fit above 2")
        if len(self.addressed_gap_ids) != len(set(self.addressed_gap_ids)):
            raise ValueError("Analyst addressed Gap IDs must be unique")
        return self


class V2CanonicalStatementModelOutput(StrictModel):
    """Luna's narrow statement draft, kept separate from its source assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    narrowest_supported_proposition: NonEmptyStr = Field(max_length=2000)
    canonical_factual_statement: NonEmptyStr = Field(max_length=2000)
    reasoning: NonEmptyStr = Field(max_length=2000)


class V2EvidenceAnalystCandidateInput(StrictModel):
    """One exact, application-assembled candidate assigned to a queued survivor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    snapshot: SourceSnapshot

    @model_validator(mode="after")
    def validate_exact_candidate_provenance(self) -> V2EvidenceAnalystCandidateInput:
        if self.candidate.run_id != self.snapshot.run_id:
            raise ValueError("Phase-9 candidate and snapshot must share a run_id")
        if self.candidate.snapshot_id != self.snapshot.snapshot_id:
            raise ValueError("Phase-9 candidate and snapshot IDs must match")
        if self.candidate.snapshot_sha256 != self.snapshot.snapshot_sha256:
            raise ValueError("Phase-9 candidate and snapshot hashes must match")
        expected_stance = (
            Stance.SUPPORTING if self.direction is ResearchDirection.SUPPORT else Stance.OPPOSING
        )
        if self.candidate.stance is not expected_stance:
            raise ValueError("candidate stance must preserve its queued research direction")
        return self


class V2EvidenceAnalystSnapshotContext(StrictModel):
    """Small source envelope supplied to Luna instead of the complete snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: NonEmptyStr
    word_count: NonNegativeInt
    truncated: bool
    preceding_context: NonEmptyStr
    following_context: NonEmptyStr


class V2EvidenceAnalystExtractionFailure(StrictModel):
    """Exact Phase-8 extraction failure retained for the Phase-9 handoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    failure: NonEmptyStr


class V2EvidenceAnalystBatchInput(StrictModel):
    """Complete Phase-8 queue plus the exact candidates available for Analyst work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    queue_result: V2SourceSelectionQueueResult
    queued_candidates: tuple[V2EvidenceAnalystCandidateInput, ...]
    extraction_failures: tuple[V2EvidenceAnalystExtractionFailure, ...] = ()
    policy_identity: str = V2_EVIDENCE_ANALYST_POLICY_IDENTITY

    @model_validator(mode="after")
    def validate_complete_queue(self) -> V2EvidenceAnalystBatchInput:
        if self.queue_result.run_id != self.run_id:
            raise ValueError("Phase-9 input must match the Phase-8 run")
        if self.queue_result.input.exact_claim != self.exact_claim:
            raise ValueError("Phase-9 exact claim must match Phase-8")
        if self.queue_result.input.directions != self.directions:
            raise ValueError("Phase-9 directions must match Phase-8")
        source_ids = tuple(item.source_id for item in self.queued_candidates)
        expected_order = tuple(
            source_id
            for source_id in self.queue_result.queued_source_ids
            if source_id in set(source_ids)
        )
        if source_ids != expected_order or len(source_ids) != len(set(source_ids)):
            raise ValueError(
                "Phase-9 candidates must be a unique order-preserving subset of the queue"
            )
        extraction_failure_ids = tuple(item.source_id for item in self.extraction_failures)
        queued_ids = set(self.queue_result.queued_source_ids)
        if len(extraction_failure_ids) != len(set(extraction_failure_ids)):
            raise ValueError("Phase-9 extraction failures must identify unique sources")
        if not set(extraction_failure_ids).issubset(queued_ids):
            raise ValueError("Phase-9 extraction failures must belong to the queued sources")
        for item in self.queued_candidates:
            if item.candidate.run_id != self.run_id:
                raise ValueError("Phase-9 candidates must match the run")
            self.directions.require_permitted(item.direction)
        return self


class V2EvidenceAnalystLLMInput(StrictModel):
    """Bounded semantic input with source, proposition, and relationship kept distinct."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    snapshot_context: V2EvidenceAnalystSnapshotContext
    targeted_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=3)


class V2CanonicalStatementLLMInput(StrictModel):
    """Application-approved score context for one canonical factual statement draft."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    assessment: V2EvidenceAnalystModelOutput
    score_decision: ScoreDecision


class V2CanonicalStatementRevisionLLMInput(StrictModel):
    """One bounded Reviewer-directed revision without changing the proposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    direction: ResearchDirection
    candidate: CandidateQuoteBlock
    assessment: V2EvidenceAnalystModelOutput
    score_decision: ScoreDecision
    current_statement: StatementDraft
    reviewer_rationale: NonEmptyStr = Field(max_length=3000)
    revision_number: Literal[1] = 1


class V2EvidenceAnalystRevisionResult(StrictModel):
    """Typed post-Reviewer Analyst revision; it still grants no Ledger admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    previous_statement_draft_id: UUID
    revised_statement: StatementDraft
    analyst_attempt_ids: tuple[UUID, ...] = Field(min_length=1, max_length=2)


class V2EvidenceAnalystState(StrEnum):
    NOT_QUEUED = "not_queued"
    READY_FOR_ADMISSION = "ready_for_admission"
    READY_FOR_REVIEWER = "ready_for_reviewer"
    REJECTED = "rejected"
    FAILED = "failed"


class V2EvidenceAnalystSourceResult(StrictModel):
    """Deep-analysis status for one survivor; no state grants Ledger admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    state: V2EvidenceAnalystState
    candidate: CandidateQuoteBlock | None = None
    assessment: V2EvidenceAnalystModelOutput | None = None
    score_decision: ScoreDecision | None = None
    statement_draft: StatementDraft | None = None
    analyst_attempt_ids: tuple[UUID, ...] = ()
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_state(self) -> V2EvidenceAnalystSourceResult:
        semantic_values = (self.assessment, self.score_decision, self.statement_draft)
        if self.state is V2EvidenceAnalystState.NOT_QUEUED:
            if self.candidate is not None or any(value is not None for value in semantic_values):
                raise ValueError("non-queued survivors cannot carry deep-analysis artifacts")
            if self.analyst_attempt_ids or self.failure is not None:
                raise ValueError("non-queued survivors cannot carry Analyst attempt state")
            return self
        if self.state is V2EvidenceAnalystState.FAILED:
            if self.failure is None:
                raise ValueError("failed Analyst results require a failure reason")
            if self.statement_draft is not None:
                raise ValueError("failed Analyst results cannot be Reviewer-ready")
            if self.candidate is None and any(value is not None for value in semantic_values):
                raise ValueError("failed extraction cannot carry Analyst semantic artifacts")
            return self
        if self.candidate is None:
            raise ValueError("completed queued results must retain their exact candidate")
        if self.failure is not None or self.assessment is None or self.score_decision is None:
            raise ValueError("completed Analyst results require assessment and score decision")
        if self.state is V2EvidenceAnalystState.REJECTED:
            if self.score_decision.approved or self.statement_draft is not None:
                raise ValueError("rejected Analyst results cannot carry a statement draft")
        elif not self.score_decision.approved or self.statement_draft is None:
            raise ValueError("Reviewer-ready results require an approved score and draft")
        return self


class V2EvidenceAnalystBatchResult(StrictModel):
    """Restartable Phase-9 output covering every survivor and containing no Ledger records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input: V2EvidenceAnalystBatchInput
    source_results: tuple[V2EvidenceAnalystSourceResult, ...]
    completed_at: datetime
    policy_identity: str = V2_EVIDENCE_ANALYST_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_complete_survivor_output(self) -> V2EvidenceAnalystBatchResult:
        if self.input.run_id != self.run_id:
            raise ValueError("Phase-9 result must match its input run")
        expected = tuple(item.source_id for item in self.input.queue_result.input.survivors)
        actual = tuple(item.source_id for item in self.source_results)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("Phase-9 output must retain every survivor in Phase-8 order")
        directions = {
            item.source_id: item.direction for item in self.input.queue_result.input.survivors
        }
        queued = set(self.input.queue_result.queued_source_ids)
        for item in self.source_results:
            if item.run_id != self.run_id:
                raise ValueError("Phase-9 source results must match the run")
            if item.direction is not directions[item.source_id]:
                raise ValueError("Phase-9 survivor direction cannot change")
            if (item.source_id in queued) == (item.state is V2EvidenceAnalystState.NOT_QUEUED):
                raise ValueError("Phase-9 queued state must match Phase-8")
        return self


class V2LedgerProvenance(StrictModel):
    """Immutable v2 discovery context attached to, but never used to relax, Ledger admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    research_direction: ResearchDirection
    discovery_round: Annotated[int, Field(ge=1, le=4)]
    source_family_id: NonEmptyStr
    recommended: bool
    relevant_gap_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=18)


class V2EvidenceAdmissionRecord(StrictModel):
    """Analyzer-admitted evidence; Reviewer metadata is retained only for compatibility."""

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
    admission_method: V2AdmissionMethod
    admission_policy_identity: NonEmptyStr
    admitted_at: datetime
    reviewer_prompt_version: NonEmptyStr | None = None
    reviewer_model_name: NonEmptyStr | None = None
    reviewed_at: datetime | None = None
    reviewer_approval_id: ReviewerApprovalId | None = None
    ledger_validated_at: datetime

    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)
    _analyst_completed_at_is_aware = field_validator("analyst_completed_at")(
        _validate_aware_datetime
    )
    _admitted_at_is_aware = field_validator("admitted_at")(_validate_aware_datetime)
    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)
    _ledger_validated_at_is_aware = field_validator("ledger_validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_score_and_admission(self) -> V2EvidenceAdmissionRecord:
        if not _is_ledger_eligible(self.evidence_quality, self.claim_fit):
            raise ValueError("evidence admission requires eligible two-axis scores")
        if self.ledger_score != _derive_ledger_score(self.evidence_quality, self.claim_fit):
            raise ValueError("evidence admission requires the derived Ledger score")
        if not _placement_matches_score_policy(
            self.evidence_quality, self.claim_fit, self.placement
        ):
            raise ValueError("evidence admission requires the derived placement")
        if self.entailment is not entailment_for_claim_fit(self.claim_fit):
            raise ValueError("evidence admission entailment must be derived from Claim Fit")
        reviewer_values = (
            self.reviewer_prompt_version,
            self.reviewer_model_name,
            self.reviewed_at,
            self.reviewer_approval_id,
        )
        if self.admission_method is V2AdmissionMethod.ANALYZER_ADMITTED and any(
            value is not None for value in reviewer_values
        ):
            raise ValueError("analyzer-admitted evidence cannot carry Reviewer metadata")
        if self.admission_method is V2AdmissionMethod.REVIEWER_APPROVED and any(
            value is None for value in reviewer_values
        ):
            raise ValueError("Reviewer-approved evidence requires complete Reviewer metadata")
        return self


class V2EvidenceAdmissionState(StrEnum):
    NOT_QUEUED = "not_queued"
    ANALYST_REJECTED = "analyst_rejected"
    ANALYST_FAILED = "analyst_failed"
    ANALYZER_ADMITTED = "analyzer_admitted"


class V2EvidenceAdmissionSourceResult(StrictModel):
    """Deterministic admission outcome for one analyzed survivor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    state: V2EvidenceAdmissionState
    provenance: V2LedgerProvenance
    evidence_record: V2EvidenceAdmissionRecord | None = None
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_admission_shape(self) -> V2EvidenceAdmissionSourceResult:
        if self.provenance.source_id != self.source_id:
            raise ValueError("admission provenance source_id must match the source result")
        if self.provenance.research_direction is not self.direction:
            raise ValueError("admission provenance direction must match the source result")
        if self.state is V2EvidenceAdmissionState.ANALYZER_ADMITTED:
            if self.evidence_record is None or self.failure is not None:
                raise ValueError("analyzer-admitted results require an evidence record")
            if self.evidence_record.admission_method is not V2AdmissionMethod.ANALYZER_ADMITTED:
                raise ValueError("fresh evidence records must be analyzer-admitted")
            if self.evidence_record.run_id != self.run_id:
                raise ValueError("evidence record run_id must match the source result")
            return self
        if self.evidence_record is not None:
            raise ValueError("only analyzer-admitted results may carry an evidence record")
        if self.state is V2EvidenceAdmissionState.ANALYST_FAILED and self.failure is None:
            raise ValueError("failed admission results require a failure reason")
        if self.state is not V2EvidenceAdmissionState.ANALYST_FAILED and self.failure is not None:
            raise ValueError("only failed admission results may carry a failure reason")
        return self


class V2EvidenceAdmissionBatchResult(StrictModel):
    """Restartable deterministic bridge from the Analyst to final synthesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    analyst_result: V2EvidenceAnalystBatchResult
    source_results: tuple[V2EvidenceAdmissionSourceResult, ...]
    completed_at: datetime
    policy_identity: str = V2_EVIDENCE_ADMISSION_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_complete_results(self) -> V2EvidenceAdmissionBatchResult:
        if self.analyst_result.run_id != self.run_id:
            raise ValueError("evidence admission must match its Analyst result")
        expected = tuple(item.source_id for item in self.analyst_result.source_results)
        actual = tuple(item.source_id for item in self.source_results)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("evidence admission must retain every survivor in order")
        return self


class V2ReviewerLedgerState(StrEnum):
    NOT_QUEUED = "not_queued"
    ANALYST_REJECTED = "analyst_rejected"
    ANALYST_FAILED = "analyst_failed"
    REVIEWER_REJECTED = "reviewer_rejected"
    REVIEWER_FAILED = "reviewer_failed"
    ADMITTED = "admitted"


class V2ReviewerLedgerSourceResult(StrictModel):
    """Complete downstream outcome for one Phase-9 survivor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    state: V2ReviewerLedgerState
    provenance: V2LedgerProvenance
    review_results: tuple[StatementReviewResult, ...] = Field(max_length=1)
    ledger_record: LedgerRecord | None = None
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> V2ReviewerLedgerSourceResult:
        if self.provenance.source_id != self.source_id:
            raise ValueError("Ledger provenance source_id must match the source result")
        if self.provenance.research_direction is not self.direction:
            raise ValueError("Ledger provenance direction must match the source result")
        if self.state is V2ReviewerLedgerState.ADMITTED:
            if self.ledger_record is None or not self.review_results or self.failure is not None:
                raise ValueError(
                    "admitted source results require a Ledger record and approval history"
                )
            return self
        if self.ledger_record is not None:
            raise ValueError("only admitted source results may carry a Ledger record")
        if (
            self.state
            in {
                V2ReviewerLedgerState.NOT_QUEUED,
                V2ReviewerLedgerState.ANALYST_REJECTED,
                V2ReviewerLedgerState.ANALYST_FAILED,
            }
            and self.review_results
        ):
            raise ValueError("non-Reviewer source results cannot carry Reviewer decisions")
        if self.state is V2ReviewerLedgerState.REVIEWER_REJECTED and not self.review_results:
            raise ValueError("Reviewer rejection requires the retained Reviewer decisions")
        if self.state is V2ReviewerLedgerState.REVIEWER_FAILED and self.failure is None:
            raise ValueError("Reviewer failure requires an explicit failure reason")
        return self


class V2ReviewerLedgerBatchResult(StrictModel):
    """Restartable Phase-10 bridge from Analyst survivors to immutable Ledger admissions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    analyst_result: V2EvidenceAnalystBatchResult
    source_results: tuple[V2ReviewerLedgerSourceResult, ...]
    completed_at: datetime
    policy_identity: Literal["researchassistant-v2-phase-10-reviewer-ledger-v2"] = (
        V2_REVIEWER_LEDGER_POLICY_IDENTITY
    )

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_complete_results(self) -> V2ReviewerLedgerBatchResult:
        if self.analyst_result.run_id != self.run_id:
            raise ValueError("Phase-10 result must match its Phase-9 input")
        expected = tuple(item.source_id for item in self.analyst_result.source_results)
        actual = tuple(item.source_id for item in self.source_results)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("Phase-10 output must retain every Phase-9 survivor in order")
        return self


class V2DeepAnalysisSourceExecutionState(StrEnum):
    ADMITTED = "admitted"
    ANALYZER_ADMITTED = "analyzer_admitted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXTRACTION_FAILED = "extraction_failed"
    ANALYST_REJECTED = "analyst_rejected"
    ANALYST_FAILED = "analyst_failed"
    REVIEWER_REJECTED = "reviewer_rejected"
    REVIEWER_FAILED = "reviewer_failed"
    NOT_ATTEMPTED = "not_attempted"


class V2DeepAnalysisSourceExecution(StrictModel):
    """Typed terminal outcome retained by the source backfill controller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    state: V2DeepAnalysisSourceExecutionState
    physical_call_sequences: tuple[PositiveInt, ...] = ()
    failure_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_execution(self) -> V2DeepAnalysisSourceExecution:
        if self.state is V2DeepAnalysisSourceExecutionState.NOT_ATTEMPTED:
            if self.physical_call_sequences or self.failure_reason is not None:
                raise ValueError("unattempted sources cannot carry execution evidence")
        elif self.state in {
            V2DeepAnalysisSourceExecutionState.ADMITTED,
            V2DeepAnalysisSourceExecutionState.ANALYZER_ADMITTED,
        }:
            if self.failure_reason is not None:
                raise ValueError("admitted sources cannot carry a failure reason")
        elif self.failure_reason is None:
            raise ValueError("terminal source failures require an explicit reason")
        return self


class V2DeepAnalysisSourceReconciliation(StrictModel):
    """Per-source conservative exposure reconciliation, independent of run totals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    source_cap_tokens: Literal[60000] = V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP
    source_cap_cost_usd: ExactUSD
    accounted_tokens: NonNegativeInt
    released_tokens: NonNegativeInt
    accounted_cost_usd: ExactUSD
    released_cost_usd: ExactUSD
    physical_call_sequences: tuple[PositiveInt, ...] = ()

    @model_validator(mode="after")
    def validate_reconciliation(self) -> V2DeepAnalysisSourceReconciliation:
        expected_release = max(0, self.source_cap_tokens - self.accounted_tokens)
        if self.released_tokens != expected_release:
            raise ValueError("source token release must reconcile exactly to its cap")
        expected_cost_release = max(
            Decimal("0"), self.source_cap_cost_usd - self.accounted_cost_usd
        )
        if self.released_cost_usd != expected_cost_release:
            raise ValueError("source cost release must reconcile exactly to its cap")
        return self


class V2DeepAnalysisBackfillResult(StrictModel):
    """Versioned final deep-analysis execution consumed by downstream synthesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    original_queued_source_ids: tuple[UUID, ...]
    replacement_source_ids: tuple[UUID, ...]
    final_execution_order: tuple[UUID, ...]
    final_queue_result: V2SourceSelectionQueueResult
    source_executions: tuple[V2DeepAnalysisSourceExecution, ...]
    source_reconciliations: tuple[V2DeepAnalysisSourceReconciliation, ...]
    remaining_run_budget: V2DeepAnalysisBudget
    final_admission_result: V2EvidenceAdmissionBatchResult | None = None
    final_reviewer_result: V2ReviewerLedgerBatchResult | None = None
    terminal_reasons: tuple[NonEmptyStr, ...] = ()
    completed_at: datetime
    policy_identity: str = V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_backfill(self) -> V2DeepAnalysisBackfillResult:
        if self.run_id != self.final_queue_result.run_id:
            raise ValueError("backfill and final queue must share the run")
        if self.final_admission_result is None and self.final_reviewer_result is None:
            raise ValueError("backfill must retain an admission or historical Reviewer result")
        if self.final_admission_result is not None and (
            self.final_admission_result.run_id != self.run_id
        ):
            raise ValueError("backfill and final admission result must share the run")
        if (
            self.final_reviewer_result is not None
            and self.final_reviewer_result.run_id != self.run_id
        ):
            raise ValueError("backfill and historical Reviewer result must share the run")
        if len(self.final_execution_order) != len(set(self.final_execution_order)):
            raise ValueError("final execution order cannot contain duplicates")
        if self.final_queue_result.queued_source_ids != self.final_execution_order:
            raise ValueError("final queue must reproduce the final execution order")
        if len(self.replacement_source_ids) != len(set(self.replacement_source_ids)):
            raise ValueError("replacement source IDs must be unique")
        if set(self.replacement_source_ids) & set(self.original_queued_source_ids):
            raise ValueError("replacement source IDs cannot repeat original queued sources")
        if not set(self.original_queued_source_ids).issubset(
            set(self.final_execution_order) | set(item.source_id for item in self.source_executions)
        ):
            raise ValueError("backfill must retain every original queued source outcome")
        if tuple(item.source_id for item in self.source_executions) != tuple(
            item.source_id for item in self.source_reconciliations
        ):
            raise ValueError("source execution and reconciliation order must match")
        return self


class V2SynthesizerLedgerItem(StrictModel):
    """The only evidence projection available to the v2 Synthesizer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    ledger_claim_id: UUID
    reviewer_approval_id: ReviewerApprovalId | None = None
    admission_method: V2AdmissionMethod = V2AdmissionMethod.REVIEWER_APPROVED
    stance: Stance
    placement: Placement
    entailment: Entailment
    approved_factual_statement: NonEmptyStr


class V2SynthesizerRecommendationMetadata(StrictModel):
    """Non-evidentiary source-selection state retained for the v2 synthesizer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    recommended: bool
    queued_for_deep_analysis: bool
    budget_prevented_reason: V2DeepAnalysisBudgetReason | None = None


class V2SynthesizerInput(StrictModel):
    """Bounded v2 synthesis projection with no raw-source text or unreviewed claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    approved_ledger_items: tuple[V2SynthesizerLedgerItem, ...] = Field(min_length=1)
    qualifications: tuple[V2SynthesizerLedgerItem, ...]
    unresolved_material_gaps: tuple[V2SourceSelectionGap, ...]
    stopping_reason: NonEmptyStr
    recommendation_metadata: tuple[V2SynthesizerRecommendationMetadata, ...]

    @model_validator(mode="after")
    def validate_v2_synthesis_input(self) -> V2SynthesizerInput:
        item_ids = tuple(item.ledger_claim_id for item in self.approved_ledger_items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("v2 synthesis Ledger claim IDs must be unique")
        if any(not self.directions.permits(item.direction) for item in self.approved_ledger_items):
            raise ValueError("v2 synthesis cannot include disabled-direction evidence")
        if any(
            item.placement is not Placement.QUALIFIED_ONLY for item in self.qualifications
        ) or not set(self.qualifications).issubset(set(self.approved_ledger_items)):
            raise ValueError("v2 synthesis qualifications must be approved qualified-only evidence")
        source_ids = tuple(item.source_id for item in self.recommendation_metadata)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("v2 synthesis recommendation metadata must have unique source IDs")
        if any(
            not self.directions.permits(item.direction) for item in self.recommendation_metadata
        ):
            raise ValueError("v2 synthesis cannot include disabled-direction recommendations")
        if any(not self.directions.permits(gap.direction) for gap in self.unresolved_material_gaps):
            raise ValueError("v2 synthesis cannot include disabled-direction gaps")
        return self


class V2ProviderRunDiagnostics(StrictModel):
    """Persisted, non-evidentiary outcome counts for one discovery provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: DiscoveryProvider
    query_attempts: NonNegativeInt = 0
    non_empty_queries: NonNegativeInt = 0
    empty_queries: NonNegativeInt = 0
    timeout_queries: NonNegativeInt = 0
    failed_queries: NonNegativeInt = 0
    search_results: NonNegativeInt = 0
    surviving_sources: NonNegativeInt = 0

    @model_validator(mode="after")
    def validate_query_counts(self) -> V2ProviderRunDiagnostics:
        counted_attempts = (
            self.non_empty_queries + self.empty_queries + self.timeout_queries + self.failed_queries
        )
        if counted_attempts != self.query_attempts:
            raise ValueError("provider query outcome counts must reconcile to query attempts")
        return self


class V2RunDiagnostics(StrictModel):
    """Persisted v2 execution facts used by the live result page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configured_providers: tuple[DiscoveryProvider, ...] = Field(min_length=1, max_length=6)
    provider_outcomes: tuple[V2ProviderRunDiagnostics, ...]
    search_attempts: NonNegativeInt = 0
    search_results: NonNegativeInt = 0
    acquisition_attempts: NonNegativeInt = 0
    sources_acquired: NonNegativeInt = 0
    sources_survived_probe: NonNegativeInt = 0
    sources_queued_for_analysis: NonNegativeInt = 0
    sources_analyzed: NonNegativeInt = 0
    approved_evidence_records: NonNegativeInt = 0

    @model_validator(mode="after")
    def validate_diagnostics(self) -> V2RunDiagnostics:
        configured = self.configured_providers
        outcome_providers = tuple(item.provider for item in self.provider_outcomes)
        if len(set(configured)) != len(configured):
            raise ValueError("configured discovery providers must be unique")
        if outcome_providers != configured:
            raise ValueError("provider diagnostics must preserve configured provider order")
        if self.search_attempts != sum(item.query_attempts for item in self.provider_outcomes):
            raise ValueError("search attempts must reconcile to provider diagnostics")
        if self.search_results != sum(item.search_results for item in self.provider_outcomes):
            raise ValueError("search results must reconcile to provider diagnostics")
        return self


class V2ResultSourceStatus(StrEnum):
    RECOMMENDED_ANALYZED = "recommended_analyzed"
    RECOMMENDED_ANALYZER_ADMITTED = "recommended_analyzer_admitted"
    RECOMMENDED_ANALYZER_REJECTED = "recommended_analyzer_rejected"
    RECOMMENDED_ANALYZER_FAILED = "recommended_analyzer_failed"
    RECOMMENDED_NO_LEDGER_EVIDENCE = "recommended_no_ledger_evidence"
    SURVIVING_ANALYZED = "surviving_analyzed"
    SURVIVING_ANALYZER_ADMITTED = "surviving_analyzer_admitted"
    SURVIVING_ANALYZER_REJECTED = "surviving_analyzer_rejected"
    SURVIVING_ANALYZER_FAILED = "surviving_analyzer_failed"
    SURVIVING_NOT_DEEPLY_ANALYZED = "surviving_not_deeply_analyzed"
    BUDGET_PREVENTED_ANALYSIS = "budget_prevented_analysis"


class V2ResultSource(StrictModel):
    """Presentation-safe source metadata; it contains no source-derived factual prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    source_url: NonEmptyStr
    title: NonEmptyStr | None = None
    source_type: NonEmptyStr | None = None
    publication_date: NonEmptyStr | None = None
    discovery_providers: tuple[DiscoveryProvider, ...]
    discovery_round: Annotated[int, Field(ge=1, le=4)]
    recommended: bool
    recommendation_rank: PositiveInt | None = None
    queue_rank: PositiveInt | None = None
    status: V2ResultSourceStatus
    ledger_claim_ids: tuple[UUID, ...] = ()
    budget_prevented_reason: V2DeepAnalysisBudgetReason | None = None

    @model_validator(mode="after")
    def validate_source_status(self) -> V2ResultSource:
        if self.recommended != (self.recommendation_rank is not None):
            raise ValueError("v2 result recommendation state and rank must agree")
        if self.status is V2ResultSourceStatus.BUDGET_PREVENTED_ANALYSIS:
            if self.budget_prevented_reason is None or self.ledger_claim_ids:
                raise ValueError("budget-prevented sources cannot have Ledger evidence")
        elif self.budget_prevented_reason is not None:
            raise ValueError("only budget-prevented sources may carry a budget reason")
        if self.status is V2ResultSourceStatus.RECOMMENDED_ANALYZED:
            if not self.recommended or not self.ledger_claim_ids:
                raise ValueError("recommended analyzed sources require Ledger evidence")
        if self.status is V2ResultSourceStatus.RECOMMENDED_ANALYZER_ADMITTED:
            if not self.recommended or not self.ledger_claim_ids:
                raise ValueError("recommended analyzer-admitted sources require evidence")
        if self.status in {
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_REJECTED,
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_FAILED,
        }:
            if not self.recommended or self.ledger_claim_ids:
                raise ValueError("recommended analyzer-terminal sources cannot carry evidence")
        if self.status is V2ResultSourceStatus.RECOMMENDED_NO_LEDGER_EVIDENCE:
            if not self.recommended or self.ledger_claim_ids:
                raise ValueError("recommended no-Ledger sources cannot carry Ledger evidence")
        if self.status is V2ResultSourceStatus.SURVIVING_ANALYZED:
            if self.recommended or not self.ledger_claim_ids:
                raise ValueError(
                    "surviving analyzed sources require nonrecommended Ledger evidence"
                )
        if self.status is V2ResultSourceStatus.SURVIVING_ANALYZER_ADMITTED:
            if self.recommended or not self.ledger_claim_ids:
                raise ValueError(
                    "surviving analyzer-admitted sources require nonrecommended evidence"
                )
        if self.status in {
            V2ResultSourceStatus.SURVIVING_ANALYZER_REJECTED,
            V2ResultSourceStatus.SURVIVING_ANALYZER_FAILED,
        }:
            if self.recommended or self.ledger_claim_ids:
                raise ValueError("surviving analyzer-terminal sources cannot carry evidence")
        if self.status is V2ResultSourceStatus.SURVIVING_NOT_DEEPLY_ANALYZED:
            if self.recommended or self.ledger_claim_ids:
                raise ValueError("unanalysed surviving sources cannot carry Ledger evidence")
        return self


class V2UnresolvedMaterialGap(StrictModel):
    """A persisted strategy gap, disclosed without inventing an answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: NonEmptyStr
    direction: ResearchDirection
    missing_evidence: NonEmptyStr
    assessed_after_round: Annotated[int, Field(ge=1, le=3)]


class V2ResearchStoppingReason(StrEnum):
    SUFFICIENT_SOURCE_POOL = "sufficient_source_pool"
    NO_USEFUL_NEW_DIRECTION = "no_useful_new_direction"
    DUPLICATE_HEAVY = "duplicate_heavy"
    PROVIDER_ELIGIBILITY_EXHAUSTED = "provider_eligibility_exhausted"
    BUDGET = "budget"
    HARD_ROUND_LIMIT = "hard_round_limit"
    DEGRADED_GAP_SEARCH_AGENT = "degraded_gap_search_agent"
    INVALID_SEARCH_AGENT_PLAN = "invalid_search_agent_plan"


class V2ResearchStoppingDisclosure(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: V2ResearchStoppingReason
    explanation: NonEmptyStr
    completed_rounds: Annotated[int, Field(ge=1, le=4)]


class V2ReleaseValidation(StrictModel):
    """The v2 release decision hashes the complete rendered output, not just evidence text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_validation: ValidationResult
    valid: bool
    errors: tuple[ValidationError, ...]
    validator_config_version: NonEmptyStr
    validated_at: datetime
    rendered_output_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    _validated_at_is_aware = field_validator("validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_release_state(self) -> V2ReleaseValidation:
        if self.valid and not self.evidence_validation.valid:
            raise ValueError("a v2 release cannot bypass failed evidence validation")
        if self.valid:
            if self.errors or self.rendered_output_hash is None:
                raise ValueError("valid v2 releases require no errors and a complete output hash")
        elif not self.errors or self.rendered_output_hash is not None:
            raise ValueError("invalid v2 releases require errors and no output hash")
        return self


class V2FinalResearchOutput(StrictModel):
    """Complete v2 result envelope, separating Ledger facts from research disclosures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    exact_claim: NonEmptyStr
    directions: ResearchDirections
    synthesis: SynthesisOutput
    recommended_source_ids: tuple[UUID, ...]
    recommended_sources: tuple[V2ResultSource, ...]
    all_surviving_sources: tuple[V2ResultSource, ...]
    unresolved_material_gaps: tuple[V2UnresolvedMaterialGap, ...]
    claim_coverage_map: tuple[V2ClaimCoverageAssessment, ...] = Field(default=(), max_length=6)
    gap_reconciliation: V2GapCoverageReconciliation | None = None
    stopping: V2ResearchStoppingDisclosure
    created_at: datetime
    release_validation: V2ReleaseValidation

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_final_output(self) -> V2FinalResearchOutput:
        if self.synthesis.run_id != self.run_id:
            raise ValueError("v2 final output synthesis must match the run")
        all_ids = tuple(item.source_id for item in self.all_surviving_sources)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("v2 final output sources must be unique")
        if any(not self.directions.permits(item.direction) for item in self.all_surviving_sources):
            raise ValueError("v2 final output cannot expose disabled-direction sources")
        if any(
            not self.directions.permits(item.direction) for item in self.unresolved_material_gaps
        ):
            raise ValueError("v2 final output cannot expose disabled-direction gaps")
        recommended_ids = tuple(item.source_id for item in self.recommended_sources)
        if recommended_ids != self.recommended_source_ids:
            raise ValueError("recommended source list must reproduce recommendation IDs")
        if any(not item.recommended for item in self.recommended_sources):
            raise ValueError("recommended source list may contain only recommended sources")
        if set(recommended_ids) - set(all_ids):
            raise ValueError("recommended source IDs must exist in surviving source list")
        if self.gap_reconciliation is not None:
            if self.gap_reconciliation.run_id != self.run_id:
                raise ValueError("Gap reconciliation must match the final-output run")
            if self.claim_coverage_map != self.gap_reconciliation.claim_coverage_map:
                raise ValueError("final claim coverage must match the Gap reconciliation")
            unresolved_ids = tuple(item.gap_id for item in self.unresolved_material_gaps)
            expected_ids = tuple(
                item.gap.gap_id
                for item in self.gap_reconciliation.records
                if item.state is not V2GapCoverageState.COVERED
            )
            if unresolved_ids != expected_ids:
                raise ValueError(
                    "final unresolved gaps must exactly reproduce non-covered reconciliation gaps"
                )
        return self
