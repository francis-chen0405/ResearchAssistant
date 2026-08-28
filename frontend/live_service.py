"""Typed application service for the persisted MVP-4 live pipeline."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection
from threading import Lock
from typing import IO, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY
from agents.v2_discovery import V2_SCOUT_ARTIFACT_KEY
from agents.v2_evidence_analyst import (
    V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
    V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX,
)
from agents.v2_final_output import render_v2_final_output
from agents.v2_source_selection import (
    V2_SOURCE_SELECTION_COMPLETION_KEY,
    V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY,
)
from cli import CLIExitCode, repository_identity
from frontend.security import redact_text
from models import (
    DEFAULT_RESEARCH_CONTROLS,
    DiscoveryProvider,
    ResearchControls,
    ResearchDirection,
    ResearchDirections,
    ResearchMode,
    RunManifest,
    RunStatus,
    Stage,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2EvidenceAnalystSourceResult,
    V2PersistedArtifact,
    V2ResultSource,
    V2ResultSourceStatus,
    V2RunDiagnostics,
    V2SourceSelectionQueueResult,
)
from money import ExactUSD, add_usd
from orchestrator import (
    MVP10_TARGETED_RESEARCHERS_ARTIFACT,
    MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
    MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT,
    PHASE9_RESEARCHERS_ARTIFACT,
    ClaimMismatchError,
    FingerprintMismatchError,
    ProviderPipelineResult,
    ProviderRunStatus,
    ResearcherPairResult,
    inspect_provider_run,
    request_run_cancellation,
)
from providers.config import ProviderConfigurationError, RunCeilings, WigoloConfig
from providers.mimo_factory import MimoProviderFactoryConfig
from providers.v2_budget import (
    V2BudgetSnapshot,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2RunCeilings,
)
from providers.v2_factory import V2ProductionFactoryConfig, build_v2_production_bundle
from store import (
    list_runs,
    open_read_only_store,
    read_provider_run_contract,
    read_run,
    read_stage_artifact,
    read_v2_artifact,
)
from v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_FINGERPRINT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_LEGACY_FINGERPRINT_KEY,
    V2ProductionFingerprint,
    V2ProductionPipelineResult,
    V2ProductionState,
    build_v2_run_diagnostics_or_empty,
    configured_v2_providers,
    infer_v2_stage,
    run_v2_production_pipeline,
    v2_cancellation_requested,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIVE_DB = PROJECT_ROOT / ".researchassistant" / "live-runs.sqlite3"
LEGACY_LIVE_RESEARCH_CONTROLS = ResearchControls(
    discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX)
)

LiveClassification = Literal[
    "starting",
    "running",
    "released",
    "blocked",
    "failed",
    "cancelled",
    "configuration_error",
    "invalid_input",
    "duplicate_active",
]

_MAX_EARLY_RESULTS = 32


def contract_controls(policy_identity: str) -> ResearchControls:
    """Recover immutable controls persisted in the canonical provider contract."""
    return ResearchControls.from_policy_identity(policy_identity)


def _read_first_v2_artifact(
    db_path: str | Path | Connection,
    run_id: UUID,
    artifact_keys: tuple[str, ...],
) -> V2PersistedArtifact:
    """Read the newest key first while preserving access to historical v2 artifacts."""
    for artifact_key in artifact_keys:
        try:
            return read_v2_artifact(db_path, run_id, artifact_key)
        except KeyError:
            continue
    raise KeyError(f"none of the v2 artifacts exist for run {run_id}: {artifact_keys}")


class LiveRunRequest(StrictModel):
    raw_claim: str = Field(min_length=1)
    db_path: str = Field(min_length=1)
    run_id: UUID | None = None
    max_tokens: int = Field(ge=1, le=500_000)
    max_cost_usd: Decimal = Field(default=Decimal("0.20"), gt=0, le=Decimal("1.00"))
    max_llm_calls: int = Field(default=160, ge=1, le=160)
    research_controls: ResearchControls = LEGACY_LIVE_RESEARCH_CONTROLS
    directions: ResearchDirections = ResearchDirections()
    crossref_enabled: bool = False

    @field_validator("raw_claim")
    @classmethod
    def validate_exact_claim(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("claim must not contain leading or trailing whitespace")
        return value

    @field_validator("db_path")
    @classmethod
    def validate_database_path(cls, value: str) -> str:
        path = Path(value).expanduser().resolve()
        if path.exists() and not path.is_file():
            raise ValueError("database location must be a file")
        if not path.parent.is_dir():
            raise ValueError("database parent directory does not exist")
        if not os.access(path.parent, os.W_OK):
            raise ValueError("database parent directory is not writable")
        if path.exists() and path.stat().st_size > 0:
            with path.open("rb") as handle:
                if handle.read(16) != b"SQLite format 3\x00":
                    raise ValueError("existing database location is not a SQLite file")
        return str(path)


class ResearchProgress(StrictModel):
    stance: Literal["supporting", "opposing"]
    status: str = Field(min_length=1)
    model_attempts: int = Field(ge=0)
    retrieval_attempts: int = Field(ge=0)
    usable_snapshots: int = Field(ge=0)
    candidates: int = Field(ge=0)


class LiveRunSnapshot(StrictModel):
    run_id: UUID
    db_path: str = Field(min_length=1)
    raw_claim: str = Field(min_length=1)
    classification: LiveClassification
    exit_code: int | None = None
    stage: str = Field(min_length=1)
    latest_checkpoint: str | None = None
    completed_checkpoints: int = Field(default=0, ge=0)
    total_checkpoints: int = Field(default=5, ge=1)
    current_research_round: int = Field(default=1, ge=1, le=3)
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: str = Field(min_length=1)
    diagnostic_component: str = Field(min_length=1)
    model_calls_used: int = Field(ge=0)
    retrieval_attempts_used: int = Field(ge=0)
    total_tokens: int | None = Field(default=0, ge=0)
    total_cost_usd: ExactUSD | None = Decimal("0")
    known_token_subtotal: int = Field(default=0, ge=0)
    known_cost_subtotal_usd: ExactUSD = Decimal("0")
    token_usage_complete: bool = True
    cost_usage_complete: bool = True
    conservative_reserved_tokens: int | None = Field(default=0, ge=0)
    conservative_reserved_cost_usd: ExactUSD | None = Decimal("0")
    supporting: ResearchProgress
    opposing: ResearchProgress
    validation_errors: tuple[str, ...] = ()
    final_brief: str | None = None
    rendered_brief_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_identity: str | None = None
    model_identity: str | None = None
    fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    research_controls: ResearchControls = DEFAULT_RESEARCH_CONTROLS
    v2_diagnostics: V2RunDiagnostics | None = None


class LiveHistoryItem(StrictModel):
    run_id: UUID
    raw_claim: str = Field(min_length=1)
    status: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    completed_at: str | None = None


class DiscoveryScoreBreakdown(StrictModel):
    relevance: int = Field(ge=0, le=35)
    intent_match: int = Field(ge=0, le=20)
    directness: int = Field(ge=0, le=15)
    metadata_completeness: int = Field(ge=0, le=10)
    likely_accessibility: int = Field(ge=0, le=10)
    source_novelty: int = Field(ge=0, le=10)
    penalties: int = Field(ge=-45, le=0)


class AcquiredSourceScoreBreakdown(StrictModel):
    readability: int = Field(ge=0, le=25)
    claim_term_coverage: int = Field(ge=0, le=35)
    document_specificity: int = Field(ge=0, le=25)
    evidence_language: int = Field(ge=0, le=15)
    penalties: int = Field(ge=-20, le=0)


class ResearchTrailItem(StrictModel):
    research_round: int = Field(ge=1, le=3)
    stance: Literal["supporting", "opposing"]
    provider: DiscoveryProvider
    intent: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    title: str
    url: str = Field(min_length=1)
    score: int | None = Field(default=None, ge=0, le=100)
    decision: Literal["selected", "deferred", "discarded"]
    selection_rank: int | None = Field(default=None, ge=1, le=20)
    breakdown: DiscoveryScoreBreakdown | None = None
    acquired_score: int | None = Field(default=None, ge=0, le=100)
    extraction_rank: int | None = Field(default=None, ge=1, le=25)
    acquired_breakdown: AcquiredSourceScoreBreakdown | None = None
    acquisition_state: Literal["acquired", "attempted", "not_attempted"] | None = None


class ResearchTrail(StrictModel):
    run_id: UUID
    items: tuple[ResearchTrailItem, ...]


class LiveStartResult(StrictModel):
    started: bool
    run_id: UUID
    classification: LiveClassification
    message: str = Field(min_length=1)


class _DatabaseLock:
    def __init__(self, db_path: Path) -> None:
        self.path = db_path.with_name(f"{db_path.name}.mvp5.lock")
        self.handle: IO[str] | None = None

    def acquire(self) -> bool:
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            return False
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None


class _ActiveRun:
    def __init__(self, future: Future[LiveRunSnapshot], database_lock: _DatabaseLock) -> None:
        self.future = future
        self.database_lock = database_lock


class LiveResearchController:
    """Keep local website requests responsive while SQLite remains authoritative."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str],
        runner: Callable[..., ProviderPipelineResult] | None = None,
        inspector: Callable[..., ProviderPipelineResult] = inspect_provider_run,
        max_workers: int = 2,
    ) -> None:
        self._environment = environment
        self._legacy_runner = runner
        self._inspector = inspector
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mvp5-live")
        self._lock = Lock()
        self._active: dict[tuple[str, UUID], _ActiveRun] = {}
        self._early_results: dict[tuple[str, UUID], LiveRunSnapshot] = {}

    def configuration_message(
        self,
        *,
        discovery_providers: tuple[DiscoveryProvider, ...] | None = None,
    ) -> str | None:
        selected_providers = (
            discovery_providers
            if discovery_providers is not None
            else DEFAULT_RESEARCH_CONTROLS.discovery_providers
        )
        try:
            if self._legacy_runner is None:
                V2ProductionFactoryConfig.from_environment(
                    self._environment,
                    repository_revision=repository_identity(),
                    discovery_providers=selected_providers,
                )
            else:
                MimoProviderFactoryConfig.from_environment(
                    self._environment,
                    repository_revision=repository_identity(),
                )
        except Exception as exc:
            return self._redact(exc)
        return None

    def start(self, request: LiveRunRequest) -> LiveStartResult:
        run_id = request.run_id or uuid4()
        db_path = Path(request.db_path).resolve()
        key = (str(db_path), run_id)
        with self._lock:
            active = self._active.get(key)
            if active is not None and not active.future.done():
                return LiveStartResult(
                    started=False,
                    run_id=run_id,
                    classification="duplicate_active",
                    message=(
                        "This persisted run is already active; reconnected without "
                        "starting a worker."
                    ),
                )
            database_active = any(
                active_key[0] == str(db_path) and not active_run.future.done()
                for active_key, active_run in self._active.items()
            )
            if database_active:
                return LiveStartResult(
                    started=False,
                    run_id=run_id,
                    classification="duplicate_active",
                    message=(
                        "This SQLite database already has an active research run. "
                        "Wait for it to finish or use a different database file."
                    ),
                )
        try:
            wigolo = WigoloConfig(
                base_url=self._environment.get("WIGOLO_BASE_URL", "http://127.0.0.1:8000")
            )
            if self._legacy_runner is None:
                factory_config: MimoProviderFactoryConfig | V2ProductionFactoryConfig = (
                    V2ProductionFactoryConfig.from_environment(
                        self._environment,
                        repository_revision=repository_identity(),
                        discovery_providers=request.research_controls.discovery_providers,
                        wigolo=wigolo,
                        ceilings=V2RunCeilings(
                            max_physical_calls=request.max_llm_calls,
                            max_total_tokens=request.max_tokens,
                            max_total_cost_usd=request.max_cost_usd,
                        ),
                        crossref_enabled=request.crossref_enabled,
                    )
                )
            else:
                factory_config = MimoProviderFactoryConfig.from_environment(
                    self._environment,
                    repository_revision=repository_identity(),
                    wigolo=wigolo,
                    ceilings=RunCeilings(
                        max_tokens=request.max_tokens,
                        max_cost_usd=request.max_cost_usd,
                        max_llm_calls=request.max_llm_calls,
                    ),
                    research_controls=request.research_controls,
                )
        except Exception as exc:
            snapshot = self._early_snapshot(
                request,
                run_id,
                "configuration_error",
                CLIExitCode.CONFIGURATION_ERROR,
                self._redact(exc),
            )
            with self._lock:
                self._remember_early_result_locked(key, snapshot)
            return LiveStartResult(
                started=False,
                run_id=run_id,
                classification="configuration_error",
                message=snapshot.message,
            )

        database_lock = _DatabaseLock(db_path)
        if not database_lock.acquire():
            return LiveStartResult(
                started=False,
                run_id=run_id,
                classification="duplicate_active",
                message=(
                    "Another application process owns this database worker lock. "
                    "Use inspection to reconnect; no duplicate worker was started."
                ),
            )
        future = self._executor.submit(
            self._run,
            request,
            run_id,
            factory_config,
            database_lock,
        )
        with self._lock:
            self._active[key] = _ActiveRun(future, database_lock)
            self._early_results.pop(key, None)
        future.add_done_callback(
            lambda completed_future: self._evict_completed_run(key, completed_future)
        )
        return LiveStartResult(
            started=True,
            run_id=run_id,
            classification="starting",
            message="Research worker started. Authoritative progress will appear from SQLite.",
        )

    def snapshot(self, db_path: str | Path, run_id: UUID) -> LiveRunSnapshot:
        resolved = str(Path(db_path).resolve())
        key = (resolved, run_id)
        with self._lock:
            active = self._active.get(key)
            early = self._early_results.pop(key, None)
        if Path(resolved).is_file():
            try:
                artifact = _read_first_v2_artifact(
                    resolved,
                    run_id,
                    (V2_PRODUCTION_ARTIFACT_KEY, V2_PRODUCTION_LEGACY_ARTIFACT_KEY),
                )
                return self._snapshot_from_v2_result(
                    V2ProductionPipelineResult.model_validate_json(artifact.payload_json)
                )
            except KeyError:
                pass
            v2_providers = configured_v2_providers(resolved, run_id)
            if v2_providers:
                try:
                    return self._snapshot_from_v2_progress(resolved, run_id, v2_providers)
                except KeyError:
                    pass
            try:
                result = self._inspector(resolved, run_id)
                return self._snapshot_from_result(result)
            except KeyError:
                pass
            except Exception as exc:
                if active is None or active.future.done():
                    return self._early_snapshot_from_values(
                        resolved,
                        run_id,
                        "Run inspection failed",
                        "failed",
                        CLIExitCode.FAILED,
                        self._redact(exc),
                    )
        if active is not None:
            if active.future.done():
                return active.future.result()
            return self._early_snapshot_from_values(
                resolved,
                run_id,
                "Awaiting persisted run manifest",
                "starting",
                None,
                "Worker is starting; no provider call is claimed until persistence records it.",
            )
        if early is not None:
            return early
        raise KeyError(f"run {run_id} not found")

    def _evict_completed_run(self, key: tuple[str, UUID], future: Future[LiveRunSnapshot]) -> None:
        """Release completed worker state while preserving only unpersisted failures."""
        try:
            snapshot = future.result()
        except Exception:
            snapshot = None
        with self._lock:
            active = self._active.get(key)
            if active is None or active.future is not future:
                return
            del self._active[key]
            if snapshot is not None and not Path(snapshot.db_path).is_file():
                self._remember_early_result_locked(key, snapshot)

    def _remember_early_result_locked(
        self, key: tuple[str, UUID], snapshot: LiveRunSnapshot
    ) -> None:
        """Keep a bounded one-shot cache for results produced before SQLite persistence."""
        self._early_results.pop(key, None)
        self._early_results[key] = snapshot
        while len(self._early_results) > _MAX_EARLY_RESULTS:
            oldest_key = next(iter(self._early_results))
            del self._early_results[oldest_key]

    def cancel(self, db_path: str | Path, run_id: UUID) -> str:
        try:
            request_run_cancellation(
                db_path,
                run_id,
                reason="cancellation requested from the local live website",
            )
        except Exception as exc:
            raise ValueError(self._redact(exc)) from exc
        return (
            "Cancellation persisted. An active provider request may continue to its deadline; "
            "no new call starts after cancellation is observed."
        )

    def history(self, db_path: str | Path, *, limit: int = 100) -> tuple[LiveHistoryItem, ...]:
        path = Path(db_path).resolve()
        if not path.is_file():
            return ()
        with open_read_only_store(path) as store:
            manifests = list_runs(store.connection, limit=limit)
            items: list[LiveHistoryItem] = []
            for manifest in manifests:
                try:
                    artifact = _read_first_v2_artifact(
                        store.connection,
                        manifest.run_id,
                        (V2_PRODUCTION_ARTIFACT_KEY, V2_PRODUCTION_LEGACY_ARTIFACT_KEY),
                    )
                    result = V2ProductionPipelineResult.model_validate_json(artifact.payload_json)
                except (KeyError, ValueError):
                    items.append(self._history_item(manifest))
                    continue
                items.append(
                    LiveHistoryItem(
                        run_id=manifest.run_id,
                        raw_claim=manifest.raw_claim,
                        status=manifest.status.value,
                        stage=infer_v2_stage(
                            str(path),
                            manifest.run_id,
                            result.current_stage,
                            result.final_output is not None,
                        ).value,
                        updated_at=manifest.updated_at.isoformat(),
                        completed_at=(
                            manifest.completed_at.isoformat() if manifest.completed_at else None
                        ),
                    )
                )
        return tuple(items)

    def research_trail(self, db_path: str | Path, run_id: UUID) -> ResearchTrail:
        path = Path(db_path).resolve()
        if not path.is_file():
            raise KeyError(f"run {run_id} not found")
        stage_keys = (
            (1, PHASE9_RESEARCHERS_ARTIFACT),
            (2, MVP10_TARGETED_RESEARCHERS_ARTIFACT),
            (2, MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT),
            (3, MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT),
        )
        items: list[ResearchTrailItem] = []
        with open_read_only_store(path) as store:
            # An existing database is not evidence that this particular run exists.
            read_run(store.connection, run_id)
            items.extend(self._v2_research_trail_items(store.connection, run_id))
            for research_round, artifact_key in stage_keys:
                try:
                    artifact = read_stage_artifact(store.connection, run_id, artifact_key)
                except KeyError:
                    continue
                if artifact.artifact_type != ResearcherPairResult.__name__:
                    continue
                pair = ResearcherPairResult.model_validate_json(artifact.payload_json)
                for side in (pair.supporting, pair.opposing):
                    if side.retrieval_batch is None:
                        continue
                    outcomes_by_rank = {
                        outcome.retrieval.search_rank: outcome
                        for outcome in side.retrieval_batch.outcomes
                    }
                    acquired_by_retrieval = {
                        item.retrieval_attempt_id: item
                        for item in side.retrieval_batch.acquired_source_ranking
                    }
                    for ranked in side.retrieval_batch.discovery_ranking:
                        components = ranked.components
                        outcome = (
                            outcomes_by_rank.get(ranked.selection_rank)
                            if ranked.selection_rank is not None
                            else None
                        )
                        acquired = (
                            acquired_by_retrieval.get(outcome.retrieval.retrieval_attempt_id)
                            if outcome is not None
                            else None
                        )
                        items.append(
                            ResearchTrailItem(
                                research_round=research_round,
                                stance=side.stance,
                                provider=ranked.query.provider.value,
                                intent=ranked.query.intent.value,
                                query_text=ranked.query.query_text,
                                title=ranked.result.title,
                                url=ranked.canonical_url,
                                score=ranked.score,
                                decision=ranked.decision.value,
                                selection_rank=ranked.selection_rank,
                                breakdown=DiscoveryScoreBreakdown(
                                    relevance=components.relevance,
                                    intent_match=components.intent_match,
                                    directness=components.directness,
                                    metadata_completeness=components.metadata_completeness,
                                    likely_accessibility=components.likely_accessibility,
                                    source_novelty=components.source_novelty,
                                    penalties=(
                                        components.generic_homepage_penalty
                                        + components.marketing_or_community_penalty
                                        + components.unrelated_title_penalty
                                    ),
                                ),
                                acquired_score=acquired.score if acquired is not None else None,
                                extraction_rank=(
                                    acquired.extraction_rank if acquired is not None else None
                                ),
                                acquired_breakdown=(
                                    AcquiredSourceScoreBreakdown(
                                        readability=acquired.components.readability,
                                        claim_term_coverage=(
                                            acquired.components.claim_term_coverage
                                        ),
                                        document_specificity=(
                                            acquired.components.document_specificity
                                        ),
                                        evidence_language=acquired.components.evidence_language,
                                        penalties=(
                                            acquired.components.generic_or_promotional_penalty
                                        ),
                                    )
                                    if acquired is not None
                                    else None
                                ),
                            )
                        )
        return ResearchTrail(
            run_id=run_id,
            items=tuple(
                sorted(
                    items,
                    key=lambda item: (
                        item.research_round,
                        item.stance,
                        item.score is None,
                        -(item.score or 0),
                        item.url,
                    ),
                )
            ),
        )

    def _v2_research_trail_items(
        self, connection: Connection, run_id: UUID
    ) -> tuple[ResearchTrailItem, ...]:
        """Project persisted v2 discovery and acquisition artifacts into the trail contract."""
        items: list[ResearchTrailItem] = []
        decision_map = {
            "retrieve": "selected",
            "maybe": "deferred",
            "skip": "discarded",
        }
        for research_round in (1, 2, 3):
            discovery_key = (
                V2_SCOUT_ARTIFACT_KEY
                if research_round == 1
                else f"phase-7-round-{research_round}-discovery-scout"
            )
            acquisition_key = (
                V2_ACQUISITION_PROBE_ARTIFACT_KEY
                if research_round == 1
                else f"phase-7-round-{research_round}-acquisition-probe"
            )
            try:
                artifact = read_v2_artifact(connection, run_id, discovery_key)
            except KeyError:
                continue
            discovery = V2DiscoveryScoutOutput.model_validate_json(artifact.payload_json)
            try:
                acquisition_artifact = read_v2_artifact(connection, run_id, acquisition_key)
            except KeyError:
                acquisition = None
            else:
                acquisition = V2AcquisitionProbeOutput.model_validate_json(
                    acquisition_artifact.payload_json
                )
            decisions = {
                scout_item.item_id: scout_item.decision.value
                for batch in discovery.scout_batches
                for scout_item in batch.items
            }
            cluster_by_item = {
                item_id: cluster.cluster_id
                for cluster in discovery.clusters
                for item_id in cluster.item_ids
            }
            acquired_clusters = (
                {source.cluster_id for source in acquisition.acquisitions}
                if acquisition is not None
                else set()
            )
            attempted_clusters = (
                {attempt.cluster_id for attempt in acquisition.attempts}
                if acquisition is not None
                else set()
            )
            for discovery_item in discovery.items:
                decision = decisions.get(discovery_item.item_id)
                if decision is None:
                    continue
                cluster_id = cluster_by_item.get(discovery_item.item_id)
                acquisition_state: Literal["acquired", "attempted", "not_attempted"]
                if cluster_id in acquired_clusters:
                    acquisition_state = "acquired"
                elif cluster_id in attempted_clusters:
                    acquisition_state = "attempted"
                else:
                    acquisition_state = "not_attempted"
                items.append(
                    ResearchTrailItem(
                        research_round=research_round,
                        stance=(
                            "supporting"
                            if discovery_item.direction.value == "support"
                            else "opposing"
                        ),
                        provider=discovery_item.provider,
                        intent="v2 discovery",
                        query_text=discovery_item.query_text,
                        title=discovery_item.title or "",
                        url=discovery_item.canonical_url,
                        decision=decision_map[decision],
                        acquisition_state=acquisition_state,
                    )
                )
        return tuple(items)

    def has_active_runs(self) -> bool:
        with self._lock:
            return any(not active.future.done() for active in self._active.values())

    def _run(
        self,
        request: LiveRunRequest,
        run_id: UUID,
        factory_config: MimoProviderFactoryConfig | V2ProductionFactoryConfig,
        database_lock: _DatabaseLock,
    ) -> LiveRunSnapshot:
        try:
            if isinstance(factory_config, V2ProductionFactoryConfig):
                bundle = build_v2_production_bundle(factory_config)
                result = run_v2_production_pipeline(
                    request.raw_claim,
                    db_path=request.db_path,
                    directions=request.directions,
                    discovery_providers=factory_config.discovery_providers,
                    search_providers=bundle.search_providers,
                    wigolo_provider=bundle.wigolo,
                    firecrawl_provider=bundle.firecrawl,
                    crossref_resolver=bundle.crossref_resolver,
                    llm_provider=bundle.llm,
                    routing_config=factory_config.routing,
                    ceilings=factory_config.ceilings,
                    run_id=run_id,
                    provider_policy_fingerprint=(factory_config.semantic_fingerprint_sha256()),
                    cancellation_requested=lambda: v2_cancellation_requested(
                        request.db_path, run_id
                    ),
                )
                return self._snapshot_from_v2_result(result)
            if self._legacy_runner is None:
                raise TypeError("legacy factory cannot be used by the fresh-v2 runner")
            legacy_result = self._legacy_runner(
                request.raw_claim,
                db_path=request.db_path,
                factory_config=factory_config,
                run_id=run_id,
                research_controls=request.research_controls,
            )
            return self._snapshot_from_result(legacy_result)
        except ClaimMismatchError as exc:
            return self._early_snapshot(
                request, run_id, "invalid_input", CLIExitCode.INVALID_INPUT, self._redact(exc)
            )
        except FingerprintMismatchError as exc:
            return self._early_snapshot(
                request,
                run_id,
                "configuration_error",
                CLIExitCode.CONFIGURATION_ERROR,
                self._redact(exc),
            )
        except (ProviderConfigurationError, TypeError) as exc:
            return self._early_snapshot(
                request,
                run_id,
                "configuration_error",
                CLIExitCode.CONFIGURATION_ERROR,
                self._redact(exc),
            )
        except ValueError as exc:
            return self._early_snapshot(
                request, run_id, "invalid_input", CLIExitCode.INVALID_INPUT, self._redact(exc)
            )
        except Exception as exc:
            return self._early_snapshot(
                request,
                run_id,
                "failed",
                CLIExitCode.FAILED,
                f"Run failed before a terminal result: {self._redact(exc)}",
            )
        finally:
            database_lock.release()

    def _snapshot_from_result(self, result: ProviderPipelineResult) -> LiveRunSnapshot:
        supporting = _research_progress(result, "supporting")
        opposing = _research_progress(result, "opposing")
        validation_errors = ()
        if result.validation_result is not None:
            validation_errors = tuple(
                f"{error.code.value} at {error.location}: {error.message}"
                for error in result.validation_result.errors
            )
        contract = None
        try:
            with open_read_only_store(result.db_path) as store:
                contract = read_provider_run_contract(store.connection, result.run_id)
        except KeyError:
            pass
        classification = result.status.value
        checkpoint = result.checkpoints[-1].stage_key if result.checkpoints else None
        exit_code = exit_code_for_status(result.status)
        current_round, progress_percent = _research_round_and_progress(result)
        return LiveRunSnapshot(
            run_id=result.run_id,
            db_path=result.db_path,
            raw_claim=result.raw_claim,
            classification=classification,
            exit_code=int(exit_code) if exit_code is not None else None,
            stage=result.current_stage.value,
            latest_checkpoint=checkpoint,
            completed_checkpoints=sum(
                checkpoint.status.value in {"completed", "blocked"}
                for checkpoint in result.checkpoints
            ),
            total_checkpoints=5,
            current_research_round=current_round,
            progress_percent=progress_percent,
            message=_result_message(result),
            diagnostic_component=_diagnostic_component(result),
            model_calls_used=result.model_calls_used,
            retrieval_attempts_used=result.retrieval_attempts_used,
            total_tokens=result.total_tokens,
            total_cost_usd=result.total_cost_usd,
            known_token_subtotal=result.usage_accounting.known_token_subtotal,
            known_cost_subtotal_usd=result.usage_accounting.known_cost_subtotal_usd,
            token_usage_complete=result.usage_accounting.token_complete,
            cost_usage_complete=result.usage_accounting.cost_complete,
            conservative_reserved_tokens=(result.usage_accounting.conservative_reserved_tokens),
            conservative_reserved_cost_usd=(result.usage_accounting.conservative_reserved_cost_usd),
            supporting=supporting,
            opposing=opposing,
            validation_errors=validation_errors,
            final_brief=result.final_brief,
            rendered_brief_hash=result.rendered_brief_hash,
            provider_identity=contract.provider_identity if contract is not None else None,
            model_identity=contract.model_identity if contract is not None else None,
            fingerprint=contract.fingerprint_sha256 if contract is not None else None,
            research_controls=(
                contract_controls(contract.policy_identity)
                if contract is not None
                else DEFAULT_RESEARCH_CONTROLS
            ),
        )

    def _snapshot_from_v2_progress(
        self,
        db_path: str,
        run_id: UUID,
        providers: tuple[DiscoveryProvider, ...],
    ) -> LiveRunSnapshot:
        manifest = read_run(db_path, run_id)
        directions = _read_v2_directions(db_path, run_id)
        diagnostics = build_v2_run_diagnostics_or_empty(db_path, run_id, providers)
        budget = _read_v2_budget_snapshot(db_path, run_id)
        stage = infer_v2_stage(db_path, run_id, manifest.current_stage, False)
        current_round = _v2_current_round(db_path, run_id)
        supporting, opposing = _read_v2_directional_progress(
            db_path,
            run_id,
            directions,
            manifest.status,
        )
        contract = None
        try:
            contract = read_provider_run_contract(db_path, run_id)
        except KeyError:
            pass
        classification: LiveClassification = {
            RunStatus.PLANNED: "starting",
            RunStatus.RUNNING: "running",
            RunStatus.COMPLETED: "released",
            RunStatus.BLOCKED: "blocked",
            RunStatus.CANCELLED: "cancelled",
            RunStatus.FAILED: "failed",
        }[manifest.status]
        exit_code = CLIExitCode.RUNNING if manifest.status is RunStatus.RUNNING else None
        if manifest.status is RunStatus.FAILED:
            exit_code = CLIExitCode.FAILED
        elif manifest.status is RunStatus.BLOCKED:
            exit_code = CLIExitCode.BLOCKED
        elif manifest.status is RunStatus.CANCELLED:
            exit_code = CLIExitCode.CANCELLED
        elif manifest.status is RunStatus.COMPLETED:
            exit_code = CLIExitCode.RELEASED
        return LiveRunSnapshot(
            run_id=run_id,
            db_path=db_path,
            raw_claim=manifest.raw_claim,
            classification=classification,
            exit_code=int(exit_code) if exit_code is not None else None,
            stage=stage.value,
            latest_checkpoint=stage.value,
            completed_checkpoints=0,
            total_checkpoints=10,
            current_research_round=current_round,
            progress_percent=_v2_progress_percent(
                stage,
                current_round,
                diagnostics,
                budget,
                supporting,
                opposing,
            ),
            message=(
                f"Research is running in {stage.value}."
                if manifest.status is RunStatus.RUNNING
                else f"Research is {classification}."
            ),
            diagnostic_component="v2-production",
            model_calls_used=budget.physical_calls_used,
            retrieval_attempts_used=diagnostics.acquisition_attempts,
            total_tokens=budget.token_exposure,
            total_cost_usd=budget.cost_exposure_usd,
            known_token_subtotal=budget.token_exposure,
            known_cost_subtotal_usd=budget.cost_exposure_usd,
            token_usage_complete=False,
            cost_usage_complete=False,
            conservative_reserved_tokens=budget.token_exposure,
            conservative_reserved_cost_usd=budget.cost_exposure_usd,
            supporting=supporting,
            opposing=opposing,
            provider_identity=contract.provider_identity if contract is not None else None,
            model_identity=contract.model_identity if contract is not None else None,
            fingerprint=contract.fingerprint_sha256 if contract is not None else None,
            research_controls=ResearchControls(
                research_mode=(
                    ResearchMode.BALANCED if directions.challenge_enabled else ResearchMode.FOCUSED
                ),
                discovery_providers=providers,
            ),
        )

    def _snapshot_from_v2_result(
        self,
        result: V2ProductionPipelineResult,
    ) -> LiveRunSnapshot:
        output = result.final_output
        directions = output.directions if output is not None else ResearchDirections()
        sources = output.all_surviving_sources if output is not None else ()
        diagnostics = result.diagnostics
        if diagnostics is None:
            providers = configured_v2_providers(result.db_path, result.run_id)
            if providers:
                diagnostics = build_v2_run_diagnostics_or_empty(
                    result.db_path,
                    result.run_id,
                    providers,
                    final_output=output,
                )
        stage = infer_v2_stage(
            result.db_path,
            result.run_id,
            result.current_stage,
            output is not None,
        )
        classification: LiveClassification = result.state.value
        exit_code = {
            V2ProductionState.RELEASED: CLIExitCode.RELEASED,
            V2ProductionState.BLOCKED: CLIExitCode.BLOCKED,
            V2ProductionState.FAILED: CLIExitCode.FAILED,
            V2ProductionState.CANCELLED: CLIExitCode.CANCELLED,
        }[result.state]
        return LiveRunSnapshot(
            run_id=result.run_id,
            db_path=result.db_path,
            raw_claim=result.raw_claim,
            classification=classification,
            exit_code=int(exit_code),
            stage=stage.value,
            latest_checkpoint=V2_PRODUCTION_ARTIFACT_KEY,
            completed_checkpoints=10,
            total_checkpoints=10,
            current_research_round=(output.stopping.completed_rounds if output else 1),
            progress_percent=100,
            message=(
                "Research completed and passed release validation."
                if result.state is V2ProductionState.RELEASED
                else result.failure_reason or "Research stopped before release."
            ),
            diagnostic_component="v2-production",
            model_calls_used=result.budget.physical_calls_used,
            retrieval_attempts_used=(
                diagnostics.sources_acquired if diagnostics is not None else len(sources)
            ),
            total_tokens=result.budget.token_exposure,
            total_cost_usd=result.budget.cost_exposure_usd,
            known_token_subtotal=result.budget.token_exposure,
            known_cost_subtotal_usd=result.budget.cost_exposure_usd,
            token_usage_complete=True,
            cost_usage_complete=True,
            conservative_reserved_tokens=result.budget.token_exposure,
            conservative_reserved_cost_usd=result.budget.cost_exposure_usd,
            supporting=_v2_research_progress(sources, "supporting", directions.support_enabled),
            opposing=_v2_research_progress(sources, "opposing", directions.challenge_enabled),
            validation_errors=(
                tuple(error.message for error in output.release_validation.errors)
                if output is not None
                else ()
            ),
            final_brief=(render_v2_final_output(output) if output is not None else None),
            rendered_brief_hash=(
                output.release_validation.rendered_output_hash if output is not None else None
            ),
            research_controls=ResearchControls(
                research_mode=(
                    ResearchMode.BALANCED if directions.challenge_enabled else ResearchMode.FOCUSED
                ),
                discovery_providers=(
                    diagnostics.configured_providers
                    if diagnostics is not None
                    else DEFAULT_RESEARCH_CONTROLS.discovery_providers
                ),
            ),
            v2_diagnostics=diagnostics,
        )

    def _early_snapshot(
        self,
        request: LiveRunRequest,
        run_id: UUID,
        classification: LiveClassification,
        exit_code: CLIExitCode | None,
        message: str,
    ) -> LiveRunSnapshot:
        return self._early_snapshot_from_values(
            request.db_path,
            run_id,
            request.raw_claim,
            classification,
            exit_code,
            message,
        )

    @staticmethod
    def _early_snapshot_from_values(
        db_path: str,
        run_id: UUID,
        raw_claim: str,
        classification: LiveClassification,
        exit_code: CLIExitCode | None,
        message: str,
    ) -> LiveRunSnapshot:
        return LiveRunSnapshot(
            run_id=run_id,
            db_path=db_path,
            raw_claim=raw_claim,
            classification=classification,
            exit_code=int(exit_code) if exit_code is not None else None,
            stage="configuration" if classification == "configuration_error" else "startup",
            message=message,
            diagnostic_component=(
                "configuration" if classification == "configuration_error" else "startup"
            ),
            model_calls_used=0,
            retrieval_attempts_used=0,
            supporting=_empty_progress("supporting"),
            opposing=_empty_progress("opposing"),
        )

    @staticmethod
    def _history_item(manifest: RunManifest) -> LiveHistoryItem:
        return LiveHistoryItem(
            run_id=manifest.run_id,
            raw_claim=manifest.raw_claim,
            status=manifest.status.value,
            stage=manifest.current_stage.value,
            updated_at=manifest.updated_at.isoformat(),
            completed_at=manifest.completed_at.isoformat() if manifest.completed_at else None,
        )

    def _redact(self, value: object) -> str:
        return redact_text(
            value,
            secrets=tuple(
                self._environment.get(name, "")
                for name in (
                    "MIMO_API_KEY",
                    "LUNA_API_KEY",
                    "EXA_API_KEY",
                    "OPENALEX_API_KEY",
                    "SERPSEARCH_API_KEY",
                    "FIRECRAWL_API_KEY",
                )
            ),
        )


