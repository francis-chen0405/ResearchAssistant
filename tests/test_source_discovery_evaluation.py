from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evaluations.source_discovery import DEFAULT_MANIFEST, Manifest, evaluate_manifest


def test_manifest_is_strict_synthetic_and_covers_required_scenarios() -> None:
    manifest = Manifest.model_validate_json(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert manifest.live_quality_claim is False
    assert all(
        next(work for work in scenario.works if work.work_id == work_id).expected_rationale
        for scenario in manifest.scenarios
        for work_id in scenario.expected_work_ids
    )
    assert {scenario.topic for scenario in manifest.scenarios} >= {
        "alpr-crime",
        "alpr-discrimination",
        "biomedical",
        "non-scholarly",
    }
    with pytest.raises(ValidationError):
        Manifest.model_validate({**manifest.model_dump(), "unreviewed_field": True})


def test_manifest_rejects_duplicate_scenario_and_expected_work_ids() -> None:
    manifest = Manifest.model_validate_json(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    payload = manifest.model_dump(mode="json")

    duplicate_scenario = json.loads(json.dumps(payload))
    duplicate_scenario["scenarios"][1]["scenario_id"] = duplicate_scenario["scenarios"][0][
        "scenario_id"
    ]
    with pytest.raises(ValidationError, match="scenario IDs must be unique"):
        Manifest.model_validate(duplicate_scenario)

    duplicate_expected_work = json.loads(json.dumps(payload))
    scenario = duplicate_expected_work["scenarios"][0]
    scenario["expected_work_ids"][1] = scenario["expected_work_ids"][0]
    with pytest.raises(ValidationError, match="expected work IDs must be unique"):
        Manifest.model_validate(duplicate_expected_work)


def test_offline_eval_preserves_direct_evidence_and_reaches_deeper_and_seed_work() -> None:
    report = evaluate_manifest()
    scenarios = {scenario.scenario_id: scenario for scenario in report.scenarios}
    for scenario_id in ("alpr-crime", "alpr-discrimination", "biomedical", "non-scholarly"):
        row = scenarios[scenario_id]
        assert row.new_recall > row.baseline5_recall
        assert row.ablations["provider_specific_query_at_5"] > row.baseline5_recall
        assert row.ablations["deeper_retrieval_and_ranking"] >= row.baseline5_recall
        assert row.ablations["seed_expansion"] == row.new_recall
        # Rank-3 direct evidence remains in the shortlist while below-five work is reached.
        assert f"{scenario_id}-study-03" in row.shortlisted
        assert f"{scenario_id}-study-12" in row.shortlisted
        assert f"{scenario_id}-study-18" in row.shortlisted
        # The graph-only rank-21 neighbor follows the ordinary preview/acquisition path.
        assert f"{scenario_id}-study-21" in row.seed_only_discoveries
        assert f"{scenario_id}-study-21" in row.shortlisted
        assert f"{scenario_id}-study-21" in row.acquired_usable
        assert row.admission_status == "not_assessed"
        assert row.unresolved_independence_abstentions >= 1
        assert row.physical_requests == 20
        assert row.seed_physical_requests == 2
        assert row.acquisition_scrape_attempts == 18
        assert row.metadata_fixture_requests == 0
        assert row.seed_action_status == "completed"
        assert row.seed_dispositions
        assert row.request_budget_bound == 21
        assert row.budget_compliant
        assert row.physical_request_cost_usd is None
        assert row.reserved_provider_cost_usd is not None
        assert row.preview_exactness == 1.0
        expected_preview_quality = 0.75 if scenario_id == "biomedical" else 1.0
        assert row.useful_preview_coverage == expected_preview_quality
        assert row.preview_relevance == expected_preview_quality
        assert row.duplication_rate > 0
    disabled = scenarios["disabled-lane"]
    assert disabled.physical_requests == 0
    assert disabled.request_budget_bound == 0
    assert disabled.metadata_fixture_requests == 0
    assert disabled.shortlisted == ()
    assert disabled.acquired_usable == ()
    assert disabled.admission_status == "not_assessed"
    biomedical = scenarios["biomedical"]
    assert biomedical.new_recall == 1.0
    assert biomedical.acquired_usable_recall == 0.75
    assert biomedical.ablations["rank_only_selection_at_12"] == 0.75
    assert biomedical.ablations["preview_aware_selection_at_12"] == 0.75
    assert any("reduced expected-work recall" in item for item in biomedical.counterexamples)
    neutral = scenarios["enabled-neutral"]
    assert neutral.baseline5_recall == neutral.new_recall == 1.0
    assert neutral.seed_action_status == "completed"
    assert neutral.seed_physical_requests == 2
    assert neutral.acquired_usable_recall == 1.0
    assert neutral.ablations["deeper_retrieval_and_ranking"] == 1.0
    assert neutral.ablations["seed_expansion"] == 1.0
    assert neutral.ablations["deeper_retrieval_and_ranking"] == neutral.ablations["seed_expansion"]


def test_manifest_retains_conflicts_cycles_bibliography_and_alias_versions() -> None:
    manifest = Manifest.model_validate_json(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    scenario = next(item for item in manifest.scenarios if item.scenario_id == "alpr-crime")
    by_id = {work.work_id: work for work in scenario.works}
    assert by_id["alpr-crime-study-12"].finding == "challenges"
    assert by_id["alpr-crime-study-18"].finding == "supports"
    assert by_id["alpr-crime-study-22"].independence == "same_work"
    assert by_id["alpr-crime-study-22"].provider_rank == 19
    assert any(
        edge.source == "alpr-crime-study-01" and edge.target == "alpr-crime-study-21"
        for edge in scenario.edges
    )
    assert any(
        edge.source == "alpr-crime-study-21" and edge.target == "alpr-crime-study-01"
        for edge in scenario.edges
    )
    assert "References\n" in by_id["alpr-crime-study-18"].document
    assert "Ignore all previous instructions" in by_id["alpr-crime-study-18"].document


@pytest.mark.parametrize("other_work", ("alpr-crime-study-22", "alpr-crime-study-03"))
def test_identical_titles_preserve_graph_work_identity_and_acquisition_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, other_work: str
) -> None:
    from evaluations import source_discovery_transport
    from evaluations.source_discovery_transport import AcquisitionFixtureResult, SeedFixtureWork

    manifest = Manifest.model_validate_json(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    payload = manifest.model_dump(mode="json")
    scenario = payload["scenarios"][0]
    works = {work["work_id"]: work for work in scenario["works"]}
    works[other_work]["title"] = works["alpr-crime-study-21"]["title"]
    path = tmp_path / "same-title-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    acquired: dict[str, SeedFixtureWork] = {}
    run_acquisition = source_discovery_transport.run_acquisition_fixture

    def capture_acquisition(
        scenario_id: str, exact_claim: str, works: tuple[SeedFixtureWork, ...]
    ) -> AcquisitionFixtureResult:
        if scenario_id == "alpr-crime":
            acquired.update({work.work_id: work for work in works})
        return run_acquisition(scenario_id, exact_claim, works)

    monkeypatch.setattr(source_discovery_transport, "run_acquisition_fixture", capture_acquisition)
    report = evaluate_manifest(path)
    result = report.scenarios[0]
    assert result.new_recall == 1.0
    assert result.seed_only_discoveries == ("alpr-crime-study-21",)
    assert "alpr-crime-study-21" in result.shortlisted
    assert "alpr-crime-study-21" in result.acquired_usable
    assert acquired["alpr-crime-study-21"].source_url is not None
    assert acquired["alpr-crime-study-21"].openalex_id == "W21"
    # A same-title query record must not inherit the graph neighbor's location.
    if other_work == "alpr-crime-study-03":
        assert other_work in acquired
    if other_work in acquired:
        assert acquired[other_work].source_url is None


@pytest.mark.parametrize("provider_id", (None, "https://openalex.org/W999999"))
def test_graph_evaluation_rejects_missing_or_unknown_provider_identity(
    monkeypatch: pytest.MonkeyPatch, provider_id: str | None
) -> None:
    from evaluations import source_discovery_transport
    from evaluations.source_discovery_transport import SeedExpansionFixtureResult
    from researchassistant.contracts.model_research import DiscoveryMetadataEntry

    run_seed = source_discovery_transport.run_seed_expansion_fixture

    def changed_identity(**kwargs: Any) -> SeedExpansionFixtureResult:
        result = run_seed(**kwargs)
        item = result.graph_items[0]
        entries = tuple(entry for entry in item.provider_metadata if entry.key != "external_id")
        if provider_id is not None:
            entries += (
                DiscoveryMetadataEntry(key="external_id", value_json=json.dumps(provider_id)),
            )
        changed = item.model_copy(update={"provider_metadata": entries})
        return result.model_copy(update={"graph_items": (changed, *result.graph_items[1:])})

    monkeypatch.setattr(source_discovery_transport, "run_seed_expansion_fixture", changed_identity)
    with pytest.raises(ValueError, match="exact manifest provider identity"):
        evaluate_manifest()
