from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from agents.renderer import (
    OPPOSING_EVIDENCE_TEMPLATE_ID,
    PARTIAL_ENTAILMENT_TEMPLATE_ID,
    SCOPE_QUALIFICATION_TEMPLATE_ID,
    SUPPORTING_EVIDENCE_TEMPLATE_ID,
    WEAK_ENTAILMENT_TEMPLATE_ID,
)
from models import (
    Entailment,
    LedgerRecord,
    Placement,
    SectionType,
    Stance,
    StrictModel,
    SynthesisItem,
    SynthesisOutput,
    SynthesisSection,
)

DEFAULT_SYNTHESIZER_PROMPT_VERSION = "phase5-deterministic-synthesizer-v1"
DEFAULT_SYNTHESIZER_MODEL_NAME = "deterministic-fixture"

_PLACEMENT_ORDER = {
    Placement.PRIMARY: 0,
    Placement.SECONDARY: 1,
    Placement.SUPPORTING: 2,
    Placement.QUALIFIED_ONLY: 3,
}


class SynthesizerLLMInput(StrictModel):
    """Typed immutable-Ledger input for the structured Synthesizer call."""

    run_id: UUID
    ledger_records: tuple[LedgerRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ledger_runs(self) -> SynthesizerLLMInput:
        if any(record.run_id != self.run_id for record in self.ledger_records):
            raise ValueError("all Ledger records must match the synthesis run_id")
        return self


def build_synthesis_output(
    *,
    run_id: UUID,
    ledger_records: Sequence[LedgerRecord],
    created_at: datetime,
    synthesizer_prompt_version: str = DEFAULT_SYNTHESIZER_PROMPT_VERSION,
    synthesizer_model_name: str = DEFAULT_SYNTHESIZER_MODEL_NAME,
) -> SynthesisOutput:
    typed_records = [
        _require_ledger_record(record, f"ledger_records[{index}]")
        for index, record in enumerate(ledger_records)
    ]

    for record in typed_records:
        if record.run_id != run_id:
            raise ValueError("Ledger record run_id must match synthesis run_id")

    sections: list[SynthesisSection] = []
    supporting = _ordered_records(
        record
        for record in typed_records
        if record.stance is Stance.SUPPORTING and record.placement is not Placement.QUALIFIED_ONLY
    )
    opposing = _ordered_records(
        record
        for record in typed_records
        if record.stance is Stance.OPPOSING and record.placement is not Placement.QUALIFIED_ONLY
    )
    limitations = _ordered_records(
        record for record in typed_records if record.placement is Placement.QUALIFIED_ONLY
    )

    if supporting:
        sections.append(
            SynthesisSection(
                section_type=SectionType.SUPPORTING,
                items=[_item_from_ledger(record) for record in supporting],
            )
        )
    if opposing:
        sections.append(
            SynthesisSection(
                section_type=SectionType.OPPOSING,
                items=[_item_from_ledger(record) for record in opposing],
            )
        )
    if limitations:
        sections.append(
            SynthesisSection(
                section_type=SectionType.LIMITATIONS,
                items=[_item_from_ledger(record) for record in limitations],
            )
        )

    return SynthesisOutput(
        run_id=run_id,
        synthesizer_prompt_version=synthesizer_prompt_version,
        synthesizer_model_name=synthesizer_model_name,
        created_at=created_at,
        sections=sections,
    )


def _require_ledger_record(record: object, location: str) -> LedgerRecord:
    if not isinstance(record, LedgerRecord):
        raise TypeError(f"{location} must be a LedgerRecord instance")
    return record


def _ordered_records(records: Iterable[LedgerRecord]) -> list[LedgerRecord]:
    return sorted(
        records,
        key=lambda record: (
            _PLACEMENT_ORDER[record.placement],
            record.stance.value,
            str(record.ledger_claim_id),
        ),
    )


def _item_from_ledger(record: LedgerRecord) -> SynthesisItem:
    return SynthesisItem(
        connective_template_id=_template_for_record(record),
        ledger_claim_id=record.ledger_claim_id,
        reviewer_approval_id=record.reviewer_approval_id,
        stance=record.stance,
        placement=record.placement,
        entailment=record.entailment,
        approved_factual_statement=record.approved_factual_statement,
    )


def _template_for_record(record: LedgerRecord) -> str:
    if record.entailment is Entailment.PARTIAL:
        return PARTIAL_ENTAILMENT_TEMPLATE_ID
    if record.entailment is Entailment.WEAK:
        return WEAK_ENTAILMENT_TEMPLATE_ID
    if record.placement is Placement.QUALIFIED_ONLY:
        return SCOPE_QUALIFICATION_TEMPLATE_ID
    if record.stance is Stance.SUPPORTING:
        return SUPPORTING_EVIDENCE_TEMPLATE_ID
    return OPPOSING_EVIDENCE_TEMPLATE_ID
