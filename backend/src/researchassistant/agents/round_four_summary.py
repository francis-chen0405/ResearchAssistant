"""Post-round search summaries, evidence coverage input and completion facts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

from researchassistant.agents.round_four_handoffs import (
    V2_POST13_GAP_AFTER_ROUND_THREE_KEY as V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_COMPLETION_KEY as V2_POST13_ROUND_FOUR_COMPLETION_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY as V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_POST_PLAN_FACTS_KEY as V2_POST13_ROUND_FOUR_POST_PLAN_FACTS_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2RoundFourPostPlanFacts as V2RoundFourPostPlanFacts,
)
from researchassistant.agents.round_four_handoffs import (
    V2RoundFourRunResult as V2RoundFourRunResult,
)
from researchassistant.agents.round_four_handoffs import (
    _read as _read,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveContinuationResult,
    V2AdaptivePlannedRound,
    V2AdaptiveRoundExecution,
)
from researchassistant.agents.v2_coverage import claim_component_focus
from researchassistant.common.money import nonnegative_difference_usd
from researchassistant.contracts.models import (
    V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
    ResearchDirections,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2ClaimCoverageDimension,
    V2ClaimCoverageFocus,
    V2ClaimCoverageKind,
    V2ClaimCoverageSpecification,
    V2DiscoveryScoutOutput,
    V2GapAcquisitionFailure,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAttemptedQuery,
    V2GapBudgetState,
    V2GapDuplicatePattern,
    V2GapProbePassage,
    V2GapSourceFamily,
    V2GapSurvivingSourceMetadata,
    V2InitialPlannerOutput,
    V2RoundFourGovernorDecision,
)
from researchassistant.evidence.evidence_portfolio import identify_source_family
from researchassistant.storage.store import insert_v2_artifact, insert_v2_artifact_batch

_RowT = TypeVar("_RowT")


def build_post_round_three_gap_input(
    *,
    initial_plan: V2InitialPlannerOutput,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    remaining_budget: V2AdaptiveBudgetState,
    db_path: str,
) -> V2GapAnalysisInput:
    """Build the existing bounded Gap contract from cumulative Round 1–3 artifacts."""
    if len(discovery_outputs) != 3 or len(acquisition_outputs) != 3:
        raise ValueError("post-Round-3 Gap Analysis requires exactly three completed rounds")
    plans = [initial_plan]
    for round_number in (2, 3):
        payload = _read(db_path, initial_plan.run_id, f"phase-7-round-{round_number}-plan")
        if payload is None:
            raise ValueError("post-Round-3 Gap Analysis is missing an adaptive round plan")
        plans.append(V2AdaptivePlannedRound.model_validate_json(payload).plan)
    sources_by_round: dict[int, list[V2GapSurvivingSourceMetadata]] = {1: [], 2: [], 3: []}
    passages_by_round: dict[int, list[V2GapProbePassage]] = {1: [], 2: [], 3: []}
    families_by_id: dict[str, V2GapSourceFamily] = {}
    family_rounds: dict[str, int] = {}
    duplicates: list[V2GapDuplicatePattern] = []
    failures: list[V2GapAcquisitionFailure] = []
    terms: list[str] = []
    for round_number, (discovery, acquisition) in enumerate(
        zip(discovery_outputs, acquisition_outputs, strict=True), start=1
    ):
        items = {item.item_id: item for item in discovery.items}
        clusters = {item.cluster_id: item for item in discovery.clusters}
        acquired = {item.snapshot.snapshot_id: item for item in acquisition.acquisitions}
        for survivor in acquisition.survivors:
            cluster = clusters[survivor.cluster_id]
            representative = min(
                (items[item_id] for item_id in cluster.item_ids),
                key=lambda item: item.provider_rank,
            )
            source = acquired[survivor.snapshot_id]
            family_id = str(identify_source_family(source.snapshot).source_family_id)
            sources_by_round[round_number].append(
                V2GapSurvivingSourceMetadata(
                    source_cluster_id=survivor.cluster_id,
                    direction=survivor.direction,
                    snapshot_id=survivor.snapshot_id,
                    snapshot_sha256=survivor.snapshot_sha256,
                    source_url=source.snapshot.source_url,
                    title=representative.title,
                    source_family_id=family_id,
                    round_number=round_number,
                )
            )
            existing_family = families_by_id.get(family_id)
            family = V2GapSourceFamily(
                family_id=family_id,
                direction=survivor.direction,
                source_cluster_ids=(survivor.cluster_id,),
                discovery_providers=tuple(
                    dict.fromkeys(reference.provider for reference in cluster.provider_references)
                ),
                round_number=round_number,
                round_numbers=(round_number,),
            )
            if existing_family is None:
                families_by_id[family_id] = family
                family_rounds[family_id] = round_number
            else:
                if existing_family.direction is not survivor.direction:
                    raise ValueError("a source family cannot cross research directions")
                families_by_id[family_id] = existing_family.model_copy(
                    update={
                        "source_cluster_ids": tuple(
                            dict.fromkeys(
                                (*existing_family.source_cluster_ids, survivor.cluster_id)
                            )
                        ),
                        "discovery_providers": tuple(
                            dict.fromkeys(
                                (
                                    *existing_family.discovery_providers,
                                    *(
                                        reference.provider
                                        for reference in cluster.provider_references
                                    ),
                                )
                            )
                        ),
                        "round_numbers": tuple(
                            dict.fromkeys((*existing_family.round_numbers, round_number))
                        ),
                    }
                )
            probe = next(
                item for item in acquisition.probes if item.snapshot_id == survivor.snapshot_id
            )
            by_id = {item.passage_id: item for item in probe.passages}
            for passage_id in survivor.passage_ids:
                passage = by_id[passage_id]
                text = passage.text[:1200]
                passages_by_round[round_number].append(
                    V2GapProbePassage(
                        passage_id=passage_id,
                        source_cluster_id=survivor.cluster_id,
                        direction=survivor.direction,
                        text=text,
                        truncated_for_gap_analysis=len(text) < len(passage.text),
                        round_number=round_number,
                    )
                )
        for cluster in discovery.clusters:
            direction = min(
                (items[item_id] for item_id in cluster.item_ids),
                key=lambda item: item.provider_rank,
            ).direction
            if len(cluster.item_ids) > 1:
                duplicates.append(
                    V2GapDuplicatePattern(
                        source_cluster_id=cluster.cluster_id,
                        direction=direction,
                        duplicate_discovery_count=len(cluster.item_ids),
                        pattern="conservatively clustered same-source discovery records",
                        round_number=round_number,
                    )
                )
        for attempt in acquisition.attempts:
            cluster = clusters[attempt.cluster_id]
            direction = min(
                (items[item_id] for item_id in cluster.item_ids),
                key=lambda item: item.provider_rank,
            ).direction
            if not attempt.succeeded:
                failures.append(
                    V2GapAcquisitionFailure(
                        source_cluster_id=attempt.cluster_id,
                        direction=direction,
                        provider=attempt.provider,
                        failure_code=attempt.failure_code or "unspecified_acquisition_failure",
                        round_number=round_number,
                    )
                )
        for item in discovery.items:
            for value in (item.title, item.abstract, item.snippet):
                if value:
                    terms.extend(token for token in value.split() if len(token) >= 4)
    previous_gaps = []
    for key in ("phase-6-gap-analysis", "phase-7-gap-analysis-after-round-2"):
        payload = _read(db_path, initial_plan.run_id, key)
        if payload is not None:
            output = V2GapAnalysisOutput.model_validate_json(payload)
            if output.result is not None:
                previous_gaps.extend(output.result.material_gaps)
    coverage_specification = _claim_coverage_specification(
        initial_plan.raw_claim, initial_plan.directions, initial_plan.claim_coverage_focus
    )
    return V2GapAnalysisInput(
        run_id=initial_plan.run_id,
        exact_claim=initial_plan.raw_claim,
        directions=initial_plan.directions,
        completed_round=3,
        attempted_queries=_representative_queries(plans),
        surviving_sources=_representative_round_rows(sources_by_round, 75),
        probe_passages=_representative_round_rows(passages_by_round, 40),
        source_families=_representative_families(families_by_id, family_rounds, 75),
        discovered_terms=tuple(dict.fromkeys(terms))[:40],
        duplicate_patterns=tuple(duplicates)[:25],
        acquisition_failures=tuple(failures)[:150],
        previous_gaps=tuple(previous_gaps)[:6],
        claim_coverage_focus=coverage_specification.focus,
        claim_coverage_specification=coverage_specification,
        remaining_budget=_gap_budget_after_protection(remaining_budget),
        policy_identity=V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
    )


def _gap_budget_after_protection(budget: V2AdaptiveBudgetState) -> V2GapBudgetState:
    return V2GapBudgetState(
        model_calls_remaining=max(
            0,
            budget.model_calls_remaining - budget.protected_downstream_model_calls,
        ),
        tokens_remaining=(
            None
            if budget.tokens_remaining is None
            else max(0, budget.tokens_remaining - budget.protected_downstream_tokens)
        ),
        cost_remaining_usd=(
            None
            if budget.cost_remaining_usd is None
            else nonnegative_difference_usd(
                budget.cost_remaining_usd,
                budget.protected_downstream_cost_usd,
            )
        ),
    )


def _representative_queries(
    plans: list[V2InitialPlannerOutput | V2AdaptiveRoundPlan],
) -> tuple[V2GapAttemptedQuery, ...]:
    """Retain a deterministic, direction-balanced quota from every completed round."""
    rows_by_round: dict[int, list[V2GapAttemptedQuery]] = {1: [], 2: [], 3: []}
    for round_number, plan in enumerate(plans, start=1):
        searches = getattr(plan, "searches", ())
        rows_by_round[round_number] = [
            V2GapAttemptedQuery(
                query_id=query.query_id,
                direction=query.direction,
                provider=query.provider,
                strategy=query.strategy,
                query_text=query.query_text,
                graph_action=getattr(query, "graph_action", None),
                round_number=round_number,
            )
            for query in searches
        ]
    return _representative_round_rows(rows_by_round, 48)


def _representative_round_rows(
    rows_by_round: dict[int, list[_RowT]], cap: int
) -> tuple[_RowT, ...]:
    """Allocate an even per-round quota before admitting deterministic overflow."""
    if cap < 3:
        raise ValueError("cumulative Round-3 context needs capacity for every completed round")
    quota = cap // 3
    selected: list[_RowT] = []
    leftovers: list[_RowT] = []
    for round_number in (1, 2, 3):
        ordered = _direction_balanced(rows_by_round[round_number])
        selected.extend(ordered[:quota])
        leftovers.extend(ordered[quota:])
    selected.extend(_direction_balanced(leftovers)[: cap - len(selected)])
    return tuple(selected)


def _direction_balanced(rows: list[_RowT]) -> list[_RowT]:
    """Keep enabled-direction evidence from disappearing behind earlier same-lane rows."""
    by_direction: dict[str, list[_RowT]] = {}
    for row in sorted(rows, key=_row_sort_key):
        direction = row.direction.value
        by_direction.setdefault(direction, []).append(row)
    ordered: list[_RowT] = []
    index = 0
    directions = sorted(by_direction)
    while any(index < len(by_direction[direction]) for direction in directions):
        for direction in directions:
            if index < len(by_direction[direction]):
                ordered.append(by_direction[direction][index])
        index += 1
    return ordered


def _row_sort_key(row: _RowT) -> tuple[str, str]:
    return (
        row.direction.value,
        str(
            getattr(
                row,
                "source_cluster_id",
                getattr(row, "passage_id", getattr(row, "query_id", "")),
            )
        ),
    )


def _representative_families(
    families_by_id: dict[str, V2GapSourceFamily], family_rounds: dict[str, int], cap: int
) -> tuple[V2GapSourceFamily, ...]:
    rows_by_round = {1: [], 2: [], 3: []}
    for family_id, family in families_by_id.items():
        rows_by_round[family_rounds[family_id]].append(family)
    return _representative_round_rows(rows_by_round, cap)


def _claim_coverage_specification(
    exact_claim: str,
    directions: ResearchDirections,
    planner_focus: tuple[V2ClaimCoverageFocus, ...] = (),
) -> V2ClaimCoverageSpecification:
    """Return the documented application-owned default without parsing claim wording.

    Exact-claim semantics are intentionally not inferred from substrings.  The always-audited
    effect and evidence-boundary dimensions are stable across empirical claims; a focused-mode
    counterevidence audit is retained as explicitly unavailable rather than omitted.  Planner
    The validated Planner may explicitly add only relevant population or mechanism components;
    it cannot widen this bounded continuation implicitly.
    """
    component_focus = claim_component_focus(exact_claim, planner_focus)
    focus = [
        *component_focus,
        V2ClaimCoverageFocus(
            dimension=V2ClaimCoverageDimension.LIMITATIONS_AND_BOUNDARIES,
            claim_component=(
                "limitations and boundaries of the available evidence for the exact claim"
            ),
            kind=V2ClaimCoverageKind.EVIDENCE_AUDIT,
        ),
        V2ClaimCoverageFocus(
            dimension=V2ClaimCoverageDimension.COUNTEREVIDENCE_OR_ALTERNATIVES,
            claim_component="counterevidence and alternative explanations for the exact claim",
            kind=V2ClaimCoverageKind.EVIDENCE_AUDIT,
            searchable=directions.challenge_enabled,
            unavailable_reason=(
                None
                if directions.challenge_enabled
                else "challenge research direction is disabled by the run controls"
            ),
        ),
        V2ClaimCoverageFocus(
            dimension=V2ClaimCoverageDimension.REPLICATION_OR_GENERALIZABILITY,
            claim_component="replication and generalizability boundaries for the exact claim",
            kind=V2ClaimCoverageKind.EVIDENCE_AUDIT,
        ),
    ]
    return V2ClaimCoverageSpecification(focus=tuple(focus))


def _build_post_plan_facts(
    planned: V2AdaptivePlannedRound,
    summary: V2AdaptiveRoundExecution,
    clock: Callable[[], datetime],
) -> V2RoundFourPostPlanFacts:
    """Build actual facts only after an accepted Round-4 plan has executed."""
    return V2RoundFourPostPlanFacts(
        run_id=planned.run_id,
        accepted_novel_query_ids=tuple(query.query_id for query in planned.plan.searches),
        accepted_query_count=len(planned.plan.searches),
        executed_query_count=summary.completed_query_count + summary.failed_query_count,
        successful_query_count=summary.completed_query_count,
        new_source_count=summary.new_source_count,
        survivor_additions=summary.survivor_additions,
        productive_execution=summary.survivor_additions > 0,
        round_status=summary.status,
        completed_at=clock(),
    )


def _finish(
    path: str,
    continuation: V2AdaptiveContinuationResult,
    gap: V2GapAnalysisOutput,
    decision: V2RoundFourGovernorDecision,
    clock: Callable[[], datetime],
    post_plan_facts: V2RoundFourPostPlanFacts | None = None,
) -> V2RoundFourRunResult:
    persisted_decision = _read(path, continuation.run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY)
    if persisted_decision is None:
        insert_v2_artifact(
            path,
            V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
            decision,
            decision.decided_at,
        )
        authorization = decision
    else:
        authorization = V2RoundFourGovernorDecision.model_validate_json(persisted_decision)
        if authorization.run_id != continuation.run_id:
            raise ValueError("persisted Round-4 Governor decision does not match the continuation")
    if _read(path, continuation.run_id, V2_POST13_GAP_AFTER_ROUND_THREE_KEY) is None:
        insert_v2_artifact(
            path,
            V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
            gap,
            gap.completed_at,
        )
    if post_plan_facts is not None:
        if post_plan_facts.run_id != continuation.run_id:
            raise ValueError("post-plan facts do not match the continuation")
        persisted_facts = _read(path, continuation.run_id, V2_POST13_ROUND_FOUR_POST_PLAN_FACTS_KEY)
        if persisted_facts is not None:
            original = V2RoundFourPostPlanFacts.model_validate_json(persisted_facts)
            if (
                post_plan_facts.model_copy(update={"completed_at": original.completed_at})
                != original
            ):
                raise ValueError("persisted Round-4 post-plan facts do not match the execution")
            post_plan_facts = original
    result = V2RoundFourRunResult(
        run_id=continuation.run_id,
        continuation=continuation,
        post_round_three_gap=gap,
        governor_decision=authorization,
        post_plan_facts=post_plan_facts,
    )
    artifacts = ((V2_POST13_ROUND_FOUR_COMPLETION_KEY, result, clock()),)
    if post_plan_facts is not None:
        artifacts = (
            (
                V2_POST13_ROUND_FOUR_POST_PLAN_FACTS_KEY,
                post_plan_facts,
                post_plan_facts.completed_at,
            ),
            *artifacts,
        )
    insert_v2_artifact_batch(path, artifacts)
    return result
