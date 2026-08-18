"""Typed application service for the persisted MVP-4 live pipeline."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import IO, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from cli import CLIExitCode, repository_identity
from frontend.security import redact_text
from models import (
    DEFAULT_RESEARCH_CONTROLS,
    DiscoveryProvider,
    ResearchControls,
    RunManifest,
    StrictModel,
)
from money import ExactUSD
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
    run_mvp3b_pipeline,
)
from providers.config import ProviderConfigurationError, RunCeilings, WigoloConfig
from providers.mimo_factory import MimoProviderFactoryConfig
from store import (
    list_runs,
    open_read_only_store,
    read_provider_run_contract,
    read_stage_artifact,
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


def contract_controls(policy_identity: str) -> ResearchControls:
    """Recover immutable controls persisted in the canonical provider contract."""
    return ResearchControls.from_policy_identity(policy_identity)


class LiveRunRequest(StrictModel):
    raw_claim: str = Field(min_length=1)
    db_path: str = Field(min_length=1)
    run_id: UUID | None = None
    max_tokens: int = Field(ge=1, le=1_000_000)
    max_cost_usd: Decimal = Field(gt=0, le=Decimal("1.00"))
    max_llm_calls: int = Field(default=160, ge=1, le=160)
    research_controls: ResearchControls = LEGACY_LIVE_RESEARCH_CONTROLS

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
    provider: Literal["exa", "openalex"]
    intent: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    title: str
    url: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    decision: Literal["selected", "deferred", "discarded"]
    selection_rank: int | None = Field(default=None, ge=1, le=20)
    breakdown: DiscoveryScoreBreakdown
    acquired_score: int | None = Field(default=None, ge=0, le=100)
    extraction_rank: int | None = Field(default=None, ge=1, le=25)
    acquired_breakdown: AcquiredSourceScoreBreakdown | None = None


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
        runner: Callable[..., ProviderPipelineResult] = run_mvp3b_pipeline,
        inspector: Callable[..., ProviderPipelineResult] = inspect_provider_run,
        max_workers: int = 2,
    ) -> None:
        self._environment = environment
        self._runner = runner
        self._inspector = inspector
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mvp5-live")
        self._lock = Lock()
        self._active: dict[tuple[str, UUID], _ActiveRun] = {}
        self._early_results: dict[tuple[str, UUID], LiveRunSnapshot] = {}

    def configuration_message(self) -> str | None:
        try:
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
            ceilings = RunCeilings(
                max_tokens=request.max_tokens,
                max_cost_usd=request.max_cost_usd,
                max_llm_calls=request.max_llm_calls,
            )
            wigolo = WigoloConfig(
                base_url=self._environment.get("WIGOLO_BASE_URL", "http://127.0.0.1:8000")
            )
            factory_config = MimoProviderFactoryConfig.from_environment(
                self._environment,
                repository_revision=repository_identity(),
                wigolo=wigolo,
                ceilings=ceilings,
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
                self._early_results[key] = snapshot
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
            early = self._early_results.get(key)
        if Path(resolved).is_file():
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
            return tuple(
                self._history_item(manifest)
                for manifest in list_runs(store.connection, limit=limit)
            )

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
                        -item.score,
                        item.url,
                    ),
                )
            ),
        )

    def has_active_runs(self) -> bool:
        with self._lock:
            return any(not active.future.done() for active in self._active.values())

    def _run(
        self,
        request: LiveRunRequest,
        run_id: UUID,
        factory_config: MimoProviderFactoryConfig,
        database_lock: _DatabaseLock,
    ) -> LiveRunSnapshot:
        try:
            result = self._runner(
                request.raw_claim,
                db_path=request.db_path,
                factory_config=factory_config,
                run_id=run_id,
                research_controls=request.research_controls,
            )
            return self._snapshot_from_result(result)
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
