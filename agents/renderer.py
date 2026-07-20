from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from pydantic import Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from models import (
    BRIEF_TITLE,
    CLAIM_LABEL,
    RELEASE_SECTION_HEADINGS,
    RELEASE_SECTION_ORDER,
    Entailment,
    LedgerRecord,
    Placement,
    SectionType,
    Stance,
    StrictModel,
    SynthesisItem,
    SynthesisOutput,
    SynthesisSection,
    ValidationError,
    ValidationErrorCode,
    ValidationResult,
)

VALIDATOR_CONFIG_VERSION = "mvp1-release-validator-v1"
MAX_LEDGER_CLAIM_USES = 1

SUPPORTING_EVIDENCE_TEMPLATE_ID = "supporting_evidence"
OPPOSING_EVIDENCE_TEMPLATE_ID = "opposing_evidence"
LIMITATION_TEMPLATE_ID = "limitation"
PARTIAL_ENTAILMENT_TEMPLATE_ID = "partial_entailment"
WEAK_ENTAILMENT_TEMPLATE_ID = "weak_entailment"
SCOPE_QUALIFICATION_TEMPLATE_ID = "scope_qualification"
RELIABILITY_QUALIFICATION_TEMPLATE_ID = "reliability_qualification"

_EnumT = TypeVar("_EnumT", bound=StrEnum)


class ApprovedConnectiveTemplate(StrictModel):
    template_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    allowed_stances: tuple[Stance, ...]
    allowed_sections: tuple[SectionType, ...]
    qualifies_limited_evidence: bool = False
    entailment_warning: Entailment | None = None

    @field_validator("allowed_stances", "allowed_sections")
    @classmethod
    def validate_non_empty_tuple(
        cls,
        value: tuple[Stance, ...] | tuple[SectionType, ...],
    ) -> tuple[Stance, ...] | tuple[SectionType, ...]:
        if not value:
            raise ValueError("template compatibility lists cannot be empty")
        return value


APPROVED_CONNECTIVE_TEMPLATES: Mapping[str, ApprovedConnectiveTemplate] = {
    SUPPORTING_EVIDENCE_TEMPLATE_ID: ApprovedConnectiveTemplate(
        template_id=SUPPORTING_EVIDENCE_TEMPLATE_ID,
        text="Supporting evidence:",
        allowed_stances=(Stance.SUPPORTING,),
        allowed_sections=(SectionType.SUPPORTING,),
    ),
    OPPOSING_EVIDENCE_TEMPLATE_ID: ApprovedConnectiveTemplate(
        template_id=OPPOSING_EVIDENCE_TEMPLATE_ID,
        text="Opposing evidence:",
        allowed_stances=(Stance.OPPOSING,),
        allowed_sections=(SectionType.OPPOSING,),
    ),
    LIMITATION_TEMPLATE_ID: ApprovedConnectiveTemplate(
        template_id=LIMITATION_TEMPLATE_ID,
        text="A limitation is:",
        allowed_stances=(Stance.SUPPORTING, Stance.OPPOSING),
        allowed_sections=(SectionType.LIMITATIONS,),
    ),
    PARTIAL_ENTAILMENT_TEMPLATE_ID: ApprovedConnectiveTemplate(
        template_id=PARTIAL_ENTAILMENT_TEMPLATE_ID,
        text="The source provides partial support:",
        allowed_stances=(Stance.SUPPORTING, Stance.OPPOSING),
        allowed_sections=(SectionType.SUPPORTING, SectionType.OPPOSING, SectionType.LIMITATIONS),
        qualifies_limited_evidence=True,
        entailment_warning=Entailment.PARTIAL,
    ),
    WEAK_ENTAILMENT_TEMPLATE_ID: ApprovedConnectiveTemplate(
        template_id=WEAK_ENTAILMENT_TEMPLATE_ID,
        text="The source provides weak support:",
        allowed_stances=(Stance.SUPPORTING, Stance.OPPOSING),
        allowed_sections=(SectionType.SUPPORTING, SectionType.OPPOSING, SectionType.LIMITATIONS),
        qualifies_limited_evidence=True,
        entailment_warning=Entailment.WEAK,
    ),
    SCOPE_QUALIFICATION_TEMPLATE_ID: ApprovedConnectiveTemplate(
        template_id=SCOPE_QUALIFICATION_TEMPLATE_ID,
        text="This source addresses a narrower version of the claim:",
        allowed_stances=(Stance.SUPPORTING, Stance.OPPOSING),
        allowed_sections=(SectionType.SUPPORTING, SectionType.OPPOSING, SectionType.LIMITATIONS),
        qualifies_limited_evidence=True,
    ),
    RELIABILITY_QUALIFICATION_TEMPLATE_ID: ApprovedConnectiveTemplate(
        template_id=RELIABILITY_QUALIFICATION_TEMPLATE_ID,
        text="This source's reliability is limited:",
        allowed_stances=(Stance.SUPPORTING, Stance.OPPOSING),
        allowed_sections=(SectionType.SUPPORTING, SectionType.OPPOSING, SectionType.LIMITATIONS),
        qualifies_limited_evidence=True,
    ),
}


