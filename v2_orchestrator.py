"""Production coordinator for the complete restart-safe ResearchAssistant v2 pipeline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, field_validator, model_validator

from agents.researcher import EVIDENCE_POLICY_VERSION
from agents.reviewer import ReviewerDecision
from agents.v2_acquisition import run_v2_acquisition_probe
from agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveContinuationResult,
    V2AdaptiveStopCode,
    run_v2_adaptive_search_continuation,
)
from agents.v2_deep_analysis import run_v2_deep_analysis_with_backfill
from agents.v2_discovery import V2DiscoveryResponse, run_v2_discovery_and_scout
from agents.v2_extraction import V2_EXTRACTION_POLICY_IDENTITY
from agents.v2_final_output import (
    V2_FINAL_OUTPUT_POLICY_IDENTITY,
    V2_FINAL_VALIDATOR_CONFIG_VERSION,
    run_v2_final_research_output,
)
from agents.v2_gap_analysis import build_v2_gap_analysis_input, run_v2_gap_analysis
from agents.v2_initial_planner import run_v2_initial_planner
from agents.v2_reviewer_ledger import V2_REVIEWER_LEDGER_POLICY_VERSION
from agents.v2_source_selection import (
    build_v2_source_selection_input,
    run_v2_source_selection_and_queue,
)
from models import (
    V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    Stage,
    StrictModel,
    SynthesisOutput,
    V2AcquisitionProbeOutput,
    V2AdaptiveSearchModelOutput,
    V2CanonicalStatementModelOutput,
    V2DeepAnalysisBackfillResult,
    V2DeepAnalysisBudget,
    V2DiscoveryScoutOutput,
    V2EvidenceAnalystModelOutput,
    V2FinalResearchOutput,
    V2GapAnalysisModelOutput,
    V2GapAnalysisOutput,
    V2GapBudgetState,
    V2InitialPlannerModelOutput,
    V2PipelineIdentity,
    V2RoundOneSearchQuery,
    V2SourceSelectionModelOutput,
    V2SourceSelectionQueueResult,
    V2VerbatimQuoteSelection,
)
from providers.llm import LLMProvider
from providers.scraper import ScraperProvider
from providers.search import (
    SearchFailureCode,
    SearchIntent,
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResult,
)
from providers.v2_budget import (
    BudgetedV2LLMProvider,
    V2BudgetExceededError,
    V2BudgetSnapshot,
    V2RunCeilings,
)
from providers.v2_routing import V2RoutingConfig
from research_governor import DEFAULT_RESEARCH_GOVERNOR_POLICY
from store import (
    init_db,
    insert_provider_run_contract,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_provider_run_contract,
    read_run,
    read_v2_artifact,
    update_run,
)

V2_PRODUCTION_ARTIFACT_KEY = "phase-12-production-result"
V2_PRODUCTION_FINGERPRINT_KEY = "phase-12-production-fingerprint"
V2_ROUND_ONE_SEARCH_KEY = "phase-12-round-1-search"
V2_PRODUCTION_POLICY_IDENTITY = "researchassistant-v2-phase-12-production-cutover-v2"
V2_MANDATORY_DOWNSTREAM_CALL_RESERVE = 14
V2_ROUND_THREE_COMPLETE_WORKLOAD_CALL_RESERVE = 8


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 production timestamps must be timezone-aware")
    return value


class V2ProductionState(StrEnum):
    RELEASED = "released"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class V2RoundOneSearchOutcome(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: V2RoundOneSearchQuery
    succeeded: bool
    results: tuple[SearchResult, ...] = ()
    failure_code: str | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> V2RoundOneSearchOutcome:
        if self.succeeded:
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("successful search cannot carry a failure")
        elif self.results or self.failure_code is None or self.failure_message is None:
            raise ValueError("failed search requires paired failure fields and no results")
        return self


class V2RoundOneSearchResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    outcomes: tuple[V2RoundOneSearchOutcome, ...]
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware)


class V2ProductionFingerprint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_payload_json: str = Field(min_length=1)
    policy_identity: str = V2_PRODUCTION_POLICY_IDENTITY
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_aware)


class V2ProductionPipelineResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    db_path: str = Field(min_length=1)
    raw_claim: str = Field(min_length=1)
    state: V2ProductionState
    final_output: V2FinalResearchOutput | None = None
    failure_reason: str | None = None
    budget: V2BudgetSnapshot
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> V2ProductionPipelineResult:
        if self.state is V2ProductionState.RELEASED:
            if self.final_output is None or not self.final_output.release_validation.valid:
                raise ValueError("released v2 production results require valid final output")
            if self.failure_reason is not None:
                raise ValueError("released v2 production results cannot carry a failure")
        elif self.failure_reason is None:
            raise ValueError("unreleased v2 production results require a reason")
        return self


def run_v2_production_pipeline(
    raw_claim: str,
    *,
    db_path: str | Path,
    directions: ResearchDirections,
    discovery_providers: tuple[DiscoveryProvider, ...],
    search_providers: Mapping[DiscoveryProvider, SearchProvider],
    wigolo_provider: ScraperProvider | None,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    ceilings: V2RunCeilings | None = None,
    firecrawl_provider: ScraperProvider | None = None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None = None,
    run_id: UUID | None = None,
    provider_policy_fingerprint: str = "injected-provider-policy-v1",
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2ProductionPipelineResult:
    """Run or resume the complete v2 path under one physical-call/token authority."""
    resolved_ceilings = ceilings or V2RunCeilings()
    if not raw_claim or raw_claim != raw_claim.strip():
        raise ValueError("fresh v2 claim must be non-empty without surrounding whitespace")
    if not discovery_providers or len(set(discovery_providers)) != len(discovery_providers):
        raise ValueError("fresh v2 discovery providers must be a unique non-empty tuple")
    if any(provider not in search_providers for provider in discovery_providers):
        raise ValueError("every enabled discovery provider requires an explicit adapter")
    now = clock or _utc_now
    resolved_run_id = run_id or uuid4()
    path = str(Path(db_path).resolve())
    _prepare_identity(path, resolved_run_id, raw_claim, routing_config, now)
    fingerprint = _production_fingerprint(
        resolved_run_id,
        directions,
        discovery_providers,
        resolved_ceilings,
        routing_config,
        provider_policy_fingerprint,
        _aware(now()),
    )
    _persist_or_validate_fingerprint(path, fingerprint)
    try:
        stored = read_v2_artifact(path, resolved_run_id, V2_PRODUCTION_ARTIFACT_KEY)
    except KeyError:
        stored = None
    if stored is not None:
        return V2ProductionPipelineResult.model_validate_json(stored.payload_json)

    budgeted_llm = BudgetedV2LLMProvider(
        db_path=path,
        run_id=resolved_run_id,
        provider=llm_provider,
        routing_config=routing_config,
        ceilings=resolved_ceilings,
        clock=now,
    )
    try:
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, Stage.CLAIM_PLANNER, now)
        planner = run_v2_initial_planner(
            raw_claim,
            db_path=path,
            directions=directions,
            discovery_providers=discovery_providers,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            run_id=resolved_run_id,
            clock=now,
        ).planner_output
        if _cancelled(cancellation_requested):
            return _cancel(path, resolved_run_id, raw_claim, budgeted_llm, now)
        round_one_search = _run_round_one_search(
            path,
            planner.searches,
            search_providers,
            cancellation_requested,
            now,
        )
        responses = tuple(
            V2DiscoveryResponse(query=item.query, results=item.results)
            for item in round_one_search.outcomes
            if item.succeeded
        )
        discovery_one = run_v2_discovery_and_scout(
            db_path=path,
            planner_output=planner,
            responses=responses,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            clock=now,
            crossref_resolver=crossref_resolver,
        ).output
        acquisition_one = run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery_one,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            clock=now,
        ).output
        budget_after_round_one = budgeted_llm.snapshot()
        gap_one = run_v2_gap_analysis(
            db_path=path,
            gap_input=build_v2_gap_analysis_input(
                planner_output=planner,
                discovery_output=discovery_one,
                acquisition_output=acquisition_one,
                remaining_budget=V2GapBudgetState(
                    model_calls_remaining=budget_after_round_one.physical_calls_remaining,
                    tokens_remaining=budget_after_round_one.tokens_remaining,
                    cost_remaining_usd=budget_after_round_one.cost_remaining_usd,
                ),
            ),
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            clock=now,
        )
        adaptive_budget = _adaptive_budget(budgeted_llm.snapshot())
        continuation = run_v2_adaptive_search_continuation(
            db_path=path,
            initial_plan=planner,
            round_one_discovery=discovery_one,
            round_one_acquisition=acquisition_one,
            round_one_gap=gap_one,
            search_providers=search_providers,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            crossref_resolver=crossref_resolver,
            budget=adaptive_budget,
            cancellation_requested=cancellation_requested,
            clock=now,
        )
        if continuation.stopping_decision.stop_code is V2AdaptiveStopCode.CANCELLED:
            return _cancel(path, resolved_run_id, raw_claim, budgeted_llm, now)
        if budgeted_llm.snapshot().physical_calls_remaining < V2_MANDATORY_DOWNSTREAM_CALL_RESERVE:
            raise V2BudgetExceededError(
                "v2 downstream reserve cannot cover selection, extraction, analysis, "
                "review, and synthesis"
            )
        discoveries, acquisitions, gaps = _completed_round_artifacts(
            path,
            resolved_run_id,
            continuation,
            discovery_one,
            acquisition_one,
            gap_one,
        )
        if not continuation.merged_survivors.sources:
            raise ValueError("no source survived acquisition and deterministic Probe")
        selection_input = build_v2_source_selection_input(
            exact_claim=raw_claim,
            merged_survivors=continuation.merged_survivors,
            discovery_outputs=discoveries,
            acquisition_outputs=acquisitions,
            gap_outputs=gaps,
        )
        before_selection = budgeted_llm.snapshot()
        selection = run_v2_source_selection_and_queue(
            db_path=path,
            selection_input=selection_input,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            budget=V2DeepAnalysisBudget(
                physical_call_ceiling=resolved_ceilings.max_physical_calls,
                physical_calls_used=before_selection.physical_calls_used,
                tokens_remaining=before_selection.tokens_remaining,
                cost_remaining_usd=before_selection.cost_remaining_usd,
            ),
            clock=now,
        ).result
        if not selection.queued_source_ids:
            reason = (
                selection.limiting_reason.value
                if selection.limiting_reason is not None
                else "unknown"
            )
            raise V2BudgetExceededError(
                "v2 deep-analysis queue is empty; budget reservation blocked all "
                f"surviving sources ({reason}). Increase the cost, token, or call ceiling."
            )
        deep_analysis = run_v2_deep_analysis_with_backfill(
            db_path=path,
            queue_result=selection,
            discovery_outputs=discoveries,
            acquisition_outputs=acquisitions,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            clock=now,
        )
        reviewer = deep_analysis.final_reviewer_result
        approved_records = tuple(
            item for item in reviewer.source_results if item.ledger_record is not None
        )
        if not approved_records:
            reasons = tuple(
                dict.fromkeys(
                    item.failure for item in reviewer.source_results if item.failure is not None
                )
            )
            detail = f" Details: {'; '.join(reasons)}" if reasons else ""
            raise ValueError("v2 produced no Reviewer-approved evidence records." + detail)
        final = run_v2_final_research_output(
            db_path=path,
            reviewer_result=reviewer,
            continuation=continuation,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            clock=now,
        ).final_output
        state = (
            V2ProductionState.RELEASED
            if final.release_validation.valid
            else V2ProductionState.BLOCKED
        )
        reason = None if state is V2ProductionState.RELEASED else "release integrity blocked output"
        result = V2ProductionPipelineResult(
            run_id=resolved_run_id,
            db_path=path,
            raw_claim=raw_claim,
            state=state,
            final_output=final,
            failure_reason=reason,
            budget=budgeted_llm.snapshot(),
            completed_at=_aware(now()),
        )
        _persist_terminal(path, result, now)
        return result
    except Exception as exc:
        result = V2ProductionPipelineResult(
            run_id=resolved_run_id,
            db_path=path,
            raw_claim=raw_claim,
            state=V2ProductionState.FAILED,
            failure_reason=f"{type(exc).__name__}: {exc}"[:2000],
            budget=budgeted_llm.snapshot(),
            completed_at=_aware(now()),
        )
        _persist_terminal(path, result, now)
        return result


def _prepare_identity(
    path: str,
    run_id: UUID,
    raw_claim: str,
    routing: V2RoutingConfig,
    clock: Callable[[], datetime],
) -> None:
    init_db(path)
    timestamp = _aware(clock())
    try:
        manifest = read_run(path, run_id)
    except KeyError:
        insert_run(
            path,
            RunManifest(
                run_id=run_id,
                status=RunStatus.PLANNED,
                raw_claim=raw_claim,
                current_stage=Stage.CLAIM_PLANNER,
                created_at=timestamp,
                updated_at=timestamp,
            ),
        )
    else:
        if manifest.raw_claim != raw_claim:
            raise ValueError("cross-claim v2 resume is forbidden")
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), timestamp)
    contract = routing.contract(run_id, timestamp)
    try:
        existing = read_provider_run_contract(path, run_id)
    except KeyError:
        insert_provider_run_contract(path, contract)
    else:
        if existing.fingerprint_sha256 != contract.fingerprint_sha256:
            raise ValueError("cross-version v2 resume is forbidden; use a new run ID")


def _production_fingerprint(
    run_id: UUID,
    directions: ResearchDirections,
    providers: tuple[DiscoveryProvider, ...],
    ceilings: V2RunCeilings,
    routing: V2RoutingConfig,
    provider_policy_fingerprint: str,
    created_at: datetime,
) -> V2ProductionFingerprint:
    payload = {
        "policy": V2_PRODUCTION_POLICY_IDENTITY,
        "directions": directions.model_dump(mode="json"),
        "providers": [provider.value for provider in providers],
        "ceilings": ceilings.model_dump(mode="json"),
        "routing_contract": routing.fingerprint_payload(),
        "provider_policy_fingerprint": provider_policy_fingerprint,
        "semantic_policy": _semantic_policy_payload(),
        "round_limit": 3,
        "final_output_contract": "researchassistant-v2-phase-11-final-output-v1",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return V2ProductionFingerprint(
        run_id=run_id,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        canonical_payload_json=canonical,
        created_at=created_at,
    )


def _semantic_policy_payload() -> dict[str, object]:
    prompt_hashes = {
        name: hashlib.sha256((Path(__file__).parent / "prompts" / name).read_bytes()).hexdigest()
        for name in ("v2_initial_planner.md", "v2_scout.md", "v2_evidence_analyst.md")
    }
    schema_types = (
        V2InitialPlannerModelOutput,
        ScoutBatch,
        V2GapAnalysisModelOutput,
        V2AdaptiveSearchModelOutput,
        V2SourceSelectionModelOutput,
        V2SourceSelectionQueueResult,
        V2DeepAnalysisBackfillResult,
        V2VerbatimQuoteSelection,
        V2EvidenceAnalystModelOutput,
        V2CanonicalStatementModelOutput,
        ReviewerDecision,
        SynthesisOutput,
        V2FinalResearchOutput,
        V2ProductionPipelineResult,
    )
    schemas = json.dumps(
        {item.__name__: item.model_json_schema() for item in schema_types},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "deep_analysis_queue_policy": (
            "researchassistant-v2-phase-8-deep-analysis-queue-v2-source-cap-60k-v1"
        ),
        "deep_analysis_backfill_policy": V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
        "deep_analysis_source_token_cap": V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
        "deep_analysis_source_physical_call_cap": V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
        "deep_analysis_workload": {
            "extractor_logical_calls": 1,
            "analyst_logical_calls": 2,
            "reviewer_logical_calls": 1,
            "attempts_per_logical_operation": 2,
        },
        "custom_prompt_hashes": prompt_hashes,
        "schema_sha256": hashlib.sha256(schemas.encode()).hexdigest(),
        "evidence_policy": EVIDENCE_POLICY_VERSION,
        "extraction_policy": V2_EXTRACTION_POLICY_IDENTITY,
        "reviewer_ledger_policy": V2_REVIEWER_LEDGER_POLICY_VERSION,
        "final_output_policy": V2_FINAL_OUTPUT_POLICY_IDENTITY,
        "release_validator": V2_FINAL_VALIDATOR_CONFIG_VERSION,
        "research_governor": DEFAULT_RESEARCH_GOVERNOR_POLICY.model_dump(mode="json"),
        "downstream_call_reserve": V2_MANDATORY_DOWNSTREAM_CALL_RESERVE,
        "round_three_workload_call_reserve": V2_ROUND_THREE_COMPLETE_WORKLOAD_CALL_RESERVE,
    }


def _persist_or_validate_fingerprint(path: str, fingerprint: V2ProductionFingerprint) -> None:
    try:
        stored = read_v2_artifact(path, fingerprint.run_id, V2_PRODUCTION_FINGERPRINT_KEY)
    except KeyError:
        insert_v2_artifact(
            path,
            V2_PRODUCTION_FINGERPRINT_KEY,
            fingerprint,
            fingerprint.created_at,
        )
        return
    existing = V2ProductionFingerprint.model_validate_json(stored.payload_json)
    if existing.sha256 != fingerprint.sha256:
        raise ValueError("v2 production policy fingerprint changed; use a new run ID")


def _run_round_one_search(
    path: str,
    queries: tuple[V2RoundOneSearchQuery, ...],
    providers: Mapping[DiscoveryProvider, SearchProvider],
    cancellation_requested: Callable[[], bool] | None,
    clock: Callable[[], datetime],
) -> V2RoundOneSearchResult:
    run_id = queries[0].run_id
    try:
        stored = read_v2_artifact(path, run_id, V2_ROUND_ONE_SEARCH_KEY)
    except KeyError:
        stored = None
    if stored is not None:
        return V2RoundOneSearchResult.model_validate_json(stored.payload_json)
    outcomes: list[V2RoundOneSearchOutcome] = []
    for query in queries:
        if _cancelled(cancellation_requested):
            break
        try:
            response = providers[query.provider].search(
                SearchRequest(
                    run_id=query.run_id,
                    provider=query.provider,
                    intent=(
                        SearchIntent.ACADEMIC_STUDY
                        if query.provider
                        in {
                            DiscoveryProvider.OPENALEX,
                            DiscoveryProvider.ARXIV,
                            DiscoveryProvider.PUBMED,
                        }
                        else SearchIntent.BROAD_WEB
                    ),
                    query_text=query.query_text,
                    limit=5,
                )
            )
            outcomes.append(
                V2RoundOneSearchOutcome(
                    query=query,
                    succeeded=True,
                    results=tuple(response.results),
                )
            )
        except SearchProviderError as exc:
            outcomes.append(
                V2RoundOneSearchOutcome(
                    query=query,
                    succeeded=False,
                    failure_code=exc.code.value,
                    failure_message=str(exc) or exc.code.value,
                )
            )
        except Exception as exc:
            outcomes.append(
                V2RoundOneSearchOutcome(
                    query=query,
                    succeeded=False,
                    failure_code=SearchFailureCode.PERMANENT_FAILURE.value,
                    failure_message=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
    result = V2RoundOneSearchResult(
        run_id=run_id,
        outcomes=tuple(outcomes),
        completed_at=_aware(clock()),
    )
    insert_v2_artifact(path, V2_ROUND_ONE_SEARCH_KEY, result, result.completed_at)
    return result


def _adaptive_budget(snapshot: V2BudgetSnapshot) -> V2AdaptiveBudgetState:
    downstream_fits = (
        snapshot.physical_calls_remaining
        > V2_MANDATORY_DOWNSTREAM_CALL_RESERVE + V2_ROUND_THREE_COMPLETE_WORKLOAD_CALL_RESERVE
    )
    return V2AdaptiveBudgetState(
        model_calls_remaining=snapshot.physical_calls_remaining,
        tokens_remaining=snapshot.tokens_remaining,
        cost_remaining_usd=snapshot.cost_remaining_usd,
        protected_downstream_model_calls=V2_MANDATORY_DOWNSTREAM_CALL_RESERVE,
        round_three_complete_workload_reservable=downstream_fits,
    )


def _completed_round_artifacts(
    path: str,
    run_id: UUID,
    continuation: V2AdaptiveContinuationResult,
    discovery_one: V2DiscoveryScoutOutput,
    acquisition_one: V2AcquisitionProbeOutput,
    gap_one: V2GapAnalysisOutput,
) -> tuple[
    tuple[V2DiscoveryScoutOutput, ...],
    tuple[V2AcquisitionProbeOutput, ...],
    tuple[V2GapAnalysisOutput, ...],
]:
    discoveries = [discovery_one]
    acquisitions = [acquisition_one]
    gaps = [gap_one]
    for round_number in range(2, continuation.stopping_decision.completed_rounds + 1):
        discovery = read_v2_artifact(path, run_id, f"phase-7-round-{round_number}-discovery-scout")
        acquisition = read_v2_artifact(
            path, run_id, f"phase-7-round-{round_number}-acquisition-probe"
        )
        discoveries.append(V2DiscoveryScoutOutput.model_validate_json(discovery.payload_json))
        acquisitions.append(V2AcquisitionProbeOutput.model_validate_json(acquisition.payload_json))
        if round_number == 2:
            try:
                gap = read_v2_artifact(path, run_id, "phase-7-gap-analysis-after-round-2")
            except KeyError:
                continue
            gaps.append(V2GapAnalysisOutput.model_validate_json(gap.payload_json))
    return tuple(discoveries), tuple(acquisitions), tuple(gaps)


def _cancel(
    path: str,
    run_id: UUID,
    raw_claim: str,
    provider: BudgetedV2LLMProvider,
    clock: Callable[[], datetime],
) -> V2ProductionPipelineResult:
    result = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=path,
        raw_claim=raw_claim,
        state=V2ProductionState.CANCELLED,
        failure_reason="Cancellation was observed before another provider call started.",
        budget=provider.snapshot(),
        completed_at=_aware(clock()),
    )
    _persist_terminal(path, result, clock)
    return result


def _persist_terminal(
    path: str,
    result: V2ProductionPipelineResult,
    clock: Callable[[], datetime],
) -> None:
    insert_v2_artifact(path, V2_PRODUCTION_ARTIFACT_KEY, result, result.completed_at)
    status = {
        V2ProductionState.RELEASED: RunStatus.COMPLETED,
        V2ProductionState.BLOCKED: RunStatus.BLOCKED,
        V2ProductionState.CANCELLED: RunStatus.CANCELLED,
        V2ProductionState.FAILED: RunStatus.FAILED,
    }[result.state]
    _set_run_state(path, result.run_id, status, Stage.FINAL_RENDERER_VALIDATOR, clock)


def _set_run_state(
    path: str,
    run_id: UUID,
    status: RunStatus,
    stage: Stage,
    clock: Callable[[], datetime],
) -> None:
    current = read_run(path, run_id)
    timestamp = _aware(clock())
    update_run(
        path,
        current.model_copy(
            update={
                "status": status,
                "current_stage": stage,
                "updated_at": timestamp,
                "completed_at": (
                    timestamp
                    if status
                    in {
                        RunStatus.COMPLETED,
                        RunStatus.BLOCKED,
                        RunStatus.CANCELLED,
                        RunStatus.FAILED,
                    }
                    else None
                ),
            }
        ),
    )


def _cancelled(callback: Callable[[], bool] | None) -> bool:
    return bool(callback and callback())


def _utc_now() -> datetime:
    return datetime.now(UTC)
