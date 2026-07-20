from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import Field, model_validator

from agents.researcher import parse_extracted_quote_block
from models import (
    CandidateQuoteBlock,
    ReviewerFailureCode,
    Score,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
)


class ReviewerInput(StrictModel):
    extracted_quote_block: str = Field(min_length=1)
    preceding_context: str = Field(min_length=1)
    following_context: str = Field(min_length=1)
    draft_statement: str = Field(min_length=1)
    claim_fit: Score


class ReviewChecks(StrictModel):
    fully_entailed: bool
    qualifications_preserved: bool
    neutral_framing: bool
    claim_fit_scope_valid: bool


class ReviewerDecision(StrictModel):
    """Narrow model-facing Reviewer output with no application-owned identifiers."""

    reviewed_statement: str = Field(min_length=1)
    approved: bool
    failure_code: ReviewerFailureCode | None = None
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision_shape(self) -> ReviewerDecision:
        if self.approved and self.failure_code is not None:
            raise ValueError("approved Reviewer decisions cannot include a failure code")
        if not self.approved and self.failure_code is None:
            raise ValueError("rejected Reviewer decisions require a failure code")
        return self


REVIEWER_DECISION_SCHEMA_VERSION = "reviewer-decision-v1"
REVIEWER_APPROVAL_DERIVATION_VERSION = "rappr_v1"


def build_reviewer_input(
    candidate: CandidateQuoteBlock,
    draft: StatementDraft,
) -> ReviewerInput:
    if draft.run_id != candidate.run_id:
        raise ValueError("statement draft run_id must match candidate run_id")
    if draft.quote_block_id != candidate.quote_block_id:
        raise ValueError("statement draft quote_block_id must match candidate")
    if draft.stance is not candidate.stance:
        raise ValueError("statement draft stance must match candidate stance")

    parsed_quote = parse_extracted_quote_block(candidate.extracted_quote_block)
    return ReviewerInput(
        extracted_quote_block=candidate.extracted_quote_block,
        preceding_context=parsed_quote.preceding_context,
        following_context=parsed_quote.following_context,
        draft_statement=draft.draft_statement,
        claim_fit=draft.claim_fit,
    )


def review_statement(
    draft: StatementDraft,
    reviewer_input: ReviewerInput,
    checks: ReviewChecks,
    *,
    reviewer_prompt_version: str,
    reviewer_model_name: str,
    reviewed_at: datetime,
) -> StatementReviewResult:
    failure_code = _first_failure_code(checks)
    if failure_code is None:
        decision = ReviewerDecision(
            reviewed_statement=draft.draft_statement,
            approved=True,
            rationale="Reviewer checks passed.",
        )
    else:
        decision = ReviewerDecision(
            reviewed_statement=draft.draft_statement,
            approved=False,
            failure_code=failure_code,
            rationale=_failure_rationale(failure_code),
        )
    return build_statement_review_result(
        draft,
        reviewer_input,
        decision,
        reviewer_prompt_version=reviewer_prompt_version,
        reviewer_model_name=reviewer_model_name,
        reviewed_at=reviewed_at,
    )


def validate_reviewer_decision(
    draft: StatementDraft,
    reviewer_input: ReviewerInput,
    decision: ReviewerDecision,
) -> None:
    if reviewer_input.draft_statement != draft.draft_statement:
        raise ValueError("Reviewer input draft statement must match the StatementDraft")
    if reviewer_input.claim_fit != draft.claim_fit:
        raise ValueError("Reviewer input Claim Fit must match the StatementDraft")
    if decision.reviewed_statement != draft.draft_statement:
        raise ValueError("Reviewer decision text must exactly match the reviewed StatementDraft")


def derive_reviewer_approval_id(
    draft: StatementDraft,
    decision: ReviewerDecision,
) -> str:
    if not decision.approved:
        raise ValueError("only approved Reviewer decisions receive an approval ID")
    if decision.reviewed_statement != draft.draft_statement:
        raise ValueError("Reviewer decision text must exactly match the reviewed StatementDraft")
    canonical_input = {
        "decision": "approved",
        "derivation_version": REVIEWER_APPROVAL_DERIVATION_VERSION,
        "quote_block_id": str(draft.quote_block_id),
        "reviewed_statement": decision.reviewed_statement,
        "reviewer_schema_version": REVIEWER_DECISION_SCHEMA_VERSION,
        "statement_draft_id": str(draft.statement_draft_id),
    }
    canonical_json = json.dumps(
        canonical_input,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"{REVIEWER_APPROVAL_DERIVATION_VERSION}_{digest}"


def build_statement_review_result(
    draft: StatementDraft,
    reviewer_input: ReviewerInput,
    decision: ReviewerDecision,
    *,
    reviewer_prompt_version: str,
    reviewer_model_name: str,
    reviewed_at: datetime,
) -> StatementReviewResult:
    _validate_aware_datetime(reviewed_at, "reviewed_at")
    validate_reviewer_decision(draft, reviewer_input, decision)
    reviewer_approval_id = (
        derive_reviewer_approval_id(draft, decision) if decision.approved else None
    )
    return StatementReviewResult(
        run_id=draft.run_id,
        statement_draft_id=draft.statement_draft_id,
        quote_block_id=draft.quote_block_id,
        approved=decision.approved,
        reviewer_approval_id=reviewer_approval_id,
        approved_factual_statement=(decision.reviewed_statement if decision.approved else None),
        failure_code=decision.failure_code,
        rationale=decision.rationale,
        reviewer_prompt_version=reviewer_prompt_version,
        reviewer_model_name=reviewer_model_name,
        reviewed_at=reviewed_at,
    )


def _first_failure_code(checks: ReviewChecks) -> ReviewerFailureCode | None:
    if not checks.fully_entailed:
        return ReviewerFailureCode.NOT_ENTAILED
    if not checks.qualifications_preserved:
        return ReviewerFailureCode.MISSING_QUALIFICATION
    if not checks.neutral_framing:
        return ReviewerFailureCode.BIASED_FRAMING
    if not checks.claim_fit_scope_valid:
        return ReviewerFailureCode.CLAIM_FIT_MISMATCH
    return None


def _failure_rationale(failure_code: ReviewerFailureCode) -> str:
    if failure_code is ReviewerFailureCode.NOT_ENTAILED:
        return "The draft is not fully entailed by the quotation and brackets."
    if failure_code is ReviewerFailureCode.MISSING_QUALIFICATION:
        return "The draft does not preserve material qualifications."
    if failure_code is ReviewerFailureCode.BIASED_FRAMING:
        return "The draft introduces biased framing, emphasis, or omission."
    return "The draft scope is inconsistent with the assigned Claim Fit score."


def _validate_aware_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value