def validate_final_release(
    synthesis: SynthesisOutput,
    ledger_records: Sequence[LedgerRecord],
    *,
    authoritative_claim: str,
    validated_at: datetime,
    validator_config_version: str = VALIDATOR_CONFIG_VERSION,
    max_ledger_claim_uses: int = MAX_LEDGER_CLAIM_USES,
) -> ValidationResult:
    framing_errors = _authoritative_claim_errors(authoritative_claim)
    ledger_lookup, ledger_errors = _ledger_lookup(synthesis, ledger_records)
    errors = [
        *framing_errors,
        *_schema_errors_from_revalidation(synthesis),
        *_hidden_field_errors(synthesis),
        *ledger_errors,
        *_section_structure_errors(synthesis),
        *_content_errors(synthesis, ledger_lookup, max_ledger_claim_uses),
    ]

    if errors:
        return ValidationResult(
            run_id=synthesis.run_id,
            valid=False,
            errors=errors,
            validator_config_version=validator_config_version,
            validated_at=validated_at,
            rendered_brief_hash=None,
        )

    rendered = _render_validated_brief(synthesis, ledger_lookup, authoritative_claim)
    return ValidationResult(
        run_id=synthesis.run_id,
        valid=True,
        errors=[],
        validator_config_version=validator_config_version,
        validated_at=validated_at,
        rendered_brief_hash=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    )


def render_brief(
    synthesis: SynthesisOutput,
    ledger_records: Sequence[LedgerRecord],
    *,
    authoritative_claim: str,
    max_ledger_claim_uses: int = MAX_LEDGER_CLAIM_USES,
) -> str:
    framing_errors = _authoritative_claim_errors(authoritative_claim)
    ledger_lookup, ledger_errors = _ledger_lookup(synthesis, ledger_records)
    errors = [
        *framing_errors,
        *_schema_errors_from_revalidation(synthesis),
        *_hidden_field_errors(synthesis),
        *ledger_errors,
        *_section_structure_errors(synthesis),
        *_content_errors(synthesis, ledger_lookup, max_ledger_claim_uses),
    ]
    if errors:
        raise ValueError("invalid SynthesisOutput cannot be rendered")
    return _render_validated_brief(synthesis, ledger_lookup, authoritative_claim)


def _authoritative_claim_errors(authoritative_claim: str) -> list[ValidationError]:
    if not isinstance(authoritative_claim, str) or authoritative_claim == "":
        return [
            _error(
                ValidationErrorCode.SCHEMA_ERROR,
                "authoritative_claim",
                "Final validation requires the exact non-empty submitted claim.",
            )
        ]
    return []


def _ledger_lookup(
    synthesis: SynthesisOutput,
    ledger_records: Sequence[LedgerRecord],
) -> tuple[dict[object, LedgerRecord], list[ValidationError]]:
    errors: list[ValidationError] = []
    lookup: dict[object, LedgerRecord] = {}
    for index, record in enumerate(ledger_records):
        if not isinstance(record, LedgerRecord):
            errors.append(
                _error(
                    ValidationErrorCode.SCHEMA_ERROR,
                    f"ledger_records[{index}]",
                    "Final validation requires LedgerRecord instances.",
                )
            )
            continue
        schema_errors = _ledger_schema_errors(record, index)
        errors.extend(schema_errors)
        if schema_errors:
            continue
        if record.run_id != synthesis.run_id:
            errors.append(
                _error(
                    ValidationErrorCode.LEDGER_MISMATCH,
                    f"ledger_records[{index}].run_id",
                    "Ledger record run_id does not match SynthesisOutput run_id.",
                )
            )
        if record.ledger_claim_id in lookup:
            errors.append(
                _error(
                    ValidationErrorCode.LEDGER_MISMATCH,
                    f"ledger_records[{index}].ledger_claim_id",
                    "Duplicate Ledger claim IDs are not allowed in final validation.",
                )
            )
        lookup[record.ledger_claim_id] = record
    return lookup, errors


