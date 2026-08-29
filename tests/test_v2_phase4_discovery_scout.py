from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError

from agents.v2_discovery import (
    V2_SCOUT_BATCH_SIZE,
    V2DiscoveryResponse,
    cluster_discovery_items,
    normalize_discovery_responses,
    run_v2_discovery_and_scout,
    scout_ordered_item_ids,
)
from models import (
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    ScoutItem,
    Stage,
    V2InitialPlannerOutput,
    V2PipelineIdentity,
    V2RoundOneSearchQuery,
)
from providers.crossref import CrossrefEnricher, CrossrefEnrichmentError
from providers.llm import LLMProviderCapabilities
from providers.search import SearchDiscoveryMetadata, SearchResult
from providers.v2_budget import V2CancellationRequested
from providers.v2_routing import V2RoutingConfig
from store import init_db, insert_run, insert_v2_pipeline_identity

NOW = datetime(2026, 8, 20, tzinfo=UTC)


class RecallScout:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self, *, malformed: bool = False) -> None:
        self.requests: list[object] = []
        self.malformed = malformed

    def generate(self, request: object) -> ScoutBatch:
        self.requests.append(request)
        candidates = request.input_artifact.candidates
        if self.malformed:
            return ScoutBatch(
                run_id=request.run_id,
                items=(ScoutItem(item_id=uuid4(), decision="retrieve", rationale="bad mapping"),),
            )
        return ScoutBatch(
            run_id=request.run_id,
            items=tuple(
                ScoutItem(
                    item_id=candidate.item_id,
                    decision="retrieve" if index == 0 else "maybe",
                    rationale="plausibly useful",
                )
                for index, candidate in enumerate(candidates)
            ),
        )


class FailThenCancelScout(RecallScout):
    def __init__(self, cancelled: list[bool]) -> None:
        super().__init__()
        self.cancelled = cancelled

    def generate(self, request: object) -> ScoutBatch:
        if not self.requests:
            self.requests.append(request)
            self.cancelled[0] = True
            raise RuntimeError("test provider failure before retry")
        return super().generate(request)


def _routing() -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        {
            "MIMO_API_KEY": "mimo-secret",
            "MIMO_V25_MODEL": "mimo-v2.5",
            "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
            "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
            "LUNA_API_KEY": "luna-secret",
            "LUNA_BASE_URL": "https://luna.example.test/v1",
            "LUNA_MODEL": "luna",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="v2-phase4-tests",
    )


def _query(
    run_id: UUID, provider: DiscoveryProvider, direction: ResearchDirection
) -> V2RoundOneSearchQuery:
    return V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        direction=direction,
        provider=provider,
        strategy="test",
        query_text=f"{direction.value} {provider.value} query",
        created_at=NOW,
    )


def _response(
    run_id: UUID,
    provider: DiscoveryProvider,
    *,
    title: str = "A useful study",
    url: str = "https://example.org/study?utm_source=test",
    doi: str | None = "10.1000/ABC",
    direction: ResearchDirection = ResearchDirection.SUPPORT,
    rank: int = 1,
) -> V2DiscoveryResponse:
    return V2DiscoveryResponse(
        query=_query(run_id, provider, direction),
        results=(
            SearchResult(
                original_url=url,
                title=title,
                snippet="discovery snippet only",
                rank=rank,
                metadata=SearchDiscoveryMetadata(
                    engine=provider.value,
                    author="Ada Author",
                    abstract="provider abstract only",
                    published_at="2024-05-01",
                    doi=doi,
                    work_type="article",
                ),
            ),
        ),
    )


def _single_scout_run(
    tmp_path: Path,
) -> tuple[str, V2InitialPlannerOutput, V2DiscoveryResponse]:
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    queries = tuple(
        V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.EXA,
            strategy=strategy,
            query_text=f"support exa {strategy}",
            created_at=NOW,
        )
        for strategy in ("direct_evidence", "mechanism", "analysis")
    )
    plan = V2InitialPlannerOutput(
        run_id=run_id,
        raw_claim="A public claim.",
        directions=directions,
        discovery_providers=(DiscoveryProvider.EXA,),
        searches=queries,
        planner_prompt_version="test-v1",
        planned_at=NOW,
    )
    response = V2DiscoveryResponse(
        query=queries[0],
        results=(
            SearchResult(
                original_url="https://example.org/study",
                title="A useful study",
                snippet="discovery snippet only",
                rank=1,
                metadata=SearchDiscoveryMetadata(
                    engine=DiscoveryProvider.EXA.value,
                    author="Ada Author",
                    abstract="provider abstract only",
                    published_at="2024-05-01",
                    doi="10.1000/ABC",
                    work_type="article",
                ),
            ),
        ),
    )
    db_path = str(tmp_path / "phase4-cancellation.sqlite3")
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
    return db_path, plan, response


