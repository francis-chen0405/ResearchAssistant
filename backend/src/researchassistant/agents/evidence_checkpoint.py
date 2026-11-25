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

from pydantic import ConfigDict, Field, model_validator

from researchassistant.agents.adaptive_summary import _merge_survivors
from researchassistant.agents.v2_deep_analysis import (
    V2DeepAnalysisWave,
    V2ExactBodyMirror,
    V2ExactBodyMirrorPlan,
    _exact_body_mirror_plan,
    _run_extracted_source,
    _run_source_extraction,
    _single_source_queue,
    exact_body_mirror_policy,
)
from researchassistant.agents.v2_discovery import _selected_model_input_tokens, uses_claim_ranking
from researchassistant.agents.v2_extraction import snapshots_by_source
from researchassistant.agents.v2_source_selection import (
    _queue_priority,
    _subtract_usd,
    build_v2_source_selection_input,
    calculate_v2_deep_analysis_queue,
)
from researchassistant.agents.v2_stage_checkpoint import checkpoint_hash, read_checkpoint
from researchassistant.common.money import add_usd
from researchassistant.contracts.extraction import V2ExactExtractionResult, V2ExtractionState
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
from researchassistant.evidence.evidence_core import validate_snapshot_integrity
from researchassistant.providers.llm import LLMProvider, LLMRequest, LLMStage
from researchassistant.providers.pricing import ModelPriceCap
from researchassistant.providers.run_scheduler import POLICY, RunScheduler
from researchassistant.providers.v2_budget import BudgetedV2LLMProvider
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.storage.sqlite_policy import overlapping_database_writes
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

