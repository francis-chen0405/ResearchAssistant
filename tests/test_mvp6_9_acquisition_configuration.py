from __future__ import annotations

import json
import sqlite3
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from models import (
    ClaimDefinition,
    MediaTypeProvenance,
    PlannerOutput,
    RetrievalRecord,
    RetrievalStatus,
    RunManifest,
    RunStatus,
    SearchQuery,
    SourceSnapshot,
    Stage,
    Stance,
)
from providers.acquisition import ACQUISITION_VERSION, WigoloAcquisitionAdapter
from providers.config import (
    FirecrawlConfig,
    LiveSmokeConfig,
    MimoConfig,
    WigoloConfig,
)
from providers.firecrawl import FallbackAcquisitionAdapter, FirecrawlAcquisitionAdapter
from providers.mimo_factory import MIMO_FINGERPRINT_VERSION
from providers.scraper import ScrapeRequest
from store import (
    CURRENT_SCHEMA_VERSION,
    init_db,
    insert_planner_output,
    insert_retrieval_attempt,
    insert_run,
    insert_snapshot,
    read_snapshot,
)
from utils import compute_sha256

NOW = datetime(2026, 8, 10, tzinfo=UTC)
PUBLIC_IP = ("93.184.216.34",)
ARTICLE_URL = "https://example.org/article"


def _firecrawl_response(metadata: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("POST", "https://api.firecrawl.dev/v2/scrape")
    return httpx.Response(
        200,
        json={
            "success": True,
            "data": {
                "markdown": "# Heading\n\nExact public evidence.",
                "metadata": {"statusCode": 200, "sourceURL": ARTICLE_URL} | metadata,
            },
        },
        request=request,
    )


def _firecrawl_adapter(metadata: dict[str, Any]) -> FirecrawlAcquisitionAdapter:
    return FirecrawlAcquisitionAdapter(
        FirecrawlConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.firecrawl.dev",
            transport=httpx.MockTransport(lambda request: _firecrawl_response(metadata)),
        ),
        host_resolver=lambda hostname: PUBLIC_IP,
    )


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("application/pdf", "application/pdf"),
        ("application/pdf; charset=binary", "application/pdf"),
        ("text/html", "text/html"),
        (None, None),
        ("", None),
        ("   ", None),
        ("; charset=utf-8", None),
        ("not a media type", None),
        ("image/png", None),
        (123, None),
    ],
)
def test_firecrawl_declaration_is_never_verified_origin_media_type(
    declared: object,
    expected: str | None,
) -> None:
    metadata = {} if declared is None else {"contentType": declared}
    result = _firecrawl_adapter(metadata).scrape(ScrapeRequest(url=ARTICLE_URL, timeout_seconds=10))

    assert result.content_type == "text/markdown"
    assert result.media_type_provenance.verified_media_type is None
    assert result.media_type_provenance.verified_source_url is None
    assert result.media_type_provenance.provider_declared_media_type == expected


def test_verified_primary_preflight_type_survives_firecrawl_fallback_conflict() -> None:
    observed_firecrawl_url: list[str] = []

    def source_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html><body>Primary source</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    def wigolo_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    def firecrawl_handler(request: httpx.Request) -> httpx.Response:
        observed_firecrawl_url.append(json.loads(request.content)["url"])
        return _firecrawl_response({"contentType": "application/pdf"})

    primary = WigoloAcquisitionAdapter(
        WigoloConfig(),
        source_client=httpx.Client(transport=httpx.MockTransport(source_handler)),
        wigolo_client=httpx.Client(
            base_url="http://127.0.0.1:8000",
            transport=httpx.MockTransport(wigolo_handler),
        ),
        host_resolver=lambda hostname: PUBLIC_IP,
    )
    fallback = FirecrawlAcquisitionAdapter(
        FirecrawlConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.firecrawl.dev",
            transport=httpx.MockTransport(firecrawl_handler),
        ),
        host_resolver=lambda hostname: PUBLIC_IP,
    )

    result = FallbackAcquisitionAdapter(primary=primary, fallback=fallback).scrape(
        ScrapeRequest(url=ARTICLE_URL, timeout_seconds=10)
    )

    assert observed_firecrawl_url == [ARTICLE_URL]
    assert result.content_type == "text/html"
    assert result.media_type_provenance == MediaTypeProvenance(
        verified_media_type="text/html",
        verified_source_url=ARTICLE_URL,
        provider_declared_media_type="application/pdf",
    )


