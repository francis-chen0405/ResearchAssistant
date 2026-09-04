"""Persistent Render worker entry point for durable hosted research jobs."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import signal
from collections.abc import Callable, Mapping
from threading import Event
from typing import cast

from hosted import (
    HostedArtifact,
    HostedCheckpoint,
    HostedExecutionError,
    HostedExecutionResult,
    HostedJobLease,
    HostedJobRunner,
    HostedPipelineExecutor,
    HostedProviderCredentials,
    HostedRepository,
    HostedRun,
    HostedRunStatus,
    UnavailableHostedExecutor,
    build_repository_from_environment,
    utc_now,
)
from v2_orchestrator import V2ProductionPipelineResult, V2ProductionState

CanonicalHostedPipelineRunner = Callable[
    [
        HostedJobLease,
        HostedProviderCredentials,
        Callable[[HostedCheckpoint], HostedRun],
    ],
    V2ProductionPipelineResult,
]


def _load_canonical_runner(environ: Mapping[str, str]) -> CanonicalHostedPipelineRunner:
    """Load the deployment's hosted adapter for the canonical v2 coordinator."""
    target = environ.get("HOSTED_CANONICAL_RUNNER", "").strip()
    if not target or ":" not in target:
        raise HostedExecutionError(
            "HOSTED_CANONICAL_RUNNER must name a hosted adapter as module:callable"
        )
    module_name, attribute_name = target.split(":", 1)
    try:
        candidate = getattr(importlib.import_module(module_name), attribute_name)
    except (ImportError, AttributeError) as exc:
        raise HostedExecutionError(
            "the configured canonical hosted adapter could not load"
        ) from exc
    if not callable(candidate):
        raise HostedExecutionError("the configured canonical hosted adapter is not callable")
    return cast(CanonicalHostedPipelineRunner, candidate)


def _hosted_result_from_canonical(
    lease: HostedJobLease,
    result: V2ProductionPipelineResult,
) -> HostedExecutionResult:
    """Project the canonical typed result into the durable hosted terminal contract."""
    payload_json = json.dumps(
        result.model_copy(update={"db_path": "hosted-ephemeral"}).model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    artifact = HostedArtifact(
        artifact_id=result.run_id,
        run_id=lease.run.run_id,
        owner_id=lease.run.owner_id,
        artifact_type="canonical-research-result",
        fingerprint=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        payload_json=payload_json,
        created_at=utc_now(),
    )
    status = result.state.value
    message = (
        "Research released."
        if result.state is V2ProductionState.RELEASED
        else result.failure_reason or f"Research finished with status: {status}."
    )
    return HostedExecutionResult(
        status=cast(HostedRunStatus, status),
        stage=result.current_stage.value,
        message=message,
        final_artifact=artifact,
    )


class CanonicalHostedPipelineExecutor:
    """Execute the canonical v2 pipeline through an explicit hosted adapter."""

    def __init__(
        self,
        repository: HostedRepository,
        runner: CanonicalHostedPipelineRunner,
    ) -> None:
        self._repository = repository
        self._runner = runner

    def execute(
        self,
        lease: HostedJobLease,
        heartbeat: Callable[[HostedCheckpoint], HostedRun],
    ) -> HostedExecutionResult:
        heartbeat(
            HostedCheckpoint(
                stage="planning",
                checkpoint="canonical-pipeline-started",
                progress_percent=5,
                message="Canonical research pipeline started.",
            )
        )
        credentials = self._repository.provider_credentials(lease.run.owner_id)
        result = self._runner(lease, credentials, heartbeat)
        if result.run_id != lease.run.run_id or result.raw_claim != lease.run.raw_claim:
            raise HostedExecutionError("canonical hosted adapter returned the wrong run identity")
        heartbeat(
            HostedCheckpoint(
                stage=result.current_stage.value,
                checkpoint="canonical-pipeline-finished",
                progress_percent=95,
                message="Canonical research pipeline finished.",
            )
        )
        return _hosted_result_from_canonical(lease, result)


def build_worker_executor(
    environ: Mapping[str, str] | None = None,
    *,
    repository: HostedRepository | None = None,
    runner: CanonicalHostedPipelineRunner | None = None,
) -> HostedPipelineExecutor:
    """Build the canonical hosted executor without a local-database fallback."""
    values = os.environ if environ is None else environ
    mode = values.get("HOSTED_PIPELINE_EXECUTOR", "canonical").casefold()
    if mode != "canonical":
        return UnavailableHostedExecutor()
    selected_repository = repository or build_repository_from_environment(values)
    selected_runner = runner or _load_canonical_runner(values)
    return CanonicalHostedPipelineExecutor(selected_repository, selected_runner)


def build_worker(
    repository: HostedRepository | None = None,
    *,
    executor: HostedPipelineExecutor | None = None,
    environ: Mapping[str, str] | None = None,
) -> HostedJobRunner:
    """Build a worker with explicit persistence and execution dependencies."""
    selected_repository = repository or build_repository_from_environment(environ)
    return HostedJobRunner(
        selected_repository,
        executor or build_worker_executor(environ, repository=selected_repository),
        worker_id=(os.environ if environ is None else environ).get("RENDER_INSTANCE_ID"),
        lease_seconds=int(
            (os.environ if environ is None else environ).get("HOSTED_JOB_LEASE_SECONDS", "300")
        ),
    )


def run_worker_loop(
    worker: HostedJobRunner,
    *,
    stop_event: Event | None = None,
    poll_seconds: float = 2.0,
) -> None:
    """Run the persistent worker until Render sends a termination signal."""
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    stopped = stop_event if stop_event is not None else Event()
    while not stopped.is_set():
        processed = worker.run_once()
        if processed is None:
            stopped.wait(poll_seconds)


def main() -> None:
    """Start the worker process with SIGTERM/SIGINT handling."""
    stop_event = Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run_worker_loop(build_worker(), stop_event=stop_event)


if __name__ == "__main__":
    main()
