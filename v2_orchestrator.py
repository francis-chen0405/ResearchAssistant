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
from agents.synthesizer import V2_DETERMINISTIC_SYNTHESIZER_VERSION
from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY, run_v2_acquisition_probe
from agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveContinuationResult,
    V2AdaptiveSearchResults,
    V2AdaptiveStopCode,
    run_v2_adaptive_search_continuation,
)
from agents.v2_deep_analysis import (
    V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
    run_v2_deep_analysis_with_backfill,
)
from agents.v2_discovery import (
    V2_SCOUT_ARTIFACT_KEY,
    V2DiscoveryResponse,
    run_v2_discovery_and_scout,
)
from agents.v2_extraction import V2_EXTRACTION_ARTIFACT_KEY, V2_EXTRACTION_POLICY_IDENTITY
from agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_POLICY_IDENTITY,
    V2_FINAL_VALIDATOR_CONFIG_VERSION,
    run_v2_final_research_output,
)
from agents.v2_gap_analysis import build_v2_gap_analysis_input, run_v2_gap_analysis
from agents.v2_initial_planner import run_v2_initial_planner
from agents.v2_source_selection import (
    V2_SOURCE_SELECTION_COMPLETION_KEY,
    V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY,
    build_v2_source_selection_input,
    run_v2_source_selection_and_queue,
)
from models import (
    V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
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
    V2DeepAnalysisBackfillResult,
    V2DeepAnalysisBudget,
    V2DiscoveryScoutOutput,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionRecord,
    V2EvidenceAdmissionSourceResult,
    V2EvidenceAnalystModelOutput,
    V2FinalResearchOutput,
    V2GapAnalysisModelOutput,
    V2GapAnalysisOutput,
    V2GapBudgetState,
    V2InitialPlannerModelOutput,
    V2PipelineIdentity,
    V2ProviderRunDiagnostics,
    V2ResultSourceStatus,
    V2RoundOneSearchQuery,
    V2RunDiagnostics,
    V2SourceSelectionModelOutput,
    V2SourceSelectionQueueResult,
    V2SynthesizerInput,
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
    V2CancellationRequested,
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
    open_read_only_store,
    read_cancellation_request,
    read_provider_run_contract,
    read_run,
    read_v2_artifact,
    update_run,
)

V2_PRODUCTION_LEGACY_ARTIFACT_KEY = "phase-12-production-result"
V2_PRODUCTION_LEGACY_FINGERPRINT_KEY = "phase-12-production-fingerprint"
V2_PRODUCTION_ARTIFACT_KEY = "phase-13-production-result-analyzer-admission"
V2_PRODUCTION_FINGERPRINT_KEY = "phase-13-production-fingerprint-analyzer-admission"
V2_ROUND_ONE_LEGACY_SEARCH_KEY = "phase-12-round-1-search"
V2_ROUND_ONE_SEARCH_KEY = "phase-13-round-1-search"
V2_PRODUCTION_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-production-cutover-analyzer-admission-v1"
)
V2_DEEP_ANALYSIS_BACKFILL_LEGACY_ARTIFACT_KEY = "phase-12-deep-analysis-backfill-v1"
V2_MANDATORY_DOWNSTREAM_CALL_RESERVE = 8
V2_ROUND_THREE_COMPLETE_WORKLOAD_CALL_RESERVE = 8


def _read_v2_payload(path: str | Path, run_id: UUID, artifact_key: str) -> str | None:
    try:
        with open_read_only_store(path) as store:
            artifact = read_v2_artifact(store.connection, run_id, artifact_key)
    except KeyError:
        return None
    return artifact.payload_json


def _json_list_count(payload: str, field_name: str) -> int:
    value = json.loads(payload).get(field_name, ())
    return len(value) if isinstance(value, list) else 0


def _empty_v2_run_diagnostics(
    configured_providers: tuple[DiscoveryProvider, ...],
) -> V2RunDiagnostics:
    return V2RunDiagnostics(
        configured_providers=configured_providers,
        provider_outcomes=tuple(
            V2ProviderRunDiagnostics(provider=provider) for provider in configured_providers
        ),
    )


