from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from agents.renderer import (
    APPROVED_CONNECTIVE_TEMPLATES,
    PARTIAL_ENTAILMENT_TEMPLATE_ID,
    SUPPORTING_EVIDENCE_TEMPLATE_ID,
    VALIDATOR_CONFIG_VERSION,
    render_brief,
    validate_final_release,
)
from agents.synthesizer import build_synthesis_output
from models import (
    Entailment,
    LedgerRecord,
    Placement,
    SectionType,
    SegmentOffset,
    Stance,
    SynthesisItem,
    SynthesisOutput,
    SynthesisSection,
    ValidationErrorCode,
)

_NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
_RUN_ID = UUID("50000000-0000-0000-0000-000000000001")
_CLAIM = "Fixture claim framing without factual findings."
_EXPECTED_BRIEF = Path(__file__).parent / "fixtures" / "phase5_expected_valid_brief.txt"


def _uuid(value: int) -> UUID:
    return UUID(f"50000000-0000-0000-0000-{value:012d}")


def _score_and_placement(evidence_quality: int, claim_fit: int) -> tuple[int, Placement]:
    total = evidence_quality + claim_fit
    if claim_fit == 3:
        return (3 if total <= 6 else 4, Placement.QUALIFIED_ONLY)
    if total <= 6:
        return 3, Placement.SUPPORTING
    if total <= 8:
        return 4, Placement.SECONDARY
    return 5, Placement.PRIMARY


def _ledger(
    value: int,
    *,
    stance: Stance,
    statement: str,
    evidence_quality: int,
    claim_fit: int,
    entailment: Entailment = Entailment.STRONG,
) -> LedgerRecord:
    ledger_score, placement = _score_and_placement(evidence_quality, claim_fit)
    return LedgerRecord(
        run_id=_RUN_ID,
        ledger_claim_id=_uuid(100 + value),
        quote_block_id=_uuid(200 + value),
        stance=stance,
        approved_factual_statement=statement,
        approved_claim_text=f'[Before.] "{statement}" [After.]',
        evidence_quality=evidence_quality,
        claim_fit=claim_fit,
        ledger_score=ledger_score,
        placement=placement,
        entailment=entailment,
        source_url=f"https://example.test/source-{value}",
        retrieval_attempt_id=_uuid(300 + value),
        snapshot_id=_uuid(400 + value),
        snapshot_sha256=f"{value:064x}",
        segment_offsets=[SegmentOffset(start_char=0, end_char=10)],
        analyst_prompt_version="analyst-v1",
        analyst_model_name="fixture-model",
        analyst_completed_at=_NOW,
        reviewer_prompt_version="reviewer-v1",
        reviewer_model_name="fixture-model",
        reviewed_at=_NOW,
        reviewer_approval_id=_uuid(500 + value),
        ledger_validated_at=_NOW,
    )


def _valid_ledgers() -> list[LedgerRecord]:
    return [
        _ledger(
            1,
            stance=Stance.SUPPORTING,
            statement="The audit reported a 12% decrease in processing time.",
            evidence_quality=5,
            claim_fit=5,
        ),
        _ledger(
            2,
            stance=Stance.OPPOSING,
            statement="The evaluation reported higher administrative costs in the first year.",
            evidence_quality=4,
            claim_fit=4,
        ),
        _ledger(
            3,
            stance=Stance.SUPPORTING,
            statement="Among surveyed schools, the pilot reported a 9% gain.",
            evidence_quality=3,
            claim_fit=3,
        ),
    ]


def _partial_ledger(entailment: Entailment = Entailment.PARTIAL) -> LedgerRecord:
    return _ledger(
        4,
        stance=Stance.SUPPORTING,
        statement="Among surveyed families, the source reported limited program support.",
        evidence_quality=4,
        claim_fit=4,
        entailment=entailment,
    )


def _synthesis(ledgers: list[LedgerRecord]) -> SynthesisOutput:
    return build_synthesis_output(
        run_id=_RUN_ID,
        ledger_records=ledgers,
        created_at=_NOW,
    )


def _replace_item(
    synthesis: SynthesisOutput,
    section_index: int,
    item_index: int,
    item: SynthesisItem,
) -> SynthesisOutput:
    sections = list(synthesis.sections)
    items = list(sections[section_index].items)
    items[item_index] = item
    sections[section_index] = sections[section_index].model_copy(update={"items": items})
    return synthesis.model_copy(update={"sections": sections})


