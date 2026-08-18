from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agents.supportingresearcher import AcquisitionPolicy, ResearcherRetrievalBatch
from frontend.live_service import LiveResearchController
from models import (
    AmbiguityRecord,
    ClaimDefinition,
    DiscoveryProvider,
    PersistedStageArtifact,
    PlannerOutput,
    ResearchControls,
    ResearchMode,
    RetrievalRecord,
    RetrievalStatus,
    RunManifest,
    RunStatus,
    SearchIntent,
    SearchQuery,
    SourceSnapshot,
    Stage,
    Stance,
)
from orchestrator import (
    PHASE9_RESEARCHERS_ARTIFACT,
    ResearcherPairResult,
    ResearcherSideStatus,
    ResearcherStageResult,
)
from providers.composite_search import CompositeSearchProvider
from providers.config import OpenAlexConfig
from providers.openalex import OpenAlexSearchAdapter
from providers.ranking import (
    DISCARD_SCORE_FLOOR,
    DiscoveryDecision,
    rank_acquired_sources,
    rank_discovery_pool,
)
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from store import (
    init_db,
    insert_planner_output,
    insert_run,
    insert_stage_artifact,
    read_planner_output,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)
EXCLUSIONS = "-site:reddit.com -site:quora.com -site:youtube.com -site:tiktok.com"


def _claim(run_id: UUID) -> ClaimDefinition:
    return ClaimDefinition(
        run_id=run_id,
        claim_text="A four-day workweek improves productivity.",
        population="employees",
        jurisdiction="general",
        time_period="current",
        comparison_baseline="five-day workweek",
        intervention_or_exposure="four-day workweek",
        causal_or_comparative_meaning="improves productivity",
        created_at=NOW,
    )


def _query(
    run_id: UUID,
    stance: Stance,
    provider: DiscoveryProvider,
    query_round: int,
) -> SearchQuery:
    return SearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        stance=stance,
        provider=provider,
        intent=(
            SearchIntent.ACADEMIC_STUDY
            if provider is DiscoveryProvider.OPENALEX
            else SearchIntent.BROAD_WEB
        ),
        query_round=query_round,
        strategy=f"{provider.value}-{query_round}",
        query_text="four day workweek productivity",
        exclusion_parameters=EXCLUSIONS if provider is DiscoveryProvider.EXA else "",
        created_at=NOW,
    )


def _planner(*, balanced: bool) -> PlannerOutput:
    run_id = uuid4()
    stances = (Stance.SUPPORTING, Stance.OPPOSING) if balanced else (Stance.SUPPORTING,)
    queries = [
        _query(run_id, stance, DiscoveryProvider.EXA, query_round)
        for stance in stances
        for query_round in (1, 2, 3)
    ]
    queries.extend(_query(run_id, stance, DiscoveryProvider.OPENALEX, 1) for stance in stances)
    return PlannerOutput(
        run_id=run_id,
        claim_definition=_claim(run_id),
        ambiguities=[
            AmbiguityRecord(
                run_id=run_id,
                ambiguity_id=uuid4(),
                description="Productivity can be measured in several ways.",
                impact="The research must preserve each study's measure.",
                created_at=NOW,
            )
        ],
        search_queries=queries,
        planner_prompt_version="mlp4-planner-v1",
        planner_model_name="mimo-v2.5-pro",
        planned_at=NOW,
    )


def test_mlp4_controls_default_to_focused_with_ten_sources() -> None:
    controls = ResearchControls()

    assert controls.research_mode is ResearchMode.FOCUSED
    assert controls.sources_per_stance_per_round == 10


@pytest.mark.parametrize("target", [5, 10, 15, 20])
def test_mlp4_controls_accept_only_advanced_source_targets(target: int) -> None:
    controls = ResearchControls(sources_per_stance_per_round=target)

    assert controls.sources_per_stance_per_round == target


def test_mlp4_controls_reject_unapproved_source_target() -> None:
    for target in (6, 12):
        with pytest.raises(ValidationError):
            ResearchControls(sources_per_stance_per_round=target)


def test_mlp4_controls_keep_the_legacy_seven_source_value_readable() -> None:
    assert ResearchControls(sources_per_stance_per_round=7).sources_per_stance_per_round == 7


def test_focused_planner_requires_separate_exa_and_openalex_queries() -> None:
    planner = _planner(balanced=False)

    assert planner.research_mode is ResearchMode.FOCUSED
    assert len(planner.queries_for_provider(DiscoveryProvider.EXA)) == 3
    assert len(planner.queries_for_provider(DiscoveryProvider.OPENALEX)) == 1


