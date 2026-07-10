"""Opposing researcher retrieval entry point."""

from __future__ import annotations

from agents.supportingresearcher import (
    Clock,
    ResearcherRetrievalBatch,
    SnapshotConsumer,
    _DeduplicationState,
    _retrieve_stance,
)
from models import PlannerOutput, Stance
from providers.scraper import RetryPolicy, ScraperProvider
from providers.search import SearchProvider


def retrieve_opposing(
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy | None = None,
    clock: Clock | None = None,
    snapshot_consumer: SnapshotConsumer | None = None,
) -> ResearcherRetrievalBatch:
    """Retrieve the three opposing rounds at a fixed depth of three."""
    from agents.supportingresearcher import _utc_now

    return _retrieve_stance(
        planner,
        Stance.OPPOSING,
        search_provider,
        scraper_provider,
        retry_policy=retry_policy or RetryPolicy(),
        clock=clock or _utc_now,
        deduplication=_DeduplicationState(),
        snapshot_consumer=snapshot_consumer,
    )
