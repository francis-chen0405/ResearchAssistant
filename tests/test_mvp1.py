from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from agents.renderer import render_brief, validate_final_release
from agents.reviewer import (
    ReviewerDecision,
    ReviewerInput,
    build_statement_review_result,
    derive_reviewer_approval_id,
)
from models import (
    ReviewerFailureCode,
    RunStatus,
    SectionType,
    StatementDraft,
    SynthesisOutput,
)
from orchestrator import run_fixture_pipeline
from store import read_run, read_synthesis

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures"
VALID_FIXTURE = FIXTURES / "basic_valid_run"
INVALID_FIXTURE = FIXTURES / "invalid_release_run"


def _draft(*, statement: str = "The exact reviewed statement.", suffix: int = 1) -> StatementDraft:
    return StatementDraft(
        run_id=UUID("81000000-0000-0000-0000-000000000001"),
        statement_draft_id=UUID(f"81000000-0000-0000-0000-{suffix:012d}"),
        quote_block_id=UUID("81000000-0000-0000-0000-000000000100"),
        stance="supporting",
        draft_statement=statement,
        claim_fit=4,
        analyst_prompt_version="analyst-v1",
        analyst_model_name="fake-analyst",
        drafted_at=NOW,
    )


def _reviewer_input(draft: StatementDraft) -> ReviewerInput:
    return ReviewerInput(
        extracted_quote_block='[Before.] "The exact reviewed statement." [After.]',
        preceding_context="Before.",
        following_context="After.",
        draft_statement=draft.draft_statement,
        claim_fit=draft.claim_fit,
    )


def _approved_decision(statement: str = "The exact reviewed statement.") -> ReviewerDecision:
    return ReviewerDecision(
        reviewed_statement=statement,
        approved=True,
        rationale="All review checks passed.",
    )


def test_model_facing_synthesis_schema_rejects_all_framing_fields(tmp_path: Path) -> None:
    result = run_fixture_pipeline(VALID_FIXTURE, output_dir=tmp_path / "valid")
    payload = result.synthesis_output.model_dump(mode="python")

    for field, value in (
        ("title", "A factual title claiming the policy works"),
        ("claim_definition", "A mutated claim"),
    ):
        with pytest.raises(ValidationError):
            SynthesisOutput.model_validate({**payload, field: value})

    section_payload = payload["sections"][0]
    with pytest.raises(ValidationError):
        SynthesisOutput.model_validate(
            {
                **payload,
                "sections": [
                    {**section_payload, "heading": "The evidence proves the policy works"},
                    *payload["sections"][1:],
                ],
            }
        )


def test_renderer_uses_only_application_framing_and_authoritative_claim(tmp_path: Path) -> None:
    result = run_fixture_pipeline(VALID_FIXTURE, output_dir=tmp_path / "valid")

    rendered = render_brief(
        result.synthesis_output,
        result.ledger_records,
        authoritative_claim=result.raw_claim,
    )

    assert rendered.startswith(
        "# Research Brief\n\nClaim under review: The fixture policy improves student outcomes.\n"
    )
    assert "## Supporting Evidence" in rendered
    assert "## Opposing Evidence" in rendered


def test_heading_like_phrases_in_approved_body_text_remain_valid(tmp_path: Path) -> None:
    result = run_fixture_pipeline(VALID_FIXTURE, output_dir=tmp_path / "valid")
    body_text = (
        "The report discusses Supporting Evidence, Opposing Evidence, and Limitations "
        "as body-text labels."
    )
    item = (
        result.synthesis_output.sections[0]
        .items[0]
        .model_copy(update={"approved_factual_statement": body_text})
    )
    ledgers = [
        record.model_copy(update={"approved_factual_statement": body_text})
        if record.ledger_claim_id == item.ledger_claim_id
        else record
        for record in result.ledger_records
    ]
    section = result.synthesis_output.sections[0].model_copy(update={"items": [item]})
    synthesis = result.synthesis_output.model_copy(
        update={"sections": [section, *result.synthesis_output.sections[1:]]}
    )

    validation = validate_final_release(
        synthesis,
        ledgers,
        authoritative_claim=result.raw_claim,
        validated_at=NOW,
    )

    assert validation.valid


