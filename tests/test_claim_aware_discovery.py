"""Exercise claim triage through offline production discovery, capture and release."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar
from uuid import UUID

import pytest
import test_query_production as production
import test_v2_phase12_production as phase12

from researchassistant.agents.evidence_checkpoint import CHECKPOINT_KEY, V2EvidenceCheckpoint
from researchassistant.agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY
from researchassistant.agents.v2_discovery import V2_SCOUT_ARTIFACT_KEY, cluster_discovery_items
from researchassistant.agents.v2_evidence_admission import V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
from researchassistant.agents.v2_final_output import render_v2_final_output
from researchassistant.api.application_services.live_sources import read_live_sources
from researchassistant.contracts.acquisition_ranking import V2AcquisitionRankingAudit
from researchassistant.contracts.artifact_keys import discovery_round_keys
from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ScoutBatch,
    ScoutItem,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2EvidenceAdmissionBatchResult,
)
from researchassistant.contracts.paper_identity import V2PaperIdentityAudit
from researchassistant.contracts.research_discovery import V2ClaimScoutRequest
from researchassistant.contracts.search import SearchDiscoveryMetadata, SearchResult
from researchassistant.research.v2_orchestrator import (
    V2ProductionPipelineResult,
    V2ProductionState,
    run_v2_production_pipeline,
)
from researchassistant.storage.store import read_v2_artifact

STUDY = "https://journal.example.org/a-study"
MIRROR = "https://archive.example.org/a-mirror"
LATER_MIRROR = "https://other-archive.example.org/a-mirror"
FULL_TEXT = "https://archive.example.org/full/a-mirror"
COUNTER = "https://journal.example.org/b-null"
GAP = "https://journal.example.org/c-follow-up"
PUBLIC_REPORT = "https://agency.example.gov/completion"
INCOMPLETE = "https://college.example.org/outcomes"
OPINION = "https://news.example.org/opinion"
SPECULATIVE = "https://news.example.org/speculation"
STUDY_TITLE = "Regional program and course completion"
STUDY_DESIGN = (
    "A controlled trial measured regional program course completion against standard materials. "
)
NULL_QUOTE = phase12.QUOTE.replace("48 percent", "62 percent")
FULLER_QUOTE = (
    "Across the full study period, 68 percent of adults in the regional program completed "
    "the course compared with 49 percent of matched adults receiving standard materials."
)
Artifact = TypeVar("Artifact", bound=StrictModel)


class _EvidenceSearch(phase12._Search):
    def __init__(self, *, truncated_first: bool = False, unique_results: bool = False) -> None:
        super().__init__(unique_results=unique_results)
        self.truncated_first = truncated_first

    def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
        round_number = request.compiled_query.conceptual_query.round_number
        if round_number > 1:
            response = super().search(request)
            mirror = SearchResult(
                original_url=LATER_MIRROR,
                title=STUDY_TITLE,
                rank=2,
                metadata=SearchDiscoveryMetadata(doi="10.5000/a-study"),
            )
            results = [*response.results, mirror]
            if self.truncated_first:
                results.append(mirror.model_copy(update={"original_url": FULL_TEXT, "rank": 3}))
            return response.model_copy(update={"results": results})
        self.requests.append(request)
        rows = (
            (OPINION, "Opinion: " + production.CLAIM, production.CLAIM, "opinion", None, None),
            (SPECULATIVE, "Speculation on enrollment", "Blog commentary.", "blog", None, None),
            (INCOMPLETE, "Regional program course completion tables", None, None, None, None),
            (
                PUBLIC_REPORT,
                "County education office primary report",
                "Official statistics on regional program course completion by participant group.",
                "report",
                None,
                None,
            ),
            (
                COUNTER,
                STUDY_TITLE,
                STUDY_DESIGN + "The groups had the same completion rate.",
                "article",
                "10.5000/b-null",
                None,
            ),
            (
                GAP,
                "Completion in rural regional program cohorts",
                "We analyzed regional program course completion among rural adults. "
                "The comparison group is not described in the abstract.",
                "article",
                "10.5000/c-follow-up",
                None,
            ),
            (
                STUDY,
                STUDY_TITLE,
                STUDY_DESIGN + "The groups had different completion rates.",
                "primary study" if self.truncated_first else "article",
                "10.5000/a-study",
                None,
            ),
            (MIRROR, STUDY_TITLE, None, "article", "10.5000/a-study", FULL_TEXT),
        )
        if self.truncated_first:
            rows += ((LATER_MIRROR, STUDY_TITLE, None, "article", "10.5000/a-study", None),)
        return phase12.SearchResponse(
            provider_name="offline-evidence-fixture",
            results=[
                SearchResult(
                    original_url=url,
                    title=title,
                    rank=rank,
                    metadata=SearchDiscoveryMetadata(
                        abstract=abstract, work_type=kind, doi=doi, full_text_url=full_text
                    ),
                )
                for rank, (url, title, abstract, kind, doi, full_text) in enumerate(rows, 1)
            ],
        )


class _EvidenceScout(production._ConceptModel):
    def generate(self, request: phase12.LLMRequest) -> object:
        if request.requested_output_type is not ScoutBatch:
            output = super().generate(request)
            if (
                isinstance(output, phase12.V2VerbatimQuoteSelection)
                and FULLER_QUOTE in request.input_artifact.untrusted_source_text
            ):
                return phase12.V2VerbatimQuoteSelection(
                    selected_sentence_ranges=(
                        phase12.SelectedSentenceRange(start_sentence=5, end_sentence=5),
                    )
                )
            if (
                isinstance(output, phase12.V2EvidenceAnalystModelOutput)
                and request.input_artifact.candidate.source_url == LATER_MIRROR
            ):
                statement = "Across the full study period, completion was 68% versus 49%."
                return output.model_copy(
                    update={
                        "narrowest_supported_proposition": statement,
                        "canonical_factual_statement": statement,
                    }
                )
            if (
                isinstance(output, phase12.V2EvidenceAnalystModelOutput)
                and request.input_artifact.candidate.source_url == COUNTER
            ):
                statement = "Both groups in the regional evaluation reported 62% completion."
                return output.model_copy(
                    update={
                        "relationship_to_claim": phase12.V2EvidenceRelationship.CHALLENGES,
                        "narrowest_supported_proposition": statement,
                        "canonical_factual_statement": statement,
                    }
                )
            return output
        self.requests.append(request)
        artifact = request.input_artifact
        assert isinstance(artifact, V2ClaimScoutRequest)
        assert artifact.exact_claim == production.CLAIM
        assert "A missing abstract is uncertainty" in request.rendered_prompt
        assert request.prompt.version == "researchassistant-v2-phase-3-ranked-scout-v3"
        decisions = {
            OPINION: ("skip", "Opinion with no original observations."),
            SPECULATIVE: ("maybe", "Material gap: An unsupported fixture priority tag."),
            INCOMPLETE: ("maybe", "A relevant title with no comparator or methods metadata."),
            COUNTER: ("retrieve", "Counterevidence: The controlled comparison reports a null."),
            GAP: ("maybe", "Material gap: Adds rural completion data with unclear comparison."),
        }
        return ScoutBatch(
            run_id=request.run_id,
            items=tuple(
                ScoutItem(
                    item_id=item.item_id,
                    decision=decisions.get(item.source_url, ("retrieve", "Direct measurement."))[0],
                    rationale=decisions.get(item.source_url, ("retrieve", "Direct measurement."))[
                        1
                    ],
                )
                for item in artifact.candidates
            ),
        )


class _EvidenceScraper(phase12._Scraper):
    def __init__(self, *, truncated_first: bool = False) -> None:
        super().__init__()
        self.truncated_first = truncated_first

    def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
        response = super().scrape(request)
        if request.url in {FULL_TEXT, GAP, LATER_MIRROR}:
            text = phase12.SOURCE_TEXT + " We used data from trial NCT01234567."
            if request.url == LATER_MIRROR:
                text += f" {FULLER_QUOTE}"
            return response.model_copy(
                update={
                    "text": text,
                    "truncated": request.url == FULL_TEXT and self.truncated_first,
                }
            )
        if request.url == COUNTER:
            return response.model_copy(
                update={"text": phase12.SOURCE_TEXT.replace(phase12.QUOTE, NULL_QUOTE)}
            )
        return response


@pytest.mark.slow
@pytest.mark.parametrize("truncated_first", (False, True), ids=("adequate", "recover-fuller"))
def test_claim_scout_controls_capture_and_preserves_shared_data_publications(
    tmp_path: Path,
    truncated_first: bool,
) -> None:
    path = tmp_path / "evidence-scout.sqlite"
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA,),
        sources_per_stance_per_round=5,
        seed_expansion_enabled=False,
    )

    def run(
        model: _EvidenceScout,
        search: _EvidenceSearch,
        scraper: _EvidenceScraper,
        run_id: UUID | None = None,
    ) -> V2ProductionPipelineResult:
        return run_v2_production_pipeline(
            production.CLAIM,
            db_path=path,
            directions=production.DIRECTIONS,
            discovery_providers=controls.discovery_providers,
            search_providers={DiscoveryProvider.EXA: search},
            wigolo_provider=scraper,
            llm_provider=model,
            routing_config=phase12._routing(),
            ceilings=production.CEILINGS,
            research_controls=controls,
            run_id=run_id,
            clock=lambda: phase12.NOW,
        )

    model = _EvidenceScout(completed_rounds=4)
    search = _EvidenceSearch(truncated_first=truncated_first, unique_results=True)
    scraper = _EvidenceScraper(truncated_first=truncated_first)
    result = run(model, search, scraper)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason

    def load(contract: type[Artifact], key: str) -> Artifact:
        return contract.model_validate_json(read_v2_artifact(path, result.run_id, key).payload_json)

    discovery = load(V2DiscoveryScoutOutput, V2_SCOUT_ARTIFACT_KEY)
    ranking = load(V2MetadataRankingArtifact, "phase-3-metadata-ranking-round-1")
    acquisition = load(V2AcquisitionProbeOutput, V2_ACQUISITION_PROBE_ARTIFACT_KEY)
    admission = load(V2EvidenceAdmissionBatchResult, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY)
    by_id = {item.item_id: item.source_url for item in discovery.items}
    decisions = {
        by_id[item.item_id]: item.decision.value
        for batch in discovery.scout_batches
        for item in batch.items
    }
    assert decisions[STUDY] == decisions[COUNTER] == decisions[PUBLIC_REPORT] == "retrieve"
    assert decisions[GAP] == decisions[INCOMPLETE] == "maybe"
    assert decisions[OPINION] == "skip"
    assert MIRROR not in decisions
    ordered_urls = [by_id[rank.item_id] for rank in ranking.ranks]
    assert ordered_urls.index(STUDY) < ordered_urls.index(OPINION)
    assert ordered_urls.index(COUNTER) < ordered_urls.index(OPINION)
    mirror_cluster = next(
        cluster for cluster in discovery.clusters if FULL_TEXT in cluster.alternate_urls
    )
    expected_mirrors = {STUDY, MIRROR}
    if truncated_first:
        expected_mirrors.add(LATER_MIRROR)
    assert {by_id[item] for item in mirror_cluster.item_ids} == expected_mirrors
    assert {item.original_url for item in mirror_cluster.metadata_provenance} == expected_mirrors
    assert {request.url for request in scraper.requests[:5]} == {
        FULL_TEXT,
        COUNTER,
        GAP,
        PUBLIC_REPORT,
        INCOMPLETE,
    }
    assert [item.snapshot.source_url for item in acquisition.acquisitions] == [
        FULL_TEXT,
        COUNTER,
        GAP,
        PUBLIC_REPORT,
        INCOMPLETE,
    ]
    assert COUNTER not in {by_id[item] for item in mirror_cluster.item_ids}
    later_discovery = load(V2DiscoveryScoutOutput, discovery_round_keys(2)[0])
    later_cluster = next(
        cluster
        for cluster in later_discovery.clusters
        if LATER_MIRROR in (cluster.preferred_url, *cluster.alternate_urls)
    )
    later_audit = load(V2AcquisitionRankingAudit, "metadata-acquisition-v2-round-2")
    assert any(
        decision.item_id in later_cluster.item_ids and decision.decision.value == "retrieve"
        for batch in later_discovery.scout_batches
        for decision in batch.items
    )
    assert any(
        row.cluster_id == later_cluster.cluster_id
        and row.disposition == ("usable" if truncated_first else "excluded_prior")
        for row in later_audit.dispositions
    )
    capture_urls = [request.url for request in scraper.requests]
    assert capture_urls.count(LATER_MIRROR) == int(truncated_first)
    assert capture_urls.count(FULL_TEXT) == 1
    locations = {STUDY, MIRROR, LATER_MIRROR, FULL_TEXT}
    (study_card,) = (
        card
        for card in read_live_sources(path, result.run_id, offset=0).items
        if card.url in locations or card.readable_url in locations
    )
    assert study_card.first_round == 1
    assert study_card.state == "admitted"
    assert study_card.readable_url == (LATER_MIRROR if truncated_first else FULL_TEXT)
    data_records = [
        row
        for row in admission.source_results
        if row.provenance.source_family_id == "shared-data:NCT01234567"
    ]
    assert len(data_records) == 2 and all(row.evidence_record for row in data_records)
    output = result.final_output
    assert output is not None and output.release_validation.valid
    rendered = render_v2_final_output(output)
    assert "one data source" in rendered
    assert "remains unresolved" in rendered
    assert output.post_analysis_assessment.challenging_count == 1
    later_acquisition = load(V2AcquisitionProbeOutput, discovery_round_keys(2)[1])
    snapshots = {
        item.snapshot.snapshot_id: item.snapshot
        for item in (*acquisition.acquisitions, *later_acquisition.acquisitions)
    }
    if truncated_first:
        original = next(
            item for item in acquisition.acquisitions if item.snapshot.source_url == FULL_TEXT
        )
        recovered = next(
            item
            for item in later_acquisition.acquisitions
            if item.snapshot.source_url == LATER_MIRROR
        )
        assert original.snapshot.truncated and not recovered.snapshot.truncated
        assert recovered.snapshot.word_count > original.snapshot.word_count
        checkpoint = load(V2EvidenceCheckpoint, CHECKPOINT_KEY)
        wave = next(wave for wave in checkpoint.waves if wave.source_id == original.cluster_id)
        early_candidate = wave.extraction.sources[0].candidate
        assert (
            early_candidate is not None
            and early_candidate.snapshot_id == original.snapshot.snapshot_id
            and early_candidate.snapshot_sha256 == original.snapshot.snapshot_sha256
        )
        (early_offset,) = early_candidate.segment_offsets
        assert (
            original.snapshot.normalized_text[early_offset.start_char : early_offset.end_char]
            == phase12.QUOTE
        )
        assert wave.analyst.source_results[0].assessment is not None
        gap_input = next(
            request.input_artifact
            for request in model.requests
            if request.requested_output_type is phase12.V2GapAnalysisModelOutput
            and request.input_artifact.completed_round == 2
        )
        visible = {item.source_cluster_id for item in gap_input.surviving_sources}
        assert recovered.cluster_id in visible and original.cluster_id not in visible
        assert all(row.source_id != original.cluster_id for row in admission.source_results)
        assert sum(row.source_id == recovered.cluster_id for row in data_records) == 1
        assert "68% versus 49%" in rendered
        audit = load(V2PaperIdentityAudit, "retained-paper-identity-v2")
        group = next(
            group for group in audit.groups if group.canonical_source_id == recovered.cluster_id
        )
        assert {row.snapshot_id: row.snapshot_hash for row in group.locations} == {
            original.snapshot.snapshot_id: original.snapshot.snapshot_sha256,
            recovered.snapshot.snapshot_id: recovered.snapshot.snapshot_sha256,
        }
    counter_record = next(
        row.evidence_record
        for row in admission.source_results
        if row.evidence_record and row.evidence_record.source_url == COUNTER
    )
    for record, quote in (
        (counter_record, NULL_QUOTE),
        *(
            (
                row.evidence_record,
                FULLER_QUOTE if row.evidence_record.source_url == LATER_MIRROR else phase12.QUOTE,
            )
            for row in data_records
        ),
    ):
        (offset,) = record.segment_offsets
        assert (
            snapshots[record.snapshot_id].normalized_text[offset.start_char : offset.end_char]
            == quote
        )
    assert {
        request.compiled_query.conceptual_query.round_number for request in search.requests
    } == {
        1,
        2,
        3,
        4,
    }
    assert any(
        request.input_artifact.target_gaps
        for request in model.requests
        if isinstance(request.input_artifact, V2ClaimScoutRequest)
    )
    replay_model = _EvidenceScout(completed_rounds=4)
    replay_search = _EvidenceSearch(truncated_first=truncated_first)
    replay_scraper = _EvidenceScraper(truncated_first=truncated_first)
    assert run(replay_model, replay_search, replay_scraper, result.run_id) == result
    assert not (replay_model.requests or replay_search.requests or replay_scraper.requests)


@pytest.mark.slow
def test_live_sources_keep_conflicting_cross_round_doi_titles_separate(tmp_path: Path) -> None:
    conflicting_title = "Distinct evening-student evaluation of course completion"
    untitled_url = "https://unknown.example.org/a-study"

    class ConflictingSearch(_EvidenceSearch):
        def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
            response = super().search(request)
            round_number = request.compiled_query.conceptual_query.round_number
            results = [
                row.model_copy(update={"title": conflicting_title})
                if row.original_url == LATER_MIRROR
                else row
                for row in response.results
                if round_number != 3 or row.original_url != LATER_MIRROR
            ]
            if round_number == 3:
                results.append(
                    SearchResult(
                        original_url=untitled_url,
                        rank=3,
                        metadata=SearchDiscoveryMetadata(doi="10.5000/a-study"),
                    )
                )
            return response.model_copy(update={"results": results})

    class UnavailableLocations(_EvidenceScraper):
        def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
            response = super().scrape(request)
            if request.url in {LATER_MIRROR, untitled_url}:
                return response.model_copy(update={"text": ""})
            return response

    path = tmp_path / "conflicting-live-sources.sqlite"
    result = production._run_fresh(
        path,
        model=_EvidenceScout(completed_rounds=4),
        search=ConflictingSearch(unique_results=True),
        scraper=UnavailableLocations(),
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason

    def saved_rank_key(round_number: int, url: str) -> str:
        key, _ = discovery_round_keys(round_number)
        discovery = V2DiscoveryScoutOutput.model_validate_json(
            read_v2_artifact(path, result.run_id, key).payload_json
        )
        ranking = V2MetadataRankingArtifact.model_validate_json(
            read_v2_artifact(
                path, result.run_id, f"phase-3-metadata-ranking-round-{round_number}"
            ).payload_json
        )
        item_id = next(item.item_id for item in discovery.items if item.source_url == url)
        return next(rank.work_key for rank in ranking.ranks if rank.item_id == item_id)

    assert (
        saved_rank_key(1, STUDY)
        == saved_rank_key(2, LATER_MIRROR)
        == saved_rank_key(3, untitled_url)
        == "doi:10.5000/a-study"
    )

    page = read_live_sources(path, result.run_id, offset=0)
    original = next(card for card in page.items if card.readable_url == FULL_TEXT)
    assert original.first_round == 1 and original.state == "admitted"
    conflicting = next((card for card in page.items if card.title == conflicting_title), None)
    assert conflicting is not None
    assert conflicting.work_id != original.work_id
    assert conflicting.first_round == 2
    assert conflicting.url == LATER_MIRROR
    assert conflicting.state == "screened" and conflicting.readable_url is None
    untitled = next(card for card in page.items if card.url == untitled_url)
    assert untitled.work_id not in {original.work_id, conflicting.work_id}
    assert untitled.readable_url is None


def test_title_and_authors_without_an_identifier_leave_relationship_unresolved() -> None:
    from test_metadata_ranking import _item

    same_title = "Regional program and course completion"
    first = _item(0, title=same_title).model_copy(update={"authors": ("A. Author",)})
    second = _item(1, title=same_title).model_copy(update={"authors": ("A. Author",)})
    clusters = cluster_discovery_items((first, second), require_identity=True)
    assert len(clusters) == 2
