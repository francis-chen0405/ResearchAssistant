"""Final v2 source prioritization and conservative deep-analysis queue planning."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict

from agents.v2_adaptive_search import V2MergedSurvivorPool
from evidence_portfolio import identify_source_family
from models import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    ResearchDirection,
    V2AcquisitionProbeOutput,
    V2DeepAnalysisBudget,
    V2DeepAnalysisBudgetReason,
    V2DeepAnalysisQueuePlan,
    V2DeepAnalysisSourceStatus,
    V2DeepAnalysisTokenReservation,
    V2DiscoveryScoutOutput,
    V2GapAnalysisOutput,
    V2SourceSelectionAttempt,
    V2SourceSelectionCandidate,
    V2SourceSelectionGap,
    V2SourceSelectionInput,
    V2SourceSelectionModelOutput,
    V2SourceSelectionProbePassage,
    V2SourceSelectionQueueResult,
    V2SourceSelectionRecommendation,
    V2SourceSelectionSearchProvenance,
)
from money import add_usd
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
from providers.v2_budget import V2CancellationRequested
from providers.v2_routing import V2RoutingConfig
from store import insert_v2_artifact, read_v2_artifact

V2_SOURCE_SELECTION_MAX_ATTEMPTS = 2
V2_SOURCE_SELECTION_LEGACY_POOL_KEY = "phase-8-complete-survivor-pool"
V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY = "phase-8-source-selection-deep-analysis-queue"
V2_SOURCE_SELECTION_POOL_KEY = "phase-13-complete-survivor-pool-analyzer-admission"
V2_SOURCE_SELECTION_COMPLETION_KEY = (
    "phase-13-source-selection-deep-analysis-queue-analyzer-admission"
)
V2_SOURCE_SELECTION_STATUS_KEY = "phase-13-source-statuses-analyzer-admission"
_RECOMMENDATION_TARGET_MAX = 10
_SYNTHESIS_BASE_INPUT_TOKENS = 1000
_SYNTHESIS_INPUT_TOKENS_PER_SOURCE = 500


class V2SourceSelectionRunResult(V2SourceSelectionQueueResult):
    """Phase result with explicit restart provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resumed: bool = False

    @property
    def result(self) -> V2SourceSelectionQueueResult:
        return V2SourceSelectionQueueResult.model_validate(
            self.model_dump(mode="python", exclude={"resumed"})
        )


