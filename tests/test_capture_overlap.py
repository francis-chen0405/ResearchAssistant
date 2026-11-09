"""Offline timing gates at the production pipeline boundary."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from time import monotonic, sleep
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import test_query_production as production
import test_v2_phase12_production as phase12
from test_acquisition_usable_fallback import ABSTRACT, _captures

from researchassistant.agents import (
    v2_acquisition,
    v2_adaptive_search,
    v2_deep_analysis,
    v2_discovery,
    v2_evidence_analyst,
    v2_stage_checkpoint,
)
from researchassistant.agents.capture_overlap import V2CaptureDispatch
from researchassistant.agents.evidence_checkpoint import CHECKPOINT_KEY, V2EvidenceCheckpoint
from researchassistant.agents.v2_discovery import V2_SCOUT_ARTIFACT_KEY
from researchassistant.agents.v2_gap_analysis import V2_GAP_ANALYSIS_ARTIFACT_KEY
from researchassistant.api.application_services.live_sources import read_live_sources
from researchassistant.api.discovery_diagnostics import enrich_discovery_diagnostics
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ScoutBatch,
    ScoutItem,
    V2AcquisitionProbeOutput,
    V2ClaimCoverageDimension,
    V2DiscoveryScoutOutput,
    V2GapAnalysisOutput,
)
from researchassistant.contracts.paper_identity import V2PaperIdentityAudit
from researchassistant.contracts.research_coverage import V2InitialPlannerClaimComponent
from researchassistant.contracts.search import SearchDiscoveryMetadata
from researchassistant.providers.acquisition import WigoloAcquisitionAdapter
from researchassistant.providers.config import WigoloConfig
from researchassistant.providers.llm import LLMStage
from researchassistant.providers.scraper import ScraperProvider, ScraperProviderError
from researchassistant.research.v2_orchestrator import (
    V2ProductionPipelineResult,
    V2ProductionState,
    run_v2_production_pipeline,
)
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.query_retrieval_store import read_pages
from researchassistant.storage.store import ReadOnlyStore, read_v2_artifact

ACQUISITION = v2_acquisition.V2_ACQUISITION_PROBE_ARTIFACT_KEY


class _Works(phase12._Search):
    def __init__(self, size: int, *, shared_host: bool = False) -> None:
        super().__init__()
        self.size = size
        self.shared_host = shared_host

    def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
        self.requests.append(request)
        return phase12.SearchResponse(
            provider_name="offline-capture-overlap",
            results=[
                phase12.SearchResult(
                    original_url=(
                        f"https://study-{0 if self.shared_host else index}.example.org/{index}"
                    ),
                    title=f"Regional program and course completion in study {index:02}",
                    rank=index + 1,
                    metadata=SearchDiscoveryMetadata(
                        abstract=(
                            "A controlled trial measured regional program course completion "
                            "against standard materials. The groups had different completion rates."
                        ),
                        work_type="article",
                    ),
                )
                for index in range(self.size)
            ],
        )


def _run(
    path: Path,
    run_id: UUID,
    model: production._ConceptModel,
    search: _Works,
    scraper: ScraperProvider,
    *,
    capture_slots: int = 3,
    cancel: Callable[[], bool] | None = None,
    target: int = 7,
) -> V2ProductionPipelineResult:
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA,),
        metadata_depth=50,
        seed_expansion_enabled=False,
        sources_per_stance_per_round=target,
    )
    return run_v2_production_pipeline(
        production.CLAIM,
        db_path=path,
        run_id=run_id,
        directions=production.DIRECTIONS,
        discovery_providers=controls.discovery_providers,
        search_providers={DiscoveryProvider.EXA: search},
        wigolo_provider=scraper,
        llm_provider=model,
        routing_config=phase12._routing(),
        ceilings=production.CEILINGS,
        research_controls=controls,
        capture_slots=capture_slots,
        cancellation_requested=cancel,
        clock=lambda: datetime.now(UTC),
    )


def _wait(predicate: Callable[[], bool]) -> None:
    deadline = monotonic() + 12
    while not predicate() and monotonic() < deadline:
        sleep(0.01)
    assert predicate(), "fixture milestone did not arrive"


class _GatedScraper(phase12._Scraper):
    def __init__(self) -> None:
        super().__init__()
        self.lock = Lock()
        self.pending: dict[str, Event] = {}
        self.finished: list[str] = []
        self.max_active = 0
        self.release_all = Event()

    def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
        release = Event()
        with self.lock:
            assert request.url not in self.pending
            self.pending[request.url] = release
            self.max_active = max(self.max_active, len(self.pending))
        try:
            _wait(lambda: release.is_set() or self.release_all.is_set())
            return super().scrape(request)
        finally:
            with self.lock:
                self.finished.append(request.url)
                del self.pending[request.url]


class _OverlapModel(production._ConceptModel):
    def __init__(self, scraper: _GatedScraper) -> None:
        super().__init__()
        self.scraper = scraper
        self.second_scout = Event()
        self.release_scout = Event()
        self.release_analysis = Event()
        self.first_analysis = Event()
        self.lock = Lock()
        self.early_active: set[UUID] = set()
        self.extracted: set[UUID] = set()
        self.max_early_active = 0
        self.first_snapshot_url: str | None = None
        self.late_specialists: tuple[str, ...] = ()
        self.gap = Event()

    def generate(self, request: phase12.LLMRequest) -> object:
        if request.stage is LLMStage.SCOUT and request.input_artifact.batch_number == 2:
            self.second_scout.set()
            assert self.release_scout.wait(12), "second Scout was never released"
            self.requests.append(request)
            candidates = request.input_artifact.candidates
            self.late_specialists = tuple(item.source_url for item in candidates[:2])
            return ScoutBatch(
                run_id=request.run_id,
                items=tuple(
                    ScoutItem(
                        item_id=item.item_id,
                        decision="maybe" if i == 1 else "retrieve",
                        rationale=(
                            "Counterevidence: The comparison found no improvement."
                            if i == 0
                            else "Material gap: Provides a relevant rural comparison."
                            if i == 1
                            else "A direct primary comparison."
                        ),
                    )
                    for i, item in enumerate(candidates)
                ),
            )
        if request.stage is LLMStage.EXTRACTOR and not self.gap.is_set():
            with self.lock:
                if not self.first_analysis.is_set():
                    self.first_snapshot_url = next(
                        capture.source.snapshot.source_url
                        for capture in _captures(self.path, request.run_id)
                        if capture.source
                        and capture.source.snapshot.snapshot_id
                        == request.input_artifact.snapshot_id
                    )
                    assert self.scraper.pending, "capture already drained before extraction"
                    self.first_analysis.set()
                assert request.source_id not in self.early_active
                self.early_active.add(request.source_id)
                self.max_early_active = max(self.max_early_active, len(self.early_active))
            assert self.release_analysis.wait(12), "extractor was never released"
            output = super().generate(request)
            with self.lock:
                self.extracted.add(request.source_id)
            return output
        if request.stage is LLMStage.ANALYST and not self.gap.is_set():
            with self.lock:
                assert request.source_id in self.extracted
                self.early_active.remove(request.source_id)
        if request.stage is LLMStage.GAP_ANALYSIS:
            assert not self.early_active
            if self.scraper.pending:
                assert request.input_artifact.outstanding_capture_source_ids
            self.gap.set()
        return super().generate(request)


@pytest.mark.parametrize("slots", (3, 5))
def test_capture_and_early_workers_overlap_without_using_download_order(
    tmp_path: Path,
    slots: int,
) -> None:
    path = tmp_path / "overlap.sqlite"
    run_id = uuid4()
    scraper = _GatedScraper()
    model = _OverlapModel(scraper)
    model.path = path
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(_run, path, run_id, model, _Works(25), scraper, capture_slots=slots)
        try:
            assert model.second_scout.wait(12)
            _wait(lambda: len(scraper.pending) == slots)
            lead = V2CaptureDispatch.model_validate_json(
                read_v2_artifact(path, run_id, f"{ACQUISITION}/overlap-v1/dispatch-1").payload_json
            ).urls[0]
            with scraper.lock:
                faster = next(url for url in scraper.pending if url != lead)
                scraper.pending[faster].set()
            _wait(lambda: faster in scraper.finished)
            assert not model.first_analysis.is_set()
            with scraper.lock:
                scraper.pending[lead].set()
            assert model.first_analysis.wait(12)
            assert model.first_snapshot_url == lead
            assert not model.gap.is_set()
            model.release_scout.set()
            scraper.release_all.set()
            _wait(lambda: model.max_early_active == 3)
            assert not model.gap.is_set()
        finally:
            model.release_scout.set()
            scraper.release_all.set()
            model.release_analysis.set()
        result = running.result(timeout=20)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output.release_validation.valid
    assert scraper.max_active == slots and model.max_early_active == 3
    assert len(scraper.requests) == 7
    checkpoint = V2EvidenceCheckpoint.model_validate_json(
        read_v2_artifact(path, run_id, CHECKPOINT_KEY).payload_json
    )
    assert len(checkpoint.waves) == len(checkpoint.findings) == 4
    urls = [wave.extraction.sources[0].candidate.source_url for wave in checkpoint.waves]
    assert urls[0] == lead
    assert set(model.late_specialists) <= set(urls)
    gaps = [request for request in model.requests if request.stage is LLMStage.GAP_ANALYSIS]
    assert len(gaps) == 1
    assert gaps[0].input_artifact.assessed_source_findings == checkpoint.findings
    for wave in checkpoint.waves:
        candidate = wave.extraction.sources[0].candidate
        snapshot = wave.analyst.input.queued_candidates[0].snapshot
        assert candidate.snapshot_id == snapshot.snapshot_id
        assert candidate.snapshot_sha256 == snapshot.snapshot_sha256
        assert phase12.QUOTE in snapshot.normalized_text
    captures = _captures(path, run_id)
    assert len(captures) == 7
    assert all(c.start.started_at < c.finished_at and c.latency_ms > 0 for c in captures)


def test_verified_html_reuse_and_bounded_browser_fallback(tmp_path: Path) -> None:
    path = tmp_path / "html.sqlite"
    run_id = uuid4()
    renders = 0
    max_renders = 0
    render_started = Event()
    release_render = Event()
    static_read = Event()
    lock = Lock()
    reads: list[str] = []
    wigolo_calls: list[tuple[str, str]] = []

    def source(request: httpx.Request) -> httpx.Response:
        index = request.url.path
        reads.append(index)
        if index == "/3":
            static_read.set()
        markup = (
            f"<main><article><p>{phase12.SOURCE_TEXT}</p></article></main>"
            if index == "/3"
            else "<html><p>JavaScript required</p>"
            f"<div hidden><div>{phase12.SOURCE_TEXT}</div></div></html>"
        )
        if index == "/0":
            heading, text = ABSTRACT.split("\n", 1)
            markup = f"<main><article><h2>{heading}</h2><p>{text}</p></article></main>"
        return httpx.Response(200, text=markup, headers={"content-type": "text/html"})

    def wigolo(request: httpx.Request) -> httpx.Response:
        nonlocal renders, max_renders
        if request.url.path == "/ra/network-policy":
            return httpx.Response(200, json={"identity": "ra-public-network-v1"})
        payload = json.loads(request.content)
        wigolo_calls.append((payload["url"], payload["render_js"]))
        if payload["render_js"] == "never":
            return httpx.Response(200, json={"status": "javascript_required"})
        with lock:
            renders += 1
            max_renders = max(max_renders, renders)
        try:
            render_started.set()
            assert release_render.wait(12)
            return httpx.Response(200, json={"status": "ok", "markdown": phase12.SOURCE_TEXT})
        finally:
            with lock:
                renders -= 1

    with (
        httpx.Client(transport=httpx.MockTransport(source)) as origin,
        httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(wigolo)) as service,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        scraper = WigoloAcquisitionAdapter(
            WigoloConfig(),
            source_client=origin,
            wigolo_client=service,
            host_resolver=lambda _host: ("93.184.216.34",),
        )
        running = pool.submit(
            _run,
            path,
            run_id,
            production._ConceptModel(),
            _Works(4),
            scraper,
        )
        try:
            assert render_started.wait(12)
            assert static_read.wait(12), "waiting browsers occupied every capture slot"
        finally:
            release_render.set()
        result = running.result(timeout=20)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert Counter(reads) == {"/0": 1, "/1": 1, "/2": 1, "/3": 1}
    assert len(wigolo_calls) == 6 and max_renders == 1
    assert all(not url.endswith("/3") for url, _method in wigolo_calls)
    static = next(c for c in _captures(path, run_id) if c.start.url.endswith("/3"))
    assert static.response.media_type_provenance.verified_source_url == static.start.url
    assert static.response.text == phase12.SOURCE_TEXT
    assert static.response.rendered is False


@pytest.mark.parametrize("boundary", ("capture", "extractor", "analyst"))
def test_known_partial_results_resume_without_repeating_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    path = tmp_path / "resume.sqlite"
    run_id = uuid4()
    model, search, scraper = production._ConceptModel(), _Works(1), phase12._Scraper()
    if boundary == "capture":
        owner, name = v2_acquisition, "insert_v2_artifact"
    elif boundary == "extractor":
        owner, name = v2_stage_checkpoint, "insert_v2_artifact"
    else:
        owner, name = v2_evidence_analyst, "finish_model_route_attempt"

    def matches(args: tuple[Any, ...]) -> bool:
        if boundary == "analyst":
            return args[1].status.value == "completed"
        key = str(args[1])
        if boundary == "extractor":
            return key.startswith("phase-13-exact-extraction-") and key.endswith("/outcome")
        return key.endswith("/response")

    original = getattr(owner, name)

    def interrupt(*args: Any, **kwargs: Any) -> object:
        result = original(*args, **kwargs)
        if matches(args):
            raise KeyboardInterrupt("offline interruption after durable response")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(owner, name, interrupt)
        with pytest.raises(KeyboardInterrupt, match="offline interruption"):
            _run(path, run_id, model, search, scraper)
    result = _run(path, run_id, model, search, scraper)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert len(scraper.requests) == 1
    calls = Counter(request.stage for request in model.requests)
    assert all(
        calls[stage] == 1
        for stage in (
            LLMStage.SCOUT,
            LLMStage.EXTRACTOR,
            LLMStage.ANALYST,
            LLMStage.GAP_ANALYSIS,
        )
    )
    assert result.final_output.release_validation.valid


def test_cancellation_drains_active_capture_and_stops_new_work(tmp_path: Path) -> None:
    path = tmp_path / "cancel.sqlite"
    run_id = uuid4()
    model, search, scraper = (
        production._ConceptModel(),
        _Works(10, shared_host=True),
        _GatedScraper(),
    )
    cancel = Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(_run, path, run_id, model, search, scraper, cancel=cancel.is_set)
        try:
            _wait(lambda: len(scraper.pending) == 1)
            cancel.set()
        finally:
            scraper.release_all.set()
        result = running.result(timeout=20)
    assert result.state is V2ProductionState.CANCELLED
    assert scraper.max_active == len(scraper.requests) == 1
    assert not scraper.pending
    assert not any(r.stage in {LLMStage.EXTRACTOR, LLMStage.GAP_ANALYSIS} for r in model.requests)


def test_failed_capture_leaves_room_for_later_eligible_work(tmp_path: Path) -> None:
    class _FailOnce(phase12._Scraper):
        def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
            result = super().scrape(request)
            if request.url.endswith("/0"):
                raise ScraperProviderError("connection_failure", "offline failure")
            return result

    path = tmp_path / "failure.sqlite"
    run_id = uuid4()
    scraper = _FailOnce()
    result = _run(path, run_id, production._ConceptModel(), _Works(10), scraper, target=5)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    acquired = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(path, run_id, ACQUISITION).payload_json
    )
    assert len(scraper.requests) == 6 and len(acquired.survivors) == 5
    assert sum(not attempt.succeeded for attempt in acquired.attempts) == 1


@pytest.mark.parametrize("boundary", ("capture", "extractor", "analyst"))
def test_unknown_outcome_remains_consumed_while_other_sources_can_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    path = tmp_path / "unknown.sqlite"
    run_id = uuid4()
    model, search, scraper = production._ConceptModel(), _Works(4), phase12._Scraper()
    if boundary == "capture":
        owner, name = v2_acquisition, "insert_v2_artifact"
    elif boundary == "extractor":
        owner, name = v2_stage_checkpoint, "insert_v2_artifact"
    else:
        owner, name = v2_evidence_analyst, "finish_model_route_attempt"
    original = getattr(owner, name)
    crashed = Event()
    guard = Lock()

    def interrupt(*args: Any, **kwargs: Any) -> object:
        if boundary == "analyst":
            matches = args[1].status.value == "completed"
        else:
            key = str(args[1])
            matches = (
                key.endswith("/response")
                if boundary == "capture"
                else key.startswith("phase-13-exact-extraction-") and key.endswith("/outcome")
            )
        with guard:
            if matches and not crashed.is_set():
                crashed.set()
                raise KeyboardInterrupt("offline interruption before durable response")
        return original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(owner, name, interrupt)
        with pytest.raises(KeyboardInterrupt, match="offline interruption"):
            _run(path, run_id, model, search, scraper, capture_slots=1)
    result = _run(path, run_id, model, search, scraper)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert len(scraper.requests) == len({request.url for request in scraper.requests}) == 4
    stages = {LLMStage.EXTRACTOR, LLMStage.ANALYST}
    calls = Counter(
        (request.stage, request.source_id) for request in model.requests if request.stage in stages
    )
    assert max(calls.values()) == 1
    if boundary == "capture":
        acquisition = V2AcquisitionProbeOutput.model_validate_json(
            read_v2_artifact(path, run_id, ACQUISITION).payload_json
        )
        assert len(acquisition.survivors) == 3
        assert sum(a.failure_code == "unknown_outcome" for a in acquisition.attempts) == 1
    else:
        checkpoint = V2EvidenceCheckpoint.model_validate_json(
            read_v2_artifact(path, run_id, CHECKPOINT_KEY).payload_json
        )
        assert sum("unknown outcome" in (f.failure or "") for f in checkpoint.findings) == 1


def test_cancellation_drains_extraction_before_analyst(tmp_path: Path) -> None:
    class _PauseExtraction(production._ConceptModel):
        def generate(self, request: phase12.LLMRequest) -> object:
            if request.stage is LLMStage.EXTRACTOR:
                entered.set()
                assert release.wait(12)
            return super().generate(request)

    entered, release, cancel = Event(), Event(), Event()
    model = _PauseExtraction()
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(
            _run,
            tmp_path / "cancel-extractor.sqlite",
            uuid4(),
            model,
            _Works(1),
            phase12._Scraper(),
            cancel=cancel.is_set,
        )
        try:
            assert entered.wait(12)
            cancel.set()
            assert not running.done()
        finally:
            release.set()
        result = running.result(timeout=20)
    assert result.state is V2ProductionState.CANCELLED
    assert [r.stage for r in model.requests if r.stage is LLMStage.EXTRACTOR] == [
        LLMStage.EXTRACTOR
    ]
    assert not any(r.stage in {LLMStage.ANALYST, LLMStage.GAP_ANALYSIS} for r in model.requests)


def test_ready_source_inside_ranked_frontier_does_not_wait_for_slower_lead(
    tmp_path: Path,
) -> None:
    path = tmp_path / "frontier.sqlite"
    run_id = uuid4()
    scraper = _GatedScraper()
    model = _OverlapModel(scraper)
    model.path = path
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(_run, path, run_id, model, _Works(5), scraper)
        try:
            _wait(lambda: len(scraper.pending) == 3)
            lead, second = (
                V2CaptureDispatch.model_validate_json(
                    read_v2_artifact(
                        path, run_id, f"{ACQUISITION}/overlap-v1/dispatch-{index}"
                    ).payload_json
                ).urls[0]
                for index in (1, 2)
            )
            with scraper.lock:
                scraper.pending[second].set()
            assert model.first_analysis.wait(12)
            assert model.first_snapshot_url == second
            assert lead in scraper.pending
        finally:
            scraper.release_all.set()
            model.release_analysis.set()
        result = running.result(timeout=20)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    checkpoint = V2EvidenceCheckpoint.model_validate_json(
        read_v2_artifact(path, run_id, CHECKPOINT_KEY).payload_json
    )
    assert [wave.extraction.sources[0].candidate.source_url for wave in checkpoint.waves][:2] == [
        lead,
        second,
    ]


class _DeeperPageInterrupted(BaseException):
    pass


class _GatedPages(phase12._Search):
    ORIGINAL = "https://publication.example.org/report"
    MIRROR = "https://repository.example.org/report"
    DOI = "10.5000/round-one-report"

    def __init__(self, *, interrupt: bool = False) -> None:
        super().__init__()
        self.deep_page = Event()
        self.release_deep = Event()
        self.interrupt = interrupt
        self.serp_owner: UUID | None = None

    def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
        self.requests.append(request)
        action = request.compiled_query
        assert action is not None
        serp = request.provider is DiscoveryProvider.SERPSEARCH
        if serp and self.serp_owner is None:
            self.serp_owner = action.artifact_id
        first_serp = serp and self.serp_owner == action.artifact_id
        if first_serp and request.page_number == 2:
            self.deep_page.set()
            assert self.release_deep.wait(15)
            if self.interrupt:
                raise _DeeperPageInterrupted
            rows = [(self.MIRROR, self.DOI, 0), ("https://new.example.org/later", None, 10)]
        elif first_serp:
            rows = [(self.ORIGINAL, self.DOI, 0)] + [
                (f"https://first-{i}.example.org/paper", None, i) for i in range(1, request.limit)
            ]
        else:
            rows = [("https://second-provider.example.org/evaluation", None, 20)]
        return phase12.SearchResponse(
            provider_name=request.provider.value,
            results=[
                phase12.SearchResult(
                    original_url=url,
                    title=f"Regional program and course completion study {paper:02d}",
                    rank=request.start_offset + rank,
                    metadata=SearchDiscoveryMetadata(
                        doi=doi,
                        abstract=(
                            "A controlled trial measured regional program course completion "
                            "against standard materials. The groups had different completion rates."
                        ),
                        work_type="article",
                    ),
                )
                for rank, (url, doi, paper) in enumerate(rows, 1)
            ],
        )


@pytest.mark.parametrize("recovery", ("adequate", "truncated", "unknown-page"))
def test_production_scouts_and_captures_before_deeper_search_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    recovery: str,
) -> None:
    path = tmp_path / "paged-overlap.sqlite"
    run_id = uuid4()
    search = _GatedPages(interrupt=recovery == "unknown-page")
    first_capture = Event()
    release_capture = Event()
    scout_waiting = Event()
    release_scout = Event()
    assessment_seen = Event()
    admit = v2_deep_analysis.run_v2_evidence_admission

    def observe_assessment(**kwargs: Any) -> object:
        analyst = kwargs["analyst_result"]
        if not assessment_seen.is_set() and any(item.assessment for item in analyst.source_results):
            page = read_live_sources(path, run_id, offset=0)
            if any(card.state == "assessed" for card in page.items):
                assert all(
                    card.note_kind == "analyst" for card in page.items if card.state == "assessed"
                )
                assessment_seen.set()
        return admit(**kwargs)

    monkeypatch.setattr(v2_deep_analysis, "run_v2_evidence_admission", observe_assessment)

    class _GatedScout(production._ConceptModel):
        def generate(self, request: Any) -> object:
            if request.stage is LLMStage.SCOUT and not scout_waiting.is_set():
                scout_waiting.set()
                assert release_scout.wait(15)
            return super().generate(request)

    aggregate_waiting = Event()
    release_aggregate = Event()
    first_key = V2_SCOUT_ARTIFACT_KEY + "/first-pass-v1"
    scout_key = "scout-checkpoint-v1/" + first_key
    persist_scout_batch = v2_discovery.insert_v2_artifact_batch

    def hold_first_pass_aggregate(db_path: str, artifacts: tuple) -> object:
        if any(key == first_key for key, _artifact, _created_at in artifacts):
            aggregate_waiting.set()
            assert release_aggregate.wait(15)
        return persist_scout_batch(db_path, artifacts)

    monkeypatch.setattr(v2_discovery, "insert_v2_artifact_batch", hold_first_pass_aggregate)

    class _Scraper(phase12._Scraper):
        def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
            response = super().scrape(request)
            if request.url == search.ORIGINAL:
                first_capture.set()
                assert release_capture.wait(15)
                return response.model_copy(update={"truncated": recovery == "truncated"})
            if request.url == search.MIRROR:
                return response.model_copy(
                    update={
                        "text": response.text
                        + " The full results include one additional comparison.",
                    }
                )
            return response

    scraper = _Scraper()
    model = _GatedScout()
    providers = (DiscoveryProvider.SERPSEARCH, DiscoveryProvider.EXA)

    def run() -> V2ProductionPipelineResult:
        return production._run_fresh(
            path,
            model=model,
            search=search,
            scraper=scraper,
            run_id=run_id,
            providers=providers,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            assert search.deep_page.wait(15)
            assert scout_waiting.wait(15)
            leads = read_live_sources(path, run_id)
            assert leads.items and {card.state for card in leads.items} == {"lead"}
            assert read_live_sources(path, run_id, known=leads.revision).unchanged
            release_scout.set()
            assert first_capture.wait(15)
            assert aggregate_waiting.wait(15)
            # Other captures can displace the blocked source from the live shortlist.
            screened = read_live_sources(path, run_id, offset=0)
            original_card = next(card for card in screened.items if card.url == search.ORIGINAL)
            assert original_card.state == "screened"
            assert original_card.note_kind == "scout"
            release_capture.set()

            def capture_is_ready() -> bool:
                return any(c.start.url == search.ORIGINAL for c in _captures(path, run_id))

            _wait(capture_is_ready)
            captured = read_live_sources(path, run_id, offset=0)
            original_card = next(card for card in captured.items if card.url == search.ORIGINAL)
            assert original_card.readable_url == search.ORIGINAL
            assert original_card.state in {"full_text", "captured", "assessed", "admitted"}
            assert not future.done()
            assert [(r.provider, r.page_number) for r in search.requests[:3]] == [
                (DiscoveryProvider.SERPSEARCH, 1),
                (DiscoveryProvider.EXA, 1),
                (DiscoveryProvider.SERPSEARCH, 2),
            ]
            prefix = v2_stage_checkpoint.read_checkpoint(
                str(path), run_id, scout_key, v2_stage_checkpoint.V2ScoutRoundCheckpoint
            )
            batch = v2_stage_checkpoint.read_checkpoint(
                str(path),
                run_id,
                f"{scout_key}/batch-1/attempt-1/outcome",
                v2_stage_checkpoint.V2StageOutcomeCheckpoint,
            )
            assert prefix is not None and prefix.ranking_artifact is not None
            assert batch is not None and isinstance(batch.candidate, ScoutBatch)
            with pytest.raises(KeyError):
                read_v2_artifact(path, run_id, first_key)
            with pytest.raises(KeyError):
                read_v2_artifact(path, run_id, V2_SCOUT_ARTIFACT_KEY)
            scouted_ids = {item.item_id for item in batch.candidate.items}
            assert scouted_ids == set(prefix.scout_item_ids)
            providers_by_item = {item.item_id: item.provider for item in prefix.items}
            assert {providers_by_item[item_id] for item_id in scouted_ids} == set(providers)
            original = next(c for c in _captures(path, run_id) if c.start.url == search.ORIGINAL)
        finally:
            release_scout.set()
            release_capture.set()
            release_aggregate.set()
            search.release_deep.set()
        if recovery == "unknown-page":
            with pytest.raises(_DeeperPageInterrupted):
                future.result(timeout=30)
        else:
            result = future.result(timeout=30)

    if recovery == "unknown-page":
        starts = provider_attempt_audit(path, run_id).starts
        result = run()
        assert provider_attempt_audit(path, run_id).starts == starts
        assert provider_attempt_audit(path, run_id).interrupted_unknown
        assert len([r for r in search.requests if r.page_number == 2]) == 1
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output.release_validation.valid
    assert assessment_seen.is_set()
    final_page = read_live_sources(path, run_id, offset=0)
    assert len(read_live_sources(path, run_id).items) <= 7
    assert any(card.state == "admitted" for card in final_page.items)
    assert search.MIRROR not in {
        card.url for card in final_page.items if card.work_id != original_card.work_id
    }
    assert any(card.work_id == original_card.work_id for card in final_page.items)
    assert [request.url for request in scraper.requests].count(search.ORIGINAL) == 1
    assert [request.url for request in scraper.requests].count(search.MIRROR) == (
        recovery == "truncated"
    )
    final = V2DiscoveryScoutOutput.model_validate_json(
        read_v2_artifact(path, run_id, V2_SCOUT_ARTIFACT_KEY).payload_json
    )
    owner = next(
        cluster for cluster in prefix.clusters if cluster.cluster_id == original.start.cluster_id
    )
    assert owner in final.clusters
    assert original.source.snapshot.snapshot_id in {
        c.source.snapshot.snapshot_id for c in _captures(path, run_id) if c.source
    }
    screened = [
        candidate.source_url
        for request in model.requests
        if request.stage is LLMStage.SCOUT
        for candidate in request.input_artifact.candidates
    ]
    assert screened.count(search.ORIGINAL) == 1 and search.MIRROR not in screened
    if recovery != "unknown-page":
        assert len(final.late_mirrors) >= 1
        assert len([page for page in read_pages(path, run_id) if page.page_number == 2]) == 1
    if recovery == "truncated":
        fuller = next(c for c in _captures(path, run_id) if c.start.url == search.MIRROR)
        checkpoint = V2EvidenceCheckpoint.model_validate_json(
            read_v2_artifact(path, run_id, CHECKPOINT_KEY).payload_json
        )
        wave = next(w for w in checkpoint.waves if w.source_id == owner.cluster_id)
        quote = wave.extraction.sources[0].candidate
        assert quote.snapshot_id == original.source.snapshot.snapshot_id
        assert quote.snapshot_id != fuller.source.snapshot.snapshot_id
        (offset,) = quote.segment_offsets
        assert (
            original.source.snapshot.normalized_text[offset.start_char : offset.end_char]
            == phase12.QUOTE
        )
        paper_audit = V2PaperIdentityAudit.model_validate_json(
            read_v2_artifact(path, run_id, "retained-paper-identity-v2").payload_json
        )
        group = next(
            group
            for group in paper_audit.groups
            if group.canonical_source_id == fuller.start.cluster_id
        )
        assert {row.snapshot_id for row in group.locations} == {
            original.source.snapshot.snapshot_id,
            fuller.source.snapshot.snapshot_id,
        }


@pytest.mark.parametrize(
    ("second_decision", "interruption", "limit", "repair"),
    (
        ("retrieve", None, None, False),
        ("retrieve", None, None, True),
        ("maybe", "plan", None, False),
        ("retrieve", "outcome", None, False),
        ("retrieve", "legacy plan", None, False),
        ("skip", None, None, False),
        ("retrieve", None, "budget", False),
        ("retrieve", None, "cap", False),
    ),
)
def test_progressive_reconsiders_skipped_work_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    second_decision: str,
    interruption: str | None,
    limit: str | None,
    repair: bool,
) -> None:
    path, run_id = tmp_path / "reconsideration.sqlite", uuid4()
    weak_url = "https://index.example.org/report"
    shorter_abstract = (
        "A controlled trial compared regional course completion outcomes "
        "against a randomly matched comparison group."
    )
    checkpoint_key = "scout-checkpoint-v1/" + V2_SCOUT_ARTIFACT_KEY
    first_key = V2_SCOUT_ARTIFACT_KEY + "/first-pass-v1"

    class Search(_GatedPages):
        MIRROR = "https://www.nber.org/papers/w12345" if repair else _GatedPages.MIRROR

        def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
            response = super().search(request)
            results = []
            for item in response.results:
                if item.original_url == self.ORIGINAL:
                    item = item.model_copy(
                        update={"metadata": item.metadata.model_copy(update={"abstract": None})}
                    )
                if item.original_url == self.MIRROR:
                    results.append(
                        item.model_copy(
                            update={
                                "original_url": weak_url,
                                "rank": item.rank + 2,
                                "metadata": item.metadata.model_copy(
                                    update={"abstract": shorter_abstract}
                                ),
                            }
                        )
                    )
                    if repair:
                        item = item.model_copy(
                            update={
                                "title": "Working Paper No. 12345",
                                "metadata": item.metadata.model_copy(update={"abstract": None}),
                            }
                        )
                results.append(item)
            return response.model_copy(
                update={"results": sorted(results, key=lambda item: item.rank)}
            )

    class Model(production._ConceptModel):
        def generate(self, request: Any) -> object:
            if request.stage is LLMStage.SCOUT:
                self.requests.append(request)
                return ScoutBatch(
                    run_id=run_id,
                    items=tuple(
                        ScoutItem(
                            item_id=candidate.item_id,
                            decision=(
                                second_decision if candidate.source_url == search.MIRROR else "skip"
                            ),
                            rationale="Offline metadata screening.",
                        )
                        for candidate in request.input_artifact.candidates
                    ),
                )
            return super().generate(request)

    search, model, scraper = Search(), Model(), phase12._Scraper()
    search.release_deep.set()
    if repair:

        def repair_metadata(number: str) -> v2_discovery.NberPaperMetadata:
            assert number == "12345"
            return v2_discovery.NberPaperMetadata(
                handle="RePEc:nbr:nberwo:12345",
                title="Regional program and course completion study 00",
                abstract=(
                    "A controlled trial measured regional program course completion against "
                    "standard materials. The groups had different completion rates."
                ),
            )

        monkeypatch.setattr(v2_discovery, "resolve_nber_metadata", repair_metadata)

    def run() -> V2ProductionPipelineResult:
        return production._run_fresh(
            path,
            model=model,
            search=search,
            scraper=scraper,
            run_id=run_id,
            providers=(DiscoveryProvider.SERPSEARCH, DiscoveryProvider.EXA),
        )

    if limit:
        select = v2_discovery._ranked_scout_selection

        def limited_selection(**kwargs: Any) -> object:
            if kwargs["reconsiderations"]:
                if limit == "cap":
                    kwargs["policy"] = kwargs["policy"].model_copy(
                        update={"max_scout_per_round": len(kwargs["already_scouted"])}
                    )
                else:
                    snapshot = kwargs["llm_provider"].snapshot()
                    kwargs["budget_snapshot"] = lambda: snapshot.model_copy(
                        update={"physical_calls_remaining": 0}
                    )
            return select(**kwargs)

        monkeypatch.setattr(v2_discovery, "_ranked_scout_selection", limited_selection)

    if interruption:
        with monkeypatch.context() as patch:
            if interruption == "legacy plan":
                cluster = v2_discovery._progressive_clusters
                patch.setattr(
                    v2_discovery,
                    "_progressive_clusters",
                    lambda items, prefix, **kwargs: cluster(items, prefix),
                )
            if interruption in {"plan", "legacy plan"}:
                persist = v2_discovery.insert_v2_artifact

                def interrupt_plan(*args: Any, **kwargs: Any) -> object:
                    result = persist(*args, **kwargs)
                    if args[1] == checkpoint_key:
                        raise KeyboardInterrupt("saved Scout plan")
                    return result

                patch.setattr(v2_discovery, "insert_v2_artifact", interrupt_plan)
            else:
                save_outcome = v2_discovery.save_stage_outcome

                def interrupt_outcome(*args: Any, **kwargs: Any) -> object:
                    result = save_outcome(*args, **kwargs)
                    if args[1].stage_key.startswith(checkpoint_key + "/batch-"):
                        raise KeyboardInterrupt("saved Scout outcome")
                    return result

                patch.setattr(v2_discovery, "save_stage_outcome", interrupt_outcome)
            with pytest.raises(KeyboardInterrupt, match="saved Scout"):
                run()
        saved = read_v2_artifact(path, run_id, checkpoint_key)
        assert not scraper.requests
        run()
        assert read_v2_artifact(path, run_id, checkpoint_key) == saved
    else:
        run()

    def discovery(key: str) -> V2DiscoveryScoutOutput:
        return V2DiscoveryScoutOutput.model_validate_json(
            read_v2_artifact(path, run_id, key).payload_json
        )

    first, final = discovery(first_key), discovery(V2_SCOUT_ARTIFACT_KEY)
    by_url = {item.source_url: item for item in final.items}
    original, improved = by_url[search.ORIGINAL], by_url[search.MIRROR]
    assert original.abstract is None and improved.abstract
    if repair:
        assert improved.title == original.title
        assert any(entry.key == "nber_metadata_repair" for entry in improved.provider_metadata)
    assert final.scout_batches[: len(first.scout_batches)] == first.scout_batches
    decisions = {row.item_id: row.decision for batch in final.scout_batches for row in batch.items}
    assert decisions[original.item_id] == "skip"
    if interruption == "legacy plan":
        assert improved.item_id not in decisions and not scraper.requests
        assert any(link.item_id == improved.item_id for link in final.late_mirrors)
        return
    assert decisions.get(improved.item_id) == (None if limit else second_decision)
    assert by_url[weak_url].item_id not in decisions
    owner = next(cluster for cluster in first.clusters if original.item_id in cluster.item_ids)
    (work,) = [cluster for cluster in final.clusters if original.item_id in cluster.item_ids]
    assert work.cluster_id == owner.cluster_id
    assert set(work.item_ids) == {original.item_id, improved.item_id, by_url[weak_url].item_id}
    checkpoint = v2_stage_checkpoint.V2ScoutRoundCheckpoint.model_validate_json(
        read_v2_artifact(path, run_id, checkpoint_key).payload_json
    )
    assert checkpoint.policy == "scout-round-checkpoint-v2"
    ranking = v2_discovery.V2MetadataRankingArtifact.model_validate_json(
        read_v2_artifact(path, run_id, "phase-3-metadata-ranking-round-1").payload_json
    )
    assert ranking == checkpoint.ranking_artifact
    assert len({rank.work_key for rank in ranking.ranks if rank.item_id in work.item_ids}) == 1
    (disposition,) = [
        row for row in ranking.scout_dispositions if row.reconsidered_from_item_id is not None
    ]
    assert disposition.item_id == improved.item_id
    assert disposition.reconsidered_from_item_id == original.item_id
    assert disposition.disposition == (f"not_scouted_{limit}" if limit else "scouted")
    assert improved.provenance_chain[0] in work.metadata_provenance

    screened = [
        candidate.source_url
        for request in model.requests
        if request.stage is LLMStage.SCOUT
        for candidate in request.input_artifact.candidates
    ]
    assert screened.count(search.ORIGINAL) == 1
    assert screened.count(search.MIRROR) == (0 if limit else 1)
    assert weak_url not in screened
    if limit:
        assert len([request for request in model.requests if request.stage is LLMStage.SCOUT]) == (
            len(first.scout_batches)
        )
    should_capture = limit is None and second_decision != "skip"
    assert [request.url for request in scraper.requests] == (
        [search.MIRROR] if should_capture else []
    )
    acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(path, run_id, ACQUISITION).payload_json
    )
    assert [row.cluster_id for row in acquisition.survivors] == (
        [owner.cluster_id] if should_capture else []
    )
    if should_capture:
        dispatch = V2CaptureDispatch.model_validate_json(
            read_v2_artifact(path, run_id, f"{ACQUISITION}/overlap-v1/dispatch-1").payload_json
        )
        assert dispatch.cluster_id == owner.cluster_id and dispatch.item_id == improved.item_id
        evidence = V2EvidenceCheckpoint.model_validate_json(
            read_v2_artifact(path, run_id, CHECKPOINT_KEY).payload_json
        )
        assert [wave.source_id for wave in evidence.waves] == [owner.cluster_id]
        calls = len(model.requests)
        run()
        assert len(model.requests) == calls
        assert [request.url for request in scraper.requests] == [search.MIRROR]


class _SlowRuralCapture(phase12._Scraper):
    def __init__(self, *, include_rural_evidence: bool) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()
        self.include_rural_evidence = include_rural_evidence

    def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
        response = super().scrape(request)
        if not request.url.endswith("/6"):
            return response
        self.started.set()
        assert self.release.wait(15)
        if self.include_rural_evidence:
            return response.model_copy(
                update={
                    "text": response.text
                    + (
                        " The rural cohort comparison included 200 participants in the "
                        "program and measured completion against the matched group."
                    ),
                }
            )
        return response


@pytest.mark.parametrize("reconcile", (False, True))
def test_initial_gap_starts_with_unrelated_capture_still_in_flight(
    tmp_path: Path,
    reconcile: bool,
) -> None:
    path = tmp_path / "gap-overlap.sqlite"
    run_id = uuid4()
    gap_started = Event()
    search = _Works(7)
    scraper = _SlowRuralCapture(include_rural_evidence=reconcile)

    class _GapSignal(production._ConceptModel):
        def generate(self, request: phase12.LLMRequest) -> object:
            output = super().generate(request)
            if request.stage is LLMStage.GAP_ANALYSIS and not gap_started.is_set():
                assert not scraper.release.is_set()
                assert len(request.input_artifact.assessed_source_findings) == 4
                assert len(request.input_artifact.outstanding_capture_source_ids) >= 1
                gap_started.set()
                if reconcile:
                    missing = "Rural cohort evidence remains missing."
                    return output.model_copy(
                        update={
                            "material_gaps": tuple(
                                gap.model_copy(update={"missing_evidence": missing})
                                for gap in output.material_gaps
                            ),
                            "new_search_directions": tuple(
                                target.model_copy(update={"missing_evidence": missing})
                                for target in output.new_search_directions
                            ),
                        }
                    )
            return output

    model = _GapSignal(completed_rounds=2 if reconcile else 1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run, path, run_id, model, search, scraper)
        try:
            assert scraper.started.wait(15)
            assert gap_started.wait(15), "the unrelated tail capture blocked Gap Analysis"
            assert not future.done()
        finally:
            scraper.release.set()
        result = future.result(timeout=30)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output.release_validation.valid
    gap = V2GapAnalysisOutput.model_validate_json(
        read_v2_artifact(path, run_id, V2_GAP_ANALYSIS_ARTIFACT_KEY).payload_json
    )
    acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(path, run_id, ACQUISITION).payload_json
    )
    late_source = next(a for a in acquisition.acquisitions if a.snapshot.source_url.endswith("/6"))
    assert late_source.cluster_id in gap.input.outstanding_capture_source_ids
    assert late_source.cluster_id not in {
        item.source_id for item in gap.input.assessed_source_findings
    }
    gaps = [r for r in model.requests if r.stage is LLMStage.GAP_ANALYSIS]
    assert sum(bool(r.input_artifact.outstanding_capture_source_ids) for r in gaps) == 1
    assert {r.compiled_query.conceptual_query.round_number for r in search.requests} == {1}
    if reconcile:
        assert len(gaps) == 2
        assert late_source.cluster_id in {
            item.source_id for item in gaps[-1].input_artifact.assessed_source_findings
        }
    else:
        assert len(gaps) == 1


def test_provisional_gap_replays_the_same_input_after_tail_capture_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "gap-resume.sqlite"
    run_id = uuid4()
    late_started, release_late, outcome_saved = Event(), Event(), Event()
    model, search = production._ConceptModel(), _Works(7)

    class _SlowLast(phase12._Scraper):
        def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
            response = super().scrape(request)
            if request.url.endswith("/6"):
                late_started.set()
                assert release_late.wait(15)
            return response

    scraper = _SlowLast()
    original = v2_stage_checkpoint.insert_v2_artifact

    def interrupt(*args: Any, **kwargs: Any) -> object:
        result = original(*args, **kwargs)
        if str(args[1]).startswith("gap-checkpoint-v1/") and str(args[1]).endswith("/outcome"):
            outcome_saved.set()
            raise KeyboardInterrupt("saved provisional Gap outcome")
        return result

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=1) as pool:
        patch.setattr(v2_stage_checkpoint, "insert_v2_artifact", interrupt)
        future = pool.submit(_run, path, run_id, model, search, scraper)
        try:
            assert late_started.wait(15)
            assert outcome_saved.wait(15)
        finally:
            release_late.set()
        with pytest.raises(KeyboardInterrupt, match="saved provisional Gap"):
            future.result(timeout=30)
    result = _run(path, run_id, model, search, scraper)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    (request,) = [r for r in model.requests if r.stage is LLMStage.GAP_ANALYSIS]
    gap = V2GapAnalysisOutput.model_validate_json(
        read_v2_artifact(path, run_id, V2_GAP_ANALYSIS_ARTIFACT_KEY).payload_json
    )
    assert gap.input == request.input_artifact
    assert gap.input.outstanding_capture_source_ids
    assert len(scraper.requests) == 7


def test_pending_capture_defers_only_its_matched_gap_across_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "mixed-gap-overlap.sqlite"
    run_id = uuid4()
    gap_started = Event()
    search = _Works(7)
    scraper = _SlowRuralCapture(include_rural_evidence=True)
    components = (
        V2InitialPlannerClaimComponent(
            dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            claim_component="increases course completion",
        ),
        V2InitialPlannerClaimComponent(
            dimension=V2ClaimCoverageDimension.POPULATION_AND_SETTING,
            claim_component="regional program",
        ),
    )
    missing = (
        "Rural cohort evidence remains missing.",
        "Urban evening-student evidence remains missing.",
    )
    gap_ids = ("rural-cohort", "urban-evening-students")

    class _MixedGaps(production._ConceptModel):
        def generate(self, request: phase12.LLMRequest) -> object:
            output = super().generate(request)
            if isinstance(output, production.V2InitialPlannerConceptsOutput):
                return output.model_copy(update={"claim_coverage_focus": components})
            if isinstance(output, production.V2AdaptiveSearchConceptsOutput):
                assert all(
                    lane.target_gap_ids == ("urban-evening-students",)
                    for lane in request.input_artifact.lanes
                )
                return output.model_copy(
                    update={
                        "searches": tuple(
                            proposal.model_copy(
                                update={
                                    "concepts": production.V2QueryConcepts(
                                        required_concepts=(
                                            production.V2QueryConceptGroup(
                                                concept="urban evening students"
                                            ),
                                            production.V2QueryConceptGroup(
                                                concept="course completion comparison"
                                            ),
                                        ),
                                        purpose="gap",
                                    ),
                                }
                            )
                            for proposal in output.searches
                        ),
                    }
                )
            if request.stage is not LLMStage.GAP_ANALYSIS or not output.continue_research:
                return output
            initial = request.input_artifact.completed_round == 1
            if initial:
                assert not scraper.release.is_set()
                assert request.input_artifact.outstanding_capture_source_ids
                gap_started.set()
            # Round 2 raises rural again. It still awaits evidence assessment.
            focus = components if initial else components[:1]
            return output.model_copy(
                update={
                    "material_gaps": tuple(
                        phase12.V2MaterialGap(
                            gap_id=gap_ids[index],
                            direction=production.DIRECTIONS.enabled_directions[0],
                            missing_evidence=missing[index],
                            rationale="The comparison is still material to the claim.",
                            claim_dimension=component.dimension,
                            unsupported_claim_component=component.claim_component,
                        )
                        for index, component in enumerate(focus)
                    ),
                    "new_search_directions": tuple(
                        phase12.V2GapSearchDirection(
                            gap_id=gap_ids[index],
                            direction=production.DIRECTIONS.enabled_directions[0],
                            missing_evidence=missing[index],
                            search_focus=missing[index],
                            claim_dimension=component.dimension,
                            resolving_evidence_kind="A controlled comparison in this population",
                        )
                        for index, component in enumerate(focus)
                    ),
                }
            )

    model = _MixedGaps(completed_rounds=3)
    original = v2_adaptive_search._run_round_from_plan

    def interrupt_after_round_two(**kwargs: Any) -> object:
        outcome = original(**kwargs)
        if kwargs["planned"].plan.round_number == 2:
            raise KeyboardInterrupt("saved the Round-2 search results")
        return outcome

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=1) as pool:
        patch.setattr(v2_adaptive_search, "_run_round_from_plan", interrupt_after_round_two)
        future = pool.submit(_run, path, run_id, model, search, scraper)
        try:
            assert scraper.started.wait(15)
            assert gap_started.wait(15)
            assert all(r.compiled_query.conceptual_query.round_number == 1 for r in search.requests)
        finally:
            scraper.release.set()
        with pytest.raises(KeyboardInterrupt, match="saved the Round-2 search results"):
            future.result(timeout=30)

    queries_before = tuple(search.requests)
    initial_gap = read_v2_artifact(path, run_id, V2_GAP_ANALYSIS_ARTIFACT_KEY)
    original_gap = V2GapAnalysisOutput.model_validate_json(initial_gap.payload_json)
    assert original_gap.input.outstanding_capture_source_ids
    assert tuple(gap.gap_id for gap in original_gap.result.material_gaps) == gap_ids
    dispatched = [r for r in queries_before if r.compiled_query.conceptual_query.round_number == 2]
    assert dispatched
    assert all(
        r.compiled_query.conceptual_query.target_gap_ids == ("urban-evening-students",)
        and "urban evening students" in r.query_text
        for r in dispatched
    )

    result = _run(path, run_id, model, search, scraper)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output.release_validation.valid
    assert tuple(search.requests) == queries_before
    assert model.search_agent_calls == 1
    assert read_v2_artifact(path, run_id, V2_GAP_ANALYSIS_ARTIFACT_KEY) == initial_gap
    gap_calls = [r.input_artifact for r in model.requests if r.stage is LLMStage.GAP_ANALYSIS]
    assert sum(bool(gap.outstanding_capture_source_ids) for gap in gap_calls) == 1
    assert len(gap_calls) == 3
    assert "rural-cohort" in {gap.gap_id for gap in gap_calls[-1].previous_gaps}
    acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(path, run_id, ACQUISITION).payload_json
    )
    late_source = next(a for a in acquisition.acquisitions if a.snapshot.source_url.endswith("/6"))
    assert late_source.cluster_id in original_gap.input.outstanding_capture_source_ids
    assert late_source.cluster_id in {
        finding.source_id for finding in gap_calls[-1].assessed_source_findings
    }


@pytest.mark.parametrize("recover", [True, False])
def test_progressive_resume_reuses_abstract_and_tries_known_article(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recover: bool
) -> None:
    abstract_url = "https://study-0.example.org/preferred"
    article_url = "https://study-0.example.org/0"

    class _KnownLocations(_Works):
        def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
            response = super().search(request)
            item = response.results[0]
            return response.model_copy(
                update={
                    "results": [
                        item.model_copy(
                            update={
                                "metadata": item.metadata.model_copy(
                                    update={"full_text_url": abstract_url}
                                )
                            }
                        )
                    ]
                }
            )

    class _AbstractFirst(phase12._Scraper):
        def scrape(self, request: phase12.ScrapeRequest) -> phase12.ScrapeResponse:
            response = super().scrape(request)
            if request.url == abstract_url:
                return response.model_copy(update={"text": ABSTRACT})
            return response if recover else response.model_copy(update={"text": ""})

    path, run_id = tmp_path / "abstract-resume.sqlite", uuid4()
    search, scraper, model = (
        _KnownLocations(1),
        _AbstractFirst(),
        production._ConceptModel(),
    )
    persist = v2_acquisition.insert_v2_artifact

    def interrupt(*args: Any, **kwargs: Any) -> object:
        result = persist(*args, **kwargs)
        if str(args[1]).endswith("/completion"):
            raise KeyboardInterrupt("offline interruption after abstract completion")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(v2_acquisition, "insert_v2_artifact", interrupt)
        with pytest.raises(KeyboardInterrupt, match="after abstract completion"):
            _run(path, run_id, model, search, scraper)
    assert [request.url for request in scraper.requests] == [abstract_url]
    (abstract,) = _captures(path, run_id)
    assert abstract.attempt.succeeded and not abstract.readable
    assert abstract.source.snapshot.normalized_text == ABSTRACT

    result = _run(path, run_id, model, search, scraper)
    assert [request.url for request in scraper.requests] == [abstract_url, article_url]
    saved_abstract, article = _captures(path, run_id)
    assert saved_abstract == abstract
    output = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(path, run_id, ACQUISITION).payload_json
    )
    assert output.attempts == (abstract.attempt, article.attempt)
    (card,) = read_live_sources(path, run_id).items
    if recover:
        assert article.readable
        assert output.acquisitions == (article.source,)
        assert output.survivors[0].snapshot_id == article.source.snapshot.snapshot_id
        checkpoint = V2EvidenceCheckpoint.model_validate_json(
            read_v2_artifact(path, run_id, CHECKPOINT_KEY).payload_json
        )
        assert checkpoint.waves[0].extraction.sources[0].candidate.snapshot_id == (
            article.source.snapshot.snapshot_id
        )
        assert card.readable_url == article_url and card.state != "abstract_only"
    else:
        assert article.source is None and not article.attempt.succeeded
        assert output.acquisitions == (abstract.source,)
        assert output.probes[0].failure == "abstract_only"
        assert not output.survivors
        assert all(
            req.stage not in {LLMStage.EXTRACTOR, LLMStage.ANALYST} for req in model.requests
        )
        assert card.readable_url == abstract_url and card.state == "abstract_only"
        with ReadOnlyStore(path) as store:
            diagnostics = enrich_discovery_diagnostics(store.connection, run_id, result.diagnostics)
        assert any("abstracts only" in message for message in diagnostics.diagnostic_messages)
