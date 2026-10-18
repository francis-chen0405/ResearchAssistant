"""Fresh wording reflects actual admission; recorded release rendering stays exact."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from test_v2_phase11_final_output import _continuation
from test_v2_post_analysis import NOW, _admission

from researchassistant.agents.v2_final_output import (
    _build_v2_final_research_output,
    build_v2_synthesizer_input,
    reconstruct_saved_v2_final_output,
    render_v2_final_output,
)
from researchassistant.evidence.renderer import (
    LEGACY_VALIDATOR_CONFIG_VERSION,
    VALIDATOR_CONFIG_VERSION,
    render_brief,
    validate_final_release,
)
from researchassistant.evidence.synthesizer import build_v2_synthesis_output


def test_admitted_warning_is_versioned_without_changing_old_rendered_hashes(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    continuation = _continuation(admission.run_id)
    synthesis = build_v2_synthesis_output(
        synthesis_input=build_v2_synthesizer_input(admission, continuation), created_at=NOW
    )
    records = tuple(
        source.evidence_record for source in admission.source_results if source.evidence_record
    )
    claim = admission.analyst_result.input.exact_claim
    old = render_brief(
        synthesis,
        records,
        authoritative_claim=claim,
        validator_config_version=LEGACY_VALIDATOR_CONFIG_VERSION,
    )
    fresh = render_brief(synthesis, records, authoritative_claim=claim)
    assert "no admitted opposing evidence" in fresh
    assert "Reviewer-approved" not in fresh
    assert old.replace("Reviewer-approved", "admitted") == fresh
    for version, rendered in (
        (LEGACY_VALIDATOR_CONFIG_VERSION, old),
        (VALIDATOR_CONFIG_VERSION, fresh),
    ):
        validation = validate_final_release(
            synthesis,
            records,
            authoritative_claim=claim,
            validated_at=NOW,
            validator_config_version=version,
        )
        assert validation.valid
        assert validation.rendered_brief_hash == sha256(rendered.encode()).hexdigest()
    saved = _build_v2_final_research_output(
        admission_result=admission,
        continuation=continuation,
        synthesis=synthesis,
        created_at=NOW,
        evidence_validator_version=LEGACY_VALIDATOR_CONFIG_VERSION,
    )
    original = saved.model_dump_json()
    rebuilt = reconstruct_saved_v2_final_output(
        saved_output=saved,
        evidence_result=admission,
        continuation=continuation,
    )
    assert (
        rebuilt.release_validation.evidence_validation
        == saved.release_validation.evidence_validation
    )
    assert render_v2_final_output(rebuilt) == render_v2_final_output(saved)
    assert saved.model_dump_json() == original
