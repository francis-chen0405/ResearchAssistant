"""Application controller for configuration, run workers, locking, and cancellation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from sqlite3 import Connection
from threading import Event, Lock
from uuid import UUID, uuid4

from researchassistant.api.live_contracts import (
    LEGACY_LIVE_RESEARCH_CONTROLS,
    AcquiredSourceScoreBreakdown,
    DiscoveryScoreBreakdown,
    LiveAttemptDiagnostic,
    LiveClassification,
    LiveHistoryItem,
    LiveRunRequest,
    LiveRunSnapshot,
    LiveStartResult,
    ResearchProgress,
    ResearchTrail,
    ResearchTrailItem,
)
from researchassistant.api.live_history import history as read_history
from researchassistant.api.live_history import research_trail as read_research_trail
from researchassistant.api.live_lifecycle import LifecycleCoordinator
from researchassistant.api.live_progress import (
    _diagnostic_component as _diagnostic_component,
)
from researchassistant.api.live_progress import (
    _empty_progress as _empty_progress,
)
from researchassistant.api.live_progress import (
    _read_first_v2_artifact as _read_first_v2_artifact,
)
from researchassistant.api.live_progress import (
    _read_v2_budget_snapshot as _read_v2_budget_snapshot,
)
from researchassistant.api.live_progress import (
    _read_v2_directional_progress as _read_v2_directional_progress,
)
from researchassistant.api.live_progress import (
    _read_v2_directions as _read_v2_directions,
)
from researchassistant.api.live_progress import (
    _read_v2_usage_summary as _read_v2_usage_summary,
)
from researchassistant.api.live_progress import (
    _research_progress as _research_progress,
)
from researchassistant.api.live_progress import (
    _research_round_and_progress as _research_round_and_progress,
)
from researchassistant.api.live_progress import (
    _result_message as _result_message,
)
from researchassistant.api.live_progress import (
    _v2_current_round as _v2_current_round,
)
from researchassistant.api.live_progress import (
    _v2_progress_percent as _v2_progress_percent,
)
from researchassistant.api.live_progress import (
    _v2_research_progress as _v2_research_progress,
)
from researchassistant.api.live_progress import (
    exit_code_for_status as exit_code_for_status,
)
from researchassistant.api.live_progress import (
    snapshot_from_v2_progress,
    snapshot_from_v2_result,
)
from researchassistant.api.profile_preflight import check_start_reservation
from researchassistant.api.security import redact_text
from researchassistant.common.pipeline_errors import ClaimMismatchError, FingerprintMismatchError
from researchassistant.contracts.models import (
    DEFAULT_RESEARCH_CONTROLS,
    DiscoveryProvider,
    ResearchControls,
)
from researchassistant.contracts.provider_results import ProviderPipelineResult
from researchassistant.platform_support.desktop_paths import application_data_dir
from researchassistant.platform_support.file_lock import FileLock
from researchassistant.providers.config import ProviderConfigurationError, RunCeilings, WigoloConfig
from researchassistant.providers.mimo_factory import MimoProviderFactoryConfig
from researchassistant.providers.model_choices import (
    CONFIGURABLE_PROFILE_ID,
    DEFAULT_STAGE_MODELS,
    StageModelSelections,
)
from researchassistant.providers.model_profiles import ProfileId, profile_environment
from researchassistant.providers.v2_budget import (
    V2RunCeilings,
)
from researchassistant.providers.v2_factory import (
    V2ProductionFactoryConfig,
    build_v2_production_bundle,
)
from researchassistant.research.pipeline_compatibility import LegacyPipelineRunner
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    configured_v2_providers,
    run_v2_production_pipeline,
    v2_cancellation_requested,
)
from researchassistant.runtime.application_runtime import CLIExitCode, repository_identity
from researchassistant.storage.provider_history import inspect_provider_run
from researchassistant.storage.run_cancellation import request_run_cancellation
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    DatabaseReader,
    open_read_only_store,
    read_provider_run_contract,
    read_run,
)

DEFAULT_LIVE_DB = application_data_dir() / "live-runs.sqlite3"


def contract_controls(policy_identity: str) -> ResearchControls:
    """Recover immutable controls persisted in the canonical provider contract."""
    return ResearchControls.from_policy_identity(policy_identity)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _DatabaseLock(FileLock):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path.with_name(f"{db_path.name}.mvp5.lock"))


class _ActiveRun:
    def __init__(self, future: Future[LiveRunSnapshot], database_lock: _DatabaseLock) -> None:
        self.future = future
        self.database_lock = database_lock


__all__ = [
    "LEGACY_LIVE_RESEARCH_CONTROLS",
    "AcquiredSourceScoreBreakdown",
    "DiscoveryScoreBreakdown",
    "LiveClassification",
    "LiveHistoryItem",
    "LiveRunRequest",
    "LiveRunSnapshot",
    "LiveStartResult",
    "ResearchProgress",
    "ResearchTrail",
    "ResearchTrailItem",
    "LiveResearchController",
    "exit_code_for_status",
]

_MAX_EARLY_RESULTS = 32


class LiveResearchController:
    """Own fresh-v2 workers and snapshots, with explicit legacy compatibility injection.

    ``runner`` remains an alias for older callers; new compatibility callers should
    pass ``legacy_runner``. Ordinary production construction supplies neither.
    """

    def __init__(
        self,
        *,
        environment: Mapping[str, str],
        legacy_runner: LegacyPipelineRunner | None = None,
        runner: LegacyPipelineRunner | None = None,
        inspector: Callable[..., ProviderPipelineResult] = inspect_provider_run,
        max_workers: int = 2,
    ) -> None:
        if legacy_runner is not None and runner is not None:
            raise TypeError("pass either legacy_runner or its runner alias, not both")
        self._shutdown_requested = Event()
        self.lifecycle = LifecycleCoordinator()
        self._environment = environment
        self._legacy_runner = legacy_runner if legacy_runner is not None else runner
        self._inspector = inspector
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mvp5-live")
        self._lock = Lock()
        self._active: dict[tuple[str, UUID], _ActiveRun] = {}
        self._early_results: dict[tuple[str, UUID], LiveRunSnapshot] = {}

    def configuration_message(
        self,
        *,
        discovery_providers: tuple[DiscoveryProvider, ...] | None = None,
        model_profile: ProfileId | None = None,
        stage_models: StageModelSelections = DEFAULT_STAGE_MODELS,
    ) -> str | None:
        selected_providers = (
            discovery_providers
            if discovery_providers is not None
            else DEFAULT_RESEARCH_CONTROLS.discovery_providers
        )
        try:
            selected_profile = model_profile
            selected_stage_models = (
                stage_models if selected_profile == CONFIGURABLE_PROFILE_ID else None
            )
            configured_environment = profile_environment(
                self._environment,
                selected_profile,
                stage_models=selected_stage_models,
            )
            if self._legacy_runner is None:
                V2ProductionFactoryConfig.from_environment(
                    configured_environment,
                    repository_revision=repository_identity(),
                    discovery_providers=selected_providers,
                    stage_models=selected_stage_models,
                )
            else:
                MimoProviderFactoryConfig.from_environment(
                    configured_environment,
                    repository_revision=repository_identity(),
                )
        except Exception as exc:
            return self._redact(exc)
        return None

    def start(self, request: LiveRunRequest) -> LiveStartResult:
        # Direct callers and HTTP admissions share the same lifecycle reservation.
        # No lifecycle mutex is held across preflight, file I/O, or provider work.
        with self.lifecycle.admission():
            return self._start(request)

    def _start(self, request: LiveRunRequest) -> LiveStartResult:
        if self._legacy_runner is not None:
            controls = request.research_controls.model_dump(mode="python")
            for name in ("metadata_depth", "seed_expansion_enabled", "scholarly_search_mode"):
                controls.pop(name, None)
            request = request.model_copy(
                update={"research_controls": ResearchControls.model_validate(controls)}
            )
        if self._shutdown_requested.is_set():
            raise ValueError("Application is shutting down")
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
            selected_stage_models = (
                request.stage_models if request.model_profile == CONFIGURABLE_PROFILE_ID else None
            )
            run_environment = profile_environment(
                self._environment,
                request.model_profile,
                stage_models=selected_stage_models,
            )
            if request.model_profile is not None and self._legacy_runner is None:
                check_start_reservation(request, self._environment)
            wigolo = WigoloConfig(
                base_url=run_environment.get("WIGOLO_BASE_URL", "http://127.0.0.1:8000")
            )
            if self._legacy_runner is None:
                factory_config: MimoProviderFactoryConfig | V2ProductionFactoryConfig = (
                    V2ProductionFactoryConfig.from_environment(
                        run_environment,
                        repository_revision=repository_identity(),
                        discovery_providers=request.research_controls.discovery_providers,
                        stage_models=selected_stage_models,
                        wigolo=wigolo,
                        ceilings=V2RunCeilings(
                            max_physical_calls=request.max_llm_calls,
                            max_total_tokens=request.max_tokens,
                            max_total_cost_usd=request.max_cost_usd,
                        ),
                        crossref_enabled=request.crossref_enabled,
                        research_controls=request.research_controls,
                    )
                )
            else:
                factory_config = MimoProviderFactoryConfig.from_environment(
                    run_environment,
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
        with self._lock:
            if self._shutdown_requested.is_set():
                database_lock.release()
                raise ValueError("Application is shutting down")
            try:
                future = self._executor.submit(
                    self._run,
                    request,
                    run_id,
                    factory_config,
                    database_lock,
                )
            except BaseException:
                database_lock.release()
                raise
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
        for projection_read in range(2):
            persisted = self._persisted_snapshot(resolved, run_id)
            # Resolve ownership and the latest outcome AFTER the read. A completed
            # future is visible even before its eviction callback acquires the lock.
            with self._lock:
                active = self._active.get(key)
                early = self._early_results.get(key)
                worker_active = active is not None and not active.future.done()
                if active is not None and not worker_active:
                    early = active.future.result()
                if (
                    projection_read == 0
                    and persisted is not None
                    and persisted.classification in {"starting", "running"}
                    and not worker_active
                    and early is not None
                    and early.stage not in {"startup", "configuration"}
                    and early.classification in {"released", "blocked", "failed", "cancelled"}
                ):
                    # A terminal commit overtook the pinned read. Revalidate and
                    # inspect again; cached results never substitute for the file.
                    continue
                if persisted is not None:
                    diagnostic = None
                    if (
                        not worker_active
                        and early is not None
                        and early.stage in {"startup", "configuration"}
                        and early.classification
                        in {"invalid_input", "configuration_error", "failed"}
                    ):
                        diagnostic = LiveAttemptDiagnostic.model_validate(
                            {
                                "classification": early.classification,
                                "exit_code": early.exit_code,
                                "message": early.message,
                                "diagnostic_component": early.diagnostic_component,
                            }
                        )
                    updates: dict[str, object] = {
                        "worker_active": worker_active,
                        "attempt_diagnostic": diagnostic,
                    }
                    # Committed terminal projections retain their classification,
                    # message, exit code and artifacts, even after a rejected attempt.
                    if persisted.classification in {"starting", "running"} and not worker_active:
                        updates.update(
                            classification=diagnostic.classification
                            if diagnostic
                            else "interrupted",
                            exit_code=diagnostic.exit_code if diagnostic else None,
                            message=(
                                f"Latest execution attempt: {diagnostic.message} "
                                if diagnostic
                                else ""
                            )
                            + "No active worker in this app. Saved progress and reservations are "
                            "unchanged; resume with the original settings or start a new run.",
                            diagnostic_component=(
                                diagnostic.diagnostic_component
                                if diagnostic
                                else "worker-ownership"
                            ),
                        )
                    return persisted.model_copy(update=updates)
                if worker_active:
                    return self._early_snapshot_from_values(
                        resolved,
                        run_id,
                        "Awaiting persisted run manifest",
                        "starting",
                        None,
                        "Worker is starting; no provider call is claimed "
                        "until persistence records it.",
                    ).model_copy(update={"worker_active": True})
                if early is not None:
                    if not Path(resolved).is_file():
                        self._early_results.pop(key, None)
                    return early
        raise KeyError(f"run {run_id} not found")

    def _persisted_snapshot(self, resolved: str, run_id: UUID) -> LiveRunSnapshot | None:
        """Inspect in one validated read-only session; never alter attempt state."""
        if not Path(resolved).is_file():
            return None
        persisted_status = None
        try:
            with open_read_only_store(resolved) as store:
                try:
                    artifact = _read_first_v2_artifact(
                        store.connection,
                        run_id,
                        (
                            V2_PRODUCTION_ARTIFACT_KEY,
                            V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
                            V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
                        ),
                    )
                except KeyError:
                    v2_providers = configured_v2_providers(store.connection, run_id)
                    if v2_providers:
                        snapshot = self._snapshot_from_v2_progress(
                            resolved, run_id, v2_providers, source=store.connection
                        )
                        return snapshot.model_copy(
                            update={
                                "persisted_status": read_run(store.connection, run_id).status.value
                            }
                        )
                else:
                    snapshot = self._snapshot_from_v2_result(
                        V2ProductionPipelineResult.model_validate_json(artifact.payload_json),
                        source=store.connection,
                        db_path=resolved,
                    )
                    return snapshot.model_copy(
                        update={"persisted_status": read_run(store.connection, run_id).status.value}
                    )
                if self._inspector is inspect_provider_run:
                    result = self._inspector(resolved, run_id, source=store.connection)
                    return self._snapshot_from_result(result, source=store.connection).model_copy(
                        update={"persisted_status": read_run(store.connection, run_id).status.value}
                    )
                persisted_status = read_run(store.connection, run_id).status.value
        except KeyError:
            pass
        if self._inspector is not inspect_provider_run:
            try:
                result = self._inspector(resolved, run_id)
                return self._snapshot_from_result(result).model_copy(
                    update={"persisted_status": persisted_status}
                )
            except KeyError:
                pass
            except Exception as exc:
                if isinstance(exc, DatabaseCompatibilityError):
                    raise
                with self._lock:
                    active = self._active.get((resolved, run_id))
                    if active is not None and not active.future.done():
                        return None
                return self._early_snapshot_from_values(
                    resolved,
                    run_id,
                    "Run inspection failed",
                    "failed",
                    CLIExitCode.FAILED,
                    self._redact(exc),
                )
        return None

    def _evict_completed_run(self, key: tuple[str, UUID], future: Future[LiveRunSnapshot]) -> None:
        """Release ownership; retain the latest attempt separately from saved progress."""
        try:
            snapshot = future.result()
        except Exception:
            snapshot = None
        with self._lock:
            active = self._active.get(key)
            if active is None or active.future is not future:
                return
            del self._active[key]
            if snapshot is not None:
                self._remember_early_result_locked(key, snapshot)

    def _remember_early_result_locked(
        self, key: tuple[str, UUID], snapshot: LiveRunSnapshot
    ) -> None:
        """Keep up to 32 ephemeral outcomes until retry, eviction or a no-DB poll.

        Polling existing databases never consumes these diagnostics. Restart drops
        them; ownership still projects unfinished saved runs as interrupted.
        """
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
        return read_history(db_path, limit=limit)

    def research_trail(self, db_path: str | Path, run_id: UUID) -> ResearchTrail:
        return read_research_trail(db_path, run_id)

    def shutdown(self, *, timeout: float = 90) -> bool:
        """Cancel at existing boundaries, preserving reservations for unknown outcomes."""
        self._shutdown_requested.set()
        with self._lock:
            active = tuple(self._active.items())
        for (db_path, run_id), worker in active:
            if worker.future.done():
                continue
            try:
                request_run_cancellation(db_path, run_id, reason="desktop application closing")
            except (KeyError, ValueError):
                # A worker not yet persisted still observes the in-memory cancellation flag.
                continue
        _, unfinished = wait([worker.future for _, worker in active], timeout=timeout)
        self._executor.shutdown(wait=False)
        return not unfinished

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
                    research_controls=request.research_controls,
                    run_id=run_id,
                    provider_policy_fingerprint=(factory_config.semantic_fingerprint_sha256()),
                    cancellation_requested=lambda: (
                        self._shutdown_requested.is_set()
                        or v2_cancellation_requested(request.db_path, run_id)
                    ),
                    _database_lock_owned=True,
                )
                return self._snapshot_from_v2_result(result)
            if self._legacy_runner is None:
                raise TypeError("legacy factory cannot be used by the fresh-v2 runner")
            from researchassistant.storage.database_lock import retained_database_lock

            with retained_database_lock(request.db_path):
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

    def _snapshot_from_result(
        self, result: ProviderPipelineResult, *, source: DatabaseReader | None = None
    ) -> LiveRunSnapshot:
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
            if source is not None:
                contract = read_provider_run_contract(source, result.run_id)
            else:
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
        *,
        source: str | Path | Connection | None = None,
    ) -> LiveRunSnapshot:
        return snapshot_from_v2_progress(db_path, run_id, providers, source=source)

    def _snapshot_from_v2_result(
        self,
        result: V2ProductionPipelineResult,
        *,
        source: str | Path | Connection | None = None,
        db_path: str | None = None,
    ) -> LiveRunSnapshot:
        return snapshot_from_v2_result(result, source=source, db_path=db_path)

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
                    "PUBMED_API_KEY",
                )
            ),
        )


def prepare_default_database() -> Path:
    from researchassistant.platform_support.private_files import private_directory

    private_directory(DEFAULT_LIVE_DB.parent)
    return DEFAULT_LIVE_DB
