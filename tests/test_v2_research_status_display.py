from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from test_v2_phase10_reviewer_ledger import NOW, Phase10Provider, _approved, _run
from test_v2_phase11_final_output import _continuation, _synthesis

from agents.v2_adaptive_search import (
    V2AdaptiveContinuationResult,
    V2AdaptiveRoundExecution,
    V2AdaptiveRoundStatus,
    V2AdaptiveStopCode,
    V2AdaptiveStoppingDecision,
    V2MergedSurvivorPool,
)
from agents.v2_final_output import build_v2_final_research_output, render_v2_final_output
from frontend.api import _build_research_status_display
from models import (
    ResearchDirection,
    ResearchDirections,
    V2ClaimCoverageAssessment,
    V2ClaimCoverageDimension,
    V2ClaimCoverageState,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2GapBudgetState,
    V2GapCoverageReconciliation,
    V2GapCoverageRecord,
    V2GapCoverageState,
    V2GapSearchDirection,
    V2MaterialGap,
    V2RoundFourDecisionCode,
    V2RoundFourGovernorDecision,
    V2RoundFourReservation,
)

DIRECTIONS = ResearchDirections(support_enabled=True, challenge_enabled=False)


def _coverage() -> V2ClaimCoverageAssessment:
    return V2ClaimCoverageAssessment(
        dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
        claim_component="the exact claim effect",
        coverage_state=V2ClaimCoverageState.PARTIAL,
        evidence_summary="Available studies do not settle the exact effect.",
    )


def _gap(gap_id: str, missing_evidence: str) -> V2MaterialGap:
    return V2MaterialGap(
        gap_id=gap_id,
        direction=ResearchDirection.SUPPORT,
        missing_evidence=missing_evidence,
        rationale="The available evidence does not resolve this dimension.",
    )


def _gap_analysis(
    run_id: UUID,
    *,
    material_gaps: tuple[V2MaterialGap, ...],
    continue_research: bool,
    stop_reason: str | None,
) -> V2GapAnalysisOutput:
    directions = DIRECTIONS
    gap_input = V2GapAnalysisInput(
        run_id=run_id,
        exact_claim="The regional program reduces the outcome.",
        directions=directions,
        completed_round=3,
        attempted_queries=(),
        surviving_sources=(),
        probe_passages=(),
        source_families=(),
        discovered_terms=(),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=(),
        remaining_budget=V2GapBudgetState(model_calls_remaining=4),
        policy_identity="researchassistant-v2-phase-6-gap-analysis-v1",
    )
    search_directions = tuple(
        V2GapSearchDirection(
            gap_id=gap.gap_id,
            direction=gap.direction,
            missing_evidence=gap.missing_evidence,
            search_focus="independent evidence",
        )
        for gap in material_gaps
    )
    result = V2GapAnalysisResult(
        run_id=run_id,
        directions=directions,
        coverage_summary="The exact effect remains only partially covered.",
        claim_coverage_map=(_coverage(),),
        material_gaps=material_gaps,
        continue_research=continue_research,
        stop_reason=stop_reason,
        new_search_directions=search_directions,
        discovered_terms=("independent evaluation",) if continue_research else (),
        analyzed_at=NOW,
    )
    return V2GapAnalysisOutput(
        run_id=run_id,
        input=gap_input,
        state=V2GapAnalysisState.COMPLETED,
        result=result,
        attempts=(),
        stop_adaptive_continuation=not continue_research,
        completed_at=NOW,
    )


def _round_four_reservation() -> V2RoundFourReservation:
    return V2RoundFourReservation(
        protected_downstream_calls=1,
        protected_downstream_tokens=0,
        protected_downstream_cost_usd="0",
        gap_attempt_calls=1,
        search_agent_calls=1,
        scout_calls=0,
        provider_search_calls=1,
        acquisition_cluster_capacity=4,
        optional_calls=2,
        optional_tokens=0,
        optional_cost_usd="0",
        available_calls=3,
    )