def build_v2_source_selection_input(
    *,
    exact_claim: str,
    merged_survivors: V2MergedSurvivorPool,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    gap_outputs: tuple[V2GapAnalysisOutput, ...],
) -> V2SourceSelectionInput:
    """Reconstruct every merged survivor with its persisted round context."""
    if not discovery_outputs or len(discovery_outputs) != len(acquisition_outputs):
        raise ValueError("source selection requires paired discovery/acquisition rounds")
    run_id = merged_survivors.run_id
    directions = discovery_outputs[0].directions
    if any(
        output.run_id != run_id or output.directions != directions
        for output in (*discovery_outputs, *acquisition_outputs)
    ) or any(
        output.run_id != run_id or output.input.directions != directions for output in gap_outputs
    ):
        raise ValueError("source-selection round artifacts must share run and directions")
    gap_rows = tuple(
        V2SourceSelectionGap(
            gap_id=gap.gap_id,
            direction=gap.direction,
            missing_evidence=gap.missing_evidence,
            assessed_after_round=output.input.completed_round,
        )
        for output in gap_outputs
        if output.result is not None
        for gap in output.result.material_gaps
    )
    discoveries = {index: item for index, item in enumerate(discovery_outputs, 1)}
    acquisitions = {index: item for index, item in enumerate(acquisition_outputs, 1)}
    for round_number, discovery in discoveries.items():
        if any(item.round_number != round_number for item in discovery.items):
            raise ValueError("source-selection discovery outputs must use completed round order")
    candidates: list[V2SourceSelectionCandidate] = []
    for merged in merged_survivors.sources:
        discovery = discoveries.get(merged.research_round)
        acquisition = acquisitions.get(merged.research_round)
        if discovery is None or acquisition is None:
            raise ValueError("merged survivor has no persisted completed round artifacts")
        survivor = merged.survivor
        cluster = next(
            (item for item in discovery.clusters if item.cluster_id == survivor.cluster_id),
            None,
        )
        source = next(
            (
                item
                for item in acquisition.acquisitions
                if item.snapshot.snapshot_id == survivor.snapshot_id
            ),
            None,
        )
        probe = next(
            (item for item in acquisition.probes if item.snapshot_id == survivor.snapshot_id),
            None,
        )
        if cluster is None or source is None or probe is None or not probe.succeeded:
            raise ValueError("merged survivor lacks its cluster, snapshot, or successful Probe")
        items = {item.item_id: item for item in discovery.items}
        representative = min(
            (items[item_id] for item_id in cluster.item_ids),
            key=lambda item: (item.provider_rank, item.provider.value, str(item.item_id)),
        )
        passages = {item.passage_id: item for item in probe.passages}
        selected_passages = tuple(
            V2SourceSelectionProbePassage(
                passage_id=passage_id,
                text=passages[passage_id].text[:1200],
                score=passages[passage_id].score,
            )
            for passage_id in survivor.passage_ids
        )
        prior_gap_ids = tuple(
            dict.fromkeys(
                gap.gap_id
                for gap in gap_rows
                if gap.direction is survivor.direction
                and gap.assessed_after_round < merged.research_round
            )
        )
        search_provenance = tuple(
            V2SourceSelectionSearchProvenance(
                query_id=item.query_id,
                provider=item.provider,
                round_number=item.round_number,
                query_text=item.query_text,
                targeted_gap_ids=(prior_gap_ids if item.round_number > 1 else ()),
            )
            for item in cluster.metadata_provenance
        )
        candidates.append(
            V2SourceSelectionCandidate(
                source_id=survivor.cluster_id,
                direction=survivor.direction,
                source_family_id=str(identify_source_family(source.snapshot).source_family_id),
                research_round=merged.research_round,
                source_url=merged.source_url,
                title=representative.title,
                source_type=representative.source_type,
                doi=representative.doi,
                authors=representative.authors,
                publication_date=representative.publication_date,
                discovery_providers=tuple(
                    dict.fromkeys(item.provider for item in cluster.provider_references)
                ),
                probe_passages=selected_passages,
                search_provenance=search_provenance,
                snapshot_word_count=source.snapshot.word_count,
                deep_analysis_input_tokens=(
                    conservative_token_estimate(source.snapshot.normalized_text) + 2000
                ),
            )
        )
    if len(candidates) != len(merged_survivors.sources):
        raise ValueError("source-selection input must retain every merged survivor")
    return V2SourceSelectionInput(
        run_id=run_id,
        exact_claim=exact_claim,
        directions=directions,
        survivors=tuple(candidates),
        gap_history=gap_rows,
    )


