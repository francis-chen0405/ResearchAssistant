from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError as PydanticValidationError

from models import (
    CandidateQuoteBlock,
    Entailment,
    LedgerRecord,
    Placement,
    ScoreDecision,
    SectionType,
    SegmentOffset,
    SourceSnapshot,
    Stance,
    SynthesisItem,
    SynthesisSection,
    ValidationError,
    ValidationErrorCode,
    ValidationResult,
)

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
QUOTE_BLOCK_ID = UUID("00000000-0000-0000-0000-000000000002")
RETRIEVAL_ATTEMPT_ID = UUID("00000000-0000-0000-0000-000000000003")
QUERY_ID = UUID("00000000-0000-0000-0000-000000000004")
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000005")
LEDGER_CLAIM_ID = UUID("00000000-0000-0000-0000-000000000006")
REVIEWER_APPROVAL_ID = UUID("00000000-0000-0000-0000-000000000007")
STATEMENT_ID = UUID("00000000-0000-0000-0000-000000000008")
HASH = "a" * 64


def aware_now() -> datetime:
    return datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def naive_now() -> datetime:
    return datetime(2026, 6, 26, 12, 0)


def candidate_kwargs() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "stance": Stance.SUPPORTING,
        "quote_block_id": QUOTE_BLOCK_ID,
        "source_url": "https://example.test/source",
        "retrieval_attempt_id": RETRIEVAL_ATTEMPT_ID,
        "query_id": QUERY_ID,
        "query_round": 1,
        "search_rank": 1,
        "retrieved_at": aware_now(),
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_sha256": HASH,
        "snapshot_created_at": aware_now(),
        "extracted_quote_block": '[Before.] "Substantive quoted evidence." [After.]',
        "segment_offsets": [
            {"start_char": 10, "end_char": 40},
            {"start_char": 50, "end_char": 80},
        ],
        "raw_segment_word_count": 100,
        "has_statistical_markers": False,
        "claim_keyword_match_count": 1,
        "truncated": False,
        "extraction_prompt_version": "extract-v1",
        "extraction_model_name": "test-model",
        "extracted_at": aware_now(),
        "post_filter_version": "filter-v1",
        "post_filter_validated_at": aware_now(),
    }


def ledger_kwargs() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "ledger_claim_id": LEDGER_CLAIM_ID,
        "quote_block_id": QUOTE_BLOCK_ID,
        "stance": Stance.SUPPORTING,
        "approved_factual_statement": "The approved factual statement is exact.",
        "approved_claim_text": '[Before.] "Substantive quoted evidence." [After.]',
        "evidence_quality": 4,
        "claim_fit": 4,
        "placement": Placement.PRIMARY,
        "entailment": Entailment.STRONG,
        "source_url": "https://example.test/source",
        "retrieval_attempt_id": RETRIEVAL_ATTEMPT_ID,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_sha256": HASH,
        "segment_offsets": [{"start_char": 10, "end_char": 40}],
        "analyst_prompt_version": "analyst-v1",
        "analyst_model_name": "test-model",
        "analyst_completed_at": aware_now(),
        "reviewer_prompt_version": "reviewer-v1",
        "reviewer_model_name": "test-model",
        "reviewed_at": aware_now(),
        "reviewer_approval_id": REVIEWER_APPROVAL_ID,
        "ledger_validated_at": aware_now(),
    }


def test_valid_candidate_ledger_synthesis_and_validation_models_construct() -> None:
    candidate = CandidateQuoteBlock(**candidate_kwargs())
    ledger = LedgerRecord(**ledger_kwargs())

    item = SynthesisItem(
        connective_template_id="supporting-evidence",
        ledger_claim_id=ledger.ledger_claim_id,
        reviewer_approval_id=ledger.reviewer_approval_id,
        stance=ledger.stance,
        placement=ledger.placement,
        entailment=ledger.entailment,
        approved_factual_statement=ledger.approved_factual_statement,
    )
    section = SynthesisSection(
        section_type=SectionType.SUPPORTING,
        heading="Supporting evidence",
        items=[item],
    )
    validation = ValidationResult(
        run_id=RUN_ID,
        valid=True,
        errors=[],
        validator_config_version="validator-v1",
        validated_at=aware_now(),
        rendered_brief_hash=HASH,
    )

    assert candidate.quote_block_id == QUOTE_BLOCK_ID
    assert section.items[0].approved_factual_statement == ledger.approved_factual_statement
    assert validation.valid is True


