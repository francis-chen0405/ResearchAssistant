"""Read-only discovery diagnostics derived from immutable artifacts."""

from __future__ import annotations

import sqlite3
from uuid import UUID

from researchassistant.contracts.acquisition_ranking import V2AcquisitionRankingAudit
from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryOperation,
    V2ExpansionResult,
    V2GraphNeighborAction,
    V2PreviewRequest,
    V2PreviewResult,
    V2ProductDiscoveryPolicy,
    V2RawDiscoveryCandidate,
    V2SeedEligibility,
)
from researchassistant.contracts.model_evidence import V2RunDiagnostics
from researchassistant.contracts.model_research import V2AcquisitionProbeOutput
from researchassistant.contracts.query_retrieval import V2QueryRetrievalResult
from researchassistant.storage.discovery_store import (
    compute_discovery_audit_counters,
    provider_attempt_audit,
    read_discovery_artifacts,
    read_discovery_binding,
)
from researchassistant.storage.query_retrieval_store import discovery_pipeline_counters
from researchassistant.storage.store import (
    _read_execute,
    _row_to_v2_artifact,
    read_snapshot_connection,
)

_ACQUISITION_AUDIT_KEYS = tuple(
    f"metadata-acquisition-v2-round-{round_number}" for round_number in range(1, 5)
)
_ACQUISITION_PROBE_KEYS = (
    "phase-5-acquisition-probe",
    "phase-7-round-1-acquisition-probe",
    "phase-7-round-2-acquisition-probe",
    "phase-7-round-3-acquisition-probe",
    "post-phase-13-round-4-acquisition-probe-v1",
)