def test_balanced_planner_requires_provider_plan_for_both_stances() -> None:
    planner = _planner(balanced=True)

    assert planner.research_mode is ResearchMode.BALANCED
    assert len(planner.search_queries) == 8


def test_new_planner_rejects_missing_openalex_lane() -> None:
    planner = _planner(balanced=False)
    payload = planner.model_dump()
    payload["search_queries"] = [
        query.model_dump()
        for query in planner.search_queries
        if query.provider is DiscoveryProvider.EXA
    ]

    with pytest.raises(ValidationError, match="OpenAlex"):
        PlannerOutput.model_validate(payload)


def test_openalex_query_forbids_web_exclusion_syntax() -> None:
    query = _query(uuid4(), Stance.SUPPORTING, DiscoveryProvider.OPENALEX, 1)
    payload = query.model_dump()
    payload["exclusion_parameters"] = EXCLUSIONS

    with pytest.raises(ValidationError, match="OpenAlex"):
        SearchQuery.model_validate(payload)


def _openalex_response(*, retracted: bool = False) -> dict[str, object]:
    return {
        "meta": {"count": 1, "per_page": 10, "cost_usd": 0.001},
        "results": [
            {
                "id": "https://openalex.org/W123",
                "doi": "https://doi.org/10.1000/example",
                "title": "Four-day workweeks and employee productivity",
                "publication_year": 2025,
                "publication_date": "2025-05-01",
                "type": "article",
                "cited_by_count": 12,
                "is_retracted": retracted,
                "relevance_score": 88.5,
                "open_access": {"is_oa": True},
                "primary_location": {
                    "landing_page_url": "https://example.edu/study",
                    "pdf_url": "https://example.edu/study.pdf",
                },
                "best_oa_location": None,
            }
        ],
    }


def _openalex_adapter(handler: httpx.MockTransport) -> OpenAlexSearchAdapter:
    config = OpenAlexConfig(api_key=SecretStr("openalex-test-secret"))
    return OpenAlexSearchAdapter(
        config,
        client=httpx.Client(base_url=config.base_url, transport=handler),
    )


@pytest.mark.parametrize(("target", "expected_attempts"), ((5, 10), (10, 15), (15, 20), (20, 25)))
def test_ranked_acquisition_reserves_a_small_bounded_backfill_pool(
    target: int,
    expected_attempts: int,
) -> None:
    policy = AcquisitionPolicy(
        discovery_results_per_query=10,
        usable_snapshots_per_query=10,
        source_target_per_stance=target,
    )

    assert policy.maximum_attempts_per_stance == expected_attempts


def test_openalex_normal_search_is_metadata_only_and_typed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_openalex_response())

    adapter = _openalex_adapter(httpx.MockTransport(handler))
    response = adapter.search(
        SearchRequest(
            run_id=uuid4(),
            provider=DiscoveryProvider.OPENALEX,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="four day workweek productivity",
            limit=10,
        )
    )

    assert seen[0].url.path == "/works"
    assert seen[0].url.params["search"] == "four day workweek productivity"
    assert "search.semantic" not in seen[0].url.params
    assert response.provider_name == "openalex"
    assert response.cost_usd == Decimal("0.001")
    assert response.results[0].original_url == "https://example.edu/study"
    assert response.results[0].metadata.doi == "https://doi.org/10.1000/example"
    assert response.results[0].metadata.cited_by_count == 12


def test_openalex_semantic_search_uses_separate_parameter() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_openalex_response())

    adapter = _openalex_adapter(httpx.MockTransport(handler))
    adapter.search(
        SearchRequest(
            run_id=uuid4(),
            provider=DiscoveryProvider.OPENALEX,
            intent=SearchIntent.ACADEMIC_STUDY,
            semantic=True,
            query_text="reduced working time organizational output",
            limit=10,
        )
    )

    assert seen[0].url.params["search.semantic"] == ("reduced working time organizational output")
    assert "search" not in seen[0].url.params


def test_openalex_retracted_works_never_enter_results() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openalex_response(retracted=True))

    adapter = _openalex_adapter(httpx.MockTransport(handler))

    with pytest.raises(SearchProviderError, match="no usable"):
        adapter.search(
            SearchRequest(
                run_id=uuid4(),
                provider=DiscoveryProvider.OPENALEX,
                intent=SearchIntent.ACADEMIC_STUDY,
                query_text="four day workweek productivity",
                limit=10,
            )
        )


