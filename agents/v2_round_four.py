"""One bounded post-Round-3 continuation and deterministic gap-coverage reconciliation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import ConfigDict

from agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveContinuationResult,
    V2AdaptivePlannedRound,
    V2AdaptiveRoundExecution,
    V2AdaptiveRoundStatus,
    V2AdaptiveStopCode,
    _eligible_budgets,
    _known_urls,
    _merge_survivors,
    _run_round_from_plan,
    _validate_and_assemble_plan,
)
from agents.v2_gap_analysis import run_v2_gap_analysis
from evidence_portfolio import identify_source_family
from models import (
    V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    ResearchDirections,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchModelOutput,
    V2ClaimCoverageDimension,
    V2ClaimCoverageFocus,
    V2ClaimCoverageKind,
    V2ClaimCoverageSpecification,
    V2DiscoveryScoutOutput,
    V2GapAcquisitionFailure,
    V2GapAnalysisInput,
    V2GapAnalysisModelOutput,
    V2GapAnalysisOutput,
    V2GapAnalysisState,
    V2GapAttemptedQuery,
    V2GapBudgetState,
    V2GapCoverageReconciliation,
    V2GapCoverageRecord,
    V2GapCoverageState,
    V2GapDuplicatePattern,
    V2GapProbePassage,
    V2GapSourceFamily,
    V2GapSurvivingSourceMetadata,
    V2InitialPlannerOutput,
    V2RoundFourDecisionCode,
    V2RoundFourGovernorDecision,
    V2RoundFourReservation,
    V2RoundFourTerminalOutcome,
    V2SearchAgentInput,
)
from providers.llm import (
    V2_LLM_ROUTING,
    LLMProvider,
    LLMProviderExecutionError,
    LLMRequest,
    LLMStage,
    invoke_llm,
    load_prompt,
    render_stage_prompt,
)
from providers.pricing import conservative_token_estimate
from providers.scraper import ScraperProvider
from providers.search import SearchProvider
from providers.v2_routing import V2ModelReservation, V2RoutingConfig
from research_governor import V2RoundFourGovernorInput, evaluate_v2_round_four_authorization
from store import insert_v2_artifact, read_v2_artifact

V2_POST13_GAP_AFTER_ROUND_THREE_KEY = "post-phase-13-gap-analysis-after-round-3-v1"
V2_POST13_ROUND_FOUR_GOVERNOR_KEY = "post-phase-13-round-4-governor-decision-v1"
V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY = "post-phase-13-round-4-terminal-outcome-v1"
V2_POST13_ROUND_FOUR_PLAN_KEY = "post-phase-13-round-4-plan-v1"
V2_POST13_ROUND_FOUR_COMPLETION_KEY = "post-phase-13-round-4-completion-v1"
V2_POST13_GAP_RECONCILIATION_KEY = "post-phase-13-gap-coverage-reconciliation-v1"

_RowT = TypeVar("_RowT")


class V2RoundFourBudgetError(LookupError):
    """The bounded fourth-round workload cannot preserve the downstream reserve."""


class V2RoundFourRunResult(StrictModel):
    """Restart-safe post-Round-3 outcome, including the immutable Gap checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    continuation: V2AdaptiveContinuationResult
    post_round_three_gap: V2GapAnalysisOutput
    governor_decision: V2RoundFourGovernorDecision
    resumed: bool = False


