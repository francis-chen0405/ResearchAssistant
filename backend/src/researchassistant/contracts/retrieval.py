"""Historical retrieval data and validation; execution belongs to the agents."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from researchassistant.contracts.discovery_ranking import (
    DiscoveryDecision,
    RankedAcquiredSource,
    RankedDiscoveryResult,
)
from researchassistant.contracts.models import (
    MediaTypeProvenance,
    RetrievalRecord,
    RetrievalStatus,
    SourceSnapshot,
    Stance,
    StrictModel,
)
from researchassistant.contracts.scraping import ScrapeStatus

RESULTS_PER_QUERY = 3


QUERIES_PER_STANCE = 3


ATTEMPTS_PER_STANCE = RESULTS_PER_QUERY * QUERIES_PER_STANCE


class RetrievalOutcome(StrictModel):
    retrieval: RetrievalRecord
    scrape_status: ScrapeStatus
    content_type: str | None = None
    provider_name: str | None = None
    provider_version: str | None = None
    canonical_url: str | None = None
    normalization_version: str | None = None
    acquisition_version: str | None = None
    media_type_provenance: MediaTypeProvenance = MediaTypeProvenance()
    snapshot_id: UUID | None = None
    attempts_made: int = Field(ge=0)
    failure_code: str | None = None
    failure_message: str | None = None
    duplicate_of_snapshot_id: UUID | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> RetrievalOutcome:
        successful = self.scrape_status is ScrapeStatus.RETRIEVED
        failed = self.scrape_status in {ScrapeStatus.FAILED, ScrapeStatus.TIMEOUT}
        normalized_failure = failed or self.scrape_status is ScrapeStatus.UNSUPPORTED
        duplicate = self.scrape_status in {
            ScrapeStatus.DUPLICATE_URL,
            ScrapeStatus.DUPLICATE_CONTENT,
        }
        if successful != (self.snapshot_id is not None):
            raise ValueError("only retrieved outcomes may reference a new snapshot")
        if failed != (self.failure_message is not None):
            raise ValueError("failed outcomes require exactly one failure message")
        if normalized_failure != (self.failure_code is not None):
            raise ValueError("failed or unsupported outcomes require exactly one failure code")
        if duplicate != (self.duplicate_of_snapshot_id is not None):
            raise ValueError("duplicate outcomes require the existing snapshot ID")
        if self.scrape_status is ScrapeStatus.RETRIEVED:
            if self.retrieval.status is not RetrievalStatus.RETRIEVED:
                raise ValueError("retrieved scrape outcomes require retrieved records")
            if self.content_type is None or self.attempts_made < 1:
                raise ValueError("retrieved scrape outcomes require content type and attempts")
        elif self.retrieval.status is RetrievalStatus.RETRIEVED:
            raise ValueError("only retrieved scrape outcomes may use retrieved records")
        if self.scrape_status in {ScrapeStatus.FAILED, ScrapeStatus.TIMEOUT}:
            if self.retrieval.status is not RetrievalStatus.FAILED or self.attempts_made < 1:
                raise ValueError("failed scrape outcomes require failed records and attempts")
        if self.scrape_status is ScrapeStatus.UNSUPPORTED:
            if self.retrieval.status is not RetrievalStatus.SKIPPED:
                raise ValueError("unsupported scrape outcomes require skipped records")
            if self.content_type is None or self.attempts_made < 1:
                raise ValueError("unsupported scrape outcomes require content type and attempts")
        if duplicate and self.retrieval.status is not RetrievalStatus.SKIPPED:
            raise ValueError("duplicate scrape outcomes require skipped records")
        if self.scrape_status is ScrapeStatus.DUPLICATE_URL and self.attempts_made not in {0, 1}:
            raise ValueError("URL duplicates require zero or one scrape attempt")
        if self.scrape_status is ScrapeStatus.DUPLICATE_CONTENT and self.attempts_made < 1:
            raise ValueError("content duplicates require at least one scrape attempt")
        return self


class ResearcherRetrievalBatch(StrictModel):
    run_id: UUID
    stance: Stance
    intended_attempt_count: int = Field(default=ATTEMPTS_PER_STANCE, ge=3, le=30)
    discovery_results_per_query: int = Field(default=RESULTS_PER_QUERY, ge=3, le=100)
    usable_snapshots_per_query: int = Field(default=RESULTS_PER_QUERY, ge=1, le=10)
    source_target_per_stance: Literal[5, 7, 10, 15, 20] | None = None
    discovery_ranking: tuple[RankedDiscoveryResult, ...] = ()
    acquired_source_ranking: tuple[RankedAcquiredSource, ...] = ()
    outcomes: list[RetrievalOutcome]
    snapshots: list[SourceSnapshot]

    @model_validator(mode="after")
    def validate_batch(self) -> ResearcherRetrievalBatch:
        if self.source_target_per_stance is not None:
            return self._validate_ranked_batch()
        if self.intended_attempt_count != (self.discovery_results_per_query * QUERIES_PER_STANCE):
            raise ValueError("intended attempt count must match configured discovery depth")
        pairs_by_round: dict[int, list[int]] = {}
        for outcome in self.outcomes:
            pairs_by_round.setdefault(outcome.retrieval.query_round, []).append(
                outcome.retrieval.search_rank
            )
        if set(pairs_by_round) != set(range(1, QUERIES_PER_STANCE + 1)):
            raise ValueError("researcher outcomes must cover all three query rounds")
        for ranks in pairs_by_round.values():
            ordered = sorted(ranks)
            if ordered != list(range(1, len(ordered) + 1)):
                raise ValueError("researcher ranks must be contiguous from rank one")
            if len(ordered) > self.discovery_results_per_query:
                raise ValueError("researcher outcomes exceed configured discovery depth")
        if any(outcome.retrieval.run_id != self.run_id for outcome in self.outcomes):
            raise ValueError("retrieval run IDs must match the batch")
        snapshots_by_round: dict[int, int] = {}
        for outcome in self.outcomes:
            if outcome.snapshot_id is not None:
                snapshots_by_round[outcome.retrieval.query_round] = (
                    snapshots_by_round.get(outcome.retrieval.query_round, 0) + 1
                )
        if any(count > self.usable_snapshots_per_query for count in snapshots_by_round.values()):
            raise ValueError("researcher snapshots exceed the per-query keep target")
        snapshot_ids = {snapshot.snapshot_id for snapshot in self.snapshots}
        outcome_snapshot_ids = {
            outcome.snapshot_id for outcome in self.outcomes if outcome.snapshot_id is not None
        }
        if len(snapshot_ids) != len(self.snapshots) or snapshot_ids != outcome_snapshot_ids:
            raise ValueError("batch snapshots must exactly match newly retrieved outcomes")
        attempts_by_id = {
            outcome.retrieval.retrieval_attempt_id: outcome for outcome in self.outcomes
        }
        for snapshot in self.snapshots:
            outcome = attempts_by_id.get(snapshot.retrieval_attempt_id)
            if outcome is None or snapshot.run_id != self.run_id:
                raise ValueError("snapshot provenance must match a batch retrieval")
            if snapshot.source_url != outcome.retrieval.resolved_url:
                raise ValueError("snapshot source URL must match the resolved retrieval URL")
        return self

    def _validate_ranked_batch(self) -> ResearcherRetrievalBatch:
        maximum_backfill_attempts = min(25, self.source_target_per_stance + 5)
        if not (
            self.source_target_per_stance
            <= self.intended_attempt_count
            <= maximum_backfill_attempts
        ):
            raise ValueError(
                "ranked batch attempt ceiling must stay within its bounded backfill pool"
            )
        selected = [
            item for item in self.discovery_ranking if item.decision is DiscoveryDecision.SELECTED
        ]
        if len(selected) > self.source_target_per_stance:
            raise ValueError("ranked batch exceeds its source target")
        expected_ranks = list(range(1, len(selected) + 1))
        if [item.selection_rank for item in selected] != expected_ranks:
            raise ValueError("ranked selections must be contiguous from rank one")
        outcome_ranks = sorted(outcome.retrieval.search_rank for outcome in self.outcomes)
        if outcome_ranks != list(range(1, len(self.outcomes) + 1)):
            raise ValueError("ranked outcomes must have contiguous acquisition ranks")
        if len(self.outcomes) > self.intended_attempt_count:
            raise ValueError("ranked outcomes exceed the bounded backfill pool")
        if len(self.snapshots) > self.intended_attempt_count:
            raise ValueError("ranked snapshots exceed the bounded backfill pool")
        ranked_snapshot_ids = [item.snapshot_id for item in self.acquired_source_ranking]
        if len(ranked_snapshot_ids) != len(set(ranked_snapshot_ids)):
            raise ValueError("acquired-source rankings require unique snapshots")
        if set(ranked_snapshot_ids) != {snapshot.snapshot_id for snapshot in self.snapshots}:
            raise ValueError("acquired-source rankings must exactly cover batch snapshots")
        if [item.extraction_rank for item in self.acquired_source_ranking] != list(
            range(1, len(self.acquired_source_ranking) + 1)
        ):
            raise ValueError("acquired-source extraction ranks must be contiguous")
        if any(outcome.retrieval.run_id != self.run_id for outcome in self.outcomes):
            raise ValueError("retrieval run IDs must match the batch")
        snapshot_ids = {snapshot.snapshot_id for snapshot in self.snapshots}
        outcome_snapshot_ids = {
            outcome.snapshot_id for outcome in self.outcomes if outcome.snapshot_id is not None
        }
        if len(snapshot_ids) != len(self.snapshots) or snapshot_ids != outcome_snapshot_ids:
            raise ValueError("batch snapshots must exactly match newly retrieved outcomes")
        attempts_by_id = {
            outcome.retrieval.retrieval_attempt_id: outcome for outcome in self.outcomes
        }
        for snapshot in self.snapshots:
            outcome = attempts_by_id.get(snapshot.retrieval_attempt_id)
            if outcome is None or snapshot.run_id != self.run_id:
                raise ValueError("snapshot provenance must match a batch retrieval")
            if snapshot.source_url != outcome.retrieval.resolved_url:
                raise ValueError("snapshot source URL must match the resolved retrieval URL")
        return self
