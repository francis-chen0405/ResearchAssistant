"""Authored held-out visibility fixtures; no useful-recall or query-policy scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from evaluations.source_discovery_transport import SeedFixtureWork, _FixtureScraper
from researchassistant.agents.v2_acquisition import run_v2_acquisition_probe
from researchassistant.contracts.acquisition_ranking import (
    V2AcquisitionRankingAudit,
    V2ClusterAcquisitionDisposition,
)
from researchassistant.contracts.metadata_ranking import (
    MetadataRank,
    V2MetadataRankingArtifact,
    V2ScoutDisposition,
)
from researchassistant.contracts.models import (
    DiscoveryProvenance,
    DiscoveryProvider,
    DiscoveryProviderReference,
    NormalizedDiscoveryItem,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    ScoutBatchAudit,
    ScoutItem,
    SourceCluster,
    Stage,
    V2AcquisitionPolicy,
    V2DiscoveryScoutOutput,
    V2PipelineIdentity,
)
from researchassistant.contracts.research_policy import V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY
from researchassistant.storage.source_leads import read_source_leads
from researchassistant.storage.store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
)

_PREPARED = Path(__file__).parent / "cases/research_quality/prepared.json"
_NOW = datetime(2026, 10, 13, tzinfo=UTC)


def _scenario(topic: dict[str, Any], folder: Path) -> dict[str, Any]:
    topic_id = topic["topic_id"]
    run_id = uuid5(NAMESPACE_URL, f"source-leads-held-out-v1/{topic_id}")
    path = folder / f"{topic_id}.sqlite"
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            raw_claim=topic["claim"],
            status=RunStatus.PLANNED,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), _NOW)
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    provider = DiscoveryProvider.OPENALEX
    items = []
    clusters = []
    scout = []
    works = {}
    ranks = []
    scout_dispositions = []
    for index in range(5):
        item_id = uuid5(run_id, f"item/{index}")
        cluster_id = uuid5(run_id, f"cluster/{index}")
        query_id = uuid5(run_id, "query")
        url = f"https://fixture.invalid/{topic_id}/{index}"
        title = f"Authored {topic_id} lead {index}"
        provenance = DiscoveryProvenance(
            provider=provider,
            query_id=query_id,
            query_text=topic["short_query"],
            direction=ResearchDirection.SUPPORT,
            round_number=1,
            provider_rank=index + 1,
            original_url=url,
        )
        items.append(
            NormalizedDiscoveryItem(
                run_id=run_id,
                item_id=item_id,
                provider=provider,
                query_id=query_id,
                query_text=topic["short_query"],
                direction=ResearchDirection.SUPPORT,
                round_number=1,
                provider_rank=index + 1,
                source_url=url,
                canonical_url=url,
                title=title,
                snippet="Authored snippet; never verified evidence.",
                provenance_chain=(provenance,),
                discovered_at=_NOW,
            )
        )
        clusters.append(
            SourceCluster(
                cluster_id=cluster_id,
                preferred_url=url,
                canonical_url=url,
                item_ids=(item_id,),
                query_references=(query_id,),
                provider_references=(
                    DiscoveryProviderReference(
                        provider=provider, item_id=item_id, provider_rank=index + 1
                    ),
                ),
                metadata_provenance=(provenance,),
            )
        )
        ranks.append(
            MetadataRank(
                item_id=item_id,
                rank=index + 1,
                score=0.5,
                work_key=f"authored:{topic_id}:{index}",
                lane_direction=ResearchDirection.SUPPORT,
                lane_provider=provider,
                rationale=("Authored display fixture, not a relevance score.",),
            )
        )
        scout_dispositions.append(
            V2ScoutDisposition(
                item_id=item_id, disposition="not_scouted_budget" if index == 1 else "scouted"
            )
        )
        if index != 1:
            scout.append(
                ScoutItem(
                    item_id=item_id,
                    decision="skip" if index == 0 else "retrieve",
                    rationale="Authored skip decision."
                    if index == 0
                    else "Authored retrieve decision.",
                )
            )
        works[url] = SeedFixtureWork(
            work_id=str(index),
            openalex_id=f"W{index + 1}",
            title=title,
            source_url=url,
            acquisition_outcome="unavailable"
            if index == 2
            else "shell"
            if index == 3
            else "usable",
            document=(
                "Methods describe a synthetic comparison of 600 observations. "
                "Results found no significant difference in outcomes. "
                "Discussion describes limitations of the synthetic population. "
            )
            * 20,
        )
    discovery = V2DiscoveryScoutOutput(
        run_id=run_id,
        directions=directions,
        items=tuple(items),
        clusters=tuple(clusters),
        scout_batches=(ScoutBatch(run_id=run_id, items=tuple(scout)),),
        scout_audits=(ScoutBatchAudit(batch_number=1, attempted_calls=1),),
        completed_at=_NOW,
    )
    insert_v2_artifact(path, "phase-4-discovery-scout", discovery, _NOW)
    ranking = V2MetadataRankingArtifact(
        run_id=run_id,
        round_number=1,
        ranks=tuple(ranks),
        scout_dispositions=tuple(scout_dispositions),
        retained_count=5,
        scouted_count=4,
        cap_limited_count=0,
        budget_limited_count=1,
    )
    insert_v2_artifact(path, "phase-3-metadata-ranking-round-1", ranking, _NOW)
    scraper = _FixtureScraper(works)
    acquired = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim=topic["claim"],
        policy=V2AcquisitionPolicy(
            max_clusters=3,
            max_urls_per_cluster=1,
            allow_firecrawl_fallback=False,
            policy_identity=V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
        ),
        clock=lambda: _NOW,
    ).output
    assert len(scraper.requests) == len(acquired.attempts) == 3
    dispositions = ("scout_skipped", "not_scouted", "unavailable", "fetched_unusable", "usable")
    audit = V2AcquisitionRankingAudit(
        run_id=run_id,
        round_number=1,
        raw_hits=5,
        deduplicated_works=5,
        scouted_candidates=4,
        acquisition_shortlisted_clusters=3,
        fetched_documents=2,
        usable_survivors=1,
        dispositions=tuple(
            V2ClusterAcquisitionDisposition(
                cluster_id=cluster.cluster_id,
                disposition=dispositions[index],
                shortlisted=index >= 2,
            )
            for index, cluster in enumerate(clusters)
        ),
    )
    insert_v2_artifact(path, "metadata-acquisition-v2-round-1", audit, _NOW)
    before = path.read_bytes(), path.stat().st_mtime_ns
    calls_before = len(scraper.requests)
    page = read_source_leads(path, run_id, limit=100)
    assert page.total == len(page.items) == 5
    assert len(scraper.requests) == calls_before
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    stages = {step.status for item in page.items for step in item.history}
    assert {"skip", "not_scouted_budget", "failed", "unusable", "readable"} <= stages
    assert all(
        item.reason and any("Admission" in unknown for unknown in item.unknowns)
        for item in page.items
    )
    return {
        "topic_id": topic_id,
        "split": "held_out",
        "origin": "authored_fixture",
        "baseline_leads_visible_without_brief": 0,
        "source_leads_visible_without_brief": page.total,
        "source_dispositions_inspectable": len(page.items),
        "saved_database_sha256": hashlib.sha256(before[0]).hexdigest(),
        "source_bytes_and_mtime_unchanged": True,
        "capacities_both_views": {
            "saved_metadata": 5,
            "saved_scout_decisions": 4,
            "acquisition_cluster_cap": 3,
            "urls_per_cluster": 1,
        },
        "fixture_setup": {
            "fake_acquisition_attempts": len(scraper.requests),
            "model_calls": 0,
            "live_provider_requests": 0,
        },
        "incremental_rendering_calls": {"search": 0, "Scout": 0, "acquisition": 0, "model": 0},
        "dispositions": [item.model_dump(mode="json") for item in page.items],
    }


def evaluate() -> dict[str, Any]:
    prepared_bytes = _PREPARED.read_bytes()
    prepared = json.loads(prepared_bytes)
    topics = [topic for topic in prepared["topics"] if topic["split"] == "held_out"]
    with tempfile.TemporaryDirectory(prefix="source-leads-evaluation-") as directory:
        cases = [_scenario(topic, Path(directory)) for topic in topics]
    return {
        "evaluation_identity": "source-leads-visibility-fixture-v1",
        "prepared_sha256": hashlib.sha256(prepared_bytes).hexdigest(),
        "scope": "Authored transfer fixtures using held-out topic labels. The prior brief-gated "
        "view exposes zero leads without a final artifact; this compares saved-disposition "
        "availability, not human readability, factual quality or useful-source recall.",
        "cases": cases,
        "useful_source_coverage": None,
        "human_readability": None,
        "query_policy_effect": None,
        "query_policy_winner": None,
        "new_paid_provider_calls": 0,
        "new_paid_exposure_usd": "0.00",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "offline_results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: {len(report['cases'])} authored held-out visibility cases; paid calls: 0")


if __name__ == "__main__":
    main()