def test_openalex_enforces_ten_call_and_one_cent_run_ceiling() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openalex_response())

    adapter = _openalex_adapter(httpx.MockTransport(handler))
    run_id = uuid4()
    request = SearchRequest(
        run_id=run_id,
        provider=DiscoveryProvider.OPENALEX,
        intent=SearchIntent.ACADEMIC_STUDY,
        query_text="four day workweek productivity",
        limit=10,
    )
    for _ in range(10):
        adapter.search(request)

    with pytest.raises(SearchProviderError, match="OpenAlex run ceiling"):
        adapter.search(request)


def _result(
    url: str,
    title: str,
    *,
    provider: DiscoveryProvider,
    rank: int,
) -> SearchResult:
    return SearchResult(
        original_url=url,
        title=title,
        rank=rank,
        metadata=SearchDiscoveryMetadata(
            engine=provider.value,
            category="academic" if provider is DiscoveryProvider.OPENALEX else None,
            published_at="2025-01-01" if provider is DiscoveryProvider.OPENALEX else None,
            doi=(
                "https://doi.org/10.1000/example"
                if provider is DiscoveryProvider.OPENALEX
                else None
            ),
        ),
    )


def test_discovery_ranking_prefers_direct_research_over_marketing() -> None:
    run_id = uuid4()
    query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.EXA, 1)
    ranked = rank_discovery_pool(
        claim_text="A four-day workweek improves employee productivity without reducing output.",
        query_results=(
            (
                query,
                _result(
                    "https://monday.com/blog/productivity/four-day-week",
                    "Why your team should try our productivity tools",
                    provider=DiscoveryProvider.EXA,
                    rank=1,
                ),
            ),
            (
                query,
                _result(
                    "https://autonomy.work/portfolio/uk-four-day-week-pilot-results",
                    "The results of the UK four-day week pilot: productivity and revenue",
                    provider=DiscoveryProvider.EXA,
                    rank=2,
                ),
            ),
        ),
        source_target=5,
    )

    assert ranked[0].result.original_url.startswith("https://autonomy.work/")
    marketing = next(item for item in ranked if "monday.com" in item.result.original_url)
    assert marketing.components.marketing_or_community_penalty == -20


def test_claim_facet_bonus_demotes_generic_academic_matches_without_excluding_them() -> None:
    run_id = uuid4()
    query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.OPENALEX, 1)
    ranked = rank_discovery_pool(
        claim_text="Remote work makes software teams less productive.",
        claim_facets=("software teams", "remote work", "less productive"),
        query_results=(
            (
                query,
                _result(
                    "https://example.edu/remote-sensing",
                    "Remote systems for aerial data collection",
                    provider=DiscoveryProvider.OPENALEX,
                    rank=1,
                ),
            ),
            (
                query,
                _result(
                    "https://example.edu/developer-productivity",
                    "How working from home affects software developer productivity",
                    provider=DiscoveryProvider.OPENALEX,
                    rank=2,
                ),
            ),
        ),
        source_target=5,
    )

    assert "developer-productivity" in ranked[0].result.original_url
    assert ranked[1].decision is not DiscoveryDecision.DISCARDED


def test_broad_claim_has_no_required_missing_facet_gate() -> None:
    run_id = uuid4()
    query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.EXA, 1)
    ranked = rank_discovery_pool(
        claim_text="Remote work affects productivity.",
        claim_facets=(),
        query_results=(
            (
                query,
                _result(
                    "https://example.edu/productivity",
                    "Remote work and employee productivity",
                    provider=DiscoveryProvider.EXA,
                    rank=1,
                ),
            ),
        ),
        source_target=5,
    )

    assert ranked[0].score >= 20


def test_discovery_ranking_keeps_marginal_sources_above_relaxed_floor() -> None:
    run_id = uuid4()
    query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.EXA, 1)
    ranked = rank_discovery_pool(
        claim_text="Four-day workweek productivity",
        query_results=(
            (
                query,
                _result(
                    "https://example.com/",
                    "Welcome",
                    provider=DiscoveryProvider.EXA,
                    rank=1,
                ),
            ),
        ),
        source_target=5,
    )

    assert DISCARD_SCORE_FLOOR == 5
    assert 5 <= ranked[0].score < 20
    assert ranked[0].decision is DiscoveryDecision.SELECTED