def _append_item(
    synthesis: SynthesisOutput,
    section_index: int,
    item: SynthesisItem,
) -> SynthesisOutput:
    sections = list(synthesis.sections)
    items = [*sections[section_index].items, item]
    sections[section_index] = sections[section_index].model_copy(update={"items": items})
    return synthesis.model_copy(update={"sections": sections})


def _assert_invalid(
    synthesis: SynthesisOutput,
    ledgers: list[LedgerRecord],
    code: ValidationErrorCode,
) -> None:
    result = validate_final_release(
        synthesis,
        ledgers,
        authoritative_claim=_CLAIM,
        validated_at=_NOW,
    )
    assert result.valid is False
    assert result.rendered_brief_hash is None
    assert any(error.code is code for error in result.errors)


def test_synthesizer_rejects_raw_dictionary_ledger_handoff() -> None:
    ledger_payload = _valid_ledgers()[0].model_dump(mode="python")

    with pytest.raises(TypeError, match="LedgerRecord"):
        build_synthesis_output(
            run_id=_RUN_ID,
            ledger_records=[ledger_payload],
            created_at=_NOW,
        )


def test_final_validator_rejects_raw_dictionary_ledger_handoff() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    ledger_payload = ledgers[0].model_dump(mode="python")

    result = validate_final_release(
        synthesis,
        [ledger_payload, *ledgers[1:]],
        authoritative_claim=_CLAIM,
        validated_at=_NOW,
    )

    assert result.valid is False
    assert result.rendered_brief_hash is None
    assert any(error.code is ValidationErrorCode.SCHEMA_ERROR for error in result.errors)


def test_empty_approved_ledger_statement_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    empty_statement_ledger = ledgers[0].model_copy(update={"approved_factual_statement": ""})

    result = validate_final_release(
        synthesis,
        [empty_statement_ledger, *ledgers[1:]],
        authoritative_claim=_CLAIM,
        validated_at=_NOW,
    )

    assert result.valid is False
    assert result.rendered_brief_hash is None
    assert any(error.code is ValidationErrorCode.SCHEMA_ERROR for error in result.errors)


def test_change_one_word_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(
        update={
            "approved_factual_statement": item.approved_factual_statement.replace(
                "decrease", "increase"
            )
        }
    )

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.ALTERED_STATEMENT,
    )


def test_change_punctuation_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(
        update={"approved_factual_statement": item.approved_factual_statement[:-1] + "!"}
    )

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.ALTERED_STATEMENT,
    )


def test_change_capitalization_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(
        update={"approved_factual_statement": item.approved_factual_statement.lower()}
    )

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.ALTERED_STATEMENT,
    )


def test_correct_id_with_wrong_statement_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    wrong_statement = ledgers[1].approved_factual_statement
    mutated = item.model_copy(update={"approved_factual_statement": wrong_statement})

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.ALTERED_STATEMENT,
    )


def test_correct_statement_with_wrong_id_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    wrong_ledger = ledgers[1]
    mutated = item.model_copy(
        update={
            "ledger_claim_id": wrong_ledger.ledger_claim_id,
            "reviewer_approval_id": wrong_ledger.reviewer_approval_id,
        }
    )

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.ALTERED_STATEMENT,
    )


@pytest.mark.parametrize("reviewer_approval_id", [None, _uuid(999)])
def test_missing_or_changed_reviewer_approval_id_blocks_release(
    reviewer_approval_id: UUID | None,
) -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(update={"reviewer_approval_id": reviewer_approval_id})

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.LEDGER_MISMATCH,
    )


def test_change_placement_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(update={"placement": Placement.SECONDARY})

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.LEDGER_MISMATCH,
    )


def test_change_stance_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(update={"stance": Stance.OPPOSING})

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.LEDGER_MISMATCH,
    )


def test_promote_qualified_only_evidence_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[2].items[0]
    promoted = item.model_copy(
        update={
            "placement": Placement.PRIMARY,
            "connective_template_id": SUPPORTING_EVIDENCE_TEMPLATE_ID,
        }
    )

    _assert_invalid(
        _replace_item(synthesis, 2, 0, promoted),
        ledgers,
        ValidationErrorCode.LEDGER_MISMATCH,
    )


