from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from test_v2_phase9_luna_evidence_analyst import _routing
from test_v2_phase10_reviewer_ledger import NOW, Phase10Provider, _approved, _run

from agents.synthesizer import _item_from_ledger
from agents.v2_adaptive_search import (
    V2AdaptiveContinuationResult,
    V2AdaptiveStopCode,
    V2AdaptiveStoppingDecision,
    V2MergedSurvivorPool,
)
from agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    _result_sources,
    build_v2_final_research_output,
    build_v2_synthesizer_input,
    render_v2_final_output,
    run_v2_final_research_output,
    validate_v2_final_release,
)
from frontend.api import ApiRuntime, create_app
from providers.llm import LLMProviderCapabilities, LLMRequest, LLMStage
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_evidence import V2ReviewerLedgerState
from researchassistant.contracts.models import (
    ModelUsageMetadata,
    ResearchDirection,
    ResearchDirections,
    Stance,
    SynthesisItem,
    SynthesisOutput,
    SynthesisSection,
    V2ClaimCoverageAssessment,
    V2ClaimCoverageDimension,
    V2ClaimCoverageState,
    V2DeepAnalysisBudgetReason,
    V2FinalResearchOutput,
    V2GapCoverageReconciliation,
    V2ResultSourceStatus,
    V2RoundFourDecisionCode,
    V2RoundFourGovernorDecision,
    V2UnresolvedMaterialGap,
)
from researchassistant.evidence.brief_export import BriefExportFormat, export_released_brief
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact


def _continuation(
    run_id: object,
    stop_code: V2AdaptiveStopCode = V2AdaptiveStopCode.ROUND_ONE_COMPLETE,
    completed_rounds: int = 1,
) -> V2AdaptiveContinuationResult:
    return V2AdaptiveContinuationResult(
        run_id=run_id,
        rounds=(),
        merged_survivors=V2MergedSurvivorPool(run_id=run_id, sources=()),
        stopping_decision=V2AdaptiveStoppingDecision(
            run_id=run_id,
            completed_rounds=completed_rounds,
            stop_code=stop_code,
            stopping_reason="The persisted research governor selected this stopping point.",
            decided_at=NOW,
        ),
        completed_at=NOW,
    )


def _synthesis(result: object, *, section_type: str = "supporting") -> SynthesisOutput:
    record = result.source_results[0].ledger_record
    assert record is not None
    return SynthesisOutput(
        run_id=result.run_id,
        synthesizer_prompt_version="phase11-test",
        synthesizer_model_name="mimo-v2.5-pro",
        created_at=NOW,
        sections=(SynthesisSection(section_type=section_type, items=(_item_from_ledger(record),)),),
    )


class _SynthesizerProvider:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> object:
        self.requests.append(request)
        assert request.stage is LLMStage.SYNTHESIZER
        items = request.input_artifact.approved_ledger_items
        sections = tuple(
            SynthesisSection(
                section_type=(
                    "supporting" if item.direction is ResearchDirection.SUPPORT else "opposing"
                ),
                items=(
                    SynthesisItem(
                        connective_template_id=(
                            "partial_entailment"
                            if item.entailment.value == "Partial"
                            else "weak_entailment"
                            if item.entailment.value == "Weak"
                            else "scope_qualification"
                            if item.placement.value == "qualified_only"
                            else "supporting_evidence"
                            if item.direction is ResearchDirection.SUPPORT
                            else "opposing_evidence"
                        ),
                        ledger_claim_id=item.ledger_claim_id,
                        reviewer_approval_id=item.reviewer_approval_id,
                        stance=item.stance,
                        placement=item.placement,
                        entailment=item.entailment,
                        approved_factual_statement=item.approved_factual_statement,
                    ),
                ),
            )
            for item in items
        )
        return SynthesisOutput(
            run_id=request.run_id,
            synthesizer_prompt_version=request.prompt.version,
            synthesizer_model_name="mimo-v2.5-pro",
            created_at=NOW,
            sections=sections,
        )

    def usage_for(
        self, request: LLMRequest, output: object, invocation_record: object
    ) -> ModelUsageMetadata:
        del request, output, invocation_record
        return ModelUsageMetadata(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost_usd=Decimal("0.001"),
        )