def run_v2_round_four_continuation(
    *,
    db_path: str | Path,
    initial_plan: V2InitialPlannerOutput,
    continuation: V2AdaptiveContinuationResult,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None,
    budget: V2AdaptiveBudgetState,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2RoundFourRunResult:
    """Run the only permitted fourth round from a successful, non-degraded Round 3."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    persisted = _read(path, initial_plan.run_id, V2_POST13_ROUND_FOUR_COMPLETION_KEY)
    if persisted is not None:
        result = V2RoundFourRunResult.model_validate_json(persisted)
        if result.continuation.run_id != initial_plan.run_id:
            raise ValueError("persisted Round-4 continuation does not match the initial plan")
        return result.model_copy(update={"resumed": True})
    if continuation.stopping_decision.completed_rounds != 3 or not continuation.rounds:
        raise ValueError("Round-4 continuation requires exactly one completed Round 3")
    round_three = continuation.rounds[-1]
    if round_three.round_number != 3 or round_three.status is not V2AdaptiveRoundStatus.COMPLETED:
        raise ValueError("Round-4 continuation requires a successful non-degraded Round 3")
    gap_input = build_post_round_three_gap_input(
        initial_plan=initial_plan,
        discovery_outputs=discovery_outputs,
        acquisition_outputs=acquisition_outputs,
        remaining_budget=budget,
        db_path=path,
    )
    if not _gap_envelope_fits(budget, gap_input, routing_config):
        return _finish(
            path,
            continuation,
            _unavailable_gap_output(gap_input, now),
            _governor_decision(
                run_id=initial_plan.run_id,
                clock=now,
                gap_attempted=False,
                protected_downstream_budget_remains=False,
                complete_workload_reservable=False,
            ),
            now,
        )
    gap = run_v2_gap_analysis(
        db_path=path,
        gap_input=gap_input,
        llm_provider=llm_provider,
        routing_config=routing_config,
        artifact_key=V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
        clock=now,
    )
    post_gap_budget = budget_snapshot() if budget_snapshot is not None else budget
    if _cancelled(cancellation_requested):
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap, cancelled=True),
            now,
        )
    if gap.result is None:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap),
            now,
        )
    if not gap.result.material_gaps or not gap.result.continue_research:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap),
            now,
        )
    attempts = _provider_attempts(initial_plan, path)
    eligible = _eligible_budgets(initial_plan, attempts, search_providers)
    if not eligible:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(run_id=initial_plan.run_id, clock=now, gap=gap),
            now,
        )
    duplicate_rate = _duplicate_rate(round_three)
    if duplicate_rate >= 0.70:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(
                run_id=initial_plan.run_id,
                clock=now,
                gap=gap,
                eligible_provider_exists=True,
                round_three_duplicate_rate=duplicate_rate,
            ),
            now,
        )
    try:
        plan = _plan_round_four(
            path=path,
            initial_plan=initial_plan,
            gap=gap,
            eligible=eligible,
            attempts=attempts,
            llm_provider=llm_provider,
            routing_config=routing_config,
            budget=budget,
            clock=now,
        )
    except V2RoundFourBudgetError:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(
                run_id=initial_plan.run_id,
                clock=now,
                gap=gap,
                eligible_provider_exists=True,
                round_three_duplicate_rate=duplicate_rate,
                complete_workload_reservable=False,
            ),
            now,
        )
    except LLMProviderExecutionError:
        terminal = _persist_terminal_outcome(path, initial_plan.run_id, "search_agent", now)
        return _finish(
            path,
            continuation,
            gap,
            terminal,
            now,
        )
    if plan is None:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(
                run_id=initial_plan.run_id,
                clock=now,
                gap=gap,
                eligible_provider_exists=True,
                round_three_duplicate_rate=duplicate_rate,
                materially_new_queries=False,
            ),
            now,
        )
    reservation = _reservation(budget, post_gap_budget, plan, gap, routing_config)
    if reservation is None:
        return _finish(
            path,
            continuation,
            gap,
            _governor_decision(
                run_id=initial_plan.run_id,
                clock=now,
                gap=gap,
                eligible_provider_exists=True,
                round_three_duplicate_rate=duplicate_rate,
                protected_downstream_budget_remains=False,
                complete_workload_reservable=False,
            ),
            now,
        )
    decision = _governor_decision(
        run_id=initial_plan.run_id,
        clock=now,
        gap=gap,
        eligible_provider_exists=True,
        round_three_duplicate_rate=duplicate_rate,
        materially_new_queries=bool(plan.plan.searches),
        round_four_productive=bool(plan.plan.searches),
        reservation=reservation,
    )
    insert_v2_artifact(path, V2_POST13_ROUND_FOUR_GOVERNOR_KEY, decision, decision.decided_at)
    search, discovery, acquisition, summary = _run_round_from_plan(
        path=path,
        planned=plan,
        search_providers=search_providers,
        llm_provider=llm_provider,
        routing_config=routing_config,
        wigolo_provider=wigolo_provider,
        firecrawl_provider=firecrawl_provider,
        crossref_resolver=crossref_resolver,
        known_urls=_known_urls(discovery_outputs),
        cancellation_requested=cancellation_requested,
        clock=now,
    )
    del search
    if summary.status is V2AdaptiveRoundStatus.CANCELLED:
        cancelled = continuation.model_copy(
            update={
                "stopping_decision": continuation.stopping_decision.model_copy(
                    update={
                        "stop_code": V2AdaptiveStopCode.CANCELLED,
                        "stopping_reason": "Cancellation was observed during targeted Round 4.",
                        "decided_at": now(),
                    }
                ),
                "completed_at": now(),
            }
        )
        return _finish(path, cancelled, gap, decision, now)
    if summary.status is V2AdaptiveRoundStatus.DEGRADED:
        failed = continuation.model_copy(
            update={
                "rounds": (*continuation.rounds, summary),
                "stopping_decision": continuation.stopping_decision.model_copy(
                    update={
                        "stop_code": V2AdaptiveStopCode.PROVIDER_FAILURE,
                        "stopping_reason": "Targeted Round 4 ended after a provider failure.",
                        "decided_at": now(),
                    }
                ),
                "completed_at": now(),
            }
        )
        terminal = _persist_terminal_outcome(path, initial_plan.run_id, "provider", now)
        return _finish(
            path,
            failed,
            gap,
            terminal,
            now,
        )
    merged = _merge_survivors(
        initial_plan.run_id,
        tuple(
            (
                round_number,
                discovery_outputs[round_number - 1],
                acquisition_outputs[round_number - 1],
            )
            for round_number in range(1, 4)
        )
        + ((4, discovery, acquisition),),
    )
    updated = continuation.model_copy(
        update={
            "rounds": (*continuation.rounds, summary),
            "merged_survivors": merged,
            "stopping_decision": continuation.stopping_decision.model_copy(
                update={
                    "completed_rounds": 4,
                    "stop_code": V2AdaptiveStopCode.ROUND_FOUR_COMPLETE,
                    "stopping_reason": (
                        "Targeted Round 4 completed; no further research round is permitted."
                    ),
                    "decided_at": now(),
                }
            ),
            "completed_at": now(),
        }
    )
    return _finish(path, updated, gap, decision, now)


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
        remaining_budget=V2GapBudgetState(
            model_calls_remaining=max(
                0,
                remaining_budget.model_calls_remaining
                - remaining_budget.protected_downstream_model_calls,
            ),
            tokens_remaining=(
                None
                if remaining_budget.tokens_remaining is None
                else max(
                    0,
                    remaining_budget.tokens_remaining
                    - remaining_budget.protected_downstream_tokens,
                )
            ),
            cost_remaining_usd=(
                None
                if remaining_budget.cost_remaining_usd is None
                else max(
                    Decimal("0"),
                    remaining_budget.cost_remaining_usd
                    - remaining_budget.protected_downstream_cost_usd,
                )
            ),
        ),
        policy_identity=V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
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
    component_focus = list(planner_focus)
    if not any(
        item.dimension is V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION for item in component_focus
    ):
        component_focus.insert(
            0,
            V2ClaimCoverageFocus(
                dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
                claim_component=exact_claim,
                kind=V2ClaimCoverageKind.CLAIM_COMPONENT,
            ),
        )
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


def reconcile_post_round_three_gaps(
    *,
    db_path: str | Path,
    post_round_three_gap: V2GapAnalysisOutput,
    admission_result: object,
    clock: Callable[[], datetime] | None = None,
) -> V2GapCoverageReconciliation:
    """Mark only Round-4 analyzer-admitted evidence with exact Gap provenance as coverage."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    persisted = _read(path, post_round_three_gap.run_id, V2_POST13_GAP_RECONCILIATION_KEY)
    if persisted is not None:
        return V2GapCoverageReconciliation.model_validate_json(persisted)
    gaps = post_round_three_gap.result.material_gaps if post_round_three_gap.result else ()
    governor_payload = _read(path, post_round_three_gap.run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY)
    governor = (
        V2RoundFourGovernorDecision.model_validate_json(governor_payload)
        if governor_payload is not None
        else None
    )
    round_four_attempted = bool(governor and governor.authorized)
    unavailable = bool(
        governor
        and governor.reason_code
        in {
            V2RoundFourDecisionCode.INSUFFICIENT_RESERVATION,
            V2RoundFourDecisionCode.GAP_ANALYSIS_UNUSABLE,
            V2RoundFourDecisionCode.NO_ELIGIBLE_PROVIDER,
        }
    )
    records: list[V2GapCoverageRecord] = []
    source_results = getattr(admission_result, "source_results", ())
    for gap in gaps:
        match = next(
            (
                source
                for source in source_results
                if getattr(source, "evidence_record", None) is not None
                and source.direction is gap.direction
                and getattr(source.provenance, "discovery_round", 0) == 4
                and gap.gap_id in source.provenance.relevant_gap_ids
                and gap.gap_id
                in next(
                    (
                        analyst.assessment.addressed_gap_ids
                        for analyst in admission_result.analyst_result.source_results
                        if analyst.source_id == source.source_id and analyst.assessment is not None
                    ),
                    (),
                )
            ),
            None,
        )
        if match is None:
            records.append(
                V2GapCoverageRecord(
                    gap=gap,
                    state=(
                        V2GapCoverageState.UNRESOLVED
                        if round_four_attempted
                        else (
                            V2GapCoverageState.UNAVAILABLE
                            if unavailable
                            else V2GapCoverageState.NOT_ATTEMPTED
                        )
                    ),
                )
            )
            continue
        query_id = next(
            (
                item.query_id
                for candidate in admission_result.analyst_result.input.queue_result.input.survivors
                if candidate.source_id == match.source_id
                for item in candidate.search_provenance
                if item.round_number == 4 and gap.gap_id in item.targeted_gap_ids
            ),
            None,
        )
        if query_id is None:
            records.append(V2GapCoverageRecord(gap=gap, state=V2GapCoverageState.UNRESOLVED))
        else:
            records.append(
                V2GapCoverageRecord(
                    gap=gap,
                    state=V2GapCoverageState.COVERED,
                    source_id=match.source_id,
                    query_id=query_id,
                    ledger_claim_id=match.evidence_record.ledger_claim_id,
                )
            )
    result = V2GapCoverageReconciliation(
        run_id=post_round_three_gap.run_id,
        post_round_three_gap_artifact_key=V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
        round_four_attempted=round_four_attempted,
        records=tuple(records),
        claim_coverage_map=(
            post_round_three_gap.result.claim_coverage_map
            if post_round_three_gap.result is not None
            else ()
        ),
        completed_at=now(),
    )
    insert_v2_artifact(path, V2_POST13_GAP_RECONCILIATION_KEY, result, result.completed_at)
    return result


def _plan_round_four(
    *,
    path: str,
    initial_plan: V2InitialPlannerOutput,
    gap: V2GapAnalysisOutput,
    eligible: tuple[object, ...],
    attempts: Mapping[DiscoveryProvider, int],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    budget: V2AdaptiveBudgetState,
    clock: Callable[[], datetime],
) -> V2AdaptivePlannedRound | None:
    stored = _read(path, initial_plan.run_id, V2_POST13_ROUND_FOUR_PLAN_KEY)
    if stored is not None:
        return V2AdaptivePlannedRound.model_validate_json(stored)
    if gap.result is None:
        return None
    previous = tuple(query.query_text for query in initial_plan.searches)
    for round_number in (2, 3):
        payload = _read(path, initial_plan.run_id, f"phase-7-round-{round_number}-plan")
        if payload is not None:
            previous += tuple(
                query.query_text
                for query in V2AdaptivePlannedRound.model_validate_json(payload).plan.searches
            )
    request_input = V2SearchAgentInput(
        run_id=initial_plan.run_id,
        exact_claim=initial_plan.raw_claim,
        round_number=4,
        directions=initial_plan.directions,
        eligible_providers=tuple(item.provider for item in eligible),
        material_gaps=gap.result.material_gaps,
        search_directions=gap.result.new_search_directions,
        discovered_terms=tuple(
            dict.fromkeys((*gap.input.discovered_terms, *gap.result.discovered_terms))
        )[:40],
        previous_queries=previous,
        provider_budgets=eligible,
        maximum_queries=min(
            4 * len(initial_plan.directions.enabled_directions),
            sum(min(2, item.remaining_calls) for item in eligible),
        ),
        policy_identity=V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    )
    if request_input.maximum_queries == 0:
        return None
    prompt = load_prompt(LLMStage.SEARCH_AGENT)
    route = routing_config.preflight().for_stage(LLMStage.SEARCH_AGENT)
    request = LLMRequest(
        run_id=initial_plan.run_id,
        stage=LLMStage.SEARCH_AGENT,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, request_input, V2AdaptiveSearchModelOutput),
        input_artifact=request_input,
        input_artifact_ids=(initial_plan.run_id,),
        requested_output_type=V2AdaptiveSearchModelOutput,
        model_alias=route.logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.SEARCH_AGENT).generation,
    )
    search_reservation = routing_config.preflight().reserve(
        LLMStage.SEARCH_AGENT, conservative_token_estimate(request.rendered_prompt)
    )
    max_scout_calls = ((request_input.maximum_queries * 5 + 29) // 30) * 2
    scout_reservation = routing_config.preflight().reserve(LLMStage.SCOUT, 1)
    if not _fits_reserve(
        budget,
        calls=2 + 1 + max_scout_calls,
        tokens=(
            2 * _gap_reservation(gap.input, routing_config).reserved_tokens
            + search_reservation.reserved_tokens
            + max_scout_calls * scout_reservation.reserved_tokens
        ),
        cost=(
            2 * _gap_reservation(gap.input, routing_config).reserved_cost_usd
            + search_reservation.reserved_cost_usd
            + max_scout_calls * scout_reservation.reserved_cost_usd
        ),
    ):
        raise V2RoundFourBudgetError("Round-4 Search Agent plan cannot fit the full reserve")
    response = invoke_llm(llm_provider, request, clock=clock).output_artifact
    if not isinstance(response, V2AdaptiveSearchModelOutput):
        return None
    assembled = _validate_and_assemble_plan(request_input, response, prompt.version, clock())
    if not assembled.searches:
        return None
    plan = assembled.model_copy(
        update={
            "policy_identity": V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
            "searches": tuple(
                query.model_copy(update={"policy_identity": V2_POST13_ROUND_FOUR_POLICY_IDENTITY})
                for query in assembled.searches
            ),
        }
    )
    result = V2AdaptivePlannedRound(
        run_id=initial_plan.run_id,
        plan=plan,
        reservation={
            "input_tokens": search_reservation.input_tokens,
            "output_tokens": search_reservation.output_tokens,
            "reserved_tokens": search_reservation.reserved_tokens,
            "reserved_cost_usd": search_reservation.reserved_cost_usd,
        },
    )
    insert_v2_artifact(path, V2_POST13_ROUND_FOUR_PLAN_KEY, result, plan.planned_at)
    return result


def _reservation(
    budget: V2AdaptiveBudgetState,
    post_gap_budget: V2AdaptiveBudgetState,
    plan: V2AdaptivePlannedRound,
    gap: V2GapAnalysisOutput,
    routing_config: V2RoutingConfig,
) -> V2RoundFourReservation | None:
    scout_calls = ((len(plan.plan.searches) * 5 + 29) // 30) * 2
    scout_reserve = routing_config.preflight().reserve(LLMStage.SCOUT, 1)
    gap_reserve = _gap_reservation(gap.input, routing_config)
    optional_tokens = (
        2 * gap_reserve.reserved_tokens
        + plan.reservation.reserved_tokens
        + scout_calls * scout_reserve.reserved_tokens
    )
    optional_cost = (
        2 * gap_reserve.reserved_cost_usd
        + plan.reservation.reserved_cost_usd
        + scout_calls * scout_reserve.reserved_cost_usd
    )
    future_tokens = plan.reservation.reserved_tokens + scout_calls * scout_reserve.reserved_tokens
    future_cost = plan.reservation.reserved_cost_usd + scout_calls * scout_reserve.reserved_cost_usd
    try:
        return V2RoundFourReservation(
            protected_downstream_calls=budget.protected_downstream_model_calls,
            protected_downstream_tokens=budget.protected_downstream_tokens,
            protected_downstream_cost_usd=budget.protected_downstream_cost_usd,
            gap_attempt_calls=2,
            search_agent_calls=1,
            scout_calls=scout_calls,
            provider_search_calls=len(plan.plan.searches),
            acquisition_cluster_capacity=len(plan.plan.searches) * 5,
            optional_calls=3 + scout_calls,
            optional_tokens=optional_tokens,
            optional_cost_usd=optional_cost,
            available_calls=budget.model_calls_remaining,
            available_tokens=budget.tokens_remaining,
            available_cost_usd=budget.cost_remaining_usd,
            consumed_gap_attempt_calls=len(gap.attempts),
            future_optional_calls=1 + scout_calls,
            future_optional_tokens=future_tokens,
            future_optional_cost_usd=future_cost,
            post_gap_available_calls=post_gap_budget.model_calls_remaining,
            post_gap_available_tokens=post_gap_budget.tokens_remaining,
            post_gap_available_cost_usd=post_gap_budget.cost_remaining_usd,
        )
    except ValueError:
        return None


def _gap_envelope_fits(
    budget: V2AdaptiveBudgetState,
    gap_input: V2GapAnalysisInput,
    routing_config: V2RoutingConfig,
) -> bool:
    reservation = _gap_reservation(gap_input, routing_config)
    return _fits_reserve(
        budget,
        calls=2,
        tokens=2 * reservation.reserved_tokens,
        cost=2 * reservation.reserved_cost_usd,
    )


def _gap_reservation(
    gap_input: V2GapAnalysisInput, routing_config: V2RoutingConfig
) -> V2ModelReservation:
    prompt = load_prompt(LLMStage.GAP_ANALYSIS)
    rendered = render_stage_prompt(prompt, gap_input, V2GapAnalysisModelOutput)
    return routing_config.preflight().reserve(
        LLMStage.GAP_ANALYSIS, conservative_token_estimate(rendered)
    )


def _fits_reserve(
    budget: V2AdaptiveBudgetState,
    *,
    calls: int,
    tokens: int,
    cost: Decimal,
) -> bool:
    if budget.model_calls_remaining < budget.protected_downstream_model_calls + calls:
        return False
    if (
        budget.tokens_remaining is not None
        and budget.tokens_remaining < budget.protected_downstream_tokens + tokens
    ):
        return False
    return (
        budget.cost_remaining_usd is None
        or budget.cost_remaining_usd >= budget.protected_downstream_cost_usd + cost
    )


def _unavailable_gap_output(
    gap_input: V2GapAnalysisInput, clock: Callable[[], datetime]
) -> V2GapAnalysisOutput:
    return V2GapAnalysisOutput(
        run_id=gap_input.run_id,
        input=gap_input,
        state=V2GapAnalysisState.DEGRADED,
        attempts=(),
        stop_adaptive_continuation=True,
        completed_at=clock(),
    )


def _provider_attempts(
    initial_plan: V2InitialPlannerOutput, path: str
) -> dict[DiscoveryProvider, int]:
    counts: Counter[DiscoveryProvider] = Counter(query.provider for query in initial_plan.searches)
    for round_number in (2, 3):
        payload = _read(path, initial_plan.run_id, f"phase-7-round-{round_number}-plan")
        if payload is not None:
            counts.update(
                query.provider
                for query in V2AdaptivePlannedRound.model_validate_json(payload).plan.searches
            )
    return dict(counts)


def _duplicate_rate(summary: V2AdaptiveRoundExecution) -> float:
    total = summary.new_source_count + summary.duplicate_source_count
    return summary.duplicate_source_count / total if total else 0.0


def _governor_decision(
    *,
    run_id: UUID,
    clock: Callable[[], datetime],
    gap: V2GapAnalysisOutput | None = None,
    gap_attempted: bool = True,
    eligible_provider_exists: bool = False,
    materially_new_queries: bool = False,
    round_three_duplicate_rate: float = 0.0,
    round_four_productive: bool = True,
    protected_downstream_budget_remains: bool = True,
    complete_workload_reservable: bool = True,
    cancelled: bool = False,
    terminal_provider_failure: bool = False,
    reservation: V2RoundFourReservation | None = None,
) -> V2RoundFourGovernorDecision:
    """Evaluate one typed set of observed Round-4 facts without selecting a result first."""
    result = gap.result if gap is not None else None
    return evaluate_v2_round_four_authorization(
        V2RoundFourGovernorInput(
            run_id=run_id,
            gap_analysis_attempted=gap_attempted,
            gap_analysis_usable=result is not None,
            material_gap_remains=bool(result and result.material_gaps),
            luna_recommends_continue=bool(result and result.continue_research),
            eligible_provider_exists=eligible_provider_exists,
            materially_new_queries=materially_new_queries,
            round_three_duplicate_rate=round_three_duplicate_rate,
            round_four_productive=round_four_productive,
            protected_downstream_budget_remains=protected_downstream_budget_remains,
            complete_workload_reservable=complete_workload_reservable,
            cancelled=cancelled,
            terminal_provider_failure=terminal_provider_failure,
            decided_at=clock(),
        ),
        reservation=reservation,
    )


def _finish(
    path: str,
    continuation: V2AdaptiveContinuationResult,
    gap: V2GapAnalysisOutput,
    decision: V2RoundFourGovernorDecision,
    clock: Callable[[], datetime],
) -> V2RoundFourRunResult:
    result = V2RoundFourRunResult(
        run_id=continuation.run_id,
        continuation=continuation,
        post_round_three_gap=gap,
        governor_decision=decision,
    )
    if _read(path, continuation.run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY) is None:
        insert_v2_artifact(
            path,
            V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
            decision,
            decision.decided_at,
        )
    if _read(path, continuation.run_id, V2_POST13_GAP_AFTER_ROUND_THREE_KEY) is None:
        insert_v2_artifact(
            path,
            V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
            gap,
            gap.completed_at,
        )
    insert_v2_artifact(path, V2_POST13_ROUND_FOUR_COMPLETION_KEY, result, clock())
    return result


def _persist_terminal_outcome(
    path: str, run_id: UUID, failed_stage: str, clock: Callable[[], datetime]
) -> V2RoundFourGovernorDecision:
    """Persist a terminal lifecycle record without replacing immutable authorization."""
    decision = _governor_decision(
        run_id=run_id,
        clock=clock,
        terminal_provider_failure=True,
    )
    if _read(path, run_id, V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY) is None:
        outcome = V2RoundFourTerminalOutcome(
            run_id=run_id,
            reason_code=V2RoundFourDecisionCode.TERMINAL_FAILURE,
            failed_stage=failed_stage,
            completed_at=decision.decided_at,
        )
        insert_v2_artifact(
            path,
            V2_POST13_ROUND_FOUR_TERMINAL_OUTCOME_KEY,
            outcome,
            outcome.completed_at,
        )
    return decision


def _read(path: str, run_id: UUID, key: str) -> str | None:
    try:
        return read_v2_artifact(path, run_id, key).payload_json
    except KeyError:
        return None


def _cancelled(callback: Callable[[], bool] | None) -> bool:
    return callback is not None and callback()


def _utc_now() -> datetime:
    return datetime.now(UTC)
