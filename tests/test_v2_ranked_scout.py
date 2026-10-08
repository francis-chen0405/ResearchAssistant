from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from agents.v2_discovery import (
    V2DiscoveryResponse,
    _ranked_scout_selection,
    _scout_candidate,
    cluster_discovery_items,
    normalize_discovery_responses,
)
from providers.llm import LLMProviderCapabilities, LLMRequest
from providers.search import SearchDiscoveryMetadata, SearchResult
from providers.v2_budget import V2BudgetSnapshot
from providers.v2_routing import V2RoutingConfig
from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.metadata_ranking import (
    MetadataRank,
    V2MetadataRankingArtifact,
    V2ScoutDisposition,
)
from researchassistant.contracts.model_contracts import (
    DiscoveryProvider,
    RunManifest,
    RunStatus,
    Stage,
    StrictModel,
)
from researchassistant.contracts.model_research import (
    NormalizedDiscoveryItem,
    ResearchDirection,
    ResearchDirections,
    ScoutBatch,
    ScoutItem,
    V2DiscoveryScoutOutput,
    V2InitialPlannerOutput,
    V2PipelineIdentity,
    V2RoundOneSearchQuery,
)
from researchassistant.research.metadata_ranking import rank_metadata
from researchassistant.storage.store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_v2_artifact,
)

NOW = datetime(2026, 10, 7, tzinfo=UTC)


class _RecallScout:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self) -> None:
        self.requests: list[object] = []

    def generate(self, request: object) -> ScoutBatch:
        self.requests.append(request)
        artifact = request.input_artifact
        return ScoutBatch(
            run_id=request.run_id,
            items=tuple(
                ScoutItem(item_id=candidate.item_id, decision="maybe", rationale="uncertain")
                for candidate in artifact.candidates
            ),
        )


class _PaddedPromptScout(_RecallScout):
    def conservative_input_tokens(self, request: LLMRequest, minimum_tokens: int) -> int:
        del request, minimum_tokens
        return 300_000


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
        repository_revision="v2-ranked-scout-tests",
    )


def _discovery_pool(count: int = 25) -> tuple[NormalizedDiscoveryItem, ...]:
    run_id = uuid4()
    query = V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        strategy="direct_evidence",
        query_text="study impact intervention randomized controlled",
        created_at=NOW,
    )
    response = V2DiscoveryResponse(
        query=query,
        results=tuple(
            SearchResult(
                original_url=f"https://journals.example.test/paper-{index}",
                title=(
                    "Highly relevant randomized study "
                    if index == count - 1
                    else "General article "
                )
                + str(index),
                snippet="randomized controlled primary study outcomes",
                rank=index + 1,
                metadata=SearchDiscoveryMetadata(
                    engine="openalex",
                    abstract=("randomized intervention study claim outcome " * 300),
                    work_type="article",
                    doi=f"10.1000/{index}",
                ),
            )
            for index in range(count)
        ),
    )
    return normalize_discovery_responses(
        run_id=run_id,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        responses=(response,),
        discovered_at=NOW,
    )


def _mixed_pool() -> tuple[NormalizedDiscoveryItem, ...]:
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=True)
    responses = []
    for direction, count in (
        (ResearchDirection.SUPPORT, 15),
        (ResearchDirection.CHALLENGE, 1),
    ):
        query = V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=direction,
            provider=DiscoveryProvider.OPENALEX,
            strategy="direct_evidence",
            query_text=f"{direction.value} randomized study intervention",
            created_at=NOW,
        )
        responses.append(
            V2DiscoveryResponse(
                query=query,
                results=tuple(
                    SearchResult(
                        original_url=f"https://journals.example.test/{direction.value}-{index}",
                        title=f"Randomized intervention study {direction.value} {index}",
                        snippet="randomized controlled primary study outcomes",
                        rank=index + 1,
                        metadata=SearchDiscoveryMetadata(
                            engine="openalex",
                            abstract="A randomized study of the intervention and outcomes.",
                            work_type="article",
                            doi=f"10.2000/{direction.value}-{index}",
                        ),
                    )
                    for index in range(count)
                ),
            )
        )
    return normalize_discovery_responses(
        run_id=run_id,
        directions=directions,
        responses=tuple(responses),
        discovered_at=NOW,
    )


