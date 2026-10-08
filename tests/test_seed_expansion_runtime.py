from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from providers.config import OpenAlexConfig
from providers.openalex_neighborhood import OpenAlexNeighborhoodAdapter
from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryBinding,
    V2DiscoveryPolicy,
    V2DiscoveryProviderBudget,
    V2GraphNeighborAction,
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    V2ProviderCapabilities,
    V2SeedEligibility,
    discovery_hash,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SourceSnapshot
from researchassistant.contracts.model_evidence import V2EvidenceRelationship
from researchassistant.contracts.model_research import (
    DiscoveryMetadataEntry,
    DiscoveryProvenance,
    DiscoveryProviderReference,
    ResearchDirection,
    ResearchDirections,
    ScoutBatch,
    ScoutBatchAudit,
    ScoutItem,
    SourceCluster,
    V2AcquiredSource,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
    V2AdaptiveSearchQuery,
    V2DiscoveryScoutOutput,
    V2GapAnalysisInput,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2GapBudgetState,
    V2GapSearchDirection,
    V2MaterialGap,
    V2PipelineIdentity,
    V2ProbePassage,
    V2ProbeResult,
    V2RoundFourDecisionCode,
    V2RoundFourGovernorDecision,
    V2RoundFourReservation,
    V2SurvivingSource,
)
from researchassistant.contracts.neighborhood import V2NeighborhoodCheckpoint
from researchassistant.contracts.query_planning import V2ConceptualAdaptiveLane
from researchassistant.research import seed_expansion as seed_expansion_module
from researchassistant.research.seed_expansion import (
    execute_expansion,
    offer_expansions,
    select_seeds,
)
from researchassistant.storage.discovery_store import (
    bind_discovery_run,
    read_discovery_artifacts,
    read_discovery_binding,
)
from researchassistant.storage.store import (
    RunManifest,
    RunStatus,
    Stage,
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_v2_artifact,
)

RUN = UUID("8eaf232a-c20b-4c93-a579-112ac61dc2f4")
NOW = datetime(2026, 10, 7, tzinfo=UTC)
CLAIM = "The intervention improves the measured outcome."
SEED_DOI = "10.5555/seed"


def _clock() -> datetime:
    return NOW


def _binding(
    path: Path, *, max_requests: int = 10, seed_identity: str = "source-seed-expansion-v2"
) -> None:
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=RUN,
            status=RunStatus.PLANNED,
            raw_claim=CLAIM,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(path), RUN, V2PipelineIdentity(), NOW)
    provider = DiscoveryProvider.OPENALEX
    capability = V2ProviderCapabilities(
        provider=provider,
        search_modes=("lexical",),
        max_metadata_per_page=10,
        max_metadata_per_operation=10,
        pagination="none",
        identity_lookup=True,
        executable_identity_lookup=True,
        relationships=("references", "citing", "related"),
        executable_relationships=("references", "citing", "related"),
        executable_search_modes=("lexical",),
        documentation_urls=("https://docs.openalex.org/api-entities/works/search-works",),
    )
    binding = V2DiscoveryBinding(
        run_id=RUN,
        artifact_id=discovery_id(RUN, "V2DiscoveryBinding", "binding"),
        identity_key="binding",
        exact_claim=CLAIM,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        providers=(provider,),
        policy=V2DiscoveryPolicy(max_seeds_per_run=3),
        capabilities=(capability,),
        provider_budgets=(
            V2DiscoveryProviderBudget(
                provider=provider,
                max_requests=max_requests,
                max_cost_usd=Decimal("0.01"),
                cost_policy_identity="offline-fixture-v1",
                reservation_per_request_usd=Decimal("0.001"),
                cost_basis="configured_upper_bound",
            ),
        ),
        provider_configuration_hash="a" * 64,
        source_identity_hash="b" * 64,
        prompt_schema_hash="c" * 64,
        seed_identity=seed_identity,  # type: ignore[arg-type]
    )
    bind_discovery_run(str(path), binding, NOW)


