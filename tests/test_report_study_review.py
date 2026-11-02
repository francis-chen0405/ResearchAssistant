from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run
from test_v2_phase11_final_output import _continuation, _synthesis

from researchassistant.agents.v2_final_output import build_v2_final_research_output
from researchassistant.api.application_services.evidence_projection import (
    _build_v2_evidence_display,
)
from researchassistant.evidence.evidence_core import count_words
from researchassistant.evidence.report_review import (
    OpeningAssertion,
    PublicationReview,
    V2ReportStudyReview,
    apply_review,
)


def test_reviewed_study_opening_and_non_doi_mirror_fail_closed(tmp_path: Path) -> None:
    _, admission = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=admission,
        continuation=_continuation(admission.run_id),
        synthesis=_synthesis(admission),
        created_at=admission.completed_at,
    )
    display = _build_v2_evidence_display(output, admission)
    # This scenario exercises the report contracts with an explicitly synthetic
    # vehicle-monitoring claim; it does not alter the persisted admission fixture.
    output = output.model_copy(
        update={"exact_claim": "Vehicle monitoring affects theft and clearance."}
    )
    item = display.items[0]
    statement = "The randomized mobile patrol study REG-2024 measured theft over six months."
    limitation = "The follow-up was limited to six months."
    item = item.model_copy(
        update={
            "quote_passage": statement,
            "approved_factual_statement": statement,
            "limitations": (limitation,),
        }
    )
    display = display.model_copy(update={"items": (item,)})
    capture = admission.analyst_result.input.queued_candidates[0].snapshot
    text = "REG-2024 Official Report Ada Author 2024 Public Institute"
    capture = capture.model_copy(
        update={
            "source_url": "https://institute.example/reports/REG-2024",
            "normalized_text": text,
            "snapshot_sha256": sha256(text.encode()).hexdigest(),
            "word_count": count_words(text),
        }
    )
    publication = PublicationReview(
        source_ids=(item.source_id,),
        identifier="REG-2024",
        authority=capture,
        title="Official Report",
        authors=("Ada Author",),
        date="2024",
        venue="Public Institute",
    )

    def assertion(role: str, text: str) -> OpeningAssertion:
        return OpeningAssertion(
            ledger_claim_id=item.ledger_claim_id,
            study_identifier="REG-2024",
            role=role,
            text=text,
            design="randomized",
            intervention="mobile patrol",
            outcome="theft",
        )

    review = V2ReportStudyReview(
        run_id=display.run_id,
        reviewer="Fixture reviewer",
        rationale="All admitted findings and limitations reviewed.",
        reviewed_at=admission.completed_at,
        publications=(publication,),
        assertions=(assertion("main", statement), assertion("limitation", limitation)),
    )
    result = apply_review(display, review)
    assert len(result.study_opening) == 2
    assert result.items[0].verified_publication.doi is None
    assert result.items[0].verified_publication.canonical_url != item.source_url
    assert not display.study_opening
    from researchassistant.evidence.brief_export import _v2_reading_aid

    export = _v2_reading_aid(output, result)
    (tmp_path / "reviewed-report.md").write_text(export)
    assert statement in export and limitation in export
    assert "not necessarily representative" not in export
    assert publication.authority.source_url in export
    assert item.source_url in export
    assert "reviewed authoritative identifier" in export
    assert V2ReportStudyReview.model_validate_json(review.model_dump_json()) == review
    # A second independent registered study keeps a different design and outcome.
    second_text = "The observational fixed camera study REG-2025 measured clearance over one year."
    second = item.model_copy(
        update={
            "source_id": uuid4(),
            "ledger_claim_id": uuid4(),
            "quote_passage": second_text,
            "approved_factual_statement": second_text,
            "relationship_to_claim": type(item.relationship_to_claim)("challenges"),
        }
    )
    second_authority_text = "REG-2025 Independent Report Ada Author 2024 Public Institute"
    second_capture = capture.model_copy(
        update={
            "normalized_text": second_authority_text,
            "snapshot_sha256": sha256(second_authority_text.encode()).hexdigest(),
            "word_count": count_words(second_authority_text),
        }
    )
    second_publication = publication.model_copy(
        update={
            "source_ids": (second.source_id,),
            "identifier": "REG-2025",
            "title": "Independent Report",
            "authority": second_capture,
        }
    )
    contrast = OpeningAssertion(
        ledger_claim_id=second.ledger_claim_id,
        study_identifier="REG-2025",
        role="contrast",
        text=second_text,
        design="observational",
        intervention="fixed camera",
        outcome="clearance",
    )
    multi = apply_review(
        display.model_copy(update={"items": (item, second)}),
        review.model_copy(
            update={
                "publications": (publication, second_publication),
                "assertions": (review.assertions[0], contrast, review.assertions[1]),
            }
        ),
    )
    assert len(multi.study_opening) == 3
    reversed_review = review.model_copy(
        update={
            "publications": (publication, second_publication),
            "assertions": (
                contrast.model_copy(update={"role": "main"}),
                review.assertions[0].model_copy(update={"role": "contrast"}),
                review.assertions[1],
            ),
        }
    )
    reversed_result = apply_review(
        display.model_copy(update={"items": (item, second)}), reversed_review
    )
    assert reversed_result.study_opening[0].ledger_claim_id == second.ledger_claim_id
    assert reversed_result.study_opening[1].ledger_claim_id == item.ledger_claim_id
    assert multi.study_opening[1].design == "observational"
    assert multi.study_opening[0].intervention == "mobile patrol"
    assert {a.study_identifier for a in multi.study_opening} == {"REG-2024", "REG-2025"}
    with pytest.raises(ValueError, match="conflicting"):
        apply_review(
            display, review.model_copy(update={"publications": (publication, publication)})
        )
    bad = review.assertions[0].model_copy(update={"text": "An unsupported causal conclusion."})
    with pytest.raises(ValueError, match="exact admitted"):
        apply_review(display, review.model_copy(update={"assertions": (bad, review.assertions[1])}))
    with pytest.raises(ValueError, match="study identity"):
        apply_review(
            display,
            review.model_copy(
                update={
                    "assertions": (
                        review.assertions[0].model_copy(update={"study_identifier": "OTHER-ID"}),
                        review.assertions[1],
                    )
                }
            ),
        )
