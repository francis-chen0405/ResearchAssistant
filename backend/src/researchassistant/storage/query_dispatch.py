"""Read-only distinction between dispatched unknown calls and guarded query actions."""

from __future__ import annotations

import sqlite3
from typing import Literal
from uuid import UUID

from researchassistant.contracts.discovery_v2 import V2ExpansionResult
from researchassistant.contracts.query_retrieval import V2QueryRetrievalResult
from researchassistant.storage.discovery_store import (
    _all_run_artifacts,
    _provider_audit_from_artifacts,
    _unknown_request_outcome,
)
from researchassistant.storage.store import (
    DatabaseReader,
    _read_connection,
    _row_to_v2_artifact,
    read_snapshot_connection,
)


def query_dispatch_states(
    source: DatabaseReader, run_id: UUID
) -> dict[UUID, Literal["unknown", "blocked"]]:
    """Classify only states established by durable attempts and retrieval receipts."""
    with _read_connection(source) as conn, read_snapshot_connection(conn):
        artifacts = _all_run_artifacts(conn, run_id)
        audit = _provider_audit_from_artifacts(artifacts, run_id)
        started = {item.operation_id for item in audit.starts}
        states: dict[UUID, Literal["unknown", "blocked"]] = {
            start.operation_id: "unknown"
            for start, completion in zip(audit.starts, audit.completions, strict=True)
            if _unknown_request_outcome(completion)
        }
        rows = conn.execute(
            "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_type IN "
            "('V2ExpansionResult', 'V2QueryRetrievalResult') ORDER BY artifact_key LIMIT 6001",
            (str(run_id),),
        ).fetchall()
        if len(rows) > 6000:
            raise sqlite3.IntegrityError("query dispatch receipt inventory exceeds reader bound")
        for row in rows:
            artifact = _row_to_v2_artifact(row)
            if artifact.artifact_type == "V2ExpansionResult":
                result = V2ExpansionResult.model_validate_json(artifact.payload_json)
                if result.run_id != run_id:
                    raise ValueError("expansion dispatch receipt belongs to another run")
                if (
                    result.status == "interrupted_unknown"
                    and result.action.artifact_id not in started
                    and audit.interrupted_unknown
                ):
                    states[result.action.artifact_id] = "blocked"
                continue
            if artifact.artifact_type != "V2QueryRetrievalResult":
                continue
            result = V2QueryRetrievalResult.model_validate_json(artifact.payload_json)
            if result.run_id != run_id:
                raise ValueError("query dispatch receipt belongs to another run")
            if (
                result.stopping_reason == "unknown_outcome"
                and result.operation_id not in started
                and audit.interrupted_unknown
            ):
                states[result.operation_id] = "blocked"
        return states
