"""Deterministic seed offers and accounted, resumable one-hop action execution."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from uuid import UUID

import httpx
from pydantic import ValidationError

from providers.openalex_neighborhood import (
    NeighborhoodRelation,
    OpenAlexNeighborhoodAdapter,
    ResolvedOpenAlexWork,
)
from providers.search import SearchFailureCode, SearchProviderError, SearchResult
from researchassistant.common.money import parse_exact_usd
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
    V2RawDiscoveryCandidate,
    V2SanitizedParameter,
    V2SeedEligibility,
    V2SourceLocation,
    V2WorkIdentity,
    V2WorkResolution,
    discovery_hash,
    discovery_id,
    normalize_doi,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    NormalizedDiscoveryItem,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
)
from researchassistant.contracts.neighborhood import (
    V2NeighborhoodCheckpoint,
    V2NeighborhoodResponse,
    V2SeedSelection,
)
from researchassistant.contracts.query_planning import V2ConceptualAdaptiveLane
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
from researchassistant.storage.query_retrieval_store import retention_headroom
from researchassistant.storage.store import read_v2_artifact

SEED_EXECUTION_ID = "source-seed-expansion-v2"


def _round_keys(round_number: int) -> tuple[str, str]:
    if round_number == 1:
        return "phase-4-discovery-scout", "phase-5-acquisition-probe"
    if round_number == 4:
        return (
            "post-phase-13-round-4-discovery-scout-v1",
            "post-phase-13-round-4-acquisition-probe-v1",
        )
    return (
        f"phase-7-round-{round_number}-discovery-scout",
        f"phase-7-round-{round_number}-acquisition-probe",
    )


def _work_id(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"(?:https://openalex.org/)?W[0-9]{1,20}", value):
        return "https://openalex.org/" + value.rsplit("/", 1)[-1]
    return None


def _metadata(item: NormalizedDiscoveryItem, key: str) -> object:
    for entry in item.provider_metadata:
        if entry.key == key:
            return json.loads(entry.value_json)
    return None


def pipeline_work_identity(item: NormalizedDiscoveryItem) -> V2WorkIdentity:
    external_id = _work_id(_metadata(item, "external_id"))
    year = (
        int(item.publication_date[:4])
        if item.publication_date and item.publication_date[:4].isdigit()
        else None
    )
    if not item.doi and not external_id:
        raise ValueError("pipeline seed lacks exact DOI/OpenAlex identifier")
    return V2WorkIdentity(
        grouping_key=f"doi:{item.doi}" if item.doi else external_id,
        doi=item.doi,
        provider_work_id=external_id,
        title=item.title,
        authors=item.authors or None,
        publication_year=year,
        resolution="verified_identifiers" if item.doi else "provider_identity",
    )


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
        binding.seed_identity == SEED_EXECUTION_ID
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
                    seed_identity=SEED_EXECUTION_ID,
                    reason="Relevant owned preview, scholarly metadata and exact identifier",
                )
                insert_pipeline_seed(path, seed, dkey, akey, clock())
                seeds.append(seed)
                selected.append(seed)
    result = V2SeedSelection(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2SeedSelection", key),
        identity_key=key,
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
    if binding.seed_identity != SEED_EXECUTION_ID or round_number not in {2, 3, 4}:
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
                    seed_identity=SEED_EXECUTION_ID,
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


def _resolved_identity(work: ResolvedOpenAlexWork) -> V2WorkIdentity:
    doi = normalize_doi(work.doi) if work.doi else None
    return V2WorkIdentity(
        grouping_key=f"doi:{doi}" if doi else work.openalex_id,
        doi=doi,
        provider_work_id=work.openalex_id,
        title=work.title,
        authors=work.authors or None,
        publication_year=work.year,
        resolution="verified_identifiers" if doi else "provider_identity",
    )


def _matches_seed(seed: V2SeedEligibility, work: ResolvedOpenAlexWork) -> bool:
    identity = _resolved_identity(work)
    expected = seed.work
    if (
        work.is_retracted is True
        or work.is_withdrawn is True
        or work.work_type in {"retraction", "withdrawn"}
    ):
        return False
    if expected.doi and identity.doi != expected.doi:
        return False
    if expected.provider_work_id and identity.provider_work_id != expected.provider_work_id:
        return False
    if expected.publication_year and identity.publication_year != expected.publication_year:
        return False

    def title_key(value: str) -> str:
        return " ".join(re.findall(r"\w+", value.casefold()))

    if expected.title and title_key(identity.title or "") != title_key(expected.title):
        return False
    if expected.authors and identity.authors:
        observed_authors = {x.casefold() for x in expected.authors}
        resolved_authors = {x.casefold() for x in identity.authors}
        # Providers can expose only a prefix/subset of the author list. Additional
        # compatible coauthors are missing metadata, not an identity contradiction.
        if not (observed_authors <= resolved_authors or resolved_authors <= observed_authors):
            return False
    return True


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
        cp = V2NeighborhoodCheckpoint.model_validate_json(
            read_v2_artifact(
                path, action.run_id, f"source-discovery-v1:V2NeighborhoodCheckpoint:{key}"
            ).payload_json
        )
        if cp.action != action:
            raise ValueError("Neighborhood parser checkpoint action differs")
        audit = provider_attempt_audit(path, action.run_id)
        complete = next((x for x in audit.completions if x and x.attempt_id == cp.attempt_id), None)
        if (
            not complete
            or complete.status != "completed"
            or complete.response_hash != cp.response_hash
        ):
            raise ValueError("Neighborhood parser lacks completed physical response")
        try:
            body = V2NeighborhoodResponse.model_validate_json(
                read_v2_artifact(
                    path,
                    action.run_id,
                    f"source-discovery-v1:V2NeighborhoodResponse:graph-response/{cp.attempt_id}",
                ).payload_json
            )
        except KeyError:
            body = None
        start = next((x for x in audit.starts if x.artifact_id == cp.attempt_id), None)
        if start is None:
            raise ValueError("Neighborhood checkpoint lacks durable request")
        if phase == "identity" and start.request_kind != "identity":
            raise ValueError("Seed identity checkpoint requires an exact identity request")
        owned_operation = next(
            (
                item
                for item in read_discovery_artifacts(path, action.run_id)
                if isinstance(item, V2DiscoveryOperation)
                and item.action.artifact_id == start.operation_id
            ),
            None,
        )
        if (
            owned_operation is None
            or not isinstance(owned_operation.action, V2GraphNeighborAction)
            or owned_operation.action.seed != action.seed
            or owned_operation.action.provider != action.provider
            or complete.operation_id != start.operation_id
            or (
                phase == "neighbors"
                and start.request_kind == "primary"
                and owned_operation.action != action
            )
        ):
            raise ValueError("Neighborhood response differs from owned seed/action request")
        if body is not None and (
            body.run_id != action.run_id
            or body.attempt_id != cp.attempt_id
            or body.operation_id != start.operation_id
            or body.response_hash != cp.response_hash
        ):
            raise ValueError("Exact provider body differs from completed response")
        if phase == "identity":
            if body is None:
                raise ValueError("Identity checkpoint lacks exact provider response")
            parsed = OpenAlexNeighborhoodAdapter.parse_resolution(
                action.seed.work.provider_work_id or action.seed.work.doi or "",
                httpx.Response(200, content=body.content.encode()),
            )
        elif (
            body is not None
            and next(x for x in audit.starts if x.artifact_id == cp.attempt_id).request_kind
            == "primary"
        ):
            if cp.work is None:
                raise ValueError("Neighbor checkpoint lacks exact identity")
            identity = _checkpoint(path, action, "identity", adapter, binding, clock, cancelled)
            if cp.work != identity.work:
                raise ValueError("Neighbor checkpoint differs from exact resolved seed")
            start = next(x for x in audit.starts if x.artifact_id == cp.attempt_id)
            parsed = OpenAlexNeighborhoodAdapter.parse_expansion(
                cp.work,
                NeighborhoodRelation(action.relationship),
                limit=start.requested_records,
                response=httpx.Response(200, content=body.content.encode()),
            )
        else:
            # No neighbor HTTP request for absent/empty relationship fields.
            identity = _checkpoint(path, action, "identity", adapter, binding, clock, cancelled)
            if cp.work != identity.work or cp.work is None or cp.results:
                raise ValueError("No-request neighbor checkpoint differs from exact seed")
            field = (
                cp.work.referenced_work_ids
                if action.relationship == "references"
                else cp.work.related_work_ids
            )
            if (
                action.relationship == "citing"
                or (field and len(field) > 0)
                or cp.status != ("unsupported" if field is None else "empty")
            ):
                raise ValueError("No-request relationship disposition differs from provider field")
            return cp
        if (
            parsed.work != cp.work
            or parsed.results != cp.results
            or parsed.status.value != cp.status
        ):
            raise ValueError("Parser checkpoint differs from exact provider response")
        return cp
    except KeyError:
        pass
    if phase == "identity":
        for prior in read_discovery_artifacts(path, action.run_id):
            if (
                isinstance(prior, V2NeighborhoodCheckpoint)
                and prior.phase == "identity"
                and prior.action.seed == action.seed
            ):
                audit = provider_attempt_audit(path, action.run_id)
                if not any(
                    x
                    and x.status == "completed"
                    and x.attempt_id == prior.attempt_id
                    and x.response_hash == prior.response_hash
                    for x in audit.completions
                ):
                    raise ValueError("Shared seed resolution lacks physical ownership")
                return _checkpoint(
                    path, prior.action, "identity", adapter, binding, clock, cancelled
                )
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


def neighbor_work_identity(item: SearchResult) -> V2WorkIdentity:
    wid = _work_id(item.metadata.external_id)
    if wid is None:
        raise ValueError("neighbor requires canonical provider identity")
    doi = normalize_doi(item.metadata.doi) if item.metadata.doi else None
    return V2WorkIdentity(
        grouping_key=f"doi:{doi}" if doi else wid,
        doi=doi,
        provider_work_id=wid,
        title=item.title or None,
        authors=tuple(item.metadata.author.split("; ")) if item.metadata.author else None,
        publication_year=int(item.metadata.published_at[:4])
        if item.metadata.published_at
        else None,
        resolution="verified_identifiers" if doi else "provider_identity",
    )


def raw_neighbor_candidate(
    action: V2GraphNeighborAction, cp: V2NeighborhoodCheckpoint, item: SearchResult
) -> V2RawDiscoveryCandidate:
    """Derive raw metadata only from an exactly reparsed provider record."""
    work = neighbor_work_identity(item)
    wid = work.provider_work_id
    if wid is None:
        raise ValueError("neighbor requires canonical provider identity")
    ckey = f"neighbor/{action.artifact_id}/{wid.rsplit('/', 1)[-1]}"
    raw = V2RawDiscoveryCandidate(
        run_id=action.run_id,
        artifact_id=discovery_id(action.run_id, "V2RawDiscoveryCandidate", ckey),
        identity_key=ckey,
        operation_id=action.artifact_id,
        attempt_id=cp.attempt_id,
        response_hash=cp.response_hash,
        provider=action.provider,
        direction=action.direction,
        round_number=action.round_number,
        provider_rank=item.rank,
        work=work,
        abstract=item.metadata.abstract,
        study_design=item.metadata.work_type,
        locations=tuple(
            V2SourceLocation(
                url=url,
                same_work_basis="provider_identity",
                kind="pdf" if url == item.metadata.pdf_url else "landing",
            )
            for url in dict.fromkeys(
                x
                for x in (
                    item.original_url,
                    item.metadata.pdf_url,
                    item.metadata.full_text_url,
                )
                if x
            )
        ),
    )
    return raw


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
