"""Retained Reviewer paths reuse validated committed decisions and admissions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import test_v2_phase10_reviewer_ledger as bridge
from test_v2_checkpoint_resume import _saved_rows

import researchassistant.agents.v2_reviewer_ledger as reviewer
from researchassistant.agents.v2_evidence_analyst import run_v2_evidence_analyst
from researchassistant.contracts.models import V2ReviewerLedgerSourceResult
from researchassistant.storage import v2_transactions
from researchassistant.storage.store import (
    insert_v2_ledger_admission,
    read_v2_ledger_admission,
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