def test_historical_no_material_gaps_projects_no_productive_search_without_mutating_brief(
    tmp_path: Path,
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    run_id = reviewer_result.run_id
    continuation = _continuation(
        run_id,
        V2AdaptiveStopCode.ROUND_THREE_COMPLETE,
        completed_rounds=3,
    )
    old_reconciliation = V2GapCoverageReconciliation(
        run_id=run_id,
        post_round_three_gap_artifact_key="post-phase-13-gap-analysis-after-round-3-v1",
        round_four_attempted=False,
        records=(),
        claim_coverage_map=(_coverage(),),
        completed_at=NOW,
    )
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=continuation,
        gap_reconciliation=old_reconciliation,
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )
    post_round_three_gap = _gap_analysis(
        run_id,
        material_gaps=(),
        continue_research=False,
        stop_reason="Another support search would overlap; the estimate remains incomplete.",
    )
    old_governor = V2RoundFourGovernorDecision(
        run_id=run_id,
        authorized=False,
        reason_code=V2RoundFourDecisionCode.NO_MATERIAL_GAPS,
        explanation="No material claim-coverage gap remains.",
        reservation=None,
        decided_at=NOW,
    )
    rendered_before = render_v2_final_output(output)
    hash_before = output.release_validation.rendered_output_hash
    payload_before = output.model_dump_json()

    status = _build_research_status_display(
        output,
        gap_analysis=post_round_three_gap,
        governor_decision=old_governor,
    )

    assert status.reason_code == "no_productive_search"
    assert "overlap" in status.explanation
    assert "coverage may remain partial or unavailable" in status.explanation.lower()
    assert status.actionable_gap_count == 0
    assert status.partial_coverage_count == 1
    assert status.unavailable_coverage_count == 0
    assert status.source == "persisted_governor"
    assert output.stopping.reason.value == "hard_round_limit"
    assert render_v2_final_output(output) == rendered_before
    assert output.release_validation.rendered_output_hash == hash_before
    assert output.model_dump_json() == payload_before


def test_completed_round_four_status_uses_reconciled_remaining_gaps_not_preauthorization_count(
    tmp_path: Path,
) -> None:
    _path, reviewer_result = _run(tmp_path, Phase10Provider([_approved()]))
    run_id = reviewer_result.run_id
    gaps = (
        _gap("gap-covered", "Independent outcome evidence."),
        _gap("gap-remaining", "A second independent outcome estimate."),
    )
    post_round_three_gap = _gap_analysis(
        run_id,
        material_gaps=gaps,
        continue_research=True,
        stop_reason=None,
    )
    authorized_decision = V2RoundFourGovernorDecision(
        run_id=run_id,
        authorized=True,
        reason_code=V2RoundFourDecisionCode.AUTHORIZED,
        explanation="Round 4 was authorized as one narrow claim-coverage continuation.",
        reservation=_round_four_reservation(),
        decided_at=NOW,
    )
    reconciliation = V2GapCoverageReconciliation(
        run_id=run_id,
        post_round_three_gap_artifact_key="post-phase-13-gap-analysis-after-round-3-v1",
        round_four_attempted=True,
        records=(
            V2GapCoverageRecord(
                gap=gaps[0],
                state=V2GapCoverageState.COVERED,
                source_id=uuid4(),
                query_id=uuid4(),
                ledger_claim_id=uuid4(),
            ),
            V2GapCoverageRecord(gap=gaps[1], state=V2GapCoverageState.UNRESOLVED),
        ),
        claim_coverage_map=(_coverage(),),
        round_four_governor_decision=authorized_decision,
        completed_at=NOW,
    )
    round_four = V2AdaptiveRoundExecution(
        run_id=run_id,
        round_number=4,
        targeted_gap_ids=("gap-covered", "gap-remaining"),
        status=V2AdaptiveRoundStatus.COMPLETED,
        planned_query_count=2,
        completed_query_count=2,
        failed_query_count=0,
        new_source_count=2,
        duplicate_source_count=0,
        survivor_additions=2,
        completed_at=NOW,
    )
    continuation = V2AdaptiveContinuationResult(
        run_id=run_id,
        rounds=(round_four,),
        merged_survivors=V2MergedSurvivorPool(run_id=run_id, sources=()),
        stopping_decision=V2AdaptiveStoppingDecision(
            run_id=run_id,
            completed_rounds=4,
            stop_code=V2AdaptiveStopCode.ROUND_FOUR_COMPLETE,
            stopping_reason="Targeted Round 4 completed; no further research round is permitted.",
            decided_at=NOW,
        ),
        completed_at=NOW,
    )
    output = build_v2_final_research_output(
        reviewer_result=reviewer_result,
        continuation=continuation,
        gap_reconciliation=reconciliation,
        synthesis=_synthesis(reviewer_result),
        created_at=NOW,
    )

    status = _build_research_status_display(
        output,
        gap_analysis=post_round_three_gap,
        governor_decision=authorized_decision,
    )

    assert len(post_round_three_gap.result.material_gaps) == 2
    assert len(output.unresolved_material_gaps) == 1
    assert status.actionable_gap_count == 1
    assert status.reason_code == output.stopping.reason.value
    assert status.explanation == output.stopping.explanation
    assert status.reason_code != "authorized"
    assert status.source == "final_output"
    assert "authorized as one narrow" not in status.explanation
