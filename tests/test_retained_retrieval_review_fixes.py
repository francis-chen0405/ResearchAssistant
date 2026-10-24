"""Retained retrieval skips known captures and reports duplicate facts accurately."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from researchassistant.agents.supportingresearcher import DeduplicationState, _retrieve_result
from researchassistant.contracts.models import SearchQuery
from researchassistant.contracts.retrieval import RetrievalOutcome
from researchassistant.contracts.scraping import RetryPolicy, ScrapeRequest, ScrapeResponse

NOW = datetime(2026, 8, 2, tzinfo=UTC)


class FamilyScraper:
    def __init__(self) -> None:
        self.calls = 0

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.calls += 1
        return ScrapeResponse(
            resolved_url=request.url,
            original_url=request.url,
            canonical_url="https://doi.org/10.1234/generated-study",
            content_type="text/html",
            text=f"Capture {self.calls} contains different text from the same generated paper.",
        )


def _query(run_id: UUID) -> SearchQuery:
    return SearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        stance="supporting",
        provider="openalex",
        intent="academic_study",
        query_round=1,
        strategy="academic_studies",
        query_text="course completion",
        exclusion_parameters="",
        created_at=NOW,
    )


def test_same_family_distinct_captures_skip_with_valid_outcome_and_explanation() -> None:
    run_id = uuid4()
    query = _query(run_id)
    scraper = FamilyScraper()
    state = DeduplicationState()
    first, snapshot = _retrieve_result(
        run_id,
        query,
        1,
        "https://example.test/study",
        scraper,
        RetryPolicy(),
        lambda: NOW,
        state,
        None,
    )
    assert snapshot is not None
    original = snapshot.model_dump_json()
    duplicate, second_snapshot = _retrieve_result(
        run_id,
        query,
        2,
        "https://example.test/study.pdf",
        scraper,
        RetryPolicy(),
        lambda: NOW,
        state,
        None,
    )
    assert first.scrape_status.value == "retrieved"
    assert second_snapshot is None and duplicate.snapshot_id is None
    assert duplicate.scrape_status.value == "duplicate_content"
    assert duplicate.duplicate_of_snapshot_id == snapshot.snapshot_id
    assert duplicate.failure_code is None and duplicate.failure_message is None
    assert duplicate.attempts_made == 1 and scraper.calls == 2
    assert RetrievalOutcome.model_validate_json(duplicate.model_dump_json()) == duplicate
    assert snapshot.model_dump_json() == original