def configured_v2_providers(path: str | Path, run_id: UUID) -> tuple[DiscoveryProvider, ...]:
    """Read the configured discovery lanes from the immutable v2 fingerprint."""
    payload = _read_v2_payload(path, run_id, V2_PRODUCTION_FINGERPRINT_KEY)
    if payload is None:
        payload = _read_v2_payload(path, run_id, V2_PRODUCTION_LEGACY_FINGERPRINT_KEY)
    if payload is None:
        return ()
    fingerprint = V2ProductionFingerprint.model_validate_json(payload)
    encoded = json.loads(fingerprint.canonical_payload_json)
    providers = encoded.get("providers")
    if not isinstance(providers, list) or not providers:
        return ()
    return tuple(dict.fromkeys(DiscoveryProvider(provider) for provider in providers))


def build_v2_run_diagnostics(
    path: str | Path,
    run_id: UUID,
    configured_providers: tuple[DiscoveryProvider, ...],
    final_output: V2FinalResearchOutput | None = None,
) -> V2RunDiagnostics:
    """Reconstruct persisted v2 execution facts for both new and historical runs."""
    providers = list(dict.fromkeys(configured_providers))
    counters: dict[DiscoveryProvider, dict[str, int]] = {
        provider: {
            "query_attempts": 0,
            "non_empty_queries": 0,
            "empty_queries": 0,
            "timeout_queries": 0,
            "failed_queries": 0,
            "search_results": 0,
        }
        for provider in providers
    }

    def record_search(
        provider: DiscoveryProvider,
        succeeded: bool,
        result_count: int,
        failure_code: str | None,
    ) -> None:
        if provider not in counters:
            providers.append(provider)
            counters[provider] = {
                "query_attempts": 0,
                "non_empty_queries": 0,
                "empty_queries": 0,
                "timeout_queries": 0,
                "failed_queries": 0,
                "search_results": 0,
            }
        provider_counts = counters[provider]
        provider_counts["query_attempts"] += 1
        provider_counts["search_results"] += result_count
        if succeeded:
            provider_counts["non_empty_queries" if result_count else "empty_queries"] += 1
        elif failure_code == SearchFailureCode.EMPTY_RESULTS.value:
            provider_counts["empty_queries"] += 1
        elif failure_code == SearchFailureCode.TIMEOUT.value:
            provider_counts["timeout_queries"] += 1
        else:
            provider_counts["failed_queries"] += 1

    round_one_payload = _read_v2_payload(path, run_id, V2_ROUND_ONE_SEARCH_KEY)
    if round_one_payload is not None:
        round_one = V2RoundOneSearchResult.model_validate_json(round_one_payload)
        for outcome in round_one.outcomes:
            record_search(
                outcome.query.provider,
                outcome.succeeded,
                len(outcome.results),
                outcome.failure_code,
            )
    for round_number in (2, 3):
        search_payload = _read_v2_payload(
            path, run_id, f"phase-7-round-{round_number}-search-results"
        )
        if search_payload is None:
            continue
        search_result = V2AdaptiveSearchResults.model_validate_json(search_payload)
        for outcome in search_result.outcomes:
            record_search(
                outcome.query.provider,
                outcome.succeeded,
                len(outcome.results),
                outcome.failure_code,
            )

    cluster_providers: dict[UUID, tuple[DiscoveryProvider, ...]] = {}
    for round_number in (1, 2, 3):
        discovery_key = (
            V2_SCOUT_ARTIFACT_KEY
            if round_number == 1
            else f"phase-7-round-{round_number}-discovery-scout"
        )
        discovery_payload = _read_v2_payload(path, run_id, discovery_key)
        if discovery_payload is None:
            continue
        discovery = V2DiscoveryScoutOutput.model_validate_json(discovery_payload)
        for cluster in discovery.clusters:
            cluster_providers[cluster.cluster_id] = tuple(
                dict.fromkeys(reference.provider for reference in cluster.provider_references)
            )

    acquisition_attempts = 0
    acquired_snapshot_ids: set[UUID] = set()
    survived_snapshot_ids: set[UUID] = set()
    surviving_by_provider: dict[DiscoveryProvider, set[UUID]] = {
        provider: set() for provider in providers
    }
    for round_number in (1, 2, 3):
        acquisition_key = (
            V2_ACQUISITION_PROBE_ARTIFACT_KEY
            if round_number == 1
            else f"phase-7-round-{round_number}-acquisition-probe"
        )
        acquisition_payload = _read_v2_payload(path, run_id, acquisition_key)
        if acquisition_payload is None:
            continue
        acquisition = V2AcquisitionProbeOutput.model_validate_json(acquisition_payload)
        acquisition_attempts += len(acquisition.attempts)
        for source in acquisition.acquisitions:
            acquired_snapshot_ids.add(source.snapshot.snapshot_id)
        for survivor in acquisition.survivors:
            survived_snapshot_ids.add(survivor.snapshot_id)
            for provider in cluster_providers.get(survivor.cluster_id, ()):
                surviving_by_provider.setdefault(provider, set()).add(survivor.snapshot_id)

    queue_payload = _read_v2_payload(path, run_id, V2_SOURCE_SELECTION_COMPLETION_KEY)
    if queue_payload is None:
        queue_payload = _read_v2_payload(path, run_id, V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY)
    queued_sources = 0
    if queue_payload is not None:
        try:
            queue = V2SourceSelectionQueueResult.model_validate_json(queue_payload)
        except ValueError:
            queued_sources = _json_list_count(queue_payload, "queued_source_ids")
        else:
            queued_sources = len(queue.queued_source_ids)

    analyzed_sources = 0
    approved_records = 0
    backfill_payload = _read_v2_payload(path, run_id, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY)
    if backfill_payload is None:
        backfill_payload = _read_v2_payload(
            path, run_id, V2_DEEP_ANALYSIS_BACKFILL_LEGACY_ARTIFACT_KEY
        )
    if backfill_payload is not None:
        try:
            backfill = V2DeepAnalysisBackfillResult.model_validate_json(backfill_payload)
        except ValueError:
            backfill_json = json.loads(backfill_payload)
            executions = backfill_json.get("source_executions", ())
            admission = backfill_json.get("final_admission_result")
            reviewer = backfill_json.get("final_reviewer_result", {})
            admission_sources = (
                admission.get("source_results", ())
                if isinstance(admission, dict)
                else reviewer.get("source_results", ())
            )
            analyzed_sources = sum(
                isinstance(item, dict) and item.get("state") != "not_attempted"
                for item in executions
            )
            approved_records = sum(
                isinstance(item, dict)
                and (
                    item.get("evidence_record") is not None or item.get("ledger_record") is not None
                )
                for item in admission_sources
            )
            final_queue = backfill_json.get("final_queue_result", {})
            queued_ids = final_queue.get("queued_source_ids", ())
            if isinstance(queued_ids, list):
                queued_sources = len(queued_ids)
        else:
            analyzed_sources = sum(
                execution.state.value != "not_attempted" for execution in backfill.source_executions
            )
            approved_records = (
                sum(
                    item.evidence_record is not None
                    for item in backfill.final_admission_result.source_results
                )
                if backfill.final_admission_result is not None
                else sum(
                    item.ledger_record is not None
                    for item in (
                        backfill.final_reviewer_result.source_results
                        if backfill.final_reviewer_result
                        else ()
                    )
                )
            )
            queued_sources = len(backfill.final_queue_result.queued_source_ids)
    elif final_output is not None:
        analyzed_statuses = {
            V2ResultSourceStatus.RECOMMENDED_ANALYZED,
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_ADMITTED,
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_REJECTED,
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_FAILED,
            V2ResultSourceStatus.SURVIVING_ANALYZED,
            V2ResultSourceStatus.SURVIVING_ANALYZER_ADMITTED,
            V2ResultSourceStatus.SURVIVING_ANALYZER_REJECTED,
            V2ResultSourceStatus.SURVIVING_ANALYZER_FAILED,
        }
        analyzed_sources = sum(
            source.status in analyzed_statuses for source in final_output.all_surviving_sources
        )
        approved_records = sum(
            len(source.ledger_claim_ids) for source in final_output.all_surviving_sources
        )

    provider_outcomes = tuple(
        V2ProviderRunDiagnostics(
            provider=provider,
            query_attempts=counters[provider]["query_attempts"],
            non_empty_queries=counters[provider]["non_empty_queries"],
            empty_queries=counters[provider]["empty_queries"],
            timeout_queries=counters[provider]["timeout_queries"],
            failed_queries=counters[provider]["failed_queries"],
            search_results=counters[provider]["search_results"],
            surviving_sources=len(surviving_by_provider.get(provider, set())),
        )
        for provider in providers
    )
    return V2RunDiagnostics(
        configured_providers=tuple(providers),
        provider_outcomes=provider_outcomes,
        search_attempts=sum(item.query_attempts for item in provider_outcomes),
        search_results=sum(item.search_results for item in provider_outcomes),
        acquisition_attempts=acquisition_attempts,
        sources_acquired=len(acquired_snapshot_ids),
        sources_survived_probe=len(survived_snapshot_ids),
        sources_queued_for_analysis=queued_sources,
        sources_analyzed=analyzed_sources,
        approved_evidence_records=approved_records,
    )


