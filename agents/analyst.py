from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from agents.researcher import verify_candidate_against_snapshot
from agents.supportingresearcher import UntrustedSourceText
from models import (
    ApprovedScore,
    CandidateQuoteBlock,
    ClaimDefinition,
    Entailment,
    LedgerRecord,
    Placement,
    Score,
    ScoreDecision,
    SourceSnapshot,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
)

QUALIFICATION_MARKERS = (
    "according to",
    "among",
    "associated",
    "could",
    "limited",
    "may",
    "narrower",
    "reported",
    "sample",
    "specific",
    "suggests",
    "surveyed",
    "under",
    "within",
)


class AnalystLLMInput(StrictModel):
    """Typed Analyst input with source text held behind the untrusted-data boundary."""

    run_id: UUID
    claim_definition: ClaimDefinition
    candidate: CandidateQuoteBlock
    source: UntrustedSourceText

    @model_validator(mode="after")
    def validate_provenance(self) -> AnalystLLMInput:
        if self.claim_definition.run_id != self.run_id or self.candidate.run_id != self.run_id:
            raise ValueError("Analyst input artifacts must share the run_id")
        if self.source.snapshot_id != self.candidate.snapshot_id:
            raise ValueError("Analyst source snapshot_id must match the candidate")
        if self.source.snapshot_sha256 != self.candidate.snapshot_sha256:
            raise ValueError("Analyst source hash must match the candidate")
        return self


def build_analyst_llm_input(
    *,
    claim_definition: ClaimDefinition,
    candidate: CandidateQuoteBlock,
    snapshot: SourceSnapshot,
) -> AnalystLLMInput:
    """Construct the semantic-analysis input without allowing raw source instructions."""
    if snapshot.run_id != candidate.run_id:
        raise ValueError("snapshot run_id must match the candidate")
    if snapshot.snapshot_id != candidate.snapshot_id:
        raise ValueError("snapshot_id must match the candidate")
    if snapshot.snapshot_sha256 != candidate.snapshot_sha256:
        raise ValueError("snapshot hash must match the candidate")
    verify_candidate_against_snapshot(snapshot, candidate)
    return AnalystLLMInput(
        run_id=candidate.run_id,
        claim_definition=claim_definition,
        candidate=candidate,
        source=UntrustedSourceText(
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.snapshot_sha256,
            text=snapshot.normalized_text,
        ),
    )


class ScorePairPolicy(StrictModel):
    evidence_quality: Score
    claim_fit: Score
    accepted: bool
    ledger_score: ApprovedScore | None = None
    placement: Placement | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_shape(self) -> ScorePairPolicy:
        if self.accepted:
            if self.ledger_score is None or self.placement is None:
                raise ValueError("accepted score pairs require Ledger score and placement")
        elif self.ledger_score is not None or self.placement is not None:
            raise ValueError("rejected score pairs cannot include Ledger fields")
        return self