def run_v2_source_selection_and_queue(
    *,
    db_path: str | Path,
    selection_input: V2SourceSelectionInput,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    budget: V2DeepAnalysisBudget,
    clock: Callable[[], datetime] | None = None,
) -> V2SourceSelectionRunResult:
    """Recommend only known survivors, fall back safely, and persist a bounded queue."""
    now = clock or _utc_now
    completed_at = now()
    _require_aware(completed_at)
    path = str(Path(db_path).resolve())
    try:
        stored = read_v2_artifact(
            path,
            selection_input.run_id,
            V2_SOURCE_SELECTION_COMPLETION_KEY,
        )
    except KeyError:
        stored = None
    if stored is not None:
        result = V2SourceSelectionQueueResult.model_validate_json(stored.payload_json)
        if result.input != selection_input or result.initial_budget != budget:
            raise ValueError("persisted source-selection state does not match this survivor pool")
        return V2SourceSelectionRunResult(**result.model_dump(), resumed=True)

    insert_v2_artifact(path, V2_SOURCE_SELECTION_POOL_KEY, selection_input, completed_at)
    route = routing_config.preflight().for_stage(LLMStage.SOURCE_SELECTION)
    if route.logical_alias is not V2_LLM_ROUTING.for_stage(LLMStage.SOURCE_SELECTION).primary:
        raise ValueError("Final Source Selection must use the MiMo-v2.5-Pro route")
    prompt = load_prompt(LLMStage.SOURCE_SELECTION)
    request = LLMRequest(
        run_id=selection_input.run_id,
        stage=LLMStage.SOURCE_SELECTION,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(
            prompt,
            selection_input,
            V2SourceSelectionModelOutput,
        ),
        input_artifact=selection_input,
        input_artifact_ids=tuple(item.source_id for item in selection_input.survivors),
        requested_output_type=V2SourceSelectionModelOutput,
        model_alias=route.logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.SOURCE_SELECTION).generation,
    )
    attempts: list[V2SourceSelectionAttempt] = []
    recommendations: tuple[V2SourceSelectionRecommendation, ...] | None = None
    for attempt_number in range(1, V2_SOURCE_SELECTION_MAX_ATTEMPTS + 1):
        reservation = routing_config.preflight().reserve(
            LLMStage.SOURCE_SELECTION,
            conservative_token_estimate(request.rendered_prompt),
        )
        if not _selection_attempt_is_safe(budget, attempts, reservation, routing_config):
            break
        try:
            invocation = invoke_llm(llm_provider, request, clock=now)
            output = V2SourceSelectionModelOutput.model_validate(
                invocation.output_artifact.model_dump(mode="python", round_trip=True)
            )
            recommendations = _validate_recommendations(selection_input, output)
            attempts.append(
                V2SourceSelectionAttempt(
                    attempt_number=attempt_number,
                    reserved_tokens=reservation.reserved_tokens,
                    reserved_cost_usd=reservation.reserved_cost_usd,
                    succeeded=True,
                )
            )
            break
        except V2CancellationRequested:
            raise
        except Exception as exc:
            attempts.append(
                V2SourceSelectionAttempt(
                    attempt_number=attempt_number,
                    reserved_tokens=reservation.reserved_tokens,
                    reserved_cost_usd=reservation.reserved_cost_usd,
                    succeeded=False,
                    failure=f"{type(exc).__name__}: {exc}"[:1000],
                )
            )

    used_fallback = recommendations is None
    if recommendations is None:
        recommendations = _fallback_recommendations(selection_input)
    ordered_recommendations = _interleave_recommendations(selection_input, recommendations)
    ordered_source_ids = _queue_priority(selection_input, ordered_recommendations)
    remaining_budget = _budget_after_selection(budget, attempts)
    queue_plan = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=ordered_source_ids,
        recommended_source_ids=tuple(item.source_id for item in ordered_recommendations),
        recommendation_rationales=ordered_recommendations,
        routing_config=routing_config,
        budget=remaining_budget,
    )
    result = V2SourceSelectionQueueResult(
        run_id=selection_input.run_id,
        input=selection_input,
        initial_budget=budget,
        recommended_source_ids=tuple(item.source_id for item in ordered_recommendations),
        recommendation_rationales=ordered_recommendations,
        used_fallback=used_fallback,
        selection_attempts=len(attempts),
        selection_attempt_records=tuple(attempts),
        priority_source_ids=ordered_source_ids,
        queued_source_ids=queue_plan.queued_source_ids,
        source_statuses=queue_plan.source_statuses,
        queue_capacity=queue_plan.queue_capacity,
        mandatory_synthesis_reservable=queue_plan.mandatory_synthesis_reservable,
        physical_calls_after_reserve=queue_plan.physical_calls_after_reserve,
        total_reserved_tokens=queue_plan.total_reserved_tokens,
        total_reserved_cost_usd=queue_plan.total_reserved_cost_usd,
        token_reservations=queue_plan.token_reservations,
        limiting_reason=queue_plan.limiting_reason,
        completed_at=completed_at,
    )
    insert_v2_artifact(path, V2_SOURCE_SELECTION_STATUS_KEY, result, completed_at)
    insert_v2_artifact(path, V2_SOURCE_SELECTION_COMPLETION_KEY, result, completed_at)
    return V2SourceSelectionRunResult(**result.model_dump(), resumed=False)