def build_v2_run_diagnostics_or_empty(
    path: str | Path,
    run_id: UUID,
    configured_providers: tuple[DiscoveryProvider, ...],
    final_output: V2FinalResearchOutput | None = None,
) -> V2RunDiagnostics:
    """Keep observability failures from replacing the authoritative terminal result."""
    try:
        return build_v2_run_diagnostics(path, run_id, configured_providers, final_output)
    except Exception:
        return _empty_v2_run_diagnostics(configured_providers)


def infer_v2_stage(
    path: str | Path,
    run_id: UUID,
    current_stage: Stage,
    final_output_present: bool,
) -> Stage:
    """Recover a useful stage for v2 artifacts written before stage persistence existed."""
    if current_stage is not Stage.CLAIM_PLANNER:
        return current_stage
    if final_output_present or any(
        _read_v2_payload(path, run_id, artifact_key) is not None
        for artifact_key in (V2_FINAL_OUTPUT_ARTIFACT_KEY, V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY)
    ):
        return Stage.FINAL_RENDERER_VALIDATOR
    for artifact_key, stage in (
        (V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY, Stage.SYNTHESIS),
        (V2_DEEP_ANALYSIS_BACKFILL_LEGACY_ARTIFACT_KEY, Stage.SYNTHESIS),
        ("phase-10-reviewer-ledger", Stage.REVIEW),
        (V2_EXTRACTION_ARTIFACT_KEY, Stage.DEEP_ANALYSIS),
        ("phase-12-exact-extraction", Stage.DEEP_ANALYSIS),
        (V2_SOURCE_SELECTION_COMPLETION_KEY, Stage.SOURCE_SELECTION),
        (V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY, Stage.SOURCE_SELECTION),
        ("phase-7-adaptive-search-completion", Stage.ADAPTIVE_SEARCH),
        ("phase-6-gap-analysis", Stage.GAP_ANALYSIS),
        (V2_ACQUISITION_PROBE_ARTIFACT_KEY, Stage.ACQUISITION),
        (V2_SCOUT_ARTIFACT_KEY, Stage.DISCOVERY),
        (V2_ROUND_ONE_SEARCH_KEY, Stage.DISCOVERY),
        (V2_ROUND_ONE_LEGACY_SEARCH_KEY, Stage.DISCOVERY),
    ):
        if _read_v2_payload(path, run_id, artifact_key) is not None:
            return stage
    return current_stage


