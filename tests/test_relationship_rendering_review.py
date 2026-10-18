"""Finding relationships and search directions remain distinct, with exact old rendering."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from test_v2_phase9_luna_evidence_analyst import (
    NOW,
    FakeLunaAnalyst,
    _assessment,
    _batch_input,
    _prepare_db,
    _routing,
)
from test_v2_phase11_final_output import _continuation

from researchassistant.agents.v2_evidence_admission import run_v2_evidence_admission
from researchassistant.agents.v2_evidence_analyst import run_v2_evidence_analyst
from researchassistant.agents.v2_final_output import (
    _build_v2_final_research_output,
    build_v2_final_research_output,
    build_v2_synthesizer_input,
    reconstruct_saved_v2_final_output,
    render_v2_final_output,
)
from researchassistant.contracts.models import ResearchDirection, V2EvidenceRelationship
from researchassistant.evidence.renderer import (
    ADMISSION_VALIDATOR_CONFIG_VERSION,
    LEGACY_VALIDATOR_CONFIG_VERSION,
)
from researchassistant.evidence.synthesizer import build_v2_synthesis_output


@pytest.mark.parametrize("direction", tuple(ResearchDirection))
@pytest.mark.parametrize(
    "relationship",
    (
        V2EvidenceRelationship.SUPPORTS,
        V2EvidenceRelationship.CHALLENGES,
        V2EvidenceRelationship.QUALIFIES,
    ),
)
@pytest.mark.parametrize("claim_fit", (3, 4, 5))
def test_fresh_relationship_wording_and_qualifications_match_the_admitted_finding(
    tmp_path: Path,
    direction: ResearchDirection,
    relationship: V2EvidenceRelationship,
    claim_fit: int,
) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=_batch_input(run_id, direction=direction),
        llm_provider=FakeLunaAnalyst([_assessment(relationship=relationship, claim_fit=claim_fit)]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    admission = run_v2_evidence_admission(db_path=path, analyst_result=analyst, clock=lambda: NOW)
    continuation = _continuation(run_id)
    projection = build_v2_synthesizer_input(admission, continuation)
    assert projection.approved_ledger_items[0].relationship_to_claim is relationship
    synthesis = build_v2_synthesis_output(synthesis_input=projection, created_at=NOW)
    output = build_v2_final_research_output(
        admission_result=admission,
        continuation=continuation,
        synthesis=synthesis,
        created_at=NOW,
    )
    assert output.release_validation.valid, output.release_validation.errors
    rendered = render_v2_final_output(output)
    assert "Direct supporting evidence:" not in rendered
    assert "Direct opposing evidence:" not in rendered
    if claim_fit == 5:
        wording = {
            V2EvidenceRelationship.SUPPORTS: "supporting",
            V2EvidenceRelationship.CHALLENGES: "challenging",
            V2EvidenceRelationship.QUALIFIES: "qualifying",
        }[relationship]
        assert f"- Evidence {wording} the claim:" in rendered
    else:
        assert "Indirect evidence—relevant but not independently decisive:" in rendered
    forged = synthesis.model_copy(
        update={
            "sections": (
                synthesis.sections[0].model_copy(
                    update={
                        "items": (
                            synthesis.sections[0]
                            .items[0]
                            .model_copy(
                                update={
                                    "connective_template_id": (
                                        "analyzer_challenges"
                                        if relationship is V2EvidenceRelationship.SUPPORTS
                                        else "analyzer_supports"
                                    )
                                }
                            ),
                        )
                    }
                ),
            )
        }
    )
    rejected = build_v2_final_research_output(
        admission_result=admission,
        continuation=continuation,
        synthesis=forged,
        created_at=NOW,
    )
    assert not rejected.release_validation.valid
    assert any("relationships" in error.message for error in rejected.release_validation.errors)


@pytest.mark.parametrize(
    "version", (LEGACY_VALIDATOR_CONFIG_VERSION, ADMISSION_VALIDATOR_CONFIG_VERSION)
)
def test_recorded_stance_wording_keeps_original_serialization_and_release_hash(
    tmp_path: Path,
    version: str,
) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=_batch_input(run_id),
        llm_provider=FakeLunaAnalyst(
            [
                _assessment(
                    relationship=V2EvidenceRelationship.CHALLENGES,
                    claim_fit=5,
                )
            ]
        ),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    admission = run_v2_evidence_admission(db_path=path, analyst_result=analyst, clock=lambda: NOW)
    continuation = _continuation(run_id)
    projection = build_v2_synthesizer_input(admission, continuation)
    old_items = tuple(
        item.model_copy(update={"relationship_to_claim": None})
        for item in projection.approved_ledger_items
    )
    assert "relationship_to_claim" not in old_items[0].model_dump_json()
    historical = build_v2_synthesis_output(
        synthesis_input=projection.model_copy(
            update={
                "approved_ledger_items": old_items,
                "qualifications": (),
            }
        ),
        created_at=NOW,
    )
    saved = _build_v2_final_research_output(
        admission_result=admission,
        continuation=continuation,
        synthesis=historical,
        created_at=NOW,
        evidence_validator_version=version,
    )
    assert saved.release_validation.valid
    encoded, rendered = saved.model_dump_json(), render_v2_final_output(saved)
    assert "- Direct supporting evidence:" in rendered
    rebuilt = reconstruct_saved_v2_final_output(
        saved_output=saved,
        evidence_result=admission,
        continuation=continuation,
    )
    assert render_v2_final_output(rebuilt) == rendered
    assert rebuilt.release_validation == saved.release_validation
    assert saved.model_dump_json() == encoded
    fresh = build_v2_final_research_output(
        admission_result=admission,
        continuation=continuation,
        synthesis=historical,
        created_at=NOW,
    )
    assert not fresh.release_validation.valid


def test_relationship_projection_rejects_a_foreign_assessment(tmp_path: Path) -> None:
    from test_v2_post_analysis import _admission

    admission = _admission(tmp_path)
    original = admission.analyst_result.source_results[0]
    foreign = original.model_copy(update={"run_id": uuid4()})
    forged = admission.model_copy(
        update={
            "analyst_result": admission.analyst_result.model_copy(
                update={"source_results": (foreign,)}
            )
        }
    )
    with pytest.raises(ValueError, match="relationship must belong"):
        build_v2_synthesizer_input(forged, _continuation(admission.run_id))


def test_historical_reviewer_items_cannot_claim_analyzer_relationships(tmp_path: Path) -> None:
    from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run
    from test_v2_phase11_final_output import _synthesis

    from researchassistant.evidence.renderer import validate_final_release

    _path, reviewer = _run(tmp_path, Phase10Provider([_approved()]))
    synthesis = _synthesis(reviewer)
    section = synthesis.sections[0]
    forged = synthesis.model_copy(
        update={
            "sections": (
                section.model_copy(
                    update={
                        "items": (
                            section.items[0].model_copy(
                                update={"connective_template_id": "analyzer_supports"}
                            ),
                        )
                    }
                ),
            )
        }
    )
    records = tuple(
        source.ledger_record for source in reviewer.source_results if source.ledger_record
    )
    result = validate_final_release(
        forged,
        records,
        authoritative_claim=reviewer.analyst_result.input.exact_claim,
        validated_at=NOW,
    )
    assert not result.valid
    assert any("Analyzer-admitted" in error.message for error in result.errors)
