from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import agents.v2_acquisition as v2_acquisition
from agents.researcher import build_source_snapshot
from agents.v2_acquisition import (
    V2_ACQUISITION_PROBE_ARTIFACT_KEY,
    probe_snapshot,
    run_v2_acquisition_probe,
)
from agents.v2_discovery import (
    V2DiscoveryResponse,
    cluster_discovery_items,
    normalize_discovery_responses,
)
from providers.acquisition import AcquisitionFailureCode
from providers.scraper import (
    ScrapeRequest,
    ScrapeResponse,
    ScraperProviderError,
    VerifiedAcquisitionPreflight,
)
from providers.search import SearchResult
from researchassistant.common.utils import count_words
from researchassistant.contracts.model_contracts import SelectedSentenceRange
from researchassistant.contracts.models import (
    V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
    V2_ACQUISITION_PROBE_POLICY_IDENTITY,
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    ScoutBatchAudit,
    ScoutItem,
    Stage,
    V2AcquisitionPolicy,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2PipelineIdentity,
    V2ProbePassage,
    V2RoundOneSearchQuery,
    V2VerbatimQuoteSelection,
)
from researchassistant.evidence.evidence_core import (
    CURRENT_QUOTE_LENGTH_POLICY,
    fresh_numbered_source_text,
    fresh_sentence_spans,
    has_statistical_markers,
    selected_segments_from_selection,
)
from researchassistant.storage.store import init_db, insert_run, insert_v2_pipeline_identity

NOW = datetime(2026, 8, 20, tzinfo=UTC)


class FixtureScraper:
    def __init__(self, responses: dict[str, ScrapeResponse | Exception]) -> None:
        self.responses = responses
        self.requests: list[ScrapeRequest] = []

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.requests.append(request)
        response = self.responses[request.url]
        if isinstance(response, Exception):
            raise response
        return response


def _response(url: str, text: str) -> ScrapeResponse:
    return ScrapeResponse(
        resolved_url=url,
        original_url=url,
        content_type="text/plain",
        text=text,
        provider_name="fixture",
        provider_version="v1",
    )


def _discovery(
    run_id: UUID, urls: tuple[str, ...], decisions: tuple[str, ...]
) -> V2DiscoveryScoutOutput:
    query = V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.EXA,
        strategy="direct_evidence",
        query_text="public evidence",
        created_at=NOW,
    )
    items = normalize_discovery_responses(
        run_id=run_id,
        directions=ResearchDirections(),
        responses=(
            V2DiscoveryResponse(
                query=query,
                results=tuple(
                    SearchResult(original_url=url, title=f"Source {index}", rank=index + 1)
                    for index, url in enumerate(urls)
                ),
            ),
        ),
        discovered_at=NOW,
    )
    return V2DiscoveryScoutOutput(
        run_id=run_id,
        directions=ResearchDirections(),
        items=items,
        clusters=cluster_discovery_items(items),
        scout_batches=(
            ScoutBatch(
                run_id=run_id,
                items=tuple(
                    ScoutItem(item_id=item.item_id, decision=decision, rationale="fixture")
                    for item, decision in zip(items, decisions, strict=True)
                ),
            ),
        ),
        scout_audits=(ScoutBatchAudit(batch_number=1, attempted_calls=1),),
        completed_at=NOW,
    )


def _prepare_db(tmp_path: Path, run_id: UUID) -> str:
    db_path = str(tmp_path / "phase5.sqlite3")
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim="A public claim.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)
    return db_path