def enrich_discovery_diagnostics(
    connection: sqlite3.Connection,
    run_id: UUID,
    diagnostics: V2RunDiagnostics,
) -> V2RunDiagnostics:
    """Enrich displayed counts from one validated, read-only request snapshot.

    Missing discovery artifacts are represented as unknown fields. Existing run
    diagnostics are retained for historical runs and stages that have not yet
    produced discovery artifacts.
    """
    if not connection.in_transaction:
        with read_snapshot_connection(connection):
            return enrich_discovery_diagnostics(connection, run_id, diagnostics)
    query_only = connection.execute("PRAGMA query_only").fetchone()
    if query_only is None or query_only[0] != 1:
        raise RuntimeError("discovery diagnostics require a query-only connection")

    try:
        binding = read_discovery_binding(connection, run_id)
    except KeyError:
        return diagnostics

    artifacts = read_discovery_artifacts(connection, run_id)
    audit = provider_attempt_audit(connection, run_id)
    counters = compute_discovery_audit_counters(connection, run_id)
    deduplicated_work_candidates = counters.unique_work_candidates
    if binding.compiler_identity == "source-query-compiler-v3":
        deduplicated_work_candidates = discovery_pipeline_counters(
            connection, run_id
        ).deduplicated_works

    operations = tuple(item for item in artifacts if isinstance(item, V2DiscoveryOperation))
    operation_ids = {item.action.artifact_id for item in operations}
    graph_operation_ids = {
        item.action.artifact_id
        for item in operations
        if isinstance(item.action, V2GraphNeighborAction)
    }
    raw_candidates = tuple(item for item in artifacts if isinstance(item, V2RawDiscoveryCandidate))
    seed_derived = {
        edge.candidate.work.grouping_key
        for item in artifacts
        if isinstance(item, V2ExpansionResult)
        and item.status == "completed"
        and item.action.artifact_id in graph_operation_ids
        for edge in item.edges
    }
    primary_records_by_operation: dict[UUID, int] = {}
    for start, completion in zip(audit.starts, audit.completions, strict=True):
        if (
            start.request_kind == "primary"
            and completion is not None
            and completion.status == "completed"
        ):
            primary_records_by_operation[start.operation_id] = (
                primary_records_by_operation.get(start.operation_id, 0)
                + completion.metadata_records
            )

    retrieval_rows = _read_execute(
        connection,
        "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key LIKE ? "
        "ORDER BY artifact_key LIMIT 6001",
        (str(run_id), "metadata-retrieval-v2:%:result"),
    ).fetchall()
    if len(retrieval_rows) > 6000:
        raise sqlite3.IntegrityError("retrieval results exceed the bounded diagnostics reader")
    retrieval_results: list[V2QueryRetrievalResult] = []
    for row in retrieval_rows:
        envelope = _row_to_v2_artifact(row)
        if envelope.artifact_type != "V2QueryRetrievalResult":
            raise sqlite3.IntegrityError("retrieval result has a conflicting artifact type")
        result = V2QueryRetrievalResult.model_validate_json(envelope.payload_json)
        if result.run_id != run_id or result.operation_id not in operation_ids:
            raise sqlite3.IntegrityError("retrieval result has conflicting run ownership")
        if result.binding_fingerprint != binding.fingerprint:
            raise sqlite3.IntegrityError("retrieval result has stale discovery settings")
        if result.retained_records != len(result.response.results):
            raise sqlite3.IntegrityError("retained metadata count differs from its saved response")
        completed_primary_records = primary_records_by_operation.get(result.operation_id, 0)
        if result.raw_hits != completed_primary_records:
            raise sqlite3.IntegrityError(
                "retrieval raw-hit count differs from physical request audit"
            )
        retrieval_results.append(result)

    retained_graph_metadata = sum(
        item.operation_id in graph_operation_ids for item in raw_candidates
    )
    retained_metadata = (
        sum(result.retained_records for result in retrieval_results) + retained_graph_metadata
        if retrieval_results or retained_graph_metadata
        else None
    )

    audit_rows = _read_execute(
        connection,
        "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key IN (?, ?, ?, ?) "
        "ORDER BY artifact_key",
        (str(run_id), *_ACQUISITION_AUDIT_KEYS),
    ).fetchall()
    shortlisted: int | None = 0 if audit_rows else None
    audit_rounds = dict(zip(_ACQUISITION_AUDIT_KEYS, range(1, 5), strict=True))
    for row in audit_rows:
        envelope = _row_to_v2_artifact(row)
        if envelope.artifact_type != "V2AcquisitionRankingAudit":
            raise sqlite3.IntegrityError("acquisition audit has a conflicting artifact type")
        result = V2AcquisitionRankingAudit.model_validate_json(envelope.payload_json)
        if result.run_id != run_id or result.round_number != audit_rounds[envelope.artifact_key]:
            raise sqlite3.IntegrityError("acquisition audit belongs to another run")
        shortlisted += result.acquisition_shortlisted_clusters

    probe_rows = _read_execute(
        connection,
        "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key IN (?, ?, ?, ?, ?) "
        "ORDER BY artifact_key",
        (str(run_id), *_ACQUISITION_PROBE_KEYS),
    ).fetchall()
    probe_previews: list[V2PreviewResult] = []
    probe_count = 0
    missing_probe_previews = 0
    for row in probe_rows:
        envelope = _row_to_v2_artifact(row)
        if envelope.artifact_type != "V2AcquisitionProbeOutput":
            raise sqlite3.IntegrityError("acquisition probe has a conflicting artifact type")
        output = V2AcquisitionProbeOutput.model_validate_json(envelope.payload_json)
        if output.run_id != run_id:
            raise sqlite3.IntegrityError("acquisition probe belongs to another run")
        acquired_by_cluster = {source.cluster_id: source for source in output.acquisitions}
        for probe in output.probes:
            if probe.preview is None:
                continue
            acquired = acquired_by_cluster.get(probe.cluster_id)
            if (
                acquired is None
                or probe.preview.request.source_id != acquired.cluster_id
                or probe.preview.request.direction != acquired.direction
                or probe.preview.request.directions != output.directions
                or probe.preview.request.exact_claim != binding.exact_claim
            ):
                raise sqlite3.IntegrityError("preview source ownership differs from acquisition")
            probe.preview.require_snapshot(acquired.snapshot)
        probe_count += len(output.probes)
        missing_probe_previews += sum(probe.preview is None for probe in output.probes)
        probe_previews.extend(probe.preview for probe in output.probes if probe.preview is not None)

    messages: list[str] = []
    partial_reasons = {
        "provider_limit",
        "provider_budget",
        "retention_cap",
        "malformed_page",
        "provider_failure",
        "unknown_outcome",
        "repeated_cursor",
        "completed_without_checkpoint",
    }
    if any(result.stopping_reason in partial_reasons for result in retrieval_results):
        messages.append("Some provider searches ended early; counts include only retained results.")
    if any(result.stopping_reason == "provider_budget" for result in retrieval_results):
        messages.append("A provider request budget was reached, so fewer results were collected.")
    if audit.interrupted_unknown or any(
        completion is not None and completion.status != "completed"
        for completion in audit.completions
    ):
        messages.append(
            "Some provider requests failed or have unknown outcomes; counts use saved results."
        )
    if any(
        completion is not None
        and completion.failure is not None
        and completion.failure.code == "budget"
        for completion in audit.completions
    ):
        messages.append("A provider request budget was reached, so fewer results were collected.")

    product_policy = (
        binding.policy if isinstance(binding.policy, V2ProductDiscoveryPolicy) else None
    )
    seed_expansion_enabled = product_policy.seed_expansion_enabled if product_policy else True
    eligible_seeds = tuple(
        item for item in artifacts if isinstance(item, V2SeedEligibility) and item.eligible
    )
    openalex_selected = any(provider.value == "openalex" for provider in binding.providers)
    capabilities = {item.provider: item for item in binding.capabilities}
    openalex = next(
        (provider for provider in binding.providers if provider.value == "openalex"), None
    )
    graph_capable = bool(
        openalex is not None
        and openalex in capabilities
        and capabilities[openalex].executable_relationships
    )
    if not seed_expansion_enabled:
        messages.append("Paper expansion was turned off for this run.")
    elif not openalex_selected:
        messages.append("OpenAlex was not selected; citation graph expansion was unavailable.")
    elif not graph_capable:
        messages.append(
            "Citation graph expansion is unavailable with the selected provider capability."
        )
    elif not eligible_seeds:
        messages.append("No eligible saved paper is available for citation expansion so far.")

    preview_requests = tuple(item for item in artifacts if isinstance(item, V2PreviewRequest))
    preview_results = tuple(
        item for item in artifacts if isinstance(item, V2PreviewResult)
    ) + tuple(probe_previews)
    completed_preview_ids = {item.request.artifact_id for item in preview_results}
    if (preview_requests and len(completed_preview_ids) < len(preview_requests)) or any(
        item.outcome == "unavailable" for item in preview_results
    ):
        messages.append(
            "Some source previews are missing or unavailable; preview coverage is incomplete."
        )
    elif (
        binding.preview_identity == "source-claim-preview-v2"
        and probe_count > 0
        and missing_probe_previews > 0
    ):
        messages.append("Some acquired sources have no saved preview for inspection.")

    if any(item.capture_usable and item.relevance_score == 0 for item in preview_results):
        messages.append("Some readable sources have no claim-relevant preview passage.")
    if any(item.content_classification == "abstract_only" for item in preview_results):
        messages.append(
            "Some source previews contain abstracts only; full-text context is missing."
        )

    return V2RunDiagnostics.model_validate(
        diagnostics.model_dump(mode="python")
        | {
            "logical_discovery_operations": len(operations),
            "physical_search_requests": len(audit.starts),
            "retained_metadata_records": retained_metadata,
            "deduplicated_work_candidates": deduplicated_work_candidates,
            "seed_derived_candidates": len(seed_derived),
            "shortlist_candidates": shortlisted,
            "diagnostic_messages": tuple(dict.fromkeys(messages)) or None,
        }
    )
