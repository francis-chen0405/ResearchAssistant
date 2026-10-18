"""Authorized Round-4 Search Agent requests and bounded accepted plans."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY as V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_PLAN_KEY as V2_POST13_ROUND_FOUR_PLAN_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2RoundFourAuthorizationError as V2RoundFourAuthorizationError,
)
from researchassistant.agents.round_four_handoffs import (
    _read as _read,
)
from researchassistant.agents.round_four_handoffs import (
    _utc_now as _utc_now,
)
from researchassistant.agents.v2_adaptive_search import (
    V2AdaptivePlannedRound,
    V2AdaptivePlanValidationError,
    V2SearchAgentReservation,
    _adaptive_concept_lanes,
    _maximum_queries,
    _validate_and_assemble_plan,
)
from researchassistant.common.resources import prompt_resource
from researchassistant.contracts.discovery_v2 import SearchMode, V2CompiledQueryAction
from researchassistant.contracts.models import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    DiscoveryProvider,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchModelOutput,
    V2GapAnalysisOutput,
    V2InitialPlannerOutput,
    V2ProviderSearchBudget,
    V2RoundFourGovernorDecision,
    V2SearchAgentInput,
)
from researchassistant.contracts.query_planning import (
    V2AdaptiveSearchConceptsOutput,
    V2ConceptualAdaptiveLane,
    V2ConceptualSearchAgentInput,
)
from researchassistant.providers.llm import (
    V2_LLM_ROUTING,
    LLMProvider,
    LLMRequest,
    LLMStage,
    invoke_llm,
    load_prompt,
    render_stage_prompt,
)
from researchassistant.providers.pricing import conservative_token_estimate
from researchassistant.providers.v2_routing import V2ModelReservation, V2RoutingConfig
from researchassistant.storage.store import insert_v2_artifact


def _build_round_four_search_agent_request(
    *,
    path: str,
    initial_plan: V2InitialPlannerOutput,
    gap: V2GapAnalysisOutput,
    eligible: tuple[V2ProviderSearchBudget, ...],
    routing_config: V2RoutingConfig,
) -> (
    tuple[
        V2SearchAgentInput | V2ConceptualSearchAgentInput,
        LLMRequest,
        V2ModelReservation,
        tuple[V2ConceptualAdaptiveLane, ...],
        tuple[V2CompiledQueryAction, ...],
        bool,
        Mapping[DiscoveryProvider, SearchMode],
    ]
    | None
):
    if gap.result is None:
        raise ValueError("Round-4 Search Agent requires a usable Gap Analysis result")
    maximum_queries = _maximum_queries(4, initial_plan, eligible)
    if maximum_queries == 0:
        return None
    previous = tuple(query.query_text for query in initial_plan.searches)
    for round_number in (2, 3):
        payload = _read(path, initial_plan.run_id, f"phase-7-round-{round_number}-plan")
        if payload is not None:
            previous += tuple(
                query.query_text
                for query in V2AdaptivePlannedRound.model_validate_json(payload).plan.searches
                if query.query_text is not None
            )
    request_input = V2SearchAgentInput(
        run_id=initial_plan.run_id,
        exact_claim=initial_plan.raw_claim,
        round_number=4,
        directions=initial_plan.directions,
        eligible_providers=tuple(item.provider for item in eligible),
        material_gaps=gap.result.material_gaps,
        search_directions=gap.result.new_search_directions,
        discovered_terms=tuple(
            dict.fromkeys((*gap.input.discovered_terms, *gap.result.discovered_terms))
        )[:40],
        previous_queries=previous,
        provider_budgets=eligible,
        maximum_queries=maximum_queries,
        policy_identity=V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
    )
    prior_actions = tuple(
        query.compiled_query for query in initial_plan.searches if query.compiled_query is not None
    )
    for round_number in (2, 3):
        payload = _read(path, initial_plan.run_id, f"phase-7-round-{round_number}-plan")
        if payload is not None:
            prior_actions += tuple(
                query.compiled_query
                for query in V2AdaptivePlannedRound.model_validate_json(payload).plan.searches
                if query.compiled_query is not None
            )
    modes = {action.conceptual_query.provider: action.mode for action in prior_actions}
    legacy_prompt = not any(query.compiled_query is not None for query in initial_plan.searches)
    if legacy_prompt:
        planner_input: V2SearchAgentInput | V2ConceptualSearchAgentInput = request_input
        lanes: tuple[V2ConceptualAdaptiveLane, ...] = ()
        output_type = V2AdaptiveSearchModelOutput
        prompt = load_prompt(LLMStage.SEARCH_AGENT)
    else:
        if DiscoveryProvider.SERPER in request_input.eligible_providers:
            raise V2AdaptivePlanValidationError(
                "Serper has no provider-native conceptual query compiler"
            )
        lanes = _adaptive_concept_lanes(request_input, modes)
        if not lanes:
            return None
        from researchassistant.contracts.query_planning import (
            V2NeighborhoodSearchAgentInput,
            V2NeighborhoodSearchOutput,
        )
        from researchassistant.research.seed_expansion import offer_expansions
        from researchassistant.storage.discovery_store import read_discovery_binding

        try:
            fresh_expansion = read_discovery_binding(path, initial_plan.run_id).seed_identity in {
                "source-seed-expansion-v2",
                "source-seed-expansion-v3",
            }
        except KeyError:
            fresh_expansion = False
        offers = (
            offer_expansions(path, initial_plan.run_id, 4, lanes, _utc_now)
            if fresh_expansion
            else ()
        )
        fresh_expansion = bool(offers)
        planner_input = (
            V2NeighborhoodSearchAgentInput(
                request=request_input, lanes=lanes, offered_expansions=offers
            )
            if fresh_expansion
            else V2ConceptualSearchAgentInput(request=request_input, lanes=lanes)
        )
        output_type = (
            V2NeighborhoodSearchOutput if fresh_expansion else V2AdaptiveSearchConceptsOutput
        )
        from researchassistant.providers.llm import load_prompt_file

        prompt = load_prompt_file(
            prompt_resource("search_agent_v3.md" if fresh_expansion else "search_agent_v2.md"),
            expected_stage=LLMStage.SEARCH_AGENT,
        )
    route = routing_config.preflight().for_stage(LLMStage.SEARCH_AGENT)
    request = LLMRequest(
        run_id=initial_plan.run_id,
        stage=LLMStage.SEARCH_AGENT,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, planner_input, output_type),
        input_artifact=planner_input,
        input_artifact_ids=(initial_plan.run_id,),
        requested_output_type=output_type,
        model_alias=route.logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.SEARCH_AGENT).generation,
    )
    search_reservation = routing_config.preflight().reserve(
        LLMStage.SEARCH_AGENT, conservative_token_estimate(request.rendered_prompt)
    )
    return planner_input, request, search_reservation, lanes, prior_actions, legacy_prompt, modes


RoundFourRequestBuilder = Callable[
    ...,
    tuple[
        V2SearchAgentInput | V2ConceptualSearchAgentInput,
        LLMRequest,
        V2ModelReservation,
        tuple[V2ConceptualAdaptiveLane, ...],
        tuple[V2CompiledQueryAction, ...],
        bool,
        Mapping[DiscoveryProvider, SearchMode],
    ]
    | None,
]


def _plan_round_four(
    *,
    path: str,
    initial_plan: V2InitialPlannerOutput,
    gap: V2GapAnalysisOutput,
    eligible: tuple[V2ProviderSearchBudget, ...],
    attempts: Mapping[DiscoveryProvider, int],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
    assemble_plan: Callable[..., V2AdaptiveRoundPlan] = _validate_and_assemble_plan,
    request_builder: RoundFourRequestBuilder = _build_round_four_search_agent_request,
) -> V2AdaptivePlannedRound | None:
    del attempts
    persisted_decision = _read(path, initial_plan.run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY)
    if persisted_decision is None:
        raise V2RoundFourAuthorizationError(
            "Round-4 Search Agent cannot execute without a persisted Governor authorization"
        )
    decision = V2RoundFourGovernorDecision.model_validate_json(persisted_decision)
    if decision.run_id != initial_plan.run_id or not decision.authorized:
        raise V2RoundFourAuthorizationError(
            "Round-4 Search Agent cannot execute without an authorized Governor decision"
        )
    stored = _read(path, initial_plan.run_id, V2_POST13_ROUND_FOUR_PLAN_KEY)
    if stored is not None:
        return V2AdaptivePlannedRound.model_validate_json(stored)
    built = request_builder(
        path=path,
        initial_plan=initial_plan,
        gap=gap,
        eligible=eligible,
        routing_config=routing_config,
    )
    if built is None:
        return None
    (
        request_input,
        request,
        search_reservation,
        lanes,
        prior_actions,
        legacy_prompt,
        modes,
    ) = built
    base_request_input = (
        request_input.request
        if isinstance(request_input, V2ConceptualSearchAgentInput)
        else request_input
    )
    if base_request_input.maximum_queries == 0:
        return None
    response = invoke_llm(llm_provider, request, clock=clock).output_artifact
    if not isinstance(response, (V2AdaptiveSearchModelOutput, V2AdaptiveSearchConceptsOutput)):
        raise V2AdaptivePlanValidationError("Search Agent returned an unexpected typed artifact")
    if isinstance(response, V2AdaptiveSearchConceptsOutput):
        assembled = assemble_plan(
            base_request_input,
            response,
            request.prompt.version,
            clock(),
            lanes=lanes,
            query_modes=modes,
            previous_compiled_queries=prior_actions,
            offered_expansions=getattr(request_input, "offered_expansions", ()),
        )
    else:
        assembled = assemble_plan(base_request_input, response, request.prompt.version, clock())
    if not assembled.searches:
        raise V2AdaptivePlanValidationError("Search Agent plan contained no accepted queries")
    plan = assembled.model_copy(
        update={
            "policy_identity": V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
            "searches": tuple(
                query.model_copy(update={"policy_identity": V2_POST13_ROUND_FOUR_POLICY_IDENTITY})
                for query in assembled.searches
            ),
        }
    )
    result = V2AdaptivePlannedRound(
        run_id=initial_plan.run_id,
        plan=plan,
        reservation=V2SearchAgentReservation(
            input_tokens=search_reservation.input_tokens,
            output_tokens=search_reservation.output_tokens,
            reserved_tokens=search_reservation.reserved_tokens,
            reserved_cost_usd=search_reservation.reserved_cost_usd,
        ),
    )
    insert_v2_artifact(path, V2_POST13_ROUND_FOUR_PLAN_KEY, result, plan.planned_at)
    return result