SCORE_PAIR_TABLE: tuple[ScorePairPolicy, ...] = (
    ScorePairPolicy(
        evidence_quality=1,
        claim_fit=1,
        accepted=False,
        reason="Evidence Quality below 2 and Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=1,
        claim_fit=2,
        accepted=False,
        reason="Evidence Quality below 2 and Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=1,
        claim_fit=3,
        accepted=False,
        reason="Evidence Quality below 2.",
    ),
    ScorePairPolicy(
        evidence_quality=1,
        claim_fit=4,
        accepted=False,
        reason="Evidence Quality below 2.",
    ),
    ScorePairPolicy(
        evidence_quality=1,
        claim_fit=5,
        accepted=False,
        reason="Evidence Quality below 2.",
    ),
    ScorePairPolicy(
        evidence_quality=2,
        claim_fit=1,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=2,
        claim_fit=2,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=2,
        claim_fit=3,
        accepted=True,
        ledger_score=3,
        placement=Placement.QUALIFIED_ONLY,
        reason="Minimum eligible score pair; Claim Fit 3 requires qualified-only use.",
    ),
    ScorePairPolicy(
        evidence_quality=2,
        claim_fit=4,
        accepted=True,
        ledger_score=3,
        placement=Placement.SUPPORTING,
        reason="Eligible low-strength supporting evidence.",
    ),
    ScorePairPolicy(
        evidence_quality=2,
        claim_fit=5,
        accepted=True,
        ledger_score=4,
        placement=Placement.SECONDARY,
        reason="Eligible evidence with exact claim fit but limited evidence quality.",
    ),
    ScorePairPolicy(
        evidence_quality=3,
        claim_fit=1,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=3,
        claim_fit=2,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=3,
        claim_fit=3,
        accepted=True,
        ledger_score=3,
        placement=Placement.QUALIFIED_ONLY,
        reason="Related or narrower evidence must remain qualified-only.",
    ),
    ScorePairPolicy(
        evidence_quality=3,
        claim_fit=4,
        accepted=True,
        ledger_score=4,
        placement=Placement.SECONDARY,
        reason="Eligible secondary evidence.",
    ),
    ScorePairPolicy(
        evidence_quality=3,
        claim_fit=5,
        accepted=True,
        ledger_score=4,
        placement=Placement.SECONDARY,
        reason="Eligible secondary evidence.",
    ),
    ScorePairPolicy(
        evidence_quality=4,
        claim_fit=1,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=4,
        claim_fit=2,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=4,
        claim_fit=3,
        accepted=True,
        ledger_score=4,
        placement=Placement.QUALIFIED_ONLY,
        reason="Strong evidence for a narrower claim must remain qualified-only.",
    ),
    ScorePairPolicy(
        evidence_quality=4,
        claim_fit=4,
        accepted=True,
        ledger_score=4,
        placement=Placement.SECONDARY,
        reason="Eligible secondary evidence.",
    ),
    ScorePairPolicy(
        evidence_quality=4,
        claim_fit=5,
        accepted=True,
        ledger_score=5,
        placement=Placement.PRIMARY,
        reason="High-quality evidence with exact claim fit.",
    ),
    ScorePairPolicy(
        evidence_quality=5,
        claim_fit=1,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=5,
        claim_fit=2,
        accepted=False,
        reason="Claim Fit below 3.",
    ),
    ScorePairPolicy(
        evidence_quality=5,
        claim_fit=3,
        accepted=True,
        ledger_score=4,
        placement=Placement.QUALIFIED_ONLY,
        reason="Excellent evidence for a related claim must remain qualified-only.",
    ),
    ScorePairPolicy(
        evidence_quality=5,
        claim_fit=4,
        accepted=True,
        ledger_score=5,
        placement=Placement.PRIMARY,
        reason="Primary evidence with minor claim-fit gaps.",
    ),
    ScorePairPolicy(
        evidence_quality=5,
        claim_fit=5,
        accepted=True,
        ledger_score=5,
        placement=Placement.PRIMARY,
        reason="Primary evidence with exact claim fit.",
    ),
)

_SCORE_PAIR_LOOKUP = {
    (policy.evidence_quality, policy.claim_fit): policy for policy in SCORE_PAIR_TABLE
}


class LedgerAdmissionRequest(StrictModel):
    candidate: CandidateQuoteBlock
    snapshot: SourceSnapshot
    score_decision: ScoreDecision
    statement_drafts: list[StatementDraft] = Field(min_length=1)
    review_results: list[StatementReviewResult] = Field(min_length=1)
    approved_factual_statement: str = Field(min_length=1)
    entailment: Entailment
    placement: Placement | None = None


