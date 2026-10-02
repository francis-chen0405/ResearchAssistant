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
from models import (
    V2ClaimCoverageAssessment,
    V2ClaimCoverageDimension,
    V2ClaimCoverageState,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceRelationship,
)


def _admission(tmp_path: Path) -> V2EvidenceAdmissionBatchResult:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=_batch_input(run_id),
        llm_provider=FakeLunaAnalyst([_assessment(relationship=V2EvidenceRelationship.QUALIFIES)]),
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
