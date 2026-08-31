"""Deployment-owned adapter for the canonical v2 hosted worker boundary."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from typing import Protocol

from cli import repository_identity
from hosted import (
    HostedCheckpoint,
    HostedError,
    HostedJobLease,
    HostedProviderCredentials,
    HostedRepository,
    HostedRun,
    build_repository_from_environment,
)
from models import ResearchDirections
from providers.v2_budget import V2RunCeilings
from providers.v2_factory import V2ProductionFactoryConfig, build_v2_production_bundle
from v2_orchestrator import V2ProductionPipelineResult, run_v2_production_pipeline


class HostedHeartbeat(Protocol):
    def __call__(self, checkpoint: HostedCheckpoint) -> HostedRun: ...


def _repository_revision(environment: Mapping[str, str]) -> str:
    """Use Render's immutable revision when available, otherwise hash the source surface."""
    return environment.get("RENDER_GIT_COMMIT", "").strip() or repository_identity()


def _hosted_cancellation_checker(
    lease: HostedJobLease,
    repository: HostedRepository,
    lease_lost: Event,
) -> Callable[[], bool]:
    """Poll durable hosted state so cancellation is observed at v2 boundaries."""

    def is_cancelled() -> bool:
        if lease_lost.is_set():
            return True
        try:
            return repository.get_run(lease.run.owner_id, lease.run.run_id).status == "cancelled"
        except HostedError:
            return False

    return is_cancelled


def _lease_heartbeat_loop(
    stop: Event,
    lease_lost: Event,
    heartbeat: HostedHeartbeat,
) -> None:
    """Keep the Supabase lease alive while the canonical coordinator is running."""
    while not stop.wait(45.0):
        try:
            heartbeat(
                HostedCheckpoint(
                    stage="canonical_research",
                    checkpoint="canonical-pipeline-heartbeat",
                    progress_percent=10,
                    message="Canonical research pipeline is still running.",
                )
            )
        except Exception:
            lease_lost.set()
            return


def run_canonical_hosted_pipeline(
    lease: HostedJobLease,
    credentials: HostedProviderCredentials,
    heartbeat: HostedHeartbeat,
) -> V2ProductionPipelineResult:
    """Run canonical v2 with Supabase-owned job state and ephemeral execution scratch space."""
    environment = dict(os.environ)
    environment.update(credentials.as_environment())
    request = lease.run.request
    ceilings = V2RunCeilings(
        max_physical_calls=request.max_llm_calls,
        max_total_tokens=request.max_tokens,
        max_total_cost_usd=request.max_cost_usd,
    )
    config = V2ProductionFactoryConfig.from_environment(
        environment,
        repository_revision=_repository_revision(environment),
        discovery_providers=request.discovery_providers,
        ceilings=ceilings,
        crossref_enabled=request.crossref_enabled,
    )
    bundle = build_v2_production_bundle(config)
    heartbeat(
        HostedCheckpoint(
            stage="planning",
            checkpoint="canonical-pipeline-configured",
            progress_percent=8,
            message="Canonical research pipeline configured.",
        )
    )
    repository = build_repository_from_environment(environment)
    stop = Event()
    lease_lost = Event()
    heartbeat_thread = Thread(
        target=_lease_heartbeat_loop,
        args=(stop, lease_lost, heartbeat),
        name=f"hosted-heartbeat-{lease.run.run_id}",
        daemon=True,
    )
    heartbeat_thread.start()
    try:
        with TemporaryDirectory(prefix=f"researchassistant-hosted-{lease.run.run_id}-") as scratch:
            return run_v2_production_pipeline(
                lease.run.raw_claim,
                db_path=Path(scratch) / "canonical.sqlite3",
                directions=ResearchDirections(
                    support_enabled=request.support_enabled,
                    challenge_enabled=request.challenge_enabled,
                ),
                discovery_providers=config.discovery_providers,
                search_providers=bundle.search_providers,
                wigolo_provider=None,
                firecrawl_provider=bundle.firecrawl,
                llm_provider=bundle.llm,
                routing_config=config.routing,
                ceilings=config.ceilings,
                run_id=lease.run.run_id,
                provider_policy_fingerprint=config.semantic_fingerprint_sha256(),
                cancellation_requested=_hosted_cancellation_checker(
                    lease,
                    repository,
                    lease_lost,
                ),
            )
    finally:
        stop.set()
        heartbeat_thread.join(timeout=2.0)
