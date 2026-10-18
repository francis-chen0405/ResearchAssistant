"""Run manifest, research-round/governor state and cancellation persistence."""

from __future__ import annotations

import sqlite3
from uuid import UUID

from researchassistant.contracts.models import (
    ResearchGovernorDecision,
    ResearchRoundRecord,
    ResearchRoundStatus,
    ResearchTerminalResult,
    RunCancellationRequest,
    RunManifest,
)
from researchassistant.storage.store_types import (
    DatabaseReader as DatabaseReader,
)
from researchassistant.storage.store_types import ReadConnectionFactory, WriteConnectionFactory
from researchassistant.storage.store_types import (
    _dt_to_iso as _dt_to_iso,
)
from researchassistant.storage.store_types import (
    _iso_to_dt as _iso_to_dt,
)
from researchassistant.storage.store_types import (
    _read_execute as _read_execute,
)


def insert_research_round_record(
    db_path: str, record: ResearchRoundRecord, *, _connect: WriteConnectionFactory
) -> None:
    """Append one completed or terminal research round; SQLite enforces its 1..3 bound."""
    if record.status in {ResearchRoundStatus.PLANNED, ResearchRoundStatus.RUNNING} or (
        record.completed_at is None
    ):
        raise ValueError("only completed or terminal research rounds may be persisted")
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO research_round_records
               (run_id, research_round, payload_json, completed_at) VALUES (?, ?, ?, ?)""",
            (
                str(record.run_id),
                record.research_round,
                record.model_dump_json(),
                _dt_to_iso(record.completed_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_research_round_records(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> tuple[ResearchRoundRecord, ...]:
    """Read persisted bounded rounds, returning no synthetic rows for historical runs."""
    with _read_connection(db_path) as conn:
        try:
            rows = _read_execute(
                conn,
                "SELECT payload_json FROM research_round_records WHERE run_id = ? "
                "ORDER BY research_round",
                (str(run_id),),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return ()
            raise
    return tuple(ResearchRoundRecord.model_validate_json(row["payload_json"]) for row in rows)


def insert_research_governor_decision(
    db_path: str, decision: ResearchGovernorDecision, *, _connect: WriteConnectionFactory
) -> None:
    """Append the single deterministic post-Round-2 authorization decision for a run."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO research_governor_decisions (run_id, payload_json, decided_at)
               VALUES (?, ?, ?)""",
            (
                str(decision.run_id),
                decision.model_dump_json(),
                _dt_to_iso(decision.decided_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_research_governor_decision(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> ResearchGovernorDecision | None:
    """Read the immutable Governor decision without creating one for a historical run."""
    with _read_connection(db_path) as conn:
        try:
            row = _read_execute(
                conn,
                "SELECT payload_json FROM research_governor_decisions WHERE run_id = ?",
                (str(run_id),),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
    return ResearchGovernorDecision.model_validate_json(row["payload_json"]) if row else None


def insert_research_terminal_result(
    db_path: str, result: ResearchTerminalResult, *, _connect: WriteConnectionFactory
) -> None:
    """Append the terminal evidence classification after the final permitted round."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO research_terminal_results (run_id, payload_json, finalized_at)
               VALUES (?, ?, ?)""",
            (
                str(result.run_id),
                result.model_dump_json(),
                _dt_to_iso(result.finalized_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_research_terminal_result(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> ResearchTerminalResult | None:
    """Read a persisted terminal classification without fabricating historical evidence."""
    with _read_connection(db_path) as conn:
        try:
            row = _read_execute(
                conn,
                "SELECT payload_json FROM research_terminal_results WHERE run_id = ?",
                (str(run_id),),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
    return ResearchTerminalResult.model_validate_json(row["payload_json"]) if row else None


def insert_run(db_path: str, manifest: RunManifest, *, _connect: WriteConnectionFactory) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO runs
               (run_id, status, raw_claim, current_stage, created_at, updated_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(manifest.run_id),
                manifest.status.value,
                manifest.raw_claim,
                manifest.current_stage.value,
                _dt_to_iso(manifest.created_at),
                _dt_to_iso(manifest.updated_at),
                _dt_to_iso(manifest.completed_at) if manifest.completed_at else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_run(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> RunManifest:
    with _read_connection(db_path) as conn:
        row = _read_execute(conn, "SELECT * FROM runs WHERE run_id = ?", (str(run_id),)).fetchone()
        if row is None:
            raise KeyError(f"run {run_id} not found")
        return _row_to_run(row)


def list_runs(
    db_path: DatabaseReader, *, limit: int = 100, _read_connection: ReadConnectionFactory
) -> list[RunManifest]:
    """Return the most recently updated runs for local inspection."""
    if limit < 1 or limit > 1000:
        raise ValueError("run history limit must be between 1 and 1000")
    with _read_connection(db_path) as conn:
        rows = _read_execute(
            conn,
            "SELECT * FROM runs ORDER BY updated_at DESC, run_id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_run(row) for row in rows]


def update_run(db_path: str, manifest: RunManifest, *, _connect: WriteConnectionFactory) -> None:
    """Update mutable run state while leaving insert-only evidence tables untouched."""
    conn = _connect(db_path)
    try:
        existing = conn.execute(
            "SELECT raw_claim FROM runs WHERE run_id = ?", (str(manifest.run_id),)
        ).fetchone()
        if existing is None:
            raise KeyError(f"run {manifest.run_id} not found")
        if existing["raw_claim"] != manifest.raw_claim:
            raise ValueError("raw_claim is immutable after run creation")
        cursor = conn.execute(
            """UPDATE runs
               SET status = ?, current_stage = ?, updated_at = ?, completed_at = ?
               WHERE run_id = ?""",
            (
                manifest.status.value,
                manifest.current_stage.value,
                _dt_to_iso(manifest.updated_at),
                _dt_to_iso(manifest.completed_at) if manifest.completed_at else None,
                str(manifest.run_id),
            ),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"run {manifest.run_id} not found")
        conn.commit()
    finally:
        conn.close()


def _row_to_run(row: sqlite3.Row) -> RunManifest:
    completed = _iso_to_dt(row["completed_at"]) if row["completed_at"] else None
    return RunManifest(
        run_id=UUID(row["run_id"]),
        status=row["status"],
        raw_claim=row["raw_claim"],
        current_stage=row["current_stage"],
        created_at=_iso_to_dt(row["created_at"]),
        updated_at=_iso_to_dt(row["updated_at"]),
        completed_at=completed,
    )


def insert_cancellation_request(
    db_path: str,
    request: RunCancellationRequest,
    *,
    _connect: WriteConnectionFactory,
    _read_connection: ReadConnectionFactory,
) -> RunCancellationRequest:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO run_cancellations (run_id, requested_at, reason)
               VALUES (?, ?, ?)""",
            (str(request.run_id), _dt_to_iso(request.requested_at), request.reason),
        )
        conn.commit()
    finally:
        conn.close()
    return read_cancellation_request(db_path, request.run_id, _read_connection=_read_connection)


def read_cancellation_request(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> RunCancellationRequest:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT * FROM run_cancellations WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"cancellation request for run {run_id} not found")
        return RunCancellationRequest(
            run_id=UUID(row["run_id"]),
            requested_at=_iso_to_dt(row["requested_at"]),
            reason=row["reason"],
        )
