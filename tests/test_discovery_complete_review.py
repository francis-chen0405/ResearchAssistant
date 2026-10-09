"""Cross-phase regressions using realistic provider metadata and work aliases."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from test_openalex_neighborhood import _work
from test_seed_expansion_runtime import _binding, _install_round_one, _manual_action
from test_v2_ranked_scout import _discovery_pool

from agents.v2_discovery import cluster_discovery_items
from evaluations.source_discovery import DEFAULT_MANIFEST, evaluate_manifest
from providers.openalex_neighborhood import OpenAlexNeighborhoodAdapter
from researchassistant.contracts.model_research import DiscoveryMetadataEntry
from researchassistant.research.seed_expansion import _matches_seed


@pytest.mark.parametrize("separator", (", ", "; "))
def test_formatted_multi_author_seed_matches_exact_resolved_authors(
    tmp_path: Path, separator: str
) -> None:
    path = tmp_path / "authors.sqlite"
    _binding(path)
    names = ("A. Researcher", "B. Researcher", "C. Researcher")
    _install_round_one(path, ({"score": 85, "authors": (separator.join(names[:2]),)},))
    action = _manual_action(path)
    body = _work("W1", doi=f"https://doi.org/{action.seed.work.doi}")
    body["publication_year"] = action.seed.work.publication_year
    body["authorships"] = [{"author": {"display_name": name}} for name in names]
    resolved = OpenAlexNeighborhoodAdapter.parse_resolution("W1", httpx.Response(200, json=body))
    assert resolved.work is not None
    assert _matches_seed(action.seed, resolved.work)
    conflicting = resolved.work.model_copy(update={"authors": ("A. Researcher", "Other Author")})
    assert not _matches_seed(action.seed, conflicting)


def test_graph_parser_retains_pdf_known_only_in_locations() -> None:
    body = _work()
    body["primary_location"] = {"landing_page_url": "https://publisher.example.org/paper"}
    body["locations"] = [
        {"landing_page_url": "https://publisher.example.org/paper"},
        {"pdf_url": "https://repository.example.org/paper.pdf", "is_oa": True},
    ]
    resolved = OpenAlexNeighborhoodAdapter.parse_resolution("W123", httpx.Response(200, json=body))
    assert resolved.work is not None
    assert resolved.work.results[0].metadata.pdf_url == "https://repository.example.org/paper.pdf"


def test_fresh_clustering_preserves_distinct_identified_papers_with_same_title() -> None:
    items = _discovery_pool(2)
    items = (items[0], items[1].model_copy(update={"title": items[0].title}))
    assert len(cluster_discovery_items(items, include_provider_locations=True)) == 2
    # Historical/default clustering keeps its original equivalence and serialized identities.
    assert len(cluster_discovery_items(items)) == 1


def test_title_only_bridge_cannot_merge_conflicting_dois() -> None:
    pool = _discovery_pool(3)
    items = tuple(item.model_copy(update={"title": "Study"}) for item in pool)
    items = (items[0], items[1].model_copy(update={"doi": None}), items[2])
    clusters = cluster_discovery_items(items, include_provider_locations=True)
    assert len(clusters) == 2
    assert not any({items[0].item_id, items[2].item_id} <= set(c.item_ids) for c in clusters)


def test_provider_ids_preserve_same_title_works_without_dois() -> None:
    items = tuple(
        item.model_copy(
            update={
                "title": "Study",
                "doi": None,
                "provider_metadata": (
                    DiscoveryMetadataEntry(key="external_id", value_json=json.dumps(f"W{index}")),
                ),
            }
        )
        for index, item in enumerate(_discovery_pool(2), 1)
    )
    assert len(cluster_discovery_items(items, include_provider_locations=True)) == 2
    aliases = (
        items[0].model_copy(update={"doi": "10.1234/shared"}),
        items[1].model_copy(update={"doi": "10.1234/shared"}),
    )
    assert len(cluster_discovery_items(aliases, include_provider_locations=True)) == 1


def test_known_pdf_is_acquired_before_nonempty_publisher_shell(tmp_path: Path) -> None:
    from test_ranked_acquisition_integration import SOURCE_TEXT, _fresh_case, _run_discovery
    from test_v2_phase5_acquisition_probe import FixtureScraper, _response

    from agents.v2_acquisition import run_v2_acquisition_probe
    from providers.search import SearchDiscoveryMetadata

    path = tmp_path / "known-pdf.sqlite"
    run_id, plan, results = _fresh_case(path)
    pdf = "https://repository.example.org/study.pdf"
    results = tuple(
        item.model_copy(update={"metadata": SearchDiscoveryMetadata(pdf_url=pdf)})
        if item.rank == 18
        else item
        for item in results
    )
    discovery, _scout = _run_discovery(path, run_id, plan, results, model_calls=10)
    scraper = FixtureScraper(
        {
            **{
                item.source_url: _response(item.source_url, "Enable JavaScript.")
                for item in discovery.output.items
            },
            pdf: _response(pdf, SOURCE_TEXT),
        }
    )
    acquired = run_v2_acquisition_probe(
        db_path=str(path), discovery_output=discovery.output, wigolo_provider=scraper
    )
    assert pdf in {request.url for request in scraper.requests}
    assert any(source.snapshot.source_url == pdf for source in acquired.output.acquisitions)
    assert acquired.output.survivors


def test_work_alias_selection_does_not_reduce_expected_work_recall(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    works = {work["work_id"]: work for work in payload["scenarios"][0]["works"]}
    canonical = works["alpr-crime-study-12"]
    alias = works["alpr-crime-study-22"]
    alias["title"] = canonical["title"]
    alias["abstract"] = canonical["abstract"]
    canonical["abstract"] = ""
    canonical["title"] = "Alternate publication record"
    path = tmp_path / "alias-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = evaluate_manifest(path).scenarios[0]
    assert alias["work_id"] in result.shortlisted
    assert canonical["work_id"] not in result.shortlisted
    assert result.new_recall == 1.0
    assert result.acquired_usable_recall == 1.0


@pytest.mark.parametrize("doi", ("10.5555/work.", "10.5555/work)", "invalid-provider-doi"))
def test_fresh_doi_normalization_preserves_exact_identifiers(tmp_path: Path, doi: str) -> None:
    from test_ranked_acquisition_integration import _fresh_case, _run_discovery

    from providers.search import SearchDiscoveryMetadata
    from researchassistant.contracts.discovery_v2 import normalize_doi

    path = tmp_path / "doi.sqlite"
    run_id, plan, results = _fresh_case(path)
    changed = results[0].model_copy(update={"metadata": SearchDiscoveryMetadata(doi=doi)})
    discovery, _scout = _run_discovery(path, run_id, plan, (changed,), model_calls=10)
    expected = None if doi == "invalid-provider-doi" else normalize_doi(doi)
    assert discovery.output.items[0].doi == expected
