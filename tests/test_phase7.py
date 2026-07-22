from __future__ import annotations

import socket
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from agents.opposingresearcher import retrieve_opposing
from agents.supportingresearcher import (
    SNAPSHOT_WORD_LIMIT,
    BalancedRetrievalResult,
    RetrievalOutcome,
    retrieve_balanced,
    retrieve_supporting,
)
from models import (
    REQUIRED_QUERY_EXCLUSIONS,
    AmbiguityRecord,
    ClaimDefinition,
    PlannerOutput,
    RetrievalStatus,
    SearchQuery,
    SourceSnapshot,
    Stance,
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
from providers.search import (
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
EXCLUSIONS = " ".join(REQUIRED_QUERY_EXCLUSIONS)


class FakeSearchProvider:
    def __init__(self, responses: list[list[str]] | None = None) -> None:
        self.requests: list[SearchRequest] = []
        self.responses = responses

    def search(self, request: SearchRequest) -> SearchResponse:
        call_number = len(self.requests)
        self.requests.append(request)
        urls = (
            self.responses[call_number]
            if self.responses is not None and call_number < len(self.responses)
            else [f"https://original.example/{call_number}/{rank}" for rank in range(1, 4)]
        )
        return SearchResponse(
            results=[
                SearchResult(original_url=url, title=f"Result {rank}")
                for rank, url in enumerate(urls, 1)
            ]
        )


class FakeScraperProvider:
    def __init__(
        self,
        behaviors: dict[str, list[ScrapeResponse | Exception]] | None = None,
    ) -> None:
        self.requests: list[ScrapeRequest] = []
        self.behaviors = behaviors or {}
        self.calls_by_url: dict[str, int] = defaultdict(int)

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.requests.append(request)
        call_index = self.calls_by_url[request.url]
        self.calls_by_url[request.url] += 1
        if request.url in self.behaviors:
            behavior = self.behaviors[request.url][call_index]
            if isinstance(behavior, Exception):
                raise behavior
            return behavior
        suffix = request.url.rsplit("/", maxsplit=1)[-1]
        return ScrapeResponse(
            resolved_url=request.url.replace("original.example", "resolved.example"),
            content_type="text/html; charset=utf-8",
            text=f"unique source {request.url} content {suffix}",
        )


def _planner() -> PlannerOutput:
    run_id = uuid4()
    queries = []
    for stance in (Stance.SUPPORTING, Stance.OPPOSING):
        for query_round in range(1, 4):
            queries.append(
                SearchQuery(
                    run_id=run_id,
                    query_id=uuid4(),
                    stance=stance,
                    query_round=query_round,
                    strategy=f"{stance.value} strategy {query_round}",
                    query_text=f"{stance.value} query {query_round}",
                    exclusion_parameters=EXCLUSIONS,
                    created_at=NOW,
                )
            )
    return PlannerOutput(
        run_id=run_id,
        claim_definition=ClaimDefinition(
            run_id=run_id,
            claim_text="A test claim",
            population="test population",
            jurisdiction="global",
            time_period="current",
            comparison_baseline="baseline",
            intervention_or_exposure="exposure",
            causal_or_comparative_meaning="comparison",
            created_at=NOW,
        ),
        ambiguities=[
            AmbiguityRecord(
                run_id=run_id,
                ambiguity_id=uuid4(),
                description="test ambiguity",
                impact="test impact",
                created_at=NOW,
            )
        ],
        search_queries=queries,
        planner_prompt_version="fixture-planner-v1",
        planner_model_name="fixture",
        planned_at=NOW,
    )


def _response(
    url: str,
    *,
    resolved_url: str | None = None,
    content_type: str = "text/html",
    text: str = "source text",
) -> ScrapeResponse:
    return ScrapeResponse(
        resolved_url=resolved_url or url,
        content_type=content_type,
        text=text,
    )


def test_provider_contracts_are_protocol_based() -> None:
    assert isinstance(FakeSearchProvider(), SearchProvider)
    assert isinstance(FakeScraperProvider(), ScraperProvider)


def test_balanced_retrieval_records_exactly_eighteen_intended_attempts() -> None:
    search = FakeSearchProvider()
    scraper = FakeScraperProvider()

    result = retrieve_balanced(_planner(), search, scraper, clock=lambda: NOW)

    assert isinstance(result, BalancedRetrievalResult)
    assert result.intended_attempt_count == 18
    assert len(result.supporting.outcomes) == len(result.opposing.outcomes) == 9
    assert len(search.requests) == 6
    assert all(request.limit == 3 for request in search.requests)
    assert all(
        all(exclusion in request.query_text for exclusion in REQUIRED_QUERY_EXCLUSIONS)
        for request in search.requests
    )


def test_retrieval_rejects_substring_exclusion_lookalikes() -> None:
    planner = _planner()
    malformed_query = planner.search_queries[0].model_copy(
        update={
            "exclusion_parameters": " ".join(
                f"{exclusion}.evil" for exclusion in REQUIRED_QUERY_EXCLUSIONS
            )
        }
    )
    malformed_planner = planner.model_copy(
        update={"search_queries": [malformed_query, *planner.search_queries[1:]]}
    )
    search = FakeSearchProvider()

    with pytest.raises(ValueError, match="missing required exclusions"):
        retrieve_supporting(
            malformed_planner,
            search,
            FakeScraperProvider(),
            clock=lambda: NOW,
        )

    assert search.requests == []


def test_ranks_rounds_and_original_resolved_urls_are_preserved() -> None:
    result = retrieve_balanced(
        _planner(), FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )

    for batch in (result.supporting, result.opposing):
        assert [
            (item.retrieval.query_round, item.retrieval.search_rank) for item in batch.outcomes
        ] == [(query_round, rank) for query_round in range(1, 4) for rank in range(1, 4)]
        assert all("original.example" in item.retrieval.source_url for item in batch.outcomes)
        assert all("resolved.example" in item.retrieval.resolved_url for item in batch.outcomes)
        assert all(item.retrieval.retrieved_at == NOW for item in batch.outcomes)
        assert all(item.retrieval.retrieved_at.utcoffset() is not None for item in batch.outcomes)


def test_duplicate_original_url_is_not_scraped_or_snapshotted_twice() -> None:
    duplicate = "https://original.example/duplicate"
    responses = [[duplicate, duplicate, "https://original.example/unique"]]
    search = FakeSearchProvider(responses=responses)
    scraper = FakeScraperProvider()

    result = retrieve_supporting(_planner(), search, scraper, clock=lambda: NOW)

    assert scraper.calls_by_url[duplicate] == 1
    assert result.outcomes[1].scrape_status is ScrapeStatus.DUPLICATE_URL
    assert result.outcomes[1].duplicate_of_snapshot_id == result.outcomes[0].snapshot_id
    assert len({snapshot.snapshot_id for snapshot in result.snapshots}) == len(result.snapshots)


def test_resolved_url_deduplication_crosses_stance_boundary() -> None:
    first = "https://one.example/source"
    second = "https://two.example/source"
    responses = [
        [first, "https://s.example/2", "https://s.example/3"],
        ["https://s.example/4", "https://s.example/5", "https://s.example/6"],
        ["https://s.example/7", "https://s.example/8", "https://s.example/9"],
        [second, "https://o.example/2", "https://o.example/3"],
        ["https://o.example/4", "https://o.example/5", "https://o.example/6"],
        ["https://o.example/7", "https://o.example/8", "https://o.example/9"],
    ]
    shared_resolved = "https://resolved.example/shared"
    scraper = FakeScraperProvider(
        {
            first: [_response(first, resolved_url=shared_resolved, text="first unique content")],
            second: [_response(second, resolved_url=shared_resolved, text="different content")],
        }
    )

    result = retrieve_balanced(
        _planner(), FakeSearchProvider(responses), scraper, clock=lambda: NOW
    )

    duplicate = result.opposing.outcomes[0]
    assert duplicate.scrape_status is ScrapeStatus.DUPLICATE_URL
    assert duplicate.retrieval.source_url == second
    assert duplicate.retrieval.resolved_url == shared_resolved
    assert duplicate.duplicate_of_snapshot_id == result.supporting.outcomes[0].snapshot_id


def test_duplicate_content_does_not_create_a_second_snapshot() -> None:
    first = "https://original.example/content-a"
    second = "https://original.example/content-b"
    responses = [[first, second, "https://original.example/content-c"]]
    scraper = FakeScraperProvider(
        {
            first: [_response(first, text="identical normalized content")],
            second: [_response(second, text="identical   normalized\ncontent")],
        }
    )

    result = retrieve_supporting(
        _planner(), FakeSearchProvider(responses), scraper, clock=lambda: NOW
    )

    assert result.outcomes[1].scrape_status is ScrapeStatus.DUPLICATE_CONTENT
    assert result.outcomes[1].duplicate_of_snapshot_id == result.outcomes[0].snapshot_id
    assert len(result.snapshots) == 8


def test_content_hash_deduplication_crosses_stance_boundary() -> None:
    responses = [
        ["https://s.example/1", "https://s.example/2", "https://s.example/3"],
        ["https://s.example/4", "https://s.example/5", "https://s.example/6"],
        ["https://s.example/7", "https://s.example/8", "https://s.example/9"],
        ["https://o.example/1", "https://o.example/2", "https://o.example/3"],
        ["https://o.example/4", "https://o.example/5", "https://o.example/6"],
        ["https://o.example/7", "https://o.example/8", "https://o.example/9"],
    ]
    scraper = FakeScraperProvider(
        {
            "https://s.example/1": [_response("https://s.example/1", text="same content")],
            "https://o.example/1": [_response("https://o.example/1", text="same   content")],
        }
    )

    result = retrieve_balanced(
        _planner(), FakeSearchProvider(responses), scraper, clock=lambda: NOW
    )

    duplicate = result.opposing.outcomes[0]
    assert duplicate.scrape_status is ScrapeStatus.DUPLICATE_CONTENT
    assert duplicate.duplicate_of_snapshot_id == result.supporting.outcomes[0].snapshot_id


def test_timeout_is_retried_then_succeeds() -> None:
    url = "https://original.example/retry"
    responses = [[url, "https://original.example/2", "https://original.example/3"]]
    scraper = FakeScraperProvider(
        {url: [ScraperTimeoutError("first timeout"), _response(url, text="retrieved after retry")]}
    )

    result = retrieve_supporting(
        _planner(),
        FakeSearchProvider(responses),
        scraper,
        retry_policy=RetryPolicy(max_attempts=2, timeout_seconds=2.5),
        clock=lambda: NOW,
    )

    assert result.outcomes[0].scrape_status is ScrapeStatus.RETRIEVED
    assert result.outcomes[0].attempts_made == 2
    assert scraper.requests[0].timeout_seconds == 2.5


def test_exhausted_timeout_and_failed_scrape_are_explicit() -> None:
    timeout_url = "https://original.example/timeout"
    failed_url = "https://original.example/failed"
    responses = [[timeout_url, failed_url, "https://original.example/ok"]]
    scraper = FakeScraperProvider(
        {
            timeout_url: [ScraperTimeoutError("slow"), ScraperTimeoutError("still slow")],
            failed_url: [ScraperProviderError("blocked by source")],
        }
    )

    result = retrieve_supporting(
        _planner(), FakeSearchProvider(responses), scraper, clock=lambda: NOW
    )

    timeout, failed = result.outcomes[:2]
    assert (timeout.scrape_status, timeout.attempts_made) == (ScrapeStatus.TIMEOUT, 2)
    assert timeout.retrieval.status is RetrievalStatus.FAILED
    assert timeout.failure_message == "still slow"
    assert (failed.scrape_status, failed.attempts_made) == (ScrapeStatus.FAILED, 1)
    assert failed.failure_message == "blocked by source"
    assert timeout.snapshot_id is failed.snapshot_id is None


@pytest.mark.parametrize("content_type", ["application/pdf", "application/octet-stream"])
def test_pdf_and_binary_content_are_explicitly_unsupported(content_type: str) -> None:
    url = "https://original.example/unsupported"
    responses = [[url, "https://original.example/2", "https://original.example/3"]]
    scraper = FakeScraperProvider(
        {url: [_response(url, content_type=content_type, text="untrusted binary-like payload")]}
    )

    result = retrieve_supporting(
        _planner(), FakeSearchProvider(responses), scraper, clock=lambda: NOW
    )

    outcome = result.outcomes[0]
    assert outcome.scrape_status is ScrapeStatus.UNSUPPORTED
    assert outcome.content_type == content_type
    assert outcome.retrieval.status is RetrievalStatus.SKIPPED
    assert outcome.snapshot_id is None


def test_supported_content_type_is_normalized_and_recorded() -> None:
    url = "https://original.example/plain"
    responses = [[url, "https://original.example/2", "https://original.example/3"]]
    scraper = FakeScraperProvider(
        {url: [_response(url, content_type="Text/Plain; charset=UTF-8", text="plain text body")]}
    )

    result = retrieve_supporting(
        _planner(), FakeSearchProvider(responses), scraper, clock=lambda: NOW
    )

    assert result.outcomes[0].content_type == "text/plain"
    assert result.outcomes[0].scrape_status is ScrapeStatus.RETRIEVED


def test_snapshot_exists_before_downstream_consumer_runs() -> None:
    observed: list[UUID] = []

    def consume(snapshot: SourceSnapshot) -> None:
        assert snapshot.snapshot_sha256
        assert snapshot.normalized_text
        observed.append(snapshot.snapshot_id)

    result = retrieve_supporting(
        _planner(),
        FakeSearchProvider(),
        FakeScraperProvider(),
        clock=lambda: NOW,
        snapshot_consumer=consume,
    )

    assert observed == [snapshot.snapshot_id for snapshot in result.snapshots]


def test_snapshot_text_is_limited_to_first_three_thousand_words() -> None:
    url = "https://original.example/long"
    text = " ".join(f"word{index}" for index in range(SNAPSHOT_WORD_LIMIT + 5))
    responses = [[url, "https://original.example/2", "https://original.example/3"]]
    scraper = FakeScraperProvider({url: [_response(url, text=text)]})

    result = retrieve_supporting(
        _planner(), FakeSearchProvider(responses), scraper, clock=lambda: NOW
    )
    snapshot = result.snapshots[0]

    assert snapshot.word_count == SNAPSHOT_WORD_LIMIT
    assert snapshot.truncated is True
    assert snapshot.normalized_text.endswith("word2999")
    assert "word3000" not in snapshot.normalized_text


def test_source_snapshots_are_immutable_after_creation() -> None:
    result = retrieve_supporting(
        _planner(), FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )

    with pytest.raises(ValidationError):
        result.snapshots[0].normalized_text = "tampered"


def test_short_search_result_set_fails_explicitly() -> None:
    search = FakeSearchProvider([["https://original.example/only-one"]])

    with pytest.raises(SearchProviderError, match="expected at least three"):
        retrieve_supporting(_planner(), search, FakeScraperProvider(), clock=lambda: NOW)


def test_malformed_provider_outputs_fail_at_the_typed_boundary() -> None:
    class MalformedSearchProvider:
        def search(self, request: SearchRequest) -> SearchResponse:
            return {"results": []}  # type: ignore[return-value]

    with pytest.raises(SearchProviderError, match="non-SearchResponse"):
        retrieve_supporting(
            _planner(), MalformedSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
        )

    class MalformedScraperProvider:
        def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
            return {"resolved_url": request.url}  # type: ignore[return-value]

    result = retrieve_supporting(
        _planner(), FakeSearchProvider(), MalformedScraperProvider(), clock=lambda: NOW
    )
    assert all(outcome.scrape_status is ScrapeStatus.FAILED for outcome in result.outcomes)
    assert all(
        outcome.failure_message == "scraper provider returned a non-ScrapeResponse value"
        for outcome in result.outcomes
    )


def test_retrieval_outcome_rejects_contradictory_status_metadata() -> None:
    result = retrieve_supporting(
        _planner(), FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )
    valid = result.outcomes[0]

    with pytest.raises(ValidationError, match="retrieved scrape outcomes require retrieved"):
        RetrievalOutcome.model_validate(
            {
                **valid.model_dump(),
                "retrieval": {
                    **valid.retrieval.model_dump(),
                    "status": RetrievalStatus.SKIPPED,
                },
            }
        )


def test_retrieval_ids_and_timestamps_are_deterministic_with_fixed_inputs() -> None:
    planner = _planner()
    first = retrieve_balanced(
        planner, FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )
    second = retrieve_balanced(
        planner, FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )

    first_records = [*first.supporting.outcomes, *first.opposing.outcomes]
    second_records = [*second.supporting.outcomes, *second.opposing.outcomes]
    assert [item.retrieval.retrieval_attempt_id for item in first_records] == [
        item.retrieval.retrieval_attempt_id for item in second_records
    ]
    assert [item.retrieval.retrieved_at for item in first_records] == [NOW] * 18
    assert [snapshot.snapshot_id for snapshot in first.supporting.snapshots] == [
        snapshot.snapshot_id for snapshot in second.supporting.snapshots
    ]


def test_stance_specific_entry_points_keep_equal_fixed_depth() -> None:
    planner = _planner()
    supporting = retrieve_supporting(
        planner, FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )
    opposing = retrieve_opposing(
        planner, FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )

    assert supporting.stance is Stance.SUPPORTING
    assert opposing.stance is Stance.OPPOSING
    assert supporting.intended_attempt_count == opposing.intended_attempt_count == 9


def test_normal_retrieval_uses_only_injected_offline_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("real network access is forbidden in Phase 7B tests")

    monkeypatch.setattr(socket, "create_connection", reject_network)

    result = retrieve_balanced(
        _planner(), FakeSearchProvider(), FakeScraperProvider(), clock=lambda: NOW
    )

    assert result.intended_attempt_count == 18
