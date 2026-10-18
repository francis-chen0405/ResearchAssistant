"""Retained retrieval skips known captures and reports duplicate facts accurately."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import test_phase9 as fixture

import researchassistant.research.historical_execution as history
from researchassistant.agents.supportingresearcher import DeduplicationState, _retrieve_result
from researchassistant.contracts.models import EvidenceTrailOutcome, SearchQuery
from researchassistant.contracts.retrieval import RetrievalOutcome
from researchassistant.contracts.scraping import RetryPolicy, ScrapeRequest, ScrapeResponse
from researchassistant.contracts.search import SearchRequest, SearchResponse
from researchassistant.storage.store import read_planner_output


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
        created_at=fixture.NOW,
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
        lambda: fixture.NOW,
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
        lambda: fixture.NOW,
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
    outcome, explanation, failure = history._mvp10_outcome_for_retrieval(
        duplicate,
        None,
        {},
        {},
        {},
    )
    assert outcome is EvidenceTrailOutcome.DUPLICATE and "source family" in explanation
    assert failure is None and snapshot.model_dump_json() == original


class NextRoundSearch(fixture.FakeSearchProvider):
    def search(self, request: SearchRequest) -> SearchResponse:
        response = super().search(request)
        return response.model_copy(
            update={
                "results": tuple(
                    result.model_copy(
                        update={
                            "original_url": result.original_url.replace(
                                "research.test", "round-two.research.test"
                            )
                        }
                    )
                    for result in response.results
                )
            }
        )


@pytest.mark.parametrize("alias", ["original", "resolved", "completed_duplicate"])
def test_completed_round_aliases_skip_before_scraping(tmp_path: Path, alias: str) -> None:
    complete = fixture._run(tmp_path)
    assert complete.status is fixture.ProviderRunStatus.RELEASED
    pair = complete.researcher_result
    assert pair is not None and pair.supporting.retrieval_batch is not None
    batch = pair.supporting.retrieval_batch
    snapshot = batch.snapshots[0]
    url = snapshot.original_url if alias == "original" else snapshot.source_url
    if alias == "completed_duplicate":
        url = next(
            outcome.retrieval.source_url
            for outcome in batch.outcomes
            if outcome.duplicate_of_snapshot_id is not None
        )
    assert url is not None
    state = history._seed_mvp11_deduplication(pair)
    scraper = FamilyScraper()
    before = Path(complete.db_path).read_bytes()
    outcome, captured = _retrieve_result(
        complete.run_id,
        _query(complete.run_id),
        1,
        url,
        scraper,
        RetryPolicy(),
        lambda: fixture.NOW,
        state,
        None,
    )
    assert captured is None and scraper.calls == outcome.attempts_made == 0
    assert outcome.scrape_status.value == "duplicate_url"
    assert outcome.duplicate_of_snapshot_id in {s.snapshot_id for s in batch.snapshots}
    assert Path(complete.db_path).read_bytes() == before


def test_completed_second_round_is_seeded_alongside_first(tmp_path: Path) -> None:
    first = fixture._run(tmp_path / "first")
    second = fixture._run(
        tmp_path / "second",
        run_id=first.run_id,
        search=NextRoundSearch(),
    )
    assert first.researcher_result is not None and second.researcher_result is not None
    state = history._seed_mvp11_deduplication(first.researcher_result, second.researcher_result)
    scraper = FamilyScraper()
    for pair in (first.researcher_result, second.researcher_result):
        for side in (pair.supporting, pair.opposing):
            assert side.retrieval_batch is not None
            for snapshot in side.retrieval_batch.snapshots:
                outcome, captured = _retrieve_result(
                    first.run_id,
                    _query(first.run_id),
                    1,
                    snapshot.source_url,
                    scraper,
                    RetryPolicy(),
                    lambda: fixture.NOW,
                    state,
                    None,
                )
                assert captured is None and outcome.attempts_made == 0
                assert outcome.duplicate_of_snapshot_id == snapshot.snapshot_id
    assert scraper.calls == 0
    # A new URL still reaches the scraper; seeding does not disable retrieval.
    _retrieve_result(
        first.run_id,
        _query(first.run_id),
        1,
        "https://new.example.test/source",
        scraper,
        RetryPolicy(),
        lambda: fixture.NOW,
        state,
        None,
    )
    assert scraper.calls == 1


@pytest.mark.parametrize("kind", ["duplicate_content", "duplicate_url", "mixed"])
def test_governor_counts_all_typed_duplicate_outcomes(tmp_path: Path, kind: str) -> None:
    complete = fixture._run(tmp_path)
    pair = complete.researcher_result
    assert pair is not None and complete.analysis_result is not None
    payload = pair.model_dump(mode="json")
    statuses = []
    for side in ("supporting", "opposing"):
        for index, outcome in enumerate(payload[side]["retrieval_batch"]["outcomes"]):
            if outcome["duplicate_of_snapshot_id"] is not None:
                outcome["scrape_status"] = (
                    "duplicate_url"
                    if kind == "mixed" and index % 2
                    else "duplicate_content"
                    if kind == "mixed"
                    else kind
                )
            statuses.append(outcome["scrape_status"])
    pair = history.ResearcherPairResult.model_validate(payload)
    before = Path(complete.db_path).read_bytes()
    result = history._mvp11_governor_input(
        complete.db_path,
        complete.run_id,
        (pair, pair),
        complete.analysis_result,
        history.ProviderOrchestrationConfig(),
        lambda: fixture.NOW,
    )
    assert result.round_two_result_count == len(statuses) == 18
    assert result.round_two_duplicate_count == 16
    assert Path(complete.db_path).read_bytes() == before
    assert read_planner_output(complete.db_path, complete.run_id).run_id == complete.run_id
