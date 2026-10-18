"""V2 immutable aggregates and their atomic relational projections."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from uuid import UUID

from researchassistant.contracts.models import (
    V2_PIPELINE_IDENTITY,
    V2_POLICY_IDENTITY,
    LedgerRecord,
    RunStatus,
    Stage,
    StrictModel,
    V2EvidenceAdmissionRecord,
    V2EvidenceAdmissionSourceResult,
    V2EvidenceAdmissionState,
    V2InitialPlannerOutput,
    V2LedgerProvenance,
    V2PersistedArtifact,
    V2PipelineIdentity,
    V2ReviewerLedgerSourceResult,
    canonical_v2_artifact_json,
    v2_artifact_fingerprint,
    v2_payload_fingerprint,
)
from researchassistant.contracts.provider_contract import parse_provider_contract_payload
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
from researchassistant.storage.store_types import (
    _require_aware_datetime as _require_aware_datetime,
)


def insert_v2_pipeline_identity(
    db_path: str,
    run_id: UUID,
    identity: V2PipelineIdentity,
    created_at: datetime,
    *,
    _connect: WriteConnectionFactory,
) -> None:
    """Explicitly identify a new run as v2; historical provider contracts cannot be relabeled."""
    _require_aware_datetime(created_at, "created_at")
    conn = _connect(db_path)
    try:
        contract = conn.execute(
            "SELECT policy_identity, payload_json FROM provider_run_contracts WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        if contract is not None and contract["policy_identity"] != V2_POLICY_IDENTITY:
            payload = parse_provider_contract_payload(contract["payload_json"])
            if not payload["fingerprint_version"].startswith("researchassistant-v2-"):
                raise ValueError("a pre-v2 provider run cannot be resumed as a v2 run")
        existing = conn.execute(
            "SELECT * FROM v2_run_identities WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if existing is not None:
            if (
                existing["pipeline_identity"] != identity.pipeline_identity
                or existing["policy_identity"] != identity.policy_identity
            ):
                raise sqlite3.IntegrityError("v2 run identity already exists with different data")
            return
        conn.execute(
            """INSERT INTO v2_run_identities
               (run_id, pipeline_identity, policy_identity, created_at) VALUES (?, ?, ?, ?)""",
            (
                str(run_id),
                identity.pipeline_identity,
                identity.policy_identity,
                _dt_to_iso(created_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_v2_artifact(
    db_path: str,
    artifact_key: str,
    artifact: StrictModel,
    created_at: datetime,
    *,
    _connect: WriteConnectionFactory,
) -> V2PersistedArtifact:
    """Persist a canonical v2 artifact once, refusing a missing v2 identity or drift."""
    conn = _connect(db_path)
    try:
        persisted = _insert_v2_artifact_on_connection(conn, artifact_key, artifact, created_at)
        conn.commit()
        return persisted
    finally:
        conn.close()


def insert_v2_artifact_batch(
    db_path: str,
    artifacts: tuple[tuple[str, StrictModel, datetime], ...],
    *,
    _connect: WriteConnectionFactory,
) -> tuple[V2PersistedArtifact, ...]:
    """Commit one run's mutually dependent immutable artifacts together."""
    if not artifacts or len({getattr(item, "run_id", None) for _, item, _ in artifacts}) != 1:
        raise ValueError("an artifact batch requires nonempty same-run artifacts")
    conn = _connect(db_path)
    try:
        persisted = tuple(
            _insert_v2_artifact_on_connection(conn, key, artifact, created_at)
            for key, artifact, created_at in artifacts
        )
        conn.commit()
        return persisted
    finally:
        conn.close()