class ValidatedLedgerPayload(StrictModel):
    """ID-free Ledger content produced only after deterministic admission succeeds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: CandidateQuoteBlock
    score_decision: ScoreDecision
    approved_review: StatementReviewResult
    approved_factual_statement: str = Field(min_length=1)
    entailment: Entailment


LedgerClaimIdDeriver = Callable[[ValidatedLedgerPayload], UUID]


def interpret_score_pair(evidence_quality: int, claim_fit: int) -> ScorePairPolicy:
    _validate_score_value(evidence_quality, "evidence_quality")
    _validate_score_value(claim_fit, "claim_fit")
    return _SCORE_PAIR_LOOKUP[(evidence_quality, claim_fit)]


def score_candidate(
    *,
    run_id: UUID,
    quote_block_id: UUID,
    evidence_quality: int,
    claim_fit: int,
    rationale: str,
    analyst_prompt_version: str,
    analyst_model_name: str,
    scored_at: datetime,
) -> ScoreDecision:
    policy = interpret_score_pair(evidence_quality, claim_fit)
    return ScoreDecision(
        run_id=run_id,
        quote_block_id=quote_block_id,
        evidence_quality=evidence_quality,
        claim_fit=claim_fit,
        ledger_score=policy.ledger_score,
        placement=policy.placement,
        approved=policy.accepted,
        rationale=rationale,
        analyst_prompt_version=analyst_prompt_version,
        analyst_model_name=analyst_model_name,
        scored_at=scored_at,
    )


def create_statement_draft(
    *,
    candidate: CandidateQuoteBlock,
    score_decision: ScoreDecision,
    statement_draft_id: UUID,
    draft_statement: str,
    drafted_at: datetime,
) -> StatementDraft:
    _validate_candidate_score_decision(candidate, score_decision)
    if not score_decision.approved:
        raise ValueError("rejected Analyst decisions cannot produce Ledger-bound drafts")
    return StatementDraft(
        run_id=candidate.run_id,
        statement_draft_id=statement_draft_id,
        quote_block_id=candidate.quote_block_id,
        stance=candidate.stance,
        draft_statement=draft_statement,
        claim_fit=score_decision.claim_fit,
        analyst_prompt_version=score_decision.analyst_prompt_version,
        analyst_model_name=score_decision.analyst_model_name,
        drafted_at=drafted_at,
    )


def validate_ledger_admission(request: LedgerAdmissionRequest) -> ValidatedLedgerPayload:
    verify_candidate_against_snapshot(request.snapshot, request.candidate)
    _validate_candidate_score_decision(request.candidate, request.score_decision)

    if not request.score_decision.approved:
        raise ValueError("rejected Analyst decisions cannot enter the Ledger")
    if request.score_decision.ledger_score is None or request.score_decision.placement is None:
        raise ValueError("approved Analyst decisions require Ledger score and placement")
    if request.placement is not None and request.placement is not request.score_decision.placement:
        raise ValueError("unauthorized placement changes are not allowed")

    final_draft, approved_review = _resolve_approved_review(
        request.candidate,
        request.statement_drafts,
        request.review_results,
    )
    if approved_review.approved_factual_statement != request.approved_factual_statement:
        raise ValueError("only the exact Reviewer-approved statement may enter the Ledger")
    if final_draft.draft_statement != request.approved_factual_statement:
        raise ValueError("approved Ledger statement must match the reviewed draft exactly")

    _validate_entailment_and_qualification(
        request.approved_factual_statement,
        request.score_decision.claim_fit,
        request.score_decision.placement,
        request.entailment,
    )

    return ValidatedLedgerPayload(
        candidate=request.candidate,
        score_decision=request.score_decision,
        approved_review=approved_review,
        approved_factual_statement=request.approved_factual_statement,
        entailment=request.entailment,
    )


def admit_ledger_record(
    request: LedgerAdmissionRequest,
    *,
    derive_ledger_claim_id: LedgerClaimIdDeriver,
    validation_clock: Callable[[], datetime],
) -> LedgerRecord:
    payload = validate_ledger_admission(request)
    ledger_validated_at = _validate_aware_datetime(
        validation_clock(),
        "ledger_validated_at",
    )
    ledger_claim_id = derive_ledger_claim_id(payload)
    candidate = payload.candidate
    score_decision = payload.score_decision
    approved_review = payload.approved_review

    return LedgerRecord(
        run_id=candidate.run_id,
        ledger_claim_id=ledger_claim_id,
        quote_block_id=candidate.quote_block_id,
        stance=candidate.stance,
        approved_factual_statement=payload.approved_factual_statement,
        approved_claim_text=candidate.extracted_quote_block,
        evidence_quality=score_decision.evidence_quality,
        claim_fit=score_decision.claim_fit,
        ledger_score=score_decision.ledger_score,
        placement=score_decision.placement,
        entailment=payload.entailment,
        source_url=candidate.source_url,
        retrieval_attempt_id=candidate.retrieval_attempt_id,
        snapshot_id=candidate.snapshot_id,
        snapshot_sha256=candidate.snapshot_sha256,
        segment_offsets=candidate.segment_offsets,
        analyst_prompt_version=score_decision.analyst_prompt_version,
        analyst_model_name=score_decision.analyst_model_name,
        analyst_completed_at=score_decision.scored_at,
        reviewer_prompt_version=approved_review.reviewer_prompt_version,
        reviewer_model_name=approved_review.reviewer_model_name,
        reviewed_at=approved_review.reviewed_at,
        reviewer_approval_id=approved_review.reviewer_approval_id,
        ledger_validated_at=ledger_validated_at,
    )


def statement_has_required_qualification(statement: str) -> bool:
    lowered = statement.casefold()
    return any(_marker_matches(lowered, marker) for marker in QUALIFICATION_MARKERS)


def _validate_score_value(value: int, field_name: str) -> None:
    if value < 1 or value > 5:
        raise ValueError(f"{field_name} must be 1 through 5")


def _validate_candidate_score_decision(
    candidate: CandidateQuoteBlock,
    score_decision: ScoreDecision,
) -> None:
    if score_decision.run_id != candidate.run_id:
        raise ValueError("Analyst decision run_id must match candidate run_id")
    if score_decision.quote_block_id != candidate.quote_block_id:
        raise ValueError("Analyst decision quote_block_id must match candidate")

    policy = interpret_score_pair(score_decision.evidence_quality, score_decision.claim_fit)
    if score_decision.approved is not policy.accepted:
        raise ValueError("Analyst decision approval does not match score-pair policy")
    if score_decision.ledger_score != policy.ledger_score:
        raise ValueError("Analyst decision Ledger score does not match score-pair policy")
    if score_decision.placement is not policy.placement:
        raise ValueError("Analyst decision placement does not match score-pair policy")


def _resolve_approved_review(
    candidate: CandidateQuoteBlock,
    drafts: Sequence[StatementDraft],
    reviews: Sequence[StatementReviewResult],
) -> tuple[StatementDraft, StatementReviewResult]:
    if len(drafts) != len(reviews):
        raise ValueError("each Ledger-bound draft requires exactly one Reviewer result")
    if len(reviews) > 2:
        raise ValueError("one revision maximum allows at most two Reviewer attempts")

    drafts_by_id: dict[UUID, StatementDraft] = {}
    for draft in drafts:
        _validate_draft_matches_candidate(candidate, draft)
        if draft.statement_draft_id in drafts_by_id:
            raise ValueError("duplicate statement draft IDs are not allowed")
        drafts_by_id[draft.statement_draft_id] = draft

    for review in reviews:
        _validate_review_shape(review)
        if review.run_id != candidate.run_id:
            raise ValueError("Reviewer result run_id must match candidate run_id")
        if review.quote_block_id != candidate.quote_block_id:
            raise ValueError("Reviewer result quote_block_id must match candidate")
        draft = drafts_by_id.get(review.statement_draft_id)
        if draft is None:
            raise ValueError("Reviewer result must reference a provided draft")
        if review.approved and review.approved_factual_statement != draft.draft_statement:
            raise ValueError("Reviewer approval must preserve the draft statement exactly")

    if len(reviews) == 2 and reviews[0].approved:
        raise ValueError("a revision is allowed only after the first Reviewer rejection")

    final_review = reviews[-1]
    if not final_review.approved:
        if len(reviews) == 2:
            raise ValueError("second Reviewer failure rejects the quote block")
        raise ValueError("Reviewer-rejected statements cannot enter the Ledger")

    final_draft = drafts_by_id[final_review.statement_draft_id]
    return final_draft, final_review


def _validate_draft_matches_candidate(
    candidate: CandidateQuoteBlock,
    draft: StatementDraft,
) -> None:
    if draft.run_id != candidate.run_id:
        raise ValueError("statement draft run_id must match candidate run_id")
    if draft.quote_block_id != candidate.quote_block_id:
        raise ValueError("statement draft quote_block_id must match candidate")
    if draft.stance is not candidate.stance:
        raise ValueError("statement draft stance must match candidate stance")


def _validate_review_shape(review: StatementReviewResult) -> None:
    if review.approved:
        if review.reviewer_approval_id is None:
            raise ValueError("Reviewer-approved statements require reviewer_approval_id")
        if review.approved_factual_statement is None:
            raise ValueError("Reviewer-approved statements require approved text")
        if review.failure_code is not None:
            raise ValueError("Reviewer-approved statements cannot include failure codes")
    else:
        if review.failure_code is None:
            raise ValueError("Reviewer rejections require a failure code")
        if review.reviewer_approval_id is not None:
            raise ValueError("Reviewer rejections cannot include reviewer_approval_id")
        if review.approved_factual_statement is not None:
            raise ValueError("Reviewer rejections cannot include approved text")


def _validate_entailment_and_qualification(
    statement: str,
    claim_fit: int,
    placement: Placement,
    entailment: Entailment,
) -> None:
    qualification_required = (
        claim_fit == 3
        or placement is Placement.QUALIFIED_ONLY
        or entailment in {Entailment.PARTIAL, Entailment.WEAK}
    )
    if qualification_required and not statement_has_required_qualification(statement):
        raise ValueError(
            "Claim Fit 3, qualified-only, Partial, and Weak statements require "
            "an explicit qualification"
        )


def _marker_matches(lowered_statement: str, marker: str) -> bool:
    pattern = rf"(?<!\w){re.escape(marker.casefold())}(?!\w)"
    return re.search(pattern, lowered_statement) is not None


def _validate_aware_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value