def exit_code_for_status(status: ProviderRunStatus) -> CLIExitCode:
    if status is ProviderRunStatus.RELEASED:
        return CLIExitCode.RELEASED
    if status is ProviderRunStatus.BLOCKED:
        return CLIExitCode.BLOCKED
    if status is ProviderRunStatus.FAILED:
        return CLIExitCode.FAILED
    if status is ProviderRunStatus.CANCELLED:
        return CLIExitCode.CANCELLED
    if status is ProviderRunStatus.RUNNING:
        return CLIExitCode.RUNNING
    raise ValueError(f"unsupported provider run status: {status!r}")


def prepare_default_database() -> Path:
    DEFAULT_LIVE_DB.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return DEFAULT_LIVE_DB


def _research_progress(
    result: ProviderPipelineResult,
    stance: Literal["supporting", "opposing"],
) -> ResearchProgress:
    if result.researcher_result is None:
        status = "running" if result.status is ProviderRunStatus.RUNNING else "not available"
        return ResearchProgress(
            stance=stance,
            status=status,
            model_attempts=0,
            retrieval_attempts=0,
            usable_snapshots=0,
            candidates=0,
        )
    side = getattr(result.researcher_result, stance)
    outcomes = side.retrieval_batch.outcomes if side.retrieval_batch is not None else ()
    usable = sum(1 for outcome in outcomes if outcome.snapshot_id is not None)
    stance_artifact_ids = {candidate.quote_block_id for candidate in side.candidates}
    if side.retrieval_batch is not None:
        stance_artifact_ids.update(
            snapshot.snapshot_id for snapshot in side.retrieval_batch.snapshots
        )
    attempts = sum(
        1
        for attempt in result.model_attempts
        if any(artifact_id in stance_artifact_ids for artifact_id in attempt.input_artifact_ids)
    )
    return ResearchProgress(
        stance=stance,
        status=side.status.value,
        model_attempts=attempts,
        retrieval_attempts=len(outcomes),
        usable_snapshots=usable,
        candidates=len(side.candidates),
    )