def _candidate(
    key: str,
    *,
    doi: str | None = SEED_DOI,
    external_id: str | None = "https://openalex.org/W1",
    title: str = "Seed study",
    authors: tuple[str, ...] = ("A. Researcher",),
    year: int | None = 2021,
    source_type: str = "article",
    retracted: bool = False,
    score: int = 80,
    capture_usable: bool = True,
) -> tuple[Any, Any, Any, Any]:
    item_id = uuid4()
    cluster_id = uuid4()
    snapshot_id = uuid4()
    query_id = uuid4()
    url = f"https://example.test/{key}"
    provider = DiscoveryProvider.OPENALEX
    direction = ResearchDirection.SUPPORT
    metadata = [
        DiscoveryMetadataEntry(key="is_retracted", value_json=json.dumps(retracted)),
    ]
    if external_id is not None:
        metadata.append(
            DiscoveryMetadataEntry(key="external_id", value_json=json.dumps(external_id))
        )
    provenance = DiscoveryProvenance(
        provider=provider,
        query_id=query_id,
        query_text=f"evidence query {key}",
        direction=direction,
        round_number=1,
        provider_rank=1,
        original_url=url,
    )
    item = {
        "run_id": RUN,
        "item_id": item_id,
        "provider": provider,
        "query_id": query_id,
        "query_text": f"evidence query {key}",
        "direction": direction,
        "round_number": 1,
        "provider_rank": 1,
        "source_url": url,
        "canonical_url": url,
        "title": title,
        "snippet": None,
        "abstract": None,
        "doi": doi,
        "authors": authors,
        "publication_date": f"{year}-01-01" if year else None,
        "source_type": source_type,
        "provider_metadata": tuple(metadata),
        "provenance_chain": (provenance,),
        "discovered_at": NOW,
    }
    from researchassistant.contracts.model_research import NormalizedDiscoveryItem

    normalized = NormalizedDiscoveryItem(**item)
    cluster = SourceCluster(
        cluster_id=cluster_id,
        preferred_url=url,
        canonical_url=url,
        item_ids=(item_id,),
        provider_references=(
            DiscoveryProviderReference(provider=provider, item_id=item_id, provider_rank=1),
        ),
        query_references=(query_id,),
        metadata_provenance=(provenance,),
    )
    text = "This study reports an improved outcome for its participants."
    digest = hashlib.sha256(text.encode()).hexdigest()
    snapshot = SourceSnapshot(
        run_id=RUN,
        retrieval_attempt_id=uuid4(),
        snapshot_id=snapshot_id,
        source_url=url,
        retrieved_at=NOW,
        normalized_text=text,
        snapshot_sha256=digest,
        word_count=len(text.split()),
        truncated=False,
        created_at=NOW,
    )
    source = V2AcquiredSource(
        cluster_id=cluster_id,
        direction=direction,
        snapshot=snapshot,
        provider=V2AcquisitionProvider.FIRECRAWL,
    )
    span_text = "improved outcome"
    start = text.index(span_text)
    preview = V2PreviewResult(
        run_id=RUN,
        artifact_id=discovery_id(RUN, "V2PreviewResult", f"preview-{key}"),
        identity_key=f"preview-{key}",
        request=V2PreviewRequest(
            run_id=RUN,
            artifact_id=discovery_id(RUN, "V2PreviewRequest", f"preview-request-{key}"),
            identity_key=f"preview-request-{key}",
            exact_claim=CLAIM,
            direction=direction,
            directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
            source_id=cluster_id,
            snapshot_id=snapshot_id,
            snapshot_hash=digest,
            preview_identity="source-claim-preview-v2",
        ),
        spans=(
            V2PreviewSpan(
                start=start,
                end=start + len(span_text),
                text=span_text,
                section="results",
                context_before=text[:start][-160:],
                context_after=text[start + len(span_text) :][:160],
                relevance_signals=("outcome",),
                omitted_before=start > 0,
                omitted_after=start + len(span_text) < len(text),
            ),
        ),
        content_classification="full_text",
        outcome="completed",
        reason="Offline relevant preview",
        capture_usable=capture_usable,
        relevance_score=score,
    )
    passage = V2ProbePassage(
        passage_id=f"passage-{key}",
        snapshot_id=snapshot_id,
        snapshot_sha256=digest,
        source_cluster_id=cluster_id,
        start_char=0,
        end_char=len(text),
        text=text,
        score=1,
        signals=("outcome",),
    )
    probe = V2ProbeResult(
        cluster_id=cluster_id,
        snapshot_id=snapshot_id,
        snapshot_sha256=digest,
        succeeded=True,
        passages=(passage,),
        preview=preview,
    )
    survivor = V2SurvivingSource(
        cluster_id=cluster_id,
        direction=direction,
        snapshot_id=snapshot_id,
        snapshot_sha256=digest,
        passage_ids=(passage.passage_id,),
    )
    return normalized, cluster, (source, probe, survivor), snapshot


def _install_round_one(path: Path, specs: tuple[dict[str, Any], ...]) -> None:
    items, clusters, acquisitions, probes, survivors = [], [], [], [], []
    for index, spec in enumerate(specs):
        item, cluster, output_parts, _ = _candidate(f"candidate-{index}", **spec)
        source, probe, survivor = output_parts
        items.append(item)
        clusters.append(cluster)
        acquisitions.append(source)
        probes.append(probe)
        survivors.append(survivor)
    scout = V2DiscoveryScoutOutput(
        run_id=RUN,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        items=tuple(items),
        clusters=tuple(clusters),
        scout_batches=(
            (
                ScoutBatch(
                    run_id=RUN,
                    items=tuple(
                        ScoutItem(item_id=item.item_id, decision="retrieve", rationale="offline")
                        for item in items
                    ),
                ),
            )
            if items
            else ()
        ),
        scout_audits=(ScoutBatchAudit(batch_number=1, attempted_calls=1),) if items else (),
        completed_at=NOW,
    )
    acquisition = V2AcquisitionProbeOutput(
        run_id=RUN,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        acquisitions=tuple(acquisitions),
        attempts=(),
        probes=tuple(probes),
        survivors=tuple(survivors),
        completed_at=NOW,
        policy_identity="researchassistant-v2-phase-5-acquisition-probe-v3",
    )
    insert_v2_artifact(str(path), "phase-4-discovery-scout", scout, NOW)
    insert_v2_artifact(str(path), "phase-5-acquisition-probe", acquisition, NOW)


def _lane(*, direction: ResearchDirection = ResearchDirection.SUPPORT) -> V2ConceptualAdaptiveLane:
    return V2ConceptualAdaptiveLane(
        direction=direction,
        provider=DiscoveryProvider.OPENALEX,
        strategy="inspect citation neighbors for a material gap",
        target_gap_ids=("gap-outcome",),
    )