def _ledger_schema_errors(record: LedgerRecord, index: int) -> list[ValidationError]:
    try:
        LedgerRecord.model_validate(record.model_dump(mode="python"))
    except PydanticValidationError as exc:
        return [
            _error(
                ValidationErrorCode.SCHEMA_ERROR,
                _prefix_location(f"ledger_records[{index}]", detail.get("loc", ())),
                str(detail.get("msg", "LedgerRecord schema validation failed.")),
            )
            for detail in exc.errors()
        ]
    return []


def _schema_errors_from_revalidation(synthesis: SynthesisOutput) -> list[ValidationError]:
    try:
        SynthesisOutput.model_validate(synthesis.model_dump(mode="python", warnings=False))
    except PydanticValidationError as exc:
        return [
            _error(
                ValidationErrorCode.SCHEMA_ERROR,
                _format_pydantic_location(detail.get("loc", ())),
                str(detail.get("msg", "SynthesisOutput schema validation failed.")),
            )
            for detail in exc.errors()
        ]
    return []


def _hidden_field_errors(synthesis: SynthesisOutput) -> list[ValidationError]:
    errors: list[ValidationError] = []
    _append_hidden_instance_fields(synthesis, "synthesis", errors)
    sections = _safe_sections(synthesis)
    if sections is None:
        errors.append(
            _error(
                ValidationErrorCode.SCHEMA_ERROR,
                "sections",
                "SynthesisOutput sections must be a list of SynthesisSection instances.",
            )
        )
        return errors
    for section_index, section in enumerate(sections):
        section_location = f"sections[{section_index}]"
        if not isinstance(section, SynthesisSection):
            errors.append(
                _error(
                    ValidationErrorCode.SCHEMA_ERROR,
                    section_location,
                    "Final validation requires SynthesisSection instances.",
                )
            )
            continue
        _append_hidden_instance_fields(section, section_location, errors)
        items = getattr(section, "items", None)
        if not isinstance(items, list):
            errors.append(
                _error(
                    ValidationErrorCode.SCHEMA_ERROR,
                    f"{section_location}.items",
                    "SynthesisSection items must be a list of SynthesisItem instances.",
                )
            )
            continue
        for item_index, item in enumerate(items):
            item_location = f"{section_location}.items[{item_index}]"
            if not isinstance(item, SynthesisItem):
                errors.append(
                    _error(
                        ValidationErrorCode.SCHEMA_ERROR,
                        item_location,
                        "Final validation requires SynthesisItem instances.",
                    )
                )
                continue
            _append_hidden_instance_fields(item, item_location, errors)
    return errors


def _section_structure_errors(synthesis: SynthesisOutput) -> list[ValidationError]:
    errors: list[ValidationError] = []
    seen: set[SectionType] = set()
    previous_order = -1
    for index, section in enumerate(_safe_sections(synthesis) or []):
        if not isinstance(section, SynthesisSection):
            continue
        location = f"sections[{index}].section_type"
        section_type = _enum_or_none(SectionType, getattr(section, "section_type", None))
        if section_type not in RELEASE_SECTION_ORDER:
            errors.append(
                _error(
                    ValidationErrorCode.INVALID_SECTION,
                    location,
                    "Section type is not part of the application-defined brief format.",
                )
            )
            continue
        if section_type in seen:
            errors.append(
                _error(
                    ValidationErrorCode.INVALID_SECTION,
                    location,
                    "Each application-defined section may appear at most once.",
                )
            )
        seen.add(section_type)
        current_order = RELEASE_SECTION_ORDER.index(section_type)
        if current_order <= previous_order:
            errors.append(
                _error(
                    ValidationErrorCode.INVALID_SECTION,
                    location,
                    "Sections must follow the application-defined section order.",
                )
            )
        previous_order = current_order
    return errors


