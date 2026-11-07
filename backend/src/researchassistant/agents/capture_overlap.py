"""Coordinate durable Scout handoffs, bounded capture, and initial evidence assessment."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, SimpleQueue
from threading import Event, Semaphore
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, model_validator

from researchassistant.agents.evidence_checkpoint import EARLY_ANALYSIS_SLOTS
from researchassistant.agents.v2_acquisition import (
    _MAX_RANKED_SOURCE_ATTEMPTS,
    V2_ACQUISITION_PROBE_ARTIFACT_KEY,
    _acquire_cluster_usable,
    _capture_candidate_ids,
    _capture_is_readable,
    _capture_locations,
    _capture_scout_decisions,
    _probe_acquired_source,
    _snapshot_from_response,
)
from researchassistant.agents.v2_discovery import (
    ScoutHandoff,
    V2DiscoveryScoutRunResult,
    _round_discovery_artifact_key,
)
from researchassistant.agents.v2_stage_checkpoint import read_checkpoint
from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
from researchassistant.contracts.models import (
    ResearchDirection,
    SourceCluster,
    StrictModel,
    V2AcquisitionPolicy,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
)
from researchassistant.contracts.scraping import ScrapeResponse
from researchassistant.providers.acquisition import CaptureControls, capture_controls
from researchassistant.providers.llm import LLMRequest
from researchassistant.providers.ranking import canonical_discovery_url
from researchassistant.providers.scraper import ScraperProvider
from researchassistant.providers.v2_budget import V2CancellationRequested
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

if TYPE_CHECKING:
    from researchassistant.agents.evidence_checkpoint import EarlyAssessment, V2EvidenceCheckpoint

DEFAULT_CAPTURE_SLOTS = 3
LATER_SCOUT_CAPTURE_RESERVE = 2

CaptureSettled = Callable[[V2DiscoveryScoutOutput, dict[UUID, V2AcquisitionProbeOutput]], None]


EarlySettled = Callable[
    [
        V2DiscoveryScoutOutput,
        dict[UUID, V2AcquisitionProbeOutput],
        tuple[UUID, ...],
        "V2EvidenceCheckpoint",
    ],
    None,
]


class V2CaptureOverlapBinding(StrictModel):
    run_id: UUID
    capture_slots: int = Field(ge=1, le=5)
    progressive: bool = Field(default=False, exclude_if=lambda value: not value)


class V2CaptureDispatch(StrictModel):
    run_id: UUID
    cluster_id: UUID
    item_id: UUID
    scout_batches: int = Field(ge=1)
    direction: ResearchDirection
    urls: tuple[str, ...]
    dispatched_at: datetime
    first_pass: bool = Field(default=False, exclude_if=lambda value: not value)


class V2CaptureReady(StrictModel):
    run_id: UUID
    dispatch: V2CaptureDispatch
    output: V2AcquisitionProbeOutput

    @model_validator(mode="after")
    def validate_ownership(self) -> V2CaptureReady:
        if (
            self.run_id != self.dispatch.run_id
            or self.run_id != self.output.run_id
            or len(self.output.acquisitions) > 1
            or any(
                row.cluster_id != self.dispatch.cluster_id
                for row in (
                    *self.output.attempts,
                    *self.output.acquisitions,
                    *self.output.survivors,
                )
            )
            or any(row.direction != self.dispatch.direction for row in self.output.acquisitions)
        ):
            raise ValueError("ready capture differs from its dispatch ownership")
        return self


@dataclass(frozen=True)
class CaptureCandidate:
    cluster: SourceCluster
    item_id: UUID
    direction: ResearchDirection
    locations: tuple[str, ...]


def bind_capture_overlap(
    path: str, run_id: UUID, artifact_key: str, slots: int, clock: Callable[[], datetime]
) -> int | None:
    """Keep the serial path for an acquisition already owned by an older build."""
    key = f"{artifact_key}/overlap-v1"
    binding = read_checkpoint(path, run_id, key, V2CaptureOverlapBinding)
    if binding is not None:
        return binding.capture_slots
    for existing_key in (artifact_key, f"{artifact_key}-input-binding"):
        try:
            read_v2_artifact(path, run_id, existing_key)
        except KeyError:
            continue
        return None
    binding = V2CaptureOverlapBinding(run_id=run_id, capture_slots=slots, progressive=True)
    insert_v2_artifact(path, key, binding, clock())
    return slots


def initial_capture_slots(path: str, run_id: UUID) -> int | None:
    binding = read_checkpoint(
        path, run_id, f"{V2_ACQUISITION_PROBE_ARTIFACT_KEY}/overlap-v1", V2CaptureOverlapBinding
    )
    return binding.capture_slots if binding is not None else None


def supports_progressive_overlap(path: str, run_id: UUID, artifact_key: str) -> bool:
    binding = read_checkpoint(path, run_id, f"{artifact_key}/overlap-v1", V2CaptureOverlapBinding)
    return binding is not None and binding.progressive


class CaptureOverlap:
    def __init__(
        self,
        *,
        path: str,
        run_id: UUID,
        artifact_key: str,
        policy: V2AcquisitionPolicy,
        exact_claim: str,
        asserted_components: tuple[str, ...],
        target_gaps: tuple[str, ...],
        direction_target: int | None,
        capture_slots: int,
        primary: ScraperProvider | None,
        fallback: ScraperProvider | None,
        cancellation_requested: Callable[[], bool] | None,
        clock: Callable[[], datetime],
        early: EarlyAssessment | None = None,
        exclusions: Callable[[V2DiscoveryScoutOutput], tuple[frozenset[UUID], frozenset[str]]]
        | None = None,
    ) -> None:
        self.path = path
        self.run_id = run_id
        self.artifact_key = artifact_key
        self.policy = policy
        self.exact_claim = exact_claim
        self.asserted_components = asserted_components
        self.target_gaps = target_gaps
        self.direction_target = direction_target
        self.capture_slots = capture_slots
        self.primary = primary
        self.fallback = fallback
        self.cancellation_requested = cancellation_requested
        self.clock = clock
        self.early = early
        self.exclusions = exclusions
        self.excluded_clusters: frozenset[UUID] = frozenset()
        self.excluded_urls: frozenset[str] = frozenset()
        self.work_owners: dict[UUID, UUID] = {}
        self.stop = Event()
        self.browser_slots = Semaphore(1)
        self.transport_slots = Semaphore(capture_slots)
        self.browser_events: SimpleQueue[tuple[UUID, bool]] = SimpleQueue()
        self.parked: set[UUID] = set()
        self.max_capture_jobs = 2 * capture_slots - 1
        self.wake: SimpleQueue[None] = SimpleQueue()
        self.handoffs: SimpleQueue[
            tuple[
                V2DiscoveryScoutOutput,
                V2MetadataRankingArtifact,
                tuple[LLMRequest, ...],
                bool,
                Event,
            ]
        ] = SimpleQueue()
        self.finished: dict[UUID, V2AcquisitionProbeOutput] = {}
        self.active: dict[UUID, tuple[V2CaptureDispatch, Future[V2AcquisitionProbeOutput]]] = {}
        self.claimed_urls: set[str] = set()
        self.dispatch_count = 0

    def cancelled(self) -> bool:
        return self.stop.is_set() or bool(
            self.cancellation_requested and self.cancellation_requested()
        )

    def check_cancelled(self) -> None:
        if self.cancelled():
            raise V2CancellationRequested("cancelled during Scout/capture overlap")

    def _publish(
        self,
        output: V2DiscoveryScoutOutput,
        ranking: V2MetadataRankingArtifact,
        pending: tuple[LLMRequest, ...],
        search_pending: bool,
    ) -> None:
        self.check_cancelled()
        accepted = Event()
        self.handoffs.put((output, ranking, pending, search_pending, accepted))
        self.wake.put(None)
        # Give the coordinator ownership of this durable prefix before Scout
        # starts a later request. It never waits for a capture to finish here.
        while not accepted.wait(timeout=0.1):
            self.check_cancelled()

    def _candidates(
        self, discovery: V2DiscoveryScoutOutput, ranking: V2MetadataRankingArtifact
    ) -> tuple[CaptureCandidate, ...]:
        if self.exclusions is not None:
            self.excluded_clusters, self.excluded_urls = self.exclusions(discovery)
        items = {item.item_id: item for item in discovery.items}
        clusters = {item_id: c for c in discovery.clusters for item_id in c.item_ids}
        self.work_owners = {
            clusters[link.item_id].cluster_id: clusters[link.scouted_item_id].cluster_id
            for link in discovery.late_mirrors
        }
        candidates: dict[UUID, CaptureCandidate] = {}
        for item_id in _capture_candidate_ids(discovery, ranking):
            cluster = clusters[item_id]
            if (
                cluster.cluster_id not in candidates
                and cluster.cluster_id not in self.excluded_clusters
            ):
                item = items[item_id]
                locations = _capture_locations(cluster, items, item)
                candidates[cluster.cluster_id] = CaptureCandidate(
                    cluster,
                    item_id,
                    item.direction,
                    tuple(
                        dict.fromkeys((*locations, cluster.preferred_url, *cluster.alternate_urls))
                    ),
                )
        return tuple(candidates.values())

    def _unclaimed_locations(self, locations: tuple[str, ...]) -> tuple[str, ...]:
        unique: dict[str, str] = {}
        for url in locations:
            identity = canonical_discovery_url(url)
            if identity not in self.claimed_urls and identity not in self.excluded_urls:
                unique.setdefault(identity, url)
        return tuple(unique.values())[: self.policy.max_urls_per_cluster]

    def _dispatch_key(self) -> str:
        return f"{self.artifact_key}/overlap-v1/dispatch-{self.dispatch_count + 1}"

    def _next_dispatch(
        self,
        discovery: V2DiscoveryScoutOutput,
        candidates: tuple[CaptureCandidate, ...],
        *,
        scout_pending: bool,
        search_pending: bool,
        limit: int,
    ) -> tuple[V2CaptureDispatch, CaptureCandidate] | None:
        key = self._dispatch_key()
        saved = read_checkpoint(self.path, self.run_id, key, V2CaptureDispatch)
        if saved is not None:
            if (search_pending and not saved.first_pass) or (
                len(discovery.scout_batches) < saved.scout_batches
            ):
                return None
            # Replay against the original Scout prefix, which may have selected
            # another location for this work than the completed round would.
            cluster = next(c for c in discovery.clusters if c.cluster_id == saved.cluster_id)
            items = {item.item_id: item for item in discovery.items}
            item = items[saved.item_id]
            if (
                cluster.cluster_id in self.excluded_clusters
                or item.item_id not in cluster.item_ids
                or item.direction != saved.direction
                or saved.urls
                != self._unclaimed_locations(
                    (
                        *_capture_locations(cluster, items, item),
                        cluster.preferred_url,
                        *cluster.alternate_urls,
                    )
                )
                or item.item_id
                not in {
                    item_id
                    for item_id, decision in _capture_scout_decisions(
                        discovery.model_copy(
                            update={"scout_batches": discovery.scout_batches[: saved.scout_batches]}
                        )
                    ).items()
                    if decision.decision.value != "skip"
                }
            ):
                raise ValueError("saved capture dispatch differs from its Scout handoff")
            return saved, CaptureCandidate(cluster, item.item_id, item.direction, saved.urls)

        if search_pending:
            # On replay, an already frozen final Scout pool supersedes new
            # dispatch from the earlier prefix. Existing prefix owners still replay.
            final_scout_key = "scout-checkpoint-v1/" + _round_discovery_artifact_key(
                discovery.items[0].round_number
            )
            try:
                read_v2_artifact(self.path, self.run_id, final_scout_key)
            except KeyError:
                pass
            else:
                return None

        # Leave space for a counterevidence lead and a promising Maybe from
        # a later Scout batch, even if all the first downloads finish quickly.
        target = self.direction_target
        if scout_pending:
            limit = max(1, limit - LATER_SCOUT_CAPTURE_RESERVE)
            if target is not None:
                target = max(1, target - LATER_SCOUT_CAPTURE_RESERVE)
        blocked = 0
        pending_by_direction = Counter(dispatch.direction for dispatch, _ in self.active.values())
        captured_works, adequate = self._captured_works()
        usable_by_direction = Counter(captured_works.values())
        active_works = {self.work_owners.get(cluster_id, cluster_id) for cluster_id in self.active}
        active_hosts = {
            urlsplit(dispatch.urls[0]).hostname
            for dispatch, _ in self.active.values()
            if dispatch.urls
        }
        for candidate in candidates:
            if self.dispatch_count + blocked >= limit:
                break
            cluster_id = candidate.cluster.cluster_id
            if cluster_id in self.finished or cluster_id in self.active:
                continue
            owner = self.work_owners.get(cluster_id, cluster_id)
            if owner in active_works or owner in adequate:
                continue
            if (
                target is not None
                and owner not in captured_works
                and (
                    pending_by_direction[candidate.direction]
                    + usable_by_direction[candidate.direction]
                    >= target
                )
            ):
                continue
            urls = self._unclaimed_locations(candidate.locations)
            if not urls and cluster_id in self.work_owners:
                continue
            if urls and urlsplit(urls[0]).hostname in active_hosts:
                blocked += 1
                pending_by_direction[candidate.direction] += 1
                continue
            dispatch = V2CaptureDispatch(
                run_id=self.run_id,
                cluster_id=cluster_id,
                item_id=candidate.item_id,
                scout_batches=len(discovery.scout_batches),
                direction=candidate.direction,
                urls=urls,
                dispatched_at=self.clock(),
                first_pass=search_pending,
            )
            insert_v2_artifact(self.path, key, dispatch, dispatch.dispatched_at)
            return dispatch, candidate
        return None

    def _captured_works(self) -> tuple[dict[UUID, ResearchDirection], set[UUID]]:
        captured_works: dict[UUID, ResearchDirection] = {}
        adequate = set()
        for cluster_id, output in self.finished.items():
            if output.survivors:
                owner = self.work_owners.get(cluster_id, cluster_id)
                captured_works.setdefault(owner, output.survivors[0].direction)
                if not output.acquisitions[0].snapshot.truncated:
                    adequate.add(owner)
        return captured_works, adequate

    def _capture(
        self, dispatch: V2CaptureDispatch, cluster: SourceCluster, discovery: V2DiscoveryScoutOutput
    ) -> V2AcquisitionProbeOutput:
        self.check_cancelled()
        key = f"{self.artifact_key}/overlap-v1/ready/{dispatch.cluster_id}"
        saved = read_checkpoint(self.path, self.run_id, key, V2CaptureReady)
        if saved is not None:
            if saved.dispatch != dispatch:
                raise ValueError("saved ready capture differs from its dispatch")
            return saved.output

        def accept_html(response: ScrapeResponse) -> bool:
            return _capture_is_readable(
                _snapshot_from_response(
                    self.run_id, cluster, dispatch.urls[0], response, dispatch.dispatched_at
                ),
                allow_abstract_only=False,
            )

        def browser_waiting(waiting: bool) -> None:
            self.browser_events.put((dispatch.cluster_id, waiting))
            self.wake.put(None)

        source, attempts = None, ()
        if dispatch.urls:
            with capture_controls(
                CaptureControls(
                    accept_html,
                    self.transport_slots,
                    self.browser_slots,
                    self.check_cancelled,
                    browser_waiting,
                )
            ):
                source, attempts = _acquire_cluster_usable(
                    db_path=self.path,
                    artifact_key=self.artifact_key,
                    tried_urls=set(),
                    run_id=self.run_id,
                    cluster=cluster,
                    direction=dispatch.direction,
                    primary=self.primary,
                    fallback=self.fallback,
                    policy=self.policy,
                    retrieved_at=dispatch.dispatched_at,
                    planned_locations=dispatch.urls,
                    cancellation_requested=self.cancelled,
                    clock=self.clock,
                )
        probe, survivor = (
            _probe_acquired_source(
                source,
                discovery.directions,
                self.policy.policy_identity,
                self.exact_claim,
                self.asserted_components,
                self.target_gaps,
            )
            if source is not None
            else (None, None)
        )
        output = V2AcquisitionProbeOutput(
            run_id=self.run_id,
            directions=discovery.directions,
            acquisitions=(source,) if source is not None else (),
            attempts=attempts,
            probes=(probe,) if probe is not None else (),
            survivors=(survivor,) if survivor is not None else (),
            policy_identity=self.policy.policy_identity,
            completed_at=self.clock(),
        )
        insert_v2_artifact(
            self.path,
            key,
            V2CaptureReady(run_id=self.run_id, dispatch=dispatch, output=output),
            output.completed_at,
        )
        return output

    def run(
        self,
        scout: Callable[[ScoutHandoff, Callable[[], bool]], V2DiscoveryScoutRunResult],
        *,
        on_scout_finished: Callable[[], None] | None = None,
        on_capture_settled: CaptureSettled | None = None,
        on_early_settled: EarlySettled | None = None,
    ) -> tuple[
        V2DiscoveryScoutRunResult, dict[UUID, V2AcquisitionProbeOutput], V2EvidenceCheckpoint | None
    ]:
        with (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="scout") as scout_pool,
            ThreadPoolExecutor(
                max_workers=self.max_capture_jobs, thread_name_prefix="capture"
            ) as capture_pool,
            ThreadPoolExecutor(
                max_workers=EARLY_ANALYSIS_SLOTS, thread_name_prefix="early-analysis"
            ) as analysis_pool,
        ):
            try:
                return self._run(
                    scout,
                    scout_pool,
                    capture_pool,
                    analysis_pool,
                    on_scout_finished,
                    on_capture_settled,
                    on_early_settled,
                )
            finally:
                self.stop.set()

    def _run(
        self,
        scout: Callable[[ScoutHandoff, Callable[[], bool]], V2DiscoveryScoutRunResult],
        scout_pool: ThreadPoolExecutor,
        capture_pool: ThreadPoolExecutor,
        analysis_pool: ThreadPoolExecutor,
        on_scout_finished: Callable[[], None] | None,
        on_capture_settled: CaptureSettled | None,
        on_early_settled: EarlySettled | None,
    ) -> tuple[
        V2DiscoveryScoutRunResult, dict[UUID, V2AcquisitionProbeOutput], V2EvidenceCheckpoint | None
    ]:
        scouting = scout_pool.submit(copy_context().run, scout, self._publish, self.cancelled)
        scouting.add_done_callback(lambda _future: self.wake.put(None))
        result = None
        handoff = None
        candidates: tuple[CaptureCandidate, ...] = ()
        scout_pending = False
        search_pending = False
        settled = False
        checkpoint = None
        limit = min(self.policy.max_clusters, _MAX_RANKED_SOURCE_ATTEMPTS)
        while True:
            self.check_cancelled()
            accepted = None
            pending: tuple[LLMRequest, ...] = ()
            if not self.handoffs.empty():
                discovery, ranking, pending, search_pending, accepted = self.handoffs.get_nowait()
                handoff = (discovery, ranking)
                candidates = self._candidates(*handoff)
                scout_pending = search_pending or bool(pending)
            if result is None and scouting.done():
                result = scouting.result()
                scout_pending = False
                search_pending = False
                if on_scout_finished is not None and result.output.items:
                    on_scout_finished()
                if result.ranking_artifact is not None:
                    handoff = (result.output, result.ranking_artifact)
                    candidates = self._candidates(*handoff)
            while not self.browser_events.empty():
                cluster_id, waiting = self.browser_events.get_nowait()
                if waiting:
                    self.parked.add(cluster_id)
                else:
                    self.parked.discard(cluster_id)
            for cluster_id, (_dispatch, future) in tuple(self.active.items()):
                if future.done():
                    self.finished[cluster_id] = future.result()
                    del self.active[cluster_id]

            if handoff is not None:
                while (
                    len(self.active) < self.max_capture_jobs
                    and len(self.active) - len(self.parked) < self.capture_slots
                    and self.dispatch_count < limit
                ):
                    self.check_cancelled()
                    work = self._next_dispatch(
                        handoff[0],
                        candidates,
                        scout_pending=scout_pending,
                        search_pending=search_pending,
                        limit=limit,
                    )
                    if work is None:
                        break
                    dispatch, candidate = work
                    cluster_id = dispatch.cluster_id
                    if cluster_id in self.active or cluster_id in self.finished:
                        raise ValueError("capture dispatch claimed a work twice")
                    self.dispatch_count += 1
                    self.claimed_urls.update(canonical_discovery_url(url) for url in dispatch.urls)
                    future = capture_pool.submit(
                        copy_context().run, self._capture, dispatch, candidate.cluster, handoff[0]
                    )
                    self.active[cluster_id] = (dispatch, future)
                    future.add_done_callback(lambda _future: self.wake.put(None))

            capture_done = result is not None and not self.active
            if capture_done and not settled:
                assert result is not None
                if on_capture_settled is not None and result.output.items:
                    on_capture_settled(result.output, self.finished)
                settled = True
            if self.early is not None and handoff is not None:
                if (
                    accepted is not None
                    and not search_pending
                    and pending
                    and candidates
                    and self.early.budget is None
                ):
                    lead = candidates[0]
                    if any(
                        item.item_id == lead.item_id and item.decision.value == "retrieve"
                        for batch in handoff[0].scout_batches
                        for item in batch.items
                    ):
                        self.early.prepare(lead.cluster.cluster_id, pending)
                if result is not None:
                    self.early.prepare()
                if self.early.budget is not None:
                    lead_id = self.early.budget.lead_source_id
                    priority = (lead_id,) if lead_id is not None else ()
                    if result is not None:
                        ids = tuple(candidate.cluster.cluster_id for candidate in candidates)
                        started = (self.active.keys() | self.finished.keys()) & set(ids)
                        ranked = list(priority)
                        for source_id in ids:
                            owner = self.work_owners.get(source_id)
                            if owner is not None and owner in started:
                                # A late location cannot displace the early
                                # assessment of a work with an owned capture.
                                ranked.append(owner)
                            ranked.append(source_id)
                        priority = tuple(dict.fromkeys(ranked))
                    captured_works, adequate = self._captured_works()
                    usable = Counter(captured_works.values())
                    outstanding = set(self.active)
                    if not capture_done and self.dispatch_count < limit:
                        for candidate in candidates:
                            cluster_id = candidate.cluster.cluster_id
                            owner = self.work_owners.get(cluster_id, cluster_id)
                            if (
                                cluster_id not in self.finished
                                and owner not in adequate
                                and self._unclaimed_locations(candidate.locations)
                                and (
                                    owner in captured_works
                                    or self.direction_target is None
                                    or usable[candidate.direction] < self.direction_target
                                )
                            ):
                                outstanding.add(cluster_id)
                    self.early.advance(
                        discovery=handoff[0],
                        priority=priority,
                        captures=self.finished,
                        outstanding=frozenset(outstanding),
                        executor=analysis_pool,
                        wake=self.wake,
                        check_cancelled=self.check_cancelled,
                    )
                    if (
                        result is not None
                        and checkpoint is None
                        and self.early.ready(capture_exhausted=capture_done)
                    ):
                        checkpoint = self.early.complete()
                        if on_early_settled is not None and result.output.items:
                            pending_ids = tuple(
                                source_id
                                for source_id in priority
                                if source_id in outstanding and source_id not in self.finished
                            )[:60]
                            on_early_settled(
                                result.output, dict(self.finished), pending_ids, checkpoint
                            )
            if accepted is not None:
                accepted.set()
            if capture_done and (self.early is None or checkpoint is not None):
                assert result is not None
                return result, self.finished, checkpoint
            while True:
                try:
                    self.wake.get(timeout=0.1)
                    break
                except Empty:
                    self.check_cancelled()
