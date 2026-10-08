from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from test_query_execution import CLAIM, DIRECTIONS, _action, _clock
from test_v2_phase5_acquisition_probe import FixtureScraper, _response
from test_v2_ranked_scout import NOW, _RecallScout, _routing, _snapshot

from agents.v2_acquisition import run_v2_acquisition_probe
from agents.v2_discovery import (
    V2DiscoveryResponse,
    V2DiscoveryScoutRunResult,
    run_v2_discovery_and_scout,
)
from providers.config import SerpSearchConfig
from providers.search import SearchResult
from providers.serpsearch import SerpSearchAdapter
from researchassistant.contracts.acquisition_ranking import V2AcquisitionRankingAudit
from researchassistant.contracts.model_contracts import (
    DiscoveryProvider,
    RunManifest,
    RunStatus,
    Stage,
)
from researchassistant.contracts.model_research import (
    ResearchDirection,
    V2AcquisitionPolicy,
    V2InitialPlannerOutput,
    V2PipelineIdentity,
    V2RoundOneSearchQuery,
)
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import execute_query, freeze_query_execution
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.query_retrieval_store import read_pages as read_query_pages
from researchassistant.storage.store import (
    init_db,
    insert_run,
    insert_v2_pipeline_identity,
    read_v2_artifact,
)

STUDY_URL = "https://papers.example.test/study-18"
SOURCE_TEXT = (
    "The controlled intervention study examined changes in community outcomes. "
    "Researchers compared 640 observations before and after the intervention and "
    "reported a measured change in the primary outcome. The study describes its "
    "sampling method, comparison group, and limitations in detail. The authors "
    "conclude that the findings support further evaluation of the intervention. "
) * 5


def _organic_page(page: int) -> dict[str, object]:
    first_rank = 1 if page == 1 else 11
    results: list[dict[str, object]] = []
    for rank in range(first_rank, first_rank + 10):
        if rank == 11:
            url = "https://papers.example.test/paper-10"
            title = "Repeated result from the first page"
            snippet = "General community news and policy overview."
        elif rank == 18:
            url = STUDY_URL
            title = "Controlled intervention outcome study"
            snippet = "A randomized study measured intervention effects on the outcome."
        else:
            url = f"https://papers.example.test/paper-{rank}"
            title = f"General article {rank}"
            snippet = "General community news and policy overview."
        results.append(
            {"url": url, "title": title, "description": snippet, "position": (rank - 1) % 10 + 1}
        )
    return {"organic_results": results}


def _fresh_case(
    path: Path,
) -> tuple[
    UUID,
    V2InitialPlannerOutput,
    tuple[SearchResult, ...],
]:
    run_id = uuid4()
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim=CLAIM,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(path), run_id, V2PipelineIdentity(), NOW)
    binding = freeze_query_execution(
        str(path), run_id, CLAIM, DIRECTIONS, (DiscoveryProvider.SERPSEARCH,), _clock()
    )
    assert binding.compiler_identity == "source-query-compiler-v3"

    shallow_action = _action(run_id, DiscoveryProvider.SERPSEARCH)
    action = compile_query(shallow_action.conceptual_query, requested_depth=20)
    queries = (
        V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.SERPSEARCH,
            strategy="broad_web",
            query_text=action.query_text,
            compiled_query=action,
            created_at=NOW,
        ),
        V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.SERPSEARCH,
            strategy="institutional_coverage",
            query_text="community institution policy evidence",
            created_at=NOW,
        ),
    )
    plan = V2InitialPlannerOutput(
        run_id=run_id,
        raw_claim=CLAIM,
        directions=DIRECTIONS,
        discovery_providers=(DiscoveryProvider.SERPSEARCH,),
        searches=queries,
        planner_prompt_version="fixture-planner",
        planned_at=NOW,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, json=_organic_page(page))

    adapter = SerpSearchAdapter(
        SerpSearchConfig(api_key="offline-fixture-key"),
        client=httpx.Client(
            base_url="https://api.serpsearch.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.SERPSEARCH,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.SERPSEARCH: adapter},
        clock=_clock(),
    )
    raw_page_results = tuple(
        result
        for page in read_query_pages(str(path), run_id)
        if page.operation_id == action.artifact_id
        for result in page.response.results
    )
    return run_id, plan, raw_page_results


def _run_discovery(
    path: Path,
    run_id: UUID,
    plan: V2InitialPlannerOutput,
    results: tuple[SearchResult, ...],
    *,
    model_calls: int,
) -> tuple[V2DiscoveryScoutRunResult, _RecallScout]:
    scout = _RecallScout()
    response = V2DiscoveryResponse(query=plan.searches[0], results=results)
    output = run_v2_discovery_and_scout(
        db_path=path,
        planner_output=plan,
        responses=(response,),
        llm_provider=scout,
        routing_config=_routing(),
        clock=lambda: NOW,
        budget_snapshot=lambda: _snapshot(model_calls),
    )
    return output, scout


def _artifact_types(path: Path, run_id: UUID) -> tuple[str, ...]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT artifact_type FROM v2_artifacts WHERE run_id=?",
            (str(run_id),),
        ).fetchall()
        return tuple(row[0] for row in rows)
    finally:
        connection.close()