def _snapshot(calls: int) -> V2BudgetSnapshot:
    return V2BudgetSnapshot(
        physical_calls_used=160 - calls,
        token_exposure=0,
        cost_exposure_usd=Decimal("0"),
        physical_calls_remaining=calls,
        tokens_remaining=500_000,
        cost_remaining_usd=Decimal("20"),
    )


def test_ranked_scout_reserves_both_attempts_and_records_unseen_items() -> None:
    items = _discovery_pool()
    policy = V2MetadataDiscoveryPolicy()
    ranks = rank_metadata(items, exact_claim="A study about an intervention", policy=policy)
    selected, sidecar = _ranked_scout_selection(
        run_id=items[0].run_id,
        round_number=1,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        items=items,
        ranks=ranks,
        policy=policy,
        routing_config=_routing(),
        llm_provider=_RecallScout(),
        budget_snapshot=lambda: _snapshot(10),
        downstream_input_tokens=None,
    )

    assert len(selected) == 20
    assert sidecar.scouted_count == 20
    assert sidecar.budget_limited_count == 5
    assert sidecar.cap_limited_count == 0
    assert sum(item.disposition == "scouted" for item in sidecar.scout_dispositions) == 20
    assert all(item.disposition != "skip" for item in sidecar.scout_dispositions)


def test_near_zero_budget_sends_no_scout_call_and_preserves_cap_dispositions() -> None:
    items = _discovery_pool(8)
    policy = V2MetadataDiscoveryPolicy()
    ranks = rank_metadata(items, exact_claim="intervention study", policy=policy)
    selected, sidecar = _ranked_scout_selection(
        run_id=items[0].run_id,
        round_number=1,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        items=items,
        ranks=ranks,
        policy=policy,
        routing_config=_routing(),
        llm_provider=_RecallScout(),
        budget_snapshot=lambda: _snapshot(8),
        downstream_input_tokens=None,
    )

    assert selected == ()
    assert sidecar.scouted_count == 0
    assert sidecar.budget_limited_count == 8
    assert sidecar.cap_limited_count == 0


def test_scout_affordability_uses_selected_adapter_prompt_estimate() -> None:
    items = _discovery_pool(1)
    policy = V2MetadataDiscoveryPolicy()
    ranks = rank_metadata(items, exact_claim="intervention study", policy=policy)
    selected, sidecar = _ranked_scout_selection(
        run_id=items[0].run_id,
        round_number=1,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        items=items,
        ranks=ranks,
        policy=policy,
        routing_config=_routing(),
        llm_provider=_PaddedPromptScout(),
        budget_snapshot=lambda: _snapshot(10),
        downstream_input_tokens=None,
    )

    assert selected == ()
    assert sidecar.budget_limited_count == 1


def test_fair_ranked_scout_keeps_scarce_enabled_lane() -> None:
    items = _mixed_pool()
    policy = V2MetadataDiscoveryPolicy(max_scout_per_round=10, max_acquisition_per_round=10)
    ranks = rank_metadata(items, exact_claim="randomized intervention study", policy=policy)
    selected, sidecar = _ranked_scout_selection(
        run_id=items[0].run_id,
        round_number=1,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=True),
        items=items,
        ranks=ranks,
        policy=policy,
        routing_config=_routing(),
        llm_provider=_RecallScout(),
        budget_snapshot=lambda: _snapshot(10),
        downstream_input_tokens=None,
    )

    assert selected
    assert {item.direction for item in selected} == {
        ResearchDirection.SUPPORT,
        ResearchDirection.CHALLENGE,
    }
    assert sidecar.scouted_count == 10


def test_ranked_scout_metadata_is_bounded_before_rendering() -> None:
    candidate = _scout_candidate(_discovery_pool(1)[0], bounded=True)

    assert len(candidate.abstract or "") == 2400
    assert len(candidate.source_url) <= 2048
    assert len(candidate.title or "") <= 400


