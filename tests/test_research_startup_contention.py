"""Active-run startup must tolerate the same polling overlap as later stages."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, nullcontext
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
import test_query_production as production
import test_v2_phase12_production as phase12

from researchassistant.agents import v2_initial_planner
from researchassistant.contracts.models import DiscoveryProvider
from researchassistant.contracts.source_recovery import SavedSourceLead
from researchassistant.providers.llm import LLMStage
from researchassistant.research.v2_orchestrator import (
    V2ProductionPipelineResult,
    V2ProductionState,
    run_v2_production_pipeline,
)
from researchassistant.storage.database_lock import database_lock
from researchassistant.storage.store import (
    _connect,
    init_db,
    open_read_only_store,
    read_v2_artifact,
)


@pytest.mark.slow
@pytest.mark.parametrize("controller_owned", [False, True])
def test_planner_startup_survives_progress_snapshot_past_default_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, controller_owned: bool
) -> None:
    path = tmp_path / "startup.sqlite3"
    init_db(str(path))
    unrelated = tmp_path / "unrelated.sqlite3"
    init_db(str(unrelated))
    run_id = uuid4()
    ready, proceed = Event(), Event()
    model = production._ConceptModel(completed_rounds=1)
    search = phase12._Search(unique_results=True)
    original = v2_initial_planner.saved_source_suggestions

    def pause_before_planner_write(
        db_path: str | Path, source_run: UUID, claim: str
    ) -> tuple[SavedSourceLead, ...]:
        with closing(_connect(str(db_path))) as active, closing(_connect(str(unrelated))) as other:
            assert active.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            assert other.execute("PRAGMA busy_timeout").fetchone()[0] == 1000
        leads = original(db_path, source_run, claim)
        ready.set()
        assert proceed.wait(10), "progress snapshot was not opened"
        return leads

    monkeypatch.setattr(v2_initial_planner, "saved_source_suggestions", pause_before_planner_write)

    def run() -> V2ProductionPipelineResult:
        with database_lock(path) if controller_owned else nullcontext():
            return run_v2_production_pipeline(
                production.CLAIM,
                db_path=path,
                directions=production.DIRECTIONS,
                discovery_providers=(DiscoveryProvider.EXA,),
                search_providers={DiscoveryProvider.EXA: search},
                wigolo_provider=phase12._Scraper(),
                llm_provider=model,
                routing_config=phase12._routing(),
                ceilings=production.CEILINGS,
                run_id=run_id,
                legacy_query_planning=False,
                clock=lambda: phase12.NOW,
                _database_lock_owned=controller_owned,
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            assert ready.wait(10), "startup did not reach saved-source planning"
            with open_read_only_store(path) as reader:
                assert reader.read_run(run_id).raw_claim == production.CLAIM
                proceed.set()
                # Real rollback-journal readers retain their shared lock until
                # close. This exceeds the old one-second startup writer wait.
                Event().wait(1.35)
                assert not model.requests
        finally:
            proceed.set()
        result = future.result(timeout=20)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert sum(request.stage is LLMStage.PLANNER for request in model.requests) == 1
    assert read_v2_artifact(path, run_id, "saved-source-suggestions-v1")
    requests = len(model.requests), len(search.requests)
    assert run().final_output == result.final_output
    assert (len(model.requests), len(search.requests)) == requests
    with closing(_connect(str(path))) as connection:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 1000
