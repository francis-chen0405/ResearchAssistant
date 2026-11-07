"""Physical adaptive search execution and durable round checkpoints."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID

from researchassistant.agents.adaptive_handoffs import (
    V2AdaptivePlannedRound as V2AdaptivePlannedRound,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveRoundExecution as V2AdaptiveRoundExecution,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveRoundStatus as V2AdaptiveRoundStatus,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveSearchOutcome as V2AdaptiveSearchOutcome,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveSearchResults as V2AdaptiveSearchResults,
)
from researchassistant.agents.adaptive_handoffs import (
    _cancelled as _cancelled,
)
from researchassistant.agents.adaptive_handoffs import (
    round_artifact_key as round_artifact_key,
)
from researchassistant.agents.adaptive_summary import (
    _cluster_urls as _cluster_urls,
)
from researchassistant.agents.capture_overlap import (
    CaptureOverlap,
    bind_capture_overlap,
    initial_capture_slots,
    production_capture_policy,
    supports_progressive_overlap,
)
from researchassistant.agents.discovery_overlap import (
    DiscoveryResponses,
    FirstPass,
    scout_during_search,
)
from researchassistant.agents.v2_acquisition import (
    acquisition_artifact_key,
    prior_publication_clusters,
    run_v2_acquisition_probe,
)
from researchassistant.agents.v2_discovery import (
    ScoutHandoff,
    V2DiscoveryResponse,
    V2DiscoveryScoutRunResult,
    run_v2_discovery_and_scout,
)
from researchassistant.contracts.discovery_v2 import V2GraphNeighborAction
from researchassistant.contracts.models import (
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchQuery,
    V2DiscoveryScoutOutput,
)
from researchassistant.contracts.search import SearchResponse
from researchassistant.providers.llm import (
    LLMProvider,
)
from researchassistant.providers.scraper import ScraperProvider
from researchassistant.providers.search import SearchProvider
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.research.metadata_ranking import RANKING_IDENTITY
from researchassistant.research.query_execution import execute_query_round, read_query_first_pass
from researchassistant.research.seed_expansion import execute_expansion
from researchassistant.storage.discovery_store import read_discovery_binding
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact


def _run_round_from_plan(
    *,
    path: str,
    planned: V2AdaptivePlannedRound,
    exact_claim: str,
    asserted_components: tuple[str, ...],
    preview_gaps: tuple[str, ...],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None,
    known_urls: frozenset[str],
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
    recover_incomplete_publications: bool = True,
) -> tuple[
    V2AdaptiveSearchResults,
    V2DiscoveryScoutOutput,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundExecution,
]:
    plan = planned.plan
    execution_key = round_artifact_key(plan.round_number, "execution")
    try:
        saved_execution = read_v2_artifact(path, plan.run_id, execution_key)
    except KeyError:
        saved_execution = None
    previous_summary = (
        V2AdaptiveRoundExecution.model_validate_json(saved_execution.payload_json)
        if saved_execution is not None
        else None
    )
    try:
        preview_binding = read_discovery_binding(path, plan.run_id)
    except KeyError:
        preview_binding = None
    fresh_preview = (
        preview_binding is not None
        and preview_binding.preview_identity == "source-claim-preview-v2"
    )
    key = acquisition_artifact_key(plan.round_number)
    policy = (
        production_capture_policy(
            path, plan.run_id, key, preview_binding.policy.max_acquisition_per_round
        )
        if fresh_preview
        else None
    )
    claim_ranking = (
        preview_binding is not None and preview_binding.ranking_identity == RANKING_IDENTITY
    )

    def exclusions(output: V2DiscoveryScoutOutput) -> tuple[frozenset[UUID], frozenset[str]]:
        return _capture_exclusions(
            path,
            output,
            plan.round_number,
            known_urls,
            claim_ranking,
            recover_incomplete_publications,
        )

    def scout(
        responses: DiscoveryResponses,
        on_batch: ScoutHandoff | None,
        cancelled: Callable[[], bool],
        first_pass_only: bool = False,
        first_pass: V2DiscoveryScoutRunResult | None = None,
    ) -> V2DiscoveryScoutRunResult:
        if not responses or cancelled():
            discovery = empty_discovery()
            return V2DiscoveryScoutRunResult(output=discovery, resumed=False)
        return run_v2_discovery_and_scout(
            db_path=path,
            planner_output=plan,
            responses=responses,
            llm_provider=llm_provider,
            routing_config=routing_config,
            clock=clock,
            crossref_resolver=crossref_resolver,
            cancellation_requested=cancelled,
            target_gaps=preview_gaps,
            on_batch=on_batch,
            first_pass_only=first_pass_only,
            first_pass=first_pass,
        )

    def empty_discovery() -> V2DiscoveryScoutOutput:
        key = round_artifact_key(plan.round_number, "discovery-scout")
        try:
            saved_discovery = read_v2_artifact(path, plan.run_id, key)
        except KeyError:
            saved_discovery = None
        discovery = V2DiscoveryScoutOutput(
            run_id=plan.run_id,
            directions=plan.directions,
            items=(),
            clusters=(),
            scout_batches=(),
            scout_audits=(),
            completed_at=(
                V2DiscoveryScoutOutput.model_validate_json(
                    saved_discovery.payload_json
                ).completed_at
                if saved_discovery is not None
                else clock()
            ),
        )
        insert_v2_artifact(
            path,
            key,
            discovery,
            saved_discovery.created_at if saved_discovery is not None else discovery.completed_at,
        )
        return discovery

    def execute_search(
        on_first_pass: FirstPass | None,
        cancelled: Callable[[], bool],
    ) -> V2AdaptiveSearchResults:
        return _execute_searches(
            path,
            plan,
            search_providers,
            cancelled,
            clock,
            on_first_pass,
        )

    def search_responses(search: V2AdaptiveSearchResults) -> DiscoveryResponses:
        return tuple(
            V2DiscoveryResponse(query=item.query, results=item.results)
            for item in search.outcomes
            if item.succeeded
        )

    search = None
    completed_captures = None
    slots = initial_capture_slots(path, plan.run_id) if claim_ranking else None
    slots = bind_capture_overlap(path, plan.run_id, key, slots, clock) if slots else None
    progressive = slots is not None and supports_progressive_overlap(path, plan.run_id, key)

    def cancelled() -> bool:
        return _cancelled(cancellation_requested)

    if slots is not None and policy is not None and not cancelled():

        def discover(
            on_batch: ScoutHandoff | None,
            stopped: Callable[[], bool],
        ) -> V2DiscoveryScoutRunResult:
            nonlocal search
            search, output = scout_during_search(
                execute=execute_search,
                responses=search_responses,
                scout=scout,
                on_batch=on_batch,
                cancelled=stopped,
                progressive=progressive,
            )
            return output

        overlap = CaptureOverlap(
            path=path,
            run_id=plan.run_id,
            artifact_key=key,
            policy=policy,
            exact_claim=exact_claim,
            asserted_components=asserted_components,
            target_gaps=preview_gaps,
            capture_slots=slots,
            direction_target=getattr(
                preview_binding.policy, "sources_per_direction_per_round", None
            ),
            primary=wigolo_provider,
            fallback=firecrawl_provider,
            cancellation_requested=cancellation_requested,
            clock=clock,
            exclusions=exclusions,
        )
        discovered, completed_captures, _checkpoint = overlap.run(discover)
    else:
        search = execute_search(None, cancelled)
        discovered = scout(search_responses(search), None, cancelled)
    assert search is not None
    cancelled_after_search = cancelled()
    discovery = discovered.output
    duplicate_ids, excluded_capture_urls = exclusions(discovery)
    cancelled_before_acquisition = _cancelled(cancellation_requested)
    if discovery.items and not cancelled_before_acquisition:
        acquisition = run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            exact_claim=exact_claim,
            asserted_components=asserted_components,
            target_gaps=preview_gaps,
            policy=policy,
            completed_captures=completed_captures,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            excluded_cluster_ids=duplicate_ids,
            excluded_capture_urls=excluded_capture_urls,
            cancellation_requested=cancellation_requested,
            clock=clock,
        ).output
    else:
        key = round_artifact_key(plan.round_number, "acquisition-probe")
        try:
            saved_acquisition = read_v2_artifact(path, plan.run_id, key)
        except KeyError:
            saved_acquisition = None
        acquisition = V2AcquisitionProbeOutput(
            run_id=plan.run_id,
            directions=plan.directions,
            acquisitions=(),
            attempts=(),
            probes=(),
            survivors=(),
            completed_at=(
                V2AcquisitionProbeOutput.model_validate_json(
                    saved_acquisition.payload_json
                ).completed_at
                if saved_acquisition is not None
                else clock()
            ),
        )
        insert_v2_artifact(
            path,
            key,
            acquisition,
            saved_acquisition.created_at
            if saved_acquisition is not None
            else acquisition.completed_at,
        )
    cancelled = (
        cancelled_after_search
        or cancelled_before_acquisition
        or _cancelled(cancellation_requested)
        or (
            previous_summary is not None
            and previous_summary.status is V2AdaptiveRoundStatus.CANCELLED
        )
    )
    summary = V2AdaptiveRoundExecution(
        run_id=plan.run_id,
        round_number=plan.round_number,
        targeted_gap_ids=plan.targeted_gap_ids,
        status=(
            V2AdaptiveRoundStatus.CANCELLED
            if cancelled
            else V2AdaptiveRoundStatus.DEGRADED
            if any(not item.succeeded for item in search.outcomes)
            else V2AdaptiveRoundStatus.COMPLETED
        ),
        planned_query_count=len(plan.searches),
        completed_query_count=sum(item.succeeded for item in search.outcomes),
        failed_query_count=sum(not item.succeeded for item in search.outcomes),
        new_source_count=len(discovery.clusters) - len(duplicate_ids),
        duplicate_source_count=len(duplicate_ids),
        survivor_additions=len(acquisition.survivors),
        completed_at=previous_summary.completed_at if previous_summary is not None else clock(),
    )
    insert_v2_artifact(
        path,
        execution_key,
        summary,
        saved_execution.created_at if saved_execution is not None else summary.completed_at,
    )
    return search, discovery, acquisition, summary


def _capture_exclusions(
    path: str,
    discovery: V2DiscoveryScoutOutput,
    round_number: int,
    known_urls: frozenset[str],
    claim_ranking: bool,
    recover_incomplete_publications: bool,
) -> tuple[frozenset[UUID], frozenset[str]]:
    cluster_locations = {
        cluster.cluster_id: _cluster_urls(cluster) for cluster in discovery.clusters
    }
    duplicate_ids = frozenset(
        cluster_id for cluster_id, locations in cluster_locations.items() if locations & known_urls
    )
    excluded_capture_urls = frozenset()
    if discovery.items and claim_ranking:
        adequate, incomplete, attempted_urls = prior_publication_clusters(
            path, discovery, round_number, recover_incomplete=recover_incomplete_publications
        )
        recoverable = {
            cluster_id
            for cluster_id in incomplete
            if cluster_locations[cluster_id] - attempted_urls
        }
        duplicate_ids = (duplicate_ids - recoverable) | adequate | (incomplete - recoverable)
        excluded_capture_urls = attempted_urls & frozenset(
            url for cluster_id in recoverable for url in cluster_locations[cluster_id]
        )
    return duplicate_ids, excluded_capture_urls


def _execute_searches(
    path: str,
    plan: V2AdaptiveRoundPlan,
    providers: Mapping[DiscoveryProvider, SearchProvider],
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
    on_first_pass: FirstPass | None = None,
) -> V2AdaptiveSearchResults:
    key = round_artifact_key(plan.round_number, "search-results")
    try:
        stored = read_v2_artifact(path, plan.run_id, key)
    except KeyError:
        stored = None

    def publish(rows: tuple[tuple[V2AdaptiveSearchQuery, SearchResponse], ...]) -> None:
        if on_first_pass is not None and rows:
            on_first_pass(
                tuple(
                    V2DiscoveryResponse(query=query, results=tuple(response.results))
                    for query, response in rows
                )
            )

    if stored is not None:
        if on_first_pass is not None:
            publish(read_query_first_pass(path, plan.searches) or ())
        return V2AdaptiveSearchResults.model_validate_json(stored.payload_json)

    def execute_graph(action: V2GraphNeighborAction) -> SearchResponse:
        configured = providers.get(action.provider)
        adapter = getattr(configured, "neighborhood_adapter", None)
        if callable(adapter):
            adapter = adapter()
        results = execute_expansion(
            path=path,
            action=action,
            adapter=adapter,
            clock=clock,
            cancellation_requested=cancellation_requested,
        )
        return SearchResponse(results=list(results), provider_name=action.provider.value)

    outcomes: list[V2AdaptiveSearchOutcome] = []
    for query, response in execute_query_round(
        plan.searches,
        path=path,
        providers=providers,
        clock=clock,
        cancellation_requested=cancellation_requested,
        execute_graph=execute_graph,
        on_first_pass=publish if on_first_pass is not None else None,
    ):
        if isinstance(response, SearchResponse):
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query, succeeded=True, results=tuple(response.results)
                )
            )
        else:
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query,
                    succeeded=False,
                    failure_code=response.code.value,
                    failure_message=str(response) or response.code.value,
                )
            )
    result = V2AdaptiveSearchResults(
        run_id=plan.run_id,
        round_number=plan.round_number,
        outcomes=tuple(outcomes),
        completed_at=clock(),
    )
    insert_v2_artifact(path, key, result, result.completed_at)
    return result


def search_failure_explanation(path: str, result: V2AdaptiveSearchResults) -> str:
    from researchassistant.storage.query_dispatch import query_dispatch_states

    states = query_dispatch_states(path, result.run_id)
    blocked = 0
    unknown = 0
    partial = 0
    failed = 0
    for outcome in result.outcomes:
        action = outcome.query.graph_action or outcome.query.compiled_query
        state = states.get(action.artifact_id) if action else None
        if state == "blocked":
            blocked += 1
        elif state == "unknown":
            unknown += 1
            partial += outcome.succeeded and bool(outcome.results)
        elif not outcome.succeeded:
            failed += 1
    if blocked or unknown:
        partial_detail = f" (including {partial} with retained partial results)" if partial else ""
        unknown_detail = f"{unknown} searches with unknown request outcomes{partial_detail}"
        return (
            f"Round {result.round_number} stopped: {failed} failed searches, "
            f"{unknown_detail}, and {blocked} searches blocked before dispatch by the "
            "unknown-request safeguard. "
            "Completed work was preserved."
        )
    return (
        f"Round {result.round_number} stopped after search failures; completed work was preserved."
    )