def test_acquisition_routes_wigolo_then_verified_firecrawl_and_persists_survivor(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    url = "https://example.org/source"
    output = _discovery(run_id, (url,), ("retrieve",))
    db_path = _prepare_db(tmp_path, run_id)
    primary = FixtureScraper(
        {
            url: ScraperProviderError(
                AcquisitionFailureCode.CHALLENGE,
                "challenge",
                verified_preflight=VerifiedAcquisitionPreflight(
                    original_url=url,
                    resolved_url=url,
                    media_type="text/html",
                ),
            )
        }
    )
    fallback = FixtureScraper(
        {
            url: _response(
                url,
                "The study sampled 640 plate reads and reported a 42% increase in correct matches "
                "across departments. Analysts compared the records over three years and describe "
                "how a published method controls for missing records. In conclusion, these "
                "findings support careful evaluation and transparent reporting.",
            )
        }
    )

    result = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=output,
        wigolo_provider=primary,
        firecrawl_provider=fallback,
        clock=lambda: NOW,
    )

    assert not result.resumed
    assert [attempt.provider.value for attempt in result.output.attempts] == ["wigolo", "firecrawl"]
    assert result.output.attempts[0].succeeded is False
    assert fallback.requests[0].verified_preflight is not None
    assert len(result.output.acquisitions) == len(result.output.survivors) == 1
    probe = result.output.probes[0]
    assert probe.succeeded and 2 <= len(probe.passages) <= 5
    for passage in probe.passages:
        snapshot = result.output.acquisitions[0].snapshot
        assert snapshot.normalized_text[passage.start_char : passage.end_char] == passage.text
        assert passage.snapshot_sha256 == snapshot.snapshot_sha256

    resumed = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=output,
        wigolo_provider=None,
        clock=lambda: NOW,
    )
    assert resumed.resumed and resumed.output == result.output
    assert V2_ACQUISITION_PROBE_ARTIFACT_KEY == "phase-5-acquisition-probe"


def test_alternate_url_follows_eligible_primary_failure_and_skip_is_not_acquired(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    preferred = "https://example.org/preferred"
    alternate = "https://mirror.example.org/alternate"
    output = _discovery(
        run_id, (preferred, alternate, "https://example.org/skip"), ("retrieve", "maybe", "skip")
    )
    # The first two discovery records are conservatively clustered by exact title.
    clustered = output.model_copy(
        update={
            "clusters": (
                output.clusters[0].model_copy(
                    update={
                        "alternate_urls": (alternate,),
                        "item_ids": tuple(item.item_id for item in output.items[:2]),
                    }
                ),
                output.clusters[2],
            )
        }
    )
    db_path = _prepare_db(tmp_path, run_id)
    primary = FixtureScraper(
        {
            preferred: ScraperProviderError(AcquisitionFailureCode.CONNECTION, "offline"),
            alternate: _response(
                alternate, "Opening text. More useful evidence with 7%. Conclusion follows."
            ),
        }
    )

    result = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=clustered,
        wigolo_provider=primary,
        clock=lambda: NOW,
    )

    assert [request.url for request in primary.requests] == [preferred, alternate]
    assert len(result.output.acquisitions) == 1
    assert result.output.acquisitions[0].snapshot.source_url == alternate


def test_probe_low_overlap_fallback_is_stable() -> None:
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/source",
        retrieved_at=NOW,
        normalized_text=(
            "Abstract opening. Plain unrelated material. Final conclusion without shared keywords. "
            "Researchers reviewed administrative records from several regional departments, "
            "comparing source documents with policy archives over a six-year interval. The report "
            "outlines study design, limitations, and future analysis without addressing the "
            "current question directly."
        ),
        truncated=False,
        created_at=NOW,
    )
    first = probe_snapshot(snapshot=snapshot, cluster_id=uuid4())
    second = probe_snapshot(snapshot=snapshot, cluster_id=first.cluster_id)
    assert first == second
    assert first.succeeded and first.passages
    assert {"claim_fit", "evidence_quality", "factual_claim", "ledger_record_id"}.isdisjoint(
        V2ProbePassage.model_fields
    )


def test_fresh_sentence_segmentation_keeps_numbers_abbreviations_and_urls_intact() -> None:
    text = (
        "The threshold was 1.6 percent in the U.S. under current rules. "
        "Web 2.0 changed access. "
        "See https://doi.org/10.1000/example.42 for details. The rule remains."
    )

    spans = fresh_sentence_spans(text)

    assert [span.text for span in spans] == [
        "The threshold was 1.6 percent in the U.S. under current rules.",
        "Web 2.0 changed access.",
        "See https://doi.org/10.1000/example.42 for details.",
        "The rule remains.",
    ]
    assert all(text[span.start_char : span.end_char] == span.text for span in spans)