def test_page_two_study_reaches_scout_shortlist_and_immutable_usable_snapshot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ranked-acquisition.sqlite"
    run_id, plan, results = _fresh_case(path)
    assert len(results) == 20
    assert len(provider_attempt_audit(str(path), run_id).starts) == 2
    assert len(read_query_pages(str(path), run_id)) == 2

    discovery_run, scout = _run_discovery(path, run_id, plan, results, model_calls=10)
    study = next(item for item in discovery_run.output.items if item.source_url == STUDY_URL)
    assert study.provider_rank == 18
    assert discovery_run.ranking_artifact is not None
    study_rank = next(
        item for item in discovery_run.ranking_artifact.ranks if item.item_id == study.item_id
    )
    assert study_rank.rank <= 3
    assert discovery_run.ranking_artifact.scouted_count == 19
    assert len(scout.requests) == 1

    acquisition_text = SOURCE_TEXT
    scraper = FixtureScraper(
        {
            item.source_url: _response(item.source_url, acquisition_text)
            for item in discovery_run.output.items
        }
    )
    acquired = run_v2_acquisition_probe(
        db_path=str(path),
        discovery_output=discovery_run.output,
        wigolo_provider=scraper,
        policy=V2AcquisitionPolicy(max_clusters=3),
        clock=lambda: NOW,
    )

    audit = V2AcquisitionRankingAudit.model_validate_json(
        read_v2_artifact(str(path), run_id, "metadata-acquisition-v2-round-1").payload_json
    )
    assert (audit.raw_hits, audit.deduplicated_works) == (20, 19)
    assert audit.scouted_candidates == 19
    assert audit.acquisition_shortlisted_clusters == 3
    assert audit.fetched_documents == audit.usable_survivors == 3
    assert STUDY_URL in {request.url for request in scraper.requests}
    assert any(source.snapshot.source_url == STUDY_URL for source in acquired.output.acquisitions)
    study_acquisition = next(
        source for source in acquired.output.acquisitions if source.snapshot.source_url == STUDY_URL
    )
    assert study_acquisition.snapshot.word_count <= 3000
    assert acquired.output.survivors
    assert not any(
        "extract" in artifact.casefold() or "admission" in artifact.casefold()
        for artifact in _artifact_types(path, run_id)
    )


def test_near_zero_model_budget_keeps_candidates_unscouted_and_skips_acquisition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ranked-acquisition-budget.sqlite"
    run_id, plan, results = _fresh_case(path)
    discovery_run, scout = _run_discovery(path, run_id, plan, results, model_calls=8)

    assert scout.requests == []
    assert discovery_run.ranking_artifact is not None
    assert discovery_run.ranking_artifact.scouted_count == 0
    assert (
        discovery_run.ranking_artifact.budget_limited_count
        + discovery_run.ranking_artifact.cap_limited_count
        == len(results)
    )
    assert all(
        disposition.disposition in {"not_scouted_budget", "not_scouted_cap"}
        for disposition in discovery_run.ranking_artifact.scout_dispositions
    )

    scraper = FixtureScraper({})
    acquired = run_v2_acquisition_probe(
        db_path=str(path),
        discovery_output=discovery_run.output,
        wigolo_provider=scraper,
        clock=lambda: NOW,
    )
    audit = V2AcquisitionRankingAudit.model_validate_json(
        read_v2_artifact(str(path), run_id, "metadata-acquisition-v2-round-1").payload_json
    )

    assert scraper.requests == []
    assert acquired.output.attempts == ()
    assert acquired.output.acquisitions == ()
    assert acquired.output.survivors == ()
    assert audit.acquisition_shortlisted_clusters == audit.fetched_documents == 0
    assert all(item.disposition == "not_scouted" for item in audit.dispositions)
