from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_v2_phase10_reviewer_ledger import (
    Phase10Provider,
    _approved,
    _rejected,
    _run,
)
from test_v2_phase11_final_output import _continuation, _synthesis

from agents.v2_final_output import build_v2_final_research_output
from frontend.api import _build_v2_evidence_display
from models import CandidateQuoteBlock, SynthesisOutput


def test_evidence_display_excludes_rejected_source_without_ledger_record(
    tmp_path: Path,
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_rejected()]))
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        synthesis=SynthesisOutput(
            run_id=reviewer_result.run_id,
            synthesizer_prompt_version="test",
            synthesizer_model_name="mimo-v2.5-pro",
            created_at=reviewer_result.completed_at,
            sections=(),
        ),
        created_at=reviewer_result.completed_at,
    )

    display = _build_v2_evidence_display(output, reviewer_result)

    assert display.items == ()


def test_admitted_detail_links_to_exact_record_and_preserves_relationship(
    tmp_path: Path,
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        synthesis=_synthesis(reviewer_result),
        created_at=reviewer_result.completed_at,
    )

    display = _build_v2_evidence_display(output, reviewer_result)

    item = display.items[0]
    record = reviewer_result.source_results[0].ledger_record
    analyst = reviewer_result.analyst_result.source_results[0]
    assert record is not None
    assert analyst.assessment is not None
    assert item.ledger_claim_id == record.ledger_claim_id
    assert item.approved_factual_statement == record.approved_factual_statement
    assert item.source_url == record.source_url
    assert item.relationship_to_claim is analyst.assessment.relationship_to_claim
    assert item.direction == "support"
    assert display.research_status.source == "final_output"


def test_projection_rejects_candidate_quote_forged_away_from_ledger_record(
    tmp_path: Path,
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        synthesis=_synthesis(reviewer_result),
        created_at=reviewer_result.completed_at,
    )
    analyst_result = reviewer_result.analyst_result
    source_result = analyst_result.source_results[0]
    assert source_result.candidate is not None
    candidate_data = source_result.candidate.model_dump(mode="python")
    candidate_data["extracted_quote_block"] = "A different statement is displayed as the quote."
    forged_candidate = CandidateQuoteBlock.model_validate(candidate_data)
    forged_source = source_result.model_copy(update={"candidate": forged_candidate})
    forged_analyst_result = analyst_result.model_copy(update={"source_results": (forged_source,)})
    forged_result = reviewer_result.model_copy(update={"analyst_result": forged_analyst_result})

    with pytest.raises((ValueError, ValidationError), match="candidate|quote|snapshot|Ledger"):
        _build_v2_evidence_display(output, forged_result)
