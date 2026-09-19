from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from models import (
    RunManifest,
    RunStatus,
    Stage,
    V2DeepAnalysisSourceReconciliation,
    V2PipelineIdentity,
    v2_payload_fingerprint,
)
from providers.v2_budget import (
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2RunCeilings,
    _read_audit,
    _snapshot,
    read_v2_physical_call_audit,
)
from store import init_db, insert_run, insert_v2_artifact, insert_v2_pipeline_identity

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def test_source_reconciliation_releases_only_unused_allowance() -> None:
    reconciliation = V2DeepAnalysisSourceReconciliation(
        source_id=uuid4(),
        source_cap_cost_usd=Decimal("1.00"),
        accounted_tokens=12_500,
        released_tokens=47_500,
        accounted_cost_usd=Decimal("0.25"),
        released_cost_usd=Decimal("0.75"),
    )

    assert reconciliation.released_tokens == 47_500
    assert reconciliation.accounted_tokens + reconciliation.released_tokens == 60_000


def test_missing_provider_usage_remains_conservative_reservation() -> None:
    run_id = uuid4()
    start = V2PhysicalCallStart(
        run_id=run_id,
        sequence=1,
        stage="analyst",
        model_alias="gpt-5.6-luna-high",
        reserved_tokens=12_500,
        reserved_cost_usd=Decimal("0.25"),
        source_id=uuid4(),
        started_at=NOW,
    )
    completion = V2PhysicalCallCompletion(
        run_id=run_id,
        sequence=1,
        succeeded=True,
        completed_at=NOW,
    )

    snapshot = _snapshot(
        [start],
        {1: completion},
        V2RunCeilings(max_total_tokens=500_000, max_total_cost_usd=Decimal("1.00")),
    )

    assert snapshot.token_exposure == 12_500
    assert snapshot.cost_exposure_usd == Decimal("0.25")
    assert snapshot.tokens_remaining == 487_500


def _physical_audit_db(tmp_path: Path, run_id: UUID) -> str:
    path = str(tmp_path / "physical-audit.sqlite3")
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="A bounded claim.",
            current_stage=Stage.EVIDENCE_ANALYST,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), NOW)
    return path


def _start(
    run_id: UUID,
    sequence: int,
    source_id: UUID,
    *,
    stage: str = "analyst",
) -> V2PhysicalCallStart:
    return V2PhysicalCallStart(
        run_id=run_id,
        sequence=sequence,
        stage=stage,
        model_alias="gpt-5.6-luna-high",
        reserved_tokens=100 + sequence,
        reserved_cost_usd=Decimal("0.001") * sequence,
        source_id=source_id,
        started_at=NOW,
    )


def _completion(run_id: UUID, sequence: int) -> V2PhysicalCallCompletion:
    return V2PhysicalCallCompletion(
        run_id=run_id,
        sequence=sequence,
        succeeded=True,
        usage_tokens=10 + sequence,
        usage_cost_usd=Decimal("0.0001") * sequence,
        completed_at=NOW,
    )


def test_bulk_physical_audit_merges_prefixes_and_preserves_unknown_completions(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    source_a = uuid4()
    source_b = uuid4()
    path = _physical_audit_db(tmp_path, run_id)

    insert_v2_artifact(path, "phase-12-physical-call-001-start", _start(run_id, 1, source_a), NOW)
    insert_v2_artifact(
        path,
        "phase-13-physical-call-002-start",
        _start(run_id, 2, source_b, stage="extractor"),
        NOW,
    )
    insert_v2_artifact(path, "phase-12-physical-call-003-start", _start(run_id, 3, source_a), NOW)
    insert_v2_artifact(path, "phase-12-physical-call-001-completion", _completion(run_id, 1), NOW)
    insert_v2_artifact(path, "phase-12-physical-call-003-completion", _completion(run_id, 3), NOW)

    audit = read_v2_physical_call_audit(path, run_id)

    assert [start.sequence for start in audit.starts] == [1, 2, 3]
    assert [start.source_id for start in audit.starts] == [source_a, source_b, source_a]
    assert [item.sequence if item is not None else None for item in audit.completions] == [
        1,
        None,
        3,
    ]
    starts, completions = _read_audit(path, run_id)
    assert [start.sequence for start in starts] == [1, 2, 3]
    assert sorted(completions) == [1, 3]


def test_bulk_physical_audit_prefers_current_prefix_for_duplicate_sequence(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    source_id = uuid4()
    path = _physical_audit_db(tmp_path, run_id)
    legacy = _start(run_id, 1, source_id, stage="legacy")
    current = _start(run_id, 1, source_id, stage="current")
    insert_v2_artifact(path, "phase-12-physical-call-001-start", legacy, NOW)
    insert_v2_artifact(path, "phase-13-physical-call-001-start", current, NOW)

    audit = read_v2_physical_call_audit(path, run_id)

    assert audit.starts == (current,)


def test_bulk_physical_audit_rejects_non_dense_start_sequences(tmp_path: Path) -> None:
    run_id = uuid4()
    source_id = uuid4()
    path = _physical_audit_db(tmp_path, run_id)
    insert_v2_artifact(path, "phase-13-physical-call-001-start", _start(run_id, 1, source_id), NOW)
    insert_v2_artifact(path, "phase-13-physical-call-003-start", _start(run_id, 3, source_id), NOW)

    with pytest.raises(ValueError, match="dense"):
        read_v2_physical_call_audit(path, run_id)


def test_bulk_physical_audit_uses_one_select_and_validates_payload_identity(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    source_id = uuid4()
    path = _physical_audit_db(tmp_path, run_id)
    insert_v2_artifact(path, "phase-13-physical-call-001-start", _start(run_id, 1, source_id), NOW)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        from store import read_v2_physical_call_artifacts

        rows = read_v2_physical_call_artifacts(connection, run_id)
    finally:
        connection.close()

    assert len(rows) == 1
    assert sum("SELECT" in statement.upper() for statement in statements) == 1

    wrong_sequence = _start(run_id, 1, source_id)
    insert_v2_artifact(path, "phase-13-physical-call-002-start", wrong_sequence, NOW)
    with pytest.raises(ValueError, match="sequence"):
        read_v2_physical_call_audit(path, run_id)


def test_bulk_physical_audit_rejects_payload_from_another_run(tmp_path: Path) -> None:
    run_id = uuid4()
    source_id = uuid4()
    path = _physical_audit_db(tmp_path, run_id)
    wrong_run = uuid4()
    payload = _start(wrong_run, 1, source_id).model_dump_json()
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """INSERT INTO v2_artifacts
               (run_id, artifact_key, artifact_type, payload_json, payload_sha256, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(run_id),
                "phase-13-physical-call-001-start",
                "V2PhysicalCallStart",
                payload,
                v2_payload_fingerprint(payload),
                NOW.isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="run_id"):
        read_v2_physical_call_audit(path, run_id)
