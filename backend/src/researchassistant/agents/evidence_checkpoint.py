"""Assess a small source batch before adaptive search, without admitting evidence early."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from queue import SimpleQueue
from uuid import UUID

from pydantic import ConfigDict, Field

from researchassistant.agents.adaptive_summary import _merge_survivors
from researchassistant.agents.v2_deep_analysis import (
    V2DeepAnalysisWave,
    _run_source_wave,
    _single_source_queue,
)
from researchassistant.agents.v2_discovery import _selected_model_input_tokens, uses_claim_ranking
from researchassistant.agents.v2_source_selection import (
    _queue_priority,
    _subtract_usd,
    build_v2_source_selection_input,
    calculate_v2_deep_analysis_queue,
)
from researchassistant.agents.v2_stage_checkpoint import read_checkpoint
from researchassistant.common.money import add_usd
from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.models import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    V2AcquisitionProbeOutput,
    V2DeepAnalysisBudget,
    V2DiscoveryScoutOutput,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
)
from researchassistant.contracts.source_recovery import AssessedSourceFinding
from researchassistant.providers.llm import LLMProvider, LLMRequest, LLMStage
from researchassistant.providers.pricing import ModelPriceCap
from researchassistant.providers.v2_budget import BudgetedV2LLMProvider, V2CancellationRequested
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

CHECKPOINT_KEY = "phase-5-assessed-evidence-checkpoint-v1"
EARLY_ANALYSIS_SLOTS = 3
EARLY_SOURCE_LIMIT = 4


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


class V2EarlyBudget(StrictModel):
    run_id: UUID
    budget: V2DeepAnalysisBudget
    protected: V2DeepAnalysisBudget
    lead_source_id: UUID | None = None


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
    claim_ranking = uses_claim_ranking(db_path, discovery.run_id)
    pool = _merge_survivors(
        discovery.run_id,
        ((1, discovery, acquisition),),
        deduplicate_papers=True,
        recover_incomplete_papers=claim_ranking,
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
            track_shared_data=claim_ranking,
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
            queue = checkpoint_queue(selection, routing_config, budget, protected, clock())
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
    result = evidence_checkpoint(discovery.run_id, exact_claim, tuple(waves))
    insert_v2_artifact(db_path, CHECKPOINT_KEY, result, clock())
    return result


def checkpoint_queue(
    selection: V2SourceSelectionInput,
    routing_config: V2RoutingConfig,
    budget: V2DeepAnalysisBudget,
    protected: V2DeepAnalysisBudget,
    completed_at: datetime,
) -> V2SourceSelectionQueueResult:
    ids = tuple(c.source_id for c in selection.survivors)
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
    return V2SourceSelectionQueueResult(
        **data,
        input=selection,
        initial_budget=budget,
        priority_source_ids=ids,
        recommended_source_ids=(),
        recommendation_rationales=(),
        used_fallback=True,
        selection_attempts=0,
        selection_attempt_records=(),
        completed_at=completed_at,
    )


def evidence_checkpoint(
    run_id: UUID, exact_claim: str, waves: tuple[V2DeepAnalysisWave, ...]
) -> V2EvidenceCheckpoint:
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
    return V2EvidenceCheckpoint(
        run_id=run_id,
        exact_claim=exact_claim,
        waves=tuple(waves),
        findings=tuple(findings),
    )


def _checkpoint_cost_allowance(cost: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(50, len(cost.as_tuple().digits) + 1)
        return cost / 2


class EarlyAssessment:
    """The ranked prefix is committed by one owner before workers spend any reservation."""

    def __init__(
        self,
        *,
        path: str,
        run_id: UUID,
        exact_claim: str,
        llm: BudgetedV2LLMProvider,
        routing: V2RoutingConfig,
        call_ceiling: int,
        protected_calls: int,
        clock: Callable[[], datetime],
    ) -> None:
        self.path = path
        self.run_id = run_id
        self.exact_claim = exact_claim
        self.llm = llm
        self.routing = routing
        self.call_ceiling = call_ceiling
        self.protected_calls = protected_calls
        routes = routing.preflight()
        extractor = routes.for_stage(LLMStage.EXTRACTOR)
        analyst = routes.for_stage(LLMStage.ANALYST)
        # The source cap applies across both stages. Price the worst mix of
        # their tokens so a long Analyst prompt or validation retry cannot use
        # another early source's reserve or the remaining Scout reservation.
        price = ModelPriceCap(
            model="early-evidence-envelope",
            input_usd_per_token=max(
                extractor.price_cap.input_usd_per_token, analyst.price_cap.input_usd_per_token
            ),
            output_usd_per_token=max(
                extractor.price_cap.output_usd_per_token, analyst.price_cap.output_usd_per_token
            ),
        )
        output = min(
            V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
            V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
            * max(extractor.max_completion_tokens, analyst.max_completion_tokens),
        )
        self.source_cost_ceiling = add_usd(
            max(
                price.upper_bound(V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP, 0),
                price.upper_bound(V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP - output, output),
            ),
            Decimal("0.000000003"),  # Rounding on three separate physical reservations.
        )
        self.clock = clock
        self.budget: V2EarlyBudget | None = None
        self.active: dict[UUID, Future[V2DeepAnalysisWave]] = {}
        self.waves: dict[UUID, V2DeepAnalysisWave] = {}
        self.plans: dict[UUID, V2EvidenceCheckpointPlan] = {}
        self.priority: tuple[UUID, ...] = ()
        self.capacity = 0

    @staticmethod
    def _plan_key(slot: int) -> str:
        return f"{CHECKPOINT_KEY}/overlap-v1/slot-{slot}"

    def prepare(
        self,
        lead_id: UUID | None = None,
        pending: tuple[LLMRequest, ...] = (),
    ) -> None:
        if self.budget is not None:
            return
        self.budget = self._budget(lead_id, pending)
        reserve = self.budget.protected
        self.capacity = min(
            EARLY_SOURCE_LIMIT,
            (reserve.physical_call_ceiling - reserve.physical_calls_used)
            // V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
            reserve.tokens_remaining // V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
            int(reserve.cost_remaining_usd // self.source_cost_ceiling),
        )
        for slot in range(1, self.capacity + 1):
            saved = read_checkpoint(
                self.path, self.run_id, self._plan_key(slot), V2EvidenceCheckpointPlan
            )
            if saved is None:
                break
            (source_id,) = saved.queue.queued_source_ids
            if source_id in self.plans:
                raise ValueError("early assessment plan repeats a source")
            self.plans[source_id] = saved

    def _budget(
        self,
        lead_id: UUID | None,
        pending: tuple[LLMRequest, ...],
    ) -> V2EarlyBudget:
        key = f"{CHECKPOINT_KEY}/overlap-v1/budget"
        saved = read_checkpoint(self.path, self.run_id, key, V2EarlyBudget)
        if saved is not None:
            return saved
        snapshot = self.llm.snapshot()
        budget = V2DeepAnalysisBudget(
            physical_call_ceiling=self.call_ceiling,
            physical_calls_used=snapshot.physical_calls_used,
            tokens_remaining=snapshot.tokens_remaining,
            cost_remaining_usd=snapshot.cost_remaining_usd,
        )
        route = self.routing.preflight()
        reservations = (
            tuple(
                route.reserve(request.stage, _selected_model_input_tokens(self.llm, request))
                for request in pending
            )
            * 2
        )  # Each of the remaining Scout batches owns its existing retry allowance.
        pending_tokens = sum(item.reserved_tokens for item in reservations)
        pending_cost = add_usd(*(item.reserved_cost_usd for item in reservations))
        protected = budget.model_copy(
            update={
                "physical_calls_used": min(
                    self.call_ceiling,
                    snapshot.physical_calls_used + self.protected_calls + len(reservations),
                ),
                "tokens_remaining": max(0, snapshot.tokens_remaining - pending_tokens - 120_000),
                "cost_remaining_usd": _checkpoint_cost_allowance(
                    _subtract_usd(snapshot.cost_remaining_usd, pending_cost)
                ),
            }
        )
        saved = V2EarlyBudget(
            run_id=self.run_id,
            budget=budget,
            protected=protected,
            lead_source_id=lead_id,
        )
        insert_v2_artifact(self.path, key, saved, self.clock())
        return saved

    def advance(
        self,
        *,
        discovery: V2DiscoveryScoutOutput,
        priority: tuple[UUID, ...],
        captures: dict[UUID, V2AcquisitionProbeOutput],
        outstanding: frozenset[UUID],
        executor: ThreadPoolExecutor,
        wake: SimpleQueue[None],
        check_cancelled: Callable[[], None],
    ) -> None:
        for source_id, future in tuple(self.active.items()):
            if future.done():
                self.waves[source_id] = future.result()
                del self.active[source_id]
        assert self.budget is not None
        self.priority = priority
        open_slots = self.capacity - len(self.plans)
        assigned = {
            source_id: captures[source_id] for source_id in self.plans if source_id in captures
        }
        for source_id in priority:
            if len(self.active) == EARLY_ANALYSIS_SLOTS:
                break
            if source_id in self.active or source_id in self.waves:
                continue
            capture = captures.get(source_id)
            plan = self.plans.get(source_id)
            if plan is None and open_slots <= 0:
                continue
            if capture is None:
                if plan is None and source_id in outstanding:
                    # A pending higher-ranked work reserves an early slot. Other
                    # ready works within the remaining slots can start immediately.
                    open_slots -= 1
                continue
            if not capture.survivors:
                if plan is not None:
                    raise ValueError("early assessment plan lost its readable capture")
                continue
            if plan is None and len(assigned) != len(self.plans):
                # Reestablish saved ownership before making new assignments.
                continue
            if plan is None and not self._unique_work(discovery, assigned, source_id, capture):
                continue
            pool = _merge_survivors(self.run_id, ((1, discovery, capture),))
            # Freeze only the source's own cluster and snapshot. The eventual
            # aggregate (or a fuller mirror) cannot change the request on replay.
            cluster = next(c for c in discovery.clusters if c.cluster_id == source_id)
            local_discovery = discovery.model_copy(
                update={
                    "items": tuple(
                        item for item in discovery.items if item.item_id in cluster.item_ids
                    ),
                    "clusters": (cluster,),
                    "scout_batches": (),
                    "scout_audits": (),
                    "late_mirrors": (),
                }
            )
            selection = build_v2_source_selection_input(
                exact_claim=self.exact_claim,
                merged_survivors=pool,
                discovery_outputs=(local_discovery,),
                acquisition_outputs=(capture,),
                gap_outputs=(),
                claim_aware=True,
                track_shared_data=True,
            )
            check_cancelled()
            queue = checkpoint_queue(
                selection,
                self.routing,
                self.budget.budget,
                self.budget.protected,
                plan.queue.completed_at if plan is not None else self.clock(),
            )
            if plan is not None and plan.queue != queue:
                raise ValueError("early assessment plan differs from its capture or reservation")
            if not queue.queued_source_ids:
                continue
            if plan is None:
                plan = V2EvidenceCheckpointPlan(run_id=self.run_id, queue=queue)
                insert_v2_artifact(
                    self.path, self._plan_key(len(self.plans) + 1), plan, queue.completed_at
                )
                self.plans[source_id] = plan
                assigned[source_id] = capture
                open_slots -= 1
            future = executor.submit(
                copy_context().run,
                self._assess,
                source_id,
                queue,
                local_discovery,
                capture,
                check_cancelled,
            )
            self.active[source_id] = future
            future.add_done_callback(lambda _future: wake.put(None))

    def _unique_work(
        self,
        discovery: V2DiscoveryScoutOutput,
        assigned: dict[UUID, V2AcquisitionProbeOutput],
        source_id: UUID,
        capture: V2AcquisitionProbeOutput,
    ) -> bool:
        pool = _merge_survivors(
            self.run_id,
            tuple((1, discovery, output) for output in (*assigned.values(), capture)),
            deduplicate_papers=True,
            recover_incomplete_papers=True,
        )
        return {source.survivor.cluster_id for source in pool.sources} == {
            *assigned,
            source_id,
        }

    def _assess(
        self,
        source_id: UUID,
        queue: V2SourceSelectionQueueResult,
        discovery: V2DiscoveryScoutOutput,
        capture: V2AcquisitionProbeOutput,
        check_cancelled: Callable[[], None],
    ) -> V2DeepAnalysisWave:
        with self.llm.limit_source_cost(source_id, self.source_cost_ceiling):
            return _run_source_wave(
                path=self.path,
                source_id=source_id,
                queue_result=queue,
                discovery_outputs=(discovery,),
                acquisition_outputs=(capture,),
                llm_provider=self.llm,
                routing_config=self.routing,
                clock=self.clock,
                admit=False,
                journal_early_attempts=True,
                check_cancelled=check_cancelled,
            )

    def ready(self, *, capture_exhausted: bool) -> bool:
        return not self.active and (
            capture_exhausted or (self.capacity > 0 and len(self.waves) == self.capacity)
        )

    def complete(self) -> V2EvidenceCheckpoint:
        saved = read_checkpoint(self.path, self.run_id, CHECKPOINT_KEY, V2EvidenceCheckpoint)
        if set(self.plans) != set(self.waves) or set(self.plans) - set(self.priority):
            raise ValueError("early assessment finished without every assigned source")
        waves = tuple(
            self.waves[source_id] for source_id in self.priority if source_id in self.waves
        )
        result = evidence_checkpoint(self.run_id, self.exact_claim, waves)
        if saved is not None:
            if saved != result:
                raise ValueError("saved evidence checkpoint differs from its early assessments")
            return saved
        insert_v2_artifact(self.path, CHECKPOINT_KEY, result, self.clock())
        return result