def test_support_only_result_discloses_scope_and_never_sends_raw_sources(tmp_path: Path) -> None:
    path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    continuation = _continuation(reviewer_result.run_id)

    synthesis_input = build_v2_synthesizer_input(reviewer_result, continuation)
    assert synthesis_input.directions == ResearchDirections(
        support_enabled=True, challenge_enabled=False
    )
    payload = synthesis_input.model_dump(mode="json")
    assert "approved_claim_text" not in str(payload)
    assert "snapshot_sha256" not in str(payload)

    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=continuation,
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )

    assert output.release_validation.valid
    assert output.recommended_sources[0].status is V2ResultSourceStatus.RECOMMENDED_ANALYZED
    rendered = render_v2_final_output(output)
    assert "Research direction: supporting evidence only" in rendered
    assert "## Challenging Evidence" not in rendered


def test_renderer_does_not_claim_no_gaps_when_coverage_has_unresolved_gaps(tmp_path: Path) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    ).model_copy(
        update={
            "claim_coverage_map": (
                V2ClaimCoverageAssessment(
                    dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
                    claim_component="the exact claim",
                    coverage_state=V2ClaimCoverageState.PARTIAL,
                    evidence_summary="Evidence is incomplete.",
                ),
            ),
            "unresolved_material_gaps": (
                V2UnresolvedMaterialGap(
                    gap_id="gap-coverage",
                    direction=ResearchDirection.SUPPORT,
                    missing_evidence="A directly relevant study remains missing.",
                    assessed_after_round=3,
                ),
            ),
        }
    )

    rendered = render_v2_final_output(output)

    assert "A directly relevant study remains missing." in rendered
    assert "No unresolved material gaps were recorded." not in rendered


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("source_url", "https://substituted.example/article"),
        ("title", "Substituted source title"),
        ("source_type", "Substituted source type"),
        ("publication_date", "2099-12-31"),
        ("discovery_providers", (DiscoveryProvider.PUBMED,)),
        ("discovery_round", 4),
    ),
)
def test_final_release_rejects_substituted_recommended_source_metadata(
    tmp_path: Path, field: str, replacement: object
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    continuation = _continuation(reviewer_result.run_id)
    synthesis = _synthesis(reviewer_result)
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=continuation,
        synthesis=synthesis,
        created_at=NOW,
    )
    assert output.release_validation.valid
    altered_source = output.all_surviving_sources[0].model_copy(update={field: replacement})
    output_fields = dict(output)
    output_fields["recommended_sources"] = (altered_source,)

    validation = validate_v2_final_release(
        synthesis=synthesis,
        ledger_records=tuple(
            source.ledger_record
            for source in reviewer_result.source_results
            if source.ledger_record is not None
        ),
        reviewer_result=reviewer_result,
        continuation=continuation,
        output_fields=output_fields,
        validated_at=NOW,
    )

    assert not validation.valid
    assert any(error.location.startswith("recommended_sources") for error in validation.errors), (
        validation.errors
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("source_url", "https://substituted.example/article"),
        ("title", "Substituted source title"),
    ),
)
def test_final_release_rejects_substituted_all_survivor_metadata(
    tmp_path: Path, field: str, replacement: object
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    continuation = _continuation(reviewer_result.run_id)
    synthesis = _synthesis(reviewer_result)
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=continuation,
        synthesis=synthesis,
        created_at=NOW,
    )
    altered_source = output.all_surviving_sources[0].model_copy(update={field: replacement})
    output_fields = dict(output)
    output_fields["all_surviving_sources"] = (altered_source,)

    validation = validate_v2_final_release(
        synthesis=synthesis,
        ledger_records=tuple(
            source.ledger_record
            for source in reviewer_result.source_results
            if source.ledger_record is not None
        ),
        reviewer_result=reviewer_result,
        continuation=continuation,
        output_fields=output_fields,
        validated_at=NOW,
    )

    assert not validation.valid
    assert any(error.location.startswith("all_surviving_sources") for error in validation.errors)