def _action(path: Path, round_number: int = 2) -> V2GraphNeighborAction:
    for completed_round in range(1, round_number):
        _install_gap_analysis(path, completed_round)
    actions = offer_expansions(str(path), RUN, round_number, (_lane(),), _clock)
    assert actions
    return actions[0]


def _manual_action(
    path: Path, round_number: int = 2, relationship: str = "references"
) -> V2GraphNeighborAction:
    """Build an already-authorized slot to test execution after budget is consumed."""
    for completed_round in range(1, round_number):
        _install_gap_analysis(path, completed_round)
    selection = select_seeds(str(path), RUN, round_number - 1, _clock)
    binding = read_discovery_binding(str(path), RUN)
    key = f"manual-budget-action/round-{round_number}/{relationship}"
    return V2GraphNeighborAction(
        run_id=RUN,
        artifact_id=discovery_id(RUN, "V2GraphNeighborAction", key),
        identity_key=key,
        seed=selection.seeds[0],
        relationship=relationship,
        provider=DiscoveryProvider.OPENALEX,
        direction=ResearchDirection.SUPPORT,
        round_number=round_number,
        target_gap_ids=("gap-outcome",),
        requested_depth=min(binding.policy.metadata_depth, 3),
        policy=binding.policy,
        capabilities=binding.capabilities[0],
        seed_identity="source-seed-expansion-v2",
    )


def _install_gap_analysis(path: Path, completed_round: int) -> None:
    key = {
        1: "phase-6-gap-analysis",
        2: "phase-7-gap-analysis-after-round-2",
        3: "phase-7-gap-analysis-after-round-3",
    }[completed_round]
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    gap = V2MaterialGap(
        gap_id="gap-outcome",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="Independent outcome evidence",
        rationale="An additional source is useful for the fixture.",
    )
    gap_input = V2GapAnalysisInput(
        run_id=RUN,
        exact_claim=CLAIM,
        directions=directions,
        completed_round=completed_round,
        attempted_queries=(),
        surviving_sources=(),
        probe_passages=(),
        source_families=(),
        discovered_terms=("outcome",),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=(),
        remaining_budget=V2GapBudgetState(model_calls_remaining=5),
    )
    result = V2GapAnalysisResult(
        coverage_summary="One independent outcome gap remains.",
        material_gaps=(gap,),
        continue_research=True,
        stop_reason=None,
        new_search_directions=(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=gap.direction,
                missing_evidence=gap.missing_evidence,
                search_focus="independent outcomes",
            ),
        ),
        discovered_terms=("outcome",),
        run_id=RUN,
        directions=directions,
        analyzed_at=NOW,
    )
    output = V2GapAnalysisOutput(
        run_id=RUN,
        input=gap_input,
        state=V2GapAnalysisState.COMPLETED,
        result=result,
        attempts=(),
        stop_adaptive_continuation=False,
        completed_at=NOW,
    )
    insert_v2_artifact(str(path), key, output, NOW)


def _authorize_round_four(path: Path) -> None:
    reservation = V2RoundFourReservation(
        protected_downstream_calls=0,
        protected_downstream_tokens=0,
        protected_downstream_cost_usd=Decimal("0"),
        gap_attempt_calls=0,
        search_agent_calls=0,
        scout_calls=0,
        provider_search_calls=2,
        acquisition_cluster_capacity=0,
        optional_calls=0,
        optional_tokens=0,
        optional_cost_usd=Decimal("0"),
        available_calls=10,
    )
    decision = V2RoundFourGovernorDecision(
        run_id=RUN,
        authorized=True,
        reason_code=V2RoundFourDecisionCode.AUTHORIZED,
        explanation="Offline fixture authorization for the bounded Round-4 request.",
        reservation=reservation,
        decided_at=NOW,
    )
    insert_v2_artifact(str(path), "post-phase-13-round-4-governor-decision-v1", decision, NOW)


def _openalex_work(
    work_id: str,
    *,
    doi: str | None,
    title: str,
    year: int = 2022,
    references: tuple[str, ...] = (),
    related: tuple[str, ...] = (),
    retracted: bool = False,
) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "type": "article",
        "is_retracted": retracted,
        "authorships": [{"author": {"display_name": "A. Researcher"}}],
        "referenced_works": [f"https://openalex.org/{value}" for value in references],
        "related_works": [f"https://openalex.org/{value}" for value in related],
        "primary_location": {
            "landing_page_url": f"https://journals.example/{work_id}",
            "pdf_url": None,
        },
        "best_oa_location": None,
        "locations": [],
    }


def _adapter(handler: Any) -> tuple[OpenAlexNeighborhoodAdapter, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        OpenAlexNeighborhoodAdapter(
            OpenAlexConfig(api_key=SecretStr("offline-test-key")), client=client
        ),
        client,
    )


def _identity(
    seed: V2SeedEligibility, *, refs: tuple[str, ...] = ("W2",), related: tuple[str, ...] = ("W3",)
) -> dict[str, Any]:
    work_id = seed.work.provider_work_id.rsplit("/", 1)[-1] if seed.work.provider_work_id else "W1"
    return _openalex_work(
        work_id,
        doi=seed.work.doi or SEED_DOI,
        title=seed.work.title or "Seed study",
        year=seed.work.publication_year or 2021,
        references=refs,
        related=related,
    )


