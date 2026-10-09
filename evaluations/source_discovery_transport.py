"""Offline fake transport that exercises the production seed-expansion path.

This module is evaluation-only.  It builds a tiny owned round-one run in a
temporary SQLite database, sends the normal seed offer and expansion actions
through the production code, and intercepts OpenAlex HTTP with ``MockTransport``.
No credentials or live provider requests are used.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid5

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from agents.v2_acquisition import run_v2_acquisition_probe
from providers.config import OpenAlexConfig
from providers.openalex_neighborhood import OpenAlexNeighborhoodAdapter
from providers.scraper import ScrapeRequest, ScrapeResponse, ScraperProviderError
from researchassistant.contracts.discovery_v2 import (
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    V2ProductDiscoveryPolicy,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SourceSnapshot
from researchassistant.contracts.model_research import (
    V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
    DiscoveryMetadataEntry,
    DiscoveryProvenance,
    DiscoveryProviderReference,
    NormalizedDiscoveryItem,
    ResearchDirection,
    ResearchDirections,
    ScoutBatch,
    ScoutBatchAudit,
    ScoutItem,
    SourceCluster,
    V2AcquiredSource,
    V2AcquisitionPolicy,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
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
    V2SurvivingSource,
)
from researchassistant.contracts.query_planning import V2ConceptualAdaptiveLane
from researchassistant.research.query_execution import freeze_query_execution
from researchassistant.research.seed_expansion import execute_expansion, offer_expansions
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.store import (
    RunManifest,
    RunStatus,
    Stage,
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
)

_NAMESPACE = UUID("10000000-0000-4000-8000-000000000006")
_NOW = datetime(2026, 10, 8, tzinfo=UTC)


class SeedFixtureWork(BaseModel):
    """A manifest work with a stable fake OpenAlex identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    work_id: str = Field(min_length=1, max_length=80)
    openalex_id: str = Field(pattern=r"^W[0-9]{1,20}$")
    doi: str | None = None
    title: str = Field(min_length=1, max_length=300)
    abstract: str = ""
    year: int = Field(default=2024, ge=1000, le=9999)
    document: str = Field(default="", max_length=100_000)
    acquisition_outcome: Literal["usable", "shell", "unavailable"] = "usable"
    source_url: str | None = None