def test_prior_keys_allow_only_a_persisted_empty_round_without_sidecar(tmp_path: Path) -> None:
    from agents.v2_discovery import _prior_work_keys

    run_id = uuid4()
    path = tmp_path / "empty-middle-round.sqlite"
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim="a claim",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(path), run_id, V2PipelineIdentity(), NOW)
    for round_number, key in ((1, "prior-round-one"),):
        item_id = uuid4()
        sidecar = V2MetadataRankingArtifact(
            run_id=run_id,
            round_number=round_number,
            ranks=(
                MetadataRank(
                    item_id=item_id,
                    rank=1,
                    score=0.5,
                    work_key=key,
                    lane_direction=ResearchDirection.SUPPORT,
                    lane_provider=DiscoveryProvider.OPENALEX,
                ),
            ),
            scout_dispositions=(
                V2ScoutDisposition(item_id=item_id, disposition="not_scouted_budget"),
            ),
            retained_count=1,
            scouted_count=0,
            cap_limited_count=0,
            budget_limited_count=1,
        )
        insert_v2_artifact(
            str(path), f"phase-3-metadata-ranking-round-{round_number}", sidecar, NOW
        )
    empty_round = V2DiscoveryScoutOutput(
        run_id=run_id,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        items=(),
        clusters=(),
        scout_batches=(),
        scout_audits=(),
        completed_at=NOW,
    )
    insert_v2_artifact(str(path), "phase-7-round-2-discovery-scout", empty_round, NOW)

    assert _prior_work_keys(str(path), run_id, 3) == ("prior-round-one",)


def test_fresh_clusters_retain_only_safe_provider_pdf_locations() -> None:
    run_id = uuid4()
    query = V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        strategy="academic_studies",
        query_text="intervention study",
        created_at=NOW,
    )
    results = tuple(
        SearchResult(
            original_url=f"https://journals.example.test/paper-{index}",
            title=f"Study {index}",
            rank=index + 1,
            metadata=SearchDiscoveryMetadata(
                engine="openalex",
                doi=f"10.4000/{0 if index < 2 else index}",
                pdf_url=location,
                full_text_url=("https://mirror.example.org/article.pdf" if index == 1 else None),
            ),
        )
        for index, location in enumerate(
            (
                "https://files.example.org/article.pdf",
                "https://mirror.example.org/article.pdf",
                "https://reader:secret@files.example.org/article.pdf",
                "http://127.0.0.1/article.pdf",
            )
        )
    )
    items = normalize_discovery_responses(
        run_id=run_id,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        responses=(V2DiscoveryResponse(query=query, results=results),),
        discovered_at=NOW,
    )

    legacy = cluster_discovery_items(items)
    fresh = cluster_discovery_items(items, include_provider_locations=True)
    valid_pdf = "https://files.example.org/article.pdf"
    assert all(valid_pdf not in cluster.alternate_urls for cluster in legacy)
    shared_work = next(cluster for cluster in fresh if len(cluster.item_ids) == 2)
    assert valid_pdf in shared_work.alternate_urls
    assert "https://mirror.example.org/article.pdf" in shared_work.alternate_urls
    assert len(shared_work.metadata_provenance) == 2
    assert all("reader:secret" not in url for cluster in fresh for url in cluster.alternate_urls)
    assert all("127.0.0.1" not in url for cluster in fresh for url in cluster.alternate_urls)


def test_conflicting_doi_metadata_is_retained_and_audited() -> None:
    run_id = uuid4()
    query = V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        strategy="academic_studies",
        query_text="intervention study",
        created_at=NOW,
    )
    items = normalize_discovery_responses(
        run_id=run_id,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        responses=(
            V2DiscoveryResponse(
                query=query,
                results=tuple(
                    SearchResult(
                        original_url="https://journal.example.org/record",
                        title="A randomized intervention study",
                        rank=index + 1,
                        metadata=SearchDiscoveryMetadata(
                            engine="openalex",
                            doi=doi,
                            work_type="article",
                        ),
                    )
                    for index, doi in enumerate(("10.5000/alpha", "10.5000/beta"))
                ),
            ),
        ),
        discovered_at=NOW,
    )
    policy = V2MetadataDiscoveryPolicy()
    ranks = rank_metadata(items, exact_claim="an intervention", policy=policy)
    _scouted, sidecar = _ranked_scout_selection(
        run_id=run_id,
        round_number=1,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        items=items,
        ranks=ranks,
        policy=policy,
        routing_config=_routing(),
        llm_provider=_RecallScout(),
        budget_snapshot=lambda: _snapshot(10),
        downstream_input_tokens=None,
    )

    assert {item.doi for item in items} == {"10.5000/alpha", "10.5000/beta"}
    assert len(sidecar.identity_conflicts) == 1
    conflict = sidecar.identity_conflicts[0]
    assert conflict.kind == "same_location_distinct_doi"
    assert set(conflict.item_ids) == {item.item_id for item in items}
    assert set(conflict.values) == {"10.5000/alpha", "10.5000/beta"}