def _json_response(request: httpx.Request, data: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, request=request)


def test_select_seeds_requires_relevant_owned_previews_and_uses_relevance_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "select.sqlite"
    _binding(path)
    _install_round_one(
        path,
        (
            {
                "doi": "10.5555/low",
                "external_id": "https://openalex.org/W10",
                "title": "Lower score",
                "score": 20,
            },
            {
                "doi": "10.5555/high",
                "external_id": "https://openalex.org/W11",
                "title": "Higher score",
                "score": 90,
            },
            {
                "doi": "10.5555/unusable",
                "external_id": "https://openalex.org/W12",
                "title": "Unusable",
                "score": 100,
                "capture_usable": False,
            },
            {
                "doi": "10.5555/zero",
                "external_id": "https://openalex.org/W13",
                "title": "Zero score",
                "score": 0,
            },
            {
                "doi": "10.5555/no-year",
                "external_id": "https://openalex.org/W14",
                "title": "No year",
                "year": None,
                "score": 100,
            },
        ),
    )

    selected = select_seeds(str(path), RUN, 1, _clock)

    assert selected.status == "offered"
    assert [seed.work.doi for seed in selected.seeds] == ["10.5555/high", "10.5555/low"]
    assert all(seed.snapshot_id and seed.source_id for seed in selected.seeds)
    # Re-reading the frozen selection is idempotent and does not allocate new seeds.
    assert select_seeds(str(path), RUN, 1, _clock) == selected


def test_seed_offer_requires_openalex_lane_and_returns_nothing_without_seed(tmp_path: Path) -> None:
    path = tmp_path / "offers.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 0},))
    assert select_seeds(str(path), RUN, 1, _clock).seeds == ()
    assert offer_expansions(str(path), RUN, 2, (_lane(),), _clock) == ()
    assert offer_expansions(str(path), RUN, 5, (_lane(),), _clock) == ()

    eligible_path = tmp_path / "disabled.sqlite"
    _binding(eligible_path)
    _install_round_one(eligible_path, ({"score": 80},))
    _lane_without_provider = V2ConceptualAdaptiveLane(
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.EXA,
        strategy="use a disabled provider",
        target_gap_ids=("gap-outcome",),
    )
    assert offer_expansions(str(eligible_path), RUN, 2, (_lane_without_provider,), _clock) == ()