def _format_no_approved_evidence_failure(
    deep_analysis: V2DeepAnalysisBackfillResult,
) -> str:
    """Explain why deep analysis produced no analyzer-admitted evidence."""
    attempted_count = sum(
        execution.state.value != "not_attempted" for execution in deep_analysis.source_executions
    )
    details: list[str] = []
    seen: set[str] = set()
    for execution in deep_analysis.source_executions:
        if execution.failure_reason is None:
            continue
        detail = (
            f"Source {execution.source_id} [{execution.state.value}]: {execution.failure_reason}"
        )
        if detail not in seen:
            details.append(detail)
            seen.add(detail)
    for reason in deep_analysis.terminal_reasons:
        if reason not in seen:
            details.append(reason)
            seen.add(reason)
    summary = (
        "v2 produced no analyzer-admitted evidence records. "
        f"Attempted sources: {attempted_count}; admitted sources: 0."
    )
    if details:
        summary += " Failures: " + " | ".join(details)
    return summary[:2000]


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
    current_stage: Stage = Stage.CLAIM_PLANNER
    final_output: V2FinalResearchOutput | None = None
    failure_reason: str | None = None
    diagnostics: V2RunDiagnostics | None = None
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


def v2_cancellation_requested(db_path: str | Path, run_id: UUID) -> bool:
    """Read the persisted cooperative-cancellation flag for one v2 run."""
    try:
        read_cancellation_request(str(Path(db_path).resolve()), run_id)
    except KeyError:
        return False
    return True


