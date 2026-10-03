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

from agents.synthesizer import build_v2_synthesis_output
from agents.v2_evidence_admission import run_v2_evidence_admission
from agents.v2_evidence_analyst import run_v2_evidence_analyst
from agents.v2_final_output import (
    build_v2_final_research_output,
    build_v2_synthesizer_input,
    render_v2_final_output,
    validate_v2_final_release,
)
from agents.v2_post_analysis import build_v2_post_analysis_assessment
from researchassistant.contracts.models import (
    V2ClaimCoverageAssessment,
    V2ClaimCoverageDimension,
    V2ClaimCoverageState,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceRelationship,
)


def _admission(
    tmp_path: Path, relationship: V2EvidenceRelationship = V2EvidenceRelationship.QUALIFIES
) -> V2EvidenceAdmissionBatchResult:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=_batch_input(run_id),
        llm_provider=FakeLunaAnalyst([_assessment(relationship=relationship)]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    return run_v2_evidence_admission(db_path=path, analyst_result=analyst, clock=lambda: NOW)


def test_post_analysis_does_not_confuse_admission_with_support(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    result = build_v2_post_analysis_assessment(
        admission_result=admission, coverage=(), unresolved_gap_count=0
    )
    assert result.supporting_count == 0
    assert result.qualifying_count == 1
    assert result.claim_support_observed is False
    assert result.claim_established is False
    assert result.assessed_after_analysis is True
    assert result.admitted_source_ids == (admission.source_results[0].source_id,)
    assert any("qualifications" in note for note in result.limitations)
    assert any("disabled" in note for note in result.limitations)


def test_post_analysis_rejects_foreign_admitted_record(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    source = admission.source_results[0]
    assert source.evidence_record is not None
    forged = source.model_copy(
        update={"evidence_record": source.evidence_record.model_copy(update={"run_id": uuid4()})}
    )
    with pytest.raises(ValueError, match="run"):
        build_v2_post_analysis_assessment(
            admission_result=admission.model_copy(update={"source_results": (forged,)}),
            coverage=(),
            unresolved_gap_count=0,
        )


def test_missing_coverage_is_not_evidence_sufficiency(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    result = build_v2_post_analysis_assessment(
        admission_result=admission,
        coverage=(
            V2ClaimCoverageAssessment(
                dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
                claim_component="The universal claim",
                coverage_state=V2ClaimCoverageState.MISSING,
                evidence_summary="No estimates address this component.",
            ),
        ),
        unresolved_gap_count=0,
    )
    assert any("coverage remains limited" in note for note in result.limitations)


def test_final_release_binds_post_analysis_counts_and_preserves_legacy_json(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    continuation = _continuation(admission.run_id)
    synthesis = build_v2_synthesis_output(
        synthesis_input=build_v2_synthesizer_input(admission, continuation), created_at=NOW
    )
    output = build_v2_final_research_output(
        admission_result=admission, continuation=continuation, synthesis=synthesis, created_at=NOW
    )
    assert output.release_validation.valid
    assert output.post_analysis_assessment is not None
    rendered = render_v2_final_output(output)
    assert "Evidence assessment after source analysis" in rendered
    assert "Support-directed Findings" in rendered
    tampered = output.model_dump(mode="python")
    tampered["post_analysis_assessment"] = output.post_analysis_assessment.model_copy(
        update={"supporting_count": 1, "qualifying_count": 0, "claim_support_observed": True}
    )
    records = tuple(s.evidence_record for s in admission.source_results if s.evidence_record)
    validation = validate_v2_final_release(
        synthesis=synthesis,
        ledger_records=records,
        admission_result=admission,
        continuation=continuation,
        output_fields=tampered,
        validated_at=NOW,
    )
    assert validation.valid is False
    assert validation.rendered_output_hash is None
    assert any(e.location == "post_analysis_assessment" for e in validation.errors)
    from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run
    from test_v2_phase11_final_output import _synthesis

    legacy_path = tmp_path / "legacy"
    legacy_path.mkdir()
    _, historical_reviewer = _run(legacy_path, Phase10Provider([_approved()]))
    legacy = build_v2_final_research_output(
        reviewer_result=historical_reviewer,
        continuation=_continuation(historical_reviewer.run_id),
        synthesis=_synthesis(historical_reviewer),
        created_at=NOW,
    )
    assert legacy.post_analysis_assessment is None
    assert "post_analysis_assessment" not in legacy.model_dump()
    assert "post_analysis_assessment" not in legacy.model_dump_json()
    assert "Evidence assessment after source analysis" not in render_v2_final_output(legacy)


@pytest.mark.parametrize(
    ("coverage_state", "gap_count", "expected"),
    [
        (V2ClaimCoverageState.PARTIAL, 2, "incomplete_coverage"),
        (V2ClaimCoverageState.MISSING, 0, "incomplete_coverage"),
        (V2ClaimCoverageState.COVERED, 1, "incomplete_coverage"),
        (V2ClaimCoverageState.COVERED, 0, "limited_evidence"),
    ],
)
def test_terminal_outcome_uses_post_analysis_evidence(
    tmp_path: Path, coverage_state: V2ClaimCoverageState, gap_count: int, expected: str
) -> None:
    admission = _admission(tmp_path)
    assessment = build_v2_post_analysis_assessment(
        admission_result=admission,
        coverage=(
            V2ClaimCoverageAssessment(
                dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
                claim_component="ALPR demographic outcomes",
                coverage_state=coverage_state,
                evidence_summary="A scoped observation, not proof of the claim.",
            ),
        ),
        unresolved_gap_count=gap_count,
    )
    assert assessment.search_outcome == expected
    assert assessment.claim_established is False
    assert assessment.policy_identity == "researchassistant-v2-post-analysis-evidence-v2"


def test_terminal_outcome_does_not_close_unknown_coverage(tmp_path: Path) -> None:
    assessment = build_v2_post_analysis_assessment(
        admission_result=_admission(tmp_path), coverage=(), unresolved_gap_count=0
    )
    assert assessment.search_outcome == "incomplete_coverage"
    assert assessment.coverage_incomplete is True


def test_terminal_analysis_complete_still_does_not_establish_claim(tmp_path: Path) -> None:
    assessment = build_v2_post_analysis_assessment(
        admission_result=_admission(tmp_path, V2EvidenceRelationship.SUPPORTS),
        coverage=(
            V2ClaimCoverageAssessment(
                dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
                claim_component="ALPR demographic outcomes",
                coverage_state=V2ClaimCoverageState.COVERED,
                evidence_summary="The selected observation addresses this dimension.",
            ),
        ),
        unresolved_gap_count=0,
    )
    assert assessment.search_outcome == "analysis_complete"
    assert assessment.claim_established is False


def test_legacy_assessment_json_and_render_remain_unchanged(tmp_path: Path) -> None:
    import hashlib

    from agents.v2_final_output import reconstruct_saved_v2_final_output
    from researchassistant.contracts.models import V2PostAnalysisAssessment

    admission = _admission(tmp_path)
    legacy = build_v2_post_analysis_assessment(
        admission_result=admission,
        coverage=(),
        unresolved_gap_count=0,
        policy_identity="researchassistant-v2-post-analysis-evidence-v1",
    )
    encoded = legacy.model_dump_json()
    assert "search_outcome" not in encoded
    assert "coverage_incomplete" not in encoded
    assert V2PostAnalysisAssessment.model_validate_json(encoded).model_dump_json() == encoded
    continuation = _continuation(admission.run_id)
    synthesis = build_v2_synthesis_output(
        synthesis_input=build_v2_synthesizer_input(admission, continuation), created_at=NOW
    )
    output = build_v2_final_research_output(
        admission_result=admission, continuation=continuation, synthesis=synthesis, created_at=NOW
    )
    historical = output.model_copy(update={"post_analysis_assessment": legacy})
    assert "Final research outcome:" not in render_v2_final_output(historical)
    historical = historical.model_copy(
        update={
            "release_validation": historical.release_validation.model_copy(
                update={
                    "rendered_output_hash": hashlib.sha256(
                        render_v2_final_output(historical).encode("utf-8")
                    ).hexdigest()
                }
            )
        }
    )
    rebuilt_legacy = reconstruct_saved_v2_final_output(
        saved_output=historical, evidence_result=admission, continuation=continuation
    )
    assert rebuilt_legacy.release_validation.valid
    assert rebuilt_legacy.post_analysis_assessment == legacy
    assert render_v2_final_output(rebuilt_legacy) == render_v2_final_output(historical)
    fields = output.model_dump(mode="python")
    fields["post_analysis_assessment"] = legacy
    fresh_validation = validate_v2_final_release(
        synthesis=synthesis,
        ledger_records=tuple(
            s.evidence_record for s in admission.source_results if s.evidence_record
        ),
        admission_result=admission,
        continuation=continuation,
        output_fields=fields,
        validated_at=NOW,
    )
    assert fresh_validation.valid is False
    assert any(error.location == "post_analysis_assessment" for error in fresh_validation.errors)
    with pytest.raises(TypeError, match="post_analysis_policy_identity"):
        build_v2_final_research_output(
            admission_result=admission,
            continuation=continuation,
            synthesis=synthesis,
            created_at=NOW,
            post_analysis_policy_identity="researchassistant-v2-post-analysis-evidence-v1",
        )
    with pytest.raises(ValueError, match="released hash"):
        reconstruct_saved_v2_final_output(
            saved_output=historical.model_copy(update={"exact_claim": "A forged claim"}),
            evidence_result=admission,
            continuation=continuation,
        )


def test_release_rejects_forged_complete_terminal_status(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    continuation = _continuation(admission.run_id)
    synthesis = build_v2_synthesis_output(
        synthesis_input=build_v2_synthesizer_input(admission, continuation), created_at=NOW
    )
    output = build_v2_final_research_output(
        admission_result=admission, continuation=continuation, synthesis=synthesis, created_at=NOW
    )
    assessment = output.post_analysis_assessment
    assert assessment is not None
    tampered = output.model_dump(mode="python")
    tampered["post_analysis_assessment"] = assessment.model_copy(
        update={"search_outcome": "analysis_complete", "coverage_incomplete": False}
    )
    validation = validate_v2_final_release(
        synthesis=synthesis,
        ledger_records=tuple(
            s.evidence_record for s in admission.source_results if s.evidence_record
        ),
        admission_result=admission,
        continuation=continuation,
        output_fields=tampered,
        validated_at=NOW,
    )
    assert validation.valid is False
    assert any(error.location == "post_analysis_assessment" for error in validation.errors)


def test_fresh_fingerprint_freezes_probe_and_post_analysis_policies() -> None:
    from researchassistant.research.v2_orchestrator import _semantic_policy_payload

    semantic = _semantic_policy_payload()
    assert (
        semantic["acquisition_probe_policy"] == "researchassistant-v2-phase-5-acquisition-probe-v2"
    )
    assert (
        semantic["post_analysis_evidence_policy"]
        == "researchassistant-v2-post-analysis-evidence-v2"
    )


def test_final_model_binds_terminal_status_to_coverage(tmp_path: Path) -> None:
    from researchassistant.contracts.models import V2FinalResearchOutput

    admission = _admission(tmp_path, V2EvidenceRelationship.SUPPORTS)
    continuation = _continuation(admission.run_id)
    synthesis = build_v2_synthesis_output(
        synthesis_input=build_v2_synthesizer_input(admission, continuation), created_at=NOW
    )
    output = build_v2_final_research_output(
        admission_result=admission, continuation=continuation, synthesis=synthesis, created_at=NOW
    )
    assessment = output.post_analysis_assessment
    assert assessment is not None
    forged = output.model_dump(mode="python")
    forged["post_analysis_assessment"] = assessment.model_copy(
        update={"search_outcome": "analysis_complete", "coverage_incomplete": False}
    ).model_dump(mode="python")
    with pytest.raises(ValueError, match="coverage must match"):
        V2FinalResearchOutput.model_validate(forged)
    for field in ("partial_coverage_count", "unavailable_coverage_count"):
        forged["post_analysis_assessment"] = assessment.model_copy(update={field: 1}).model_dump(
            mode="python"
        )
        with pytest.raises(ValueError, match="coverage counts must match"):
            V2FinalResearchOutput.model_validate(forged)
