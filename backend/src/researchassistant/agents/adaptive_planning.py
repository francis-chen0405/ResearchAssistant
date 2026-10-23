"""Adaptive search planning, bounded lanes and deterministic novelty validation."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveBudgetError as V2AdaptiveBudgetError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveBudgetState as V2AdaptiveBudgetState,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveCancellationError as V2AdaptiveCancellationError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveNoContinuationError as V2AdaptiveNoContinuationError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptiveNoEligibleProviderError as V2AdaptiveNoEligibleProviderError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptivePlannedRound as V2AdaptivePlannedRound,
)
from researchassistant.agents.adaptive_handoffs import (
    V2AdaptivePlanValidationError as V2AdaptivePlanValidationError,
)
from researchassistant.agents.adaptive_handoffs import (
    V2PlanningAttempt as V2PlanningAttempt,
)
from researchassistant.agents.adaptive_handoffs import (
    V2PlanningOutcome as V2PlanningOutcome,
)
from researchassistant.agents.adaptive_handoffs import (
    V2PlanningRepairInput as V2PlanningRepairInput,
)
from researchassistant.agents.adaptive_handoffs import (
    V2SearchAgentReservation as V2SearchAgentReservation,
)
from researchassistant.agents.adaptive_handoffs import (
    _cancelled as _cancelled,
)
from researchassistant.agents.v2_gap_analysis import V2GapAnalysisRunResult
from researchassistant.common.money import add_usd
from researchassistant.common.resources import prompt_resource
from researchassistant.contracts.discovery_v2 import (
    SearchMode,
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2GraphNeighborAction,
    V2MetadataDiscoveryPolicy,
    discovery_id,
)
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchDirection,
    StrictModel,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchConceptsOutput,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchProposal,
    V2AdaptiveSearchQuery,
    V2GapAnalysisOutput,
    V2InitialPlannerOutput,
    V2PersistedArtifact,
    V2ProviderSearchBudget,
    V2SearchAgentInput,
)
from researchassistant.contracts.query_compiler import compile_query, conceptual_signature
from researchassistant.contracts.query_planning import (
    V2ConceptualAdaptiveLane,
    V2ConceptualSearchAgentInput,
    V2NeighborhoodSearchAgentInput,
    V2NeighborhoodSearchOutput,
)
from researchassistant.providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationError,
    LLMProvider,
    LLMRequest,
    LLMResponseValidationError,
    LLMStage,
    invoke_llm,
    load_prompt,
    load_prompt_file,
    render_stage_prompt,
)
from researchassistant.providers.mimo import MimoFailureCode, MimoProviderError
from researchassistant.providers.pricing import conservative_token_estimate
from researchassistant.providers.search import SearchProvider
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.research.query_execution import (
    available_query_budgets,
)
from researchassistant.research.seed_expansion import offer_expansions
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

_TOKEN_RE = re.compile(r"[a-z0-9]+")


_PROVIDER_TOTAL_CEILINGS = {
    DiscoveryProvider.SERPSEARCH: 12,
    DiscoveryProvider.EXA: 18,
    DiscoveryProvider.OPENALEX: 10,
    DiscoveryProvider.ARXIV: 6,
    DiscoveryProvider.PUBMED: 6,
    DiscoveryProvider.SERPER: 6,
}


_ROUND_TWO_PER_DIRECTION_CAPS = {
    DiscoveryProvider.SERPSEARCH: 2,
    DiscoveryProvider.EXA: 3,
    DiscoveryProvider.OPENALEX: 1,
    DiscoveryProvider.ARXIV: 1,
    DiscoveryProvider.PUBMED: 1,
    DiscoveryProvider.SERPER: 1,
}


def normalize_query_text(value: str) -> str:
    """Cheap canonical query form used for exact history rejection."""
    return " ".join(_TOKEN_RE.findall(value.casefold()))


def queries_are_materially_new(candidate: str, previous_queries: tuple[str, ...]) -> bool:
    """Reject exact repeats and obvious token-preserving or one-token rewrites."""
    normalized = normalize_query_text(candidate)
    if not normalized:
        return False
    candidate_tokens = Counter(normalized.split())
    for previous in previous_queries:
        prior = normalize_query_text(previous)
        if normalized == prior:
            return False
        prior_tokens = Counter(prior.split())
        difference = sum((candidate_tokens - prior_tokens).values()) + sum(
            (prior_tokens - candidate_tokens).values()
        )
        if difference <= 1:
            return False
    return True


def _plan_round(
    *,
    path: str,
    round_number: int,
    initial_plan: V2InitialPlannerOutput,
    gap_output: V2GapAnalysisOutput | V2GapAnalysisRunResult,
    previous_queries: tuple[str, ...],
    provider_attempts: Mapping[DiscoveryProvider, int],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    budget: V2AdaptiveBudgetState,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime],
    persist_artifact: Callable[
        [str, str, StrictModel, datetime], V2PersistedArtifact
    ] = insert_v2_artifact,
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
    legacy_prompt: bool = False,
    previous_compiled_queries: tuple[V2CompiledQueryAction, ...] = (),
) -> V2AdaptivePlannedRound:
    key = f"phase-7-round-{round_number}-plan"
    try:
        stored = read_v2_artifact(path, initial_plan.run_id, key)
    except KeyError:
        stored = None
    if stored is not None:
        return V2AdaptivePlannedRound.model_validate_json(stored.payload_json)
    legacy_prompt = legacy_prompt or all(
        query.compiled_query is None for query in initial_plan.searches
    )
    resolved_query_modes = dict(query_modes or {})
    for query in initial_plan.searches:
        if query.compiled_query is not None:
            resolved_query_modes.setdefault(query.provider, query.compiled_query.mode)
    previous_compiled_queries = previous_compiled_queries or tuple(
        query.compiled_query for query in initial_plan.searches if query.compiled_query is not None
    )
    if gap_output.result is None or not gap_output.result.continue_research:
        raise V2AdaptiveNoContinuationError(
            "Luna did not authorize a material adaptive search recommendation"
        )
    budgets = _eligible_budgets(initial_plan, provider_attempts, search_providers, path=path)
    if not budgets:
        raise V2AdaptiveNoEligibleProviderError(
            "No eligible enabled provider remains within its search ceiling."
        )
    maximum_queries = _maximum_queries(round_number, initial_plan, budgets)
    base_request_input = V2SearchAgentInput(
        run_id=initial_plan.run_id,
        exact_claim=initial_plan.raw_claim,
        round_number=round_number,
        directions=initial_plan.directions,
        eligible_providers=tuple(item.provider for item in budgets),
        material_gaps=gap_output.result.material_gaps,
        search_directions=gap_output.result.new_search_directions,
        discovered_terms=tuple(
            dict.fromkeys((*gap_output.input.discovered_terms, *gap_output.result.discovered_terms))
        )[:40],
        previous_queries=previous_queries,
        provider_budgets=budgets,
        maximum_queries=maximum_queries,
    )
    route = routing_config.preflight().for_stage(LLMStage.SEARCH_AGENT)
    if legacy_prompt:
        request_input: V2SearchAgentInput | V2ConceptualSearchAgentInput = base_request_input
        output_type = V2AdaptiveSearchModelOutput
        prompt = load_prompt(LLMStage.SEARCH_AGENT)
        lanes: tuple[V2ConceptualAdaptiveLane, ...] = ()
    else:
        if DiscoveryProvider.SERPER in base_request_input.eligible_providers:
            raise V2AdaptiveNoEligibleProviderError(
                "Serper has no provider-native conceptual query compiler"
            )
        lanes = _adaptive_concept_lanes(base_request_input, resolved_query_modes)
        if not lanes:
            raise V2AdaptiveNoEligibleProviderError(
                "No application-owned conceptual lane remains within the round limits."
            )
        offers = offer_expansions(path, initial_plan.run_id, round_number, lanes, clock)
        fresh_expansion = bool(offers)
        request_input = (
            V2NeighborhoodSearchAgentInput(
                request=base_request_input, lanes=lanes, offered_expansions=offers
            )
            if fresh_expansion
            else V2ConceptualSearchAgentInput(request=base_request_input, lanes=lanes)
        )
        output_type = (
            V2NeighborhoodSearchOutput if fresh_expansion else V2AdaptiveSearchConceptsOutput
        )
        prompt = load_prompt_file(
            prompt_resource("search_agent_v3.md" if fresh_expansion else "search_agent_v2.md"),
            expected_stage=LLMStage.SEARCH_AGENT,
        )
    request = LLMRequest(
        run_id=initial_plan.run_id,
        stage=LLMStage.SEARCH_AGENT,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, request_input, output_type),
        input_artifact=request_input,
        input_artifact_ids=(initial_plan.run_id,),
        requested_output_type=output_type,
        model_alias=route.logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.SEARCH_AGENT).generation,
    )
    plan, reservation = _plan_with_repair(
        persist_artifact=persist_artifact,
        path=path,
        request=request,
        request_input=request_input,
        base_request_input=base_request_input,
        lanes=lanes,
        query_modes=resolved_query_modes,
        previous_compiled_queries=previous_compiled_queries,
        output_type=output_type,
        legacy_prompt=legacy_prompt,
        llm_provider=llm_provider,
        routing_config=routing_config,
        budget=budget,
        budget_snapshot=budget_snapshot,
        cancellation_requested=cancellation_requested,
        clock=clock,
    )
    planned = V2AdaptivePlannedRound(
        run_id=initial_plan.run_id,
        plan=plan,
        reservation=V2SearchAgentReservation(
            input_tokens=reservation.input_tokens,
            output_tokens=reservation.output_tokens,
            reserved_tokens=reservation.reserved_tokens,
            reserved_cost_usd=reservation.reserved_cost_usd,
        ),
    )
    persist_artifact(path, key, planned, plan.planned_at)
    return planned


def _plan_with_repair(
    *,
    path: str,
    request: LLMRequest,
    request_input: V2SearchAgentInput | V2ConceptualSearchAgentInput,
    base_request_input: V2SearchAgentInput,
    lanes: tuple[V2ConceptualAdaptiveLane, ...],
    query_modes: Mapping[DiscoveryProvider, SearchMode],
    previous_compiled_queries: tuple[V2CompiledQueryAction, ...],
    output_type: type[V2AdaptiveSearchModelOutput] | type[V2AdaptiveSearchConceptsOutput],
    legacy_prompt: bool,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    budget: V2AdaptiveBudgetState,
    budget_snapshot: Callable[[], V2AdaptiveBudgetState] | None,
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
    persist_artifact: Callable[
        [str, str, StrictModel, datetime], V2PersistedArtifact
    ] = insert_v2_artifact,
) -> tuple[V2AdaptiveRoundPlan, V2SearchAgentReservation]:
    prior: V2PlanningOutcome | None = None
    remaining = budget
    for number in (1, 2):
        if _cancelled(cancellation_requested):
            raise V2AdaptiveCancellationError()
        rendered = request.rendered_prompt
        input_artifact = request_input
        if prior is not None:
            if isinstance(request_input, V2ConceptualSearchAgentInput):
                input_artifact = request_input.model_copy(
                    update={"rejected_feedback": prior.explanation or prior.rejection_code}
                )
            else:
                input_artifact = V2PlanningRepairInput(
                    **request_input.model_dump(),
                    rejected=prior,
                )
            rendered = render_stage_prompt(
                request.prompt,
                input_artifact,
                output_type,
            )
        attempt_id = uuid5(
            request.run_id, f"adaptive-reliability-{base_request_input.round_number}-{number}"
        )
        current = request.model_copy(
            update={
                "rendered_prompt": rendered,
                "input_artifact": input_artifact,
                "input_artifact_ids": (*request.input_artifact_ids, attempt_id),
            }
        )
        reserved = routing_config.preflight().reserve(
            LLMStage.SEARCH_AGENT, conservative_token_estimate(rendered)
        )
        reservation = V2SearchAgentReservation(
            input_tokens=reserved.input_tokens,
            output_tokens=reserved.output_tokens,
            reserved_tokens=reserved.reserved_tokens,
            reserved_cost_usd=reserved.reserved_cost_usd,
        )
        key = f"adaptive-reliability-round-{base_request_input.round_number}-attempt-{number}"
        try:
            started = V2PlanningAttempt.model_validate_json(
                read_v2_artifact(path, request.run_id, key).payload_json
            )
        except KeyError:
            started = None
        digest = sha256(rendered.encode()).hexdigest()
        if started is not None:
            if started.request_hash != digest:
                raise V2AdaptivePlanValidationError("Persisted planning request does not match")
            try:
                outcome = V2PlanningOutcome.model_validate_json(
                    read_v2_artifact(path, request.run_id, key + "-outcome").payload_json
                )
            except KeyError as exc:
                raise V2AdaptivePlanValidationError(
                    "Follow-up planning has an unknown outcome; its attempt remains consumed",
                    code="unknown_outcome",
                ) from exc
        else:
            _require_budget(
                budget_snapshot() if budget_snapshot else remaining,
                reserved.reserved_tokens,
                reserved.reserved_cost_usd,
            )
            started = V2PlanningAttempt(
                run_id=request.run_id,
                attempt_id=attempt_id,
                round_number=base_request_input.round_number,
                attempt_number=number,
                request_hash=digest,
                prompt_version=request.prompt.version,
                started_at=clock(),
            )
            persist_artifact(path, key, started, started.started_at)
            try:
                response = invoke_llm(llm_provider, current, clock=clock).output_artifact
                if not isinstance(
                    response,
                    (V2AdaptiveSearchModelOutput, V2AdaptiveSearchConceptsOutput),
                ):
                    raise V2AdaptivePlanValidationError("Unexpected Search Agent artifact")
                try:
                    _validate_and_assemble_plan(
                        base_request_input,
                        response,
                        request.prompt.version,
                        clock(),
                        lanes=lanes,
                        query_modes=query_modes,
                        previous_compiled_queries=previous_compiled_queries,
                        offered_expansions=getattr(request_input, "offered_expansions", ()),
                    )
                    outcome = V2PlanningOutcome(
                        run_id=request.run_id, candidate=response, completed_at=clock()
                    )
                except V2AdaptivePlanValidationError as exc:
                    outcome = V2PlanningOutcome(
                        run_id=request.run_id,
                        candidate=response,
                        rejection_code=exc.code,
                        explanation=str(exc)[:2000],
                        completed_at=clock(),
                    )
                except (TypeError, ValueError) as exc:
                    outcome = V2PlanningOutcome(
                        run_id=request.run_id,
                        candidate=response,
                        rejection_code="invalid_concept",
                        explanation=str(exc)[:2000],
                        completed_at=clock(),
                    )
            except LLMResponseValidationError:
                outcome = V2PlanningOutcome(
                    run_id=request.run_id,
                    rejection_code="schema_failure",
                    explanation="Return a valid instance of the requested output schema.",
                    completed_at=clock(),
                )
            except LLMInvocationError as exc:
                cause = exc.__cause__
                if isinstance(cause, MimoProviderError) and cause.code in {
                    MimoFailureCode.SCHEMA,
                    MimoFailureCode.MALFORMED_JSON,
                    MimoFailureCode.TRUNCATED,
                }:
                    outcome = V2PlanningOutcome(
                        run_id=request.run_id,
                        rejection_code="schema_failure",
                        explanation="Return complete valid JSON matching the requested schema.",
                        completed_at=clock(),
                    )
                else:
                    outcome = V2PlanningOutcome(
                        run_id=request.run_id,
                        rejection_code="provider_failure",
                        explanation="Provider call failed; no automatic planning repair.",
                        completed_at=clock(),
                    )
                    persist_artifact(path, key + "-outcome", outcome, outcome.completed_at)
                    raise
            persist_artifact(path, key + "-outcome", outcome, outcome.completed_at)
        if outcome.rejection_code is None and outcome.candidate is not None:
            return (
                _validate_and_assemble_plan(
                    base_request_input,
                    outcome.candidate,
                    request.prompt.version,
                    outcome.completed_at,
                    lanes=lanes,
                    query_modes=query_modes,
                    previous_compiled_queries=previous_compiled_queries,
                    offered_expansions=getattr(request_input, "offered_expansions", ()),
                ),
                reservation,
            )
        if outcome.rejection_code == "provider_failure":
            raise V2AdaptivePlanValidationError("A previous planning provider call failed")
        prior = outcome
        remaining = remaining.model_copy(
            update={
                "model_calls_remaining": max(0, remaining.model_calls_remaining - 1),
                "tokens_remaining": None
                if remaining.tokens_remaining is None
                else max(0, remaining.tokens_remaining - reserved.reserved_tokens),
                "cost_remaining_usd": None
                if remaining.cost_remaining_usd is None
                else max(Decimal("0"), remaining.cost_remaining_usd - reserved.reserved_cost_usd),
            }
        )
    raise V2AdaptivePlanValidationError(
        "Follow-up search stopped after two invalid plans. Results use sources already collected. "
        + (prior.explanation or "")
    )


def _validate_and_assemble_plan(
    request: V2SearchAgentInput,
    response: V2AdaptiveSearchModelOutput | V2AdaptiveSearchConceptsOutput,
    prompt_version: str,
    planned_at: datetime,
    *,
    lanes: tuple[V2ConceptualAdaptiveLane, ...] = (),
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
    previous_compiled_queries: tuple[V2CompiledQueryAction, ...] = (),
    offered_expansions: tuple[V2GraphNeighborAction, ...] = (),
) -> V2AdaptiveRoundPlan:
    if isinstance(response, V2NeighborhoodSearchOutput):
        offered = {action.artifact_id: action for action in offered_expansions}
        text_proposals = []
        graph_queries = {}
        for proposal in response.searches:
            if proposal.lane_index >= len(lanes):
                raise V2AdaptivePlanValidationError("Unknown application lane", code="unknown_lane")
            if proposal.graph_action_id is None:
                text_proposals.append(proposal.model_dump(exclude={"graph_action_id"}))
                continue
            action = offered.get(proposal.graph_action_id)
            lane = lanes[proposal.lane_index]
            if action is None or (action.direction, action.provider, action.target_gap_ids) != (
                lane.direction,
                lane.provider,
                lane.target_gap_ids,
            ):
                raise V2AdaptivePlanValidationError(
                    "Unknown or mismatched graph action", code="unknown_graph_action"
                )
            graph_queries[proposal.lane_index] = V2AdaptiveSearchQuery(
                run_id=request.run_id,
                query_id=action.artifact_id,
                round_number=request.round_number,
                direction=action.direction,
                provider=action.provider,
                targeted_gap_ids=action.target_gap_ids,
                strategy=lane.strategy,
                query_text=None,
                graph_action=action,
                policy_identity=request.policy_identity,
                created_at=planned_at,
            )
        text_plan = (
            _validate_and_assemble_plan(
                request,
                V2AdaptiveSearchConceptsOutput(searches=tuple(text_proposals)),
                prompt_version,
                planned_at,
                lanes=lanes,
                query_modes=query_modes,
                previous_compiled_queries=previous_compiled_queries,
            )
            if text_proposals
            else None
        )
        texts = iter(text_plan.searches if text_plan else ())
        combined = []
        for proposal in response.searches:
            if proposal.graph_action_id is not None:
                combined.append(graph_queries[proposal.lane_index])
            else:
                query = next(texts, None)
                if query is not None:
                    combined.append(query)
        cap = min(request.maximum_queries, 3 if request.round_number == 3 else 12)
        combined = combined[:cap]
        # A graph lookup needs an identity HTTP call plus a bounded neighbor/detail call.
        # Tighter physical budgets shorten the prefix; no graph quota is invented.
        available = {item.provider: item.remaining_calls for item in request.provider_budgets}
        used = Counter()
        accepted = []
        for query in combined:
            demand = (
                2
                if query.graph_action is not None or query.provider is DiscoveryProvider.PUBMED
                else 1
            )
            if used[query.provider] + demand > available.get(query.provider, 0):
                continue
            used[query.provider] += demand
            accepted.append(query)
        if not accepted:
            raise V2AdaptivePlanValidationError(
                "No action fits existing physical provider capacity"
            )
        return V2AdaptiveRoundPlan(
            run_id=request.run_id,
            round_number=request.round_number,
            directions=request.directions,
            enabled_providers=request.eligible_providers,
            targeted_gap_ids=tuple(
                dict.fromkeys(gap for query in accepted for gap in query.targeted_gap_ids)
            ),
            discovered_terms=request.discovered_terms,
            searches=tuple(accepted),
            search_agent_prompt_version=prompt_version,
            policy_identity=request.policy_identity,
            planned_at=planned_at,
        )
    previous_policies = tuple(action.policy for action in previous_compiled_queries)
    if previous_policies and any(
        policy != previous_policies[0] for policy in previous_policies[1:]
    ):
        raise V2AdaptivePlanValidationError(
            "previous compiled searches use inconsistent discovery policies",
            code="inconsistent_discovery_policy",
        )
    discovery_policy = previous_policies[0] if previous_policies else V2MetadataDiscoveryPolicy()
    compiled_candidates: list[V2CompiledQueryAction | None] = []
    if isinstance(response, V2AdaptiveSearchConceptsOutput):
        proposals: list[V2AdaptiveSearchProposal] = []
        signatures: set[tuple[object, ...]] = {
            conceptual_signature(action.conceptual_query, action.mode)
            for action in previous_compiled_queries
        }
        for proposal in response.searches:
            if proposal.lane_index >= len(lanes):
                raise V2AdaptivePlanValidationError(
                    "Search Agent selected an unknown application lane", code="unknown_lane"
                )
            lane = lanes[proposal.lane_index]
            identity = (
                f"round-{request.round_number}/lane-{proposal.lane_index}/"
                f"{lane.direction.value}/{lane.provider.value}"
            )
            concepts = proposal.concepts
            conceptual = V2ConceptualQuery(
                run_id=request.run_id,
                artifact_id=discovery_id(request.run_id, "V2ConceptualQuery", identity),
                identity_key=identity,
                required_concepts=tuple(
                    V2ConceptGroup(concept=item.concept, synonyms=item.aliases)
                    for item in concepts.required_concepts
                ),
                methods=concepts.methods,
                outcomes=concepts.outcomes,
                purpose=concepts.purpose,
                direction=lane.direction,
                provider=lane.provider,
                round_number=request.round_number,
                target_gap_ids=lane.target_gap_ids,
            )
            compiled = compile_query(
                conceptual,
                mode=lane.mode,
                requested_depth=discovery_policy.metadata_depth,
                policy=discovery_policy,
            )
            signature = conceptual_signature(conceptual, compiled.mode)
            if signature in signatures:
                raise V2AdaptivePlanValidationError(
                    "Search Agent repeated a previous material query concept/mode",
                    code="repeated_concept",
                )
            signatures.add(signature)
            proposals.append(
                V2AdaptiveSearchProposal(
                    direction=lane.direction,
                    provider=lane.provider,
                    targeted_gap_ids=lane.target_gap_ids,
                    strategy=lane.strategy,
                    query_text=compiled.query_text,
                )
            )
            compiled_candidates.append(compiled)
        response = V2AdaptiveSearchModelOutput(searches=tuple(proposals))
    else:
        compiled_candidates.extend(None for _ in response.searches)
    gap_by_id = {gap.gap_id: gap for gap in request.material_gaps}
    counts: Counter[tuple[ResearchDirection, DiscoveryProvider]] = Counter()
    direction_counts: Counter[ResearchDirection] = Counter()
    providers_by_direction: dict[ResearchDirection, set[DiscoveryProvider]] = {}
    accepted: list[V2AdaptiveSearchQuery] = []
    history = list(request.previous_queries)
    total_cap = (
        min(request.maximum_queries, 3) if request.round_number == 3 else request.maximum_queries
    )
    for zero_index, item in enumerate(response.searches):
        index = zero_index + 1
        try:
            request.directions.require_permitted(item.direction)
        except ValueError as exc:
            raise V2AdaptivePlanValidationError(str(exc), code="disabled_direction") from exc
        if item.provider not in request.eligible_providers:
            raise V2AdaptivePlanValidationError(
                "Search Agent selected a disabled or ineligible provider", code="disabled_provider"
            )
        if any(gap_id not in gap_by_id for gap_id in item.targeted_gap_ids):
            raise V2AdaptivePlanValidationError(
                "Search Agent query must target persisted Gap IDs", code="unknown_gap"
            )
        if any(
            gap_by_id[gap_id].direction is not item.direction for gap_id in item.targeted_gap_ids
        ):
            raise V2AdaptivePlanValidationError(
                "Search Agent query direction must match every targeted Gap",
                code="gap_direction_mismatch",
            )
        compiled = compiled_candidates[zero_index]
        mode_change_exception = False
        if compiled is not None:
            candidate_signature = conceptual_signature(compiled.conceptual_query, compiled.mode)
            mode_change_exception = any(
                action.mode != compiled.mode
                and conceptual_signature(action.conceptual_query, action.mode)[1:]
                == candidate_signature[1:]
                for action in previous_compiled_queries
            ) or any(
                prior is not None
                and prior.mode != compiled.mode
                and conceptual_signature(prior.conceptual_query, prior.mode)[1:]
                == candidate_signature[1:]
                for prior in compiled_candidates[:zero_index]
            )
        if not mode_change_exception and not queries_are_materially_new(
            item.query_text, tuple(history)
        ):
            match = next(
                (
                    position
                    for position, previous in enumerate(history, 1)
                    if not queries_are_materially_new(item.query_text, (previous,))
                ),
                0,
            )
            origin = (
                "previous query history"
                if match <= len(request.previous_queries)
                else "this proposal"
            )
            raise V2AdaptivePlanValidationError(
                f"Search Agent query {index} repeats or trivially rewrites query history: "
                f"matched query {match} in {origin} "
                "(equal tokens or at most one token difference).",
                code="repeated_query",
            )
        history.append(item.query_text)
        cap = (
            1
            if request.round_number == 3
            else 2
            if request.round_number == 4
            else _ROUND_TWO_PER_DIRECTION_CAPS[item.provider]
        )
        lane = (item.direction, item.provider)
        provider_lanes = providers_by_direction.setdefault(item.direction, set())
        if (
            len(accepted) >= total_cap
            or counts[lane] >= cap
            or (
                request.round_number == 4
                and item.provider not in provider_lanes
                and len(provider_lanes) >= 2
            )
            or (request.round_number == 4 and direction_counts[item.direction] >= 4)
        ):
            continue
        counts[lane] += 1
        direction_counts[item.direction] += 1
        provider_lanes.add(item.provider)
        accepted.append(
            V2AdaptiveSearchQuery(
                run_id=request.run_id,
                query_id=uuid5(
                    NAMESPACE_URL,
                    f"researchassistant-v2-adaptive-query::{request.run_id}::{request.round_number}::{index}::{normalize_query_text(item.query_text)}",
                ),
                round_number=request.round_number,
                direction=item.direction,
                provider=item.provider,
                targeted_gap_ids=item.targeted_gap_ids,
                strategy=item.strategy,
                query_text=item.query_text,
                compiled_query=compiled_candidates[zero_index],
                policy_identity=request.policy_identity,
                created_at=planned_at,
            )
        )
    if not accepted:
        raise V2AdaptivePlanValidationError("Search Agent plan contained no accepted queries")
    return V2AdaptiveRoundPlan(
        run_id=request.run_id,
        round_number=request.round_number,
        directions=request.directions,
        enabled_providers=request.eligible_providers,
        targeted_gap_ids=tuple(
            dict.fromkeys(gap_id for item in accepted for gap_id in item.targeted_gap_ids)
        ),
        discovered_terms=request.discovered_terms,
        searches=tuple(accepted),
        search_agent_prompt_version=prompt_version,
        policy_identity=request.policy_identity,
        planned_at=planned_at,
    )


def _eligible_budgets(
    plan: V2InitialPlannerOutput,
    attempted: Mapping[DiscoveryProvider, int],
    providers: Mapping[DiscoveryProvider, SearchProvider],
    *,
    path: str | None = None,
) -> tuple[V2ProviderSearchBudget, ...]:
    if path is not None and any(query.compiled_query is not None for query in plan.searches):
        return tuple(
            item
            for item in available_query_budgets(path, plan.run_id)
            if item.provider in providers
        )
    return tuple(
        V2ProviderSearchBudget(
            provider=provider,
            attempted_calls=attempted.get(provider, 0),
            maximum_calls=_PROVIDER_TOTAL_CEILINGS[provider],
        )
        for provider in plan.discovery_providers
        if provider in providers and attempted.get(provider, 0) < _PROVIDER_TOTAL_CEILINGS[provider]
    )


def _maximum_queries(
    round_number: int, plan: V2InitialPlannerOutput, budgets: tuple[V2ProviderSearchBudget, ...]
) -> int:
    compiled = any(query.compiled_query is not None for query in plan.searches)
    remaining = {
        item.provider: item.remaining_calls
        // (2 if compiled and item.provider is DiscoveryProvider.PUBMED else 1)
        for item in budgets
    }
    if round_number == 3:
        return min(3, sum(min(1, count) for count in remaining.values()))
    if round_number == 4:
        return min(
            4 * len(plan.directions.enabled_directions),
            sum(min(2, count) for count in remaining.values()),
        )
    return min(
        12,
        sum(
            min(
                _ROUND_TWO_PER_DIRECTION_CAPS[provider] * len(plan.directions.enabled_directions),
                count,
            )
            for provider, count in remaining.items()
        ),
    )


def _adaptive_concept_lanes(
    request: V2SearchAgentInput,
    query_modes: Mapping[DiscoveryProvider, SearchMode],
) -> tuple[V2ConceptualAdaptiveLane, ...]:
    """Create bounded application-owned slots before requesting adaptive concepts."""
    total_cap = min(request.maximum_queries, 3 if request.round_number == 3 else 12)
    lane_counts: Counter[tuple[ResearchDirection, DiscoveryProvider]] = Counter()
    direction_counts: Counter[ResearchDirection] = Counter()
    providers_by_direction: dict[ResearchDirection, set[DiscoveryProvider]] = {}
    physical_used: Counter[DiscoveryProvider] = Counter()
    available = {item.provider: item.remaining_calls for item in request.provider_budgets}
    gaps = {gap.gap_id: gap for gap in request.material_gaps}
    results: list[V2ConceptualAdaptiveLane] = []
    for search_direction in request.search_directions:
        gap = gaps[search_direction.gap_id]
        for provider in request.eligible_providers:
            lane = (search_direction.direction, provider)
            cap = (
                1
                if request.round_number == 3
                else 2
                if request.round_number == 4
                else _ROUND_TWO_PER_DIRECTION_CAPS[provider]
            )
            direction_providers = providers_by_direction.setdefault(
                search_direction.direction, set()
            )
            if (
                physical_used[provider] + (2 if provider is DiscoveryProvider.PUBMED else 1)
                > available[provider]
                or len(results) >= total_cap
                or lane_counts[lane] >= cap
                or (
                    request.round_number == 4
                    and provider not in direction_providers
                    and len(direction_providers) >= 2
                )
                or (request.round_number == 4 and direction_counts[search_direction.direction] >= 4)
            ):
                continue
            results.append(
                V2ConceptualAdaptiveLane(
                    direction=search_direction.direction,
                    provider=provider,
                    strategy=_bounded_lane_strategy(
                        search_direction.search_focus or gap.missing_evidence
                    ),
                    target_gap_ids=(gap.gap_id,),
                    mode=query_modes.get(provider),
                )
            )
            physical_used[provider] += 2 if provider is DiscoveryProvider.PUBMED else 1
            lane_counts[lane] += 1
            direction_counts[search_direction.direction] += 1
            direction_providers.add(provider)
        if len(results) >= total_cap:
            break
    return tuple(results)


def _bounded_lane_strategy(value: str) -> str:
    """Keep verbose gap advice within the lane prompt bound without losing the full gap input."""
    normalized = " ".join(value.split())
    if len(normalized) <= 240:
        return normalized
    prefix = normalized[:240]
    return prefix.rpartition(" ")[0] or prefix


def _require_budget(budget: V2AdaptiveBudgetState, tokens: int, cost: Decimal) -> None:
    if budget.model_calls_remaining <= budget.protected_downstream_model_calls:
        raise V2AdaptiveBudgetError("Insufficient protected model-call budget for adaptive search.")
    if (
        budget.tokens_remaining is not None
        and tokens + budget.protected_downstream_tokens > budget.tokens_remaining
    ):
        raise V2AdaptiveBudgetError(
            "Insufficient token budget for adaptive Search Agent reservation."
        )
    if (
        budget.cost_remaining_usd is not None
        and add_usd(budget.protected_downstream_cost_usd, cost) > budget.cost_remaining_usd
    ):
        raise V2AdaptiveBudgetError(
            "Insufficient cost budget for adaptive Search Agent reservation."
        )