@pytest.mark.parametrize(
    ("relationship", "analyst_relationship"),
    (
        ("references", V2EvidenceRelationship.SUPPORTS),
        ("citing", V2EvidenceRelationship.CHALLENGES),
    ),
)
def test_graph_neighbor_enters_full_evidence_chain(
    tmp_path: Path,
    relationship: str,
    analyst_relationship: V2EvidenceRelationship,
) -> None:
    from agents.v2_discovery import (
        V2DiscoveryResponse,
        cluster_discovery_items,
        normalize_discovery_responses,
    )

    path = tmp_path / "reference.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = (
        _action(path)
        if relationship == "references"
        else _manual_action(path, relationship=relationship)
    )
    assert action.relationship == relationship
    assert action.direction is ResearchDirection.SUPPORT
    responses = [
        _identity(action.seed),
        _openalex_work(
            "W2", doi="10.5555/neighbor", title="A completely different title", references=("W1",)
        ),
    ]
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = responses.pop(0)
        return _json_response(
            request, body if request.url.path.endswith("/W1") else {"results": [body]}
        )

    adapter, client = _adapter(handler)
    try:
        results = execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()

    assert len(requests) == 2
    assert len(results) == 1, [
        (item.status, item.reason, len(item.edges))
        for item in read_discovery_artifacts(str(path), RUN)
        if type(item).__name__ == "V2ExpansionResult"
    ]
    assert results[0].metadata.external_id == "https://openalex.org/W2"
    adaptive_query = V2AdaptiveSearchQuery(
        run_id=RUN,
        query_id=action.artifact_id,
        round_number=action.round_number,
        direction=action.direction,
        provider=action.provider,
        targeted_gap_ids=action.target_gap_ids,
        strategy="citation neighborhood for gap-outcome",
        query_text=None,
        graph_action=action,
        created_at=NOW,
    )
    normalized_items = normalize_discovery_responses(
        run_id=RUN,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        responses=(V2DiscoveryResponse(query=adaptive_query, results=tuple(results)),),
        discovered_at=NOW,
    )
    assert len(cluster_discovery_items(normalized_items)) == 1
    assert normalized_items[0].graph_action == action
    # Send the graph-backed item through the same persisted Scout boundary used
    # for text-query results; Scout only sees metadata and cannot erase provenance.
    from test_v2_phase12_production import SOURCE_TEXT, _routing, _V2Model

    from agents.v2_acquisition import run_v2_acquisition_probe
    from agents.v2_discovery import run_v2_discovery_and_scout
    from providers.llm import LLMProviderCapabilities
    from providers.scraper import ScrapeResponse
    from researchassistant.contracts.model_research import V2AdaptiveRoundPlan

    class ScoutModel:
        capabilities = LLMProviderCapabilities(
            supports_temperature=True,
            supports_structured_output_control=True,
        )

        def generate(self, request: Any) -> object:
            return ScoutBatch(
                run_id=RUN,
                items=tuple(
                    ScoutItem(
                        item_id=item.item_id,
                        decision="retrieve",
                        rationale="Citation-neighborhood result merits ordinary review.",
                    )
                    for item in request.input_artifact.candidates
                ),
            )

    round_plan = V2AdaptiveRoundPlan(
        run_id=RUN,
        round_number=action.round_number,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        enabled_providers=(DiscoveryProvider.OPENALEX,),
        targeted_gap_ids=action.target_gap_ids,
        discovered_terms=(),
        searches=(
            V2AdaptiveSearchQuery(
                run_id=RUN,
                query_id=action.artifact_id,
                round_number=action.round_number,
                direction=action.direction,
                provider=action.provider,
                targeted_gap_ids=action.target_gap_ids,
                strategy="citation neighborhood for material gap",
                query_text=None,
                graph_action=action,
                created_at=NOW,
            ),
        ),
        search_agent_prompt_version="fixture-v1",
        planned_at=NOW,
    )
    scouted = run_v2_discovery_and_scout(
        db_path=str(path),
        planner_output=round_plan,
        responses=(V2DiscoveryResponse(query=round_plan.searches[0], results=tuple(results)),),
        llm_provider=ScoutModel(),
        routing_config=_routing(),
        clock=_clock,
    ).output
    assert scouted.items[0].graph_action == action
    assert scouted.items[0].provenance_chain[0].graph_action == action
    assert scouted.scout_batches[0].items[0].decision.value == "retrieve"

    class Scraper:
        def scrape(self, request: Any) -> ScrapeResponse:
            text = SOURCE_TEXT
            if relationship == "citing":
                text = (
                    "The evaluation studied matched adults in a regional program. "
                    "Among 240 surveyed adults in the regional program, 41 percent reported "
                    "completing the assigned course within six months, compared with 58 percent "
                    "of matched adults receiving the standard materials during the same "
                    "observation period. "
                    "The authors note that assignment was not randomized and self-reported "
                    "completion may not generalize beyond the participating region."
                )
            return ScrapeResponse(
                resolved_url=request.url,
                original_url=request.url,
                content_type="text/plain",
                text=text,
                provider_name="offline-neighborhood-fixture",
                provider_version="v1",
            )

    acquisition = run_v2_acquisition_probe(
        db_path=str(path),
        discovery_output=scouted,
        wigolo_provider=Scraper(),
        exact_claim=CLAIM,
        clock=_clock,
    ).output
    assert acquisition.survivors
    assert acquisition.survivors[0].cluster_id == scouted.clusters[0].cluster_id

    # Continue the very same acquired graph source through selection, exact
    # extraction, Analyst, and deterministic admission. No synthetic source is
    # substituted after discovery.
    from agents.v2_adaptive_search import V2MergedSurvivor, V2MergedSurvivorPool
    from agents.v2_evidence_admission import run_v2_evidence_admission
    from agents.v2_evidence_analyst import run_v2_evidence_analyst
    from agents.v2_extraction import run_v2_exact_extraction
    from agents.v2_source_selection import (
        build_v2_source_selection_input,
        run_v2_source_selection_and_queue,
    )
    from researchassistant.contracts.model_research import (
        V2AcquisitionProbeOutput,
        V2DeepAnalysisBudget,
        V2DiscoveryScoutOutput,
    )

    round_one_scout = V2DiscoveryScoutOutput.model_validate_json(
        read_v2_artifact(path, RUN, "phase-4-discovery-scout").payload_json
    )
    round_one_acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(path, RUN, "phase-5-acquisition-probe").payload_json
    )

    merged = V2MergedSurvivorPool(
        run_id=RUN,
        sources=(
            V2MergedSurvivor(
                research_round=action.round_number,
                source_url=scouted.clusters[0].preferred_url,
                survivor=acquisition.survivors[0],
            ),
        ),
    )
    selection_input = build_v2_source_selection_input(
        exact_claim="The regional program increases course completion.",
        merged_survivors=merged,
        discovery_outputs=(round_one_scout, scouted),
        acquisition_outputs=(round_one_acquisition, acquisition),
        gap_outputs=(),
    )
    candidate = selection_input.survivors[0]
    graph_provenance = candidate.search_provenance[0]
    assert graph_provenance.query_id == action.artifact_id
    assert graph_provenance.round_number == action.round_number
    assert graph_provenance.provider is DiscoveryProvider.OPENALEX
    assert graph_provenance.query_text is None
    assert graph_provenance.graph_action == action
    selection = run_v2_source_selection_and_queue(
        db_path=str(path),
        selection_input=selection_input,
        llm_provider=_V2Model(),
        routing_config=_routing(),
        budget=V2DeepAnalysisBudget(
            physical_call_ceiling=40,
            physical_calls_used=0,
            tokens_remaining=200_000,
            cost_remaining_usd=Decimal("1"),
        ),
        clock=_clock,
    )
    extraction = run_v2_exact_extraction(
        db_path=str(path),
        queue_result=selection.result,
        discovery_outputs=(round_one_scout, scouted),
        acquisition_outputs=(round_one_acquisition, acquisition),
        llm_provider=_V2Model(),
        routing_config=_routing(),
        clock=_clock,
    )
    snapshot_by_source = {source.cluster_id: source.snapshot for source in acquisition.acquisitions}

    class AnalystModel(_V2Model):
        def generate(self, request: Any) -> object:
            output = super().generate(request)
            if relationship == "citing" and request.requested_output_type.__name__ == (
                "V2EvidenceAnalystModelOutput"
            ):
                return output.model_copy(
                    update={
                        "narrowest_supported_proposition": (
                            "The intervention group had lower reported course completion."
                        ),
                        "canonical_factual_statement": (
                            "Among surveyed regional-program adults, 41% reported course "
                            "completion versus 58% among matched adults receiving standard "
                            "materials."
                        ),
                        "relationship_to_claim": V2EvidenceRelationship.CHALLENGES,
                    }
                )
            return output

    analyst = run_v2_evidence_analyst(
        db_path=str(path),
        batch_input=extraction.analyst_input(snapshot_by_source),
        llm_provider=AnalystModel(),
        routing_config=_routing(),
        clock=_clock,
    )
    admission = run_v2_evidence_admission(db_path=str(path), analyst_result=analyst, clock=_clock)
    assert admission.source_results[0].evidence_record is not None
    assert analyst.source_results[0].assessment.relationship_to_claim is analyst_relationship
    record = admission.source_results[0].evidence_record
    assert admission.source_results[0].source_id == candidate.source_id
    queued_candidate = analyst.input.queue_result.input.survivors[0]
    assert queued_candidate.source_id == candidate.source_id
    assert queued_candidate.search_provenance[0].query_id == action.artifact_id
    assert queued_candidate.search_provenance[0].graph_action == action
    assert record.quote_block_id == analyst.source_results[0].candidate.quote_block_id
    assert record.snapshot_id == acquisition.acquisitions[0].snapshot.snapshot_id
    assert record.snapshot_sha256 == acquisition.acquisitions[0].snapshot.snapshot_sha256
    artifacts = read_discovery_artifacts(str(path), RUN)
    from researchassistant.contracts.discovery_v2 import (
        V2ExpansionResult,
        V2NormalizedDiscoveryCandidate,
    )

    expanded = next(item for item in artifacts if isinstance(item, V2ExpansionResult))
    candidate = next(item for item in artifacts if isinstance(item, V2NormalizedDiscoveryCandidate))
    assert expanded.status == "completed"
    assert expanded.edges[0].candidate == next(
        item for item in artifacts if type(item).__name__ == "V2RawDiscoveryCandidate"
    )
    assert candidate.disposition == "retained"
    assert candidate.disposition_reason.startswith("Ordinary ranking")