def test_verified_preflight_follows_redirect_boundary_into_fallback() -> None:
    final_url = "https://final.example/article"
    requested: list[str] = []

    def source_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ARTICLE_URL:
            return httpx.Response(302, headers={"location": final_url}, request=request)
        return httpx.Response(
            200,
            content=b"<html><body>Final source</body></html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    def firecrawl_handler(request: httpx.Request) -> httpx.Response:
        requested.append(json.loads(request.content)["url"])
        response = _firecrawl_response({"sourceURL": final_url, "contentType": "text/html"})
        return response

    primary = WigoloAcquisitionAdapter(
        WigoloConfig(),
        source_client=httpx.Client(transport=httpx.MockTransport(source_handler)),
        wigolo_client=httpx.Client(
            base_url="http://127.0.0.1:8000",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"invalid", request=request)
            ),
        ),
        host_resolver=lambda hostname: PUBLIC_IP,
    )
    fallback = FirecrawlAcquisitionAdapter(
        FirecrawlConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.firecrawl.dev",
            transport=httpx.MockTransport(firecrawl_handler),
        ),
        host_resolver=lambda hostname: PUBLIC_IP,
    )

    result = FallbackAcquisitionAdapter(primary=primary, fallback=fallback).scrape(
        ScrapeRequest(url=ARTICLE_URL, timeout_seconds=10)
    )

    assert requested == [final_url]
    assert result.resolved_url == final_url
    assert result.media_type_provenance.verified_source_url == final_url
    assert result.media_type_provenance.verified_media_type == "text/html"


def _planner(run_id: UUID) -> PlannerOutput:
    exclusions = "-site:reddit.com -site:quora.com -site:youtube.com -site:tiktok.com"
    queries = [
        SearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            stance=stance,
            query_round=round_number,
            strategy=f"{stance.value}-{round_number}",
            query_text="test query",
            exclusion_parameters=exclusions,
            created_at=NOW,
        )
        for stance in (Stance.SUPPORTING, Stance.OPPOSING)
        for round_number in range(1, 4)
    ]
    return PlannerOutput(
        run_id=run_id,
        claim_definition=ClaimDefinition(
            run_id=run_id,
            claim_text="Test claim",
            population="People",
            jurisdiction="Global",
            time_period="Current",
            comparison_baseline="Baseline",
            intervention_or_exposure="Exposure",
            causal_or_comparative_meaning="Comparison",
            created_at=NOW,
        ),
        ambiguities=[],
        search_queries=queries,
        planner_prompt_version="test-v1",
        planner_model_name="test-model",
        planned_at=NOW,
    )