def _insert_v2_artifact_on_connection(
    conn: sqlite3.Connection,
    artifact_key: str,
    artifact: StrictModel,
    created_at: datetime,
) -> V2PersistedArtifact:
    """Apply the existing immutable artifact checks within the caller's transaction."""
    from researchassistant.contracts.historical import HistoricalRead

    if isinstance(artifact, HistoricalRead):
        raise ValueError("historical inspection values cannot be admitted as new artifacts")
    if not artifact_key:
        raise ValueError("artifact_key must not be empty")
    _require_aware_datetime(created_at, "created_at")
    run_id = getattr(artifact, "run_id", None)
    if not isinstance(run_id, UUID):
        raise ValueError("v2 artifacts must carry a UUID run_id")
    artifact_type = type(artifact).__name__
    if not (
        artifact_type.startswith("V2")
        or artifact_type
        in {
            "ScoutBatch",
            "ProbeResult",
            "GapAnalysisResult",
            "SurvivingSourceRecord",
            "SourceRecommendationResult",
            "DeepAnalysisStatus",
        }
    ):
        raise ValueError("only v2 artifact schemas may be persisted through the v2 boundary")
    payload_json = canonical_v2_artifact_json(artifact)
    payload_sha256 = v2_artifact_fingerprint(artifact)
    persisted = V2PersistedArtifact(
        run_id=run_id,
        artifact_key=artifact_key,
        artifact_type=artifact_type,
        payload_json=payload_json,
        payload_sha256=payload_sha256,
        created_at=created_at,
    )
    identity = conn.execute(
        "SELECT pipeline_identity, policy_identity FROM v2_run_identities WHERE run_id = ?",
        (str(run_id),),
    ).fetchone()
    if identity is None:
        raise ValueError("v2 artifacts require an explicit v2 run identity")
    if (
        identity["pipeline_identity"] != V2_PIPELINE_IDENTITY
        or identity["policy_identity"] != V2_POLICY_IDENTITY
    ):
        raise ValueError("v2 run identity is incompatible with this pipeline")
    existing = conn.execute(
        "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
        (str(run_id), artifact_key),
    ).fetchone()
    if existing is not None:
        restored = _row_to_v2_artifact(existing)
        if restored != persisted:
            raise sqlite3.IntegrityError(
                f"v2 artifact {artifact_key} already exists with different data"
            )
        return restored
    conn.execute(
        """INSERT INTO v2_artifacts
           (run_id, artifact_key, artifact_type, payload_json, payload_sha256, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            str(persisted.run_id),
            persisted.artifact_key,
            persisted.artifact_type,
            persisted.payload_json,
            persisted.payload_sha256,
            _dt_to_iso(persisted.created_at),
        ),
    )
    return persisted


def insert_v2_terminal_artifact(
    db_path: str,
    artifact_key: str,
    artifact: StrictModel,
    completed_at: datetime,
    status: RunStatus,
    stage: Stage,
    *,
    _connect: WriteConnectionFactory,
) -> V2PersistedArtifact:
    """Commit an immutable terminal artifact and its mutable run manifest together."""
    if status not in {
        RunStatus.COMPLETED,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    }:
        raise ValueError("a terminal artifact requires a terminal run status")
    _require_aware_datetime(completed_at, "completed_at")
    run_id = getattr(artifact, "run_id", None)
    raw_claim = getattr(artifact, "raw_claim", None)
    if not isinstance(run_id, UUID) or not isinstance(raw_claim, str):
        raise ValueError("terminal artifact requires a run ID and claim")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        persisted = _insert_v2_artifact_on_connection(conn, artifact_key, artifact, completed_at)
        current = conn.execute(
            "SELECT raw_claim, status, current_stage, completed_at FROM runs WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        if current is None:
            raise KeyError(f"run {run_id} not found")
        if current["raw_claim"] != raw_claim:
            raise ValueError("terminal artifact claim differs from immutable run claim")
        if (
            current["status"] != status.value
            or current["current_stage"] != stage.value
            or current["completed_at"] is None
        ):
            conn.execute(
                """UPDATE runs SET status = ?, current_stage = ?, updated_at = ?,
                   completed_at = ? WHERE run_id = ?""",
                (
                    status.value,
                    stage.value,
                    _dt_to_iso(completed_at),
                    _dt_to_iso(completed_at),
                    str(run_id),
                ),
            )
        conn.commit()
        return persisted
    finally:
        conn.close()


def read_v2_artifact(
    db_path: DatabaseReader,
    run_id: UUID,
    artifact_key: str,
    *,
    _read_connection: ReadConnectionFactory,
) -> V2PersistedArtifact:
    """Read a persisted v2 envelope without converting it into a mutable handoff."""
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
            (str(run_id), artifact_key),
        ).fetchone()
        if row is None:
            raise KeyError(f"v2 artifact {artifact_key} for run {run_id} not found")
        return _row_to_v2_artifact(row)


def read_v2_physical_call_artifacts(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> tuple[V2PersistedArtifact, ...]:
    """Read every current or legacy physical-call envelope in one query."""
    with _read_connection(db_path) as conn:
        rows = _read_execute(
            conn,
            """SELECT * FROM v2_artifacts
               WHERE run_id = ?
                 AND (
                     artifact_key LIKE 'phase-13-physical-call-%'
                     OR artifact_key LIKE 'phase-12-physical-call-%'
                 )
               ORDER BY artifact_key
               LIMIT 641""",
            (str(run_id),),
        ).fetchall()
        if len(rows) > 640:
            raise sqlite3.IntegrityError("v2 physical-call audit exceeds its bounded row count")
        return tuple(_row_to_v2_artifact(row) for row in rows)


def insert_v2_ledger_admission(
    db_path: str,
    record: LedgerRecord,
    provenance: V2LedgerProvenance,
    *,
    _connect: WriteConnectionFactory,
) -> None:
    """Append one v2-approved Ledger record with immutable discovery provenance."""
    conn = _connect(db_path)
    try:
        _insert_v2_ledger_admission_on_connection(conn, record, provenance)
        conn.commit()
    finally:
        conn.close()


def insert_v2_ledger_admission_checkpoint(
    db_path: str,
    artifact_key: str,
    source_result: V2ReviewerLedgerSourceResult,
    created_at: datetime,
    *,
    _connect: WriteConnectionFactory,
) -> None:
    """Commit a historical Reviewer source checkpoint with its exact admission."""
    record = source_result.ledger_record
    if record is None or record.run_id != source_result.run_id:
        raise ValueError("Reviewer admission checkpoints require an owned Ledger record")
    conn = _connect(db_path)
    try:
        _insert_v2_ledger_admission_on_connection(conn, record, source_result.provenance)
        _insert_v2_artifact_on_connection(conn, artifact_key, source_result, created_at)
        conn.commit()
    finally:
        conn.close()


def _insert_v2_ledger_admission_on_connection(
    conn: sqlite3.Connection, record: LedgerRecord, provenance: V2LedgerProvenance
) -> None:
    record = LedgerRecord.model_validate(record.model_dump())
    record_json = record.model_dump_json()
    provenance_json = provenance.model_dump_json()
    identity = conn.execute(
        "SELECT pipeline_identity FROM v2_run_identities WHERE run_id = ?",
        (str(record.run_id),),
    ).fetchone()
    if identity is None or identity["pipeline_identity"] != V2_PIPELINE_IDENTITY:
        raise ValueError("v2 Ledger admissions require an explicit v2 run identity")
    existing = conn.execute(
        "SELECT ledger_record_json, provenance_json FROM v2_ledger_admissions "
        "WHERE ledger_claim_id = ?",
        (str(record.ledger_claim_id),),
    ).fetchone()
    if existing is not None:
        if (
            existing["ledger_record_json"] != record_json
            or existing["provenance_json"] != provenance_json
        ):
            raise sqlite3.IntegrityError("v2 Ledger admission is immutable")
        return
    conn.execute(
        """INSERT INTO v2_ledger_admissions
           (ledger_claim_id, run_id, source_id, research_direction, discovery_round,
            source_family_id, recommended, relevant_gap_ids_json, ledger_record_json,
            provenance_json, admitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(record.ledger_claim_id),
            str(record.run_id),
            str(provenance.source_id),
            provenance.research_direction.value,
            provenance.discovery_round,
            provenance.source_family_id,
            int(provenance.recommended),
            json.dumps(provenance.relevant_gap_ids, ensure_ascii=False, separators=(",", ":")),
            record_json,
            provenance_json,
            _dt_to_iso(record.ledger_validated_at),
        ),
    )


