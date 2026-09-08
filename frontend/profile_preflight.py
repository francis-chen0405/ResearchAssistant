"""Offline first-call reservation check before a desktop worker is created."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from agents.v2_initial_planner import V2_INITIAL_PLANNER_PROMPT_PATH
from frontend.live_contracts import LiveRunRequest
from models import V2InitialPlannerInput, V2InitialPlannerModelOutput, V2InitialPlannerPolicy
from providers.llm import LLMStage, load_prompt_file, render_stage_prompt
from providers.model_profiles import profile_environment
from providers.pricing import conservative_token_estimate
from providers.v2_routing import V2ModelReservation, V2RoutingConfig


def check_start_reservation(
    request: LiveRunRequest, environment: Mapping[str, str]
) -> V2ModelReservation:
    routing = V2RoutingConfig.from_environment(
        profile_environment(environment, request.model_profile), repository_revision="preflight"
    )
    providers = request.research_controls.discovery_providers
    artifact = V2InitialPlannerInput(
        run_id=request.run_id or UUID(int=0),
        raw_claim=request.raw_claim,
        directions=request.directions,
        discovery_providers=providers,
        search_lanes=V2InitialPlannerPolicy().search_lanes(request.directions, providers),
    )
    prompt = load_prompt_file(V2_INITIAL_PLANNER_PROMPT_PATH, expected_stage=LLMStage.PLANNER)
    rendered = render_stage_prompt(prompt, artifact, V2InitialPlannerModelOutput)
    reservation = routing.preflight().reserve(
        LLMStage.PLANNER, conservative_token_estimate(rendered)
    )
    if reservation.reserved_tokens > request.max_tokens:
        raise ValueError(
            "The token limit cannot reserve the initial planning call. Increase it in Settings."
        )
    if reservation.reserved_cost_usd > request.max_cost_usd:
        raise ValueError(
            "The model budget cannot reserve the initial planning call. "
            "Increase the budget or shorten the question."
        )
    return reservation