@pytest.mark.parametrize(
    ("evidence_quality", "claim_fit"),
    [
        (0, 4),
        (6, 4),
        (4, 0),
        (4, 6),
    ],
)
def test_invalid_score_ranges_are_rejected(evidence_quality: int, claim_fit: int) -> None:
    with pytest.raises(PydanticValidationError):
        ScoreDecision(
            run_id=RUN_ID,
            quote_block_id=QUOTE_BLOCK_ID,
            evidence_quality=evidence_quality,
            claim_fit=claim_fit,
            placement=Placement.PRIMARY,
            approved=True,
            rationale="The score decision is documented.",
            analyst_prompt_version="analyst-v1",
            analyst_model_name="test-model",
            scored_at=aware_now(),
        )


def test_missing_reviewer_approval_is_rejected_for_ledger_records() -> None:
    kwargs = ledger_kwargs()
    del kwargs["reviewer_approval_id"]

    with pytest.raises(PydanticValidationError):
        LedgerRecord(**kwargs)


def test_invalid_placement_is_rejected() -> None:
    kwargs = ledger_kwargs()
    kwargs["placement"] = "headline"

    with pytest.raises(PydanticValidationError):
        LedgerRecord(**kwargs)


def test_invalid_entailment_is_rejected() -> None:
    kwargs = ledger_kwargs()
    kwargs["entailment"] = "Certain"

    with pytest.raises(PydanticValidationError):
        LedgerRecord(**kwargs)


def test_reversed_offsets_are_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        SegmentOffset(start_char=30, end_char=20)


def test_overlapping_offsets_are_rejected() -> None:
    kwargs = candidate_kwargs()
    kwargs["segment_offsets"] = [
        {"start_char": 10, "end_char": 40},
        {"start_char": 39, "end_char": 80},
    ]

    with pytest.raises(PydanticValidationError):
        CandidateQuoteBlock(**kwargs)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        SourceSnapshot(
            run_id=RUN_ID,
            retrieval_attempt_id=RETRIEVAL_ATTEMPT_ID,
            snapshot_id=SNAPSHOT_ID,
            source_url="https://example.test/source",
            retrieved_at=naive_now(),
            normalized_text="Snapshot text.",
            snapshot_sha256=HASH,
            word_count=2,
            truncated=False,
            created_at=aware_now(),
        )


def test_empty_approved_factual_statements_are_rejected() -> None:
    kwargs = ledger_kwargs()
    kwargs["approved_factual_statement"] = ""

    with pytest.raises(PydanticValidationError):
        LedgerRecord(**kwargs)


def test_invalid_synthesizer_section_types_are_rejected() -> None:
    item = SynthesisItem(
        connective_template_id="supporting-evidence",
        ledger_claim_id=LEDGER_CLAIM_ID,
        reviewer_approval_id=REVIEWER_APPROVAL_ID,
        stance=Stance.SUPPORTING,
        placement=Placement.PRIMARY,
        entailment=Entailment.STRONG,
        approved_factual_statement="The approved factual statement is exact.",
    )

    with pytest.raises(PydanticValidationError):
        SynthesisSection(section_type="background", heading="Background", items=[item])


def test_synthesizer_rejects_incompatible_stance_for_section() -> None:
    item = SynthesisItem(
        connective_template_id="opposing-evidence",
        ledger_claim_id=LEDGER_CLAIM_ID,
        reviewer_approval_id=REVIEWER_APPROVAL_ID,
        stance=Stance.OPPOSING,
        placement=Placement.PRIMARY,
        entailment=Entailment.STRONG,
        approved_factual_statement="The approved factual statement is exact.",
    )

    with pytest.raises(PydanticValidationError):
        SynthesisSection(section_type=SectionType.SUPPORTING, heading="Support", items=[item])


def test_malformed_validation_errors_are_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        ValidationError(
            code=ValidationErrorCode.SCHEMA_ERROR, location="", message="Missing field."
        )


def test_invalid_validation_results_require_errors() -> None:
    with pytest.raises(PydanticValidationError):
        ValidationResult(
            run_id=RUN_ID,
            valid=False,
            errors=[],
            validator_config_version="validator-v1",
            validated_at=aware_now(),
            rendered_brief_hash=None,
        )