def _content_errors(
    synthesis: SynthesisOutput,
    ledger_lookup: Mapping[object, LedgerRecord],
    max_ledger_claim_uses: int,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    claim_use_counts: Counter[object] = Counter()

    for section_index, section in enumerate(_safe_sections(synthesis) or []):
        if not isinstance(section, SynthesisSection):
            continue
        section_type = _enum_or_none(SectionType, getattr(section, "section_type", None))
        section_location = f"sections[{section_index}]"
        items = getattr(section, "items", None)
        if not isinstance(items, list):
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, SynthesisItem):
                continue
            item_location = f"{section_location}.items[{item_index}]"
            claim_use_counts[item.ledger_claim_id] += 1
            _append_section_compatibility_errors(
                errors,
                section_type,
                item,
                item_location,
            )
            template = _append_template_errors(errors, section_type, item, item_location)
            ledger = ledger_lookup.get(item.ledger_claim_id)
            if ledger is None:
                errors.append(
                    _error(
                        ValidationErrorCode.LEDGER_MISMATCH,
                        f"{item_location}.ledger_claim_id",
                        "Synthesis item references a Ledger claim ID that is not present.",
                    )
                )
                continue
            _append_ledger_match_errors(errors, ledger, item, item_location)
            if template is not None:
                _append_template_policy_errors(errors, ledger, template, item, item_location)

    for ledger_claim_id, count in claim_use_counts.items():
        if count > max_ledger_claim_uses:
            errors.append(
                _error(
                    ValidationErrorCode.LEDGER_MISMATCH,
                    f"ledger_claim_id:{ledger_claim_id}",
                    "Ledger claim exceeds the permitted final-brief use count.",
                )
            )
    return errors


def _append_section_compatibility_errors(
    errors: list[ValidationError],
    section_type: SectionType | None,
    item: SynthesisItem,
    item_location: str,
) -> None:
    stance = _enum_or_none(Stance, item.stance)
    if section_type is SectionType.SUPPORTING and stance is not Stance.SUPPORTING:
        errors.append(
            _error(
                ValidationErrorCode.INVALID_SECTION,
                f"{item_location}.stance",
                "Supporting sections may render only supporting Ledger items.",
            )
        )
    if section_type is SectionType.OPPOSING and stance is not Stance.OPPOSING:
        errors.append(
            _error(
                ValidationErrorCode.INVALID_SECTION,
                f"{item_location}.stance",
                "Opposing sections may render only opposing Ledger items.",
            )
        )


def _append_template_errors(
    errors: list[ValidationError],
    section_type: SectionType | None,
    item: SynthesisItem,
    item_location: str,
) -> ApprovedConnectiveTemplate | None:
    template = APPROVED_CONNECTIVE_TEMPLATES.get(item.connective_template_id)
    if template is None:
        errors.append(
            _error(
                ValidationErrorCode.INVALID_TEMPLATE,
                f"{item_location}.connective_template_id",
                "Connective template ID is not in the approved non-factual registry.",
            )
        )
        return None

    stance = _enum_or_none(Stance, item.stance)
    if stance is not None and stance not in template.allowed_stances:
        errors.append(
            _error(
                ValidationErrorCode.INVALID_TEMPLATE,
                f"{item_location}.connective_template_id",
                "Connective template is not approved for this Ledger stance.",
            )
        )
    if section_type is not None and section_type not in template.allowed_sections:
        errors.append(
            _error(
                ValidationErrorCode.INVALID_TEMPLATE,
                f"{item_location}.connective_template_id",
                "Connective template is not approved for this section type.",
            )
        )
    return template


def _append_ledger_match_errors(
    errors: list[ValidationError],
    ledger: LedgerRecord,
    item: SynthesisItem,
    item_location: str,
) -> None:
    if item.reviewer_approval_id != ledger.reviewer_approval_id:
        errors.append(
            _error(
                ValidationErrorCode.LEDGER_MISMATCH,
                f"{item_location}.reviewer_approval_id",
                "Reviewer approval ID does not match the Ledger record.",
            )
        )
    if item.approved_factual_statement != ledger.approved_factual_statement:
        errors.append(
            _error(
                ValidationErrorCode.ALTERED_STATEMENT,
                f"{item_location}.approved_factual_statement",
                "Approved factual statement must exactly match the Ledger record.",
            )
        )
    if item.stance != ledger.stance:
        errors.append(
            _error(
                ValidationErrorCode.LEDGER_MISMATCH,
                f"{item_location}.stance",
                "Synthesis item stance does not match the Ledger record.",
            )
        )
    if item.placement != ledger.placement:
        errors.append(
            _error(
                ValidationErrorCode.LEDGER_MISMATCH,
                f"{item_location}.placement",
                "Synthesis item placement does not match the Ledger record.",
            )
        )
    if item.entailment != ledger.entailment:
        errors.append(
            _error(
                ValidationErrorCode.LEDGER_MISMATCH,
                f"{item_location}.entailment",
                "Synthesis item entailment does not match the Ledger record.",
            )
        )