def test_snapshot_persistence_reconstructs_media_type_provenance(tmp_path: Path) -> None:
    db_path = str(tmp_path / "provenance.sqlite3")
    run_id = uuid4()
    planner = _planner(run_id)
    query = planner.search_queries[0]
    retrieval = RetrievalRecord(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        query_id=query.query_id,
        query_round=query.query_round,
        query_text=query.query_text,
        search_rank=1,
        source_url=ARTICLE_URL,
        resolved_url=ARTICLE_URL,
        status=RetrievalStatus.RETRIEVED,
        retrieved_at=NOW,
    )
    text = "Exact normalized evidence"
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=retrieval.retrieval_attempt_id,
        snapshot_id=uuid4(),
        source_url=ARTICLE_URL,
        original_url=ARTICLE_URL,
        canonical_url="https://example.org/canonical",
        retrieved_at=NOW,
        normalized_text=text,
        snapshot_sha256=compute_sha256(text),
        word_count=3,
        truncated=False,
        normalization_version="ra-normalization-v1",
        acquisition_version=ACQUISITION_VERSION,
        provider_name="firecrawl",
        provider_version="v2",
        media_type_provenance=MediaTypeProvenance(
            verified_media_type="text/html",
            verified_source_url=ARTICLE_URL,
            provider_declared_media_type="application/pdf",
        ),
        created_at=NOW,
    )
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="Test claim",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_planner_output(db_path, planner)
    insert_retrieval_attempt(db_path, retrieval)
    insert_snapshot(db_path, snapshot)

    assert read_snapshot(db_path, snapshot.snapshot_id) == snapshot
    historical_snapshot_id = uuid4()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO snapshots (
                snapshot_id, run_id, retrieval_attempt_id, source_url, retrieved_at,
                normalized_text, snapshot_sha256, word_count, truncated, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(historical_snapshot_id),
                str(run_id),
                str(retrieval.retrieval_attempt_id),
                ARTICLE_URL,
                NOW.isoformat(),
                text,
                compute_sha256(text),
                3,
                0,
                NOW.isoformat(),
            ),
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(snapshots)")}
    historical = read_snapshot(db_path, historical_snapshot_id)
    assert historical is not None
    assert historical.media_type_provenance == MediaTypeProvenance()
    assert historical.original_url is None
    assert historical.acquisition_version is None
    assert CURRENT_SCHEMA_VERSION == 8
    assert {
        "original_url",
        "canonical_url",
        "normalization_version",
        "acquisition_version",
        "provider_name",
        "provider_version",
        "media_type_provenance_json",
    } <= columns


def _parse_environment_example(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator == "=", f"malformed environment example line: {raw_line}"
        values[key] = value
    return values


def test_environment_example_constructs_supported_legacy_smoke_offline() -> None:
    environment = _parse_environment_example(Path(".env.example"))
    assert environment["MIMO_API_KEY"] == ""
    environment |= {
        "MIMO_API_KEY": "offline-placeholder",
        "RESEARCH_ASSISTANT_LIVE_SMOKE": "1",
        "RESEARCH_ASSISTANT_LIVE_APPROVED": "I_APPROVE_ONE_MIMO_LIVE_SMOKE",
    }

    smoke = LiveSmokeConfig(
        enabled=environment["RESEARCH_ASSISTANT_LIVE_SMOKE"] == "1",
        approved_now=(
            environment["RESEARCH_ASSISTANT_LIVE_APPROVED"] == "I_APPROVE_ONE_MIMO_LIVE_SMOKE"
        ),
        max_search_calls=int(environment["RESEARCH_ASSISTANT_SMOKE_MAX_SEARCH_CALLS"]),
        max_acquisition_calls=int(environment["RESEARCH_ASSISTANT_SMOKE_MAX_ACQUISITION_CALLS"]),
        max_llm_calls=int(environment["RESEARCH_ASSISTANT_SMOKE_MAX_LLM_CALLS"]),
        max_tokens=int(environment["RESEARCH_ASSISTANT_SMOKE_MAX_TOKENS"]),
        max_cost_usd=environment["RESEARCH_ASSISTANT_SMOKE_MAX_COST_USD"],
        output_path=Path(environment["RESEARCH_ASSISTANT_SMOKE_OUTPUT"]),
    )
    smoke.require_enabled()
    assert smoke.max_tokens <= 25_000
    assert MimoConfig.from_environment(environment).api_key.get_secret_value() == (
        "offline-placeholder"
    )


def test_mvp6_9_acquisition_and_fingerprint_identities_change() -> None:
    assert ACQUISITION_VERSION == "mvp6.9-acquisition-provenance-v3"
    assert MIMO_FINGERPRINT_VERSION == "mvp9-verified-quote-selection-v1"


def test_package_description_is_durable_and_phase_neutral() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    description = project["description"]
    assert "Debate Research Agent System" in description
    assert "MVP-" not in description
