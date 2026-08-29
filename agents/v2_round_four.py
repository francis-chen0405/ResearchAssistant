"""One bounded post-Round-3 continuation and deterministic gap-coverage reconciliation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
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
from models import (
    V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2AdaptiveSearchModelOutput,
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
    V2SearchAgentInput,
)
from providers.llm import (
    V2_LLM_ROUTING,
    LLMProvider,
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
from store import insert_v2_artifact, read_v2_artifact

V2_POST13_GAP_AFTER_ROUND_THREE_KEY = "post-phase-13-gap-analysis-after-round-3-v1"
V2_POST13_ROUND_FOUR_GOVERNOR_KEY = "post-phase-13-round-4-governor-decision-v1"
V2_POST13_ROUND_FOUR_PLAN_KEY = "post-phase-13-round-4-plan-v1"
V2_POST13_ROUND_FOUR_COMPLETION_KEY = "post-phase-13-round-4-completion-v1"
V2_POST13_GAP_RECONCILIATION_KEY = "post-phase-13-gap-coverage-reconciliation-v1"


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
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.INSUFFICIENT_RESERVATION,
                "Round 4 was not started because two bounded post-Round-3 Gap Analysis "
                "attempts and the protected downstream reserve do not fit.",
                now,
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
    if _cancelled(cancellation_requested):
        return _finish(
            path,
            continuation,
            gap,
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.CANCELLED,
                "Round 4 was not started because cancellation was requested.",
                now,
            ),
            now,
        )
    if gap.result is None:
        return _finish(
            path,
            continuation,
            gap,
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.GAP_ANALYSIS_UNUSABLE,
                "Round 4 was not started because post-Round-3 Gap Analysis was unusable.",
                now,
            ),
            now,
        )
    if not gap.result.material_gaps or not gap.result.continue_research:
        return _finish(
            path,
            continuation,
            gap,
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.NO_MATERIAL_GAPS,
                "Round 4 was not started because no material post-Round-3 gaps remain.",
                now,
            ),
            now,
        )
    attempts = _provider_attempts(initial_plan, path)
    eligible = _eligible_budgets(initial_plan, attempts, search_providers)
    if not eligible:
        return _finish(
            path,
            continuation,
            gap,
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.NO_ELIGIBLE_PROVIDER,
                "Round 4 was not started because no eligible provider capacity remains.",
                now,
            ),
            now,
        )
    duplicate_rate = _duplicate_rate(round_three)
    if duplicate_rate >= 0.70:
        return _finish(
            path,
            continuation,
            gap,
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.DUPLICATE_HEAVY,
                "Round 4 was not started because Round 3 was duplicate-heavy.",
                now,
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
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.INSUFFICIENT_RESERVATION,
                "Round 4 was not started because the maximum narrow workload and protected "
                "downstream reserve do not fit.",
                now,
            ),
            now,
        )
    if plan is None:
        return _finish(
            path,
            continuation,
            gap,
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.NO_NOVEL_QUERY,
                "Round 4 was not started because no non-trivial novel queries were accepted.",
                now,
            ),
            now,
        )
    reservation = _reservation(budget, plan, gap, routing_config)
    if reservation is None:
        return _finish(
            path,
            continuation,
            gap,
            _decision(
                initial_plan.run_id,
                False,
                V2RoundFourDecisionCode.INSUFFICIENT_RESERVATION,
                "Round 4 was not started because its full bounded workload and downstream "
                "reserve do not fit.",
                now,
            ),
            now,
        )
    decision = _decision(
        initial_plan.run_id,
        True,
        V2RoundFourDecisionCode.AUTHORIZED,
        "Round 4 was authorized as a narrow gap-directed continuation with protected "
        "downstream capacity.",
        now,
        reservation,
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
    sources: list[V2GapSurvivingSourceMetadata] = []
    passages: list[V2GapProbePassage] = []
    families: list[V2GapSourceFamily] = []
    duplicates: list[V2GapDuplicatePattern] = []
    failures: list[V2GapAcquisitionFailure] = []
    terms: list[str] = []
    for discovery, acquisition in zip(discovery_outputs, acquisition_outputs, strict=True):
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
            sources.append(
                V2GapSurvivingSourceMetadata(
                    source_cluster_id=survivor.cluster_id,
                    direction=survivor.direction,
                    snapshot_id=survivor.snapshot_id,
                    snapshot_sha256=survivor.snapshot_sha256,
                    source_url=source.snapshot.source_url,
                    title=representative.title,
                    source_family_id=f"cluster:{survivor.cluster_id}",
                )
            )
            families.append(
                V2GapSourceFamily(
                    family_id=f"cluster:{survivor.cluster_id}",
                    direction=survivor.direction,
                    source_cluster_ids=(survivor.cluster_id,),
                    discovery_providers=tuple(
                        dict.fromkeys(
                            reference.provider for reference in cluster.provider_references
                        )
                    ),
                )
            )
            probe = next(
                item for item in acquisition.probes if item.snapshot_id == survivor.snapshot_id
            )
            by_id = {item.passage_id: item for item in probe.passages}
            for passage_id in survivor.passage_ids:
                passage = by_id[passage_id]
                text = passage.text[:1200]
                passages.append(
                    V2GapProbePassage(
                        passage_id=passage_id,
                        source_cluster_id=survivor.cluster_id,
                        direction=survivor.direction,
                        text=text,
                        truncated_for_gap_analysis=len(text) < len(passage.text),
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
    return V2GapAnalysisInput(
        run_id=initial_plan.run_id,
        exact_claim=initial_plan.raw_claim,
        directions=initial_plan.directions,
        completed_round=3,
        attempted_queries=tuple(
            V2GapAttemptedQuery(
                query_id=query.query_id,
                direction=query.direction,
                provider=query.provider,
                strategy=query.strategy,
                query_text=query.query_text,
            )
            for plan in plans
            for query in plan.searches
        )[:48],
        surviving_sources=tuple(sources)[:75],
        probe_passages=tuple(passages)[:40],
        source_families=tuple(families)[:75],
        discovered_terms=tuple(dict.fromkeys(terms))[:40],
        duplicate_patterns=tuple(duplicates)[:25],
        acquisition_failures=tuple(failures)[:150],
        previous_gaps=tuple(previous_gaps)[:6],
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


def _decision(
    run_id: UUID,
    authorized: bool,
    code: V2RoundFourDecisionCode,
    explanation: str,
    clock: Callable[[], datetime],
    reservation: V2RoundFourReservation | None = None,
) -> V2RoundFourGovernorDecision:
    return V2RoundFourGovernorDecision(
        run_id=run_id,
        authorized=authorized,
        reason_code=code,
        explanation=explanation,
        reservation=reservation,
        decided_at=clock(),
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


def _read(path: str, run_id: UUID, key: str) -> str | None:
    try:
        return read_v2_artifact(path, run_id, key).payload_json
    except KeyError:
        return None


def _cancelled(callback: Callable[[], bool] | None) -> bool:
    return callback is not None and callback()


def _utc_now() -> datetime:
    return datetime.now(UTC)
