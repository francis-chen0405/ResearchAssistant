"""Stable historical provider results and exact accounting, without orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from researchassistant.common.money import ExactUSD, add_usd
from researchassistant.contracts.historical import HistoricalRead, RecordCompatibilityResult
from researchassistant.contracts.models import (
    CandidateQuoteBlock,
    LedgerRecord,
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageAccounting,
    ModelUsageMetadata,
    OrchestrationCheckpoint,
    PlannerOutput,
    PortfolioCoverageAssessment,
    ProvisionalCandidate,
    ResearchGovernorDecision,
    ResearchRoundRecord,
    ResearchTerminalResult,
    ScoreDecision,
    Stage,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
    SynthesisOutput,
    ValidationResult,
)
from researchassistant.contracts.retrieval import ResearcherRetrievalBatch


class ProviderRunStatus(StrEnum):
    RELEASED = "released"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RUNNING = "running"


class ResearcherSideStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ResearcherFailure(StrictModel):
    stage: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    snapshot_id: UUID | None = None


class ResearcherStageResult(StrictModel):
    run_id: UUID
    stance: Literal["supporting", "opposing"]
    status: ResearcherSideStatus
    retrieval_batch: ResearcherRetrievalBatch | None = None
    provisional_candidates: tuple[ProvisionalCandidate, ...] = ()
    candidates: tuple[CandidateQuoteBlock, ...] = ()
    failures: tuple[ResearcherFailure, ...] = ()

    @model_validator(mode="after")
    def validate_side_result(self) -> ResearcherStageResult:
        if self.retrieval_batch is not None:
            if self.retrieval_batch.run_id != self.run_id:
                raise ValueError("retrieval batch must match researcher run_id")
            if self.retrieval_batch.stance.value != self.stance:
                raise ValueError("retrieval batch stance must match researcher result")
        if any(item.run_id != self.run_id for item in self.provisional_candidates):
            raise ValueError("provisional candidate run_id must match researcher result")
        if any(item.run_id != self.run_id for item in self.candidates):
            raise ValueError("candidate run_id must match researcher result")
        if self.status is ResearcherSideStatus.FAILED and not self.failures:
            raise ValueError("failed researcher results require an explicit failure")
        if self.status is ResearcherSideStatus.COMPLETED and self.failures:
            raise ValueError("completed researcher results cannot include failures")
        if self.status is ResearcherSideStatus.SKIPPED and (
            self.retrieval_batch is not None
            or self.provisional_candidates
            or self.candidates
            or self.failures
        ):
            raise ValueError("skipped researcher results cannot contain research artifacts")
        return self


class ResearcherPairResult(StrictModel):
    run_id: UUID
    supporting: ResearcherStageResult
    opposing: ResearcherStageResult

    @model_validator(mode="after")
    def validate_pair(self) -> ResearcherPairResult:
        if self.supporting.run_id != self.run_id or self.opposing.run_id != self.run_id:
            raise ValueError("both researcher sides must match the run_id")
        if self.supporting.stance != "supporting" or self.opposing.stance != "opposing":
            raise ValueError("researcher pair has incorrect stance assignment")
        if (
            self.supporting.retrieval_batch is not None
            and self.opposing.retrieval_batch is not None
            and self.supporting.retrieval_batch.intended_attempt_count
            != self.opposing.retrieval_batch.intended_attempt_count
        ):
            raise ValueError("supporting and opposing retrieval limits must be equal")
        return self


class AnalysisStageResult(StrictModel):
    run_id: UUID
    analyst_decisions: tuple[ScoreDecision, ...]
    statement_drafts: tuple[StatementDraft, ...]
    reviewer_decisions: tuple[StatementReviewResult, ...]
    ledger_records: tuple[LedgerRecord, ...]
    rejected_quote_block_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_analysis_run_ids(self) -> AnalysisStageResult:
        collections: tuple[Sequence[object], ...] = (
            self.analyst_decisions,
            self.statement_drafts,
            self.reviewer_decisions,
            self.ledger_records,
        )
        for artifacts in collections:
            if any(getattr(artifact, "run_id", None) != self.run_id for artifact in artifacts):
                raise ValueError("analysis artifacts must all match the run_id")
        return self


def summarize_model_usage(attempts: Sequence[ModelRouteAttempt]) -> ModelUsageAccounting:
    """Aggregate exact usage separately from conservative unknown-usage exposure."""
    known_tokens = 0
    known_cost = Decimal("0")
    missing_token_ids: list[UUID] = []
    missing_cost_ids: list[UUID] = []
    conservative_tokens = 0
    conservative_cost = Decimal("0")
    token_exposure_provable = True
    cost_exposure_provable = True
    for attempt in attempts:
        usage_is_final = attempt.status is not ModelAttemptStatus.RUNNING
        usage_tokens = (
            _usage_token_total(attempt.usage)
            if usage_is_final and attempt.usage is not None
            else None
        )
        usage_cost = (
            attempt.usage.cost_usd if usage_is_final and attempt.usage is not None else None
        )
        if usage_tokens is None:
            missing_token_ids.append(attempt.attempt_id)
            if attempt.reserved_tokens is None:
                token_exposure_provable = False
            else:
                conservative_tokens += attempt.reserved_tokens
        else:
            known_tokens += usage_tokens
            conservative_tokens += usage_tokens
        if usage_cost is None:
            missing_cost_ids.append(attempt.attempt_id)
            if attempt.reserved_cost_usd is None:
                cost_exposure_provable = False
            else:
                conservative_cost = add_usd(conservative_cost, attempt.reserved_cost_usd)
        else:
            known_cost = add_usd(known_cost, usage_cost)
            conservative_cost = add_usd(conservative_cost, usage_cost)
    token_complete = not missing_token_ids
    cost_complete = not missing_cost_ids
    return ModelUsageAccounting(
        exact_total_tokens=known_tokens if token_complete else None,
        exact_total_cost_usd=known_cost if cost_complete else None,
        known_token_subtotal=known_tokens,
        known_cost_subtotal_usd=known_cost,
        token_complete=token_complete,
        cost_complete=cost_complete,
        missing_token_attempt_ids=tuple(missing_token_ids),
        missing_cost_attempt_ids=tuple(missing_cost_ids),
        conservative_reserved_tokens=(conservative_tokens if token_exposure_provable else None),
        conservative_reserved_cost_usd=(conservative_cost if cost_exposure_provable else None),
    )


class ProviderPipelineResult(StrictModel):
    run_id: UUID
    status: ProviderRunStatus
    raw_claim: str = Field(min_length=1)
    db_path: str = Field(min_length=1)
    current_stage: Stage
    failure_reason: str | None = None
    planner_output: PlannerOutput | None = None
    compatibility_issues: tuple[RecordCompatibilityResult, ...] = ()
    researcher_result: ResearcherPairResult | None = None
    analysis_result: AnalysisStageResult | None = None
    portfolio_coverage: PortfolioCoverageAssessment | None = None
    research_rounds: tuple[ResearchRoundRecord, ...] = ()
    research_governor_decision: ResearchGovernorDecision | None = None
    terminal_research_result: ResearchTerminalResult | None = None
    synthesis_output: SynthesisOutput | None = None
    validation_result: ValidationResult | None = None
    final_brief: str | None = None
    rendered_brief_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checkpoints: tuple[OrchestrationCheckpoint, ...] = ()
    model_attempts: tuple[ModelRouteAttempt, ...] = ()
    usage_accounting: ModelUsageAccounting = Field(
        default_factory=lambda: summarize_model_usage(())
    )
    retrieval_attempts_used: int = Field(default=0, ge=0)
    model_calls_used: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(default=0, ge=0)
    total_cost_usd: ExactUSD | None = Decimal("0")

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> ProviderPipelineResult:
        expected_accounting = summarize_model_usage(self.model_attempts)
        if self.usage_accounting != expected_accounting:
            raise ValueError("usage_accounting must match every persisted physical model attempt")
        if self.total_tokens != expected_accounting.exact_total_tokens:
            raise ValueError("total_tokens must contain only the exact complete token total")
        if self.total_cost_usd != expected_accounting.exact_total_cost_usd:
            raise ValueError("total_cost_usd must contain only the exact complete cost total")
        if self.status is ProviderRunStatus.RELEASED:
            if (
                self.validation_result is None
                or not self.validation_result.valid
                or self.final_brief is None
                or self.rendered_brief_hash is None
            ):
                raise ValueError("released runs require valid validation, final brief, and hash")
            actual_hash = sha256(self.final_brief.encode("utf-8")).hexdigest()
            if self.rendered_brief_hash != actual_hash:
                raise ValueError("released final brief does not match its rendered hash")
        elif self.status is ProviderRunStatus.BLOCKED:
            if self.validation_result is None or self.validation_result.valid:
                raise ValueError("blocked runs require an invalid validation result")
            if self.final_brief is not None or self.rendered_brief_hash is not None:
                raise ValueError("blocked runs cannot carry a final brief or hash")
        elif self.status in {ProviderRunStatus.FAILED, ProviderRunStatus.CANCELLED}:
            if self.failure_reason is None:
                raise ValueError("failed and cancelled runs require an explicit reason")
            if self.final_brief is not None or self.rendered_brief_hash is not None:
                raise ValueError("failed and cancelled runs cannot carry a final brief or hash")
        elif self.status is ProviderRunStatus.RUNNING:
            if self.final_brief is not None or self.rendered_brief_hash is not None:
                raise ValueError("running runs cannot carry a final brief or hash")
        return self


def _combine_analysis_results(
    initial: AnalysisStageResult, targeted: AnalysisStageResult
) -> AnalysisStageResult:
    """Merge independently persisted round results without reprocessing known evidence."""
    # Inspection may combine recognized historical rounds; retain their read-only
    # type so current Ledger rules are never substituted for the recorded rules.
    result_type = (
        type(initial)
        if isinstance(initial, HistoricalRead)
        else type(targeted)
        if isinstance(targeted, HistoricalRead)
        else AnalysisStageResult
    )
    return result_type(
        run_id=initial.run_id,
        analyst_decisions=(*initial.analyst_decisions, *targeted.analyst_decisions),
        statement_drafts=(*initial.statement_drafts, *targeted.statement_drafts),
        reviewer_decisions=(*initial.reviewer_decisions, *targeted.reviewer_decisions),
        ledger_records=tuple(
            sorted(
                (*initial.ledger_records, *targeted.ledger_records),
                key=lambda item: str(item.ledger_claim_id),
            )
        ),
        rejected_quote_block_ids=tuple(
            sorted((*initial.rejected_quote_block_ids, *targeted.rejected_quote_block_ids), key=str)
        ),
    )


def _usage_token_total(usage: ModelUsageMetadata) -> int | None:
    if usage.total_tokens is not None:
        return usage.total_tokens
    if usage.input_tokens is not None and usage.output_tokens is not None:
        return usage.input_tokens + usage.output_tokens
    return None
