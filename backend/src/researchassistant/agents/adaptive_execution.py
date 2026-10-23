"""Physical adaptive search execution and durable round checkpoints."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

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
from researchassistant.agents.v2_acquisition import run_v2_acquisition_probe
from researchassistant.agents.v2_discovery import V2DiscoveryResponse, run_v2_discovery_and_scout
from researchassistant.contracts.model_research import (
    V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
    V2AcquisitionPolicy,
)
from researchassistant.contracts.models import (
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2DiscoveryScoutOutput,
)
from researchassistant.contracts.search import SearchFailureCode
from researchassistant.providers.llm import (
    LLMProvider,
)
from researchassistant.providers.scraper import ScraperProvider
from researchassistant.providers.search import SearchProvider, SearchProviderError
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.research.query_execution import (
    execute_query,
    fair_query_order,
)
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
    search = _execute_searches(path, plan, search_providers, cancellation_requested, clock)
    cancelled_after_search = _cancelled(cancellation_requested)
    responses = tuple(
        V2DiscoveryResponse(query=item.query, results=item.results)
        for item in search.outcomes
        if item.succeeded
    )
    if responses and not cancelled_after_search:
        discovery = run_v2_discovery_and_scout(
            db_path=path,
            planner_output=plan,
            responses=responses,
            llm_provider=llm_provider,
            routing_config=routing_config,
            clock=clock,
            crossref_resolver=crossref_resolver,
            cancellation_requested=cancellation_requested,
        ).output
    else:
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
    duplicate_ids = frozenset(
        cluster.cluster_id for cluster in discovery.clusters if _cluster_urls(cluster) & known_urls
    )
    cancelled_before_acquisition = _cancelled(cancellation_requested)
    if discovery.items and not cancelled_before_acquisition:
        acquisition = run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            exact_claim=exact_claim,
            asserted_components=asserted_components,
            target_gaps=preview_gaps,
            policy=V2AcquisitionPolicy(
                policy_identity=V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
                max_clusters=preview_binding.policy.max_acquisition_per_round,
            )
            if fresh_preview
            else None,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            excluded_cluster_ids=duplicate_ids,
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


def _execute_searches(
    path: str,
    plan: V2AdaptiveRoundPlan,
    providers: Mapping[DiscoveryProvider, SearchProvider],
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
) -> V2AdaptiveSearchResults:
    key = round_artifact_key(plan.round_number, "search-results")
    try:
        stored = read_v2_artifact(path, plan.run_id, key)
    except KeyError:
        stored = None
    if stored is not None:
        return V2AdaptiveSearchResults.model_validate_json(stored.payload_json)
    outcomes: list[V2AdaptiveSearchOutcome] = []
    for query in fair_query_order(plan.searches):
        if _cancelled(cancellation_requested):
            break
        try:
            if query.graph_action is not None:
                configured = providers.get(query.provider)
                adapter = getattr(configured, "neighborhood_adapter", None)
                if callable(adapter):
                    adapter = adapter()
                results = execute_expansion(
                    path=path,
                    action=query.graph_action,
                    adapter=adapter,
                    clock=clock,
                    cancellation_requested=cancellation_requested,
                )
                from researchassistant.contracts.search import SearchResponse

                response = SearchResponse(results=list(results), provider_name=query.provider.value)
            else:
                response = execute_query(
                    path=path,
                    run_id=query.run_id,
                    provider=query.provider,
                    query_text=query.query_text,
                    compiled_query=query.compiled_query,
                    providers=providers,
                    clock=clock,
                    cancellation_requested=cancellation_requested,
                )
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query, succeeded=True, results=tuple(response.results)
                )
            )
        except SearchProviderError as exc:
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query,
                    succeeded=False,
                    failure_code=exc.code.value,
                    failure_message=str(exc) or exc.code.value,
                )
            )
        except Exception as exc:
            outcomes.append(
                V2AdaptiveSearchOutcome(
                    query=query,
                    succeeded=False,
                    failure_code=SearchFailureCode.PERMANENT_FAILURE.value,
                    failure_message=f"{type(exc).__name__}: {exc}"[:500],
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
