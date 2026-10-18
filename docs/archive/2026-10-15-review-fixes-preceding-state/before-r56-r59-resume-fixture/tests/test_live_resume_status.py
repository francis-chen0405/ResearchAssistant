"""Production-boundary resume rejection preserves the historical run and audit."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import frontend.live_service as live
from frontend.api import ApiRuntime, create_app
from frontend.live_contracts import LiveRunRequest, LiveRunSnapshot
from frontend.service_manager import WigoloServiceManager
from providers.config import ExaConfig
from providers.llm import LLMRequest
from providers.v2_budget import V2RunCeilings, read_v2_physical_call_audit
from providers.v2_factory import V2ProductionFactoryConfig
from researchassistant.api.discovery_diagnostics import enrich_discovery_diagnostics
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirections,
)
from researchassistant.providers.scraper import ScrapeRequest, ScrapeResponse
from researchassistant.providers.search import SearchRequest, SearchResponse
from researchassistant.research.v2_orchestrator import (
    build_v2_run_diagnostics_or_empty,
    run_v2_production_pipeline,
)
from researchassistant.storage.store import init_db, open_read_only_store, read_run
from tests.test_query_production import _ConceptModel
from tests.test_v2_phase12_production import NOW, _routing, _Scraper, _Search, _V2Model

CLAIM = "The regional program increases course completion."


class _InterruptedModel(_V2Model):
    def generate(self, request: LLMRequest) -> object:
        raise KeyboardInterrupt("offline interruption after physical reservation")


@dataclass
class _RunFixture:
    path: Path
    run_id: UUID
    factory: V2ProductionFactoryConfig

    def request(self, *, depth: int = 20) -> LiveRunRequest:
        return LiveRunRequest(
            raw_claim=CLAIM,
            db_path=str(self.path),
            run_id=self.run_id,
            research_controls=self.factory.research_controls.model_copy(
                update={"metadata_depth": depth}
            ),
            max_tokens=self.factory.ceilings.max_total_tokens,
            max_cost_usd=self.factory.ceilings.max_total_cost_usd,
            max_llm_calls=self.factory.ceilings.max_physical_calls,
            directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        )

    def execute(self, model: _V2Model) -> object:
        return run_v2_production_pipeline(
            CLAIM,
            db_path=self.path,
            run_id=self.run_id,
            directions=self.request().directions,
            discovery_providers=self.factory.discovery_providers,
            search_providers={DiscoveryProvider.EXA: _Search()},
            wigolo_provider=_Scraper(),
            llm_provider=model,
            routing_config=self.factory.routing,
            ceilings=self.factory.ceilings,
            research_controls=self.factory.research_controls,
            provider_policy_fingerprint=self.factory.semantic_fingerprint_sha256(),
            clock=lambda: NOW,
        )


@pytest.fixture
def run_fixture(tmp_path: Path) -> _RunFixture:
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,), metadata_depth=20)
    return _RunFixture(
        tmp_path / "runs.sqlite3",
        uuid4(),
        V2ProductionFactoryConfig(
            routing=_routing(),
            research_controls=controls,
            discovery_providers=controls.discovery_providers,
            ceilings=V2RunCeilings(
                max_physical_calls=40,
                max_total_tokens=100_000,
                max_total_cost_usd=Decimal("1"),
            ),
            exa=ExaConfig(api_key="offline-fixture"),
        ),
    )


@pytest.fixture
def interrupted(run_fixture: _RunFixture) -> _RunFixture:
    with pytest.raises(KeyboardInterrupt):
        run_fixture.execute(_InterruptedModel())
    assert read_run(run_fixture.path, run_fixture.run_id).status.value == "running"
    assert len(read_v2_physical_call_audit(run_fixture.path, run_fixture.run_id).starts) == 1
    return run_fixture


def _install_bundle(
    monkeypatch: pytest.MonkeyPatch,
    fixture: _RunFixture,
    *,
    depth: int = 20,
    entered: Event | None = None,
    release: Event | None = None,
    model: _V2Model | None = None,
) -> tuple[_V2Model, _Search, _Scraper]:
    model = model if model is not None else _ConceptModel()
    search, scraper = _Search(), _Scraper()
    factory = fixture.factory.model_copy(
        update={"research_controls": fixture.request(depth=depth).research_controls}
    )

    def from_environment(*args: object, **kwargs: object) -> V2ProductionFactoryConfig:
        return factory

    def build_bundle(config: V2ProductionFactoryConfig) -> SimpleNamespace:
        if entered is not None and release is not None:
            entered.set()
            assert release.wait(5)
        return SimpleNamespace(
            llm=model,
            search_providers={DiscoveryProvider.EXA: search},
            wigolo=scraper,
            firecrawl=None,
            crossref_resolver=None,
        )

    monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", from_environment)
    monkeypatch.setattr(live, "build_v2_production_bundle", build_bundle)
    return model, search, scraper


@pytest.mark.parametrize("pause_stage", ["search", "acquisition"])
def test_active_polling_returns_saved_discovery_diagnostics(
    run_fixture: _RunFixture, monkeypatch: pytest.MonkeyPatch, pause_stage: str
) -> None:
    entered, release = Event(), Event()
    # Leave enough synthetic headroom for the mandatory analysis reservations
    # so this fixture actually reaches both discovery and acquisition.
    run_fixture.factory = run_fixture.factory.model_copy(
        update={
            "ceilings": V2RunCeilings(
                max_physical_calls=160, max_total_tokens=500_000, max_total_cost_usd=Decimal("5")
            )
        }
    )
    _, search, scraper = _install_bundle(monkeypatch, run_fixture)
    search.unique_results = True
    original_search, original_scrape = search.search, scraper.scrape

    def paused_search(request: SearchRequest) -> SearchResponse:
        if pause_stage == "search":
            entered.set()
            assert release.wait(20)
        return original_search(request)

    def paused_scrape(request: ScrapeRequest) -> ScrapeResponse:
        if pause_stage == "acquisition":
            entered.set()
            assert release.wait(20)
        return original_scrape(request)

    monkeypatch.setattr(search, "search", paused_search)
    monkeypatch.setattr(scraper, "scrape", paused_scrape)
    controller = live.LiveResearchController(environment={})
    try:
        started = controller.start(run_fixture.request())
        assert started.started, started.message
        assert entered.wait(10), controller.snapshot(run_fixture.path, started.run_id).message
        before = run_fixture.path.read_bytes()
        with open_read_only_store(run_fixture.path) as store:
            expected = enrich_discovery_diagnostics(
                store.connection,
                started.run_id,
                build_v2_run_diagnostics_or_empty(
                    store.connection, started.run_id, run_fixture.factory.discovery_providers
                ),
            )
        client = TestClient(
            create_app(
                ApiRuntime(controller=controller, services=WigoloServiceManager(), environment={}),
                load_keychain_on_start=False,
                allowed_hosts=("testserver",),
            )
        )
        response = client.get(
            f"/api/research/{started.run_id}", params={"db_path": str(run_fixture.path)}
        )
        assert response.status_code == 200, response.text
        snapshot = LiveRunSnapshot.model_validate(response.json())
        assert snapshot.classification == "running" and snapshot.worker_active
        assert snapshot.v2_diagnostics == expected
        assert expected.physical_search_requests > 0
        if pause_stage == "acquisition":
            assert expected.retained_metadata_records > 0
        assert run_fixture.path.read_bytes() == before
    finally:
        release.set()
        assert controller.shutdown(timeout=20)


def test_interrupted_polling_keeps_partial_diagnostics(interrupted: _RunFixture) -> None:
    controller = live.LiveResearchController(environment={})
    before = interrupted.path.read_bytes()
    try:
        snapshot = controller.snapshot(interrupted.path, interrupted.run_id)
        assert snapshot.classification == "interrupted" and not snapshot.worker_active
        assert snapshot.v2_diagnostics is not None
        assert snapshot.v2_diagnostics.physical_search_requests == 0
        assert snapshot.v2_diagnostics.retained_metadata_records is None
        assert interrupted.path.read_bytes() == before
    finally:
        assert controller.shutdown(timeout=20)


def test_api_lifespan_drains_active_resume_without_refunding_unknown_calls(
    interrupted: _RunFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_mlp3_api import FakeServices

    from researchassistant.api import api

    entered, release = Event(), Event()
    model, search, scraper = _install_bundle(
        monkeypatch, interrupted, entered=entered, release=release
    )
    controller = live.LiveResearchController(environment={})
    services = FakeServices()
    stops: list[bool] = []
    observed: list[bool] = []
    before = read_v2_physical_call_audit(interrupted.path, interrupted.run_id)
    monkeypatch.setattr(services, "owns_running_process", lambda: True)
    monkeypatch.setattr(services, "stop", lambda: stops.append(controller.has_active_runs()))
    monkeypatch.setattr(api, "_prepare_default_database", lambda: None)
    runtime = ApiRuntime(controller=controller, services=services, environment={})

    def release_on_cancellation() -> None:
        observed.append(controller._shutdown_requested.wait(5))
        observed.append(not stops)
        release.set()

    monitor = Thread(target=release_on_cancellation)
    monitor.start()
    try:
        with TestClient(api.create_app(runtime, load_keychain_on_start=False)):
            assert controller.start(interrupted.request()).started
            assert entered.wait(5)
        monitor.join(5)
        assert not monitor.is_alive()
        assert observed == [True, True]
        assert stops == [False]
        assert not controller.has_active_runs()
        assert model.requests == search.requests == scraper.requests == []
        assert read_v2_physical_call_audit(interrupted.path, interrupted.run_id) == before
        assert before.starts and before.completions == (None,)
    finally:
        release.set()
        controller.shutdown(timeout=10)
        monitor.join(5)


def _complete_attempt(
    controller: live.LiveResearchController, request: LiveRunRequest
) -> LiveRunSnapshot:
    # Run the real worker and exercise the callback without timing-based polling.
    run_id = request.run_id
    assert run_id is not None
    assert controller.start(request).started
    key = (request.db_path, run_id)
    with controller._lock:
        active = controller._active.get(key)
        cached = controller._early_results.get(key)
    if active is not None:
        result = active.future.result(timeout=10)
        controller._evict_completed_run(key, active.future)
        return result
    assert cached is not None
    return cached


def test_incompatible_resume_visible_first_poll_and_keeps_database_unchanged(
    interrupted: _RunFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = interrupted
    controller = live.LiveResearchController(environment={})
    before = controller.snapshot(fixture.path, fixture.run_id)
    database_hash = sha256(fixture.path.read_bytes()).hexdigest()
    audit = read_v2_physical_call_audit(fixture.path, fixture.run_id)
    model, search, scraper = _install_bundle(monkeypatch, fixture, depth=50)
    try:
        failed = _complete_attempt(controller, fixture.request(depth=50))
        assert failed.classification == "invalid_input"
        runtime = ApiRuntime(
            controller=controller,
            services=WigoloServiceManager(base_environment={}),
            environment={},
        )
        client = TestClient(
            create_app(runtime, load_keychain_on_start=False), base_url="http://127.0.0.1"
        )
        response = client.get(
            f"/api/research/{fixture.run_id}", params={"db_path": str(fixture.path)}
        )
        assert response.status_code == 200
        snapshot = LiveRunSnapshot.model_validate(response.json())
        assert snapshot.classification == "invalid_input", snapshot.message
        assert snapshot.persisted_status == "running"
        assert snapshot.worker_active is False
        assert snapshot.attempt_diagnostic is not None
        assert snapshot.attempt_diagnostic.message == "Discovery settings changed; start a new run."
        assert snapshot.research_controls.metadata_depth == 20
        assert "original settings" in snapshot.message
        assert controller.snapshot(fixture.path, fixture.run_id) == snapshot
        assert not controller.has_active_runs()
        assert model.requests == search.requests == scraper.requests == []
        assert sha256(fixture.path.read_bytes()).hexdigest() == database_hash
        assert read_v2_physical_call_audit(fixture.path, fixture.run_id) == audit
        excluded = {
            "classification",
            "exit_code",
            "message",
            "diagnostic_component",
            "attempt_diagnostic",
        }
        assert snapshot.model_dump(exclude=excluded) == before.model_dump(exclude=excluded)
        assert snapshot.conservative_reserved_tokens > 0
        assert snapshot.conservative_reserved_cost_usd > 0
    finally:
        controller.shutdown(timeout=0)


def test_matching_resume_is_active_and_clears_previous_rejection(
    interrupted: _RunFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = interrupted
    controller = live.LiveResearchController(environment={})
    _install_bundle(monkeypatch, fixture, depth=50)
    _complete_attempt(controller, fixture.request(depth=50))
    entered, release = Event(), Event()

    class PausedModel(_ConceptModel):
        def generate(self, request: LLMRequest) -> object:
            result = super().generate(request)
            entered.set()
            assert release.wait(5)
            return result

    model, _, _ = _install_bundle(monkeypatch, fixture, model=PausedModel())
    original_audit = read_v2_physical_call_audit(fixture.path, fixture.run_id)
    try:
        assert controller.start(fixture.request()).started
        assert entered.wait(5)
        snapshot = controller.snapshot(fixture.path, fixture.run_id)
        assert snapshot.classification == "running"
        assert snapshot.worker_active is True
        assert snapshot.persisted_status == "running"
        assert snapshot.attempt_diagnostic is None
        with controller._lock:
            active = controller._active[(str(fixture.path), fixture.run_id)]
        # Complete the status transition through the real cancellation boundary.
        # The ten-second guard measures draining this controlled provider call,
        # rather than unrelated discovery/acquisition for a complete research run.
        controller.cancel(fixture.path, fixture.run_id)
        release.set()
        result = active.future.result(timeout=10)
        assert result.classification not in {"invalid_input", "configuration_error"}
        assert result.classification == "cancelled"
        assert model.requests, "Matching resume must pass compatibility and execute the model"
        controller._evict_completed_run((str(fixture.path), fixture.run_id), active.future)
        terminal = controller.snapshot(fixture.path, fixture.run_id)
        assert terminal.classification == result.classification
        assert terminal.worker_active is False
        assert terminal.attempt_diagnostic is None
        # The unknown physical attempt is not refunded or overwritten by compatible resume.
        resumed_audit = read_v2_physical_call_audit(fixture.path, fixture.run_id)
        assert resumed_audit.starts[0] == original_audit.starts[0]
        assert resumed_audit.completions[0] is original_audit.completions[0] is None
    finally:
        release.set()
        controller.shutdown(timeout=0)


def test_completed_result_authoritative_after_rejected_resume(
    run_fixture: _RunFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = run_fixture
    fixture.factory = fixture.factory.model_copy(
        update={
            "ceilings": V2RunCeilings(
                max_physical_calls=160, max_total_tokens=500_000, max_total_cost_usd=Decimal("5")
            )
        }
    )
    fixture.execute(_ConceptModel())
    controller = live.LiveResearchController(environment={})
    before = controller.snapshot(fixture.path, fixture.run_id)
    assert before.classification == "released"
    assert before.persisted_status == "completed"
    database_hash = sha256(fixture.path.read_bytes()).hexdigest()
    model, search, scraper = _install_bundle(monkeypatch, fixture, depth=50)
    try:
        assert (
            _complete_attempt(controller, fixture.request(depth=50)).classification
            == "invalid_input"
        )
        snapshot = controller.snapshot(fixture.path, fixture.run_id)
        assert snapshot.model_dump(exclude={"attempt_diagnostic"}) == before.model_dump(
            exclude={"attempt_diagnostic"}
        )
        assert snapshot.attempt_diagnostic is not None
        assert model.requests == search.requests == scraper.requests == []
        assert sha256(fixture.path.read_bytes()).hexdigest() == database_hash
    finally:
        controller.shutdown(timeout=0)


def test_restart_has_no_worker_and_drops_only_ephemeral_diagnostic(
    interrupted: _RunFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = interrupted
    controller = live.LiveResearchController(environment={})
    _install_bundle(monkeypatch, fixture, depth=50)
    _complete_attempt(controller, fixture.request(depth=50))
    controller.shutdown(timeout=0)
    before = fixture.path.read_bytes(), fixture.path.stat().st_mtime_ns
    restarted = live.LiveResearchController(environment={})
    try:
        snapshot = restarted.snapshot(fixture.path, fixture.run_id)
        assert snapshot.classification == "interrupted"
        assert snapshot.persisted_status == "running"
        assert snapshot.worker_active is False
        assert snapshot.attempt_diagnostic is None
        assert snapshot.research_controls.metadata_depth == 20
        assert "No active worker in this app" in snapshot.message
        assert (fixture.path.read_bytes(), fixture.path.stat().st_mtime_ns) == before
    finally:
        restarted.shutdown(timeout=0)


@pytest.mark.parametrize("evict", [False, True])
def test_poll_observes_completion_during_database_read(
    interrupted: _RunFixture, monkeypatch: pytest.MonkeyPatch, evict: bool
) -> None:
    fixture = interrupted
    controller = live.LiveResearchController(environment={})
    entered, release = Event(), Event()
    _install_bundle(monkeypatch, fixture, depth=50, entered=entered, release=release)
    assert controller.start(fixture.request(depth=50)).started
    assert entered.wait(5)
    key = (str(fixture.path), fixture.run_id)
    with controller._lock:
        active = controller._active[key]
    # Suppress the automatic callback to test both pre-eviction and post-eviction reads.
    original_evict = controller._evict_completed_run
    monkeypatch.setattr(controller, "_evict_completed_run", lambda key, future: None)
    projected, finish_poll = Event(), Event()
    original_read = controller._persisted_snapshot

    def delayed_read(resolved: str, run_id: UUID) -> LiveRunSnapshot | None:
        result = original_read(resolved, run_id)
        projected.set()
        assert finish_poll.wait(5)
        return result

    monkeypatch.setattr(controller, "_persisted_snapshot", delayed_read)
    snapshots: list[LiveRunSnapshot] = []
    failures: list[BaseException] = []

    def poll() -> None:
        try:
            snapshots.append(controller.snapshot(fixture.path, fixture.run_id))
        except BaseException as exc:
            failures.append(exc)

    thread = Thread(target=poll)
    thread.start()
    try:
        assert projected.wait(5)
        release.set()
        assert active.future.result(timeout=10).classification == "invalid_input"
        if evict:
            original_evict(key, active.future)
        finish_poll.set()
        thread.join(5)
        assert not thread.is_alive()
        assert failures == []
        assert snapshots[0].classification == "invalid_input"
        assert snapshots[0].worker_active is False
        assert snapshots[0].attempt_diagnostic is not None
        original_evict(key, active.future)
        assert controller.snapshot(fixture.path, fixture.run_id) == snapshots[0]
    finally:
        release.set()
        finish_poll.set()
        thread.join(5)
        controller.shutdown(timeout=0)


@pytest.mark.parametrize("persisted", [False, True])
def test_early_worker_failure_is_pollable_and_redacted(
    run_fixture: _RunFixture,
    monkeypatch: pytest.MonkeyPatch,
    persisted: bool,
) -> None:
    fixture = run_fixture
    if persisted:
        with pytest.raises(KeyboardInterrupt):
            fixture.execute(_InterruptedModel())
    _install_bundle(monkeypatch, fixture)

    def fail_bundle(config: V2ProductionFactoryConfig) -> SimpleNamespace:
        raise RuntimeError("offline-fixture failed before provider transport")

    monkeypatch.setattr(live, "build_v2_production_bundle", fail_bundle)
    controller = live.LiveResearchController(environment={"EXA_API_KEY": "offline-fixture"})
    try:
        failed = _complete_attempt(controller, fixture.request())
        snapshot = controller.snapshot(fixture.path, fixture.run_id)
        assert failed.classification == snapshot.classification == "failed"
        assert not snapshot.worker_active
        assert "offline-fixture" not in snapshot.message
        if persisted:
            assert snapshot.persisted_status == "running"
            assert snapshot.attempt_diagnostic is not None
            assert "offline-fixture" not in snapshot.attempt_diagnostic.message
        else:
            assert not fixture.path.exists()
    finally:
        controller.shutdown(timeout=0)


def test_terminal_commit_overtakes_progress_poll_without_false_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import Future

    from researchassistant.contracts.models import RunStatus
    from researchassistant.research.v2_orchestrator import V2_PRODUCTION_ARTIFACT_KEY
    from researchassistant.storage.store import insert_v2_artifact, update_run
    from tests.test_audit_live_service import _inconsistent_terminal_result, _initialize_run

    path, run_id = tmp_path / "commit-race.sqlite3", uuid4()
    _initialize_run(path, status=RunStatus.RUNNING, directions=ResearchDirections(), run_id=run_id)
    controller = live.LiveResearchController(environment={})
    key = (str(path), run_id)
    future: Future[LiveRunSnapshot] = Future()
    controller._active[key] = live._ActiveRun(future, live._DatabaseLock(path))
    original_read = controller._persisted_snapshot
    reads = 0

    def commit_during_poll(resolved: str, inspected_run_id: UUID) -> LiveRunSnapshot | None:
        nonlocal reads
        snapshot = original_read(resolved, inspected_run_id)
        reads += 1
        if reads == 1:
            assert snapshot is not None and snapshot.classification == "running"
            terminal = _inconsistent_terminal_result(run_id, path)
            insert_v2_artifact(str(path), V2_PRODUCTION_ARTIFACT_KEY, terminal, NOW)
            manifest = read_run(path, run_id)
            update_run(str(path), manifest.model_copy(update={"status": RunStatus.FAILED}))
            future.set_result(controller._snapshot_from_v2_result(terminal))
            controller._evict_completed_run(key, future)
        return snapshot

    monkeypatch.setattr(controller, "_persisted_snapshot", commit_during_poll)
    try:
        snapshot = controller.snapshot(path, run_id)
        assert reads == 2
        assert snapshot.classification == snapshot.persisted_status == "failed"
        assert snapshot.worker_active is False
        assert snapshot.attempt_diagnostic is None
        assert snapshot.latest_checkpoint == V2_PRODUCTION_ARTIFACT_KEY
        assert "No active worker" not in snapshot.message
    finally:
        controller.shutdown(timeout=0)


def test_planned_manifest_does_not_claim_a_worker_after_restart(tmp_path: Path) -> None:
    from researchassistant.contracts.models import RunStatus
    from tests.test_audit_live_service import _initialize_run

    path, run_id = tmp_path / "planned.sqlite3", uuid4()
    _initialize_run(path, status=RunStatus.PLANNED, directions=ResearchDirections(), run_id=run_id)
    before = path.read_bytes(), path.stat().st_mtime_ns
    controller = live.LiveResearchController(environment={})
    try:
        snapshot = controller.snapshot(path, run_id)
        assert snapshot.persisted_status == "planned"
        assert snapshot.classification == "interrupted"
        assert snapshot.worker_active is False
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    finally:
        controller.shutdown(timeout=0)


def test_pre_migration_source_identity_rejects_resume_without_rewriting_history(
    run_fixture: _RunFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from researchassistant.research import discovery_policy
    from researchassistant.runtime.application_runtime import repository_identity

    old_identity = "source-sha256:3db588793ffa3fd023a39172b798eec5682202a53c433dbb2b056a4d46945e5b"
    assert repository_identity() != old_identity

    def prior_identity(root: Path | None = None) -> str:
        return old_identity

    # Freeze the real predecessor source identity in an isolated fake-provider run.
    with monkeypatch.context() as predecessor:
        predecessor.setattr(discovery_policy, "repository_identity", prior_identity)
        with pytest.raises(KeyboardInterrupt):
            run_fixture.execute(_InterruptedModel())
    before = sha256(run_fixture.path.read_bytes()).hexdigest()
    audit = read_v2_physical_call_audit(run_fixture.path, run_fixture.run_id)
    model, search, scraper = _install_bundle(monkeypatch, run_fixture)
    controller = live.LiveResearchController(environment={})
    try:
        attempt = _complete_attempt(controller, run_fixture.request())
        assert attempt.classification == "failed"
        snapshot = controller.snapshot(run_fixture.path, run_fixture.run_id)
        assert snapshot.classification == "failed"
        assert "discovery binding replay conflicts with stored identity" in snapshot.message
        assert snapshot.persisted_status == "running"
        assert snapshot.worker_active is False
        assert model.requests == search.requests == scraper.requests == []
        assert sha256(run_fixture.path.read_bytes()).hexdigest() == before
        assert read_v2_physical_call_audit(run_fixture.path, run_fixture.run_id) == audit
        # Historical read-only inspection remains available after rejection.
        assert (
            controller.snapshot(run_fixture.path, run_fixture.run_id).run_id == run_fixture.run_id
        )
    finally:
        controller.shutdown(timeout=0)


@pytest.mark.parametrize("replacement", ["missing", "empty"])
@pytest.mark.parametrize("evict", [False, True])
def test_completed_worker_cannot_replace_missing_persisted_run(
    run_fixture: _RunFixture,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
    evict: bool,
) -> None:
    fixture = run_fixture
    fixture.factory = fixture.factory.model_copy(
        update={
            "ceilings": V2RunCeilings(
                max_physical_calls=160, max_total_tokens=500_000, max_total_cost_usd=Decimal("5")
            )
        }
    )
    _install_bundle(monkeypatch, fixture)
    controller = live.LiveResearchController(environment={})
    if not evict:
        # Cover the completed-future window before its eviction callback runs.
        monkeypatch.setattr(controller, "_evict_completed_run", lambda key, future: None)
    try:
        completed = _complete_attempt(controller, fixture.request())
        assert completed.classification == "released"
        assert completed.final_brief is not None and completed.rendered_brief_hash is not None
        assert controller.snapshot(fixture.path, fixture.run_id).classification == "released"
        original = fixture.path.with_suffix(".original.sqlite3")
        fixture.path.rename(original)
        original_bytes = original.read_bytes()
        if replacement == "empty":
            init_db(fixture.path)
            before = fixture.path.read_bytes(), fixture.path.stat().st_mtime_ns
        else:
            before = None
        for _ in range(2):
            with pytest.raises(KeyError, match="not found"):
                controller.snapshot(fixture.path, fixture.run_id)
            assert (str(fixture.path), fixture.run_id) not in controller._early_results
            if before is None:
                assert not fixture.path.exists()
            else:
                assert (fixture.path.read_bytes(), fixture.path.stat().st_mtime_ns) == before
        assert original.read_bytes() == original_bytes
    finally:
        controller.shutdown(timeout=0)


def test_completed_worker_rereads_manifest_committed_during_first_poll(
    run_fixture: _RunFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = run_fixture
    fixture.factory = fixture.factory.model_copy(
        update={
            "ceilings": V2RunCeilings(
                max_physical_calls=160, max_total_tokens=500_000, max_total_cost_usd=Decimal("5")
            )
        }
    )
    _install_bundle(monkeypatch, fixture)
    controller = live.LiveResearchController(environment={})
    try:
        assert _complete_attempt(controller, fixture.request()).classification == "released"
        original_read = controller._persisted_snapshot
        reads = 0

        def first_read_precedes_commit(resolved: str, run_id: UUID) -> LiveRunSnapshot | None:
            nonlocal reads
            reads += 1
            return None if reads == 1 else original_read(resolved, run_id)

        monkeypatch.setattr(controller, "_persisted_snapshot", first_read_precedes_commit)
        before = fixture.path.read_bytes(), fixture.path.stat().st_mtime_ns
        snapshot = controller.snapshot(fixture.path, fixture.run_id)
        assert reads == 2
        assert snapshot.classification == "released" and snapshot.final_brief is not None
        assert snapshot.persisted_status == "completed" and not snapshot.worker_active
        assert (fixture.path.read_bytes(), fixture.path.stat().st_mtime_ns) == before
    finally:
        controller.shutdown(timeout=0)
