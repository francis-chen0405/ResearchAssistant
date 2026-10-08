from __future__ import annotations

from pathlib import Path

from test_ranked_acquisition_integration import (
    SOURCE_TEXT,
    _fresh_case,
    _run_discovery,
)
from test_v2_phase5_acquisition_probe import FixtureScraper, _response

from agents.v2_acquisition import run_v2_acquisition_probe
from researchassistant.contracts.acquisition_ranking import V2AcquisitionRankingAudit
from researchassistant.storage.store import read_v2_artifact


def test_shared_alternate_url_is_audited_as_duplicate_after_one_fetch(tmp_path: Path) -> None:
    db_path = tmp_path / "shared-alternate-disposition.sqlite"
    run_id, plan, results = _fresh_case(db_path)
    discovery_run, _scout = _run_discovery(db_path, run_id, plan, results, model_calls=10)
    assert discovery_run.ranking_artifact is not None
    assert len(discovery_run.output.clusters) >= 2

    shared_url = "https://cdn.example.test/shared-full-text.pdf"
    clusters = tuple(
        cluster.model_copy(
            update={"alternate_urls": tuple(sorted(set(cluster.alternate_urls) | {shared_url}))}
        )
        for cluster in discovery_run.output.clusters
    )
    discovery = discovery_run.output.model_copy(update={"clusters": clusters})
    scraper = FixtureScraper(
        {item.source_url: _response(item.source_url, SOURCE_TEXT) for item in discovery.items}
    )

    acquired = run_v2_acquisition_probe(
        db_path=str(db_path),
        discovery_output=discovery,
        wigolo_provider=scraper,
        clock=lambda: discovery.completed_at,
    ).output

    audit_artifact = read_v2_artifact(str(db_path), run_id, "metadata-acquisition-v2-round-1")
    audit = V2AcquisitionRankingAudit.model_validate_json(audit_artifact.payload_json)
    assert len(acquired.acquisitions) == 1
    assert len(scraper.requests) == 1
    fetched_cluster_id = acquired.acquisitions[0].cluster_id
    dispositions = {item.cluster_id: item for item in audit.dispositions}
    duplicate_rows = tuple(item for item in audit.dispositions if item.disposition == "duplicate")

    assert dispositions[fetched_cluster_id].disposition == "usable"
    assert len(duplicate_rows) == len(discovery.clusters) - 1
    assert all(item.shortlisted for item in duplicate_rows)
    assert audit.acquisition_shortlisted_clusters == sum(
        item.shortlisted for item in audit.dispositions
    )
    assert audit.fetched_documents == len(acquired.acquisitions) == 1
    assert audit.deduplicated_works == len(audit.dispositions) == len(discovery.clusters)
    assert all(attempt.cluster_id == fetched_cluster_id for attempt in acquired.attempts)
