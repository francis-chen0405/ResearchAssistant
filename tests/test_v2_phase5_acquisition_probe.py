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
from models import (
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    ScoutBatchAudit,
    ScoutItem,
    Stage,
    V2DiscoveryScoutOutput,
    V2PipelineIdentity,
    V2ProbePassage,
    V2RoundOneSearchQuery,
)
from providers.acquisition import AcquisitionFailureCode
from providers.scraper import (
    ScrapeRequest,
    ScrapeResponse,
    ScraperProviderError,
    VerifiedAcquisitionPreflight,
)
from providers.search import SearchResult
from store import init_db, insert_run, insert_v2_pipeline_identity

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
                "Opening evidence has 42% support. [1] References establish the method. "
                "In conclusion, the evidence remains useful.",
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
            "Abstract opening. Plain unrelated material. Final conclusion without shared keywords."
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
