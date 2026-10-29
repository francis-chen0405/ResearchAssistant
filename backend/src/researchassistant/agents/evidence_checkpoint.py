"""Assess a small source batch before adaptive search, without admitting evidence early."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict, Field

from researchassistant.agents.adaptive_summary import _merge_survivors
from researchassistant.agents.v2_deep_analysis import (
    V2DeepAnalysisWave,
    _run_source_wave,
    _single_source_queue,
)
from researchassistant.agents.v2_source_selection import (
    _queue_priority,
    build_v2_source_selection_input,
    calculate_v2_deep_analysis_queue,
)
from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.models import (
    V2AcquisitionProbeOutput,
    V2DeepAnalysisBudget,
    V2DiscoveryScoutOutput,
    V2SourceSelectionQueueResult,
)
from researchassistant.contracts.source_recovery import AssessedSourceFinding
from researchassistant.providers.llm import LLMProvider
from researchassistant.providers.v2_budget import V2CancellationRequested
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

CHECKPOINT_KEY = "phase-5-assessed-evidence-checkpoint-v1"


class V2EvidenceCheckpoint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: UUID
    exact_claim: str
    waves: tuple[V2DeepAnalysisWave, ...] = Field(default=(), max_length=4)
    findings: tuple[AssessedSourceFinding, ...] = Field(default=(), max_length=4)


class V2EvidenceCheckpointPlan(StrictModel):
    """A preliminary queue is not a final Source Selection artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: UUID
    queue: V2SourceSelectionQueueResult


def assess_initial_sources(
    *,
    db_path: str | Path,
    exact_claim: str,
    discovery: V2DiscoveryScoutOutput,
    acquisition: V2AcquisitionProbeOutput,
    budget: V2DeepAnalysisBudget,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
    cancellation_requested: Callable[[], bool] | None = None,
) -> V2EvidenceCheckpoint:
    try:
        stored = read_v2_artifact(db_path, discovery.run_id, CHECKPOINT_KEY)
    except KeyError:
        stored = None
    if stored is not None:
        result = V2EvidenceCheckpoint.model_validate_json(stored.payload_json)
        if result.run_id != discovery.run_id or result.exact_claim != exact_claim:
            raise ValueError("evidence checkpoint claim changed")
        return result
    pool = _merge_survivors(
        discovery.run_id, ((1, discovery, acquisition),), deduplicate_papers=True
    )
    waves: list[V2DeepAnalysisWave] = []
    if pool.sources:
        selection = build_v2_source_selection_input(
            exact_claim=exact_claim,
            merged_survivors=pool,
            discovery_outputs=(discovery,),
            acquisition_outputs=(acquisition,),
            gap_outputs=(),
            claim_aware=True,
        )
        candidates = {c.source_id: c for c in selection.survivors}
        ordered = tuple(candidates[source_id] for source_id in _queue_priority(selection, ()))
        # A checkpoint must leave room for discovery/gap work and later evidence assessment.
        selected = tuple(ordered[:4])
        selection = selection.model_copy(update={"survivors": selected})
        try:
            stored_plan = read_v2_artifact(db_path, discovery.run_id, CHECKPOINT_KEY + "-plan")
        except KeyError:
            stored_plan = None
        if stored_plan is not None:
            frozen_plan = V2EvidenceCheckpointPlan.model_validate_json(stored_plan.payload_json)
            if frozen_plan.run_id != discovery.run_id:
                raise ValueError("evidence checkpoint plan belongs to another run")
            queue = frozen_plan.queue
            if queue.input != selection:
                raise ValueError("evidence checkpoint survivor input changed")
        else:
            protected = budget.model_copy(
                update={
                    "tokens_remaining": max(0, budget.tokens_remaining - 120_000),
                    "cost_remaining_usd": _checkpoint_cost_allowance(budget.cost_remaining_usd),
                }
            )
            ids = tuple(c.source_id for c in selected)
            plan = calculate_v2_deep_analysis_queue(
                selection_input=selection,
                ordered_source_ids=ids,
                recommended_source_ids=(),
                routing_config=routing_config,
                budget=protected,
            )
            data = plan.model_dump(
                exclude={
                    "policy_identity",
                    "attempts_per_logical_operation",
                    "extractor_attempts_per_source",
                    "extractor_logical_calls_per_source",
                    "analyst_logical_calls_per_source",
                    "reviewer_logical_calls_per_source",
                }
            )
            queue = V2SourceSelectionQueueResult(
                **data,
                input=selection,
                initial_budget=budget,
                priority_source_ids=ids,
                recommended_source_ids=(),
                recommendation_rationales=(),
                used_fallback=True,
                selection_attempts=0,
                selection_attempt_records=(),
                completed_at=clock(),
            )
            insert_v2_artifact(
                db_path,
                CHECKPOINT_KEY + "-plan",
                V2EvidenceCheckpointPlan(run_id=discovery.run_id, queue=queue),
                clock(),
            )
        for source_id in queue.queued_source_ids:
            if cancellation_requested is not None and cancellation_requested():
                raise V2CancellationRequested("cancelled before evidence checkpoint source")
            waves.append(
                _run_source_wave(
                    path=str(db_path),
                    source_id=source_id,
                    queue_result=_single_source_queue(queue, source_id, routing_config),
                    discovery_outputs=(discovery,),
                    acquisition_outputs=(acquisition,),
                    llm_provider=llm_provider,
                    routing_config=routing_config,
                    clock=clock,
                    admit=False,
                )
            )
    findings: list[AssessedSourceFinding] = []
    for wave in waves:
        source = next(s for s in wave.analyst.source_results if s.source_id == wave.source_id)
        assessment = source.assessment
        findings.append(
            AssessedSourceFinding(
                source_id=wave.source_id,
                direction=source.direction,
                outcome=source.state.value,
                supported_proposition=assessment.narrowest_supported_proposition
                if assessment
                else None,
                relationship_to_claim=assessment.relationship_to_claim.value
                if assessment
                else None,
                limitations=tuple(
                    item[:500]
                    for item in (
                        *assessment.material_limitations,
                        *assessment.inferential_boundaries,
                    )[:12]
                )
                if assessment
                else (),
                failure=source.failure,
            )
        )
    result = V2EvidenceCheckpoint(
        run_id=discovery.run_id,
        exact_claim=exact_claim,
        waves=tuple(waves),
        findings=tuple(findings),
    )
    insert_v2_artifact(db_path, CHECKPOINT_KEY, result, clock())
    return result


def _checkpoint_cost_allowance(cost: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(50, len(cost.as_tuple().digits) + 1)
        return cost / 2
