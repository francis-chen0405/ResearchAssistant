"""Discovery retains query directions and safely projects optional identity metadata."""

from __future__ import annotations

from pathlib import Path

import pytest
import test_product_discovery_pipeline as product
from pydantic import ValidationError
from test_four_round_survivor_capacity import _BalancedModel
from test_seed_expansion_runtime import NOW, RUN, _binding, _clock, _install_round_one

from researchassistant.common.discovery_identity import pipeline_work_identity
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirection,
    ResearchDirections,
    ResearchMode,
    V2DiscoveryScoutOutput,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
    V2SourceSelectionSearchProvenance,
)
from researchassistant.contracts.query_planning import V2NeighborhoodSearchOutput
from researchassistant.providers.llm import LLMRequest
from researchassistant.research.seed_expansion import select_seeds
from researchassistant.research.v2_orchestrator import V2ProductionState, run_v2_production_pipeline
from researchassistant.storage.store import read_v2_artifact


def test_same_work_in_both_search_lanes_reconciles_without_cross_lane_evidence_credit(
    tmp_path: Path,
) -> None:
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX),
        research_mode=ResearchMode.BALANCED,
        sources_per_stance_per_round=20,
    )
    model, search = _BalancedModel(completed_rounds=4), product._WideSearch()
    path = tmp_path / "generated.sqlite3"
    result = run_v2_production_pipeline(
        product.production.CLAIM,
        db_path=path,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=True),
        discovery_providers=controls.discovery_providers,
        search_providers={provider: search for provider in controls.discovery_providers},
        wigolo_provider=product.phase12._Scraper(),
        llm_provider=model,
        routing_config=product.phase12._routing(),
        ceilings=product.production.CEILINGS,
        research_controls=controls,
        clock=lambda: NOW,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    selection = V2SourceSelectionQueueResult.model_validate_json(
        read_v2_artifact(
            path, result.run_id, "phase-13-source-selection-deep-analysis-queue-analyzer-admission"
        ).payload_json
    )
    cross_lane = tuple(
        source
        for source in selection.input.survivors
        if {item.direction for item in source.search_provenance}
        == {ResearchDirection.SUPPORT, ResearchDirection.CHALLENGE}
    )
    assert cross_lane
    gap_directions = {gap.gap_id: gap.direction for gap in selection.input.gap_history}
    for source in cross_lane:
        assert all(item.provenance_version == 2 for item in source.search_provenance)
        assert all(
            gap_directions[gap_id] is provenance.direction
            for provenance in source.search_provenance
            for gap_id in provenance.targeted_gap_ids
        )
    for status in selection.source_statuses:
        assert all(gap_directions[gap_id] is status.direction for gap_id in status.gap_ids)
    for request in model.requests:
        if request.requested_output_type.__name__ == "V2EvidenceAnalystModelOutput":
            assert all(
                gap_directions[gap_id] is request.input_artifact.direction
                for gap_id in request.input_artifact.targeted_gap_ids
            )
    # A claimed query direction cannot replace its own targeted Gap's direction.
    source = next(
        source
        for source in cross_lane
        if any(provenance.targeted_gap_ids for provenance in source.search_provenance)
    )
    provenance = next(item for item in source.search_provenance if item.targeted_gap_ids)
    opposite = (
        ResearchDirection.CHALLENGE
        if provenance.direction is ResearchDirection.SUPPORT
        else ResearchDirection.SUPPORT
    )
    forged = source.model_copy(
        update={
            "search_provenance": tuple(
                item.model_copy(update={"direction": opposite}) if item == provenance else item
                for item in source.search_provenance
            )
        }
    )
    with pytest.raises(ValidationError, match="query direction"):
        V2SourceSelectionInput.model_validate(
            {
                **selection.input.model_dump(),
                "survivors": tuple(
                    forged if item.source_id == source.source_id else item
                    for item in selection.input.survivors
                ),
            }
        )


def test_legacy_query_provenance_serialization_has_no_invented_direction() -> None:
    original = {
        "query_id": str(RUN),
        "provider": "openalex",
        "round_number": 1,
        "query_text": "generated historical query",
        "targeted_gap_ids": [],
    }
    legacy = V2SourceSelectionSearchProvenance.model_validate(original)
    assert legacy.model_dump(mode="json") == original
    with pytest.raises(ValidationError, match="original direction"):
        V2SourceSelectionSearchProvenance.model_validate({**original, "provenance_version": 2})