def _empty_progress(stance: Literal["supporting", "opposing"]) -> ResearchProgress:
    return ResearchProgress(
        stance=stance,
        status="not started",
        model_attempts=0,
        retrieval_attempts=0,
        usable_snapshots=0,
        candidates=0,
    )


def _v2_research_progress(
    sources: tuple[V2ResultSource, ...],
    stance: Literal["supporting", "opposing"],
    enabled: bool,
) -> ResearchProgress:
    direction = "support" if stance == "supporting" else "challenge"
    matching = tuple(source for source in sources if source.direction.value == direction)
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
    analyzed = sum(source.status in analyzed_statuses for source in matching)
    return ResearchProgress(
        stance=stance,
        status="completed" if enabled else "disabled",
        model_attempts=analyzed,
        retrieval_attempts=len(matching),
        usable_snapshots=len(matching),
        candidates=analyzed,
    )


def _read_v2_directions(db_path: str, run_id: UUID) -> ResearchDirections:
    try:
        artifact = _read_first_v2_artifact(
            db_path,
            run_id,
            (V2_PRODUCTION_FINGERPRINT_KEY, V2_PRODUCTION_LEGACY_FINGERPRINT_KEY),
        )
        fingerprint = V2ProductionFingerprint.model_validate_json(artifact.payload_json)
        payload = json.loads(fingerprint.canonical_payload_json)
        return ResearchDirections.model_validate(payload["directions"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ResearchDirections()


def _read_v2_budget_snapshot(db_path: str, run_id: UUID) -> V2BudgetSnapshot:
    ceilings = V2RunCeilings()
    try:
        artifact = _read_first_v2_artifact(
            db_path,
            run_id,
            (V2_PRODUCTION_FINGERPRINT_KEY, V2_PRODUCTION_LEGACY_FINGERPRINT_KEY),
        )
        fingerprint = V2ProductionFingerprint.model_validate_json(artifact.payload_json)
        payload = json.loads(fingerprint.canonical_payload_json)
        ceilings = V2RunCeilings.model_validate(payload["ceilings"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass

    starts: list[V2PhysicalCallStart] = []
    completions: dict[int, V2PhysicalCallCompletion] = {}
    for sequence in range(1, ceilings.max_physical_calls + 1):
        try:
            start_artifact = _read_first_v2_artifact(
                db_path,
                run_id,
                (
                    f"phase-13-physical-call-{sequence:03d}-start",
                    f"phase-12-physical-call-{sequence:03d}-start",
                ),
            )
        except KeyError:
            break
        start = V2PhysicalCallStart.model_validate_json(start_artifact.payload_json)
        starts.append(start)
        try:
            completion_artifact = _read_first_v2_artifact(
                db_path,
                run_id,
                (
                    f"phase-13-physical-call-{sequence:03d}-completion",
                    f"phase-12-physical-call-{sequence:03d}-completion",
                ),
            )
        except KeyError:
            continue
        completions[sequence] = V2PhysicalCallCompletion.model_validate_json(
            completion_artifact.payload_json
        )

    token_exposure = 0
    cost_exposure = Decimal("0")
    for start in starts:
        completion = completions.get(start.sequence)
        token_exposure += (
            completion.usage_tokens
            if completion is not None and completion.usage_tokens is not None
            else start.reserved_tokens
        )
        cost_exposure = add_usd(
            cost_exposure,
            (
                completion.usage_cost_usd
                if completion is not None and completion.usage_cost_usd is not None
                else start.reserved_cost_usd
            ),
        )
    return V2BudgetSnapshot(
        physical_calls_used=len(starts),
        token_exposure=token_exposure,
        cost_exposure_usd=cost_exposure,
        physical_calls_remaining=max(0, ceilings.max_physical_calls - len(starts)),
        tokens_remaining=max(0, ceilings.max_total_tokens - token_exposure),
        cost_remaining_usd=max(Decimal("0"), ceilings.max_total_cost_usd - cost_exposure),
    )


def _v2_current_round(db_path: str, run_id: UUID) -> int:
    for round_number in (3, 2):
        for suffix in ("search-results", "discovery-scout", "acquisition-probe"):
            try:
                read_v2_artifact(
                    db_path,
                    run_id,
                    f"phase-7-round-{round_number}-{suffix}",
                )
            except KeyError:
                continue
            return round_number
    return 1


def _read_v2_directional_progress(
    db_path: str,
    run_id: UUID,
    directions: ResearchDirections,
    status: RunStatus,
) -> tuple[ResearchProgress, ResearchProgress]:
    acquired: dict[ResearchDirection, int] = {
        ResearchDirection.SUPPORT: 0,
        ResearchDirection.CHALLENGE: 0,
    }
    survivors: dict[ResearchDirection, set[UUID]] = {
        ResearchDirection.SUPPORT: set(),
        ResearchDirection.CHALLENGE: set(),
    }
    for round_number in (1, 2, 3):
        artifact_key = (
            V2_ACQUISITION_PROBE_ARTIFACT_KEY
            if round_number == 1
            else f"phase-7-round-{round_number}-acquisition-probe"
        )
        try:
            artifact = read_v2_artifact(db_path, run_id, artifact_key)
        except KeyError:
            continue
        output = V2AcquisitionProbeOutput.model_validate_json(artifact.payload_json)
        for source in output.acquisitions:
            acquired[source.direction] += 1
        for survivor in output.survivors:
            survivors[survivor.direction].add(survivor.snapshot_id)

    survivor_ids: dict[ResearchDirection, tuple[UUID, ...]] = {
        ResearchDirection.SUPPORT: (),
        ResearchDirection.CHALLENGE: (),
    }
    try:
        queue_artifact = _read_first_v2_artifact(
            db_path,
            run_id,
            (V2_SOURCE_SELECTION_COMPLETION_KEY, V2_SOURCE_SELECTION_LEGACY_COMPLETION_KEY),
        )
    except KeyError:
        pass
    else:
        queue = V2SourceSelectionQueueResult.model_validate_json(queue_artifact.payload_json)
        survivor_ids = {
            direction: tuple(
                item.source_id for item in queue.input.survivors if item.direction is direction
            )
            for direction in (ResearchDirection.SUPPORT, ResearchDirection.CHALLENGE)
        }
    analyzed: dict[ResearchDirection, int] = {
        ResearchDirection.SUPPORT: 0,
        ResearchDirection.CHALLENGE: 0,
    }
    source_prefixes = (
        V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
        V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX,
        "phase-9-luna-evidence-analyst-source",
    )
    for direction, source_ids in survivor_ids.items():
        for source_id in source_ids:
            source_artifact = None
            for prefix in source_prefixes:
                try:
                    source_artifact = read_v2_artifact(
                        db_path,
                        run_id,
                        f"{prefix}-{source_id}",
                    )
                except KeyError:
                    continue
                break
            if source_artifact is None:
                continue
            source_result = V2EvidenceAnalystSourceResult.model_validate_json(
                source_artifact.payload_json
            )
            if source_result.state.value != "not_queued":
                analyzed[direction] += 1

    def build_progress(direction: ResearchDirection) -> ResearchProgress:
        enabled = directions.permits(direction)
        terminal = status is not RunStatus.RUNNING
        return ResearchProgress(
            stance="supporting" if direction is ResearchDirection.SUPPORT else "opposing",
            status=("disabled" if not enabled else "completed" if terminal else "running"),
            model_attempts=analyzed[direction],
            retrieval_attempts=acquired[direction],
            usable_snapshots=len(survivors[direction]),
            candidates=analyzed[direction],
        )

    return build_progress(ResearchDirection.SUPPORT), build_progress(ResearchDirection.CHALLENGE)


def _v2_progress_percent(
    stage: Stage,
    current_round: int,
    diagnostics: V2RunDiagnostics,
    budget: V2BudgetSnapshot,
    supporting: ResearchProgress,
    opposing: ResearchProgress,
) -> int:
    stage_value = stage.value
    base = {
        "claim_planner": 4,
        "discovery": 12,
        "acquisition": 25,
        "gap_analysis": 39,
        "adaptive_search": 50,
        "source_selection": 63,
        "deep_analysis": 70,
        "evidence_analyst": 70,
        "evidence_admission": 85,
        "review": 85,
        "statement_reviewer": 85,
        "claim_ledger": 87,
        "debate_synthesizer": 92,
        "synthesis": 92,
        "final_renderer_validator": 97,
    }.get(stage_value, 5)
    analyzed = supporting.candidates + opposing.candidates
    if stage_value in {"adaptive_search", "source_selection"}:
        activity = min(9, budget.physical_calls_used // 2)
        return min(69 if stage_value == "source_selection" else 61, base + activity)
    if stage_value in {"deep_analysis", "evidence_analyst"}:
        queued = max(1, diagnostics.sources_queued_for_analysis)
        return min(84, base + round(14 * min(1.0, analyzed / queued)))
    if stage_value in {"evidence_admission", "statement_reviewer", "claim_ledger"}:
        return min(90, base + min(3, diagnostics.approved_evidence_records))
    if current_round > 1:
        return min(87, base + (current_round - 1) * 2)
    return base


def _research_round_and_progress(result: ProviderPipelineResult) -> tuple[int, int]:
    checkpoint_keys = {checkpoint.stage_key for checkpoint in result.checkpoints}
    if any(key.startswith("mvp11-round-three") for key in checkpoint_keys):
        current_round = 3
    elif any(key.startswith("mvp11-round-two") for key in checkpoint_keys):
        current_round = 2
    else:
        current_round = 1
    if result.status is not ProviderRunStatus.RUNNING:
        return current_round, 100
    if result.current_stage.value in {"debate_synthesizer", "final_renderer_validator"}:
        return current_round, 88 if result.current_stage.value == "debate_synthesizer" else 96
    stage_progress = {
        "claim_planner": 10,
        "supporting_researcher": 28,
        "opposing_researcher": 34,
        "evidence_analyst": 52,
        "evidence_admission": 58,
        "statement_reviewer": 58,
        "claim_ledger": 62,
    }.get(result.current_stage.value, 5)
    round_floor = {1: 0, 2: 62, 3: 76}[current_round]
    round_span = {1: 1.0, 2: 0.18, 3: 0.12}[current_round]
    return current_round, min(
        87, max(round_floor, round_floor + round(stage_progress * round_span))
    )


def _result_message(result: ProviderPipelineResult) -> str:
    if result.status is ProviderRunStatus.RELEASED:
        return "Released after deterministic validation. Human review is still required."
    if result.status is ProviderRunStatus.BLOCKED:
        return "Blocked by the deterministic final validator; no brief or hash was released."
    if result.status is ProviderRunStatus.CANCELLED:
        return (
            f"Cancelled at the cooperative {result.current_stage.value} boundary. "
            "An already active request was allowed to finish or reach its deadline."
        )
    if result.status is ProviderRunStatus.FAILED:
        return f"Failed in {result.current_stage.value}: {result.failure_reason}"
    if result.status is ProviderRunStatus.RUNNING:
        return f"Research is running in {result.current_stage.value}."
    raise ValueError(f"unsupported provider run status: {result.status!r}")


def _diagnostic_component(result: ProviderPipelineResult) -> str:
    if result.status is ProviderRunStatus.BLOCKED:
        return "validation"
    reason = (result.failure_reason or "").lower()
    if "searxng" in reason:
        return "searxng"
    if "wigolo" in reason:
        return "wigolo"
    if any(term in reason for term in ("retrieval", "acquisition", "source", "scrape")):
        return "retrieval"
    if any(term in reason for term in ("mimo", "xiaomi", "model", "llm")):
        return "mimo"
    if "validat" in reason:
        return "validation"
    return result.current_stage.value