def _append_template_policy_errors(
    errors: list[ValidationError],
    ledger: LedgerRecord,
    template: ApprovedConnectiveTemplate,
    item: SynthesisItem,
    item_location: str,
) -> None:
    if ledger.placement is Placement.QUALIFIED_ONLY and not template.qualifies_limited_evidence:
        errors.append(
            _error(
                ValidationErrorCode.INVALID_TEMPLATE,
                f"{item_location}.connective_template_id",
                "qualified_only Ledger items require an approved qualification template.",
            )
        )

    if ledger.entailment is Entailment.PARTIAL:
        if template.entailment_warning is not Entailment.PARTIAL:
            errors.append(
                _error(
                    ValidationErrorCode.INVALID_TEMPLATE,
                    f"{item_location}.connective_template_id",
                    "Partial entailment items require the partial-support warning template.",
                )
            )
    elif ledger.entailment is Entailment.WEAK:
        if template.entailment_warning is not Entailment.WEAK:
            errors.append(
                _error(
                    ValidationErrorCode.INVALID_TEMPLATE,
                    f"{item_location}.connective_template_id",
                    "Weak entailment items require the weak-support warning template.",
                )
            )
    elif item.connective_template_id in {
        PARTIAL_ENTAILMENT_TEMPLATE_ID,
        WEAK_ENTAILMENT_TEMPLATE_ID,
    }:
        errors.append(
            _error(
                ValidationErrorCode.INVALID_TEMPLATE,
                f"{item_location}.connective_template_id",
                "Entailment warning templates may not be used for Strong entailment items.",
            )
        )


def _render_validated_brief(
    synthesis: SynthesisOutput,
    ledger_lookup: Mapping[object, LedgerRecord],
    authoritative_claim: str,
) -> str:
    lines = [
        f"# {BRIEF_TITLE}",
        "",
        f"{CLAIM_LABEL}: {authoritative_claim}",
    ]
    for section in synthesis.sections:
        lines.extend(("", f"## {RELEASE_SECTION_HEADINGS[section.section_type]}"))
        for item in section.items:
            template = APPROVED_CONNECTIVE_TEMPLATES[item.connective_template_id]
            ledger = ledger_lookup[item.ledger_claim_id]
            lines.append(
                f"- {template.text} {ledger.approved_factual_statement} "
                f"[source: {ledger.source_url}]"
            )
    return "\n".join(lines) + "\n"


def _append_hidden_instance_fields(
    instance: StrictModel,
    location: str,
    errors: list[ValidationError],
) -> None:
    expected_fields = set(type(instance).model_fields)
    unexpected = {
        field_name
        for field_name in vars(instance)
        if field_name not in expected_fields and not field_name.startswith("_")
    }
    extra = getattr(instance, "__pydantic_extra__", None)
    if extra:
        unexpected.update(extra)
    for field_name in sorted(unexpected):
        errors.append(
            _error(
                ValidationErrorCode.SCHEMA_ERROR,
                f"{location}.{field_name}",
                "Unknown renderable fields are not allowed in SynthesisOutput.",
            )
        )


def _safe_sections(synthesis: SynthesisOutput) -> list[object] | None:
    sections = getattr(synthesis, "sections", None)
    return sections if isinstance(sections, list) else None


def _enum_or_none(enum_type: type[_EnumT], value: object) -> _EnumT | None:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return None


def _format_pydantic_location(location: object) -> str:
    if not isinstance(location, tuple) or not location:
        return "synthesis"
    return ".".join(str(part) for part in location)


def _prefix_location(prefix: str, location: object) -> str:
    suffix = _format_pydantic_location(location)
    if suffix == "synthesis":
        return prefix
    return f"{prefix}.{suffix}"


def _error(
    code: ValidationErrorCode,
    location: str,
    message: str,
) -> ValidationError:
    return ValidationError(code=code, location=location, message=message)
