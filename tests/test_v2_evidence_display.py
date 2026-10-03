from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

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
from frontend.api import (
    V2EvidenceDisplayItem,
    _build_shared_website_groups,
    _build_v2_evidence_display,
    _source_budget_outcome,
    _source_context_notice,
)
from researchassistant.contracts.models import (
    CandidateQuoteBlock,
    SynthesisOutput,
    V2DeepAnalysisSourceExecution,
    V2DeepAnalysisSourceExecutionState,
)


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
    assert item.claim_fit == record.claim_fit
    assert item.relationship_to_claim is analyst.assessment.relationship_to_claim
    assert item.direction == "support"
    assert display.research_status.source == "final_output"


def test_source_title_projection_uses_readable_fallback_and_retains_captured_title(
    tmp_path: Path,
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        synthesis=_synthesis(reviewer_result),
        created_at=reviewer_result.completed_at,
    )
    source = output.all_surviving_sources[0]
    captured_title = "S2056608520000082jra 1..28"
    source_with_citation_heading = source.model_copy(
        update={
            "title": captured_title,
            "source_url": "https://example.org/paper.pdf",
        }
    )
    titled_output = output.model_copy(
        update={"all_surviving_sources": (source_with_citation_heading,)}
    )

    display = _build_v2_evidence_display(titled_output, reviewer_result)

    title = display.source_titles[0]
    assert title.source_id == source.source_id
    assert title.display_title == "PDF file: paper.pdf (example.org)"
    assert title.captured_title == captured_title


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


def test_typed_source_budget_block_is_distinct_from_extraction_failure() -> None:
    source_id = uuid4()
    blocked = V2DeepAnalysisSourceExecution(
        source_id=source_id,
        state=V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED,
        failure_reason="source token budget could not cover this request",
    )

    assert _source_budget_outcome(blocked) == "source_budget_blocked"


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        ("source {source} token cap cannot cover this call", "token_cap_blocked"),
        (
            "LLMProviderExecutionError: LLM provider failed: source {source} "
            "token cap cannot cover this call",
            "token_cap_blocked",
        ),
        ("source {source} physical-call cap is exhausted", "physical_call_cap_blocked"),
        (
            "Unexpected wrapper: source {source} token cap cannot cover this call",
            None,
        ),
        ("source {source} token cap cannot cover this call after retry", None),
        ("source 00000000-0000-4000-8000-000000000000 token cap cannot cover this call", None),
        ("provider returned an unrelated extraction error", None),
    ),
)
def test_historical_extraction_budget_reason_requires_exact_source_bound_message(
    message: str, expected: str | None
) -> None:
    source_id = uuid4()
    execution = V2DeepAnalysisSourceExecution(
        source_id=source_id,
        state=V2DeepAnalysisSourceExecutionState.EXTRACTION_FAILED,
        failure_reason=message.format(source=source_id),
    )

    assert _source_budget_outcome(execution) == expected


def _display_item(source_id: UUID, source_url: str) -> V2EvidenceDisplayItem:
    return V2EvidenceDisplayItem(
        source_id=source_id,
        ledger_claim_id=uuid4(),
        source_url=source_url,
        source_family="family",
        direction="support",
        relationship_to_claim="qualifies",
        approved_factual_statement="A narrow finding.",
        recommendation_status="Analyzed",
        evidence_summary="A bounded description.",
        supporting_proposition="A bounded proposition.",
        quote_passage="An exact quote.",
        validation_status="analyzer_admitted_not_independently_reviewed",
    )


def test_shared_website_groups_only_exact_same_host_without_claiming_identity() -> None:
    same_host_items = tuple(
        _display_item(uuid4(), url)
        for url in (
            "https://imy.se/page-one",
            "https://www.imy.se/page-two",
            "https://imy.se/en/page-three",
        )
    )
    different_domain = _display_item(uuid4(), "https://example.org/page")

    groups = _build_shared_website_groups((*same_host_items, different_domain))

    assert len(groups) == 1
    assert groups[0].host == "imy.se"
    assert set(groups[0].source_ids) == {item.source_id for item in same_host_items}
    assert "does not establish independent corroboration" in groups[0].explanation
    assert "duplicates" in groups[0].explanation
    assert different_domain.source_id not in groups[0].source_ids


def test_legal_source_context_discloses_unverified_scope_and_broad_state_assertion() -> None:
    notice = _source_context_notice(
        source_type="general_web",
        exact_claim="Private surveillance is illegal in all 50 states.",
        title="US Surveillance Laws",
        statement="Home video recording is generally legal in all 50 states.",
    )

    assert notice is not None
    assert "Legal scope has not been independently verified" in notice
    assert "all-50-states statement has not been independently verified" in notice
    assert "jurisdiction" in notice
    missing_type_notice = _source_context_notice(
        source_type=None,
        exact_claim="Private surveillance is illegal.",
        title="US Surveillance Laws - Surveillance Guides",
        statement=(
            "Recording video on one’s own property is generally legal in all 50 states, "
            "with incidental capture."
        ),
    )
    assert missing_type_notice is not None
    assert "all-50-states statement has not been independently verified" in missing_type_notice
    assert (
        _source_context_notice(
            source_type="research_paper",
            exact_claim="Private surveillance is illegal.",
            title="US Surveillance Laws",
            statement="A broad legal assertion.",
        )
        is None
    )
    assert (
        _source_context_notice(
            source_type="general_web",
            exact_claim="A method has a flaw.",
            title="Research overview",
            statement="The flaw was reported in a guide.",
        )
        is None
    )
