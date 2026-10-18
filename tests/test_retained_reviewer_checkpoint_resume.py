"""Retained Reviewer paths reuse validated committed decisions and admissions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import test_phase9 as native
import test_v2_phase10_reviewer_ledger as bridge
from test_v2_checkpoint_resume import _saved_rows

import researchassistant.agents.v2_reviewer_ledger as reviewer
import researchassistant.research.historical_execution as history
from researchassistant.agents.v2_evidence_analyst import run_v2_evidence_analyst
from researchassistant.contracts.models import V2ReviewerLedgerSourceResult
from researchassistant.storage import v2_transactions
from researchassistant.storage.store import (
    insert_v2_ledger_admission,
    read_ledger_record,
    read_statement_review,
    read_v2_ledger_admission,
)


@pytest.mark.parametrize("boundary", ["insert_statement_review", "insert_ledger_record"])
def test_native_reviewer_or_ledger_prefix_preserves_original_time_and_provider_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    path = tmp_path / "generated.sqlite3"
    run_id = uuid4()
    original = getattr(history, boundary)
    captured = []

    def interrupt(*args: Any, **kwargs: Any) -> object:
        original(*args, **kwargs)
        captured.append(args[1])
        raise KeyboardInterrupt("generated native admission prefix")

    def run(model: native.FakeLLMProvider) -> native.ProviderPipelineResult:
        return history.run_provider_pipeline(
            "The fixture policy improves student outcomes.",
            db_path=path,
            search_provider=native.FakeSearchProvider(),
            scraper_provider=native.FakeScraperProvider(),
            llm_provider=model,
            run_id=run_id,
            clock=lambda: datetime.now(UTC),
        )

    monkeypatch.setattr(history, boundary, interrupt)
    with pytest.raises(KeyboardInterrupt):
        run(native.FakeLLMProvider())
    monkeypatch.setattr(history, boundary, original)
    before = _saved_rows(path)
    model = native.FakeLLMProvider()
    resumed = run(model)
    assert resumed.status is native.ProviderRunStatus.RELEASED, resumed.failure_reason
    assert {key: _saved_rows(path)[key] for key in before} == before
    saved = captured[0]
    if boundary == "insert_statement_review":
        assert read_statement_review(path, run_id, saved.statement_draft_id) == saved
    else:
        assert read_ledger_record(path, saved.ledger_claim_id) == saved
    assert not any(
        saved.quote_block_id in request.input_artifact_ids
        for request in model.requests
        if request.stage.value in {"analyst", "reviewer"}
    )


@pytest.mark.parametrize("legacy_prefix", [False, True])
def test_historical_bridge_preserves_relational_admission_on_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy_prefix: bool
) -> None:
    run_id = uuid4()
    path = bridge._prepare_db(tmp_path, run_id)
    provider = bridge.Phase10Provider([bridge._approved()])
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=bridge._batch_input(run_id),
        llm_provider=provider,
        routing_config=bridge._routing(),
        clock=lambda: bridge.NOW,
    )
    original = reviewer.insert_v2_ledger_admission_checkpoint
    captured = []

    def interrupt(
        database: str, key: str, source: V2ReviewerLedgerSourceResult, when: datetime
    ) -> None:
        captured.append(source)
        if legacy_prefix:
            insert_v2_ledger_admission(database, source.ledger_record, source.provenance)
        else:
            original(database, key, source, when)
        raise KeyboardInterrupt("generated historical admission prefix")

    monkeypatch.setattr(reviewer, "insert_v2_ledger_admission_checkpoint", interrupt)
    with pytest.raises(KeyboardInterrupt):
        reviewer.run_v2_reviewer_ledger(
            db_path=path,
            analyst_result=analyst,
            llm_provider=provider,
            routing_config=bridge._routing(),
            clock=lambda: datetime.now(UTC),
        )
    monkeypatch.setattr(reviewer, "insert_v2_ledger_admission_checkpoint", original)
    record = captured[0].ledger_record
    assert record is not None
    saved = read_v2_ledger_admission(path, record.ledger_claim_id)
    before = _saved_rows(Path(path))
    replay = bridge.Phase10Provider([])
    result = reviewer.run_v2_reviewer_ledger(
        db_path=path,
        analyst_result=analyst,
        llm_provider=replay,
        routing_config=bridge._routing(),
        clock=lambda: datetime.now(UTC),
    )
    assert not replay.requests
    assert result.source_results[0].ledger_record == record
    assert result.source_results[0].review_results[0].reviewed_at == record.reviewed_at
    assert read_v2_ledger_admission(path, record.ledger_claim_id) == saved
    assert {key: _saved_rows(Path(path))[key] for key in before} == before


def test_bridge_checkpoint_failure_rolls_back_relational_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = uuid4()
    path = bridge._prepare_db(tmp_path, run_id)
    provider = bridge.Phase10Provider([bridge._approved()])
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=bridge._batch_input(run_id),
        llm_provider=provider,
        routing_config=bridge._routing(),
        clock=lambda: bridge.NOW,
    )
    original = v2_transactions._insert_v2_artifact_on_connection

    def fail_checkpoint(*args: Any, **kwargs: Any) -> object:
        if args[1].startswith("phase-10-reviewer-ledger-source-"):
            raise RuntimeError("generated failure before source checkpoint")
        return original(*args, **kwargs)

    monkeypatch.setattr(v2_transactions, "_insert_v2_artifact_on_connection", fail_checkpoint)
    with pytest.raises(RuntimeError, match="before source checkpoint"):
        reviewer.run_v2_reviewer_ledger(
            db_path=path,
            analyst_result=analyst,
            llm_provider=provider,
            routing_config=bridge._routing(),
            clock=lambda: bridge.NOW,
        )
    import sqlite3

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM v2_ledger_admissions").fetchone()[0] == 0
    monkeypatch.setattr(v2_transactions, "_insert_v2_artifact_on_connection", original)
    replay = bridge.Phase10Provider([])
    result = reviewer.run_v2_reviewer_ledger(
        db_path=path,
        analyst_result=analyst,
        llm_provider=replay,
        routing_config=bridge._routing(),
        clock=lambda: datetime.now(UTC),
    )
    assert result.source_results[0].ledger_record is not None
    assert not replay.requests