def test_tangential_related_work_can_be_skipped_without_acquisition_or_ledger(
    tmp_path: Path,
) -> None:
    from test_v2_phase12_production import _routing

    from agents.v2_acquisition import run_v2_acquisition_probe
    from agents.v2_discovery import V2DiscoveryResponse, run_v2_discovery_and_scout
    from providers.llm import LLMProviderCapabilities
    from researchassistant.contracts.model_research import V2AdaptiveRoundPlan

    path = tmp_path / "tangential.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _manual_action(path, relationship="related")
    identity = _identity(action.seed, related=("W3",))
    neighbor = _openalex_work(
        "W3", doi="10.5555/tangential", title="Tangential discussion of unrelated species"
    )
    bodies = [identity, neighbor]

    def handler(request: httpx.Request) -> httpx.Response:
        body = bodies.pop(0)
        return _json_response(
            request, body if request.url.path.endswith("/W1") else {"results": [body]}
        )

    adapter, client = _adapter(handler)
    try:
        results = execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()
    assert len(results) == 1

    query = V2AdaptiveSearchQuery(
        run_id=RUN,
        query_id=action.artifact_id,
        round_number=action.round_number,
        direction=action.direction,
        provider=action.provider,
        targeted_gap_ids=action.target_gap_ids,
        strategy="inspect related work for the material gap",
        query_text=None,
        graph_action=action,
        created_at=NOW,
    )
    plan = V2AdaptiveRoundPlan(
        run_id=RUN,
        round_number=action.round_number,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        enabled_providers=(DiscoveryProvider.OPENALEX,),
        targeted_gap_ids=action.target_gap_ids,
        discovered_terms=(),
        searches=(query,),
        search_agent_prompt_version="fixture-v1",
        planned_at=NOW,
    )

    class SkipTangentialModel:
        capabilities = LLMProviderCapabilities(
            supports_temperature=True,
            supports_structured_output_control=True,
        )

        def generate(self, request: Any) -> object:
            return ScoutBatch(
                run_id=RUN,
                items=tuple(
                    ScoutItem(
                        item_id=item.item_id,
                        decision="skip",
                        rationale="Tangential related work does not address this claim.",
                    )
                    for item in request.input_artifact.candidates
                ),
            )

    scouted = run_v2_discovery_and_scout(
        db_path=str(path),
        planner_output=plan,
        responses=(V2DiscoveryResponse(query=query, results=results),),
        llm_provider=SkipTangentialModel(),
        routing_config=_routing(),
        clock=_clock,
    ).output
    assert scouted.items[0].graph_action == action
    assert scouted.scout_batches[0].items[0].decision.value == "skip"

    class UnexpectedScraper:
        def scrape(self, request: Any) -> Any:
            raise AssertionError("Scout-skipped work must not be acquired")

    acquisition = run_v2_acquisition_probe(
        db_path=str(path),
        discovery_output=scouted,
        wigolo_provider=UnexpectedScraper(),
        clock=_clock,
    ).output
    assert acquisition.acquisitions == ()
    assert acquisition.survivors == ()
    with pytest.raises(KeyError):
        read_v2_artifact(path, RUN, "phase-13-evidence-admission")