def calculate_v2_deep_analysis_queue(
    *,
    selection_input: V2SourceSelectionInput,
    ordered_source_ids: tuple[UUID, ...],
    recommended_source_ids: tuple[UUID, ...],
    routing_config: V2RoutingConfig,
    budget: V2DeepAnalysisBudget,
    recommendation_rationales: tuple[V2SourceSelectionRecommendation, ...] = (),
) -> V2DeepAnalysisQueuePlan:
    """Return the longest priority prefix safe for calls, retries, tokens, and cost."""
    candidates = {item.source_id: item for item in selection_input.survivors}
    if len(ordered_source_ids) != len(set(ordered_source_ids)):
        raise ValueError("deep-analysis queue priority cannot contain duplicate sources")
    if set(ordered_source_ids) != set(candidates):
        raise ValueError("deep-analysis priority must retain every survivor exactly once")
    if not set(recommended_source_ids).issubset(candidates):
        raise ValueError("deep-analysis recommendations cannot invent sources")
    if tuple(ordered_source_ids[: len(recommended_source_ids)]) != recommended_source_ids:
        raise ValueError("recommended survivors must lead the deep-analysis priority")

    rationale_by_id = {item.source_id: item for item in recommendation_rationales}
    preflight = routing_config.preflight()
    synthesis_zero = _synthesis_reservation(preflight, 0)
    synthesis_calls = 2
    synthesis_reservable = _fits(
        budget,
        physical_calls=synthesis_calls,
        tokens=synthesis_zero[0],
        cost=synthesis_zero[1],
    )
    queued: list[UUID] = []
    reservation_points: list[V2DeepAnalysisTokenReservation] = []
    source_tokens = 0
    source_cost = Decimal("0")
    limiting_reason: V2DeepAnalysisBudgetReason | None = None
    if synthesis_reservable:
        for source_id in ordered_source_ids:
            candidate_tokens, candidate_cost = _source_reservation(
                preflight,
                candidates[source_id],
            )
            proposed_source_tokens = source_tokens + candidate_tokens
            proposed_source_cost = add_usd(source_cost, candidate_cost)
            synthesis_tokens, synthesis_cost = _synthesis_reservation(
                preflight,
                len(queued) + 1,
            )
            total_tokens = proposed_source_tokens + synthesis_tokens
            total_cost = add_usd(proposed_source_cost, synthesis_cost)
            physical_calls = (
                synthesis_calls + (len(queued) + 1) * V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
            )
            limiting_reason = _limiting_reason(
                budget,
                physical_calls=physical_calls,
                tokens=total_tokens,
                cost=total_cost,
            )
            if limiting_reason is not None:
                break
            queued.append(source_id)
            source_tokens = proposed_source_tokens
            source_cost = proposed_source_cost
            reservation_points.append(
                V2DeepAnalysisTokenReservation(
                    source_id=source_id,
                    queue_size=len(queued),
                    cumulative_reserved_tokens=total_tokens,
                    cumulative_reserved_cost_usd=total_cost,
                )
            )
    else:
        limiting_reason = _limiting_reason(
            budget,
            physical_calls=synthesis_calls,
            tokens=synthesis_zero[0],
            cost=synthesis_zero[1],
        )

    if queued:
        total_tokens = reservation_points[-1].cumulative_reserved_tokens
        total_cost = reservation_points[-1].cumulative_reserved_cost_usd
        physical_after = (
            budget.physical_calls_used
            + synthesis_calls
            + len(queued) * V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
        )
    elif synthesis_reservable:
        total_tokens, total_cost = synthesis_zero
        physical_after = budget.physical_calls_used + synthesis_calls
    else:
        total_tokens, total_cost = 0, Decimal("0")
        physical_after = budget.physical_calls_used
    queued_set = set(queued)
    recommended_rank = {
        source_id: index for index, source_id in enumerate(recommended_source_ids, 1)
    }
    queue_rank = {source_id: index for index, source_id in enumerate(queued, 1)}
    statuses = tuple(
        V2DeepAnalysisSourceStatus(
            source_id=candidate.source_id,
            direction=candidate.direction,
            recommended=candidate.source_id in recommended_rank,
            recommendation_rank=recommended_rank.get(candidate.source_id),
            selection_rationale=(
                rationale_by_id[candidate.source_id].rationale
                if candidate.source_id in rationale_by_id
                else (
                    "Recommended by deterministic complementary fallback ordering."
                    if candidate.source_id in recommended_rank
                    else None
                )
            ),
            gap_ids=(
                rationale_by_id[candidate.source_id].gap_ids
                if candidate.source_id in rationale_by_id
                else ()
            ),
            queued_for_deep_analysis=candidate.source_id in queued_set,
            queue_rank=queue_rank.get(candidate.source_id),
            budget_prevented_reason=(
                None if candidate.source_id in queued_set else limiting_reason
            ),
        )
        for candidate in selection_input.survivors
    )
    return V2DeepAnalysisQueuePlan(
        run_id=selection_input.run_id,
        queued_source_ids=tuple(queued),
        source_statuses=statuses,
        queue_capacity=len(queued),
        mandatory_synthesis_reservable=synthesis_reservable,
        physical_calls_after_reserve=physical_after,
        total_reserved_tokens=total_tokens,
        total_reserved_cost_usd=total_cost,
        token_reservations=tuple(reservation_points),
        limiting_reason=limiting_reason,
    )