def test_multi_provider_normalization_preserves_provenance_and_crossref_failure() -> None:
    run_id = uuid4()
    responses = tuple(
        _response(run_id, provider, url=f"https://{provider.value}.example/study")
        for provider in (
            DiscoveryProvider.OPENALEX,
            DiscoveryProvider.ARXIV,
            DiscoveryProvider.PUBMED,
            DiscoveryProvider.EXA,
            DiscoveryProvider.SERPER,
        )
    )

    def failing_crossref(doi: str) -> CrossrefIdentityMetadata:
        raise RuntimeError(doi)

    items = normalize_discovery_responses(
        run_id=run_id,
        directions=ResearchDirections(),
        responses=responses,
        discovered_at=NOW,
        crossref_resolver=failing_crossref,
    )

    assert {item.provider for item in items} == {
        DiscoveryProvider.OPENALEX,
        DiscoveryProvider.ARXIV,
        DiscoveryProvider.PUBMED,
        DiscoveryProvider.EXA,
        DiscoveryProvider.SERPER,
    }
    assert all(item.provenance_chain[0].query_text == item.query_text for item in items)
    assert all(item.crossref and item.crossref.failure_code == "RuntimeError" for item in items)
    assert all(item.doi == "10.1000/abc" for item in items)
    assert all(item.abstract == "provider abstract only" for item in items)
    repeated = normalize_discovery_responses(
        run_id=run_id,
        directions=ResearchDirections(),
        responses=responses,
        discovered_at=NOW,
        crossref_resolver=failing_crossref,
    )
    assert tuple(item.item_id for item in repeated) == tuple(item.item_id for item in items)
    with pytest.raises(ValidationError, match="Scout response IDs must be unique"):
        ScoutBatch(
            run_id=run_id,
            items=(
                ScoutItem(item_id=items[0].item_id, decision="maybe", rationale="first"),
                ScoutItem(item_id=items[0].item_id, decision="maybe", rationale="duplicate"),
            ),
        )


def test_crossref_success_and_conservative_canonical_deduplication() -> None:
    run_id = uuid4()

    def crossref(doi: str) -> CrossrefIdentityMetadata:
        return CrossrefIdentityMetadata(
            doi=doi,
            canonical_title="Canonical Study Title",
            canonical_authors=("Ada Author",),
            publication_date="2024-01-02",
            verified=True,
        )

    responses = (
        _response(run_id, DiscoveryProvider.EXA),
        _response(
            run_id,
            DiscoveryProvider.PUBMED,
            url="https://mirror.example.org/paper?utm_campaign=ignore",
        ),
        _response(
            run_id,
            DiscoveryProvider.ARXIV,
            title="Same Topic But A Different Paper",
            url="https://arxiv.example.org/different",
            doi=None,
        ),
    )
    items = normalize_discovery_responses(
        run_id=run_id,
        directions=ResearchDirections(),
        responses=responses,
        discovered_at=NOW,
        crossref_resolver=crossref,
    )
    clusters = cluster_discovery_items(items)

    assert len(clusters) == 2
    doi_cluster = next(cluster for cluster in clusters if len(cluster.item_ids) == 2)
    assert "https://mirror.example.org/paper?utm_campaign=ignore" in doi_cluster.alternate_urls
    assert doi_cluster.provider_references[0].provider is DiscoveryProvider.EXA


