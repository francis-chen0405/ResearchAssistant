"""Parsed metadata checkpoints in immutable v2_artifacts with verified request ownership."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from researchassistant.contracts.acquisition_ranking import V2DiscoveryPipelineCounters
from researchassistant.contracts.discovery_v2 import discovery_hash
from researchassistant.contracts.query_retrieval import V2QueryPageCheckpoint, V2QueryParseReceipt
from researchassistant.storage.discovery_store import provider_attempt_audit, read_discovery_binding
from researchassistant.storage.store import (
    DatabaseReader,
    _connect,
    _insert_v2_artifact_on_connection,
    _read_connection,
    read_v2_artifact,
)


def page_key(operation_id: UUID, page_number: int) -> str:
    return f"metadata-retrieval-v2:{operation_id}:page:{page_number}"


def parse_receipt_key(operation_id: UUID, page_number: int) -> str:
    return f"metadata-retrieval-v2:{operation_id}:parse:{page_number}"


def validate_page(source: DatabaseReader, page: V2QueryPageCheckpoint) -> None:
    binding = read_discovery_binding(source, page.run_id)
    if page.binding_fingerprint != binding.fingerprint:
        raise ValueError("parsed metadata checkpoint has stale binding")
    audit = provider_attempt_audit(source, page.run_id)
    pairs = {
        start.artifact_id: (start, completion)
        for start, completion in zip(audit.starts, audit.completions, strict=True)
    }
    primary_records = 0
    for attempt_id, response_hash in zip(page.attempt_ids, page.response_hashes, strict=True):
        pair = pairs.get(attempt_id)
        if pair is None:
            raise ValueError("metadata checkpoint lacks its durable physical response")
        start, completion = pair
        if (
            start.operation_id != page.operation_id
            or start.page_number != page.page_number
            or start.requested_records != page.requested_records
            or completion is None
            or completion.status != "completed"
            or completion.response_hash != response_hash
        ):
            raise ValueError("metadata checkpoint conflicts with physical request provenance")
        if start.request_kind == "primary":
            primary_records += completion.metadata_records
    if primary_records != page.raw_hits:
        raise ValueError("metadata raw-hit count differs from its completed primary response")
    try:
        envelope = read_v2_artifact(
            source, page.run_id, parse_receipt_key(page.operation_id, page.page_number)
        )
        if envelope.artifact_type != "V2QueryParseReceipt":
            raise ValueError("metadata parser receipt has conflicting artifact type")
        receipt = V2QueryParseReceipt.model_validate_json(envelope.payload_json)
    except KeyError as exc:
        raise ValueError("metadata checkpoint lacks its immutable parser receipt") from exc
    if (
        receipt.run_id != page.run_id
        or receipt.operation_id != page.operation_id
        or receipt.binding_fingerprint != page.binding_fingerprint
        or receipt.page_number != page.page_number
        or receipt.attempt_ids != page.attempt_ids
        or receipt.response_hashes != page.response_hashes
        or receipt.parsed_response_hash != discovery_hash(page.response.model_dump_json())
    ):
        raise ValueError("metadata checkpoint differs from its immutable parser receipt")


def read_pages(source: DatabaseReader, run_id: UUID) -> tuple[V2QueryPageCheckpoint, ...]:
    with _read_connection(source) as conn:
        keys = conn.execute(
            "SELECT artifact_key FROM v2_artifacts WHERE run_id=? AND artifact_type=? "
            "ORDER BY artifact_key",
            (str(run_id), "V2QueryPageCheckpoint"),
        ).fetchall()
        pages = tuple(
            V2QueryPageCheckpoint.model_validate_json(
                read_v2_artifact(conn, run_id, row[0]).payload_json
            )
            for row in keys
        )
        for page in pages:
            if page.run_id != run_id:
                raise ValueError("metadata checkpoint belongs to another run")
            validate_page(conn, page)
        return pages


def retention_headroom(source: DatabaseReader, run_id: UUID, round_number: int) -> int:
    binding = read_discovery_binding(source, run_id)
    pages = read_pages(source, run_id)
    return max(
        0,
        min(
            binding.policy.max_raw_per_run - sum(len(page.response.results) for page in pages),
            binding.policy.max_raw_per_round
            - sum(
                len(page.response.results) for page in pages if page.round_number == round_number
            ),
        ),
    )


def persist_page(path: str, page: V2QueryPageCheckpoint, created_at: datetime) -> None:
    conn = _connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        validate_page(conn, page)
        existing = read_pages(conn, page.run_id)
        if not any(
            item.operation_id == page.operation_id and item.page_number == page.page_number
            for item in existing
        ):
            if len(page.response.results) > retention_headroom(
                conn, page.run_id, page.round_number
            ):
                raise ValueError("parsed page exceeds frozen retention headroom")
        _insert_v2_artifact_on_connection(
            conn, page_key(page.operation_id, page.page_number), page, created_at
        )
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def raw_hit_counts(source: DatabaseReader, run_id: UUID) -> dict[int, int]:
    """Count primary raw records once, including responses that could not be parsed."""
    from researchassistant.contracts.discovery_v2 import V2CompiledQueryAction, V2DiscoveryOperation
    from researchassistant.storage.discovery_store import read_discovery_artifacts

    operations = {
        artifact.action.artifact_id: artifact.action.conceptual_query.round_number
        for artifact in read_discovery_artifacts(source, run_id)
        if isinstance(artifact, V2DiscoveryOperation)
        and isinstance(artifact.action, V2CompiledQueryAction)
    }
    counts: dict[int, int] = {}
    audit = provider_attempt_audit(source, run_id)
    for start, completion in zip(audit.starts, audit.completions, strict=True):
        if (
            start.request_kind == "primary"
            and completion is not None
            and start.operation_id in operations
        ):
            round_number = operations[start.operation_id]
            counts[round_number] = counts.get(round_number, 0) + completion.metadata_records
    return counts


def discovery_pipeline_counters(
    source: DatabaseReader, run_id: UUID
) -> V2DiscoveryPipelineCounters:
    """Read one owned snapshot and derive each pipeline boundary independently."""
    from researchassistant.contracts.acquisition_ranking import (
        V2AcquisitionRankingAudit,
        V2DiscoveryPipelineCounters,
    )
    from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact

    with _read_connection(source) as conn:
        binding = read_discovery_binding(conn, run_id)
        if binding.compiler_identity != "source-query-compiler-v3":
            raise ValueError("pipeline discovery counters require the new retrieval identity")
        rankings = []
        acquisitions = []
        for round_number in range(1, 5):
            for prefix, contract, target in (
                ("phase-3-metadata-ranking-round-", V2MetadataRankingArtifact, rankings),
                ("metadata-acquisition-v2-round-", V2AcquisitionRankingAudit, acquisitions),
            ):
                try:
                    artifact = read_v2_artifact(conn, run_id, f"{prefix}{round_number}")
                except KeyError:
                    continue
                value = contract.model_validate_json(artifact.payload_json)
                if value.run_id != run_id or value.round_number != round_number:
                    raise ValueError(
                        "discovery counter artifact has conflicting run/round identity"
                    )
                target.append(value)
        admissions = conn.execute(
            "SELECT COUNT(*) FROM v2_ledger_admissions WHERE run_id=?", (str(run_id),)
        ).fetchone()[0]
        return V2DiscoveryPipelineCounters(
            run_id=run_id,
            raw_hits=sum(raw_hit_counts(conn, run_id).values()),
            deduplicated_works=len(
                {rank.work_key for ranking in rankings for rank in ranking.ranks}
            ),
            scouted_candidates=sum(ranking.scouted_count for ranking in rankings),
            acquisition_shortlisted_clusters=sum(
                audit.acquisition_shortlisted_clusters for audit in acquisitions
            ),
            fetched_documents=sum(audit.fetched_documents for audit in acquisitions),
            usable_survivors=sum(audit.usable_survivors for audit in acquisitions),
            evidence_admissions=admissions,
        )