def test_fresh_binding_gate_keeps_legacy_discovery_on_legacy_scout_path(tmp_path: Path) -> None:
    # Existing legacy path is exercised by the phase-4 suite; this assertion protects
    # the dispatch gate itself from an accidental unconditional rank activation.
    from agents import v2_discovery

    database = tmp_path / "legacy.sqlite"
    init_db(str(database))
    assert v2_discovery._fresh_ranked_binding(str(database), uuid4()) is None


def test_ranked_run_persists_sidecar_and_resumes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agents import v2_discovery

    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    queries = (
        V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.OPENALEX,
            strategy="academic_studies",
            query_text="randomized study of intervention",
            created_at=NOW,
        ),
    )
    plan = V2InitialPlannerOutput(
        run_id=run_id,
        raw_claim="A claim about an intervention.",
        directions=directions,
        discovery_providers=(DiscoveryProvider.OPENALEX,),
        searches=queries,
        planner_prompt_version="test-v2",
        planned_at=NOW,
    )
    response = V2DiscoveryResponse(
        query=queries[0],
        results=(
            SearchResult(
                original_url="https://journals.example.test/paper",
                title="A randomized intervention study",
                snippet="study findings",
                rank=12,
                metadata=SearchDiscoveryMetadata(
                    engine="openalex",
                    doi="10.3000/study",
                    abstract="A primary randomized study.",
                    work_type="article",
                ),
            ),
        ),
    )
    path = tmp_path / "ranked-run.sqlite"
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim=plan.raw_claim,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(path), run_id, V2PipelineIdentity(), NOW)
    policy = V2MetadataDiscoveryPolicy()
    binding = type("Binding", (), {"exact_claim": plan.raw_claim, "policy": policy})()
    monkeypatch.setattr(v2_discovery, "_fresh_ranked_binding", lambda _path, _run: binding)
    inserted_keys: list[str] = []
    insert_artifact = v2_discovery.insert_v2_artifact

    def record_artifact(
        db_path: str, artifact_key: str, artifact: StrictModel, created_at: datetime
    ) -> object:
        inserted_keys.append(artifact_key)
        return insert_artifact(db_path, artifact_key, artifact, created_at)

    monkeypatch.setattr(v2_discovery, "insert_v2_artifact", record_artifact)
    scout = _RecallScout()
    result = v2_discovery.run_v2_discovery_and_scout(
        db_path=path,
        planner_output=plan,
        responses=(response,),
        llm_provider=scout,
        routing_config=_routing(),
        clock=lambda: NOW,
        budget_snapshot=lambda: _snapshot(10),
    )

    assert result.ranking_artifact is not None
    assert result.ranking_artifact.ranks[0].rank == 1
    assert v2_discovery._prior_work_keys(str(path), run_id, 2) == (
        result.ranking_artifact.ranks[0].work_key,
    )
    prior_keys = v2_discovery._prior_work_keys(str(path), run_id, 2)
    reranked = rank_metadata(
        result.output.items,
        exact_claim=plan.raw_claim,
        policy=policy,
        known_work_keys=prior_keys,
    )
    assert reranked[0].novelty == 0.0
    stored = read_v2_artifact(str(path), run_id, "phase-3-metadata-ranking-round-1")
    assert stored.artifact_type == "V2MetadataRankingArtifact"
    assert inserted_keys[-2:] == [
        "phase-3-metadata-ranking-round-1",
        "phase-4-discovery-scout",
    ]
    resumed = v2_discovery.run_v2_discovery_and_scout(
        db_path=path,
        planner_output=plan,
        responses=(response,),
        llm_provider=_RecallScout(),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    assert resumed.resumed
    assert resumed.ranking_artifact == result.ranking_artifact
    assert len(scout.requests) == 1
    with pytest.raises(ValueError, match="Scout dispositions"):
        v2_discovery._read_ranking_artifact(
            str(path), plan, resumed.output.model_copy(update={"scout_batches": ()})
        )
