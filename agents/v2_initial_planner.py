"""Fresh-v2 startup planning: one broad, policy-constrained Round-1 plan only."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import ConfigDict

from models import (
    DiscoveryProvider,
    ProviderRunContract,
    ResearchDirections,
    RunManifest,
    RunStatus,
    Stage,
    StrictModel,
    V2InitialPlannerInput,
    V2InitialPlannerModelOutput,
    V2InitialPlannerOutput,
    V2InitialPlannerPolicy,
    V2PipelineIdentity,
    V2RoundOneSearchQuery,
)
from providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationRecord,
    LLMProvider,
    LLMRequest,
    LLMStage,
    invoke_llm,
    load_prompt_file,
    render_stage_prompt,
)
from providers.v2_routing import V2RoutingConfig
from store import (
    init_db,
    insert_provider_run_contract,
    insert_run,
    insert_v2_artifact,
    insert_v2_initial_planner_output,
    insert_v2_pipeline_identity,
    read_provider_run_contract,
    read_run,
    read_v2_initial_planner_output,
)

V2_INITIAL_PLANNER_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "v2_initial_planner.md"
)


class V2InitialPlannerFingerprintMismatchError(RuntimeError):
    """Raised when an existing fresh-v2 run has a different immutable contract."""


class V2InitialPlannerRunResult(StrictModel):
    """Typed result of v2 startup planning; no search execution is started here."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    planner_output: V2InitialPlannerOutput
    provider_contract: ProviderRunContract
    invocation: LLMInvocationRecord | None = None
    resumed: bool


def run_v2_initial_planner(
    raw_claim: str,
    *,
    db_path: str | Path,
    directions: ResearchDirections,
    discovery_providers: tuple[DiscoveryProvider, ...],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    run_id: UUID | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2InitialPlannerRunResult:
    """Create or reconstruct the one allowed broad Round-1 plan for a fresh v2 run."""
    if not raw_claim:
        raise ValueError("raw_claim must be non-empty")
    now = clock or _utc_now
    planned_at = _aware_now(now)
    resolved_run_id = run_id or uuid4()
    path = str(Path(db_path).resolve())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    init_db(path)
    contract = routing_config.contract(resolved_run_id, planned_at)
    _require_mimo_pro_planner_route(routing_config)

    try:
        existing_manifest = read_run(path, resolved_run_id)
    except KeyError:
        insert_run(
            path,
            RunManifest(
                run_id=resolved_run_id,
                status=RunStatus.PLANNED,
                raw_claim=raw_claim,
                current_stage=Stage.CLAIM_PLANNER,
                created_at=planned_at,
                updated_at=planned_at,
            ),
        )
    else:
        if existing_manifest.raw_claim != raw_claim:
            raise ValueError("raw_claim must match the existing v2 run exactly")

    try:
        existing_contract = read_provider_run_contract(path, resolved_run_id)
    except KeyError:
        existing_contract = None
    if existing_contract is not None and (
        existing_contract.fingerprint_sha256 != contract.fingerprint_sha256
        or existing_contract.payload_json != contract.payload_json
    ):
        raise V2InitialPlannerFingerprintMismatchError(
            "incompatible fingerprint for existing v2 run; use a new run ID"
        )
    persisted_contract = existing_contract or contract

    insert_v2_pipeline_identity(path, resolved_run_id, V2PipelineIdentity(), planned_at)
    if existing_contract is None:
        insert_provider_run_contract(path, contract)
    try:
        stored = read_v2_initial_planner_output(path, resolved_run_id)
    except KeyError:
        stored = None
    if stored is not None:
        if (
            stored.raw_claim != raw_claim
            or stored.directions != directions
            or stored.discovery_providers != discovery_providers
        ):
            raise V2InitialPlannerFingerprintMismatchError(
                "existing v2 Round-1 plan does not match the requested startup controls"
            )
        return V2InitialPlannerRunResult(
            planner_output=stored,
            provider_contract=persisted_contract,
            resumed=True,
        )

    policy = V2InitialPlannerPolicy()
    planner_input = V2InitialPlannerInput(
        run_id=resolved_run_id,
        raw_claim=raw_claim,
        directions=directions,
        discovery_providers=discovery_providers,
        search_lanes=policy.search_lanes(directions, discovery_providers),
    )
    prompt = load_prompt_file(V2_INITIAL_PLANNER_PROMPT_PATH, expected_stage=LLMStage.PLANNER)
    request = LLMRequest(
        run_id=resolved_run_id,
        stage=LLMStage.PLANNER,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, planner_input, V2InitialPlannerModelOutput),
        input_artifact=planner_input,
        input_artifact_ids=(resolved_run_id,),
        requested_output_type=V2InitialPlannerModelOutput,
        model_alias=V2_LLM_ROUTING.for_stage(LLMStage.PLANNER).primary,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.PLANNER).generation,
    )
    invocation = invoke_llm(llm_provider, request, clock=now)
    response = invocation.output_artifact
    if not isinstance(response, V2InitialPlannerModelOutput):
        raise TypeError("v2 initial Planner returned an unexpected typed artifact")
    output = _assemble_initial_plan(
        planner_input=planner_input,
        response=response,
        prompt_version=prompt.version,
        planned_at=planned_at,
    )
    insert_v2_initial_planner_output(path, output)
    insert_v2_artifact(path, "phase-3-initial-round-1-plan", output, output.planned_at)
    return V2InitialPlannerRunResult(
        planner_output=output,
        provider_contract=contract,
        invocation=invocation.record,
        resumed=False,
    )


def _assemble_initial_plan(
    *,
    planner_input: V2InitialPlannerInput,
    response: V2InitialPlannerModelOutput,
    prompt_version: str,
    planned_at: datetime,
) -> V2InitialPlannerOutput:
    searches = tuple(
        V2RoundOneSearchQuery(
            run_id=planner_input.run_id,
            query_id=uuid5(
                NAMESPACE_URL,
                (
                    "researchassistant-v2-initial-planner::"
                    f"{planner_input.run_id}::{item.direction.value}::{item.provider.value}::"
                    f"{item.strategy}"
                ),
            ),
            direction=item.direction,
            provider=item.provider,
            strategy=item.strategy,
            query_text=item.query_text,
            created_at=planned_at,
        )
        for item in response.searches
    )
    return V2InitialPlannerOutput(
        run_id=planner_input.run_id,
        raw_claim=planner_input.raw_claim,
        directions=planner_input.directions,
        discovery_providers=planner_input.discovery_providers,
        scope_interpretations=response.scope_interpretations,
        claim_coverage_focus=response.claim_coverage_focus,
        searches=searches,
        planner_prompt_version=prompt_version,
        planned_at=planned_at,
    )


def _require_mimo_pro_planner_route(routing_config: V2RoutingConfig) -> None:
    route = routing_config.preflight().for_stage(LLMStage.PLANNER)
    if route.logical_alias.value != "mimo-v2.5-pro" or route.physical_model != "mimo-v2.5-pro":
        raise ValueError("the v2 Initial Planner requires MiMo-v2.5-Pro")


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 initial planner clock must return a timezone-aware datetime")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