def test_citing_response_must_independently_verify_the_seed_relation(tmp_path: Path) -> None:
    path = tmp_path / "citing.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    references = _action(path, 2)
    assert references.relationship == "references"
    adapter, client = _adapter(
        lambda request: _json_response(
            request,
            _identity(references.seed)
            if request.url.path.endswith("/W1")
            else {
                "results": [
                    _openalex_work("W2", doi="10.5555/ref", title="Reference", references=("W1",))
                ]
            },
        )
    )
    try:
        execute_expansion(path=str(path), action=references, adapter=adapter, clock=_clock)
    finally:
        client.close()
    citing = _action(path, 3)
    assert citing.relationship == "citing"
    adapter, client = _adapter(
        lambda request: _json_response(
            request,
            _identity(citing.seed)
            if request.url.path.endswith("/W1")
            else {
                "results": [
                    _openalex_work(
                        "W2", doi="10.5555/conflict", title="False citing result", references=()
                    )
                ]
            },
        )
    )
    try:
        assert execute_expansion(path=str(path), action=citing, adapter=adapter, clock=_clock) == ()
    finally:
        client.close()
    artifacts = read_discovery_artifacts(str(path), RUN)
    from researchassistant.contracts.discovery_v2 import V2ExpansionResult

    result = next(
        item
        for item in artifacts
        if isinstance(item, V2ExpansionResult) and item.action.artifact_id == citing.artifact_id
    )
    assert result.status == "unavailable"
    assert result.edges == ()


def test_related_tangential_work_is_retained_for_ordinary_scout_review(tmp_path: Path) -> None:
    path = tmp_path / "related.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 80},))
    # Consume reference and citing actions first, leaving related as the next honest offer.
    first = _action(path, 2)
    adapter, client = _adapter(
        lambda request: _json_response(
            request,
            _identity(first.seed)
            if request.url.path.endswith("/W1")
            else {
                "results": [
                    _openalex_work("W2", doi="10.5555/ref", title="Reference", references=("W1",))
                ]
            },
        )
    )
    try:
        execute_expansion(path=str(path), action=first, adapter=adapter, clock=_clock)
    finally:
        client.close()
    second = _action(path, 3)
    assert second.relationship == "citing"
    adapter, client = _adapter(
        lambda request: _json_response(
            request,
            _identity(second.seed)
            if request.url.path.endswith("/W1")
            else {
                "results": [
                    _openalex_work("W4", doi="10.5555/citing", title="Citing", references=("W1",))
                ]
            },
        )
    )
    try:
        execute_expansion(path=str(path), action=second, adapter=adapter, clock=_clock)
    finally:
        client.close()
    third = _action(path, 4)
    assert third.relationship == "related"
    unauth_calls = []
    unauth_adapter, unauth_client = _adapter(
        lambda request: (
            unauth_calls.append(request) or _json_response(request, _identity(third.seed))
        )
    )
    try:
        assert (
            execute_expansion(path=str(path), action=third, adapter=unauth_adapter, clock=_clock)
            == ()
        )
    finally:
        unauth_client.close()
    assert unauth_calls == []
    _authorize_round_four(path)
    adapter, client = _adapter(
        lambda request: _json_response(
            request,
            _identity(third.seed)
            if request.url.path.endswith("/W1")
            else {
                "results": [
                    _openalex_work(
                        "W3", doi="10.5555/tangential", title="Tangential unrelated paper"
                    )
                ]
            },
        )
    )
    try:
        results = execute_expansion(path=str(path), action=third, adapter=adapter, clock=_clock)
    finally:
        client.close()
    assert len(results) == 1
    assert results[0].title == "Tangential unrelated paper"


def test_doi_aliases_and_seed_cycles_are_recorded_as_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "cycles.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 80},))
    action = _action(path)
    neighbors = [
        _openalex_work("W2", doi=SEED_DOI, title="Duplicate DOI mirror"),
        _openalex_work("W1", doi=None, title="Cycle back to seed"),
    ]
    adapter, client = _adapter(
        lambda request: _json_response(
            request,
            _identity(action.seed, refs=("W2", "W1"))
            if request.url.path.endswith("/W1")
            else {"results": neighbors},
        )
    )
    try:
        assert execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock) == ()
    finally:
        client.close()
    artifacts = read_discovery_artifacts(str(path), RUN)
    from researchassistant.contracts.discovery_v2 import V2CandidateDisposition

    duplicates = [item for item in artifacts if isinstance(item, V2CandidateDisposition)]
    assert len(duplicates) == 2
    assert {item.disposition for item in duplicates} == {"duplicate"}