def test_discovery_ranking_still_discards_near_zero_sources() -> None:
    run_id = uuid4()
    query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.EXA, 1)
    ranked = rank_discovery_pool(
        claim_text="Four-day workweek productivity",
        query_results=(
            (
                query,
                _result(
                    "https://monday.com/",
                    "Welcome",
                    provider=DiscoveryProvider.EXA,
                    rank=1,
                ),
            ),
        ),
        source_target=5,
    )

    assert ranked[0].score < DISCARD_SCORE_FLOOR
    assert ranked[0].decision is DiscoveryDecision.DISCARDED


@pytest.mark.parametrize("source_target", [5, 10, 15, 20])
def test_discovery_ranking_selects_only_top_n_without_reserved_slots(
    source_target: int,
) -> None:
    run_id = uuid4()
    query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.EXA, 1)
    query_results = tuple(
        (
            query,
            _result(
                f"https://research.example.edu/studies/{index}",
                f"Four-day workweek productivity study {index}",
                provider=DiscoveryProvider.EXA,
                rank=index,
            ),
        )
        for index in range(1, 31)
    )

    ranked = rank_discovery_pool(
        claim_text="Four-day workweek productivity",
        query_results=query_results,
        source_target=source_target,
    )
    selected = [item for item in ranked if item.decision is DiscoveryDecision.SELECTED]

    assert len(selected) == source_target
    assert [item.selection_rank for item in selected] == list(range(1, source_target + 1))


def test_discovery_ranking_collapses_only_exact_canonical_urls() -> None:
    run_id = uuid4()
    exa_query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.EXA, 1)
    openalex_query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.OPENALEX, 1)
    url = "https://example.edu/study?utm_source=test"
    ranked = rank_discovery_pool(
        claim_text="Four-day workweek productivity",
        query_results=(
            (
                exa_query,
                _result(
                    url,
                    "Four-day workweek productivity study",
                    provider=DiscoveryProvider.EXA,
                    rank=1,
                ),
            ),
            (
                openalex_query,
                _result(
                    "https://example.edu/study",
                    "Four-day workweek productivity study",
                    provider=DiscoveryProvider.OPENALEX,
                    rank=1,
                ),
            ),
        ),
        source_target=5,
    )

    assert len(ranked) == 1


def test_acquired_source_ranking_moves_weak_text_to_bottom_without_deleting_it() -> None:
    run_id = uuid4()
    query = _query(run_id, Stance.SUPPORTING, DiscoveryProvider.EXA, 1)
    strong_retrieval = RetrievalRecord(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        query_id=query.query_id,
        query_round=1,
        query_text=query.query_text,
        search_rank=1,
        source_url="https://example.edu/study",
        resolved_url="https://example.edu/study",
        status=RetrievalStatus.RETRIEVED,
        retrieved_at=NOW,
    )
    weak_retrieval = strong_retrieval.model_copy(
        update={
            "retrieval_attempt_id": uuid4(),
            "search_rank": 2,
            "source_url": "https://example.com/",
            "resolved_url": "https://example.com/",
        }
    )
    strong_text = (
        "A four-day workweek productivity study measured employee output and evidence. " * 30
    )
    weak_text = "Welcome to our community and our product."
    snapshots = tuple(
        SourceSnapshot(
            run_id=run_id,
            snapshot_id=uuid4(),
            retrieval_attempt_id=retrieval.retrieval_attempt_id,
            source_url=retrieval.resolved_url,
            original_url=retrieval.source_url,
            retrieved_at=NOW,
            normalized_text=text,
            snapshot_sha256=sha256(text.encode()).hexdigest(),
            word_count=len(text.split()),
            truncated=False,
            created_at=NOW,
        )
        for retrieval, text in (
            (weak_retrieval, weak_text),
            (strong_retrieval, strong_text),
        )
    )

    ranked = rank_acquired_sources(
        claim_text="A four-day workweek improves productivity.",
        snapshots=snapshots,
        retrievals=(weak_retrieval, strong_retrieval),
    )

    assert [item.snapshot_id for item in ranked] == [
        snapshots[1].snapshot_id,
        snapshots[0].snapshot_id,
    ]
    assert len(ranked) == 2


class _SearchLane:
    def __init__(self, responses: list[SearchResponse | SearchProviderError]) -> None:
        self.responses = responses
        self.requests: list[SearchRequest] = []

    def search(self, request: SearchRequest) -> SearchResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, SearchProviderError):
            raise response
        return response