def test_resume_rejects_persisted_source_metadata_substitution(tmp_path: Path) -> None:
    path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    continuation = _continuation(reviewer_result.run_id)
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=continuation,
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )
    altered_source = output.all_surviving_sources[0].model_copy(
        update={"title": "Persisted substituted source title"}
    )
    tampered = output.model_copy(
        update={
            "all_surviving_sources": (altered_source,),
            "recommended_sources": (altered_source,),
        }
    )
    insert_v2_artifact(path, V2_FINAL_OUTPUT_ARTIFACT_KEY, tampered, NOW)

    with pytest.raises(ValueError, match="persisted v2 final output source disclosures"):
        run_v2_final_research_output(
            db_path=path,
            reviewer_result=reviewer_result,
            continuation=continuation,
            llm_provider=_SynthesizerProvider(),
            routing_config=_routing(),
            clock=lambda: NOW,
        )


def test_recommended_source_order_may_differ_from_survivor_order_on_build_and_resume(
    tmp_path: Path,
) -> None:
    path, initial = _run(tmp_path, Phase10Provider([_approved()]))
    original_candidate = initial.analyst_result.input.queue_result.input.survivors[0]
    second_source_id = uuid4()
    second_candidate = original_candidate.model_copy(
        update={
            "source_id": second_source_id,
            "source_family_id": "distinct-source-family",
            "source_url": "https://second.example/article",
            "title": "Second source",
        }
    )
    selection = initial.analyst_result.input.queue_result
    selection_input = selection.input.model_copy(
        update={"survivors": (original_candidate, second_candidate)}
    )
    original_status = selection.source_statuses[0]
    first_status = original_status.model_copy(update={"recommendation_rank": 2, "queue_rank": 2})
    second_status = original_status.model_copy(
        update={
            "source_id": second_source_id,
            "recommendation_rank": 1,
            "queue_rank": 1,
        }
    )
    selection = selection.model_copy(
        update={
            "input": selection_input,
            "recommended_source_ids": (second_source_id, original_candidate.source_id),
            "source_statuses": (second_status, first_status),
            "priority_source_ids": (second_source_id, original_candidate.source_id),
            "queued_source_ids": (second_source_id, original_candidate.source_id),
        }
    )
    analyst_input = initial.analyst_result.input.model_copy(update={"queue_result": selection})
    analyst_result = initial.analyst_result.model_copy(update={"input": analyst_input})
    original_result = initial.source_results[0]
    second_result = original_result.model_copy(
        update={
            "source_id": second_source_id,
            "state": V2ReviewerLedgerState.NOT_QUEUED,
            "provenance": original_result.provenance.model_copy(
                update={
                    "source_id": second_source_id,
                    "source_family_id": "distinct-source-family",
                    "recommended": True,
                }
            ),
            "review_results": (),
            "ledger_record": None,
        }
    )
    reviewer_result = initial.model_copy(
        update={
            "analyst_result": analyst_result,
            "source_results": (original_result, second_result),
        }
    )
    continuation = _continuation(reviewer_result.run_id)
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=continuation,
        synthesis=_synthesis(initial),
        created_at=NOW,
    )

    assert output.release_validation.valid
    assert tuple(source.source_id for source in output.all_surviving_sources) == (
        original_candidate.source_id,
        second_source_id,
    )
    assert tuple(source.source_id for source in output.recommended_sources) == (
        second_source_id,
        original_candidate.source_id,
    )
    insert_v2_artifact(path, V2_FINAL_OUTPUT_ARTIFACT_KEY, output, NOW)
    resumed = run_v2_final_research_output(
        db_path=path,
        reviewer_result=reviewer_result,
        continuation=continuation,
        llm_provider=_SynthesizerProvider(),
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert resumed.resumed
    assert resumed.final_output.recommended_sources == output.recommended_sources


def test_phase11_invokes_mimo_and_persists_restartable_output(tmp_path: Path) -> None:
    path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    provider = _SynthesizerProvider()
    first = run_v2_final_research_output(
        db_path=path,
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert first.final_output.release_validation.valid
    assert len(provider.requests) == 1
    assert provider.requests[0].input_artifact.__class__.__name__ == "V2SynthesizerInput"
    assert read_v2_artifact(path, reviewer_result.run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY)
    resumed = run_v2_final_research_output(
        db_path=path,
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    assert resumed.resumed
    assert len(provider.requests) == 1


def test_v2_export_and_api_schema_use_the_persisted_final_output(tmp_path: Path) -> None:
    path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )
    insert_v2_artifact(path, V2_FINAL_OUTPUT_ARTIFACT_KEY, output, NOW)

    exported = export_released_brief(
        path,
        str(reviewer_result.run_id),
        tmp_path / "v2-result.md",
        BriefExportFormat.MARKDOWN,
        generated_at=NOW,
    )
    assert exported.output_path.endswith("v2-result.md")
    assert "Research direction: supporting evidence only" in (tmp_path / "v2-result.md").read_text()

    class _Controller:
        def has_active_runs(self) -> bool:
            return False

    class _Services:
        def owns_running_process(self) -> bool:
            return False

    from fastapi.testclient import TestClient

    app = create_app(
        ApiRuntime(controller=_Controller(), services=_Services(), environment={}),
        load_keychain_on_start=False,
        allowed_hosts=("testserver",),
        allowed_origins=("http://127.0.0.1:3000",),
    )
    with TestClient(app) as client:
        response = client.get(
            f"/api/research/{reviewer_result.run_id}/v2-result", params={"db_path": path}
        )
    assert response.status_code == 200
    assert response.json()["directions"] == {
        "support_enabled": True,
        "challenge_enabled": False,
    }
    assert response.json()["all_surviving_sources"][0]["status"] == "recommended_analyzed"

    with TestClient(app) as client:
        evidence = client.get(
            f"/api/research/{reviewer_result.run_id}/v2-evidence", params={"db_path": path}
        )
    assert evidence.status_code == 200
    assert evidence.json()["items"][0]["validation_status"] == "admitted"
    assert evidence.json()["items"][0]["quote_passage"]


@pytest.mark.parametrize(
    ("directions", "section_type"),
    [
        (ResearchDirections(support_enabled=True, challenge_enabled=False), "supporting"),
        (ResearchDirections(support_enabled=False, challenge_enabled=True), "opposing"),
        (ResearchDirections(support_enabled=True, challenge_enabled=True), "supporting"),
    ],
)
def test_direction_configurations_are_enforced(
    tmp_path: Path,
    directions: ResearchDirections,
    section_type: str,
) -> None:
    _, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    record = reviewer_result.source_results[0].ledger_record
    assert record is not None
    direction = (
        ResearchDirection.SUPPORT if directions.support_enabled else ResearchDirection.CHALLENGE
    )
    stance = "supporting" if direction is ResearchDirection.SUPPORT else "opposing"
    record = record.model_copy(
        update={"stance": Stance.SUPPORTING if stance == "supporting" else Stance.OPPOSING}
    )
    source = reviewer_result.source_results[0].model_copy(
        update={
            "direction": direction,
            "provenance": reviewer_result.source_results[0].provenance.model_copy(
                update={"research_direction": direction}
            ),
            "ledger_record": record,
        }
    )
    selection_input = reviewer_result.analyst_result.input.queue_result.input.model_copy(
        update={
            "directions": directions,
            "survivors": (
                reviewer_result.analyst_result.input.queue_result.input.survivors[0].model_copy(
                    update={"direction": direction}
                ),
            ),
        }
    )
    queue = reviewer_result.analyst_result.input.queue_result.model_copy(
        update={
            "input": selection_input,
            "source_statuses": (
                reviewer_result.analyst_result.input.queue_result.source_statuses[0].model_copy(
                    update={"direction": direction}
                ),
            ),
        }
    )
    analyst_input = reviewer_result.analyst_result.input.model_copy(
        update={"queue_result": queue, "directions": directions}
    )
    transformed = reviewer_result.model_copy(
        update={
            "analyst_result": reviewer_result.analyst_result.model_copy(
                update={"input": analyst_input}
            ),
            "source_results": (source,),
        }
    )
    synthesis = SynthesisOutput(
        run_id=transformed.run_id,
        synthesizer_prompt_version="phase11-test",
        synthesizer_model_name="mimo-v2.5-pro",
        created_at=NOW,
        sections=(SynthesisSection(section_type=section_type, items=(_item_from_ledger(record),)),),
    )

    output = build_v2_final_research_output(
        reviewer_result=transformed,
        continuation=_continuation(transformed.run_id),
        synthesis=synthesis,
        created_at=NOW,
    )

    assert output.release_validation.valid
    assert output.directions == directions


@pytest.mark.parametrize(
    ("stop_code", "expected"),
    [
        (V2AdaptiveStopCode.ROUND_ONE_COMPLETE, "sufficient_source_pool"),
        (V2AdaptiveStopCode.NO_NEW_QUERY, "no_useful_new_direction"),
        (V2AdaptiveStopCode.NO_ELIGIBLE_PROVIDER, "provider_eligibility_exhausted"),
        (V2AdaptiveStopCode.BUDGET, "budget"),
        (V2AdaptiveStopCode.ROUND_THREE_COMPLETE, "hard_round_limit"),
        (V2AdaptiveStopCode.GAP_ANALYSIS_DEGRADED, "degraded_gap_search_agent"),
    ],
)
def test_stopping_reasons_are_exposed(
    tmp_path: Path, stop_code: V2AdaptiveStopCode, expected: str
) -> None:
    _, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id, stop_code),
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )
    assert output.stopping.reason.value == expected


