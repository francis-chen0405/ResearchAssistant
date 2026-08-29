from __future__ import annotations

from decimal import Decimal
from pathlib import Path

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
)
from brief_export import BriefExportFormat, export_released_brief
from frontend.api import ApiRuntime, create_app
from models import (
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
    V2ResultSourceStatus,
    V2UnresolvedMaterialGap,
)
from providers.llm import LLMProviderCapabilities, LLMRequest, LLMStage
from store import insert_v2_artifact, read_v2_artifact


def _continuation(
    run_id: object,
    stop_code: V2AdaptiveStopCode = V2AdaptiveStopCode.ROUND_ONE_COMPLETE,
) -> V2AdaptiveContinuationResult:
    return V2AdaptiveContinuationResult(
        run_id=run_id,
        rounds=(),
        merged_survivors=V2MergedSurvivorPool(run_id=run_id, sources=()),
        stopping_decision=V2AdaptiveStoppingDecision(
            run_id=run_id,
            completed_rounds=1,
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