CHECKPOINT_KEY = "phase-5-assessed-evidence-checkpoint-v1"
EARLY_ANALYSIS_SLOTS = POLICY.analysis.maximum
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
    discovery: V2DiscoveryScoutOutput | None = Field(default=None, exclude_if=lambda v: v is None)
    capture: V2AcquisitionProbeOutput | None = Field(default=None, exclude_if=lambda v: v is None)

    @model_validator(mode="after")
    def validate_source_handoff(self) -> V2EvidenceCheckpointPlan:
        if (self.discovery is None) != (self.capture is None):
            raise ValueError("early source handoff requires both discovery and capture")
        if self.queue.run_id != self.run_id:
            raise ValueError("early source queue belongs to another run")
        if self.discovery is not None and self.capture is not None:
            if (
                self.discovery.run_id != self.run_id
                or self.capture.run_id != self.run_id
                or len(self.queue.queued_source_ids) != 1
                or self.queue.queued_source_ids[0]
                not in {source.cluster_id for source in self.capture.survivors}
            ):
                raise ValueError("early source handoff differs from its queue ownership")
        return self


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
    deduplicate_bodies = exact_body_mirror_policy(str(db_path), discovery.run_id, clock())
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
        mirror_plan = _exact_body_mirror_plan(
            queue,
            queue.queued_source_ids,
            snapshots_by_source((acquisition,)),
            enabled=deduplicate_bodies,
        )
        mirror_key = CHECKPOINT_KEY + "-exact-body-mirrors-v1"
        saved_mirrors = read_checkpoint(
            db_path, discovery.run_id, mirror_key, V2ExactBodyMirrorPlan
        )
        if saved_mirrors is None:
            insert_v2_artifact(db_path, mirror_key, mirror_plan, clock())
        elif saved_mirrors != mirror_plan:
            raise ValueError("evidence checkpoint mirror ownership changed")
        mirror_ids = {mirror.source_id for mirror in mirror_plan.mirrors}
        source_ids = tuple(
            source_id for source_id in queue.queued_source_ids if source_id not in mirror_ids
        )
        scheduler = getattr(llm_provider, "scheduler", None) or RunScheduler(cancellation_requested)

        def check_cancelled() -> None:
            scheduler.check_cancelled()

        def analyze(source_id: UUID, extraction: V2ExactExtractionResult) -> V2DeepAnalysisWave:
            return _run_extracted_source(
                path=str(db_path),
                source_id=source_id,
                extraction=extraction,
                acquisition_outputs=(acquisition,),
                llm_provider=llm_provider,
                routing_config=routing_config,
                clock=clock,
                admit=False,
                journal_early_attempts=True,
                check_cancelled=check_cancelled,
            )

        # The frozen queue already protects the whole authorized early set. No
        # source is added as either stage refills, and its hold spans both stages.
        extracted: dict[UUID, V2ExactExtractionResult] = {}
        completed: dict[UUID, V2DeepAnalysisWave] = {}
        extracting: dict[UUID, Future[V2ExactExtractionResult]] = {}
        analyzing: dict[UUID, Future[V2DeepAnalysisWave]] = {}
        cursor = 0
        with (
            scheduler.stage_scope("extraction", "analysis"),
            overlapping_database_writes(str(db_path)),
            ThreadPoolExecutor(max_workers=POLICY.extraction.maximum) as extraction_pool,
            ThreadPoolExecutor(max_workers=POLICY.analysis.maximum) as analysis_pool,
        ):
            try:
                while len(completed) < len(source_ids):
                    check_cancelled()
                    for source_id, analysis_future in tuple(analyzing.items()):
                        if analysis_future.done():
                            completed[source_id] = analysis_future.result()
                            del analyzing[source_id]
                    for source_id, extraction_future in tuple(extracting.items()):
                        if extraction_future.done():
                            extraction = extraction_future.result()
                            if any(
                                item.state is V2ExtractionState.EXTRACTED
                                for item in extraction.sources
                            ):
                                extracted[source_id] = extraction
                            else:
                                completed[source_id] = analyze(source_id, extraction)
                            del extracting[source_id]
                    capacity = getattr(llm_provider, "stage_capacity_available", None)
                    target = scheduler.update_stage(
                        "analysis",
                        ready=len(extracted),
                        running=len(analyzing),
                        capacity=capacity(LLMStage.ANALYST) if callable(capacity) else True,
                    )
                    for source_id in source_ids:
                        if len(analyzing) >= target:
                            break
                        if source_id in extracted:
                            analysis_future = analysis_pool.submit(
                                copy_context().run,
                                analyze,
                                source_id,
                                extracted.pop(source_id),
                            )
                            analyzing[source_id] = analysis_future
                            analysis_future.add_done_callback(lambda _future: scheduler.notify())
                    target = scheduler.update_stage(
                        "extraction",
                        ready=len(source_ids) - cursor,
                        running=len(extracting),
                        downstream=len(extracted) + scheduler.model_waiting(LLMStage.ANALYST.value),
                        capacity=capacity(LLMStage.EXTRACTOR) if callable(capacity) else True,
                    )
                    while cursor < len(source_ids) and len(extracting) < target:
                        check_cancelled()
                        source_id = source_ids[cursor]
                        cursor += 1
                        extraction_future = extraction_pool.submit(
                            copy_context().run,
                            _run_source_extraction,
                            path=str(db_path),
                            source_id=source_id,
                            queue_result=_single_source_queue(queue, source_id, routing_config),
                            discovery_outputs=(discovery,),
                            acquisition_outputs=(acquisition,),
                            llm_provider=llm_provider,
                            routing_config=routing_config,
                            clock=clock,
                            journal_early_attempts=True,
                        )
                        extracting[source_id] = extraction_future
                        extraction_future.add_done_callback(lambda _future: scheduler.notify())
                    if extracting or analyzing:
                        scheduler.wait_for_change()
            except BaseException:
                scheduler.stop_admission()
                raise
            finally:
                for future in (*extracting.values(), *analyzing.values()):
                    future.cancel()
        waves = [completed[source_id] for source_id in source_ids]
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
                addressed_gap_ids=assessment.addressed_gap_ids if assessment else (),
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
        self.assessment_captures: dict[UUID, V2AcquisitionProbeOutput] = {}
        self.extracting: dict[UUID, Future[V2ExactExtractionResult]] = {}
        self.extracted: dict[UUID, V2ExactExtractionResult] = {}
        self.waves: dict[UUID, V2DeepAnalysisWave] = {}
        self.plans: dict[UUID, V2EvidenceCheckpointPlan] = {}
        self.priority: tuple[UUID, ...] = ()
        self.capacity = 0
        self.deduplicate_bodies = False

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
        self.deduplicate_bodies = exact_body_mirror_policy(self.path, self.run_id, self.clock())
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
        extraction_executor: ThreadPoolExecutor,
        wake: SimpleQueue[None],
        check_cancelled: Callable[[], None],
        scout_pending: bool = False,
    ) -> None:
        for source_id, future in tuple(self.active.items()):
            if future.done():
                self.waves[source_id] = future.result()
                del self.active[source_id]
        for source_id, extraction_future in tuple(self.extracting.items()):
            if extraction_future.done():
                extraction = extraction_future.result()
                if any(item.state is V2ExtractionState.EXTRACTED for item in extraction.sources):
                    self.extracted[source_id] = extraction
                else:
                    capture = self.assessment_captures[source_id]
                    self.waves[source_id] = self._assess(
                        source_id,
                        extraction,
                        capture,
                        check_cancelled,
                    )
                del self.extracting[source_id]
        scheduler = self.llm.scheduler
        analysis_target = scheduler.update_stage(
            "analysis",
            ready=len(self.extracted),
            running=len(self.active),
            capacity=self.llm.stage_capacity_available(LLMStage.ANALYST),
        )
        for source_id in self.plans:
            if len(self.active) >= analysis_target:
                break
            if source_id not in self.extracted:
                continue
            check_cancelled()
            capture = self.assessment_captures[source_id]
            future = executor.submit(
                copy_context().run,
                self._assess,
                source_id,
                self.extracted.pop(source_id),
                capture,
                check_cancelled,
            )
            self.active[source_id] = future
            future.add_done_callback(lambda _future: wake.put(None))
        assert self.budget is not None
        self.priority = priority
        # Pending ranked captures protect slots inside this frontier. The other
        # half is unavailable until Scout settles, even if downloads finish early.
        assignment_limit = (
            max(1, self.capacity // 2) if scout_pending and self.capacity else self.capacity
        )
        open_slots = assignment_limit - len(self.plans)
        assigned = {
            source_id: captures[source_id] for source_id in self.plans if source_id in captures
        }
        ready_ids = {
            source_id
            for source_id in priority
            if source_id in captures
            and captures[source_id].survivors
            and source_id not in self.active
            and source_id not in self.waves
            and source_id not in self.extracting
            and source_id not in self.extracted
            and (source_id in self.plans or open_slots > 0)
        }
        extraction_target = scheduler.update_stage(
            "extraction",
            ready=min(
                len(ready_ids),
                max(
                    0,
                    assignment_limit
                    - len(self.active)
                    - len(self.waves)
                    - len(self.extracting)
                    - len(self.extracted),
                ),
            ),
            running=len(self.extracting),
            downstream=len(self.extracted) + scheduler.model_waiting(LLMStage.ANALYST.value),
            capacity=self.llm.stage_capacity_available(LLMStage.EXTRACTOR),
        )
        for source_id in priority:
            if len(self.extracting) >= extraction_target:
                break
            if (
                source_id in self.active
                or source_id in self.waves
                or source_id in self.extracting
                or source_id in self.extracted
            ):
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
            if plan is not None and plan.discovery is not None and plan.capture is not None:
                # Replay the exact source-local handoff, not a growing Scout aggregate.
                local_discovery = plan.discovery
                capture = plan.capture
                selection = plan.queue.input
            else:
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
                plan = V2EvidenceCheckpointPlan(
                    run_id=self.run_id, queue=queue, discovery=local_discovery, capture=capture
                )
                insert_v2_artifact(
                    self.path, self._plan_key(len(self.plans) + 1), plan, queue.completed_at
                )
                self.plans[source_id] = plan
                assigned[source_id] = capture
                open_slots -= 1
            self.assessment_captures[source_id] = capture
            extraction_future = extraction_executor.submit(
                copy_context().run,
                self._extract,
                source_id,
                queue,
                local_discovery,
                capture,
                check_cancelled,
            )
            self.extracting[source_id] = extraction_future
            extraction_future.add_done_callback(lambda _future: wake.put(None))

    def _unique_work(
        self,
        discovery: V2DiscoveryScoutOutput,
        assigned: dict[UUID, V2AcquisitionProbeOutput],
        source_id: UUID,
        capture: V2AcquisitionProbeOutput,
    ) -> bool:
        if self.deduplicate_bodies:
            source = next(item for item in capture.survivors if item.cluster_id == source_id)
            snapshot = next(
                item.snapshot
                for item in capture.acquisitions
                if item.snapshot.snapshot_id == source.snapshot_id
            )
            validate_snapshot_integrity(snapshot)
            if not snapshot.truncated:
                key = f"{CHECKPOINT_KEY}/exact-body-mirror/{source_id}"
                saved = read_checkpoint(self.path, self.run_id, key, V2ExactBodyMirrorPlan)
                # Repeated readiness callbacks retain their first proven owner,
                # even if another equivalent capture has since become ready.
                retained_order = tuple(assigned)
                if saved is not None:
                    retained_id = saved.mirrors[0].retained_source_id
                    if retained_id not in assigned:
                        raise ValueError("early mirror retained capture is unavailable")
                    retained_order = (
                        retained_id,
                        *(item for item in assigned if item != retained_id),
                    )
                for retained_id in retained_order:
                    if retained_id == source_id:
                        continue
                    earlier = assigned[retained_id]
                    retained = next(
                        item for item in earlier.survivors if item.cluster_id == retained_id
                    )
                    original = next(
                        item.snapshot
                        for item in earlier.acquisitions
                        if item.snapshot.snapshot_id == retained.snapshot_id
                    )
                    validate_snapshot_integrity(original)
                    if (
                        source.direction == retained.direction
                        and not original.truncated
                        and snapshot.snapshot_sha256 == original.snapshot_sha256
                        and snapshot.normalized_text == original.normalized_text
                    ):
                        mirror = V2ExactBodyMirror(
                            source_id=source_id,
                            retained_source_id=retained_id,
                            snapshot_sha256=snapshot.snapshot_sha256,
                        )
                        mirror_plan = V2ExactBodyMirrorPlan(
                            run_id=self.run_id,
                            enabled=True,
                            input_sha256=checkpoint_hash(mirror.model_dump(mode="json")),
                            mirrors=(mirror,),
                        )
                        if saved is None:
                            insert_v2_artifact(self.path, key, mirror_plan, self.clock())
                        elif saved != mirror_plan:
                            raise ValueError("early mirror ownership changed")
                        return False
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

    def _extract(
        self,
        source_id: UUID,
        queue: V2SourceSelectionQueueResult,
        discovery: V2DiscoveryScoutOutput,
        capture: V2AcquisitionProbeOutput,
        check_cancelled: Callable[[], None],
    ) -> V2ExactExtractionResult:
        check_cancelled()
        with self.llm.limit_source_cost(source_id, self.source_cost_ceiling):
            return _run_source_extraction(
                path=self.path,
                source_id=source_id,
                queue_result=queue,
                discovery_outputs=(discovery,),
                acquisition_outputs=(capture,),
                llm_provider=self.llm,
                routing_config=self.routing,
                clock=self.clock,
                journal_early_attempts=True,
            )

    def _assess(
        self,
        source_id: UUID,
        extraction: V2ExactExtractionResult,
        capture: V2AcquisitionProbeOutput,
        check_cancelled: Callable[[], None],
    ) -> V2DeepAnalysisWave:
        with self.llm.limit_source_cost(source_id, self.source_cost_ceiling):
            return _run_extracted_source(
                path=self.path,
                source_id=source_id,
                extraction=extraction,
                acquisition_outputs=(capture,),
                llm_provider=self.llm,
                routing_config=self.routing,
                clock=self.clock,
                admit=False,
                journal_early_attempts=True,
                check_cancelled=check_cancelled,
            )

    def ready(self, *, capture_exhausted: bool) -> bool:
        return not (self.active or self.extracting or self.extracted) and (
            capture_exhausted or (self.capacity > 0 and len(self.waves) == self.capacity)
        )

    def complete(self) -> V2EvidenceCheckpoint:
        saved = read_checkpoint(self.path, self.run_id, CHECKPOINT_KEY, V2EvidenceCheckpoint)
        if set(self.plans) != set(self.waves) or set(self.plans) - set(self.priority):
            raise ValueError("early assessment finished without every assigned source")
        # Slot assignment order is durable; completion order and later ranking
        # changes must not reorder findings on restart.
        waves = tuple(self.waves[source_id] for source_id in self.plans)
        result = evidence_checkpoint(self.run_id, self.exact_claim, waves)
        if saved is not None:
            if saved != result:
                raise ValueError("saved evidence checkpoint differs from its early assessments")
            return saved
        insert_v2_artifact(self.path, CHECKPOINT_KEY, result, self.clock())
        return result