def test_post_round_three_stop_disclosure_preserves_partial_coverage(
    tmp_path: Path,
) -> None:
    _, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    run_id = reviewer_result.run_id
    governor = V2RoundFourGovernorDecision(
        run_id=run_id,
        authorized=False,
        reason_code=V2RoundFourDecisionCode.NO_PRODUCTIVE_SEARCH,
        explanation=(
            "Round 4 was not started because no productive new search was identified. "
            "Coverage may remain partial or unavailable."
        ),
        reservation=None,
        decided_at=NOW,
    )
    coverage = V2ClaimCoverageAssessment(
        dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        claim_component="the exact claim",
        coverage_state=V2ClaimCoverageState.PARTIAL,
        evidence_summary="The available evidence does not settle the effect.",
    )
    reconciliation = V2GapCoverageReconciliation(
        run_id=run_id,
        post_round_three_gap_artifact_key="post-phase-13-gap-analysis-after-round-3-v1",
        round_four_attempted=False,
        records=(),
        claim_coverage_map=(coverage,),
        round_four_governor_decision=governor,
        completed_at=NOW,
    )

    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(
            run_id, V2AdaptiveStopCode.ROUND_THREE_COMPLETE, completed_rounds=3
        ),
        gap_reconciliation=reconciliation,
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )
    rendered = render_v2_final_output(output)

    assert output.release_validation.valid
    assert output.stopping.reason.value == "no_productive_new_search"
    assert output.stopping.explanation == governor.explanation
    assert "coverage may remain partial or unavailable" in rendered.lower()
    assert "effect_or_association: partial" in rendered
    assert "hard_round_limit" not in rendered
    assert "No unresolved material gaps were recorded." not in rendered