@pytest.mark.parametrize(
    "authors",
    [
        (", ".join(f"Generated Researcher {index:02}" for index in range(20)),),
        ("A" * 241,),
    ],
)
def test_long_optional_authors_do_not_discard_owned_seed_or_change_original_metadata(
    tmp_path: Path, authors: tuple[str, ...]
) -> None:
    path = tmp_path / "generated.sqlite3"
    _binding(path)
    _install_round_one(path, ({"score": 85, "authors": authors},))
    saved = read_v2_artifact(path, RUN, "phase-4-discovery-scout")
    item = V2DiscoveryScoutOutput.model_validate_json(saved.payload_json).items[0]
    identity = pipeline_work_identity(item)
    assert identity.authors is None
    assert identity.title == item.title and identity.doi == item.doi
    seeds = select_seeds(str(path), RUN, 1, _clock)
    assert len(seeds.seeds) == 1 and seeds.seeds[0].work == identity
    assert read_v2_artifact(path, RUN, "phase-4-discovery-scout") == saved
    assert item.authors == authors


def test_representable_author_names_remain_exact_and_are_not_truncated(tmp_path: Path) -> None:
    path = tmp_path / "generated.sqlite3"
    _binding(path)
    authors = ("Surname, Given", "A" * 240)
    _install_round_one(path, ({"score": 85, "authors": authors},))
    item = V2DiscoveryScoutOutput.model_validate_json(
        read_v2_artifact(path, RUN, "phase-4-discovery-scout").payload_json
    ).items[0]
    assert pipeline_work_identity(item).authors == authors


class LongAuthorSearch(product.phase12._Search):
    def search(self, request: product.phase12.SearchRequest) -> product.phase12.SearchResponse:
        response = super().search(request)
        return response.model_copy(
            update={
                "results": [
                    item.model_copy(
                        update={
                            "metadata": item.metadata.model_copy(
                                update={
                                    "doi": "10.1234/generated-course-study",
                                    "published_at": "2023-01-01",
                                    "work_type": "article",
                                    "author": (
                                        ", ".join(
                                            f"Generated Researcher {index:02}"
                                            for index in range(20)
                                        )
                                        if request.provider is DiscoveryProvider.ARXIV
                                        else None
                                    ),
                                }
                            )
                        }
                    )
                    for item in response.results
                ]
            }
        )


class NeighborhoodModel(product.production._ConceptModel):
    def generate(self, request: LLMRequest) -> object:
        if request.requested_output_type is V2NeighborhoodSearchOutput:
            self.requests.append(request)
            self.search_agent_calls += 1
            round_number = request.input_artifact.request.round_number
            return V2NeighborhoodSearchOutput.model_validate(
                {
                    "searches": tuple(
                        {
                            "lane_index": index,
                            "concepts": {
                                "required_concepts": (
                                    {
                                        "concept": (
                                            "independent replication course completion round "
                                            f"{round_number} lane {index}"
                                        ),
                                        "aliases": ("replication study",),
                                    },
                                ),
                                "purpose": "gap",
                            },
                        }
                        for index, _lane in enumerate(request.input_artifact.lanes)
                    )
                }
            )
        return super().generate(request)


def test_long_arxiv_author_display_does_not_stop_follow_up_planning(tmp_path: Path) -> None:
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.OPENALEX, DiscoveryProvider.ARXIV)
    )
    search = LongAuthorSearch(unique_results=True)
    result = run_v2_production_pipeline(
        product.production.CLAIM,
        db_path=tmp_path / "generated.sqlite3",
        directions=product.production.DIRECTIONS,
        discovery_providers=controls.discovery_providers,
        search_providers={provider: search for provider in controls.discovery_providers},
        wigolo_provider=product.phase12._Scraper(),
        llm_provider=NeighborhoodModel(completed_rounds=4),
        routing_config=product.phase12._routing(),
        ceilings=product.production.CEILINGS,
        research_controls=controls,
        clock=lambda: NOW,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert {
        request.compiled_query.conceptual_query.round_number for request in search.requests
    } == {1, 2, 3, 4}
