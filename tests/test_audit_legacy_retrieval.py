"""Offline concurrency regressions for historical cross-stance source deduplication."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Event, Lock
from uuid import UUID, uuid4

from agents.supportingresearcher import DeduplicationState, _retrieve_result
from models import REQUIRED_QUERY_EXCLUSIONS, SearchQuery, Stance
from providers.scraper import (
    RetryPolicy,
    ScrapeRequest,
    ScrapeResponse,
    ScraperProviderError,
    ScrapeStatus,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)
SHARED_URL = "https://example.org/shared-source"


def _query(stance: Stance, run_id: UUID | None = None) -> SearchQuery:
    resolved_run_id = run_id if run_id is not None else uuid4()
    return SearchQuery(
        run_id=resolved_run_id,
        query_id=uuid4(),
        stance=stance,
        query_round=1,
        strategy=f"{stance.value} source strategy",
        query_text=f"{stance.value} evidence query",
        exclusion_parameters=" ".join(REQUIRED_QUERY_EXCLUSIONS),
        created_at=NOW,
    )


class _CountingScraper:
    def __init__(self) -> None:
        self.calls = 0
        self._lock = Lock()

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        with self._lock:
            self.calls += 1
        return ScrapeResponse(
            resolved_url=request.url,
            content_type="text/plain",
            text=(
                f"A sufficiently detailed source sentence for {request.url} "
                "and evidence validation."
            ),
        )


class _HeldFirstScraper(_CountingScraper):
    def __init__(self) -> None:
        super().__init__()
        self.first_entered = Event()
        self.release_first = Event()
        self.second_entered = Event()

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        with self._lock:
            self.calls += 1
            call = self.calls
        if call == 1:
            self.first_entered.set()
            if not self.release_first.wait(timeout=5):
                raise TimeoutError("first scrape was not released")
        else:
            self.second_entered.set()
        return ScrapeResponse(
            resolved_url=request.url,
            content_type="text/plain",
            text=(
                f"A sufficiently detailed source sentence for {request.url} "
                "and evidence validation."
            ),
        )


class _FailOnceScraper(_CountingScraper):
    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        with self._lock:
            self.calls += 1
            call = self.calls
        if call == 1:
            raise ScraperProviderError("temporary_failure", "controlled test failure")
        return ScrapeResponse(
            resolved_url=request.url,
            content_type="text/plain",
            text=(
                f"A sufficiently detailed source sentence for {request.url} "
                "and evidence validation."
            ),
        )


def _retrieve(
    query: SearchQuery,
    scraper: _CountingScraper,
    deduplication: DeduplicationState,
    url: str,
    rank: int = 1,
) -> tuple[object, object]:
    return _retrieve_result(
        query.run_id,
        query,
        rank,
        url,
        scraper,
        RetryPolicy(max_attempts=1),
        lambda: NOW,
        deduplication,
        None,
    )


def test_simultaneous_cross_stance_duplicate_url_is_scraped_once() -> None:
    run_id = uuid4()
    scraper = _HeldFirstScraper()
    deduplication = DeduplicationState()
    queries = (_query(Stance.SUPPORTING, run_id), _query(Stance.OPPOSING, run_id))
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_retrieve, queries[0], scraper, deduplication, SHARED_URL)
        assert scraper.first_entered.wait(timeout=2)
        second = executor.submit(_retrieve, queries[1], scraper, deduplication, SHARED_URL)
        duplicate_scrape_started = scraper.second_entered.wait(timeout=0.1)
        scraper.release_first.set()
        first_outcome, first_snapshot = first.result(timeout=2)
        second_outcome, second_snapshot = second.result(timeout=2)

    assert not duplicate_scrape_started
    assert scraper.calls == 1
    assert first_snapshot is not None
    assert second_snapshot is None
    assert {first_outcome.scrape_status, second_outcome.scrape_status} == {
        ScrapeStatus.RETRIEVED,
        ScrapeStatus.DUPLICATE_URL,
    }


def test_failed_scrape_releases_inflight_claim_for_a_later_attempt() -> None:
    query = _query(Stance.SUPPORTING)
    scraper = _FailOnceScraper()
    deduplication = DeduplicationState()

    first, first_snapshot = _retrieve(query, scraper, deduplication, SHARED_URL)
    second, second_snapshot = _retrieve(query, scraper, deduplication, SHARED_URL, rank=2)

    assert first.scrape_status is ScrapeStatus.FAILED
    assert first_snapshot is None
    assert second.scrape_status is ScrapeStatus.RETRIEVED
    assert second_snapshot is not None
    assert scraper.calls == 2


def test_different_urls_remain_acquirable_in_parallel() -> None:
    deduplication = DeduplicationState()
    barrier = Barrier(2)

    class _ParallelScraper(_CountingScraper):
        def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
            barrier.wait(timeout=2)
            return super().scrape(request)

    parallel_scraper = _ParallelScraper()
    run_id = uuid4()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            future.result(timeout=3)
            for future in (
                executor.submit(
                    _retrieve,
                    _query(Stance.SUPPORTING, run_id),
                    parallel_scraper,
                    deduplication,
                    "https://example.org/first",
                ),
                executor.submit(
                    _retrieve,
                    _query(Stance.OPPOSING, run_id),
                    parallel_scraper,
                    deduplication,
                    "https://example.org/second",
                ),
            )
        )

    assert parallel_scraper.calls == 2
    assert all(snapshot is not None for _, snapshot in results)
