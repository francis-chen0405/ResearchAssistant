"""Offline usability fallbacks preserve each capture and never replay unknown calls."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_preview_runtime import CLAIM, STUDY
from test_v2_phase5_acquisition_probe import NOW, FixtureScraper, _discovery, _prepare_db, _response

from agents.v2_acquisition import (
    V2AcquisitionCaptureCompletion,
    V2AcquisitionCaptureStart,
    run_v2_acquisition_probe,
)
from agents.v2_discovery import cluster_discovery_items
from providers.acquisition import AcquisitionFailureCode
from providers.scraper import ScrapeRequest, ScrapeResponse, ScraperProviderError
from providers.v2_budget import V2CancellationRequested
from researchassistant.contracts.model_contracts import MediaTypeProvenance
from researchassistant.contracts.model_research import (
    V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
    V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
    V2AcquisitionPolicy,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
)
from researchassistant.storage.store import ReadOnlyStore, read_v2_artifact

LANDING = "https://example.org/landing"
ALTERNATE = "https://mirror.example.org/fulltext"


def _clustered(run_id: UUID) -> V2DiscoveryScoutOutput:
    initial = _discovery(run_id, (LANDING, ALTERNATE), ("retrieve", "maybe"))
    items = tuple(
        item.model_copy(update={"title": "The intervention trial", "doi": "10.1000/trial"})
        for item in initial.items
    )
    return V2DiscoveryScoutOutput.model_validate(
        {
            **initial.model_dump(),
            "items": items,
            "clusters": cluster_discovery_items(items, include_provider_locations=True),
        }
    )


def _policy(**limits: int | float | bool) -> V2AcquisitionPolicy:
    return V2AcquisitionPolicy(policy_identity=V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY, **limits)


def _captures(path: str, run_id: UUID) -> tuple[V2AcquisitionCaptureCompletion, ...]:
    with ReadOnlyStore(path) as store:
        keys = store.connection.execute(
            "SELECT artifact_key FROM v2_artifacts WHERE run_id=? "
            "AND artifact_key LIKE '%/captures/%/completion' ORDER BY rowid",
            (str(run_id),),
        ).fetchall()
        return tuple(
            V2AcquisitionCaptureCompletion.model_validate_json(
                read_v2_artifact(store.connection, run_id, row[0]).payload_json
            )
            for row in keys
        )


@pytest.mark.parametrize(
    "shell", ["OSF", "", "References\nDOI 10.1234/only 1999 2020 55 88", "Error 503.\n" + STUDY]
)
def test_shell_to_allowed_alternate_retains_every_capture(tmp_path: Path, shell: str) -> None:
    run_id = uuid4()
    discovery = _clustered(run_id)
    path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, shell), ALTERNATE: _response(ALTERNATE, STUDY)}
    )
    result = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
        clock=lambda: NOW,
    )
    assert [r.url for r in scraper.requests] == [LANDING, ALTERNATE]
    assert len(result.output.attempts) == 2
    assert len(result.output.survivors) == 1
    assert result.output.acquisitions[0].snapshot.source_url == ALTERNATE
    before = Path(path).read_bytes(), Path(path).stat().st_mtime_ns
    captures = _captures(path, run_id)
    assert [c.response.text for c in captures if c.response is not None] == [shell, STUDY]
    assert [c.readable for c in captures] == [False, True]
    assert [c.attempt.succeeded for c in captures] == [bool(shell), True]
    assert (
        captures[0].source is None
        if not shell
        else captures[0].source.snapshot.normalized_text == shell
    )
    assert captures[1].source is not None
    assert captures[1].source.snapshot == result.output.acquisitions[0].snapshot
    assert all(c.start.direction == result.output.survivors[0].direction for c in captures)
    assert (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) == before
    resumed = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=None,
        exact_claim=CLAIM,
        policy=_policy(),
        clock=lambda: NOW + timedelta(days=1),
    )
    assert resumed.resumed and resumed.output == result.output
    assert len(scraper.requests) == 2
    with pytest.raises(ValueError, match="identity changed"):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=None,
            exact_claim=CLAIM,
            policy=V2AcquisitionPolicy(policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY),
        )
    with sqlite3.connect(path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE v2_artifacts SET payload_json='{}' WHERE artifact_key LIKE '%/captures/%'"
        )


def test_all_unusable_retains_two_separate_snapshots(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, "OSF"), ALTERNATE: _response(LANDING, "OSF")}
    )
    output = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=_clustered(run_id),
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
    ).output
    captures = _captures(path, run_id)
    assert len(scraper.requests) == len(output.attempts) == len(captures) == 2
    assert not output.survivors
    assert all(not c.readable and c.source is not None for c in captures)
    assert len({c.source.snapshot.snapshot_id for c in captures if c.source}) == 2
    assert len({c.source.snapshot.retrieval_attempt_id for c in captures if c.source}) == 2


def test_known_pdf_first_with_current_policy_and_ranked_discovery(tmp_path: Path) -> None:
    from test_ranked_acquisition_integration import _fresh_case, _run_discovery

    from providers.search import SearchDiscoveryMetadata

    path = tmp_path / "pdf.sqlite"
    run_id, plan, results = _fresh_case(path)
    pdf = "https://repository.example.org/study.pdf"
    results = tuple(
        item.model_copy(update={"metadata": SearchDiscoveryMetadata(pdf_url=pdf)})
        if item.rank == 18
        else item
        for item in results
    )
    discovery, _scout = _run_discovery(path, run_id, plan, results, model_calls=10)
    scraper = FixtureScraper(
        {
            **{
                item.source_url: _response(item.source_url, "OSF")
                for item in discovery.output.items
            },
            pdf: _response(pdf, STUDY),
        }
    )
    output = run_v2_acquisition_probe(
        db_path=str(path),
        discovery_output=discovery.output,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
    ).output
    owner = next(
        c for c in discovery.output.clusters if pdf in c.alternate_urls or pdf == c.preferred_url
    )
    owned_attempts = [a for a in output.attempts if a.cluster_id == owner.cluster_id]
    assert [a.url for a in owned_attempts] == [pdf]
    assert any(s.cluster_id == owner.cluster_id for s in output.survivors)


def test_untried_alternate_is_not_marked_acquired_and_duplicate_is_not_fetched(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    discovery = _discovery(run_id, (LANDING, ALTERNATE), ("retrieve", "retrieve"))
    first, second = discovery.clusters
    discovery = discovery.model_copy(
        update={
            "clusters": (
                first.model_copy(update={"alternate_urls": (ALTERNATE,)}),
                second.model_copy(update={"alternate_urls": (LANDING,)}),
            )
        }
    )
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, STUDY), ALTERNATE: _response(ALTERNATE, "OSF")}
    )
    output = run_v2_acquisition_probe(
        db_path=_prepare_db(tmp_path, run_id),
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
    ).output
    assert [r.url for r in scraper.requests] == [LANDING, ALTERNATE]
    assert len(output.attempts) == 2
    assert len(output.survivors) == 1
    assert [a.cluster_id for a in output.attempts] == [first.cluster_id, second.cluster_id]


def test_lower_url_budget_prevents_alternate(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, "OSF"), ALTERNATE: _response(ALTERNATE, STUDY)}
    )
    output = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=_clustered(run_id),
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(max_urls_per_cluster=1, max_clusters=1, timeout_seconds=0.25),
    ).output
    assert [r.url for r in scraper.requests] == [LANDING]
    assert scraper.requests[0].timeout_seconds == 0.25
    assert not output.survivors
    assert len(_captures(path, run_id)) == 1


def test_cancel_after_shell_then_restart_reuses_capture_without_request(tmp_path: Path) -> None:
    run_id = uuid4()
    discovery = _clustered(run_id)
    path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, "OSF"), ALTERNATE: _response(ALTERNATE, STUDY)}
    )
    with pytest.raises(V2CancellationRequested):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            exact_claim=CLAIM,
            policy=_policy(),
            cancellation_requested=lambda: bool(scraper.requests),
            clock=lambda: NOW,
        )
    assert [r.url for r in scraper.requests] == [LANDING]
    assert len(_captures(path, run_id)) == 1
    with pytest.raises(KeyError):
        read_v2_artifact(path, run_id, "phase-5-acquisition-probe")
    output = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
        clock=lambda: NOW + timedelta(hours=1),
    ).output
    assert [r.url for r in scraper.requests] == [LANDING, ALTERNATE]
    assert len(output.attempts) == 2 and len(output.survivors) == 1
    assert len(_captures(path, run_id)) == 2
    assert _captures(path, run_id)[0].start.started_at == NOW


class InterruptedScraper(FixtureScraper):
    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.requests.append(request)
        raise V2CancellationRequested("interrupted with unknown outcome")


def test_unknown_physical_attempt_is_never_replayed(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    scraper = InterruptedScraper({})
    discovery = _clustered(run_id)
    with pytest.raises(V2CancellationRequested):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            exact_claim=CLAIM,
            policy=_policy(),
            clock=lambda: NOW,
        )
    with ReadOnlyStore(path) as store:
        row = store.connection.execute(
            "SELECT payload_json FROM v2_artifacts WHERE artifact_key LIKE '%/captures/%/start'"
        ).fetchone()
        assert row is not None
        assert V2AcquisitionCaptureStart.model_validate_json(row[0]).run_id == run_id
    assert not _captures(path, run_id)
    with pytest.raises(ValueError, match="outcome is unknown"):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            exact_claim=CLAIM,
            policy=_policy(),
            clock=lambda: NOW,
        )
    assert len(scraper.requests) == 1


@pytest.mark.parametrize("readable", [True, False])
def test_verified_html_allows_optional_method_fallback(tmp_path: Path, readable: bool) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    response = _response(LANDING, STUDY if readable else "OSF").model_copy(
        update={
            "media_type_provenance": MediaTypeProvenance(
                verified_media_type="text/html", verified_source_url=LANDING
            ),
            "content_type": "text/html",
        }
    )
    primary = FixtureScraper({LANDING: response})
    fallback = FixtureScraper({LANDING: _response(LANDING, STUDY)})
    discovery = _discovery(run_id, (LANDING,), ("retrieve",))
    output = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=primary,
        firecrawl_provider=fallback,
        exact_claim=CLAIM,
        policy=_policy(),
    ).output
    assert len(primary.requests) == 1
    assert len(fallback.requests) == (0 if readable else 1)
    assert len(output.survivors) == 1
    if not readable:
        assert fallback.requests[0].verified_preflight is not None
        assert len(_captures(path, run_id)) == 2


def test_timeout_retains_failed_attempt_and_tries_alternate(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper(
        {
            LANDING: ScraperProviderError(AcquisitionFailureCode.TIMEOUT, "deadline"),
            ALTERNATE: _response(ALTERNATE, STUDY),
        }
    )
    output = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=_clustered(run_id),
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(timeout_seconds=0.1),
    ).output
    assert len(scraper.requests) == len(output.attempts) == 2
    assert all(r.timeout_seconds == 0.1 for r in scraper.requests)
    assert output.attempts[0].failure_code == AcquisitionFailureCode.TIMEOUT
    assert len(output.survivors) == 1
    assert _captures(path, run_id)[0].source is None


def test_historical_v3_dispatch_keeps_first_capture_and_does_not_repair(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _clustered(run_id)
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, "OSF"), ALTERNATE: _response(ALTERNATE, STUDY)}
    )
    policy = V2AcquisitionPolicy(policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY)
    original = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=policy,
    ).output
    assert len(scraper.requests) == 1 and not original.survivors
    assert not _captures(path, run_id)
    assert V2AcquisitionProbeOutput.model_validate_json(original.model_dump_json()) == original
    resumed = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=policy,
    )
    assert resumed.resumed and resumed.output == original
    assert len(scraper.requests) == 1


@pytest.mark.parametrize("claim", [CLAIM, "Automated license plate readers reduce crime."])
def test_readable_null_or_unrelated_capture_stops_without_seeking_agreement(
    tmp_path: Path, claim: str
) -> None:
    run_id = uuid4()
    scraper = FixtureScraper(
        {
            LANDING: _response(LANDING, STUDY),
            ALTERNATE: _response(
                ALTERNATE, STUDY.replace("no significant effect", "a significant improvement")
            ),
        }
    )
    output = run_v2_acquisition_probe(
        db_path=_prepare_db(tmp_path, run_id),
        discovery_output=_clustered(run_id),
        wigolo_provider=scraper,
        exact_claim=claim,
        policy=_policy(),
    ).output
    assert [r.url for r in scraper.requests] == [LANDING]
    assert len(output.survivors) == 1
    assert "no significant effect" in output.acquisitions[0].snapshot.normalized_text
    if claim != CLAIM:
        assert output.probes[0].preview is not None
        assert output.probes[0].preview.relevance_score == 0


def test_same_location_appearing_twice_and_shared_shell_are_requested_once(tmp_path: Path) -> None:
    run_id = uuid4()
    discovery = _discovery(run_id, (LANDING, ALTERNATE), ("retrieve", "retrieve"))
    first, second = discovery.clusters
    discovery = discovery.model_copy(
        update={
            "clusters": (
                first.model_copy(update={"alternate_urls": (LANDING,)}),
                second.model_copy(
                    update={"preferred_url": LANDING, "alternate_urls": (ALTERNATE,)}
                ),
            )
        }
    )
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, "OSF"), ALTERNATE: _response(ALTERNATE, STUDY)}
    )
    output = run_v2_acquisition_probe(
        db_path=_prepare_db(tmp_path, run_id),
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
    ).output
    assert [r.url for r in scraper.requests] == [LANDING, ALTERNATE]
    assert len(output.attempts) == 2 and len(output.survivors) == 1
    assert output.survivors[0].cluster_id == second.cluster_id


def test_unknown_attempt_blocks_even_when_provider_is_unavailable(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _clustered(run_id)
    with pytest.raises(V2CancellationRequested):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=InterruptedScraper({}),
            exact_claim=CLAIM,
            policy=_policy(),
        )
    with pytest.raises(ValueError, match="outcome is unknown"):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=None,
            exact_claim=CLAIM,
            policy=_policy(),
        )
    with pytest.raises(KeyError):
        read_v2_artifact(path, run_id, "phase-5-acquisition-probe")


def test_processing_interruption_retains_response_and_reuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agents.v2_acquisition as acquisition

    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _clustered(run_id)
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, "OSF"), ALTERNATE: _response(ALTERNATE, STUDY)}
    )
    original = acquisition._capture_is_readable

    def interrupted(snapshot: acquisition.SourceSnapshot) -> bool:
        raise RuntimeError("assessment interrupted")

    monkeypatch.setattr(acquisition, "_capture_is_readable", interrupted)
    with pytest.raises(RuntimeError, match="assessment interrupted"):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            exact_claim=CLAIM,
            policy=_policy(),
            clock=lambda: NOW,
        )
    with ReadOnlyStore(path) as store:
        row = store.connection.execute(
            "SELECT payload_json FROM v2_artifacts WHERE artifact_key LIKE '%/captures/%/response'"
        ).fetchone()
        assert row is not None
        captured = acquisition.V2AcquisitionCaptureResponse.model_validate_json(row[0])
        assert captured.response is not None and captured.response.text == "OSF"
    monkeypatch.setattr(acquisition, "_capture_is_readable", original)
    output = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
        clock=lambda: NOW + timedelta(days=1),
    ).output
    assert [r.url for r in scraper.requests] == [LANDING, ALTERNATE]
    assert len(output.attempts) == 2 and len(output.survivors) == 1
    assert _captures(path, run_id)[0].start.started_at == NOW


def test_unknown_fallback_attempt_blocks_when_fallback_is_unavailable(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _discovery(run_id, (LANDING,), ("retrieve",))
    response = _response(LANDING, "OSF").model_copy(
        update={
            "content_type": "text/html",
            "media_type_provenance": MediaTypeProvenance(
                verified_media_type="text/html", verified_source_url=LANDING
            ),
        }
    )
    primary = FixtureScraper({LANDING: response})
    fallback = InterruptedScraper({})
    with pytest.raises(V2CancellationRequested):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=primary,
            firecrawl_provider=fallback,
            exact_claim=CLAIM,
            policy=_policy(),
        )
    with pytest.raises(ValueError, match="outcome is unknown"):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=None,
            firecrawl_provider=None,
            exact_claim=CLAIM,
            policy=_policy(),
        )
    assert len(primary.requests) == len(fallback.requests) == 1


def test_cancel_before_dispatch_makes_no_request_or_capture(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    scraper = FixtureScraper({LANDING: _response(LANDING, STUDY)})
    with pytest.raises(V2CancellationRequested):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=_clustered(run_id),
            wigolo_provider=scraper,
            exact_claim=CLAIM,
            policy=_policy(),
            cancellation_requested=lambda: True,
        )
    assert not scraper.requests
    assert not _captures(path, run_id)


def test_cancel_during_readable_call_persists_capture_without_stage_completion(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _clustered(run_id)
    scraper = FixtureScraper({LANDING: _response(LANDING, STUDY)})
    with pytest.raises(V2CancellationRequested):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            exact_claim=CLAIM,
            policy=_policy(),
            cancellation_requested=lambda: bool(scraper.requests),
        )
    assert len(_captures(path, run_id)) == 1
    with pytest.raises(KeyError):
        read_v2_artifact(path, run_id, "phase-5-acquisition-probe")
    output = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=None,
        exact_claim=CLAIM,
        policy=_policy(),
    ).output
    assert len(scraper.requests) == len(output.attempts) == len(output.survivors) == 1


def test_canonical_metadata_does_not_mark_an_unvisited_alternate_tried(tmp_path: Path) -> None:
    run_id = uuid4()
    scraper = FixtureScraper(
        {
            LANDING: _response(LANDING, "OSF").model_copy(update={"canonical_url": ALTERNATE}),
            ALTERNATE: _response(ALTERNATE, STUDY),
        }
    )
    output = run_v2_acquisition_probe(
        db_path=_prepare_db(tmp_path, run_id),
        discovery_output=_clustered(run_id),
        wigolo_provider=scraper,
        exact_claim=CLAIM,
        policy=_policy(),
    ).output
    assert [r.url for r in scraper.requests] == [LANDING, ALTERNATE]
    assert len(output.attempts) == 2 and len(output.survivors) == 1