def _validate_recommendations(
    selection_input: V2SourceSelectionInput,
    output: V2SourceSelectionModelOutput,
) -> tuple[V2SourceSelectionRecommendation, ...]:
    candidates = {item.source_id: item for item in selection_input.survivors}
    gaps = {item.gap_id: item for item in selection_input.gap_history}
    by_direction: dict[ResearchDirection, list[V2SourceSelectionRecommendation]] = defaultdict(list)
    for recommendation in output.recommendations:
        candidate = candidates.get(recommendation.source_id)
        if candidate is None:
            raise ValueError("Final Source Selection invented an unknown source ID")
        if any(
            gap_id not in gaps or gaps[gap_id].direction is not candidate.direction
            for gap_id in recommendation.gap_ids
        ):
            raise ValueError("recommended Gap IDs must exist in the source direction")
        by_direction[candidate.direction].append(recommendation)
    for direction in selection_input.directions.enabled_directions:
        available = [item for item in selection_input.survivors if item.direction is direction]
        selected = by_direction[direction]
        if available and not selected:
            raise ValueError("Final Source Selection must recommend from every populated direction")
        if len(selected) > _RECOMMENDATION_TARGET_MAX:
            raise ValueError("Final Source Selection cannot exceed ten sources per direction")
        unseen_families = {item.source_family_id for item in available}
        seen_families: set[str] = set()
        for recommendation in selected:
            family = candidates[recommendation.source_id].source_family_id
            if family in seen_families and unseen_families - seen_families:
                raise ValueError(
                    "Final Source Selection repeated a family before using available diversity"
                )
            seen_families.add(family)
    return output.recommendations


def _fallback_recommendations(
    selection_input: V2SourceSelectionInput,
) -> tuple[V2SourceSelectionRecommendation, ...]:
    recommendations: list[V2SourceSelectionRecommendation] = []
    for direction in selection_input.directions.enabled_directions:
        candidates = tuple(
            item for item in selection_input.survivors if item.direction is direction
        )
        for candidate in _complementary_order(candidates)[:_RECOMMENDATION_TARGET_MAX]:
            recommendations.append(
                V2SourceSelectionRecommendation(
                    source_id=candidate.source_id,
                    rationale=(
                        "Deterministic fallback retained high Probe priority while adding "
                        "an unused source family before redundant family members."
                    ),
                )
            )
    return tuple(recommendations)


def _interleave_recommendations(
    selection_input: V2SourceSelectionInput,
    recommendations: tuple[V2SourceSelectionRecommendation, ...],
) -> tuple[V2SourceSelectionRecommendation, ...]:
    candidates = {item.source_id: item for item in selection_input.survivors}
    lanes = {
        direction: [
            item for item in recommendations if candidates[item.source_id].direction is direction
        ]
        for direction in selection_input.directions.enabled_directions
    }
    return tuple(_interleave_lanes(lanes, selection_input.directions.enabled_directions))


def _queue_priority(
    selection_input: V2SourceSelectionInput,
    recommendations: tuple[V2SourceSelectionRecommendation, ...],
) -> tuple[UUID, ...]:
    recommended_ids = tuple(item.source_id for item in recommendations)
    recommended_set = set(recommended_ids)
    remainder_lanes = {
        direction: [
            item.source_id
            for item in _complementary_order(
                tuple(
                    candidate
                    for candidate in selection_input.survivors
                    if candidate.direction is direction
                    and candidate.source_id not in recommended_set
                )
            )
        ]
        for direction in selection_input.directions.enabled_directions
    }
    return (
        *recommended_ids,
        *_interleave_lanes(remainder_lanes, selection_input.directions.enabled_directions),
    )


def _complementary_order(
    candidates: tuple[V2SourceSelectionCandidate, ...],
) -> tuple[V2SourceSelectionCandidate, ...]:
    families: dict[str, list[V2SourceSelectionCandidate]] = defaultdict(list)
    for candidate in candidates:
        families[candidate.source_family_id].append(candidate)
    for values in families.values():
        values.sort(key=_candidate_sort_key)
    family_order = sorted(families, key=lambda family: _candidate_sort_key(families[family][0]))
    ordered: list[V2SourceSelectionCandidate] = []
    while any(families.values()):
        for family in family_order:
            if families[family]:
                ordered.append(families[family].pop(0))
    return tuple(ordered)


