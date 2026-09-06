"""Application controller for configuration, run workers, locking, and cancellation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from threading import Event, Lock
from uuid import UUID, uuid4

from agents.v2_final_output import render_v2_final_output
from application_runtime import CLIExitCode, repository_identity
from desktop_paths import application_data_dir
from file_lock import FileLock
from frontend.live_contracts import (
    LEGACY_LIVE_RESEARCH_CONTROLS,
    AcquiredSourceScoreBreakdown,
    DiscoveryScoreBreakdown,
    LiveClassification,
    LiveHistoryItem,
    LiveRunRequest,
    LiveRunSnapshot,
    LiveStartResult,
    ResearchProgress,
    ResearchTrail,
    ResearchTrailItem,
)
from frontend.live_history import history as read_history
from frontend.live_history import research_trail as read_research_trail
from frontend.live_progress import (
    _diagnostic_component as _diagnostic_component,
)
from frontend.live_progress import (
    _empty_progress as _empty_progress,
)
from frontend.live_progress import (
    _read_first_v2_artifact as _read_first_v2_artifact,
)
from frontend.live_progress import (
    _read_v2_budget_snapshot as _read_v2_budget_snapshot,
)
from frontend.live_progress import (
    _read_v2_directional_progress as _read_v2_directional_progress,
)
from frontend.live_progress import (
    _read_v2_directions as _read_v2_directions,
)
from frontend.live_progress import (
    _research_progress as _research_progress,
)
from frontend.live_progress import (
    _research_round_and_progress as _research_round_and_progress,
)
from frontend.live_progress import (
    _result_message as _result_message,
)
from frontend.live_progress import (
    _v2_current_round as _v2_current_round,
)
from frontend.live_progress import (
    _v2_progress_percent as _v2_progress_percent,
)
from frontend.live_progress import (
    _v2_research_progress as _v2_research_progress,
)
from frontend.live_progress import (
    exit_code_for_status as exit_code_for_status,
)
from frontend.security import redact_text
from models import (
    DEFAULT_RESEARCH_CONTROLS,
    DiscoveryProvider,
    ResearchControls,
    ResearchDirections,
    ResearchMode,
    RunStatus,
)
from orchestrator import (
    ClaimMismatchError,
    FingerprintMismatchError,
    ProviderPipelineResult,
    inspect_provider_run,
    request_run_cancellation,
)
from providers.config import ProviderConfigurationError, RunCeilings, WigoloConfig
from providers.mimo_factory import MimoProviderFactoryConfig
from providers.v2_budget import (
    V2RunCeilings,
)
from providers.v2_factory import V2ProductionFactoryConfig, build_v2_production_bundle
from store import (
    open_read_only_store,
    read_provider_run_contract,
    read_run,
)
from v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
    build_v2_run_diagnostics_or_empty,
    configured_v2_providers,
    infer_v2_stage,
    run_v2_production_pipeline,
    v2_cancellation_requested,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIVE_DB = application_data_dir() / "live-runs.sqlite3"


def contract_controls(policy_identity: str) -> ResearchControls:
    """Recover immutable controls persisted in the canonical provider contract."""
    return ResearchControls.from_policy_identity(policy_identity)


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
    """Keep local website requests responsive while SQLite remains authoritative."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str],
        runner: Callable[..., ProviderPipelineResult] | None = None,
        inspector: Callable[..., ProviderPipelineResult] = inspect_provider_run,
        max_workers: int = 2,
    ) -> None:
        self._shutdown_requested = Event()
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
        with self._lock:
            active = self._active.get(key)
            early = self._early_results.pop(key, None)
        if Path(resolved).is_file():
            try:
                artifact = _read_first_v2_artifact(
                    resolved,
                    run_id,
                    (
                        V2_PRODUCTION_ARTIFACT_KEY,
                        V2_PRODUCTION_PHASE13_ARTIFACT_KEY,
                        V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
                    ),
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
            final_brief=(
                render_v2_final_output(output)
                if output is not None and output.release_validation.valid
                else None
            ),
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
    DEFAULT_LIVE_DB.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return DEFAULT_LIVE_DB