def test_crossref_adapter_success_and_failure_are_non_evidentiary() -> None:
    def success_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works/10.1000/abc"
        return httpx.Response(
            200,
            json={
                "message": {
                    "DOI": "10.1000/ABC",
                    "title": ["Canonical title"],
                    "author": [{"given": "Ada", "family": "Author"}],
                    "issued": {"date-parts": [[2024, 5, 1]]},
                }
            },
        )

    enricher = CrossrefEnricher(
        client=httpx.Client(
            base_url="https://api.crossref.org",
            transport=httpx.MockTransport(success_handler),
        )
    )
    metadata = enricher.resolve("10.1000/abc")

    assert metadata.verified
    assert metadata.canonical_authors == ("Ada Author",)
    failed = CrossrefEnricher(
        client=httpx.Client(
            base_url="https://api.crossref.org",
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        )
    )
    with pytest.raises(CrossrefEnrichmentError, match="HTTP 503"):
        failed.resolve("10.1000/abc")


def test_v2_scout_batches_thirty_items_retries_falls_back_and_persists(tmp_path: Path) -> None:
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    queries = tuple(
        V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.EXA,
            strategy=strategy,
            query_text=f"support exa {strategy}",
            created_at=NOW,
        )
        for strategy in ("direct_evidence", "mechanism", "analysis")
    )
    plan = V2InitialPlannerOutput(
        run_id=run_id,
        raw_claim="A public claim.",
        directions=directions,
        discovery_providers=(DiscoveryProvider.EXA,),
        searches=queries,
        planner_prompt_version="test-v1",
        planned_at=NOW,
    )
    responses = (
        V2DiscoveryResponse(
            query=queries[0],
            results=tuple(
                SearchResult(
                    original_url=f"https://example.org/{index}",
                    title=f"Study {index}",
                    rank=index + 1,
                )
                for index in range(31)
            ),
        ),
    )
    db_path = str(tmp_path / "phase4.sqlite3")
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
    scout = RecallScout(malformed=True)
    result = run_v2_discovery_and_scout(
        db_path=db_path,
        planner_output=plan,
        responses=responses,
        llm_provider=scout,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert [len(request.input_artifact.candidates) for request in scout.requests] == [
        30,
        30,
        1,
        1,
    ]
    assert V2_SCOUT_BATCH_SIZE == 30
    assert scout.requests[0].model_alias.value == "mimo-v2.5"
    assert all(
        audit.fallback_used and audit.attempted_calls == 2 for audit in result.output.scout_audits
    )
    assert len(scout_ordered_item_ids(result.output)) == 31
    resumed = run_v2_discovery_and_scout(
        db_path=db_path,
        planner_output=plan,
        responses=(),
        llm_provider=scout,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    assert resumed.resumed and resumed.output == result.output


def test_scout_cancellation_before_first_attempt_is_typed_and_makes_no_call(
    tmp_path: Path,
) -> None:
    db_path, plan, response = _single_scout_run(tmp_path)
    checks = [False, True]

    def cancellation_requested() -> bool:
        return checks.pop(0) if checks else True

    scout = RecallScout()
    with pytest.raises(V2CancellationRequested, match="before discovery work"):
        run_v2_discovery_and_scout(
            db_path=db_path,
            planner_output=plan,
            responses=(response,),
            llm_provider=scout,
            routing_config=_routing(),
            clock=lambda: NOW,
            cancellation_requested=cancellation_requested,
        )

    assert scout.requests == []


def test_scout_cancellation_between_attempts_prevents_retry(
    tmp_path: Path,
) -> None:
    db_path, plan, response = _single_scout_run(tmp_path)
    cancelled = [False]
    scout = FailThenCancelScout(cancelled)

    with pytest.raises(V2CancellationRequested, match="cancellation was observed"):
        run_v2_discovery_and_scout(
            db_path=db_path,
            planner_output=plan,
            responses=(response,),
            llm_provider=scout,
            routing_config=_routing(),
            clock=lambda: NOW,
            cancellation_requested=lambda: cancelled[0],
        )

    assert len(scout.requests) == 1


def test_direction_isolation_rejects_disabled_discovery_before_scout() -> None:
    run_id = uuid4()
    with pytest.raises(ValueError, match="disabled research direction"):
        normalize_discovery_responses(
            run_id=run_id,
            directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
            responses=(
                _response(run_id, DiscoveryProvider.EXA, direction=ResearchDirection.CHALLENGE),
            ),
            discovered_at=NOW,
        )
