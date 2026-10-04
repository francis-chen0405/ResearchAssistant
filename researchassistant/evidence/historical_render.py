"""Release-v1 rendering for supported historical inspection, with original hash checks."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from agents.renderer import render_brief
from researchassistant.contracts.models import (
    BRIEF_TITLE,
    CLAIM_LABEL,
    RELEASE_SECTION_HEADINGS,
    LedgerRecord,
    ProviderRunContract,
    SynthesisOutput,
    ValidationResult,
)
from researchassistant.storage.historical_decode import AUGUST_POLICY, AUGUST_PROMPTS, AUGUST_SCHEMA

# Verified against retained 1fc21a8:agents/renderer.py, mvp1-release-validator-v1.
RELEASE_V1_TEMPLATES = {
    "supporting_evidence": "Supporting evidence:",
    "opposing_evidence": "Opposing evidence:",
    "limitation": "A limitation is:",
    "partial_entailment": "The source provides partial support:",
    "weak_entailment": "The source provides weak support:",
    "scope_qualification": "This source addresses a narrower version of the claim:",
    "reliability_qualification": "This source's reliability is limited:",
}


def render_native_historical_brief(
    synthesis: SynthesisOutput,
    records: Sequence[LedgerRecord],
    claim: str,
    validation: ValidationResult,
    contract: ProviderRunContract | None,
) -> str:
    if contract is None or (
        contract.schema_identity,
        contract.prompt_identity,
        contract.policy_identity,
    ) != (AUGUST_SCHEMA, AUGUST_PROMPTS, AUGUST_POLICY):
        raise ValueError("unsupported historical released-content contract")
    ProviderRunContract.model_validate(contract.model_dump())
    if not validation.valid or validation.validator_config_version != "mvp1-release-validator-v1":
        raise ValueError("unsupported historical release-validation contract")
    # Reuse current structural/provenance/template matching checks. This does not
    # grant a new release or change the persisted validation/hash.
    render_brief(synthesis, records, authoritative_claim=claim)
    lookup = {record.ledger_claim_id: record for record in records}
    lines = [f"# {BRIEF_TITLE}", "", f"{CLAIM_LABEL}: {claim}"]
    for section in synthesis.sections:
        lines.extend(("", f"## {RELEASE_SECTION_HEADINGS[section.section_type]}"))
        for item in section.items:
            record = lookup[item.ledger_claim_id]
            lines.append(
                f"- {RELEASE_V1_TEMPLATES[item.connective_template_id]} "
                f"{record.approved_factual_statement} [source: {record.source_url}]"
            )
    result = "\n".join(lines) + "\n"
    if sha256(result.encode("utf-8")).hexdigest() != validation.rendered_brief_hash:
        raise ValueError("historical released brief does not match its original validation hash")
    return result
