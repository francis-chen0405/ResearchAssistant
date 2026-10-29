"""One optional evidence-driven round after final source admission.

The earlier admission remains an immutable input. A successful follow-up admits only
new source identities, then builds a validated aggregate view for final synthesis.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict, Field

from researchassistant.agents.adaptive_execution import (
    _run_round_from_plan,
    search_failure_explanation,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveBudgetError,
    V2AdaptiveNoContinuationError,
    V2AdaptiveNoEligibleProviderError,
    V2AdaptivePlanValidationError,
    round_artifact_key,
)
from researchassistant.agents.adaptive_planning import _plan_round
from researchassistant.agents.adaptive_summary import _known_urls, _merge_survivors
from researchassistant.agents.round_four_authorization import (
    _fits_reserve,
    _gap_envelope_fits,
    _gap_reservation,
    _provider_attempts,
)
from researchassistant.agents.round_four_handoffs import V2RoundFourRunResult
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveContinuationResult,
    V2AdaptiveRoundStatus,
    V2AdaptiveStopCode,
)
from researchassistant.agents.v2_deep_analysis import run_v2_deep_analysis_with_backfill
from researchassistant.agents.v2_discovery import V2_SCOUT_BATCH_SIZE
from researchassistant.agents.v2_gap_analysis import run_v2_gap_analysis
from researchassistant.agents.v2_post_analysis import build_v2_post_analysis_assessment
from researchassistant.agents.v2_round_four import run_v2_round_four_continuation
from researchassistant.agents.v2_source_selection import (
    build_v2_source_selection_input,
    calculate_v2_deep_analysis_queue,
)
from researchassistant.common.money import add_usd
from researchassistant.contracts.discovery_v2 import SearchMode
from researchassistant.contracts.model_evidence import (
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystBatchResult,
)
from researchassistant.contracts.models import (
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2DeepAnalysisBudget,
    V2DiscoveryScoutOutput,
    V2GapAnalysisOutput,
    V2GapBudgetState,
    V2InitialPlannerOutput,
    V2SourceSelectionGap,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
)
from researchassistant.contracts.source_recovery import AssessedSourceFinding
from researchassistant.providers.llm import LLMProvider, LLMStage
from researchassistant.providers.scraper import ScraperProvider
from researchassistant.providers.search import SearchProvider
from researchassistant.providers.v2_budget import V2CancellationRequested
from researchassistant.providers.v2_routing import V2ModelReservation, V2RoutingConfig
from researchassistant.storage.discovery_store import read_discovery_binding
from researchassistant.storage.query_dispatch import query_dispatch_states
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

POST_ANALYSIS_DECISION_KEY = "post-analysis-evidence-round-decision-v1"
POST_ANALYSIS_COMPLETION_KEY = "post-analysis-evidence-round-completion-v1"
POST_ANALYSIS_GAP_KEY = "post-analysis-evidence-gap-v1"
POST_ANALYSIS_QUEUE_KEY = "post-analysis-evidence-queue-v1"
POST_ANALYSIS_BACKFILL_KEY = "post-analysis-evidence-backfill-v1"
POST_ANALYSIS_ADMISSION_KEY = "post-analysis-evidence-admission-v1"
POST_ANALYSIS_COMBINED_KEY = "post-analysis-combined-admission-v1"


class V2PostAnalysisRoundDecision(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_rounds: int = Field(ge=1, le=4)
    next_round: int | None = Field(default=None, ge=2, le=4)
    reason: str = Field(min_length=1)
    targeted_gap_ids: tuple[str, ...] = ()
    assessed_source_ids: tuple[UUID, ...] = ()
    decided_at: datetime


class V2PostAnalysisRoundOutcome(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    decision: V2PostAnalysisRoundDecision
    continuation: V2AdaptiveContinuationResult
    admission: V2EvidenceAdmissionBatchResult
    stop_reason: str = Field(min_length=1)
    new_source_ids: tuple[UUID, ...] = ()
    round_four_gap: V2GapAnalysisOutput | None = None
    completed_at: datetime


def run_v2_post_analysis_round(
    *,
    db_path: str | Path,
    initial_plan: V2InitialPlannerOutput,
    continuation: V2AdaptiveContinuationResult,
    admission: V2EvidenceAdmissionBatchResult,
    discoveries: tuple[V2DiscoveryScoutOutput, ...],
    acquisitions: tuple[V2AcquisitionProbeOutput, ...],
    gaps: tuple[V2GapAnalysisOutput, ...],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState],
    deep_budget_snapshot: Callable[[], V2DeepAnalysisBudget],
    cancellation_requested: Callable[[], bool],
    clock: Callable[[], datetime],
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
) -> V2PostAnalysisRoundOutcome:
    """Use at most the next unused round; every physical stage keeps its own checkpoint."""
    path = str(Path(db_path).resolve())
    run_id = initial_plan.run_id
    if (
        continuation.run_id != run_id
        or admission.run_id != run_id
        or admission.analyst_result.input.exact_claim != initial_plan.raw_claim
    ):
        raise ValueError("post-analysis inputs differ from the admitted run")
    input_hash = sha256(
        (admission.model_dump_json() + continuation.model_dump_json()).encode("utf-8")
    ).hexdigest()
    saved = _read(path, run_id, POST_ANALYSIS_COMPLETION_KEY, V2PostAnalysisRoundOutcome)
    if saved is not None:
        if saved.decision.input_sha256 != input_hash:
            raise ValueError("post-analysis replay input changed")
        return saved

    previous_rounds = continuation.stopping_decision.completed_rounds
    existing = _read(path, run_id, POST_ANALYSIS_DECISION_KEY, V2PostAnalysisRoundDecision)
    if existing is not None and existing.input_sha256 != input_hash:
        raise ValueError("post-analysis decision input changed")

    def decide(
        reason: str,
        *,
        round_number: int | None = None,
        gap_ids: tuple[str, ...] = (),
        source_ids: tuple[UUID, ...] = (),
    ) -> V2PostAnalysisRoundDecision:
        decision = V2PostAnalysisRoundDecision(
            run_id=run_id,
            input_sha256=input_hash,
            previous_rounds=previous_rounds,
            next_round=round_number,
            reason=reason,
            targeted_gap_ids=gap_ids,
            assessed_source_ids=source_ids,
            decided_at=clock(),
        )
        if existing is not None and existing != decision:
            # A resumed dispatch must keep the original decision timestamp and inputs.
            if existing.model_dump(exclude={"decided_at"}) != decision.model_dump(
                exclude={"decided_at"}
            ):
                raise ValueError("post-analysis decision changed during replay")
            return existing
        insert_v2_artifact(path, POST_ANALYSIS_DECISION_KEY, decision, decision.decided_at)
        return decision

    def finish(
        decision: V2PostAnalysisRoundDecision,
        reason: str,
        *,
        final_continuation: V2AdaptiveContinuationResult = continuation,
        final_admission: V2EvidenceAdmissionBatchResult = admission,
        new_ids: tuple[UUID, ...] = (),
        assessed_gap: V2GapAnalysisOutput | None = None,
        round_four_gap: V2GapAnalysisOutput | None = None,
    ) -> V2PostAnalysisRoundOutcome:
        if final_admission is admission and (assessed_gap or round_four_gap):
            final_admission = _attach_assessed_gap(admission, assessed_gap or round_four_gap)
        if any(
            state in {"unknown", "blocked"}
            for state in query_dispatch_states(path, run_id).values()
        ):
            interruption = (
                "A provider request has an unknown outcome; its reservation is retained "
                "and additional searches were blocked. Existing evidence was preserved."
            )
            reason = f"{reason}. {interruption}"
            prior = final_continuation.stopping_decision
            final_continuation = final_continuation.model_copy(
                update={
                    "stopping_decision": final_continuation.stopping_decision.model_copy(
                        update={
                            "stop_code": V2AdaptiveStopCode.PROVIDER_FAILURE,
                            "stopping_reason": (
                                f"{prior.stopping_reason} {interruption}"
                                if prior.stop_code is V2AdaptiveStopCode.PROVIDER_FAILURE
                                else interruption
                            ),
                            "decided_at": decision.decided_at,
                        }
                    )
                }
            )
        result = V2PostAnalysisRoundOutcome(
            run_id=run_id,
            decision=decision,
            continuation=final_continuation,
            admission=final_admission,
            stop_reason=reason,
            new_source_ids=new_ids,
            round_four_gap=round_four_gap,
            completed_at=clock(),
        )
        insert_v2_artifact(path, POST_ANALYSIS_COMPLETION_KEY, result, result.completed_at)
        return result

    if cancellation_requested():
        raise V2CancellationRequested("cancelled before post-analysis decision")
    round_four_result: V2RoundFourRunResult | None = None
    if existing is not None:
        if existing.next_round is None:
            return finish(existing, existing.reason)
        next_round = existing.next_round
        if next_round == 4:
            findings = _assessed_findings(admission, gaps[-1])
            round_four_result = run_v2_round_four_continuation(
                db_path=path,
                initial_plan=initial_plan,
                continuation=continuation,
                discovery_outputs=discoveries,
                acquisition_outputs=acquisitions,
                search_providers=search_providers,
                llm_provider=llm_provider,
                routing_config=routing_config,
                wigolo_provider=wigolo_provider,
                firecrawl_provider=firecrawl_provider,
                crossref_resolver=crossref_resolver,
                budget=budget_snapshot(),
                budget_snapshot=budget_snapshot,
                cancellation_requested=cancellation_requested,
                clock=clock,
                assessed_source_findings=findings,
            )
            gap = round_four_result.post_round_three_gap
        else:
            saved_gap = _read(path, run_id, POST_ANALYSIS_GAP_KEY, V2GapAnalysisOutput)
            if saved_gap is None:
                raise ValueError("authorized post-analysis round has no saved Gap result")
            gap = saved_gap
        decision = existing
    elif previous_rounds == 3:
        next_round = 4
        if (
            not continuation.rounds
            or continuation.rounds[-1].round_number != 3
            or continuation.rounds[-1].status is not V2AdaptiveRoundStatus.COMPLETED
        ):
            decision = decide("prior round did not complete safely")
            return finish(decision, decision.reason)
        if any(
            state in {"unknown", "blocked"}
            for state in query_dispatch_states(path, run_id).values()
        ):
            decision = decide("unknown request reservation blocks another dispatch")
            return finish(decision, decision.reason)
        if (
            len(continuation.merged_survivors.sources)
            + read_discovery_binding(path, run_id).policy.max_acquisition_per_round
            > 240
        ):
            decision = decide("insufficient room within the overall survivor ceiling")
            return finish(decision, decision.reason)
        if not gaps:
            decision = decide("no prior claim-gap input is available")
            return finish(decision, decision.reason)
        coverage = admission.analyst_result.input.queue_result.input.latest_gap_coverage
        assessment = build_v2_post_analysis_assessment(
            admission_result=admission,
            coverage=coverage,
            unresolved_gap_count=len(gaps[-1].result.material_gaps)
            if gaps[-1].result is not None
            else 0,
        )
        if assessment.search_outcome == "analysis_complete":
            decision = decide("admitted evidence and claim coverage are adequate")
            return finish(decision, decision.reason)
        findings = _assessed_findings(admission, gaps[-1])
        round_four_result = run_v2_round_four_continuation(
            db_path=path,
            initial_plan=initial_plan,
            continuation=continuation,
            discovery_outputs=discoveries,
            acquisition_outputs=acquisitions,
            search_providers=search_providers,
            llm_provider=llm_provider,
            routing_config=routing_config,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            crossref_resolver=crossref_resolver,
            budget=budget_snapshot(),
            budget_snapshot=budget_snapshot,
            cancellation_requested=cancellation_requested,
            clock=clock,
            assessed_source_findings=findings,
        )
        gap = round_four_result.post_round_three_gap
        if cancellation_requested() or (
            round_four_result.continuation.stopping_decision.stop_code
            is V2AdaptiveStopCode.CANCELLED
        ):
            raise V2CancellationRequested("cancelled during post-analysis Round 4")
        if (
            round_four_result.continuation.stopping_decision.completed_rounds != 4
            or not round_four_result.continuation.rounds
            or round_four_result.continuation.rounds[-1].status
            is not V2AdaptiveRoundStatus.COMPLETED
        ):
            reason = (
                f"Round-4 governor stopped: {round_four_result.governor_decision.reason_code.value}"
            )
            decision = decide(reason)
            return finish(
                decision,
                reason,
                final_continuation=round_four_result.continuation,
                round_four_gap=gap,
            )
        decision = decide(
            "one gap-driven follow-up authorized by Round-4 governor",
            round_number=4,
            gap_ids=tuple(item.gap_id for item in gap.result.material_gaps)
            if gap.result is not None
            else (),
            source_ids=tuple(item.source_id for item in findings),
        )
    else:
        if previous_rounds >= 4:
            decision = decide("overall round ceiling reached")
            return finish(decision, decision.reason)
        next_round = previous_rounds + 1
        if _has_artifact(path, run_id, f"phase-7-round-{next_round}-plan"):
            decision = decide("existing round plan has a different authorization")
            return finish(decision, decision.reason)
        if any(
            state in {"unknown", "blocked"}
            for state in query_dispatch_states(path, run_id).values()
        ):
            decision = decide("unknown request reservation blocks another dispatch")
            return finish(decision, decision.reason)
        survivor_count = len(continuation.merged_survivors.sources)
        acquisition_capacity = read_discovery_binding(path, run_id).policy.max_acquisition_per_round
        if survivor_count + acquisition_capacity > 240:
            decision = decide("insufficient room within the overall survivor ceiling")
            return finish(decision, decision.reason)
        coverage = admission.analyst_result.input.queue_result.input.latest_gap_coverage
        assessment = build_v2_post_analysis_assessment(
            admission_result=admission,
            coverage=coverage,
            unresolved_gap_count=len(gaps[-1].result.material_gaps)
            if gaps and gaps[-1].result is not None
            else 0,
        )
        if assessment.search_outcome == "analysis_complete":
            decision = decide("admitted evidence and claim coverage are adequate")
            return finish(decision, decision.reason)
        budget = budget_snapshot()
        if not gaps:
            decision = decide("no prior claim-gap input is available")
            return finish(decision, decision.reason)
        findings = _assessed_findings(admission, gaps[-1])
        gap_input = gaps[-1].input.model_copy(
            update={
                "assessed_source_findings": findings,
                "remaining_budget": V2GapBudgetState(
                    model_calls_remaining=budget.model_calls_remaining,
                    tokens_remaining=budget.tokens_remaining,
                    cost_remaining_usd=budget.cost_remaining_usd,
                ),
            }
        )
        gap_input = type(gaps[-1].input).model_validate(gap_input.model_dump())
        saved_gap = _has_artifact(path, run_id, POST_ANALYSIS_GAP_KEY)
        if not saved_gap and (
            not _gap_envelope_fits(budget, gap_input, routing_config)
            or not _source_budget_fits(
                budget,
                routing_config,
                gap_reservation=_gap_reservation(gap_input, routing_config),
            )
        ):
            decision = decide("insufficient complete protected follow-up budget")
            return finish(decision, decision.reason)
        gap = run_v2_gap_analysis(
            db_path=path,
            gap_input=gap_input,
            llm_provider=llm_provider,
            routing_config=routing_config,
            artifact_key=POST_ANALYSIS_GAP_KEY,
            clock=clock,
        )
        if cancellation_requested():
            raise V2CancellationRequested("cancelled after post-analysis gap assessment")
        if gap.result is None or not gap.result.continue_research or not gap.result.material_gaps:
            decision = decide("no useful novel evidence-gap action")
            return finish(decision, decision.reason, assessed_gap=gap)
        budget = budget_snapshot()
        if not _source_budget_fits(budget, routing_config) and not _has_artifact(
            path, run_id, f"phase-7-round-{next_round}-plan"
        ):
            decision = decide("insufficient protected source-assessment budget")
            return finish(decision, decision.reason, assessed_gap=gap)
        decision = decide(
            "one gap-driven follow-up authorized",
            round_number=next_round,
            gap_ids=tuple(item.gap_id for item in gap.result.material_gaps),
            source_ids=tuple(item.source_id for item in findings),
        )
    budget = budget_snapshot()
    if any(
        state in {"unknown", "blocked"} for state in query_dispatch_states(path, run_id).values()
    ):
        return finish(
            decision,
            "unknown request reservation blocks follow-up replay",
            assessed_gap=gap,
        )
    if round_four_result is not None:
        discovery = _read(
            path,
            run_id,
            round_artifact_key(4, "discovery-scout"),
            V2DiscoveryScoutOutput,
        )
        acquisition = _read(
            path,
            run_id,
            round_artifact_key(4, "acquisition-probe"),
            V2AcquisitionProbeOutput,
        )
        if discovery is None or acquisition is None:
            raise ValueError("completed post-analysis Round 4 lacks saved source artifacts")
        summary = round_four_result.continuation.rounds[-1]
    else:
        previous_queries = tuple(q.query_text for q in initial_plan.searches)
        previous_actions = tuple(
            q.compiled_query for q in initial_plan.searches if q.compiled_query is not None
        )
        for round_number in range(2, next_round):
            prior = _read_payload(path, run_id, f"phase-7-round-{round_number}-plan")
            if prior is not None:
                from researchassistant.agents.v2_adaptive_search import (
                    V2AdaptivePlannedRound,
                )

                plan = V2AdaptivePlannedRound.model_validate_json(prior)
                previous_queries += tuple(q.query_text for q in plan.plan.searches if q.query_text)
                previous_actions += tuple(
                    q.compiled_query for q in plan.plan.searches if q.compiled_query is not None
                )
        try:
            planned = _plan_round(
                path=path,
                round_number=next_round,
                initial_plan=initial_plan,
                gap_output=gap,
                previous_queries=previous_queries,
                provider_attempts=_provider_attempts(initial_plan, path),
                previous_compiled_queries=previous_actions,
                search_providers=search_providers,
                llm_provider=llm_provider,
                routing_config=routing_config,
                query_modes=query_modes,
                legacy_prompt=False,
                budget=budget,
                budget_snapshot=budget_snapshot,
                cancellation_requested=cancellation_requested,
                clock=clock,
            )
        except (
            V2AdaptiveBudgetError,
            V2AdaptiveNoContinuationError,
            V2AdaptiveNoEligibleProviderError,
            V2AdaptivePlanValidationError,
        ) as exc:
            return finish(
                decision,
                f"follow-up planning stopped: {type(exc).__name__}",
                assessed_gap=gap,
            )
        if not _source_budget_fits(
            budget_snapshot(),
            routing_config,
            planned_queries=len(planned.plan.searches),
        ) and not _has_artifact(path, run_id, round_artifact_key(next_round, "search-results")):
            return finish(
                decision,
                "insufficient complete follow-up budget before dispatch",
                assessed_gap=gap,
            )
        search, discovery, acquisition, summary = _run_round_from_plan(
            path=path,
            planned=planned,
            exact_claim=initial_plan.raw_claim,
            asserted_components=tuple(x.claim_component for x in initial_plan.claim_coverage_focus),
            preview_gaps=tuple(item.missing_evidence for item in gap.result.material_gaps),
            search_providers=search_providers,
            llm_provider=llm_provider,
            routing_config=routing_config,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            crossref_resolver=crossref_resolver,
            known_urls=_known_urls(discoveries),
            cancellation_requested=cancellation_requested,
            clock=clock,
        )
    if summary.status is V2AdaptiveRoundStatus.CANCELLED or cancellation_requested():
        raise V2CancellationRequested("cancelled during post-analysis follow-up")
    if summary.status is V2AdaptiveRoundStatus.DEGRADED:
        if round_four_result is not None:
            failed = round_four_result.continuation
        else:
            failed = continuation.model_copy(
                update={
                    "rounds": (*continuation.rounds, summary),
                    "stopping_decision": continuation.stopping_decision.model_copy(
                        update={
                            "completed_rounds": next_round,
                            "stop_code": V2AdaptiveStopCode.PROVIDER_FAILURE,
                            "stopping_reason": search_failure_explanation(path, search),
                            "decided_at": clock(),
                        }
                    ),
                    "completed_at": clock(),
                }
            )
        return finish(
            decision,
            "follow-up search degraded; earlier evidence retained",
            final_continuation=failed,
            assessed_gap=gap,
            round_four_gap=gap if round_four_result is not None else None,
        )
    all_discoveries = (*discoveries, discovery)
    all_acquisitions = (*acquisitions, acquisition)
    merged = _merge_survivors(
        run_id,
        tuple(
            (n, d, a)
            for n, (d, a) in enumerate(zip(all_discoveries, all_acquisitions, strict=True), 1)
        ),
        deduplicate_papers=True,
    )
    existing_ids = {item.survivor.cluster_id for item in continuation.merged_survivors.sources}
    new_ids = tuple(
        item.survivor.cluster_id
        for item in merged.sources
        if item.survivor.cluster_id not in existing_ids
    )
    updated = continuation.model_copy(
        update={
            "rounds": (*continuation.rounds, summary),
            "merged_survivors": merged,
            "stopping_decision": continuation.stopping_decision.model_copy(
                update={
                    "completed_rounds": next_round,
                    "stop_code": V2AdaptiveStopCode.ROUND_TWO_COMPLETE
                    if next_round == 2
                    else V2AdaptiveStopCode.ROUND_THREE_COMPLETE
                    if next_round == 3
                    else V2AdaptiveStopCode.ROUND_FOUR_COMPLETE,
                    "stopping_reason": (
                        "One post-analysis evidence round completed; no further round is permitted."
                    ),
                    "decided_at": clock(),
                }
            ),
            "completed_at": clock(),
        }
    )
    if round_four_result is not None:
        updated = round_four_result.continuation
    if not new_ids:
        return finish(
            decision,
            "follow-up found no novel retained source",
            final_continuation=updated,
            assessed_gap=gap,
            round_four_gap=gap if round_four_result is not None else None,
        )
    # The assessment Gap can repeat a same-round ID from the earlier strategy Gap.
    # Retain its newer wording/coverage while keeping all distinct older gaps.
    gap_outputs = _unique_gap_outputs((*gaps, gap))
    full_input = build_v2_source_selection_input(
        exact_claim=initial_plan.raw_claim,
        merged_survivors=merged,
        discovery_outputs=all_discoveries,
        acquisition_outputs=all_acquisitions,
        gap_outputs=gap_outputs,
        claim_aware=True,
        compact_model_view=True,
        asserted_components=tuple(x.claim_component for x in initial_plan.claim_coverage_focus),
    )
    old_queue = admission.analyst_result.input.queue_result
    new_candidates = tuple(item for item in full_input.survivors if item.source_id in new_ids)
    new_input = V2SourceSelectionInput.model_validate(
        full_input.model_copy(update={"survivors": new_candidates}).model_dump()
    )
    new_queue = _read(path, run_id, POST_ANALYSIS_QUEUE_KEY, V2SourceSelectionQueueResult)
    if new_queue is not None:
        if new_queue.input != new_input:
            raise ValueError("saved follow-up queue differs from its source identities")
    else:
        before = deep_budget_snapshot()
        queue_plan = calculate_v2_deep_analysis_queue(
            selection_input=new_input,
            ordered_source_ids=tuple(item.source_id for item in new_candidates),
            recommended_source_ids=(),
            routing_config=routing_config,
            budget=before,
        )
        new_queue = V2SourceSelectionQueueResult(
            run_id=run_id,
            input=new_input,
            initial_budget=before,
            recommended_source_ids=(),
            recommendation_rationales=(),
            used_fallback=True,
            selection_attempts=0,
            selection_attempt_records=(),
            priority_source_ids=tuple(item.source_id for item in new_candidates),
            queued_source_ids=queue_plan.queued_source_ids,
            source_statuses=queue_plan.source_statuses,
            queue_capacity=queue_plan.queue_capacity,
            mandatory_synthesis_reservable=queue_plan.mandatory_synthesis_reservable,
            physical_calls_after_reserve=queue_plan.physical_calls_after_reserve,
            total_reserved_tokens=queue_plan.total_reserved_tokens,
            total_reserved_cost_usd=queue_plan.total_reserved_cost_usd,
            token_reservations=queue_plan.token_reservations,
            limiting_reason=queue_plan.limiting_reason,
            completed_at=clock(),
        )
        insert_v2_artifact(path, POST_ANALYSIS_QUEUE_KEY, new_queue, new_queue.completed_at)
    if not new_queue.queued_source_ids:
        return finish(
            decision,
            "budget cannot assess a novel source",
            final_continuation=updated,
            assessed_gap=gap,
            round_four_gap=gap if round_four_result is not None else None,
        )
    extra = run_v2_deep_analysis_with_backfill(
        db_path=path,
        queue_result=new_queue,
        discovery_outputs=all_discoveries,
        acquisition_outputs=all_acquisitions,
        llm_provider=llm_provider,
        routing_config=routing_config,
        cancellation_requested=cancellation_requested,
        clock=clock,
        artifact_key=POST_ANALYSIS_BACKFILL_KEY,
        admission_artifact_key=POST_ANALYSIS_ADMISSION_KEY,
    )
    if extra.final_admission_result is None:
        raise ValueError("post-analysis deep analysis did not retain admission")
    combined = _combine_admissions(
        admission,
        extra.final_admission_result,
        full_input,
        old_queue,
        extra.final_queue_result,
    )
    insert_v2_artifact(path, POST_ANALYSIS_COMBINED_KEY, combined, combined.completed_at)
    return finish(
        decision,
        "one evidence-gap follow-up assessed; prior evidence retained",
        final_continuation=updated,
        final_admission=combined,
        new_ids=new_ids,
        round_four_gap=gap if round_four_result is not None else None,
    )


def _assessed_findings(
    admission: V2EvidenceAdmissionBatchResult, gap: V2GapAnalysisOutput
) -> tuple[AssessedSourceFinding, ...]:
    visible_ids = {item.source_cluster_id for item in gap.input.surviving_sources}
    assessed = admission.analyst_result.source_results
    visible = tuple(item for item in assessed if item.source_id in visible_ids)
    reviewed = sorted(
        (item for item in visible if item.assessment is not None),
        key=lambda item: (
            item.assessment.relationship_to_claim.value,
            str(item.source_id),
        ),
    )
    failed = sorted(
        (item for item in visible if item.assessment is None),
        key=lambda item: (item.state.value, str(item.source_id)),
    )
    ranked = (*reviewed[:2], *failed[:2], *reviewed[2:], *failed[2:])
    rows: list[AssessedSourceFinding] = []
    for item in ranked[:4]:
        assessment = item.assessment
        rows.append(
            AssessedSourceFinding(
                source_id=item.source_id,
                direction=item.direction,
                outcome=item.state.value,
                supported_proposition=assessment.narrowest_supported_proposition
                if assessment
                else None,
                relationship_to_claim=assessment.relationship_to_claim.value
                if assessment
                else None,
                limitations=tuple(
                    text[:500]
                    for text in (
                        *assessment.material_limitations,
                        *assessment.inferential_boundaries,
                    )[:12]
                )
                if assessment
                else (),
                failure=item.failure[:1000] if item.failure else None,
            )
        )
    return tuple(rows)


def _source_budget_fits(
    budget: V2AdaptiveBudgetState,
    routing_config: V2RoutingConfig,
    *,
    gap_reservation: V2ModelReservation | None = None,
    planned_queries: int = 1,
) -> bool:
    """Keep one source assessment and finalization affordable before provider dispatch."""
    preflight = routing_config.preflight()
    extractor = preflight.reserve(LLMStage.EXTRACTOR, 3_000)
    analyst = preflight.reserve(LLMStage.ANALYST, 3_000)
    scout = preflight.reserve(LLMStage.SCOUT, 1)
    scout_calls = (
        (max(1, planned_queries) * 5 + V2_SCOUT_BATCH_SIZE - 1) // V2_SCOUT_BATCH_SIZE
    ) * 2
    calls = 3 + scout_calls
    tokens = V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP + scout_calls * scout.reserved_tokens
    cost_components = [
        extractor.reserved_cost_usd,
        extractor.reserved_cost_usd,
        analyst.reserved_cost_usd,
        *(scout.reserved_cost_usd for _ in range(scout_calls)),
    ]
    if planned_queries == 1 and gap_reservation is not None:
        search = preflight.reserve(LLMStage.SEARCH_AGENT, 4_000)
        calls += 3
        tokens += 2 * gap_reservation.reserved_tokens + search.reserved_tokens
        cost_components.extend(
            (
                gap_reservation.reserved_cost_usd,
                gap_reservation.reserved_cost_usd,
                search.reserved_cost_usd,
            )
        )
    elif planned_queries == 1:
        search = preflight.reserve(LLMStage.SEARCH_AGENT, 4_000)
        calls += 1
        tokens += search.reserved_tokens
        cost_components.append(search.reserved_cost_usd)
    cost = add_usd(*cost_components)
    return _fits_reserve(budget, calls=calls, tokens=tokens, cost=cost)


def _unique_gap_outputs(
    outputs: tuple[V2GapAnalysisOutput, ...],
) -> tuple[V2GapAnalysisOutput, ...]:
    """Prefer the assessed Gap when an earlier strategy Gap used the same ID."""
    seen: set[tuple[int, str]] = set()
    retained: list[V2GapAnalysisOutput] = []
    for output in reversed(outputs):
        if output.result is None:
            retained.append(output)
            continue
        gaps = tuple(
            gap
            for gap in output.result.material_gaps
            if (output.input.completed_round, gap.gap_id) not in seen
        )
        seen.update((output.input.completed_round, gap.gap_id) for gap in gaps)
        retained.append(
            output.model_copy(
                update={"result": output.result.model_copy(update={"material_gaps": gaps})}
            )
        )
    return tuple(reversed(retained))


def _attach_assessed_gap(
    admission: V2EvidenceAdmissionBatchResult,
    gap: V2GapAnalysisOutput,
) -> V2EvidenceAdmissionBatchResult:
    """Add a saved assessed Gap to the final view without changing prior records."""
    if gap.result is None:
        return admission
    original_queue = admission.analyst_result.input.queue_result
    original_input = original_queue.input
    new_ids = {item.gap_id for item in gap.result.material_gaps}
    history = tuple(
        item
        for item in original_input.gap_history
        if not (item.assessed_after_round == gap.input.completed_round and item.gap_id in new_ids)
    ) + tuple(
        V2SourceSelectionGap(
            gap_id=item.gap_id,
            direction=item.direction,
            missing_evidence=item.missing_evidence,
            claim_dimension=item.claim_dimension,
            unsupported_claim_component=item.unsupported_claim_component,
            assessed_after_round=gap.input.completed_round,
        )
        for item in gap.result.material_gaps
    )
    updated_input = V2SourceSelectionInput.model_validate(
        original_input.model_copy(
            update={
                "gap_history": history,
                "latest_gap_coverage": (
                    gap.result.claim_coverage_map or original_input.latest_gap_coverage
                ),
            }
        ).model_dump()
    )
    updated_queue = V2SourceSelectionQueueResult.model_validate(
        original_queue.model_copy(update={"input": updated_input}).model_dump()
    )
    analyst = admission.analyst_result
    analyst_input = V2EvidenceAnalystBatchInput.model_validate(
        analyst.input.model_copy(update={"queue_result": updated_queue}).model_dump()
    )
    updated_analyst = V2EvidenceAnalystBatchResult.model_validate(
        analyst.model_copy(update={"input": analyst_input}).model_dump()
    )
    return V2EvidenceAdmissionBatchResult.model_validate(
        admission.model_copy(update={"analyst_result": updated_analyst}).model_dump()
    )


def _combine_admissions(
    earlier: V2EvidenceAdmissionBatchResult,
    later: V2EvidenceAdmissionBatchResult,
    full_input: V2SourceSelectionInput,
    old_queue: V2SourceSelectionQueueResult,
    new_queue: V2SourceSelectionQueueResult,
) -> V2EvidenceAdmissionBatchResult:
    """Validate one final view without re-admitting or rewriting either source batch."""
    if earlier.run_id != later.run_id or earlier.policy_identity != later.policy_identity:
        raise ValueError("post-analysis evidence batches are incompatible")
    old_ids = {item.source_id for item in old_queue.input.survivors}
    if old_ids.intersection(item.source_id for item in new_queue.input.survivors):
        raise ValueError("post-analysis source identity overlaps prior admission")
    input_with_originals = V2SourceSelectionInput.model_validate(
        full_input.model_copy(
            update={"survivors": (*old_queue.input.survivors, *new_queue.input.survivors)}
        ).model_dump()
    )
    rank_offset = len(old_queue.queued_source_ids)
    statuses = (
        *old_queue.source_statuses,
        *(
            item.model_copy(update={"queue_rank": item.queue_rank + rank_offset})
            if item.queue_rank is not None
            else item
            for item in new_queue.source_statuses
        ),
    )
    combined_queue = V2SourceSelectionQueueResult(
        run_id=earlier.run_id,
        input=input_with_originals,
        initial_budget=old_queue.initial_budget,
        recommended_source_ids=old_queue.recommended_source_ids,
        recommendation_rationales=old_queue.recommendation_rationales,
        used_fallback=old_queue.used_fallback,
        selection_attempts=old_queue.selection_attempts,
        selection_attempt_records=old_queue.selection_attempt_records,
        priority_source_ids=(
            *old_queue.priority_source_ids,
            *new_queue.priority_source_ids,
        ),
        queued_source_ids=(*old_queue.queued_source_ids, *new_queue.queued_source_ids),
        source_statuses=statuses,
        queue_capacity=old_queue.queue_capacity + new_queue.queue_capacity,
        mandatory_synthesis_reservable=old_queue.mandatory_synthesis_reservable,
        physical_calls_after_reserve=max(
            old_queue.physical_calls_after_reserve,
            new_queue.physical_calls_after_reserve,
        ),
        total_reserved_tokens=old_queue.total_reserved_tokens + new_queue.total_reserved_tokens,
        total_reserved_cost_usd=_combined_queue_cost(
            old_queue.total_reserved_cost_usd,
            new_queue.total_reserved_cost_usd,
        ),
        token_reservations=(
            *old_queue.token_reservations,
            *new_queue.token_reservations,
        ),
        limiting_reason=new_queue.limiting_reason or old_queue.limiting_reason,
        completed_at=new_queue.completed_at,
    )
    first = earlier.analyst_result
    second = later.analyst_result
    analyst_input = V2EvidenceAnalystBatchInput(
        run_id=earlier.run_id,
        exact_claim=first.input.exact_claim,
        directions=first.input.directions,
        queue_result=combined_queue,
        queued_candidates=(
            *first.input.queued_candidates,
            *second.input.queued_candidates,
        ),
        extraction_failures=(
            *first.input.extraction_failures,
            *second.input.extraction_failures,
        ),
        policy_identity=first.input.policy_identity,
    )
    analyst = V2EvidenceAnalystBatchResult(
        run_id=earlier.run_id,
        input=analyst_input,
        source_results=(*first.source_results, *second.source_results),
        completed_at=second.completed_at,
        policy_identity=first.policy_identity,
    )
    return V2EvidenceAdmissionBatchResult(
        run_id=earlier.run_id,
        analyst_result=analyst,
        source_results=(*earlier.source_results, *later.source_results),
        completed_at=later.completed_at,
        policy_identity=earlier.policy_identity,
    )


def _combined_queue_cost(earlier: Decimal, later: Decimal) -> Decimal:
    return add_usd(earlier, later)


def _read(path: str, run_id: UUID, key: str, model: type[StrictModel]) -> StrictModel | None:
    try:
        artifact = read_v2_artifact(path, run_id, key)
    except KeyError:
        return None
    return model.model_validate_json(artifact.payload_json)


def _read_payload(path: str, run_id: UUID, key: str) -> str | None:
    try:
        return read_v2_artifact(path, run_id, key).payload_json
    except KeyError:
        return None


def _has_artifact(path: str, run_id: UUID, key: str) -> bool:
    return _read_payload(path, run_id, key) is not None