def test_composite_search_uses_semantic_openalex_only_for_weak_normal_results() -> None:
    weak = SearchResponse(
        provider_name="openalex",
        results=[
            _result(
                "https://example.edu/unrelated",
                "Welcome",
                provider=DiscoveryProvider.OPENALEX,
                rank=1,
            ).model_copy(update={"relevance_score": 1.0})
        ],
    )
    strong = SearchResponse(
        provider_name="openalex",
        results=[
            _result(
                "https://example.edu/study",
                "Four-day workweek productivity study",
                provider=DiscoveryProvider.OPENALEX,
                rank=1,
            ).model_copy(update={"relevance_score": 80.0})
        ],
    )
    exa = _SearchLane([])
    openalex = _SearchLane([weak, strong])
    composite = CompositeSearchProvider(exa=cast(object, exa), openalex=cast(object, openalex))

    response = composite.search(
        SearchRequest(
            run_id=uuid4(),
            provider=DiscoveryProvider.OPENALEX,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="four day workweek productivity",
            limit=10,
        )
    )

    assert response.results[0].original_url == "https://example.edu/study"
    assert [request.semantic for request in openalex.requests] == [False, True]


def test_composite_search_degrades_after_bounded_transient_openalex_failures() -> None:
    transient = SearchProviderError(
        SearchFailureCode.TRANSIENT_OUTAGE,
        "temporary",
        retryable=True,
    )
    openalex = _SearchLane([transient, transient])
    composite = CompositeSearchProvider(
        exa=cast(object, _SearchLane([])),
        openalex=cast(object, openalex),
    )

    response = composite.search(
        SearchRequest(
            run_id=uuid4(),
            provider=DiscoveryProvider.OPENALEX,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="four day workweek productivity",
            limit=10,
        )
    )

    assert response.results == []
    assert response.degraded_pool is True
    assert len(openalex.requests) == 2


def test_provider_specific_queries_round_trip_through_schema_migration(
    tmp_path: Path,
) -> None:
    planner = _planner(balanced=False)
    db_path = str(tmp_path / "mlp4.sqlite3")
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=planner.run_id,
            status=RunStatus.PLANNED,
            raw_claim=planner.claim_definition.claim_text,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_planner_output(db_path, planner)

    restored = read_planner_output(db_path, planner.run_id)

    assert restored == planner
    assert len(restored.queries_for_provider(DiscoveryProvider.OPENALEX)) == 1


def test_post_run_research_trail_reads_persisted_discovery_scores(tmp_path: Path) -> None:
    planner = _planner(balanced=False)
    query = planner.queries_for_provider(DiscoveryProvider.EXA)[0]
    ranking = rank_discovery_pool(
        claim_text=planner.claim_definition.claim_text,
        query_results=(
            (
                query,
                _result(
                    "https://example.com/",
                    "Welcome",
                    provider=DiscoveryProvider.EXA,
                    rank=1,
                ),
            ),
        ),
        source_target=5,
    )
    pair = ResearcherPairResult(
        run_id=planner.run_id,
        supporting=ResearcherStageResult(
            run_id=planner.run_id,
            stance="supporting",
            status=ResearcherSideStatus.COMPLETED,
            retrieval_batch=ResearcherRetrievalBatch(
                run_id=planner.run_id,
                stance=Stance.SUPPORTING,
                intended_attempt_count=5,
                discovery_results_per_query=10,
                usable_snapshots_per_query=5,
                source_target_per_stance=5,
                discovery_ranking=ranking,
                outcomes=[],
                snapshots=[],
            ),
        ),
        opposing=ResearcherStageResult(
            run_id=planner.run_id,
            stance="opposing",
            status=ResearcherSideStatus.SKIPPED,
        ),
    )
    db_path = str(tmp_path / "trail.sqlite3")
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=planner.run_id,
            status=RunStatus.COMPLETED,
            raw_claim=planner.claim_definition.claim_text,
            current_stage=Stage.FINAL_RENDERER_VALIDATOR,
            created_at=NOW,
            updated_at=NOW,
            completed_at=NOW,
        ),
    )
    insert_stage_artifact(
        db_path,
        PersistedStageArtifact(
            run_id=planner.run_id,
            artifact_key=PHASE9_RESEARCHERS_ARTIFACT,
            artifact_type=ResearcherPairResult.__name__,
            payload_json=pair.model_dump_json(),
            created_at=NOW,
        ),
    )

    trail = LiveResearchController(environment={}).research_trail(db_path, planner.run_id)

    assert len(trail.items) == 1
    assert trail.items[0].provider == "exa"
    assert trail.items[0].decision == "selected"
    assert trail.items[0].breakdown.penalties == -25