class SeedExpansionFixtureResult(BaseModel):
    """Observed output and counters from the ordinary production expansion path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    neighbors: tuple[SeedFixtureWork, ...]
    action_status: str
    physical_requests: int
    reserved_cost_usd: str
    actual_cost_usd: str | None
    attempt_starts: int
    dispositions: dict[str, int]
    transport_calls: int
    graph_items: tuple[NormalizedDiscoveryItem, ...]


class AcquiredPreviewFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    work_id: str
    preview: V2PreviewResult
    snapshot_text: str
    snapshot_sha256: str
    probe_succeeded: bool
    disposition: str


class AcquisitionFixtureResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    usable_work_ids: tuple[str, ...]
    dispositions: dict[str, str]
    previews: tuple[AcquiredPreviewFixture, ...]
    physical_scrape_attempts: int
    fake_transport_calls: int


class _FixtureScraper:
    def __init__(self, works_by_url: dict[str, SeedFixtureWork]) -> None:
        self.works_by_url = works_by_url
        self.requests: list[ScrapeRequest] = []

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.requests.append(request)
        try:
            work = self.works_by_url[request.url]
        except KeyError as exc:
            raise ScraperProviderError("fixture_mismatch", "Unexpected fixture URL") from exc
        if work.acquisition_outcome == "unavailable":
            raise ScraperProviderError("fixture_unavailable", "Synthetic source unavailable")
        text = (
            "Cookie settings\nSign in\nTerms of use\n"
            if work.acquisition_outcome == "shell"
            else work.document
            or (
                f"Title\n{work.title}\nMethods\nSynthetic comparison methods.\nResults\n"
                f"{work.abstract or 'The measured outcome changed in this synthetic study.'}\n"
                "Discussion\nThe result applies only to the synthetic study population."
            )
        )
        return ScrapeResponse(
            resolved_url=request.url,
            original_url=request.url,
            content_type="text/plain",
            text=text,
            provider_name="offline-fixture-scraper",
            provider_version="v1",
        )


def _id(scenario_id: str, name: str) -> UUID:
    return uuid5(_NAMESPACE, f"{scenario_id}/{name}")


def _clock() -> datetime:
    return _NOW


def _openalex_record(work: SeedFixtureWork, references: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{work.openalex_id}",
        "doi": f"https://doi.org/{work.doi}" if work.doi else None,
        "title": work.title,
        "publication_year": work.year,
        "type": "article",
        "is_retracted": False,
        "authorships": [{"author": {"display_name": "Synthetic author"}}],
        "referenced_works": [f"https://openalex.org/{item}" for item in references],
        "related_works": [],
        "primary_location": {
            "landing_page_url": f"https://fixture.invalid/{work.work_id}",
            "pdf_url": None,
        },
        "best_oa_location": None,
        "locations": [],
    }


def _install_seed_artifacts(
    path: str, run_id: UUID, scenario_id: str, claim: str, seed: SeedFixtureWork
) -> None:
    item_id = _id(scenario_id, "seed/item")
    cluster_id = _id(scenario_id, "seed/cluster")
    snapshot_id = _id(scenario_id, "seed/snapshot")
    query_id = _id(scenario_id, "seed/query")
    source_url = f"https://fixture.invalid/{scenario_id}/{seed.work_id}"
    provider = DiscoveryProvider.OPENALEX
    direction = ResearchDirection.SUPPORT
    provenance = DiscoveryProvenance(
        provider=provider,
        query_id=query_id,
        query_text=claim,
        direction=direction,
        round_number=1,
        provider_rank=1,
        original_url=source_url,
    )
    item = NormalizedDiscoveryItem(
        run_id=run_id,
        item_id=item_id,
        provider=provider,
        query_id=query_id,
        query_text=claim,
        direction=direction,
        round_number=1,
        provider_rank=1,
        source_url=source_url,
        canonical_url=source_url,
        title=seed.title,
        abstract=seed.abstract or None,
        doi=seed.doi,
        authors=("Synthetic author",),
        publication_date=f"{seed.year}-01-01",
        source_type="article",
        provider_metadata=(
            DiscoveryMetadataEntry(
                key="external_id", value_json=json.dumps(f"https://openalex.org/{seed.openalex_id}")
            ),
            DiscoveryMetadataEntry(key="is_retracted", value_json="false"),
        ),
        provenance_chain=(provenance,),
        discovered_at=_NOW,
    )
    cluster = SourceCluster(
        cluster_id=cluster_id,
        preferred_url=source_url,
        canonical_url=source_url,
        item_ids=(item_id,),
        provider_references=(
            DiscoveryProviderReference(provider=provider, item_id=item_id, provider_rank=1),
        ),
        query_references=(query_id,),
        metadata_provenance=(provenance,),
    )
    text = f"{seed.title}\nMethods\nSynthetic methods.\nResults\n{claim}."
    digest = hashlib.sha256(text.encode()).hexdigest()
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=_id(scenario_id, "seed/retrieval"),
        snapshot_id=snapshot_id,
        source_url=source_url,
        retrieved_at=_NOW,
        normalized_text=text,
        snapshot_sha256=digest,
        word_count=len(text.split()),
        truncated=False,
        created_at=_NOW,
    )
    source = V2AcquiredSource(
        cluster_id=cluster_id,
        direction=direction,
        snapshot=snapshot,
        provider=V2AcquisitionProvider.FIRECRAWL,
    )
    exact = claim[: min(len(claim), 50)]
    start = text.index(exact) if exact in text else text.index("Synthetic methods")
    span_text = text[start : start + min(40, len(text) - start)]
    preview = V2PreviewResult(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewResult", "preview/seed"),
        identity_key="preview/seed",
        request=V2PreviewRequest(
            run_id=run_id,
            artifact_id=discovery_id(run_id, "V2PreviewRequest", "preview-request/seed"),
            identity_key="preview-request/seed",
            exact_claim=claim,
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
                section="results" if start >= text.index("Results") else "methods",
                context_before=text[max(0, start - 120) : start],
                context_after=text[start + len(span_text) : start + len(span_text) + 120],
                relevance_signals=("outcome",),
                omitted_before=start > 0,
                omitted_after=start + len(span_text) < len(text),
            ),
        ),
        content_classification="full_text",
        outcome="completed",
        reason="Synthetic owned preview",
        capture_usable=True,
        relevance_score=80,
    )
    passage = V2ProbePassage(
        passage_id="seed-passage",
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
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    scout = V2DiscoveryScoutOutput(
        run_id=run_id,
        directions=directions,
        items=(item,),
        clusters=(cluster,),
        scout_batches=(
            ScoutBatch(
                run_id=run_id,
                items=(ScoutItem(item_id=item_id, decision="retrieve", rationale="fixture"),),
            ),
        ),
        scout_audits=(ScoutBatchAudit(batch_number=1, attempted_calls=1),),
        completed_at=_NOW,
    )
    acquisition = V2AcquisitionProbeOutput(
        run_id=run_id,
        directions=directions,
        acquisitions=(source,),
        attempts=(),
        probes=(probe,),
        survivors=(survivor,),
        completed_at=_NOW,
        policy_identity="researchassistant-v2-phase-5-acquisition-probe-v3",
    )
    insert_v2_artifact(path, "phase-4-discovery-scout", scout, _NOW)
    insert_v2_artifact(path, "phase-5-acquisition-probe", acquisition, _NOW)


def _install_gap_analysis(path: str, run_id: UUID, claim: str) -> None:
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    gap = V2MaterialGap(
        gap_id="fixture-gap",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="Independent outcome evidence",
        rationale="The offline fixture authorizes one neighborhood inspection.",
    )
    analysis_input = V2GapAnalysisInput(
        run_id=run_id,
        exact_claim=claim,
        directions=directions,
        attempted_queries=(),
        surviving_sources=(),
        probe_passages=(),
        source_families=(),
        discovered_terms=("outcome",),
        duplicate_patterns=(),
        acquisition_failures=(),
        previous_gaps=(),
        remaining_budget=V2GapBudgetState(model_calls_remaining=1),
    )
    result = V2GapAnalysisResult(
        coverage_summary="One synthetic outcome gap remains.",
        material_gaps=(gap,),
        continue_research=True,
        stop_reason=None,
        new_search_directions=(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=gap.direction,
                missing_evidence=gap.missing_evidence,
                search_focus="independent outcome evidence",
            ),
        ),
        discovered_terms=("outcome",),
        run_id=run_id,
        directions=directions,
        analyzed_at=_NOW,
    )
    output = V2GapAnalysisOutput(
        run_id=run_id,
        input=analysis_input,
        state=V2GapAnalysisState.COMPLETED,
        result=result,
        attempts=(),
        stop_adaptive_continuation=False,
        completed_at=_NOW,
    )
    insert_v2_artifact(path, "phase-6-gap-analysis", output, _NOW)


def run_seed_expansion_fixture(
    *,
    scenario_id: str,
    claim: str,
    seed: SeedFixtureWork,
    works: tuple[SeedFixtureWork, ...],
    neighbor_work_ids: tuple[str, ...],
    max_neighbors: int = 10,
    run_id: UUID | None = None,
) -> SeedExpansionFixtureResult:
    """Run one isolated production seed-expansion fixture and clean its SQLite state."""
    with tempfile.TemporaryDirectory(prefix="source-discovery-eval-") as directory:
        return _run_seed_expansion_fixture(
            db_path=f"{directory}/fixture.sqlite3",
            scenario_id=scenario_id,
            claim=claim,
            seed=seed,
            works=works,
            neighbor_work_ids=neighbor_work_ids,
            max_neighbors=max_neighbors,
            run_id=run_id,
        )


def _run_seed_expansion_fixture(
    *,
    db_path: str,
    scenario_id: str,
    claim: str,
    seed: SeedFixtureWork,
    works: tuple[SeedFixtureWork, ...],
    neighbor_work_ids: tuple[str, ...],
    max_neighbors: int,
    run_id: UUID | None,
) -> SeedExpansionFixtureResult:
    """Execute a real offer, exact identity resolution, and one-hop graph read.

    ``neighbor_work_ids`` are fixture IDs claimed by the synthetic seed's
    references field. The helper still validates them against the manifest and
    returns only records admitted by production ``execute_expansion``.
    """
    if not works or seed.work_id not in {work.work_id for work in works}:
        raise ValueError("the selected seed must be present in the fixture works")
    by_id = {work.work_id: work for work in works}
    if len(by_id) != len(works) or not set(neighbor_work_ids) <= set(by_id):
        raise ValueError("fixture work IDs must be unique and graph targets must be present")
    if not 1 <= max_neighbors <= 10:
        raise ValueError("fake neighborhood must remain within the production ten-work bound")

    run_id = run_id or _id(scenario_id, "run/seed-transport")
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim=claim,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), _NOW)
    policy = V2ProductDiscoveryPolicy(
        metadata_depth=max_neighbors,
        seed_expansion_enabled=True,
        scholarly_search_mode="lexical",
    )
    provider = DiscoveryProvider.OPENALEX
    freeze_query_execution(
        db_path,
        run_id,
        claim,
        ResearchDirections(support_enabled=True, challenge_enabled=False),
        (provider,),
        _clock,
        query_modes={provider: "lexical"},
        provider_configuration_fingerprint="offline-fake-openalex-v1",
        discovery_policy=policy,
    )
    _install_seed_artifacts(db_path, run_id, scenario_id, claim, seed)
    _install_gap_analysis(db_path, run_id, claim)

    target_ids = tuple(dict.fromkeys(neighbor_work_ids))[:max_neighbors]
    # Include a cycle back to the seed and a repeated target in the provider body
    # so the normal duplicate/cycle dispositions are exercised.
    references = (*target_ids, seed.work_id)
    provider_references = tuple(by_id[item].openalex_id for item in references)
    seed_record = _openalex_record(seed, provider_references)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.url.path == f"/works/{seed.openalex_id}":
            return httpx.Response(200, json=seed_record)
        if request.url.path == "/works":
            requested = request.url.params.get("filter", "")
            identifiers = [part.removeprefix("openalex:") for part in requested.split("|")]
            records = [
                _openalex_record(by_openalex)
                for identifier in identifiers
                if (
                    by_openalex := next(
                        (item for item in by_id.values() if item.openalex_id == identifier), None
                    )
                )
                is not None
            ]
            if records:
                records.append(records[0])
            return httpx.Response(200, json={"results": records})
        return httpx.Response(404, json={"error": "unexpected fake endpoint"})

    lane = V2ConceptualAdaptiveLane(
        direction=ResearchDirection.SUPPORT,
        provider=provider,
        strategy="Inspect one bounded citation neighborhood for the evaluation fixture.",
        target_gap_ids=("fixture-gap",),
    )
    actions = offer_expansions(db_path, run_id, 2, (lane,), _clock)
    if len(actions) != 1:
        raise ValueError(f"production seed offer did not produce one action: {len(actions)}")
    action = actions[0]
    if action.seed.work.provider_work_id != f"https://openalex.org/{seed.openalex_id}":
        raise ValueError("production seed selection chose a different fixture seed")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        adapter = OpenAlexNeighborhoodAdapter(
            OpenAlexConfig(api_key=SecretStr("offline-evaluation-only")), client=client
        )
        returned = execute_expansion(path=db_path, action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()

    by_openalex = {work.openalex_id: work for work in works}
    admitted = tuple(
        by_openalex[result.metadata.external_id.rsplit("/", 1)[-1]]
        for result in returned
        if result.metadata.external_id
        and result.metadata.external_id.rsplit("/", 1)[-1] in by_openalex
    )
    graph_items = tuple(
        NormalizedDiscoveryItem(
            run_id=run_id,
            item_id=_id(scenario_id, f"graph-item/{result.metadata.external_id}"),
            provider=DiscoveryProvider.OPENALEX,
            query_id=action.artifact_id,
            query_text=None,
            graph_action=action,
            direction=action.direction,
            round_number=action.round_number,
            provider_rank=result.rank,
            source_url=result.original_url,
            canonical_url=result.original_url,
            title=result.title,
            snippet=result.snippet,
            abstract=result.metadata.abstract,
            doi=result.metadata.doi,
            authors=(result.metadata.author,) if result.metadata.author else (),
            publication_date=result.metadata.published_at,
            source_type=result.metadata.work_type,
            provider_metadata=(
                DiscoveryMetadataEntry(
                    key="external_id", value_json=json.dumps(result.metadata.external_id)
                ),
                DiscoveryMetadataEntry(
                    key="is_retracted", value_json=json.dumps(result.metadata.is_retracted)
                ),
            ),
            provenance_chain=(
                DiscoveryProvenance(
                    provider=DiscoveryProvider.OPENALEX,
                    query_id=action.artifact_id,
                    query_text=None,
                    graph_action=action,
                    direction=action.direction,
                    round_number=action.round_number,
                    provider_rank=result.rank,
                    original_url=result.original_url,
                    targeted_gap_ids=action.target_gap_ids,
                ),
            ),
            discovered_at=_NOW,
        )
        for result in returned
        if result.metadata.external_id
    )
    audit = provider_attempt_audit(db_path, run_id)
    starts = [start for start in audit.starts if start.operation_id == action.artifact_id]
    completions = [
        completion
        for completion in audit.completions
        if completion and completion.operation_id == action.artifact_id
    ]
    reserved = sum((start.reserved_cost_usd for start in starts), Decimal("0"))
    known_costs = [completion.actual_cost_usd for completion in completions]
    actual = (
        str(sum(known_costs, Decimal("0")))
        if known_costs and all(value is not None for value in known_costs)
        else None
    )
    from researchassistant.contracts.discovery_v2 import V2ExpansionResult
    from researchassistant.storage.discovery_store import read_discovery_artifacts

    expansion = next(
        item
        for item in read_discovery_artifacts(db_path, run_id)
        if isinstance(item, V2ExpansionResult) and item.action.artifact_id == action.artifact_id
    )
    dispositions: dict[str, int] = {}
    from researchassistant.contracts.discovery_v2 import V2CandidateDisposition

    for item in read_discovery_artifacts(db_path, run_id):
        if isinstance(item, V2CandidateDisposition) and item.operation_id == action.artifact_id:
            dispositions[item.disposition] = dispositions.get(item.disposition, 0) + 1
    if calls != len(starts):
        raise ValueError("fake transport calls differ from durable physical request audit")
    return SeedExpansionFixtureResult(
        neighbors=admitted,
        action_status=expansion.status,
        physical_requests=len(starts),
        reserved_cost_usd=str(reserved),
        actual_cost_usd=actual,
        attempt_starts=len(starts),
        dispositions=dispositions,
        transport_calls=calls,
        graph_items=graph_items,
    )


def run_acquisition_fixture(
    scenario_id: str,
    exact_claim: str,
    works: tuple[SeedFixtureWork, ...],
) -> AcquisitionFixtureResult:
    """Run shortlisted synthetic candidates through ordinary acquisition and preview.

    The discovery Scout decisions are deterministic benchmark inputs. Acquisition,
    immutable snapshot creation, and claim-aware preview are the production stages.
    No Analyst/admission or research-model request is made by this fixture.
    """
    if len(works) > 25:
        raise ValueError("acquisition fixture exceeds the production 25-cluster ceiling")
    if len({work.work_id for work in works}) != len(works):
        raise ValueError("acquisition fixture work IDs must be unique")
    if not works:
        return AcquisitionFixtureResult(
            usable_work_ids=(),
            dispositions={},
            previews=(),
            physical_scrape_attempts=0,
            fake_transport_calls=0,
        )

    run_id = _id(scenario_id, "run/acquisition")
    with tempfile.TemporaryDirectory(prefix="source-acquisition-eval-") as directory:
        db_path = f"{directory}/fixture.sqlite3"
        init_db(db_path)
        insert_run(
            db_path,
            RunManifest(
                run_id=run_id,
                status=RunStatus.PLANNED,
                raw_claim=exact_claim,
                current_stage=Stage.CLAIM_PLANNER,
                created_at=_NOW,
                updated_at=_NOW,
            ),
        )
        insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), _NOW)
        directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
        provider = DiscoveryProvider.OPENALEX
        items: list[NormalizedDiscoveryItem] = []
        clusters: list[SourceCluster] = []
        scout_items: list[ScoutItem] = []
        work_by_url: dict[str, SeedFixtureWork] = {}
        for rank, work in enumerate(works, 1):
            item_id = _id(scenario_id, f"acquisition/{work.work_id}/item")
            cluster_id = _id(scenario_id, f"acquisition/{work.work_id}/cluster")
            query_id = _id(scenario_id, "acquisition/query")
            url = work.source_url or f"https://fixture.invalid/{scenario_id}/{work.work_id}"
            provenance = DiscoveryProvenance(
                provider=provider,
                query_id=query_id,
                query_text=exact_claim,
                direction=ResearchDirection.SUPPORT,
                round_number=1,
                provider_rank=rank,
                original_url=url,
            )
            item = NormalizedDiscoveryItem(
                run_id=run_id,
                item_id=item_id,
                provider=provider,
                query_id=query_id,
                query_text=exact_claim,
                direction=ResearchDirection.SUPPORT,
                round_number=1,
                provider_rank=rank,
                source_url=url,
                canonical_url=url,
                title=work.title,
                snippet=work.abstract or None,
                abstract=work.abstract or None,
                doi=work.doi,
                authors=("Synthetic author",),
                publication_date=f"{work.year}-01-01",
                source_type="article",
                provider_metadata=(
                    DiscoveryMetadataEntry(
                        key="external_id", value_json=json.dumps(work.openalex_id)
                    ),
                ),
                provenance_chain=(provenance,),
                discovered_at=_NOW,
            )
            cluster = SourceCluster(
                cluster_id=cluster_id,
                preferred_url=url,
                canonical_url=url,
                item_ids=(item_id,),
                provider_references=(
                    DiscoveryProviderReference(
                        provider=provider, item_id=item_id, provider_rank=rank
                    ),
                ),
                query_references=(query_id,),
                metadata_provenance=(provenance,),
            )
            items.append(item)
            clusters.append(cluster)
            scout_items.append(
                ScoutItem(item_id=item_id, decision="retrieve", rationale="Synthetic benchmark")
            )
            work_by_url[url] = work
        discovery = V2DiscoveryScoutOutput(
            run_id=run_id,
            directions=directions,
            items=tuple(items),
            clusters=tuple(clusters),
            scout_batches=(ScoutBatch(run_id=run_id, items=tuple(scout_items)),),
            scout_audits=(ScoutBatchAudit(batch_number=1, attempted_calls=1),),
            completed_at=_NOW,
        )
        scraper = _FixtureScraper(work_by_url)
        acquired = run_v2_acquisition_probe(
            db_path=db_path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            policy=V2AcquisitionPolicy(
                max_clusters=max(1, len(works)),
                allow_firecrawl_fallback=False,
                policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
            ),
            exact_claim=exact_claim,
            clock=_clock,
        ).output

        probes_by_cluster = {probe.cluster_id: probe for probe in acquired.probes}
        usable_clusters = {source.cluster_id for source in acquired.survivors}
        acquired_clusters = {source.cluster_id for source in acquired.acquisitions}
        previews = []
        dispositions: dict[str, str] = {}
        for work, cluster in zip(works, clusters, strict=True):
            probe = probes_by_cluster.get(cluster.cluster_id)
            if cluster.cluster_id not in acquired_clusters:
                dispositions[work.work_id] = "unavailable"
                continue
            source = next(
                item for item in acquired.acquisitions if item.cluster_id == cluster.cluster_id
            )
            if probe is None or probe.preview is None:
                raise ValueError("claim-aware acquisition omitted its exact preview")
            status = "usable" if cluster.cluster_id in usable_clusters else "fetched_unusable"
            dispositions[work.work_id] = status
            previews.append(
                AcquiredPreviewFixture(
                    work_id=work.work_id,
                    preview=probe.preview,
                    snapshot_text=source.snapshot.normalized_text,
                    snapshot_sha256=source.snapshot.snapshot_sha256,
                    probe_succeeded=probe.succeeded,
                    disposition=status,
                )
            )
        physical_attempts = len(acquired.attempts)
        if physical_attempts != len(scraper.requests):
            raise ValueError("fake scraper calls differ from persisted acquisition attempts")
        return AcquisitionFixtureResult(
            usable_work_ids=tuple(
                work.work_id
                for work, cluster in zip(works, clusters, strict=True)
                if cluster.cluster_id in usable_clusters
            ),
            dispositions=dispositions,
            previews=tuple(previews),
            physical_scrape_attempts=physical_attempts,
            fake_transport_calls=len(scraper.requests),
        )
