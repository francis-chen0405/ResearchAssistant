"""Deterministic Phase 7B retrieval shared by both researcher stances."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from agents.researcher import build_source_snapshot
from models import (
    REQUIRED_QUERY_EXCLUSIONS,
    PlannerOutput,
    RetrievalRecord,
    RetrievalStatus,
    SearchQuery,
    SourceSnapshot,
    Stance,
    StrictModel,
)
from providers.scraper import (
    RetryPolicy,
    ScrapeRequest,
    ScrapeResponse,
    ScraperProvider,
    ScraperProviderError,
    ScraperTimeoutError,
    ScrapeStatus,
)
from providers.search import SearchProvider, SearchProviderError, SearchRequest, SearchResponse
from utils import compute_sha256

RESULTS_PER_QUERY = 3
QUERIES_PER_STANCE = 3
ATTEMPTS_PER_STANCE = RESULTS_PER_QUERY * QUERIES_PER_STANCE
TOTAL_INTENDED_ATTEMPTS = ATTEMPTS_PER_STANCE * 2
SNAPSHOT_WORD_LIMIT = 3_000

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*(?:%)?")


class RetrievalOutcome(StrictModel):
    retrieval: RetrievalRecord
    scrape_status: ScrapeStatus
    content_type: str | None = None
    snapshot_id: UUID | None = None
    attempts_made: int = Field(ge=0)
    failure_message: str | None = None
    duplicate_of_snapshot_id: UUID | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> RetrievalOutcome:
        successful = self.scrape_status is ScrapeStatus.RETRIEVED
        failed = self.scrape_status in {ScrapeStatus.FAILED, ScrapeStatus.TIMEOUT}
        duplicate = self.scrape_status in {
            ScrapeStatus.DUPLICATE_URL,
            ScrapeStatus.DUPLICATE_CONTENT,
        }
        if successful != (self.snapshot_id is not None):
            raise ValueError("only retrieved outcomes may reference a new snapshot")
        if failed != (self.failure_message is not None):
            raise ValueError("failed outcomes require exactly one failure message")
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
    intended_attempt_count: Literal[9] = ATTEMPTS_PER_STANCE
    outcomes: list[RetrievalOutcome]
    snapshots: list[SourceSnapshot]

    @model_validator(mode="after")
    def validate_batch(self) -> ResearcherRetrievalBatch:
        if len(self.outcomes) != ATTEMPTS_PER_STANCE:
            raise ValueError("each researcher must record exactly nine intended attempts")
        expected_pairs = {
            (query_round, rank)
            for query_round in range(1, QUERIES_PER_STANCE + 1)
            for rank in range(1, RESULTS_PER_QUERY + 1)
        }
        actual_pairs = {
            (outcome.retrieval.query_round, outcome.retrieval.search_rank)
            for outcome in self.outcomes
        }
        if actual_pairs != expected_pairs:
            raise ValueError("researcher outcomes must preserve three ranks for all three rounds")
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


class BalancedRetrievalResult(StrictModel):
    run_id: UUID
    intended_attempt_count: Literal[18] = TOTAL_INTENDED_ATTEMPTS
    supporting: ResearcherRetrievalBatch
    opposing: ResearcherRetrievalBatch

    @model_validator(mode="after")
    def validate_balance(self) -> BalancedRetrievalResult:
        if self.supporting.run_id != self.run_id or self.opposing.run_id != self.run_id:
            raise ValueError("both researcher batches must match the run ID")
        if self.supporting.stance is not Stance.SUPPORTING:
            raise ValueError("supporting batch has the wrong stance")
        if self.opposing.stance is not Stance.OPPOSING:
            raise ValueError("opposing batch has the wrong stance")
        if self.supporting.intended_attempt_count != self.opposing.intended_attempt_count:
            raise ValueError("supporting and opposing retrieval depth must be equal")
        return self


@dataclass
class _DeduplicationState:
    original_urls: dict[str, UUID] = field(default_factory=dict)
    resolved_urls: dict[str, UUID] = field(default_factory=dict)
    content_hashes: dict[str, UUID] = field(default_factory=dict)
    resolved_by_original: dict[str, str] = field(default_factory=dict)


Clock = Callable[[], datetime]
SnapshotConsumer = Callable[[SourceSnapshot], None]


def retrieve_supporting(
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy | None = None,
    clock: Clock | None = None,
    snapshot_consumer: SnapshotConsumer | None = None,
) -> ResearcherRetrievalBatch:
    """Retrieve the three supporting rounds at a fixed depth of three."""
    return _retrieve_stance(
        planner,
        Stance.SUPPORTING,
        search_provider,
        scraper_provider,
        retry_policy=retry_policy or RetryPolicy(),
        clock=clock or _utc_now,
        deduplication=_DeduplicationState(),
        snapshot_consumer=snapshot_consumer,
    )


def retrieve_balanced(
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy | None = None,
    clock: Clock | None = None,
    snapshot_consumer: SnapshotConsumer | None = None,
) -> BalancedRetrievalResult:
    """Retrieve both sides with one shared deduplication boundary."""
    policy = retry_policy or RetryPolicy()
    now = clock or _utc_now
    deduplication = _DeduplicationState()
    supporting = _retrieve_stance(
        planner,
        Stance.SUPPORTING,
        search_provider,
        scraper_provider,
        retry_policy=policy,
        clock=now,
        deduplication=deduplication,
        snapshot_consumer=snapshot_consumer,
    )
    opposing = _retrieve_stance(
        planner,
        Stance.OPPOSING,
        search_provider,
        scraper_provider,
        retry_policy=policy,
        clock=now,
        deduplication=deduplication,
        snapshot_consumer=snapshot_consumer,
    )
    return BalancedRetrievalResult(
        run_id=planner.run_id,
        supporting=supporting,
        opposing=opposing,
    )


def _retrieve_stance(
    planner: PlannerOutput,
    stance: Stance,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy,
    clock: Clock,
    deduplication: _DeduplicationState,
    snapshot_consumer: SnapshotConsumer | None,
) -> ResearcherRetrievalBatch:
    queries = _queries_for_stance(planner, stance)
    outcomes: list[RetrievalOutcome] = []
    snapshots: list[SourceSnapshot] = []

    for query in queries:
        request = SearchRequest(
            query_text=_query_with_exclusions(query),
            limit=RESULTS_PER_QUERY,
        )
        try:
            response = search_provider.search(request)
        except SearchProviderError:
            raise
        except Exception as exc:
            raise SearchProviderError(
                f"search failed for {stance.value} round {query.query_round}: {exc}"
            ) from exc
        if not isinstance(response, SearchResponse):
            raise SearchProviderError("search provider returned a non-SearchResponse value")
        if len(response.results) < RESULTS_PER_QUERY:
            raise SearchProviderError(
                f"search returned {len(response.results)} results; expected at least three"
            )

        for rank, result in enumerate(response.results[:RESULTS_PER_QUERY], start=1):
            outcome, snapshot = _retrieve_result(
                planner.run_id,
                query,
                rank,
                result.original_url,
                scraper_provider,
                retry_policy,
                clock,
                deduplication,
            )
            outcomes.append(outcome)
            if snapshot is not None:
                snapshots.append(snapshot)
                if snapshot_consumer is not None:
                    snapshot_consumer(snapshot)

    return ResearcherRetrievalBatch(
        run_id=planner.run_id,
        stance=stance,
        outcomes=outcomes,
        snapshots=snapshots,
    )


def _retrieve_result(
    run_id: UUID,
    query: SearchQuery,
    rank: int,
    original_url: str,
    scraper_provider: ScraperProvider,
    retry_policy: RetryPolicy,
    clock: Clock,
    deduplication: _DeduplicationState,
) -> tuple[RetrievalOutcome, SourceSnapshot | None]:
    retrieval_attempt_id = uuid5(
        NAMESPACE_URL,
        f"phase-7b-retrieval::{run_id}::{query.query_id}::{rank}::{original_url}",
    )
    if original_url in deduplication.original_urls:
        snapshot_id = deduplication.original_urls[original_url]
        resolved_url = deduplication.resolved_by_original[original_url]
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            resolved_url,
            RetrievalStatus.SKIPPED,
            clock(),
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.DUPLICATE_URL,
                attempts_made=0,
                duplicate_of_snapshot_id=snapshot_id,
            ),
            None,
        )

    response, failure_status, failure_message, attempts_made = _scrape_with_retry(
        scraper_provider,
        original_url,
        retry_policy,
    )
    retrieved_at = clock()
    if response is None:
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            original_url,
            RetrievalStatus.FAILED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=failure_status,
                attempts_made=attempts_made,
                failure_message=failure_message,
            ),
            None,
        )

    content_type = _normalized_content_type(response.content_type)
    if not _is_supported_content_type(content_type):
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.SKIPPED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.UNSUPPORTED,
                content_type=content_type,
                attempts_made=attempts_made,
            ),
            None,
        )

    if response.resolved_url in deduplication.resolved_urls:
        snapshot_id = deduplication.resolved_urls[response.resolved_url]
        deduplication.original_urls[original_url] = snapshot_id
        deduplication.resolved_by_original[original_url] = response.resolved_url
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.SKIPPED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.DUPLICATE_URL,
                content_type=content_type,
                attempts_made=attempts_made,
                duplicate_of_snapshot_id=snapshot_id,
            ),
            None,
        )

    normalized_text, truncated = _truncate_text(response.text)
    if not normalized_text:
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.FAILED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.FAILED,
                content_type=content_type,
                attempts_made=attempts_made,
                failure_message="scraper returned no textual content",
            ),
            None,
        )

    content_hash = compute_sha256(normalized_text)
    if content_hash in deduplication.content_hashes:
        snapshot_id = deduplication.content_hashes[content_hash]
        deduplication.original_urls[original_url] = snapshot_id
        deduplication.resolved_urls[response.resolved_url] = snapshot_id
        deduplication.resolved_by_original[original_url] = response.resolved_url
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.SKIPPED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.DUPLICATE_CONTENT,
                content_type=content_type,
                attempts_made=attempts_made,
                duplicate_of_snapshot_id=snapshot_id,
            ),
            None,
        )

    snapshot_id = uuid5(
        NAMESPACE_URL,
        f"phase-7b-snapshot::{run_id}::{response.resolved_url}::{content_hash}",
    )
    snapshot = build_source_snapshot(
        run_id=run_id,
        retrieval_attempt_id=retrieval_attempt_id,
        snapshot_id=snapshot_id,
        source_url=response.resolved_url,
        retrieved_at=retrieved_at,
        normalized_text=normalized_text,
        truncated=truncated,
        created_at=clock(),
    )
    deduplication.original_urls[original_url] = snapshot_id
    deduplication.resolved_urls[response.resolved_url] = snapshot_id
    deduplication.content_hashes[content_hash] = snapshot_id
    deduplication.resolved_by_original[original_url] = response.resolved_url
    record = _retrieval_record(
        run_id,
        retrieval_attempt_id,
        query,
        rank,
        original_url,
        response.resolved_url,
        RetrievalStatus.RETRIEVED,
        retrieved_at,
    )
    return (
        RetrievalOutcome(
            retrieval=record,
            scrape_status=ScrapeStatus.RETRIEVED,
            content_type=content_type,
            snapshot_id=snapshot_id,
            attempts_made=attempts_made,
        ),
        snapshot,
    )


def _scrape_with_retry(
    scraper_provider: ScraperProvider,
    url: str,
    retry_policy: RetryPolicy,
) -> tuple[ScrapeResponse | None, ScrapeStatus, str | None, int]:
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            response = scraper_provider.scrape(
                ScrapeRequest(url=url, timeout_seconds=retry_policy.timeout_seconds)
            )
            if not isinstance(response, ScrapeResponse):
                raise ScraperProviderError("scraper provider returned a non-ScrapeResponse value")
            return response, ScrapeStatus.RETRIEVED, None, attempt
        except (ScraperTimeoutError, TimeoutError) as exc:
            if attempt == retry_policy.max_attempts:
                return None, ScrapeStatus.TIMEOUT, str(exc) or "scrape timed out", attempt
        except ScraperProviderError as exc:
            return None, ScrapeStatus.FAILED, str(exc) or "scrape failed", attempt
        except Exception as exc:
            return None, ScrapeStatus.FAILED, f"unexpected scraper failure: {exc}", attempt
    raise RuntimeError("retry loop ended without a result")


def _queries_for_stance(planner: PlannerOutput, stance: Stance) -> list[SearchQuery]:
    queries = sorted(
        (query for query in planner.search_queries if query.stance is stance),
        key=lambda query: query.query_round,
    )
    if len(queries) != QUERIES_PER_STANCE:
        raise ValueError(f"planner must provide exactly three {stance.value} queries")
    return queries


def _query_with_exclusions(query: SearchQuery) -> str:
    missing = [
        exclusion
        for exclusion in REQUIRED_QUERY_EXCLUSIONS
        if exclusion not in query.exclusion_parameters
    ]
    if missing:
        raise ValueError(f"query is missing required exclusions: {', '.join(missing)}")
    return f"{query.query_text} {query.exclusion_parameters}".strip()


def _retrieval_record(
    run_id: UUID,
    retrieval_attempt_id: UUID,
    query: SearchQuery,
    rank: int,
    original_url: str,
    resolved_url: str,
    status: RetrievalStatus,
    retrieved_at: datetime,
) -> RetrievalRecord:
    return RetrievalRecord(
        run_id=run_id,
        retrieval_attempt_id=retrieval_attempt_id,
        query_id=query.query_id,
        query_round=query.query_round,
        query_text=query.query_text,
        search_rank=rank,
        source_url=original_url,
        resolved_url=resolved_url,
        status=status,
        retrieved_at=retrieved_at,
    )


def _truncate_text(text: str) -> tuple[str, bool]:
    normalized = " ".join(text.split())
    matches = list(_WORD_RE.finditer(normalized))
    if len(matches) <= SNAPSHOT_WORD_LIMIT:
        return normalized, False
    return normalized[: matches[SNAPSHOT_WORD_LIMIT - 1].end()], True


def _normalized_content_type(content_type: str) -> str:
    return content_type.split(";", maxsplit=1)[0].strip().lower()


def _is_supported_content_type(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type in {
        "application/xhtml+xml",
        "application/xml",
    }


def _utc_now() -> datetime:
    return datetime.now(UTC)