def test_provider_budget_partial_and_cancellation_resume_do_not_repeat_identity(
    tmp_path: Path,
) -> None:
    budget_path = tmp_path / "budget.sqlite"
    _binding(budget_path, max_requests=1)
    _install_round_one(budget_path, ({"score": 80},))
    _install_gap_analysis(budget_path, 1)
    assert offer_expansions(str(budget_path), RUN, 2, (_lane(),), _clock) == ()
    action = _manual_action(budget_path)
    budget_calls = []
    adapter, client = _adapter(
        lambda request: (
            budget_calls.append(request) or _json_response(request, _identity(action.seed))
        )
    )
    try:
        assert (
            execute_expansion(path=str(budget_path), action=action, adapter=adapter, clock=_clock)
            == ()
        )
    finally:
        client.close()
    assert len(budget_calls) == 1
    budget_artifacts = read_discovery_artifacts(str(budget_path), RUN)
    from researchassistant.contracts.discovery_v2 import V2ExpansionResult

    assert (
        next(item for item in budget_artifacts if isinstance(item, V2ExpansionResult)).status
        == "pending"
    )

    cancel_path = tmp_path / "cancel.sqlite"
    _binding(cancel_path)
    _install_round_one(cancel_path, ({"score": 80},))
    cancel_action = _action(cancel_path)
    cancel_calls = []
    adapter, client = _adapter(
        lambda request: (
            cancel_calls.append(request)
            or _json_response(
                request,
                _identity(cancel_action.seed)
                if request.url.path.endswith("/W1")
                else {
                    "results": [
                        _openalex_work(
                            "W2", doi="10.5555/resumed", title="Resumed", references=("W1",)
                        )
                    ]
                },
            )
        )
    )
    cancel_count = 0

    def cancelled() -> bool:
        nonlocal cancel_count
        cancel_count += 1
        return cancel_count > 1

    try:
        execute_expansion(
            path=str(cancel_path),
            action=cancel_action,
            adapter=adapter,
            clock=_clock,
            cancellation_requested=cancelled,
        )
        resumed = execute_expansion(
            path=str(cancel_path), action=cancel_action, adapter=adapter, clock=_clock
        )
    finally:
        client.close()
    assert len(cancel_calls) == 2
    assert len(resumed) == 1


def test_unknown_after_start_is_not_reissued_after_crash_like_transport_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unknown.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 80},))
    action = _action(path)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("transport ended after dispatch", request=request)

    adapter, client = _adapter(handler)
    try:
        execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
        execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()
    assert len(calls) == 1


def test_completed_response_replays_after_crash_before_parser_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "response-replay.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 80},))
    action = _action(path)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _json_response(
            request,
            _identity(action.seed)
            if request.url.path.endswith("/W1")
            else {
                "results": [
                    _openalex_work(
                        "W2", doi="10.5555/replayed", title="Replayed", references=("W1",)
                    )
                ]
            },
        )

    adapter, client = _adapter(handler)
    persist_once = seed_expansion_module._persist_once
    crashed = False

    def crash_after_response(db_path: str, artifact: Any, created_at: datetime) -> None:
        nonlocal crashed
        if isinstance(artifact, V2NeighborhoodCheckpoint) and not crashed:
            crashed = True
            raise RuntimeError("simulated process loss after durable HTTP completion")
        persist_once(db_path, artifact, created_at)

    monkeypatch.setattr(seed_expansion_module, "_persist_once", crash_after_response)
    try:
        with pytest.raises(RuntimeError, match="simulated process loss"):
            execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
        monkeypatch.setattr(seed_expansion_module, "_persist_once", persist_once)
        results = execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()
    assert len(calls) == 2
    assert [result.metadata.external_id for result in results] == ["https://openalex.org/W2"]


def test_forged_hash_valid_parser_checkpoint_is_rejected_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "forged-parser.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 80},))
    action = _action(path)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _json_response(request, _identity(action.seed))

    adapter, client = _adapter(handler)
    persist_once = seed_expansion_module._persist_once
    forged_saved = False

    def persist_forged_checkpoint(db_path: str, artifact: Any, created_at: datetime) -> None:
        nonlocal forged_saved
        if isinstance(artifact, V2NeighborhoodCheckpoint) and artifact.phase == "identity":
            assert artifact.work is not None
            forged_work = artifact.work.model_copy(update={"title": "Forged identity title"})
            forged_hash = discovery_hash(
                (
                    forged_work.model_dump_json(),
                    tuple(item.model_dump_json() for item in artifact.results),
                    artifact.status,
                )
            )
            forged = V2NeighborhoodCheckpoint(
                run_id=artifact.run_id,
                artifact_id=artifact.artifact_id,
                identity_key=artifact.identity_key,
                action=artifact.action,
                phase=artifact.phase,
                attempt_id=artifact.attempt_id,
                response_hash=artifact.response_hash,
                parsed_hash=forged_hash,
                work=forged_work,
                results=artifact.results,
                status=artifact.status,
            )
            persist_once(db_path, forged, created_at)
            forged_saved = True
            raise RuntimeError("crash after injecting a checksum-valid parser record")
        persist_once(db_path, artifact, created_at)

    monkeypatch.setattr(seed_expansion_module, "_persist_once", persist_forged_checkpoint)
    try:
        with pytest.raises(RuntimeError, match="checksum-valid parser"):
            execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
        monkeypatch.setattr(seed_expansion_module, "_persist_once", persist_once)
        with pytest.raises(ValueError, match="Parser checkpoint differs"):
            execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()
    assert forged_saved
    assert len(calls) == 1


def test_ambiguous_seed_identity_stops_before_neighbor_request(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85, "external_id": None},))
    action = _action(path)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        ambiguous = [
            _openalex_work("W1", doi=SEED_DOI, title=action.seed.work.title or "Seed study"),
            _openalex_work("W9", doi=SEED_DOI, title=action.seed.work.title or "Seed study"),
        ]
        return _json_response(request, {"results": ambiguous})

    adapter, client = _adapter(handler)
    try:
        assert execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock) == ()
    finally:
        client.close()
    assert len(calls) == 1
