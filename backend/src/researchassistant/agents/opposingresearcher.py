"""Opposing researcher retrieval entry point."""

from __future__ import annotations

from collections.abc import Callable

from researchassistant.agents.supportingresearcher import (
    AcquisitionPolicy,
    Clock,
    DeduplicationState,
    SnapshotConsumer,
    _retrieve_stance,
)
from researchassistant.contracts.models import PlannerOutput, Stance
from researchassistant.contracts.retrieval import ResearcherRetrievalBatch
from researchassistant.contracts.scraping import RetryPolicy
from researchassistant.providers.scraper import ScraperProvider
from researchassistant.providers.search import SearchProvider


def retrieve_opposing(
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy | None = None,
    acquisition_policy: AcquisitionPolicy | None = None,
    clock: Clock | None = None,
    snapshot_consumer: SnapshotConsumer | None = None,
    boundary_check: Callable[[], None] | None = None,
    deduplication: DeduplicationState | None = None,
) -> ResearcherRetrievalBatch:
    """Retrieve the three opposing rounds at a fixed depth of three."""
    from researchassistant.agents.supportingresearcher import _utc_now

    return _retrieve_stance(
        planner,
        Stance.OPPOSING,
        search_provider,
        scraper_provider,
        retry_policy=retry_policy or RetryPolicy(),
        acquisition_policy=acquisition_policy or AcquisitionPolicy(),
        clock=clock or _utc_now,
        deduplication=deduplication or DeduplicationState(),
        snapshot_consumer=snapshot_consumer,
        boundary_check=boundary_check,
    )