def test_declined_round_four_override_requires_three_completed_rounds(
    tmp_path: Path,
) -> None:
    _, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    run_id = reviewer_result.run_id
    governor = V2RoundFourGovernorDecision(
        run_id=run_id,
        authorized=False,
        reason_code=V2RoundFourDecisionCode.NO_PRODUCTIVE_SEARCH,
        explanation="No productive new search was identified.",
        reservation=None,
        decided_at=NOW,
    )
    reconciliation = V2GapCoverageReconciliation(
        run_id=run_id,
        post_round_three_gap_artifact_key="post-phase-13-gap-analysis-after-round-3-v1",
        round_four_attempted=False,
        records=(),
        round_four_governor_decision=governor,
        completed_at=NOW,
    )
    continuation = _continuation(run_id, V2AdaptiveStopCode.ROUND_THREE_COMPLETE).model_copy(
        update={
            "stopping_decision": _continuation(
                run_id, V2AdaptiveStopCode.ROUND_THREE_COMPLETE
            ).stopping_decision.model_copy(update={"completed_rounds": 2})
        }
    )

    with pytest.raises(ValueError, match="requires exactly three completed rounds"):
        build_v2_final_research_output(
            reviewer_result=reviewer_result,
            continuation=continuation,
            gap_reconciliation=reconciliation,
            synthesis=_synthesis(reviewer_result),
            created_at=NOW,
        )