@pytest.mark.parametrize(
    ("section_type", "item_index"),
    [(SectionType.SUPPORTING, 1), (SectionType.OPPOSING, 0)],
)
def test_opposing_and_supporting_items_cannot_cross_sections(
    section_type: SectionType,
    item_index: int,
) -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[item_index].items[0]
    bad_section = SynthesisSection.model_construct(
        section_type=section_type,
        items=[item],
    )
    mutated = synthesis.model_copy(update={"sections": [bad_section]})

    _assert_invalid(mutated, ledgers, ValidationErrorCode.INVALID_SECTION)


def test_unknown_template_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(update={"connective_template_id": "unapproved_template"})

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.INVALID_TEMPLATE,
    )


def test_hidden_prose_in_extra_field_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0].model_copy()
    object.__setattr__(item, "hidden_prose", "This proves a fact outside the Ledger.")

    _assert_invalid(
        _replace_item(synthesis, 0, 0, item),
        ledgers,
        ValidationErrorCode.SCHEMA_ERROR,
    )


def test_free_form_factual_transition_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(update={"connective_template_id": "This proves the claim because:"})

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        ValidationErrorCode.INVALID_TEMPLATE,
    )


@pytest.mark.parametrize(
    ("entailment", "required_template"),
    [
        (Entailment.PARTIAL, PARTIAL_ENTAILMENT_TEMPLATE_ID),
        (Entailment.WEAK, "weak_entailment"),
    ],
)
def test_omit_partial_or_weak_entailment_warning_blocks_release(
    entailment: Entailment,
    required_template: str,
) -> None:
    ledger = _partial_ledger(entailment)
    synthesis = _synthesis([ledger])
    assert synthesis.sections[0].items[0].connective_template_id == required_template
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(update={"connective_template_id": SUPPORTING_EVIDENCE_TEMPLATE_ID})

    _assert_invalid(
        _replace_item(synthesis, 0, 0, mutated),
        [ledger],
        ValidationErrorCode.INVALID_TEMPLATE,
    )


def test_reuse_one_ledger_claim_too_many_times_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    duplicated = _append_item(synthesis, 0, synthesis.sections[0].items[0])

    _assert_invalid(duplicated, ledgers, ValidationErrorCode.LEDGER_MISMATCH)


def test_render_statement_not_in_ledger_blocks_release() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    rogue = SynthesisItem(
        connective_template_id=SUPPORTING_EVIDENCE_TEMPLATE_ID,
        ledger_claim_id=_uuid(777),
        reviewer_approval_id=_uuid(778),
        stance=Stance.SUPPORTING,
        placement=Placement.PRIMARY,
        entailment=Entailment.STRONG,
        approved_factual_statement="This statement is not in the Ledger.",
    )
    mutated = _append_item(synthesis, 0, rogue)

    _assert_invalid(mutated, ledgers, ValidationErrorCode.LEDGER_MISMATCH)


def test_valid_output_produces_stable_hash() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    rendered = render_brief(synthesis, ledgers, authoritative_claim=_CLAIM)
    expected = _EXPECTED_BRIEF.read_text(encoding="utf-8")

    result = validate_final_release(
        synthesis,
        ledgers,
        authoritative_claim=_CLAIM,
        validated_at=_NOW,
    )

    assert rendered == expected
    assert result.valid is True
    assert result.errors == []
    assert result.validator_config_version == VALIDATOR_CONFIG_VERSION
    assert result.rendered_brief_hash == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert result.rendered_brief_hash == (
        "7895588120c041b61196d3c36326de35c6de5a8d5bafdd6f6269e6c381677240"
    )
    assert set(APPROVED_CONNECTIVE_TEMPLATES) == {
        "supporting_evidence",
        "opposing_evidence",
        "limitation",
        "partial_entailment",
        "weak_entailment",
        "scope_qualification",
        "reliability_qualification",
    }


def test_invalid_output_returns_invalid_result_with_no_hash() -> None:
    ledgers = _valid_ledgers()
    synthesis = _synthesis(ledgers)
    item = synthesis.sections[0].items[0]
    mutated = item.model_copy(update={"approved_factual_statement": "Not approved."})

    result = validate_final_release(
        _replace_item(synthesis, 0, 0, mutated),
        ledgers,
        authoritative_claim=_CLAIM,
        validated_at=_NOW,
    )

    assert result.valid is False
    assert result.rendered_brief_hash is None
    assert result.errors
