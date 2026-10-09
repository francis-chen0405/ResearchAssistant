from __future__ import annotations

from evaluations.source_discovery_transport import (
    SeedFixtureWork,
    run_acquisition_fixture,
    run_seed_expansion_fixture,
)


def test_seed_evaluation_uses_owned_seed_offer_and_fake_provider_transport() -> None:
    seed = SeedFixtureWork(
        work_id="seed-paper",
        openalex_id="W100",
        doi="10.5555/seed-paper",
        title="Synthetic seed study",
        abstract="A synthetic study of an outcome.",
        year=2021,
    )
    neighbor = SeedFixtureWork(
        work_id="graph-only-paper",
        openalex_id="W200",
        doi="10.5555/graph-only-paper",
        title="Synthetic referenced study",
        abstract="A referenced synthetic study.",
        year=2023,
    )

    result = run_seed_expansion_fixture(
        scenario_id="transport-regression",
        claim="The intervention changes the measured outcome.",
        seed=seed,
        works=(seed, neighbor),
        neighbor_work_ids=(neighbor.work_id, neighbor.work_id),
    )

    assert result.action_status == "completed"
    assert result.neighbors == (neighbor,)
    assert result.transport_calls == result.physical_requests == result.attempt_starts == 2
    assert result.reserved_cost_usd == "0.002"
    assert result.actual_cost_usd is None
    # The production visited-work admission recognizes the returned seed cycle.
    assert result.dispositions == {"duplicate": 1}
    assert result.graph_items[0].graph_action is not None
    assert (
        result.graph_items[0].provenance_chain[0].graph_action == result.graph_items[0].graph_action
    )


def test_shortlist_fixture_uses_real_acquisition_snapshot_and_exact_preview() -> None:
    claim = "The intervention changes the measured outcome."
    substantive = (
        "Title\nSynthetic intervention study\nMethods\n"
        + "We compared treatment and comparison groups using repeated measures. " * 12
        + "\nResults\nThe intervention changes the measured outcome for participants. "
        + "The estimate remains uncertain and applies only to this sampled population. " * 12
        + "\nDiscussion\nThe synthetic results require cautious interpretation. " * 8
    )
    works = (
        SeedFixtureWork(
            work_id="usable-paper",
            openalex_id="W301",
            doi="10.5555/usable-paper",
            title="Synthetic intervention study",
            abstract="A synthetic study of the measured outcome.",
            year=2023,
            document=substantive,
        ),
        SeedFixtureWork(
            work_id="shell-paper",
            openalex_id="W302",
            title="Synthetic shell page",
            acquisition_outcome="shell",
        ),
        SeedFixtureWork(
            work_id="unavailable-paper",
            openalex_id="W303",
            title="Synthetic unavailable page",
            acquisition_outcome="unavailable",
        ),
    )

    result = run_acquisition_fixture("acquisition-regression", claim, works)

    assert result.dispositions == {
        "usable-paper": "usable",
        "shell-paper": "fetched_unusable",
        "unavailable-paper": "unavailable",
    }
    assert result.usable_work_ids == ("usable-paper",)
    assert result.physical_scrape_attempts == result.fake_transport_calls == 3
    usable = next(item for item in result.previews if item.work_id == "usable-paper")
    assert usable.probe_succeeded and usable.preview.capture_usable
    assert usable.preview.request.exact_claim == claim
    assert all(
        usable.snapshot_text[span.start : span.end] == span.text for span in usable.preview.spans
    )
    shell = next(item for item in result.previews if item.work_id == "shell-paper")
    assert not shell.preview.capture_usable