def read_v2_ledger_admission(
    db_path: DatabaseReader, ledger_claim_id: UUID, *, _read_connection: ReadConnectionFactory
) -> tuple[LedgerRecord, V2LedgerProvenance]:
    """Read one immutable v2 Ledger admission and its separate provenance context."""
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT ledger_record_json, provenance_json FROM v2_ledger_admissions "
            "WHERE ledger_claim_id = ?",
            (str(ledger_claim_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"v2 Ledger admission {ledger_claim_id} not found")
        return (
            LedgerRecord.model_validate_json(row["ledger_record_json"]),
            V2LedgerProvenance.model_validate_json(row["provenance_json"]),
        )


def insert_v2_evidence_admission(
    db_path: str,
    record: V2EvidenceAdmissionRecord,
    provenance: V2LedgerProvenance,
    *,
    _connect: WriteConnectionFactory,
) -> None:
    """Append one immutable analyzer-admitted evidence record."""
    conn = _connect(db_path)
    try:
        _insert_v2_evidence_admission_on_connection(conn, record, provenance)
        conn.commit()
    finally:
        conn.close()


def insert_v2_evidence_admission_checkpoint(
    db_path: str,
    artifact_key: str,
    source_result: V2EvidenceAdmissionSourceResult,
    created_at: datetime,
    *,
    _connect: WriteConnectionFactory,
) -> None:
    """Commit a source checkpoint with its immutable relational admission."""
    source_result = V2EvidenceAdmissionSourceResult.model_validate(source_result.model_dump())
    record = source_result.evidence_record
    if record is None or source_result.state is not V2EvidenceAdmissionState.ANALYZER_ADMITTED:
        raise ValueError("atomic evidence checkpoints require an admitted source")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _insert_v2_evidence_admission_on_connection(conn, record, source_result.provenance)
        _insert_v2_artifact_on_connection(conn, artifact_key, source_result, created_at)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _insert_v2_evidence_admission_on_connection(
    conn: sqlite3.Connection,
    record: V2EvidenceAdmissionRecord,
    provenance: V2LedgerProvenance,
) -> None:
    """Validate and append admission within its caller's transaction."""
    if record.admission_method.value != "analyzer_admitted":
        raise ValueError("fresh evidence admissions must use analyzer_admitted")
    record_json = record.model_dump_json()
    provenance_json = provenance.model_dump_json()
    identity = conn.execute(
        "SELECT pipeline_identity FROM v2_run_identities WHERE run_id = ?",
        (str(record.run_id),),
    ).fetchone()
    if identity is None or identity["pipeline_identity"] != V2_PIPELINE_IDENTITY:
        raise ValueError("v2 evidence admissions require an explicit v2 run identity")
    existing = conn.execute(
        "SELECT ledger_record_json, provenance_json FROM v2_ledger_admissions "
        "WHERE ledger_claim_id = ?",
        (str(record.ledger_claim_id),),
    ).fetchone()
    if existing is not None:
        if (
            existing["ledger_record_json"] != record_json
            or existing["provenance_json"] != provenance_json
        ):
            raise sqlite3.IntegrityError("v2 evidence admission is immutable")
        return
    conn.execute(
        """INSERT INTO v2_ledger_admissions
           (ledger_claim_id, run_id, source_id, research_direction, discovery_round,
            source_family_id, recommended, relevant_gap_ids_json, ledger_record_json,
            provenance_json, admitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(record.ledger_claim_id),
            str(record.run_id),
            str(provenance.source_id),
            provenance.research_direction.value,
            provenance.discovery_round,
            provenance.source_family_id,
            int(provenance.recommended),
            json.dumps(provenance.relevant_gap_ids, ensure_ascii=False, separators=(",", ":")),
            record_json,
            provenance_json,
            _dt_to_iso(record.ledger_validated_at),
        ),
    )


def read_v2_evidence_admission(
    db_path: DatabaseReader, ledger_claim_id: UUID, *, _read_connection: ReadConnectionFactory
) -> tuple[V2EvidenceAdmissionRecord, V2LedgerProvenance]:
    """Read one immutable analyzer admission and its discovery provenance."""
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT ledger_record_json, provenance_json FROM v2_ledger_admissions "
            "WHERE ledger_claim_id = ?",
            (str(ledger_claim_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"v2 evidence admission {ledger_claim_id} not found")
        return (
            V2EvidenceAdmissionRecord.model_validate_json(row["ledger_record_json"]),
            V2LedgerProvenance.model_validate_json(row["provenance_json"]),
        )


def insert_v2_initial_planner_output(
    db_path: str,
    output: V2InitialPlannerOutput,
    *,
    _connect: WriteConnectionFactory,
    _read_connection: ReadConnectionFactory,
) -> None:
    """Append one validated fresh-v2 initial plan and exactly its Round-1 search queries."""
    conn = _connect(db_path)
    try:
        identity = conn.execute(
            "SELECT pipeline_identity FROM v2_run_identities WHERE run_id = ?",
            (str(output.run_id),),
        ).fetchone()
        if identity is None or identity["pipeline_identity"] != V2_PIPELINE_IDENTITY:
            raise ValueError("v2 initial planner output requires an explicit v2 run identity")
        existing = conn.execute(
            "SELECT run_id FROM v2_initial_planner_outputs WHERE run_id = ?", (str(output.run_id),)
        ).fetchone()
        if existing is not None:
            if (
                read_v2_initial_planner_output(
                    db_path, output.run_id, _read_connection=_read_connection
                )
                != output
            ):
                raise sqlite3.IntegrityError("v2 initial planner output is immutable")
            return
        conn.execute("BEGIN IMMEDIATE")
        artifact_row = conn.execute(
            "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
            (str(output.run_id), "phase-3-initial-round-1-plan"),
        ).fetchone()
        if artifact_row is not None:
            artifact = _row_to_v2_artifact(artifact_row)
            if (
                artifact.artifact_type != type(output).__name__
                or V2InitialPlannerOutput.model_validate_json(artifact.payload_json) != output
                or artifact.created_at != output.planned_at
            ):
                raise sqlite3.IntegrityError("Initial planner artifact disagrees with new queries")
        conn.execute(
            """INSERT INTO v2_initial_planner_outputs
               (run_id, raw_claim, directions_json, discovery_providers_json, policy_identity,
                scope_interpretations_json, planner_prompt_version, planner_model_name, planned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(output.run_id),
                output.raw_claim,
                json.dumps(
                    output.directions.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps([provider.value for provider in output.discovery_providers]),
                output.policy_identity,
                json.dumps(
                    [item.model_dump(mode="json") for item in output.scope_interpretations],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                output.planner_prompt_version,
                output.planner_model_name,
                _dt_to_iso(output.planned_at),
            ),
        )
        for search in output.searches:
            conn.execute(
                """INSERT INTO v2_round_one_search_queries
                   (query_id, run_id, direction, provider, round_number, strategy, query_text,
                    policy_identity, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(search.query_id),
                    str(search.run_id),
                    search.direction.value,
                    search.provider.value,
                    search.round_number,
                    search.strategy,
                    search.query_text,
                    search.policy_identity,
                    _dt_to_iso(search.created_at),
                ),
            )
        # Keep the complete typed handoff in the same transaction as its relational
        # projection. Coverage and compiled-query fields have no historical columns.
        if artifact_row is None:
            conn.execute(
                """INSERT INTO v2_artifacts
                   (run_id, artifact_key, artifact_type, payload_json, payload_sha256, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(output.run_id),
                    "phase-3-initial-round-1-plan",
                    type(output).__name__,
                    canonical_v2_artifact_json(output),
                    v2_artifact_fingerprint(output),
                    _dt_to_iso(output.planned_at),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def read_v2_initial_planner_output(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> V2InitialPlannerOutput:
    """Reconstruct a typed fresh-v2 Round-1 plan without creating later-round searches."""
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn, "SELECT * FROM v2_initial_planner_outputs WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"v2 initial planner output for run {run_id} not found")
        searches = _read_execute(
            conn,
            "SELECT * FROM v2_round_one_search_queries WHERE run_id = ? ORDER BY rowid",
            (str(run_id),),
        ).fetchall()
        relational = V2InitialPlannerOutput.model_validate(
            {
                "run_id": run_id,
                "raw_claim": row["raw_claim"],
                "directions": json.loads(row["directions_json"]),
                "discovery_providers": json.loads(row["discovery_providers_json"]),
                "policy_identity": row["policy_identity"],
                "scope_interpretations": json.loads(row["scope_interpretations_json"]),
                "searches": [
                    {
                        "run_id": item["run_id"],
                        "query_id": item["query_id"],
                        "direction": item["direction"],
                        "provider": item["provider"],
                        "round_number": item["round_number"],
                        "strategy": item["strategy"],
                        "query_text": item["query_text"],
                        "policy_identity": item["policy_identity"],
                        "created_at": _iso_to_dt(item["created_at"]),
                    }
                    for item in searches
                ],
                "planner_prompt_version": row["planner_prompt_version"],
                "planner_model_name": row["planner_model_name"],
                "planned_at": _iso_to_dt(row["planned_at"]),
            }
        )
        artifact_row = _read_execute(
            conn,
            "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
            (str(run_id), "phase-3-initial-round-1-plan"),
        ).fetchone()
        if artifact_row is None:
            return relational
        complete = V2InitialPlannerOutput.model_validate_json(
            _row_to_v2_artifact(artifact_row).payload_json
        )
        projection = complete.model_copy(
            update={
                "claim_coverage_focus": (),
                "searches": tuple(
                    query.model_copy(update={"compiled_query": None}) for query in complete.searches
                ),
            }
        )
        if projection != relational:
            raise sqlite3.IntegrityError("Initial planner artifact disagrees with stored queries")
        return complete


def _row_to_v2_artifact(row: sqlite3.Row) -> V2PersistedArtifact:
    payload_json = row["payload_json"]
    payload_sha256 = row["payload_sha256"]
    if not isinstance(payload_json, str) or not isinstance(payload_sha256, str):
        raise sqlite3.IntegrityError("v2 artifact payload integrity data is not valid text")
    expected_sha256 = v2_payload_fingerprint(payload_json)
    if payload_sha256 != expected_sha256:
        raise sqlite3.IntegrityError(f"v2 artifact {row['artifact_key']} payload SHA-256 mismatch")
    payload = json.loads(payload_json)
    if isinstance(payload, dict) and "run_id" in payload:
        try:
            owner = UUID(payload["run_id"])
        except (ValueError, TypeError, AttributeError):
            raise sqlite3.IntegrityError("v2 artifact payload has an invalid run owner") from None
        if owner != UUID(row["run_id"]):
            raise sqlite3.IntegrityError(
                "v2 artifact payload belongs to another run than its envelope"
            )
    return V2PersistedArtifact(
        run_id=UUID(row["run_id"]),
        artifact_key=row["artifact_key"],
        artifact_type=row["artifact_type"],
        payload_json=payload_json,
        payload_sha256=payload_sha256,
        created_at=_iso_to_dt(row["created_at"]),
    )