def test_final_validator_rejects_hidden_framing_extra_sections_and_reordering(
    tmp_path: Path,
) -> None:
    result = run_fixture_pipeline(VALID_FIXTURE, output_dir=tmp_path / "valid")
    synthesis = result.synthesis_output

    factual_title = synthesis.model_copy(deep=True)
    factual_title.__dict__["title"] = "The fixture policy definitively improves outcomes"
    altered_claim = synthesis.model_copy(deep=True)
    altered_claim.__dict__["claim_definition"] = "The policy always improves outcomes."
    mutated_heading = synthesis.model_copy(deep=True)
    mutated_heading.sections[0].__dict__["heading"] = "Evidence proving the claim"
    reordered = synthesis.model_copy(update={"sections": list(reversed(synthesis.sections))})
    extra_section = synthesis.model_copy(
        update={
            "sections": [
                *synthesis.sections,
                synthesis.sections[0].model_copy(update={"section_type": SectionType.CONCLUSION}),
            ]
        }
    )
    duplicated = synthesis.model_copy(
        update={"sections": [synthesis.sections[0], *synthesis.sections]}
    )
    malformed = synthesis.model_copy(
        update={"sections": [{"section_type": "supporting", "items": []}]}
    )

    for adversarial in (
        factual_title,
        altered_claim,
        mutated_heading,
        reordered,
        extra_section,
        duplicated,
        malformed,
    ):
        validation = validate_final_release(
            adversarial,
            result.ledger_records,
            authoritative_claim=result.raw_claim,
            validated_at=NOW,
        )
        assert not validation.valid
        assert validation.rendered_brief_hash is None


def test_reviewer_decision_rejects_provider_supplied_approval_id() -> None:
    with pytest.raises(ValidationError):
        ReviewerDecision.model_validate(
            {
                "reviewed_statement": "The exact reviewed statement.",
                "approved": True,
                "rationale": "Approved.",
                "reviewer_approval_id": "rappr_v1_" + "a" * 64,
            }
        )


def test_approval_ids_are_application_owned_stable_and_semantic() -> None:
    draft = _draft()
    reviewer_input = _reviewer_input(draft)
    decision = _approved_decision()

    first = build_statement_review_result(
        draft,
        reviewer_input,
        decision,
        reviewer_prompt_version="reviewer-v1",
        reviewer_model_name="fake-reviewer",
        reviewed_at=NOW,
    )
    second = build_statement_review_result(
        draft,
        reviewer_input,
        decision,
        reviewer_prompt_version="different-prompt-version",
        reviewer_model_name="different-route-metadata",
        reviewed_at=NOW + timedelta(days=1),
    )
    changed = _draft(statement="A materially different reviewed statement.", suffix=2)
    changed_id = derive_reviewer_approval_id(changed, _approved_decision(changed.draft_statement))

    assert isinstance(first.reviewer_approval_id, str)
    assert first.reviewer_approval_id.startswith("rappr_v1_")
    assert len(first.reviewer_approval_id) == len("rappr_v1_") + 64
    assert first.reviewer_approval_id == second.reviewer_approval_id
    assert first.reviewer_approval_id != changed_id


def test_altered_reviewed_text_is_rejected_before_id_creation(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    draft = _draft()
    called = False

    def fail_if_called(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("approval ID derivation ran before exact-text validation")

    monkeypatch.setattr("agents.reviewer.derive_reviewer_approval_id", fail_if_called)
    with pytest.raises(ValueError, match="exactly match"):
        build_statement_review_result(
            draft,
            _reviewer_input(draft),
            _approved_decision("Altered reviewed text."),
            reviewer_prompt_version="reviewer-v1",
            reviewer_model_name="fake-reviewer",
            reviewed_at=NOW,
        )
    assert not called


def test_rejected_decisions_receive_no_approval_id() -> None:
    draft = _draft()
    result = build_statement_review_result(
        draft,
        _reviewer_input(draft),
        ReviewerDecision(
            reviewed_statement=draft.draft_statement,
            approved=False,
            failure_code=ReviewerFailureCode.NOT_ENTAILED,
            rationale="The quotation does not entail the statement.",
        ),
        reviewer_prompt_version="reviewer-v1",
        reviewer_model_name="fake-reviewer",
        reviewed_at=NOW,
    )

    assert not result.approved
    assert result.reviewer_approval_id is None


def test_fixture_terminal_statuses_survive_database_reopen(tmp_path: Path) -> None:
    valid = run_fixture_pipeline(VALID_FIXTURE, output_dir=tmp_path / "valid")
    invalid = run_fixture_pipeline(INVALID_FIXTURE, output_dir=tmp_path / "invalid")

    assert isinstance(valid.reviewer_decisions[0].reviewer_approval_id, UUID)
    assert read_run(valid.db_path, valid.run_id).status is RunStatus.COMPLETED
    assert read_run(invalid.db_path, invalid.run_id).status is RunStatus.BLOCKED


def test_legacy_sqlite_synthesis_framing_is_ignored_on_read(tmp_path: Path) -> None:
    result = run_fixture_pipeline(VALID_FIXTURE, output_dir=tmp_path / "valid")
    with sqlite3.connect(result.db_path) as connection:
        connection.execute(
            "UPDATE synthesis_attempts SET title = ?, claim_definition = ? WHERE run_id = ?",
            ("Legacy factual title", "Legacy mutated claim", str(result.run_id)),
        )
        connection.execute(
            "UPDATE synthesis_sections SET heading = ? WHERE run_id = ?",
            ("Legacy model-owned heading", str(result.run_id)),
        )
        connection.commit()

    assert read_synthesis(result.db_path, result.run_id) == result.synthesis_output