def _candidate_sort_key(candidate: V2SourceSelectionCandidate) -> tuple[int, int, int, str]:
    primary = int(
        any(
            marker in (candidate.source_type or "").casefold()
            for marker in ("primary", "empirical", "government", "dataset", "study")
        )
    )
    return (
        -max(item.score for item in candidate.probe_passages),
        -primary,
        candidate.research_round,
        str(candidate.source_id),
    )


def _interleave_lanes(
    lanes: dict[ResearchDirection, list[object]],
    directions: tuple[ResearchDirection, ...],
) -> list[object]:
    result: list[object] = []
    index = 0
    while any(index < len(lanes[direction]) for direction in directions):
        for direction in directions:
            if index < len(lanes[direction]):
                result.append(lanes[direction][index])
        index += 1
    return result


def _source_reservation(
    preflight: object,
    candidate: V2SourceSelectionCandidate,
) -> tuple[int, Decimal]:
    totals: list[tuple[int, Decimal]] = []
    for stage, physical_attempts in (
        (LLMStage.EXTRACTOR, 2),
        (LLMStage.ANALYST, 1),
    ):
        reservation = preflight.reserve(stage, candidate.deep_analysis_input_tokens)
        for _ in range(physical_attempts):
            totals.append((reservation.reserved_tokens, reservation.reserved_cost_usd))
    return V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP, add_usd(*(item[1] for item in totals))


def _synthesis_reservation(preflight: object, queue_size: int) -> tuple[int, Decimal]:
    input_tokens = _SYNTHESIS_BASE_INPUT_TOKENS + queue_size * _SYNTHESIS_INPUT_TOKENS_PER_SOURCE
    reservation = preflight.reserve(LLMStage.SYNTHESIZER, input_tokens)
    return reservation.reserved_tokens * 2, add_usd(
        reservation.reserved_cost_usd,
        reservation.reserved_cost_usd,
    )


def _selection_attempt_is_safe(
    budget: V2DeepAnalysisBudget,
    attempts: Sequence[V2SourceSelectionAttempt],
    reservation: object,
    routing_config: V2RoutingConfig,
) -> bool:
    prior_tokens = sum(item.reserved_tokens for item in attempts)
    prior_cost = add_usd(*(item.reserved_cost_usd for item in attempts))
    synthesis_tokens, synthesis_cost = _synthesis_reservation(routing_config.preflight(), 0)
    return _fits(
        budget,
        physical_calls=len(attempts) + 1 + 2,
        tokens=prior_tokens + reservation.reserved_tokens + synthesis_tokens,
        cost=add_usd(prior_cost, reservation.reserved_cost_usd, synthesis_cost),
    )


def _budget_after_selection(
    budget: V2DeepAnalysisBudget,
    attempts: Sequence[V2SourceSelectionAttempt],
) -> V2DeepAnalysisBudget:
    reserved_tokens = sum(item.reserved_tokens for item in attempts)
    reserved_cost = add_usd(*(item.reserved_cost_usd for item in attempts))
    return V2DeepAnalysisBudget(
        physical_calls_used=budget.physical_calls_used + len(attempts),
        tokens_remaining=max(0, budget.tokens_remaining - reserved_tokens),
        cost_remaining_usd=_subtract_usd(budget.cost_remaining_usd, reserved_cost),
    )


def _fits(
    budget: V2DeepAnalysisBudget,
    *,
    physical_calls: int,
    tokens: int,
    cost: Decimal,
) -> bool:
    return (
        _limiting_reason(
            budget,
            physical_calls=physical_calls,
            tokens=tokens,
            cost=cost,
        )
        is None
    )


def _limiting_reason(
    budget: V2DeepAnalysisBudget,
    *,
    physical_calls: int,
    tokens: int,
    cost: Decimal,
) -> V2DeepAnalysisBudgetReason | None:
    if budget.physical_calls_used + physical_calls > budget.physical_call_ceiling:
        return V2DeepAnalysisBudgetReason.PHYSICAL_CALL_CEILING
    if tokens > budget.tokens_remaining:
        return V2DeepAnalysisBudgetReason.TOKEN_RESERVE
    if cost > budget.cost_remaining_usd:
        return V2DeepAnalysisBudgetReason.COST_RESERVE
    return None


def _subtract_usd(available: Decimal, used: Decimal) -> Decimal:
    if used >= available:
        return Decimal("0")
    precision = max(50, len(available.as_tuple().digits) + len(used.as_tuple().digits) + 10)
    with localcontext() as context:
        context.prec = precision
        return available - used


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("source-selection clock must return a timezone-aware datetime")


def _utc_now() -> datetime:
    return datetime.now(UTC)