def test_v2_sentence_range_selection_uses_fresh_exact_boundaries() -> None:
    text = (
        "The threshold was 1.6 percent in the U.S. under current rules. "
        "The second sentence follows."
    )
    selection = V2VerbatimQuoteSelection(
        selected_sentence_ranges=(SelectedSentenceRange(start_sentence=1, end_sentence=1),)
    )

    assert selected_segments_from_selection(text, selection) == [
        "The threshold was 1.6 percent in the U.S. under current rules."
    ]
    assert fresh_numbered_source_text(text) == (
        "[1] The threshold was 1.6 percent in the U.S. under current rules.\n"
        "[2] The second sentence follows."
    )


def test_probe_does_not_select_page_controls_or_url_when_substantive_text_exists() -> None:
    text = (
        "Home. Page 1 of 4. https://example.org/report. Cookie settings and sign in. "
        "The Swedish authority states that household camera use is exempt only in narrow "
        "circumstances, depending on the purpose, area monitored, and people recorded. "
        "The guidance explains that public spaces and commercial purposes fall outside "
        "the exemption and require a separate assessment."
    )
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/report",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=False,
        created_at=NOW,
    )

    result = probe_snapshot(snapshot=snapshot, cluster_id=uuid4())

    assert result.succeeded
    assert result.passages
    assert all("https://" not in passage.text for passage in result.passages)
    assert all("Page 1 of 4" not in passage.text for passage in result.passages)
    assert all("Cookie settings" not in passage.text for passage in result.passages)


@pytest.mark.parametrize(
    "text",
    (
        "OSF",
        "A required part of this site couldn’t load. This may be due to a browser extension, "
        "network issues, or browser settings. Please check your connection, disable any ad "
        "blockers, or try using a different browser.",
    ),
)
def test_probe_rejects_non_substantive_and_error_shell_only_snapshots(text: str) -> None:
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/source",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=False,
        created_at=NOW,
    )

    result = probe_snapshot(snapshot=snapshot, cluster_id=uuid4())

    assert result.succeeded is False
    assert result.passages == ()
    assert result.failure is not None


@pytest.mark.parametrize(
    ("text", "should_probe_succeed"),
    (
        (
            "The report describes unequal camera deployment in neighborhoods across the city, "
            "but does not compare outcomes for residents or explain intent.",
            False,
        ),
        (
            "The study found a 12% higher rate of stops involving Black drivers using ALPR "
            "alerts across three cities after accounting for population differences.",
            True,
        ),
    ),
)
def test_probe_v2_respects_the_possible_quote_length_floor(
    text: str, should_probe_succeed: bool
) -> None:
    minimum_words = (
        CURRENT_QUOTE_LENGTH_POLICY.statistical_min_words
        if has_statistical_markers(text)
        else CURRENT_QUOTE_LENGTH_POLICY.non_statistical_min_words
    )
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/source",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=False,
        created_at=NOW,
    )

    result = probe_snapshot(snapshot=snapshot, cluster_id=uuid4())

    assert (count_words(text) >= minimum_words) is should_probe_succeed
    assert result.succeeded is should_probe_succeed
    assert bool(result.passages) is should_probe_succeed