def test_historical_final_output_without_round_four_fact_keeps_recorded_rendering(
    tmp_path: Path,
) -> None:
    _, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    run_id = reviewer_result.run_id
    coverage = V2ClaimCoverageAssessment(
        dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        claim_component="the exact claim",
        coverage_state=V2ClaimCoverageState.PARTIAL,
        evidence_summary="The historical coverage map remains partial.",
    )
    old_reconciliation_payload = {
        "run_id": str(run_id),
        "post_round_three_gap_artifact_key": "post-phase-13-gap-analysis-after-round-3-v1",
        "round_four_attempted": False,
        "records": [],
        "claim_coverage_map": [coverage.model_dump(mode="json")],
        "completed_at": NOW.isoformat(),
    }
    old_reconciliation = V2GapCoverageReconciliation.model_validate_json(
        json.dumps(old_reconciliation_payload)
    )
    assert old_reconciliation.round_four_governor_decision is None
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(run_id, V2AdaptiveStopCode.ROUND_THREE_COMPLETE),
        gap_reconciliation=old_reconciliation,
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )
    prior_render = render_v2_final_output(output)
    prior_hash = output.release_validation.rendered_output_hash
    old_payload = output.model_dump(mode="json")
    old_payload["release_validation"]["validator_config_version"] = (
        "researchassistant-v2-post-phase-13-round-four-release-validator-v1"
    )
    historical_output = V2FinalResearchOutput.model_validate(old_payload)

    assert historical_output.stopping.reason.value == "hard_round_limit"
    assert render_v2_final_output(historical_output) == prior_render
    assert historical_output.release_validation.rendered_output_hash == prior_hash


def test_disabled_direction_and_ledger_mismatch_fail_closed(tmp_path: Path) -> None:
    _, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    synthesis = _synthesis(reviewer_result).model_copy(
        update={"sections": (SynthesisSection(section_type="opposing", items=()),)}
    )
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=_continuation(reviewer_result.run_id),
        synthesis=synthesis,
        created_at=NOW,
    )
    assert not output.release_validation.valid
    assert output.release_validation.rendered_output_hash is None


def test_budget_prevented_source_has_explicit_status(tmp_path: Path) -> None:
    _, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    queue = reviewer_result.analyst_result.input.queue_result.model_copy(
        update={
            "source_statuses": (
                reviewer_result.analyst_result.input.queue_result.source_statuses[0].model_copy(
                    update={
                        "queued_for_deep_analysis": False,
                        "queue_rank": None,
                        "budget_prevented_reason": V2DeepAnalysisBudgetReason.COST_RESERVE,
                    }
                ),
            )
        }
    )
    transformed = reviewer_result.model_copy(
        update={
            "analyst_result": reviewer_result.analyst_result.model_copy(
                update={
                    "input": reviewer_result.analyst_result.input.model_copy(
                        update={"queue_result": queue}
                    )
                }
            ),
            "source_results": (
                reviewer_result.source_results[0].model_copy(
                    update={"ledger_record": None, "state": "not_queued", "review_results": ()}
                ),
            ),
        }
    )
    sources = _result_sources(transformed)
    assert sources[0].status is V2ResultSourceStatus.BUDGET_PREVENTED_ANALYSIS
