"""Deterministic opt-in policy helpers; no transports or production activation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field

from providers.llm import LLMStage
from providers.ranking import canonical_discovery_url
from providers.v2_budget import V2BudgetSnapshot
from providers.v2_routing import V2ModelReservation, V2RoutingConfig
from researchassistant.common.money import add_usd
from researchassistant.contracts import discovery_v2
from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryBinding,
    V2DiscoveryPolicy,
    V2DiscoveryProviderBudget,
    V2DiscoveryValue,
    V2ProviderCapabilities,
    discovery_hash,
    discovery_id,
    normalize_doi,
    safe_location,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import ResearchDirection, ResearchDirections
from researchassistant.runtime.application_runtime import repository_identity

# Keep the established mandatory downstream reserve; this module can only tighten it.
MANDATORY_DOWNSTREAM_CALLS = 8
SCOUT_BATCH_SIZE = 20
_PROVIDER_ORDER = (
    DiscoveryProvider.SERPSEARCH,
    DiscoveryProvider.EXA,
    DiscoveryProvider.OPENALEX,
    DiscoveryProvider.ARXIV,
    DiscoveryProvider.PUBMED,
)


class V2DiscoveryLaneQuota(V2DiscoveryValue):
    direction: ResearchDirection
    provider: DiscoveryProvider
    candidates: int = Field(strict=True, ge=0, le=300)


def fair_candidate_quotas(
    *,
    policy: V2DiscoveryPolicy,
    directions: ResearchDirections,
    providers: tuple[DiscoveryProvider, ...],
    available_by_lane: Mapping[tuple[ResearchDirection, DiscoveryProvider], int],
    retained_run_count: int,
    retained_round_count: int = 0,
    stage: Literal["retention", "scout", "acquisition"] = "retention",
    safely_available_model_candidates: int | None = None,
) -> tuple[V2DiscoveryLaneQuota, ...]:
    """Allocate after collecting bounded lane outcomes, never by response arrival order.

    Each enabled lane receives one candidate per pass until its demand or the shared
    remaining cap is exhausted. Missing/failed lanes have zero demand; their spare
    share returns to the remaining enabled lanes. Callers retain stable provider-rank
    and application-ID ordering within each quota.
    """
    if len(set(providers)) != len(providers) or not providers:
        raise ValueError("fair allocation requires unique enabled providers")
    if not set(providers) <= set(_PROVIDER_ORDER):
        raise ValueError("unsupported discovery provider")
    if any(
        type(value) is not int or value < 0 for value in (retained_run_count, retained_round_count)
    ):
        raise ValueError("retained candidate counts must be nonnegative integers")
    lanes = tuple(
        (direction, provider)
        for direction in directions.enabled_directions
        for provider in _PROVIDER_ORDER
        if provider in providers
    )
    if not set(available_by_lane) <= set(lanes):
        raise ValueError("allocation demand contains a disabled direction/provider")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in available_by_lane.values()
    ):
        raise ValueError("lane candidate demand must be nonnegative integers")
    raw_capacity = max(
        0,
        min(
            policy.max_raw_per_round - retained_round_count,
            policy.max_raw_per_run - retained_run_count,
        ),
    )
    if stage == "retention":
        remaining = raw_capacity
    elif stage == "scout":
        if (
            type(safely_available_model_candidates) is not int
            or safely_available_model_candidates < 0
        ):
            raise ValueError("Scout allocation requires safely available model capacity")
        remaining = min(policy.max_scout_per_round, safely_available_model_candidates)
    elif stage == "acquisition":
        remaining = policy.max_acquisition_per_round
    else:
        raise ValueError("invalid discovery allocation stage")
    allocated = dict.fromkeys(lanes, 0)
    while remaining:
        progressed = False
        for lane in lanes:
            if not remaining:
                break
            if allocated[lane] < available_by_lane.get(lane, 0):
                allocated[lane] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    return tuple(
        V2DiscoveryLaneQuota(direction=d, provider=p, candidates=allocated[d, p]) for d, p in lanes
    )


def effective_metadata_depth(
    policy: V2DiscoveryPolicy,
    capabilities: V2ProviderCapabilities,
    requested_depth: int,
    remaining_requests: int,
    *,
    executable: bool = True,
) -> int:
    """Zero means no request may start; provider caps always dominate desired depth."""
    if type(requested_depth) is not int or not 1 <= requested_depth <= 50:
        raise ValueError("requested metadata depth must be 1–50")
    if type(remaining_requests) is not int or remaining_requests < 0:
        raise ValueError("remaining requests must be nonnegative")
    pages = min(policy.max_pages_per_operation, remaining_requests) // (
        capabilities.physical_requests_per_page
    )
    pagination = capabilities.executable_pagination if executable else capabilities.pagination
    if pagination == "none":
        pages = min(1, pages)
    return min(
        policy.metadata_depth,
        requested_depth,
        capabilities.max_metadata_per_operation,
        capabilities.max_metadata_per_page * pages,
    )


def stable_work_key(*, doi: str | None, canonical_url: str) -> str:
    """Use DOI or existing canonical URL identity without broadening same-work merging.

    This key is a conservative grouping anchor. Existing title/author clustering can
    resolve additional duplicates later; this helper never equates author/title-only
    metadata with independently verified work identity.
    """
    safe_location(canonical_url)
    if doi is not None:
        return f"doi:{normalize_doi(doi)}"
    return f"url:{discovery_hash(canonical_discovery_url(canonical_url))}"


def safe_optional_model_prefix(
    *,
    snapshot: V2BudgetSnapshot,
    routing: V2RoutingConfig,
    downstream_input_tokens: Mapping[LLMStage, int],
    optional_reservations: tuple[V2ModelReservation, ...],
) -> int:
    """Protect downstream calls/tokens/cost before any optional planning/Scout/selection.

    Callers must render and conservatively estimate actual downstream prompt inputs.
    This affordability helper does not reserve or authorize a physical model call;
    `BudgetedV2LLMProvider` remains the durable physical model accounting owner.
    """
    preflight = routing.preflight()
    stages = tuple(stage for stage, _route in preflight.routing)
    if set(downstream_input_tokens) != set(stages):
        raise ValueError("downstream protection requires complete configured stage estimates")
    protected = tuple(preflight.reserve(stage, downstream_input_tokens[stage]) for stage in stages)
    protected_tokens = MANDATORY_DOWNSTREAM_CALLS * max(item.reserved_tokens for item in protected)
    largest_cost = max(item.reserved_cost_usd for item in protected)
    protected_cost = add_usd(*(largest_cost for _ in range(MANDATORY_DOWNSTREAM_CALLS)))
    tokens = 0
    costs = protected_cost
    admitted = 0
    for reservation in optional_reservations:
        if reservation.stage not in {
            LLMStage.SCOUT,
            LLMStage.SEARCH_AGENT,
            LLMStage.SOURCE_SELECTION,
        }:
            raise ValueError("optional discovery workload has unsupported model stage")
        route = preflight.for_stage(reservation.stage)
        expected = preflight.reserve(reservation.stage, reservation.input_tokens)
        if reservation != expected or reservation.physical_model != route.physical_model:
            raise ValueError("optional reservation differs from selected route/budget")
        next_tokens = tokens + reservation.reserved_tokens
        next_costs = add_usd(costs, reservation.reserved_cost_usd)
        if (
            MANDATORY_DOWNSTREAM_CALLS + admitted + 1 > snapshot.physical_calls_remaining
            or protected_tokens + next_tokens > snapshot.tokens_remaining
            or next_costs > snapshot.cost_remaining_usd
        ):
            break
        tokens, costs = next_tokens, next_costs
        admitted += 1
    return admitted


def scout_candidate_capacity(
    policy: V2DiscoveryPolicy, safe_batches: int, available_candidates: int
) -> int:
    if any(type(value) is not int or value < 0 for value in (safe_batches, available_candidates)):
        raise ValueError("Scout capacity inputs must be nonnegative integers")
    return min(policy.max_scout_per_round, safe_batches * SCOUT_BATCH_SIZE, available_candidates)


def discovery_contract_schema_hash(root: Path) -> str:
    """Bind exact new schemas plus existing executable planning/Scout prompt bytes."""
    schemas = {
        name: value.model_json_schema()
        for name, value in vars(discovery_v2).items()
        if isinstance(value, type)
        and issubclass(value, V2DiscoveryValue)
        and value.__module__ == discovery_v2.__name__
    }
    prompts = {
        name: discovery_hash((root / "prompts" / name).read_text(encoding="utf-8"))
        for name in ("v2_initial_planner.md", "v2_scout.md", "search_agent.md")
    }
    return discovery_hash(
        json.dumps({"schemas": schemas, "prompts": prompts}, sort_keys=True, separators=(",", ":"))
    )


def build_discovery_binding(
    *,
    run_id: UUID,
    exact_claim: str,
    directions: ResearchDirections,
    providers: tuple[DiscoveryProvider, ...],
    policy: V2DiscoveryPolicy,
    capabilities: tuple[V2ProviderCapabilities, ...],
    provider_budgets: tuple[V2DiscoveryProviderBudget, ...],
    provider_configuration_hash: str,
    source_root: Path,
) -> V2DiscoveryBinding:
    """Freeze a new opt-in contract without altering legacy run fingerprint schemas."""
    return V2DiscoveryBinding(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2DiscoveryBinding", "binding"),
        identity_key="binding",
        exact_claim=exact_claim,
        directions=directions,
        providers=providers,
        policy=policy,
        capabilities=capabilities,
        provider_budgets=provider_budgets,
        provider_configuration_hash=provider_configuration_hash,
        source_identity_hash=repository_identity(source_root).removeprefix("source-sha256:"),
        prompt_schema_hash=discovery_contract_schema_hash(source_root),
    )


def stable_candidate_order(
    candidates: tuple[discovery_v2.V2RawDiscoveryCandidate, ...],
) -> tuple[discovery_v2.V2RawDiscoveryCandidate, ...]:
    """Keep scores provider-local and order candidates by owned lane/rank/identity."""
    if len({item.artifact_id for item in candidates}) != len(candidates):
        raise ValueError("candidate order cannot contain duplicate application identities")
    if len({item.run_id for item in candidates}) > 1:
        raise ValueError("candidate ordering cannot mix runs")
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.round_number,
                item.direction.value,
                _PROVIDER_ORDER.index(item.provider),
                str(item.operation_id),
                item.provider_rank,
                str(item.artifact_id),
            ),
        )
    )