def test_probe_v2_keeps_substantive_text_beside_a_page_error_banner() -> None:
    error_banner = (
        "A required part of this site couldn’t load. This may be due to a browser extension, "
        "network issues, or browser settings. Please check your connection, disable any ad "
        "blockers, or try using a different browser."
    )
    report_text = (
        "The study compares the distribution of automated plate reader cameras with "
        "neighborhood population and income measures across the region. Its findings describe "
        "unequal deployment patterns, but the analysis does not measure stops or enforcement "
        "outcomes for individual residents."
    )
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/source",
        retrieved_at=NOW,
        normalized_text=f"{error_banner}\n{report_text}",
        truncated=False,
        created_at=NOW,
    )

    result = probe_snapshot(snapshot=snapshot, cluster_id=uuid4())

    assert result.succeeded
    assert result.passages
    assert any("study compares" in passage.text for passage in result.passages)
    assert all("couldn’t load" not in passage.text for passage in result.passages)
    assert all("browser extension" not in passage.text for passage in result.passages)


def test_probe_v2_marks_snapshots_without_sentence_spans_unusable() -> None:
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/source",
        retrieved_at=NOW,
        normalized_text="\n",
        truncated=False,
        created_at=NOW,
    )

    result = probe_snapshot(snapshot=snapshot, cluster_id=uuid4())

    assert result.succeeded is False
    assert result.passages == ()
    assert result.failure is not None
    legacy_result = probe_snapshot(
        snapshot=snapshot,
        cluster_id=result.cluster_id,
        policy_identity=V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
    )
    assert legacy_result.succeeded
    assert legacy_result.passages == ()


@pytest.mark.parametrize(
    "text",
    (
        "OSF",
        "The report describes unequal camera deployment in neighborhoods across the city, "
        "but does not compare outcomes for residents or explain intent.",
        "A required part of this site couldn’t load. This may be due to a browser extension, "
        "network issues, or browser settings. Please check your connection, disable any ad "
        "blockers, or try using a different browser.",
    ),
)
def test_probe_shell_capture_never_becomes_an_acquisition_survivor(
    tmp_path: Path, text: str
) -> None:
    run_id = uuid4()
    url = "https://example.org/source"
    output = _discovery(run_id, (url,), ("retrieve",))
    db_path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper({url: _response(url, text)})

    result = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=output,
        wigolo_provider=scraper,
        clock=lambda: NOW,
    )

    assert len(result.output.acquisitions) == 1
    assert result.output.policy_identity == V2_ACQUISITION_PROBE_POLICY_IDENTITY
    assert result.output.probes[0].succeeded is False
    assert result.output.probes[0].passages == ()
    assert result.output.survivors == ()


def test_explicit_legacy_probe_policy_preserves_fallback_survivor(tmp_path: Path) -> None:
    run_id = uuid4()
    url = "https://example.org/source"
    output = _discovery(run_id, (url,), ("retrieve",))
    db_path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper({url: _response(url, "OSF")})

    result = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=output,
        wigolo_provider=scraper,
        policy=V2AcquisitionPolicy(policy_identity=V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY),
        clock=lambda: NOW,
    )

    assert result.output.policy_identity == V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY
    assert result.output.probes[0].succeeded
    assert result.output.survivors
    assert (
        V2AcquisitionProbeOutput.model_validate_json(
            result.output.model_dump_json()
        ).policy_identity
        == V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY
    )


def test_probe_v2_identity_is_the_default_policy() -> None:
    assert V2AcquisitionPolicy().policy_identity == V2_ACQUISITION_PROBE_POLICY_IDENTITY


def test_probe_failure_preserves_snapshot_and_excludes_source_from_survivors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = uuid4()
    url = "https://example.org/source"
    output = _discovery(run_id, (url,), ("retrieve",))
    db_path = _prepare_db(tmp_path, run_id)
    primary = FixtureScraper(
        {url: _response(url, "Opening. Evidence 12%. Citation [1]. Conclusion.")}
    )

    def failed_probe(*, snapshot: object, cluster_id: object) -> object:
        raise RuntimeError("Probe fixture failure")

    monkeypatch.setattr(v2_acquisition, "probe_snapshot", failed_probe)
    result = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=output,
        wigolo_provider=primary,
        clock=lambda: NOW,
    )

    assert len(result.output.acquisitions) == 1
    assert result.output.probes[0].succeeded is False
    assert result.output.probes[0].passages == ()
    assert result.output.survivors == ()
