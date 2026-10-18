"""Deterministic seed offers and accounted, resumable one-hop action execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from uuid import UUID

import httpx
from pydantic import ValidationError

from researchassistant.common.discovery_identity import (
    _matches_seed as _matches_seed,
)
from researchassistant.common.discovery_identity import (
    _metadata as _metadata,
)
from researchassistant.common.discovery_identity import (
    _resolved_identity as _resolved_identity,
)
from researchassistant.common.discovery_identity import (
    _work_id as _work_id,
)
from researchassistant.common.discovery_identity import (
    neighbor_work_identity as neighbor_work_identity,
)
from researchassistant.common.discovery_identity import (
    pipeline_work_identity as pipeline_work_identity,
)
from researchassistant.common.discovery_identity import (
    raw_neighbor_candidate as raw_neighbor_candidate,
)
from researchassistant.common.money import parse_exact_usd
from researchassistant.contracts.artifact_keys import discovery_round_keys as _round_keys
from researchassistant.contracts.discovery_v2 import (
    V2CandidateDisposition,
    V2DiscoveryBinding,
    V2DiscoveryFailure,
    V2DiscoveryOperation,
    V2ExpansionEdge,
    V2ExpansionResult,
    V2GraphNeighborAction,
    V2NormalizedDiscoveryCandidate,
    V2ProviderAttemptCompletion,
    V2ProviderAttemptStart,
    V2RankComponents,
    V2SanitizedParameter,
    V2SeedEligibility,
    V2WorkResolution,
    discovery_hash,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
)
from researchassistant.contracts.neighborhood import (
    V2NeighborhoodCheckpoint,
    V2NeighborhoodResponse,
    V2SeedSelection,
)
from researchassistant.contracts.neighborhood_results import (
    NeighborhoodRelation,
    ResolvedOpenAlexWork,
)
from researchassistant.contracts.query_planning import V2ConceptualAdaptiveLane
from researchassistant.contracts.search import SearchFailureCode, SearchResult
from researchassistant.providers.openalex_neighborhood import OpenAlexNeighborhoodAdapter
from researchassistant.providers.search import SearchProviderError
from researchassistant.research.query_execution import available_query_budgets
from researchassistant.storage.discovery_store import (
    _persist_once,
    complete_provider_attempt,
    insert_candidate_disposition,
    insert_discovery_candidate,
    insert_discovery_operation,
    insert_expansion_result,
    insert_pipeline_seed,
    insert_raw_candidate,
    insert_work_resolution,
    provider_attempt_audit,
    read_discovery_artifacts,
    read_discovery_binding,
    reserve_provider_attempt,
)
from researchassistant.storage.neighborhood_store import (
    MissingNeighborhoodCheckpoint,
    read_neighborhood_checkpoint,
)
from researchassistant.storage.query_retrieval_store import retention_headroom
from researchassistant.storage.store import read_v2_artifact

SEED_EXECUTION_ID = "source-seed-expansion-v3"
_PIPELINE_SEED_IDENTITIES = {"source-seed-expansion-v2", SEED_EXECUTION_ID}


def select_seeds(
    path: str, run_id: UUID, completed_round: int, clock: Callable[[], datetime]
) -> V2SeedSelection:
    binding = read_discovery_binding(path, run_id)
    key = f"seed-selection/round-{completed_round}"
    try:
        return V2SeedSelection.model_validate_json(
            read_v2_artifact(
                path, run_id, f"source-discovery-v1:V2SeedSelection:{key}"
            ).payload_json
        )
    except KeyError:
        pass
    prior = read_discovery_artifacts(path, run_id)
    seeds = [item for item in prior if isinstance(item, V2SeedEligibility) and item.eligible]
    selected = []
    if (
        binding.seed_identity in _PIPELINE_SEED_IDENTITIES
        and DiscoveryProvider.OPENALEX in binding.providers
        and completed_round < 4
    ):
        dkey, akey = _round_keys(completed_round)
        try:
            discovery = V2DiscoveryScoutOutput.model_validate_json(
                read_v2_artifact(path, run_id, dkey).payload_json
            )
            acquisition = V2AcquisitionProbeOutput.model_validate_json(
                read_v2_artifact(path, run_id, akey).payload_json
            )
        except KeyError:
            discovery = None
        if discovery is not None:
            items = {item.item_id: item for item in discovery.items}
            clusters = {item.cluster_id: item for item in discovery.clusters}
            probes = {item.snapshot_id: item for item in acquisition.probes}
            options = []
            for survivor in acquisition.survivors:
                preview = probes[survivor.snapshot_id].preview
                if preview is None or not preview.capture_usable or preview.relevance_score <= 0:
                    continue
                for item_id in clusters[survivor.cluster_id].item_ids:
                    item = items[item_id]
                    if item.graph_action is not None:
                        continue  # Expanded papers never become another hop.
                    external_id = _work_id(_metadata(item, "external_id"))
                    if (not item.doi and not external_id) or not item.title:
                        continue
                    if item.source_type not in {
                        "article",
                        "review",
                        "proceedings-article",
                        "dissertation",
                    }:
                        continue
                    year = (
                        int(item.publication_date[:4])
                        if item.publication_date and item.publication_date[:4].isdigit()
                        else None
                    )
                    if year is None or _metadata(item, "is_retracted") is True:
                        continue
                    work = pipeline_work_identity(item)
                    if any(work.shares_work_anchor(seed.work) for seed in seeds):
                        continue
                    options.append(
                        (
                            -preview.relevance_score,
                            work.grouping_key,
                            str(item_id),
                            item,
                            work,
                            survivor,
                        )
                    )
            for _, _, _, item, work, survivor in sorted(options, key=lambda x: x[:3]):
                if len(seeds) >= binding.policy.max_seeds_per_run:
                    break
                if any(work.shares_work_anchor(seed.work) for seed in seeds):
                    continue
                seed_key = f"seed/{item.item_id}"
                seed = V2SeedEligibility(
                    run_id=run_id,
                    artifact_id=discovery_id(run_id, "V2SeedEligibility", seed_key),
                    identity_key=seed_key,
                    candidate_id=item.item_id,
                    source_id=survivor.cluster_id,
                    snapshot_id=survivor.snapshot_id,
                    work=work,
                    eligible=True,
                    seed_identity=binding.seed_identity,
                    reason="Relevant owned preview, scholarly metadata and exact identifier",
                )
                insert_pipeline_seed(path, seed, dkey, akey, clock())
                seeds.append(seed)
                selected.append(seed)
    result = V2SeedSelection(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2SeedSelection", key),
        identity_key=key,
        seed_identity=binding.seed_identity
        if binding.seed_identity in _PIPELINE_SEED_IDENTITIES
        else "source-seed-expansion-v2",
        round_number=completed_round,
        seeds=tuple(seeds),
        status="offered" if seeds else "skipped",
        reason="Bounded eligible seed pool"
        if seeds
        else "No configured capable provider or reliable relevant seed",
    )
    _persist_once(path, result, clock())
    return result


def offer_expansions(
    path: str,
    run_id: UUID,
    round_number: int,
    lanes: tuple[V2ConceptualAdaptiveLane, ...],
    clock: Callable[[], datetime],
) -> tuple[V2GraphNeighborAction, ...]:
    try:
        binding = read_discovery_binding(path, run_id)
    except KeyError:
        return ()
    if not getattr(binding.policy, "seed_expansion_enabled", True):
        return ()
    if binding.seed_identity not in _PIPELINE_SEED_IDENTITIES or round_number not in {2, 3, 4}:
        return ()
    selection = select_seeds(path, run_id, round_number - 1, clock)
    artifacts = read_discovery_artifacts(path, run_id)
    used = {
        (item.action.seed.work.grouping_key, item.action.relationship)
        for item in artifacts
        if isinstance(item, V2DiscoveryOperation) and isinstance(item.action, V2GraphNeighborAction)
    }
    results = [item for item in artifacts if isinstance(item, V2ExpansionResult)]
    failed_seed_ids = {
        item.candidate_id
        for item in artifacts
        if isinstance(item, V2WorkResolution) and item.status == "unresolved"
    }
    resolved_actions = {
        item.operation_id
        for item in artifacts
        if isinstance(item, V2WorkResolution) and item.status == "resolved"
    }
    failed_seed_ids.update(
        result.action.seed.candidate_id
        for result in results
        if result.status in {"unavailable", "skipped", "interrupted_unknown"}
        and result.action.artifact_id not in resolved_actions
    )
    all_neighbors = {
        edge.candidate.work.grouping_key for result in results for edge in result.edges
    }
    headroom = min(
        binding.policy.max_expansion_per_run - len(all_neighbors),
        retention_headroom(path, run_id, round_number),
    )
    available = next(
        (
            x.remaining_calls
            for x in available_query_budgets(path, run_id)
            if x.provider is DiscoveryProvider.OPENALEX
        ),
        0,
    )
    offers = []
    reserved_neighbors: dict[str, int] = {}
    for index, lane in enumerate(lanes):
        if lane.provider is not DiscoveryProvider.OPENALEX or headroom <= 0 or available < 2:
            continue
        for seed in selection.seeds:
            if seed.candidate_id in failed_seed_ids:
                continue
            neighbors = {
                edge.candidate.work.grouping_key
                for result in results
                if result.action.seed.work.grouping_key == seed.work.grouping_key
                for edge in result.edges
            }
            remaining = min(
                headroom,
                binding.policy.max_neighbors_per_seed
                - len(neighbors)
                - reserved_neighbors.get(seed.work.grouping_key, 0),
                binding.policy.metadata_depth,
            )
            if remaining <= 0:
                continue
            for relation in selection.relationship_priority:
                if (seed.work.grouping_key, relation) in used:
                    continue
                key = f"neighbors/round-{round_number}/lane-{index}/{seed.candidate_id}/{relation}"
                action = V2GraphNeighborAction(
                    run_id=run_id,
                    artifact_id=discovery_id(run_id, "V2GraphNeighborAction", key),
                    identity_key=key,
                    seed=seed,
                    relationship=relation,
                    provider=lane.provider,
                    direction=lane.direction,
                    round_number=round_number,
                    target_gap_ids=lane.target_gap_ids,
                    requested_depth=remaining,
                    policy=binding.policy,
                    capabilities=next(
                        x for x in binding.capabilities if x.provider == lane.provider
                    ),
                    seed_identity=binding.seed_identity,
                )
                offers.append(action)
                reserved_neighbors[seed.work.grouping_key] = (
                    reserved_neighbors.get(seed.work.grouping_key, 0) + remaining
                )
                available -= 2
                headroom -= remaining
                used.add((seed.work.grouping_key, relation))
                break
            if offers and offers[-1].identity_key.startswith(
                f"neighbors/round-{round_number}/lane-{index}/"
            ):
                break
    return tuple(offers)


class _GraphPhysicalExecution:
    def __init__(
        self,
        path: str,
        action: V2GraphNeighborAction,
        binding: V2DiscoveryBinding,
        clock: Callable[[], datetime],
        cancelled: Callable[[], bool] | None,
        phase: str,
    ) -> None:
        self.path, self.action, self.binding = path, action, binding
        self.clock, self.cancelled, self.phase = clock, cancelled, phase
        self.start: V2ProviderAttemptStart | None = None
        self.completion: V2ProviderAttemptCompletion | None = None
        self.response: V2NeighborhoodResponse | None = None

    def request(
        self, parameters: Mapping[str, str | int | bool], send: Callable[[], httpx.Response]
    ) -> httpx.Response:
        if self.cancelled and self.cancelled():
            raise SearchProviderError(
                SearchFailureCode.CANCELLED, "Expansion cancelled before transport"
            )
        audit = provider_attempt_audit(self.path, self.action.run_id)
        starts = [x for x in audit.starts if x.operation_id == self.action.artifact_id]
        prior = next(
            (
                x
                for x in starts
                if x.request_kind == ("identity" if self.phase == "identity" else "primary")
            ),
            None,
        )
        if prior is not None:
            self.start = prior
            self.completion = next(
                (x for x in audit.completions if x and x.attempt_id == prior.artifact_id), None
            )
            if self.completion is not None and self.completion.status == "completed":
                try:
                    body = V2NeighborhoodResponse.model_validate_json(
                        read_v2_artifact(
                            self.path,
                            self.action.run_id,
                            f"source-discovery-v1:V2NeighborhoodResponse:graph-response/{prior.artifact_id}",
                        ).payload_json
                    )
                except KeyError:
                    body = None
                if body is not None and body.response_hash == self.completion.response_hash:
                    return httpx.Response(200, content=body.content.encode())
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE, "Started physical expansion cannot be repeated"
            )
        budget = next(
            x for x in self.binding.provider_budgets if x.provider == self.action.provider
        )
        key = f"graph-attempt/{self.action.artifact_id}/{len(starts) + 1}"
        self.start = V2ProviderAttemptStart(
            run_id=self.action.run_id,
            artifact_id=discovery_id(self.action.run_id, "V2ProviderAttemptStart", key),
            identity_key=key,
            operation_id=self.action.artifact_id,
            binding_fingerprint=self.binding.fingerprint,
            provider=self.action.provider,
            sequence=len(starts) + 1,
            page_number=1,
            request_kind="identity" if self.phase == "identity" else "primary",
            parameters=tuple(V2SanitizedParameter(name=k, value=v) for k, v in parameters.items()),
            requested_records=2
            if self.phase == "identity"
            else int(parameters.get("per_page", self.action.requested_depth)),
            reserved_cost_usd=budget.reservation_per_request_usd,
            cost_basis=budget.cost_basis,
            started_at=self.clock(),
        )
        try:
            reserve_provider_attempt(self.path, self.start)
        except ValueError as exc:
            raise SearchProviderError(SearchFailureCode.BUDGET_EXHAUSTED, str(exc)) from exc
        try:
            response = send()
        except BaseException:
            self._complete(
                status="interrupted_unknown",
                failure=V2DiscoveryFailure(code="interrupted", detail="unknown_after_start"),
            )
            raise
        success = 200 <= response.status_code < 300
        actual = None
        ids = []
        count = 0
        try:
            body = response.json()
            raw_cost = body.get("meta", {}).get("cost_usd")
            if raw_cost is not None:
                actual = parse_exact_usd(raw_cost)
            records = (
                body.get("results", []) if self.phase != "identity" or "results" in body else [body]
            )
            if isinstance(records, list):
                count = min(len(records), self.start.requested_records)
                if self.phase == "neighbors":
                    for record in records[: self.start.requested_records]:
                        wid = _work_id(record.get("id")) if isinstance(record, dict) else None
                        if wid:
                            cid = discovery_id(
                                self.action.run_id,
                                "V2RawDiscoveryCandidate",
                                f"neighbor/{self.action.artifact_id}/{wid.rsplit('/', 1)[-1]}",
                            )
                            if cid not in ids:
                                ids.append(cid)
        except (ValueError, TypeError, AttributeError):
            pass
        if success:
            rkey = f"graph-response/{self.start.artifact_id}"
            try:
                self.response = V2NeighborhoodResponse(
                    run_id=self.action.run_id,
                    artifact_id=discovery_id(self.action.run_id, "V2NeighborhoodResponse", rkey),
                    identity_key=rkey,
                    operation_id=self.action.artifact_id,
                    attempt_id=self.start.artifact_id,
                    response_hash=sha256(response.content).hexdigest(),
                    content=response.content.decode("utf-8"),
                )
            except (ValidationError, UnicodeError, ValueError):
                self.response = None  # Oversized/unsafe/malformed data cannot become candidates.
        self._complete(
            status="completed" if success else "failed",
            response_hash=sha256(response.content).hexdigest() if success else None,
            failure=None
            if success
            else V2DiscoveryFailure(
                code="rate_limit" if response.status_code == 429 else "invalid_request",
                detail="provider_failure",
            ),
            actual=actual,
            metadata_records=count if success else 0,
            result_ids=tuple(ids) if success else (),
        )
        return response

    def _complete(
        self,
        *,
        status: Literal["completed", "failed", "interrupted_unknown"],
        response_hash: str | None = None,
        failure: V2DiscoveryFailure | None = None,
        actual: Decimal | None = None,
        metadata_records: int = 0,
        result_ids: tuple[UUID, ...] = (),
    ) -> None:
        if self.start is None:
            raise RuntimeError("Completion has no physical start")
        key = f"completion/{self.start.artifact_id}"
        self.completion = V2ProviderAttemptCompletion(
            run_id=self.action.run_id,
            artifact_id=discovery_id(self.action.run_id, "V2ProviderAttemptCompletion", key),
            identity_key=key,
            attempt_id=self.start.artifact_id,
            operation_id=self.action.artifact_id,
            status=status,
            response_hash=response_hash,
            result_ids=result_ids,
            failure=failure,
            actual_cost_usd=actual,
            metadata_records=metadata_records,
            cost_basis="unknown" if actual is None else "reported",
            completed_at=self.clock(),
        )
        complete_provider_attempt(
            self.path, self.completion, self.completion.completed_at, response=self.response
        )


def _checkpoint(
    path: str,
    action: V2GraphNeighborAction,
    phase: str,
    adapter: OpenAlexNeighborhoodAdapter | None,
    binding: V2DiscoveryBinding,
    clock: Callable[[], datetime],
    cancelled: Callable[[], bool] | None,
    work: ResolvedOpenAlexWork | None = None,
) -> V2NeighborhoodCheckpoint:
    key = f"graph-parser/{action.artifact_id}/{phase}"
    try:
        return read_neighborhood_checkpoint(path, action, phase)
    except MissingNeighborhoodCheckpoint:
        pass
    if adapter is None:
        raise ValueError("Missing checkpoint cannot be replayed without configured transport")
    physical = _GraphPhysicalExecution(path, action, binding, clock, cancelled, phase)
    if phase == "identity":
        identifier = action.seed.work.provider_work_id or action.seed.work.doi
        parsed = adapter.resolve(identifier or "", requester=physical.request)
    else:
        if work is None:
            raise ValueError("Neighbor request requires exact resolved identity")
        earlier = [
            x
            for x in read_discovery_artifacts(path, action.run_id)
            if isinstance(x, V2ExpansionResult)
        ]
        all_works = {
            edge.candidate.work.grouping_key for result in earlier for edge in result.edges
        }
        seed_works = {
            edge.candidate.work.grouping_key
            for result in earlier
            if result.action.seed.work.grouping_key == action.seed.work.grouping_key
            for edge in result.edges
        }
        limit = min(
            action.requested_depth,
            retention_headroom(path, action.run_id, action.round_number),
            binding.policy.max_expansion_per_run - len(all_works),
            binding.policy.max_neighbors_per_seed - len(seed_works),
        )
        if binding.seed_identity == SEED_EXECUTION_ID:
            # A completed response owns its original parse limit even if another
            # action has since consumed candidate capacity. The requester reuses
            # its bytes or rejects a failed/unknown start; it never sends again.
            prior = next(
                (
                    start
                    for start in provider_attempt_audit(path, action.run_id).starts
                    if start.operation_id == action.artifact_id and start.request_kind == "primary"
                ),
                None,
            )
            if prior is not None:
                limit = prior.requested_records
        if limit <= 0:
            raise SearchProviderError(
                SearchFailureCode.BUDGET_EXHAUSTED, "Expansion metadata cap exhausted"
            )
        parsed = adapter.expand(
            work, NeighborhoodRelation(action.relationship), requester=physical.request, limit=limit
        )
    if physical.completion is None:
        # Unsupported/empty fields produce no physical subrequest.
        if phase == "neighbors":
            identity = _checkpoint(path, action, "identity", adapter, binding, clock, cancelled)
            physical.completion = next(
                x
                for x in provider_attempt_audit(path, action.run_id).completions
                if x and x.attempt_id == identity.attempt_id
            )
        else:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE, "Unsupported exact seed identifier"
            )
    completion = physical.completion
    if physical.start is not None and physical.response is None:
        # Replay may already have its durable response even though this invocation did not send.
        try:
            read_v2_artifact(
                path,
                action.run_id,
                f"source-discovery-v1:V2NeighborhoodResponse:graph-response/{completion.attempt_id}",
            )
        except KeyError as exc:
            raise SearchProviderError(
                SearchFailureCode.MALFORMED_RESPONSE, "Unsafe/oversized response cannot be retained"
            ) from exc
    cp = V2NeighborhoodCheckpoint(
        run_id=action.run_id,
        artifact_id=discovery_id(action.run_id, "V2NeighborhoodCheckpoint", key),
        identity_key=key,
        action=action,
        phase=phase,
        attempt_id=completion.attempt_id,
        response_hash=completion.response_hash,
        work=parsed.work,
        results=parsed.results,
        status=parsed.status.value,
        parsed_hash=discovery_hash(
            (
                parsed.work.model_dump_json() if parsed.work else None,
                tuple(x.model_dump_json() for x in parsed.results),
                parsed.status.value,
            )
        ),
    )
    _persist_once(path, cp, clock())
    return cp


def execute_expansion(
    *,
    path: str,
    action: V2GraphNeighborAction,
    adapter: OpenAlexNeighborhoodAdapter | None,
    clock: Callable[[], datetime],
    cancellation_requested: Callable[[], bool] | None = None,
) -> tuple[SearchResult, ...]:
    """Run only an already planned slot; each HTTP call reserves against shared ceilings."""
    binding = read_discovery_binding(path, action.run_id)
    if not getattr(binding.policy, "seed_expansion_enabled", True):
        raise ValueError("Expansion from papers is disabled in the frozen run settings")
    key = f"expansion/{action.artifact_id}/result"
    try:
        cached = V2ExpansionResult.model_validate_json(
            read_v2_artifact(
                path, action.run_id, f"source-discovery-v1:V2ExpansionResult:{key}"
            ).payload_json
        )
        if cached.action != action:
            raise ValueError("Expansion result action differs")
        if cached.status != "pending":
            if not cached.edges:
                return ()
            cp = _checkpoint(
                path, action, "neighbors", adapter, binding, clock, cancellation_requested
            )
            from researchassistant.storage.discovery_store import _validate_raw_candidate

            for edge in cached.edges:
                _validate_raw_candidate(path, edge.candidate, binding)
            returned = {edge.candidate.work.provider_work_id for edge in cached.edges}
            return tuple(item for item in cp.results if item.metadata.external_id in returned)
    except KeyError:
        pass
    opkey = f"graph-operation/{action.artifact_id}"
    try:
        envelope = read_v2_artifact(
            path, action.run_id, f"source-discovery-v1:V2DiscoveryOperation:{opkey}"
        )
        operation = V2DiscoveryOperation.model_validate_json(envelope.payload_json)
    except KeyError:
        operation = V2DiscoveryOperation(
            run_id=action.run_id,
            artifact_id=discovery_id(action.run_id, "V2DiscoveryOperation", opkey),
            identity_key=opkey,
            binding_fingerprint=binding.fingerprint,
            action=action,
            created_at=clock(),
        )
        insert_discovery_operation(path, operation, operation.created_at)
    if operation.action != action or operation.binding_fingerprint != binding.fingerprint:
        raise ValueError("Expansion differs from frozen operation")
    edges = []
    results = []
    status, reason = "skipped", "No configured capable provider"
    try:
        if adapter is not None:
            cp = _checkpoint(
                path, action, "identity", adapter, binding, clock, cancellation_requested
            )
            resolved = (
                cp.status == "resolved"
                and cp.work is not None
                and _matches_seed(action.seed, cp.work)
            )
            rkey = f"resolution/{action.artifact_id}"
            resolution = V2WorkResolution(
                run_id=action.run_id,
                artifact_id=discovery_id(action.run_id, "V2WorkResolution", rkey),
                identity_key=rkey,
                candidate_id=action.seed.candidate_id,
                provider=action.provider,
                work=_resolved_identity(cp.work) if resolved else action.seed.work,
                status="resolved" if resolved else "unresolved",
                operation_id=action.artifact_id,
                reason="Exact identifier and compatible title/authors/year"
                if resolved
                else "Unresolved, conflicting, retracted or unsupported seed",
            )
            insert_work_resolution(path, resolution, clock())
            if resolved:
                cp = _checkpoint(
                    path,
                    action,
                    "neighbors",
                    adapter,
                    binding,
                    clock,
                    cancellation_requested,
                    cp.work,
                )
                status, reason = "completed", "Bounded provider-reported one-hop neighborhood"
                if cp.status == "unsupported":
                    status, reason = "skipped", "Unsupported or absent provider relationship field"
                elif cp.status == "malformed":
                    status, reason = "unavailable", "Malformed neighborhood response"
                artifacts = read_discovery_artifacts(path, action.run_id)
                earlier = [item for item in artifacts if isinstance(item, V2ExpansionResult)]
                used_seed = {
                    edge.candidate.work.grouping_key
                    for result in earlier
                    if result.action.seed.work.grouping_key == action.seed.work.grouping_key
                    for edge in result.edges
                }
                used_run = {
                    edge.candidate.work.grouping_key for result in earlier for edge in result.edges
                }
                # Include IDs learned by exact resolution of DOI-only seeds, as
                # well as their original anchors and previously discovered aliases.
                seed_works = [
                    item.work
                    for item in artifacts
                    if isinstance(item, V2SeedEligibility)
                    or (isinstance(item, V2WorkResolution) and item.status == "resolved")
                ]
                visited_ids = {
                    work.provider_work_id for work in seed_works if work.provider_work_id
                }
                visited_dois = {work.doi for work in seed_works if work.doi}
                visited_ids.update(
                    edge.candidate.work.provider_work_id
                    for result in earlier
                    for edge in result.edges
                )
                visited_dois.update(
                    edge.candidate.work.doi for result in earlier for edge in result.edges
                )
                for round_number in range(1, action.round_number):
                    dkey, _ = _round_keys(round_number)
                    try:
                        discovered = V2DiscoveryScoutOutput.model_validate_json(
                            read_v2_artifact(path, action.run_id, dkey).payload_json
                        )
                    except KeyError:
                        continue
                    visited_dois.update(item.doi for item in discovered.items if item.doi)
                    visited_ids.update(
                        _work_id(_metadata(item, "external_id")) for item in discovered.items
                    )
                headroom = min(
                    action.requested_depth,
                    binding.policy.max_neighbors_per_seed - len(used_seed),
                    binding.policy.max_expansion_per_run - len(used_run),
                )
                if binding.seed_identity == SEED_EXECUTION_ID:
                    headroom = min(
                        headroom,
                        retention_headroom(
                            path,
                            action.run_id,
                            action.round_number,
                            excluding_operation_id=action.artifact_id,
                        ),
                    )
                for item in cp.results:
                    wid = _work_id(item.metadata.external_id)
                    if not wid:
                        continue
                    work = neighbor_work_identity(item)
                    doi = work.doi
                    raw = raw_neighbor_candidate(action, cp, item)
                    insert_raw_candidate(path, raw, clock())
                    duplicate = (
                        wid in visited_ids
                        or (doi and doi in visited_dois)
                        or work.grouping_key in used_run
                    )
                    excluded = item.metadata.is_retracted is True or item.metadata.work_type in {
                        "retraction",
                        "withdrawn",
                    }
                    if duplicate or excluded or len(edges) >= headroom:
                        dkey = f"disposition/{raw.artifact_id}"
                        insert_candidate_disposition(
                            path,
                            V2CandidateDisposition(
                                run_id=action.run_id,
                                artifact_id=discovery_id(
                                    action.run_id, "V2CandidateDisposition", dkey
                                ),
                                identity_key=dkey,
                                candidate_id=raw.artifact_id,
                                operation_id=action.artifact_id,
                                round_number=action.round_number,
                                disposition="duplicate"
                                if duplicate
                                else "excluded"
                                if excluded
                                else "cap_prevented",
                                reason="Visited work or DOI alias"
                                if duplicate
                                else "Retracted/withdrawn"
                                if excluded
                                else "Expansion capacity exhausted",
                            ),
                            clock(),
                        )
                        continue
                    nkey = f"normalized-neighbor/{raw.artifact_id}"
                    normalized = V2NormalizedDiscoveryCandidate(
                        run_id=action.run_id,
                        artifact_id=discovery_id(
                            action.run_id, "V2NormalizedDiscoveryCandidate", nkey
                        ),
                        identity_key=nkey,
                        raw_candidates=(raw,),
                        work=work,
                        locations=raw.locations,
                        rank=V2RankComponents(
                            rationale="Relationship metadata only; common ranking follows"
                        ),
                        disposition="retained",
                        disposition_reason="Ordinary ranking/Scout/acquisition required",
                    )
                    insert_discovery_candidate(path, normalized, clock())
                    ekey = f"edge/{raw.artifact_id}"
                    edge = V2ExpansionEdge(
                        run_id=action.run_id,
                        artifact_id=discovery_id(action.run_id, "V2ExpansionEdge", ekey),
                        identity_key=ekey,
                        action=action,
                        candidate=raw,
                        edge_verification="provider_reported",
                    )
                    edges.append(edge)
                    results.append(item)
                    used_run.add(work.grouping_key)
                    visited_ids.add(wid)
                    if doi:
                        visited_dois.add(doi)
            else:
                reason = "Unresolved, conflicting, retracted or unsupported seed"
    except SearchProviderError as exc:
        unknown = provider_attempt_audit(path, action.run_id).interrupted_unknown
        status = (
            "interrupted_unknown"
            if unknown
            else "pending"
            if exc.code in {SearchFailureCode.CANCELLED, SearchFailureCode.BUDGET_EXHAUSTED}
            else "unavailable"
        )
        reason = (
            "Unknown physical outcome; no further requests"
            if unknown
            else "Cancellation or capacity exhausted with partial state"
            if status == "pending"
            else "Provider failure; attempted action retained"
        )
    except (httpx.HTTPError, ValidationError):
        unknown = provider_attempt_audit(path, action.run_id).interrupted_unknown
        status = "interrupted_unknown" if unknown else "unavailable"
        reason = (
            "Unknown physical outcome"
            if unknown
            else "Invalid or malformed bounded provider metadata"
        )
    result = V2ExpansionResult(
        run_id=action.run_id,
        artifact_id=discovery_id(action.run_id, "V2ExpansionResult", key),
        identity_key=key,
        action=action,
        edges=tuple(edges) if status == "completed" else (),
        status=status,
        reason=reason,
    )
    # Pending progress has a separate immutable checkpoint identity on each boundary.
    if status == "pending":
        pkey = f"{key}/pending-{len(provider_attempt_audit(path, action.run_id).starts)}"
        result = result.model_copy(
            update={
                "identity_key": pkey,
                "artifact_id": discovery_id(action.run_id, "V2ExpansionResult", pkey),
            }
        )
    insert_expansion_result(path, result, clock())
    return tuple(results) if status == "completed" else ()
