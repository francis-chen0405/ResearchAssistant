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
from providers.llm import (
    V2_LLM_ROUTING,
    LLMProvider,
    LLMRequest,
    LLMStage,
    invoke_llm,
    load_prompt,
    load_prompt_file,
    render_stage_prompt,
)
from providers.pricing import conservative_token_estimate
from providers.v2_budget import V2CancellationRequested
from providers.v2_routing import V2RoutingConfig
from researchassistant.common.money import add_usd
from researchassistant.contracts.discovery_v2 import V2PreviewRequest, V2PreviewResult, discovery_id
from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
from researchassistant.contracts.model_research import V2_PREVIEW_SELECTION_POLICY_IDENTITY
from researchassistant.contracts.models import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    ResearchDirection,
    SourceSnapshot,
    V2AcquisitionProbeOutput,
    V2ClaimCoverageAssessment,
    V2ClaimCoverageState,
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
    validate_v2_source_selection_gap_history,
)
from researchassistant.contracts.source_selection_preview import (
    V2SelectionOmission,
    V2SelectionShortlistAudit,
)
from researchassistant.evidence.evidence_portfolio import identify_source_family
from researchassistant.research.source_preview import build_claim_preview
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

V2_SOURCE_SELECTION_MAX_ATTEMPTS = 2
V2_SOURCE_SELECTION_LEGACY_POOL_KEY = "phase-8-complete-survivor-pool"
V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY = "phase-8-source-selection-deep-analysis-queue"
V2_SOURCE_SELECTION_POOL_KEY = "phase-13-complete-survivor-pool-analyzer-admission"
V2_SOURCE_SELECTION_COMPLETION_KEY = (
    "phase-13-source-selection-deep-analysis-queue-analyzer-admission"
)
V2_SOURCE_SELECTION_STATUS_KEY = "phase-13-source-statuses-analyzer-admission"
_RECOMMENDATION_TARGET_MAX = 10


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
    claim_aware: bool = False,
    asserted_components: tuple[str, ...] = (),
    metadata_ranking_outputs: tuple[V2MetadataRankingArtifact, ...] = (),
    preview_builder: Callable[[V2PreviewRequest, SourceSnapshot], V2PreviewResult] | None = None,
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
            claim_dimension=gap.claim_dimension,
            unsupported_claim_component=gap.unsupported_claim_component,
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
    rankings = {item.round_number: item for item in metadata_ranking_outputs}
    if len(rankings) != len(metadata_ranking_outputs):
        raise ValueError("selection metadata rankings must be unique by round")
    for number, ranking in rankings.items():
        discovery = discoveries.get(number)
        if discovery is None or {rank.item_id for rank in ranking.ranks} != {
            item.item_id for item in discovery.items
        }:
            raise ValueError("selection ranking differs from discovery membership")
    if any(item.run_id != run_id for item in metadata_ranking_outputs):
        raise ValueError("selection metadata ranking belongs to another run")
    fresh_preview = claim_aware or preview_builder is build_claim_preview
    if fresh_preview and preview_builder is None:
        preview_builder = build_claim_preview
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
        preview: V2PreviewResult | None = None
        if preview_builder is not None:
            key = f"selection-preview/{survivor.cluster_id}/{survivor.snapshot_id}"
            preview_request = V2PreviewRequest(
                run_id=run_id,
                artifact_id=discovery_id(run_id, "V2PreviewRequest", key),
                identity_key=key,
                exact_claim=exact_claim,
                direction=survivor.direction,
                directions=directions,
                source_id=survivor.cluster_id,
                snapshot_id=survivor.snapshot_id,
                snapshot_hash=survivor.snapshot_sha256,
                preview_identity="source-claim-preview-v2"
                if fresh_preview
                else "source-claim-preview-v1",
                asserted_components=asserted_components if fresh_preview else (),
                target_gaps=tuple(dict.fromkeys(gap.missing_evidence for gap in gap_rows))[:6]
                if fresh_preview
                else (),
            )
            preview = V2PreviewResult.model_validate(
                preview_builder(preview_request, source.snapshot).model_dump(mode="python")
            )
            if preview.request != preview_request:
                raise ValueError("selection preview differs from its exact claim/snapshot request")
            preview.require_snapshot(source.snapshot)
            if preview.outcome == "completed":
                selected_passages = tuple(
                    V2SourceSelectionProbePassage(
                        passage_id=f"preview:{preview.artifact_id}:{span.start}:{span.end}",
                        text=span.text if fresh_preview else span.text[:1200],
                        score=preview.relevance_score if fresh_preview else 0,
                    )
                    for span in preview.spans
                )
            elif fresh_preview:
                # Retain usable acquisition with explicit unknown/low relevance, no stale excerpts.
                selected_passages = ()
            # Historical callback unavailability retains the original Probe fallback.
        search_provenance = tuple(
            V2SourceSelectionSearchProvenance(
                query_id=item.query_id,
                provider=item.provider,
                round_number=item.round_number,
                query_text=item.query_text,
                graph_action=item.graph_action,
                targeted_gap_ids=item.targeted_gap_ids,
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
                preview=preview,
                metadata_ranks=tuple(
                    rank
                    for rank in rankings[merged.research_round].ranks
                    if rank.item_id in cluster.item_ids
                )
                if merged.research_round in rankings
                else (),
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
        gap_reporting_policy="conservative-v1",
        latest_gap_coverage=_latest_gap_coverage(gap_outputs),
        policy_identity=V2_PREVIEW_SELECTION_POLICY_IDENTITY
        if fresh_preview
        else "researchassistant-v2-phase-8-source-selection-v1",
    )


def _latest_gap_coverage(
    outputs: tuple[V2GapAnalysisOutput, ...],
) -> tuple[V2ClaimCoverageAssessment, ...]:
    for output in reversed(outputs):
        if output.result is not None and output.result.claim_coverage_map:
            return output.result.claim_coverage_map
    focus = next(
        (
            output.input.claim_coverage_focus
            for output in reversed(outputs)
            if output.input.claim_coverage_focus
        ),
        (),
    )
    return tuple(
        V2ClaimCoverageAssessment(
            **item.model_dump(),
            coverage_state=V2ClaimCoverageState.UNAVAILABLE,
            evidence_summary=(
                "No completed coverage assessment is available; coverage is unverified."
            ),
        )
        for item in focus
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
    validate_v2_source_selection_gap_history(selection_input.gap_history)
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
    fresh = selection_input.policy_identity == V2_PREVIEW_SELECTION_POLICY_IDENTITY
    prompt = (
        load_prompt_file(
            Path(__file__).resolve().parents[1] / "prompts" / "source_selection_v3.md",
            expected_stage=LLMStage.SOURCE_SELECTION,
        )
        if fresh
        else load_prompt(LLMStage.SOURCE_SELECTION)
    )
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
    if fresh:
        request, shortlist = _bounded_selection_request(request, selection_input, llm_provider)
        insert_v2_artifact(path, "source-selection-preview-shortlist-v2", shortlist, completed_at)
    attempts: list[V2SourceSelectionAttempt] = []
    recommendations: tuple[V2SourceSelectionRecommendation, ...] | None = None
    for attempt_number in range(1, V2_SOURCE_SELECTION_MAX_ATTEMPTS + 1):
        if request is None:
            break
        reservation = routing_config.preflight().reserve(
            LLMStage.SOURCE_SELECTION,
            _actual_input_tokens(llm_provider, request),
        )
        if not _selection_attempt_is_safe(
            budget,
            attempts,
            reservation,
            routing_config,
            protected_sources=selection_input.survivors if fresh else (),
        ):
            break
        try:
            invocation = invoke_llm(llm_provider, request, clock=now)
            output = V2SourceSelectionModelOutput.model_validate(
                invocation.output_artifact.model_dump(mode="python", round_trip=True)
            )
            recommendations = _validate_recommendations(request.input_artifact, output)
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


def _actual_input_tokens(provider: LLMProvider, request: LLMRequest) -> int:
    """Use the durable reservation owner's complete adapter input estimate."""
    minimum = conservative_token_estimate(request.rendered_prompt)
    estimator = getattr(provider, "conservative_input_tokens", None)
    tokens = estimator(request, minimum) if callable(estimator) else minimum
    if type(tokens) is not int or tokens < minimum:
        raise ValueError("selection input estimate cannot understate rendered input")
    return tokens


def _bounded_selection_request(
    request: LLMRequest,
    full_pool: V2SourceSelectionInput,
    provider: LLMProvider,
) -> tuple[LLMRequest | None, V2SelectionShortlistAudit]:
    """Select a stable fair prefix of whole sources; retain every omitted disposition."""
    cap = 24000
    lanes = {
        direction: list(
            _complementary_order(
                tuple(item for item in full_pool.survivors if item.direction is direction)
            )
        )
        for direction in full_pool.directions.enabled_directions
    }
    ordered = _interleave_lanes(lanes, full_pool.directions.enabled_directions)
    selected: list[V2SourceSelectionCandidate] = []
    fitted_request: LLMRequest | None = None
    fitted_tokens = 0
    for candidate in ordered:
        pool = full_pool.model_copy(update={"survivors": tuple((*selected, candidate))})
        proposal = request.model_copy(
            update={
                "input_artifact": pool,
                "input_artifact_ids": tuple(item.source_id for item in pool.survivors),
                "rendered_prompt": render_stage_prompt(
                    request.prompt, pool, V2SourceSelectionModelOutput
                ),
            }
        )
        tokens = _actual_input_tokens(provider, proposal)
        if tokens > cap:
            break
        selected.append(candidate)
        fitted_request, fitted_tokens = proposal, tokens
    included = tuple(item.source_id for item in selected)
    included_set = set(included)
    audit = V2SelectionShortlistAudit(
        run_id=full_pool.run_id,
        total_sources=len(full_pool.survivors),
        included_source_ids=included,
        rendered_input_tokens=fitted_tokens,
        omitted=tuple(
            V2SelectionOmission(
                source_id=item.source_id,
                reason=(
                    "Whole source omitted from model input by deterministic fair input-cap "
                    "prefix; retained for fallback/queue."
                ),
            )
            for item in full_pool.survivors
            if item.source_id not in included_set
        ),
    )
    return fitted_request, audit


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
    queued: list[UUID] = []
    reservation_points: list[V2DeepAnalysisTokenReservation] = []
    source_tokens = 0
    source_cost = Decimal("0")
    limiting_reason: V2DeepAnalysisBudgetReason | None = None
    for source_id in ordered_source_ids:
        candidate_tokens, candidate_cost = _source_reservation(
            preflight,
            candidates[source_id],
        )
        proposed_source_tokens = source_tokens + candidate_tokens
        proposed_source_cost = add_usd(source_cost, candidate_cost)
        physical_calls = (len(queued) + 1) * V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
        limiting_reason = _limiting_reason(
            budget,
            physical_calls=physical_calls,
            tokens=proposed_source_tokens,
            cost=proposed_source_cost,
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
                cumulative_reserved_tokens=source_tokens,
                cumulative_reserved_cost_usd=source_cost,
            )
        )

    if queued:
        total_tokens = reservation_points[-1].cumulative_reserved_tokens
        total_cost = reservation_points[-1].cumulative_reserved_cost_usd
        physical_after = (
            budget.physical_calls_used + len(queued) * V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
        )
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
        mandatory_synthesis_reservable=True,
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
                        + (
                            f" Preview: {candidate.preview.reason}"
                            if candidate.preview is not None
                            else ""
                        )
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
        -(
            candidate.preview.relevance_score
            if candidate.preview is not None
            and candidate.preview.request.preview_identity == "source-claim-preview-v2"
            else max((item.score for item in candidate.probe_passages), default=0)
        ),
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


def _selection_attempt_is_safe(
    budget: V2DeepAnalysisBudget,
    attempts: Sequence[V2SourceSelectionAttempt],
    reservation: object,
    routing_config: V2RoutingConfig,
    *,
    protected_sources: tuple[V2SourceSelectionCandidate, ...] = (),
) -> bool:
    prior_tokens = sum(item.reserved_tokens for item in attempts)
    prior_cost = add_usd(*(item.reserved_cost_usd for item in attempts))
    protected_tokens, protected_cost, protected_calls = 0, Decimal("0"), 0
    if protected_sources:
        protected_tokens, protected_cost = min(
            (
                _source_reservation(routing_config.preflight(), source)
                for source in protected_sources
            ),
            key=lambda value: (value[1], value[0]),
        )
        protected_calls = V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
    return _fits(
        budget,
        physical_calls=len(attempts) + 1 + protected_calls,
        tokens=prior_tokens + reservation.reserved_tokens + protected_tokens,
        cost=add_usd(prior_cost, reservation.reserved_cost_usd, protected_cost),
    )


def _budget_after_selection(
    budget: V2DeepAnalysisBudget,
    attempts: Sequence[V2SourceSelectionAttempt],
) -> V2DeepAnalysisBudget:
    reserved_tokens = sum(item.reserved_tokens for item in attempts)
    reserved_cost = add_usd(*(item.reserved_cost_usd for item in attempts))
    return V2DeepAnalysisBudget(
        physical_call_ceiling=budget.physical_call_ceiling,
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
