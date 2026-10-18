"""Frozen provider run contracts and durable historical stage checkpoints."""

from __future__ import annotations

import sqlite3
from uuid import UUID

from researchassistant.contracts.models import (
    OrchestrationCheckpoint,
    PersistedStageArtifact,
    ProviderRunContract,
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


def insert_provider_run_contract(
    db_path: str, contract: ProviderRunContract, *, _connect: WriteConnectionFactory
) -> None:
    """Insert one immutable provider compatibility contract or verify exact identity."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM provider_run_contracts WHERE run_id = ?",
            (str(contract.run_id),),
        ).fetchone()
        if row is not None:
            existing = _row_to_provider_run_contract(row)
            if existing != contract:
                raise sqlite3.IntegrityError(
                    f"provider run contract for {contract.run_id} is immutable"
                )
            return
        conn.execute(
            """INSERT INTO provider_run_contracts
               (run_id, fingerprint_sha256, provider_identity, adapter_identity,
                model_identity, prompt_identity, schema_identity,
                normalization_identity, policy_identity, repository_revision,
                payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(contract.run_id),
                contract.fingerprint_sha256,
                contract.provider_identity,
                contract.adapter_identity,
                contract.model_identity,
                contract.prompt_identity,
                contract.schema_identity,
                contract.normalization_identity,
                contract.policy_identity,
                contract.repository_revision,
                contract.payload_json,
                _dt_to_iso(contract.created_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_provider_run_contract(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> ProviderRunContract:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT * FROM provider_run_contracts WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"provider run contract for {run_id} not found")
        return _row_to_provider_run_contract(row)


def _row_to_provider_run_contract(row: sqlite3.Row) -> ProviderRunContract:
    return ProviderRunContract(
        run_id=UUID(row["run_id"]),
        fingerprint_sha256=row["fingerprint_sha256"],
        provider_identity=row["provider_identity"],
        adapter_identity=row["adapter_identity"],
        model_identity=row["model_identity"],
        prompt_identity=row["prompt_identity"],
        schema_identity=row["schema_identity"],
        normalization_identity=row["normalization_identity"],
        policy_identity=row["policy_identity"],
        repository_revision=row["repository_revision"],
        payload_json=row["payload_json"],
        created_at=_iso_to_dt(row["created_at"]),
    )


def upsert_orchestration_checkpoint(
    db_path: str, checkpoint: OrchestrationCheckpoint, *, _connect: WriteConnectionFactory
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO orchestration_checkpoints
               (run_id, stage_key, status, failure_reason, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(run_id, stage_key) DO UPDATE SET
                   status = excluded.status,
                   failure_reason = excluded.failure_reason,
                   updated_at = excluded.updated_at""",
            (
                str(checkpoint.run_id),
                checkpoint.stage_key,
                checkpoint.status.value,
                checkpoint.failure_reason,
                _dt_to_iso(checkpoint.updated_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_orchestration_checkpoint(
    db_path: DatabaseReader,
    run_id: UUID,
    stage_key: str,
    *,
    _read_connection: ReadConnectionFactory,
) -> OrchestrationCheckpoint:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            """SELECT * FROM orchestration_checkpoints
               WHERE run_id = ? AND stage_key = ?""",
            (str(run_id), stage_key),
        ).fetchone()
        if row is None:
            raise KeyError(f"checkpoint {stage_key} for run {run_id} not found")
        return OrchestrationCheckpoint(
            run_id=UUID(row["run_id"]),
            stage_key=row["stage_key"],
            status=row["status"],
            failure_reason=row["failure_reason"],
            updated_at=_iso_to_dt(row["updated_at"]),
        )


def read_orchestration_checkpoints(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> list[OrchestrationCheckpoint]:
    with _read_connection(db_path) as conn:
        rows = _read_execute(
            conn,
            """SELECT * FROM orchestration_checkpoints
               WHERE run_id = ? ORDER BY updated_at, stage_key""",
            (str(run_id),),
        ).fetchall()
        return [
            OrchestrationCheckpoint(
                run_id=UUID(row["run_id"]),
                stage_key=row["stage_key"],
                status=row["status"],
                failure_reason=row["failure_reason"],
                updated_at=_iso_to_dt(row["updated_at"]),
            )
            for row in rows
        ]


def insert_stage_artifact(
    db_path: str, artifact: PersistedStageArtifact, *, _connect: WriteConnectionFactory
) -> None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """SELECT * FROM orchestration_stage_artifacts
               WHERE run_id = ? AND artifact_key = ?""",
            (str(artifact.run_id), artifact.artifact_key),
        ).fetchone()
        if row is not None:
            existing = _row_to_stage_artifact(row)
            if (
                existing.artifact_type != artifact.artifact_type
                or existing.payload_json != artifact.payload_json
            ):
                raise sqlite3.IntegrityError(
                    f"stage artifact {artifact.artifact_key} already exists with different data"
                )
            return
        conn.execute(
            """INSERT INTO orchestration_stage_artifacts
               (run_id, artifact_key, artifact_type, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(artifact.run_id),
                artifact.artifact_key,
                artifact.artifact_type,
                artifact.payload_json,
                _dt_to_iso(artifact.created_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_stage_artifact(
    db_path: DatabaseReader,
    run_id: UUID,
    artifact_key: str,
    *,
    _read_connection: ReadConnectionFactory,
) -> PersistedStageArtifact:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            """SELECT * FROM orchestration_stage_artifacts
               WHERE run_id = ? AND artifact_key = ?""",
            (str(run_id), artifact_key),
        ).fetchone()
        if row is None:
            raise KeyError(f"stage artifact {artifact_key} for run {run_id} not found")
        return _row_to_stage_artifact(row)


def _row_to_stage_artifact(row: sqlite3.Row) -> PersistedStageArtifact:
    return PersistedStageArtifact(
        run_id=UUID(row["run_id"]),
        artifact_key=row["artifact_key"],
        artifact_type=row["artifact_type"],
        payload_json=row["payload_json"],
        created_at=_iso_to_dt(row["created_at"]),
    )
