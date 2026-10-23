"""Fresh-v2 startup planning: one broad, policy-constrained Round-1 plan only."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import ConfigDict

from researchassistant.agents.v2_coverage import claim_component_focus
from researchassistant.agents.v2_stage_checkpoint import (
    V2PlannerInputCheckpoint,
    V2StageOutcomeCheckpoint,
    checkpoint_hash,
    read_checkpoint,
    save_stage_outcome,
    stage_attempt,
)
from researchassistant.common.research_guidance import SAVED_LEADS_GUIDANCE
from researchassistant.common.resources import prompt_resource
from researchassistant.contracts.discovery_v2 import (
    SearchMode,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2MetadataDiscoveryPolicy,
    discovery_id,
)
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ProviderRunContract,
    ResearchDirections,
    RunManifest,
    RunStatus,
    Stage,
    StrictModel,
    V2InitialPlannerConceptsOutput,
    V2InitialPlannerInput,
    V2InitialPlannerModelOutput,
    V2InitialPlannerOutput,
    V2InitialPlannerPolicy,
    V2PipelineIdentity,
    V2RoundOneSearchQuery,
)
from researchassistant.contracts.query_compiler import compile_query
from researchassistant.contracts.source_recovery import V2SavedSourceSuggestions
from researchassistant.providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationError,
    LLMInvocationRecord,
    LLMProvider,
    LLMProviderExecutionError,
    LLMRequest,
    LLMStage,
    invoke_llm,
    load_prompt_file,
    render_stage_prompt,
)
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.research.query_execution import freeze_query_execution
from researchassistant.storage.saved_source_suggestions import saved_source_suggestions
from researchassistant.storage.store import (
    init_db,
    insert_provider_run_contract,
    insert_run,
    insert_v2_artifact,
    insert_v2_initial_planner_output,
    insert_v2_pipeline_identity,
    read_provider_run_contract,
    read_run,
    read_v2_artifact,
    read_v2_initial_planner_output,
)

V2_INITIAL_PLANNER_PROMPT_PATH = prompt_resource("v2_initial_planner.md")
_INITIAL_PLAN_KEY = "phase-3-initial-round-1-plan"
_PLANNER_CHECKPOINT_KEY = "initial-planner-checkpoint-v1"


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
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
    discovery_policy: V2MetadataDiscoveryPolicy | None = None,
    provider_configuration_fingerprint: str = "injected-provider-policy-v1",
    legacy_prompt: bool = False,
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
    artifact_plan = read_checkpoint(
        path, resolved_run_id, _INITIAL_PLAN_KEY, V2InitialPlannerOutput
    )
    if stored is not None and artifact_plan is not None and stored != artifact_plan:
        raise ValueError("saved initial plan projections disagree")
    relational_missing = stored is None
    if stored is None:
        stored = artifact_plan
    if stored is not None:
        if (
            stored.raw_claim != raw_claim
            or stored.directions != directions
            or stored.discovery_providers != discovery_providers
        ):
            raise V2InitialPlannerFingerprintMismatchError(
                "existing v2 Round-1 plan does not match the requested startup controls"
            )
        stored_is_legacy = all(query.compiled_query is None for query in stored.searches)
        if stored_is_legacy != legacy_prompt:
            raise V2InitialPlannerFingerprintMismatchError(
                "existing query planning contract differs; use a new run ID"
            )
        if not legacy_prompt:
            freeze_query_execution(
                path,
                resolved_run_id,
                raw_claim,
                directions,
                discovery_providers,
                now,
                query_modes=query_modes,
                discovery_policy=discovery_policy,
                provider_configuration_fingerprint=provider_configuration_fingerprint,
            )
        if relational_missing:
            insert_v2_initial_planner_output(path, stored)
        if artifact_plan is None:
            insert_v2_artifact(path, _INITIAL_PLAN_KEY, stored, stored.planned_at)
        return V2InitialPlannerRunResult(
            planner_output=stored,
            provider_contract=persisted_contract,
            resumed=True,
        )

    if not legacy_prompt:
        freeze_query_execution(
            path,
            resolved_run_id,
            raw_claim,
            directions,
            discovery_providers,
            now,
            query_modes=query_modes,
            discovery_policy=discovery_policy,
            provider_configuration_fingerprint=provider_configuration_fingerprint,
        )

    policy = V2InitialPlannerPolicy()
    suggestions = ()
    if not legacy_prompt:
        try:
            saved = read_v2_artifact(path, resolved_run_id, "saved-source-suggestions-v1")
        except KeyError:
            frozen = V2SavedSourceSuggestions(
                run_id=resolved_run_id,
                exact_claim=raw_claim,
                leads=saved_source_suggestions(path, resolved_run_id, raw_claim),
            )
            insert_v2_artifact(path, "saved-source-suggestions-v1", frozen, planned_at)
        else:
            frozen = V2SavedSourceSuggestions.model_validate_json(saved.payload_json)
            if frozen.run_id != resolved_run_id or frozen.exact_claim != raw_claim:
                raise ValueError("saved source suggestions changed run or claim")
        suggestions = frozen.leads
    if not legacy_prompt and DiscoveryProvider.SERPER in discovery_providers:
        raise ValueError("Serper has no provider-native conceptual query compiler")
    planner_input = V2InitialPlannerInput(
        run_id=resolved_run_id,
        raw_claim=raw_claim,
        directions=directions,
        discovery_providers=discovery_providers,
        search_lanes=policy.search_lanes(directions, discovery_providers),
        saved_source_leads=suggestions,
    )
    prompt_path = (
        V2_INITIAL_PLANNER_PROMPT_PATH
        if legacy_prompt
        else prompt_resource("v2_initial_planner_v2.md")
    )
    prompt = load_prompt_file(prompt_path, expected_stage=LLMStage.PLANNER)
    output_type = V2InitialPlannerModelOutput if legacy_prompt else V2InitialPlannerConceptsOutput
    request = LLMRequest(
        run_id=resolved_run_id,
        stage=LLMStage.PLANNER,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, planner_input, output_type)
        + ("\n" + SAVED_LEADS_GUIDANCE if suggestions else ""),
        input_artifact=planner_input,
        input_artifact_ids=(resolved_run_id,),
        requested_output_type=output_type,
        model_alias=routing_config.preflight().for_stage(LLMStage.PLANNER).logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.PLANNER).generation,
    )
    input_hash = checkpoint_hash(
        {
            "input": planner_input.model_dump(mode="json"),
            "routing": routing_config.preflight().model_dump(mode="json"),
            "query_modes": {provider.value: mode for provider, mode in (query_modes or {}).items()},
            "discovery_policy": discovery_policy.model_dump(mode="json")
            if discovery_policy is not None
            else None,
            "provider_configuration": provider_configuration_fingerprint,
            "legacy_prompt": legacy_prompt,
        }
    )
    checkpoint = read_checkpoint(
        path, resolved_run_id, _PLANNER_CHECKPOINT_KEY, V2PlannerInputCheckpoint
    )
    checkpoint_replayed = checkpoint is not None
    if checkpoint is None:
        checkpoint = V2PlannerInputCheckpoint(
            run_id=resolved_run_id, input_hash=input_hash, planned_at=planned_at
        )
        insert_v2_artifact(path, _PLANNER_CHECKPOINT_KEY, checkpoint, planned_at)
    elif checkpoint.input_hash != input_hash:
        raise V2InitialPlannerFingerprintMismatchError("persisted initial Planner input changed")
    planned_at = checkpoint.planned_at
    attempt, outcome, new_attempt = stage_attempt(
        path=path,
        key=_PLANNER_CHECKPOINT_KEY,
        number=1,
        request=request,
        started_at=_aware_now(now),
    )
    if new_attempt:
        try:
            invocation = invoke_llm(
                llm_provider,
                request.model_copy(
                    update={"input_artifact_ids": (*request.input_artifact_ids, attempt.attempt_id)}
                ),
                clock=now,
            )
            response = invocation.output_artifact
            if not isinstance(response, output_type):
                raise TypeError("v2 initial Planner returned an unexpected typed artifact")
        except Exception as exc:
            outcome = V2StageOutcomeCheckpoint(
                run_id=resolved_run_id,
                attempt_id=attempt.attempt_id,
                request_hash=attempt.request_hash,
                invocation=exc.record if isinstance(exc, LLMInvocationError) else None,
                failure=f"{type(exc).__name__}: {exc}"[:1000],
                completed_at=_aware_now(now),
            )
            save_stage_outcome(path, attempt, outcome)
            raise
        outcome = V2StageOutcomeCheckpoint(
            run_id=resolved_run_id,
            attempt_id=attempt.attempt_id,
            request_hash=attempt.request_hash,
            candidate=response,
            invocation=invocation.record,
            completed_at=_aware_now(now),
        )
        save_stage_outcome(path, attempt, outcome)
    assert outcome is not None
    if outcome.failure is not None:
        if outcome.invocation is not None:
            raise LLMProviderExecutionError(outcome.failure, outcome.invocation)
        raise RuntimeError(outcome.failure)
    response = outcome.candidate
    if not isinstance(response, output_type):
        raise ValueError("saved initial Planner outcome has the wrong output type")
    output = _assemble_initial_plan(
        planner_input=planner_input,
        response=response,
        prompt_version=prompt.version,
        planned_at=planned_at,
        query_modes=query_modes or {},
        discovery_policy=discovery_policy,
    )
    insert_v2_initial_planner_output(path, output)
    insert_v2_artifact(path, _INITIAL_PLAN_KEY, output, output.planned_at)
    return V2InitialPlannerRunResult(
        planner_output=output,
        provider_contract=persisted_contract,
        invocation=outcome.invocation,
        resumed=checkpoint_replayed,
    )


def _assemble_initial_plan(
    *,
    planner_input: V2InitialPlannerInput,
    response: V2InitialPlannerModelOutput | V2InitialPlannerConceptsOutput,
    prompt_version: str,
    planned_at: datetime,
    query_modes: Mapping[DiscoveryProvider, SearchMode],
    discovery_policy: V2MetadataDiscoveryPolicy | None = None,
) -> V2InitialPlannerOutput:
    searches: list[V2RoundOneSearchQuery] = []
    lanes = (
        planner_input.search_lanes
        if isinstance(response, V2InitialPlannerConceptsOutput)
        else response.searches
    )
    for index, lane in enumerate(lanes):
        query_id = uuid5(
            NAMESPACE_URL,
            (
                "researchassistant-v2-initial-planner::"
                f"{planner_input.run_id}::{lane.direction.value}::{lane.provider.value}::"
                f"{lane.strategy}"
            ),
        )
        if isinstance(response, V2InitialPlannerConceptsOutput):
            if len(response.queries) != len(planner_input.search_lanes):
                raise ValueError("conceptual Planner must return one item for each supplied lane")
            concepts = response.queries[index]
            identity = f"round-1/{lane.direction.value}/{lane.provider.value}/{lane.strategy}"
            conceptual = V2ConceptualQuery(
                run_id=planner_input.run_id,
                artifact_id=discovery_id(planner_input.run_id, "V2ConceptualQuery", identity),
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
                round_number=1,
            )
            compiled = compile_query(
                conceptual,
                mode=query_modes.get(lane.provider),
                requested_depth=(discovery_policy or V2MetadataDiscoveryPolicy()).metadata_depth,
                policy=discovery_policy or V2MetadataDiscoveryPolicy(),
            )
            query_text = compiled.query_text
        else:
            item = response.searches[index]
            compiled = None
            query_text = item.query_text
        searches.append(
            V2RoundOneSearchQuery(
                run_id=planner_input.run_id,
                query_id=query_id,
                direction=lane.direction,
                provider=lane.provider,
                strategy=lane.strategy,
                query_text=query_text,
                compiled_query=compiled,
                created_at=planned_at,
            )
        )
    return V2InitialPlannerOutput(
        run_id=planner_input.run_id,
        raw_claim=planner_input.raw_claim,
        directions=planner_input.directions,
        discovery_providers=planner_input.discovery_providers,
        scope_interpretations=response.scope_interpretations,
        claim_coverage_focus=claim_component_focus(
            planner_input.raw_claim,
            response.claim_coverage_focus,
            require_exact_components=isinstance(response, V2InitialPlannerConceptsOutput),
        ),
        searches=tuple(searches),
        planner_prompt_version=prompt_version,
        planned_at=planned_at,
    )


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 initial planner clock must return a timezone-aware datetime")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