def _raise_if_v2_cancelled(callback: Callable[[], bool] | None) -> None:
    if _cancelled(callback):
        raise V2CancellationRequested("v2 cancellation was observed at an orchestration boundary")


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

    # A completed Phase-12 run is an immutable historical result. Read it before
    # creating or validating the Phase-13 identity, whose route fingerprint is
    # intentionally different after the Analyzer Admission cutover.
    init_db(path)
    try:
        legacy_terminal = read_v2_artifact(path, resolved_run_id, V2_PRODUCTION_LEGACY_ARTIFACT_KEY)
    except KeyError:
        legacy_terminal = None
    if legacy_terminal is not None:
        return V2ProductionPipelineResult.model_validate_json(legacy_terminal.payload_json)

    def effective_cancellation_requested() -> bool:
        return _cancelled(cancellation_requested) or v2_cancellation_requested(
            path, resolved_run_id
        )

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
        cancellation_requested=effective_cancellation_requested,
        clock=now,
    )
    current_stage = Stage.CLAIM_PLANNER
    try:
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
        _raise_if_v2_cancelled(effective_cancellation_requested)
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
        _raise_if_v2_cancelled(effective_cancellation_requested)
        current_stage = Stage.DISCOVERY
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
        round_one_search = _run_round_one_search(
            path,
            planner.searches,
            search_providers,
            effective_cancellation_requested,
            now,
        )
        _raise_if_v2_cancelled(effective_cancellation_requested)
        responses = tuple(
            V2DiscoveryResponse(query=item.query, results=item.results)
            for item in round_one_search.outcomes
            if item.succeeded
        )
        current_stage = Stage.DISCOVERY
        discovery_one = run_v2_discovery_and_scout(
            db_path=path,
            planner_output=planner,
            responses=responses,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            clock=now,
            crossref_resolver=crossref_resolver,
            cancellation_requested=effective_cancellation_requested,
        ).output
        _raise_if_v2_cancelled(effective_cancellation_requested)
        current_stage = Stage.ACQUISITION
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
        acquisition_one = run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery_one,
            wigolo_provider=wigolo_provider,
            firecrawl_provider=firecrawl_provider,
            cancellation_requested=effective_cancellation_requested,
            clock=now,
        ).output
        _raise_if_v2_cancelled(effective_cancellation_requested)
        budget_after_round_one = budgeted_llm.snapshot()
        current_stage = Stage.GAP_ANALYSIS
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
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
        _raise_if_v2_cancelled(effective_cancellation_requested)
        current_stage = Stage.ADAPTIVE_SEARCH
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
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
            cancellation_requested=effective_cancellation_requested,
            clock=now,
        )
        if continuation.stopping_decision.stop_code is V2AdaptiveStopCode.CANCELLED:
            return _cancel(
                path,
                resolved_run_id,
                raw_claim,
                budgeted_llm,
                current_stage,
                discovery_providers,
                now,
            )
        _raise_if_v2_cancelled(effective_cancellation_requested)
        if budgeted_llm.snapshot().physical_calls_remaining < V2_MANDATORY_DOWNSTREAM_CALL_RESERVE:
            raise V2BudgetExceededError(
                "v2 downstream reserve cannot cover selection, extraction, analysis, and admission"
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
        current_stage = Stage.SOURCE_SELECTION
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
        _raise_if_v2_cancelled(effective_cancellation_requested)
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
        _raise_if_v2_cancelled(effective_cancellation_requested)
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
        current_stage = Stage.DEEP_ANALYSIS
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
        _raise_if_v2_cancelled(effective_cancellation_requested)
        deep_analysis = run_v2_deep_analysis_with_backfill(
            db_path=path,
            queue_result=selection,
            discovery_outputs=discoveries,
            acquisition_outputs=acquisitions,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            clock=now,
        )
        _raise_if_v2_cancelled(effective_cancellation_requested)
        current_stage = Stage.EVIDENCE_ADMISSION
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
        admission = deep_analysis.final_admission_result
        if admission is None:
            raise ValueError("fresh v2 deep analysis did not produce an evidence admission result")
        approved_records = tuple(
            item for item in admission.source_results if item.evidence_record is not None
        )
        if not approved_records:
            raise ValueError(_format_no_approved_evidence_failure(deep_analysis))
        current_stage = Stage.SYNTHESIS
        _set_run_state(path, resolved_run_id, RunStatus.RUNNING, current_stage, now)
        _raise_if_v2_cancelled(effective_cancellation_requested)
        final = run_v2_final_research_output(
            db_path=path,
            admission_result=admission,
            continuation=continuation,
            llm_provider=budgeted_llm,
            routing_config=routing_config,
            clock=now,
        ).final_output
        _raise_if_v2_cancelled(effective_cancellation_requested)
        current_stage = Stage.FINAL_RENDERER_VALIDATOR
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
            current_stage=current_stage,
            final_output=final,
            failure_reason=reason,
            diagnostics=build_v2_run_diagnostics_or_empty(
                path,
                resolved_run_id,
                discovery_providers,
                final_output=final,
            ),
            budget=budgeted_llm.snapshot(),
            completed_at=_aware(now()),
        )
        _persist_terminal(path, result, now)
        return result
    except V2CancellationRequested:
        return _cancel(
            path,
            resolved_run_id,
            raw_claim,
            budgeted_llm,
            current_stage,
            discovery_providers,
            now,
        )
    except Exception as exc:
        result = V2ProductionPipelineResult(
            run_id=resolved_run_id,
            db_path=path,
            raw_claim=raw_claim,
            state=V2ProductionState.FAILED,
            current_stage=current_stage,
            failure_reason=f"{type(exc).__name__}: {exc}"[:2000],
            diagnostics=build_v2_run_diagnostics_or_empty(
                path, resolved_run_id, discovery_providers
            ),
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
        "final_output_contract": "researchassistant-v2-phase-13-final-output-analyzer-admission-v1",
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
        V2EvidenceAdmissionBatchResult,
        V2EvidenceAdmissionSourceResult,
        V2EvidenceAdmissionRecord,
        V2SynthesizerInput,
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
            "researchassistant-v2-phase-13-deep-analysis-queue-analyzer-admission-v1"
        ),
        "deep_analysis_backfill_policy": V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
        "deep_analysis_source_token_cap": V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
        "deep_analysis_source_physical_call_cap": V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
        "deep_analysis_workload": {
            "extractor_logical_calls": 1,
            "analyst_logical_calls": 1,
            "reviewer_logical_calls": 0,
            "synthesizer_logical_calls": 0,
            "attempts_per_logical_operation": {
                "extractor": 2,
                "analyst": 1,
                "reviewer": 0,
                "synthesizer": 0,
            },
        },
        "synthesis_assembly": V2_DETERMINISTIC_SYNTHESIZER_VERSION,
        "custom_prompt_hashes": prompt_hashes,
        "schema_sha256": hashlib.sha256(schemas.encode()).hexdigest(),
        "evidence_policy": EVIDENCE_POLICY_VERSION,
        "extraction_policy": V2_EXTRACTION_POLICY_IDENTITY,
        "evidence_admission_policy": V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
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
    current_stage: Stage,
    discovery_providers: tuple[DiscoveryProvider, ...],
    clock: Callable[[], datetime],
) -> V2ProductionPipelineResult:
    result = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=path,
        raw_claim=raw_claim,
        state=V2ProductionState.CANCELLED,
        current_stage=current_stage,
        failure_reason="Cancellation was observed before another provider call started.",
        diagnostics=build_v2_run_diagnostics_or_empty(path, run_id, discovery_providers),
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
    terminal_stage = (
        Stage.FINAL_RENDERER_VALIDATOR
        if result.state is V2ProductionState.RELEASED
        else result.current_stage
    )
    _set_run_state(path, result.run_id, status, terminal_stage, clock)


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
