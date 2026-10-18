"""Bounded source dispositions from a single validated, read-only snapshot.

No normalization, ranking, capture or model work is rerun here. Missing records
remain unknown. Discovery wording and snippets cannot become evidence in this view.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from researchassistant.contracts.acquisition_capture import (
    V2AcquisitionCaptureCompletion,
    V2AcquisitionCaptureResponse,
    V2AcquisitionCaptureStart,
)
from researchassistant.contracts.acquisition_ranking import V2AcquisitionRankingAudit
from researchassistant.contracts.artifact_keys import discovery_round_keys
from researchassistant.contracts.discovery_v2 import (
    V2CandidateDisposition,
    V2DiscoveryBinding,
    V2DiscoveryOperation,
    V2NormalizedDiscoveryCandidate,
    V2RawDiscoveryCandidate,
)
from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
from researchassistant.contracts.model_contracts import SourceSnapshot
from researchassistant.contracts.model_evidence import (
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionSourceResult,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystSourceResult,
)
from researchassistant.contracts.query_retrieval import (
    V2QueryPageCheckpoint,
    V2QueryRetrievalResult,
)
from researchassistant.contracts.research_acquisition import V2AcquisitionProbeOutput
from researchassistant.contracts.research_discovery import V2DiscoveryScoutOutput
from researchassistant.contracts.research_selection import V2SourceSelectionQueueResult
from researchassistant.contracts.source_leads import SourceLead, SourceLeadsPage, SourceLeadStage
from researchassistant.storage.discovery_store import read_discovery_operation
from researchassistant.storage.historical_decode import decode_v2_artifact
from researchassistant.storage.query_retrieval_store import validate_page
from researchassistant.storage.store import (
    _read_execute,
    _row_to_v2_artifact,
    open_read_only_store,
    read_run,
    read_snapshot_connection,
)

_TYPES = {
    model.__name__: model
    for model in (
        V2DiscoveryBinding,
        V2DiscoveryOperation,
        V2RawDiscoveryCandidate,
        V2NormalizedDiscoveryCandidate,
        V2CandidateDisposition,
        V2DiscoveryScoutOutput,
        V2MetadataRankingArtifact,
        V2AcquisitionRankingAudit,
        V2AcquisitionProbeOutput,
        V2AcquisitionCaptureStart,
        V2AcquisitionCaptureResponse,
        V2AcquisitionCaptureCompletion,
        V2SourceSelectionQueueResult,
        V2EvidenceAnalystSourceResult,
        V2EvidenceAnalystBatchResult,
        V2EvidenceAdmissionBatchResult,
        V2EvidenceAdmissionSourceResult,
        V2QueryPageCheckpoint,
        V2QueryRetrievalResult,
    )
}
_MAX_ARTIFACTS = 12000
_MAX_BYTES = 128 * 1024 * 1024
_NOTICE = (
    "Saved discovery leads from this run. Titles and search directions are metadata, "
    "not verified evidence or proof of a relationship to the claim. Confidence describes "
    "the saved disposition only; usefulness and study independence remain unknown. "
    "Missing stages and upstream hits without saved metadata are unknown. "
    "Expand lead history for recorded dispositions; original saved artifacts remain unchanged."
)


def _same_run(value: object, run_id: UUID) -> None:
    if isinstance(value, BaseModel):
        if hasattr(value, "run_id") and value.run_id != run_id:
            raise sqlite3.IntegrityError("source lead artifact has cross-run ownership")
        if (
            isinstance(value, SourceSnapshot)
            and value.snapshot_sha256 != sha256(value.normalized_text.encode()).hexdigest()
        ):
            raise sqlite3.IntegrityError("source lead snapshot checksum differs from its text")
        for name in type(value).model_fields:
            _same_run(getattr(value, name), run_id)
    elif isinstance(value, (tuple, list)):
        for member in value:
            _same_run(member, run_id)


def _key_matches(key: str, value: BaseModel) -> bool:
    if isinstance(
        value,
        (
            V2DiscoveryBinding,
            V2DiscoveryOperation,
            V2RawDiscoveryCandidate,
            V2NormalizedDiscoveryCandidate,
            V2CandidateDisposition,
        ),
    ):
        return key == f"source-discovery-v1:{type(value).__name__}:{value.identity_key}"
    if isinstance(value, (V2QueryPageCheckpoint, V2QueryRetrievalResult)):
        suffix = (
            f"page:{value.page_number}" if isinstance(value, V2QueryPageCheckpoint) else "result"
        )
        return key == f"metadata-retrieval-v2:{value.operation_id}:{suffix}"
    if isinstance(value, V2DiscoveryScoutOutput):
        return key in {discovery_round_keys(n)[0] for n in range(1, 5)}
    if isinstance(value, V2MetadataRankingArtifact):
        return key == f"phase-3-metadata-ranking-round-{value.round_number}"
    if isinstance(value, V2AcquisitionRankingAudit):
        return key == f"metadata-acquisition-v2-round-{value.round_number}"
    if isinstance(value, V2AcquisitionProbeOutput):
        return key in {discovery_round_keys(n)[1] for n in range(1, 5)}
    if isinstance(
        value,
        (V2AcquisitionCaptureStart, V2AcquisitionCaptureResponse, V2AcquisitionCaptureCompletion),
    ):
        start = value if isinstance(value, V2AcquisitionCaptureStart) else value.start
        suffix = {
            V2AcquisitionCaptureStart: "start",
            V2AcquisitionCaptureResponse: "response",
            V2AcquisitionCaptureCompletion: "completion",
        }[type(value)]
        tail = (
            f"/captures/{start.cluster_id}/{sha256(start.url.encode()).hexdigest()}"
            f"/{start.provider.value}/{suffix}"
        )
        return any(key == discovery_round_keys(n)[1] + tail for n in range(1, 5))
    if isinstance(value, V2SourceSelectionQueueResult):
        return key in {
            "phase-13-source-selection-deep-analysis-queue-analyzer-admission",
            "phase-13-source-statuses-analyzer-admission",
            "phase-8-source-selection-deep-analysis-queue",
        }
    if isinstance(value, V2EvidenceAnalystSourceResult):
        return key in {
            f"phase-13-luna-evidence-analyst-source-v2-{value.source_id}",
            f"phase-13-luna-evidence-analyst-source-{value.source_id}",
        }
    if isinstance(value, V2EvidenceAnalystBatchResult):
        if key in {
            f"phase-13-luna-evidence-analyst-batch-source-{source_id}"
            for source_id in value.input.queue_result.queued_source_ids
        }:
            return True
        return key in {
            "phase-13-luna-evidence-analyst-analyzer-admission",
            "phase-9-luna-evidence-analyst",
        }
    if isinstance(value, V2EvidenceAdmissionBatchResult):
        return key == "phase-13-evidence-admission" or (
            key
            in {
                f"phase-13-evidence-admission-batch-source-{source_id}"
                for source_id in value.analyst_result.input.queue_result.queued_source_ids
            }
        )
    if isinstance(value, V2EvidenceAdmissionSourceResult):
        return key in {
            f"phase-13-evidence-admission-source-v2-{value.source_id}",
            f"phase-13-evidence-admission-source-{value.source_id}",
        }
    return False


def _inventory(connection: sqlite3.Connection, run_id: UUID) -> list[tuple[str, BaseModel]]:
    placeholders = ",".join("?" for _ in _TYPES)
    stage_keys = [
        *[key for number in range(1, 5) for key in discovery_round_keys(number)],
        *[f"phase-3-metadata-ranking-round-{n}" for n in range(1, 5)],
        *[f"metadata-acquisition-v2-round-{n}" for n in range(1, 5)],
        "phase-13-source-selection-deep-analysis-queue-analyzer-admission",
        "phase-13-source-statuses-analyzer-admission",
        "phase-8-source-selection-deep-analysis-queue",
        "phase-13-luna-evidence-analyst-analyzer-admission",
        "phase-9-luna-evidence-analyst",
        "phase-13-evidence-admission",
    ]
    patterns = [
        *[f"{discovery_round_keys(n)[1]}/captures/%" for n in range(1, 5)],
        "metadata-retrieval-v2:%:page:%",
        "metadata-retrieval-v2:%:result",
        "phase-13-luna-evidence-analyst-source-%",
        "phase-13-luna-evidence-analyst-batch-source-%",
        "phase-13-evidence-admission-batch-source-%",
        "phase-13-evidence-admission-source-%",
        *[
            f"source-discovery-v1:{name}:%"
            for name in (
                "V2DiscoveryBinding",
                "V2DiscoveryOperation",
                "V2RawDiscoveryCandidate",
                "V2NormalizedDiscoveryCandidate",
                "V2CandidateDisposition",
            )
        ],
    ]
    keys_sql = ",".join("?" for _ in stage_keys)
    patterns_sql = " OR ".join("artifact_key LIKE ?" for _ in patterns)
    rows = _read_execute(
        connection,
        f"SELECT artifact_key, artifact_type, length(CAST(payload_json AS BLOB)) AS size "
        f"FROM v2_artifacts WHERE run_id = ? AND (artifact_type IN ({placeholders}) "
        f"OR artifact_key IN ({keys_sql}) OR {patterns_sql}) "
        "ORDER BY rowid LIMIT ?",
        (str(run_id), *_TYPES, *stage_keys, *patterns, _MAX_ARTIFACTS + 1),
    ).fetchall()
    if len(rows) > _MAX_ARTIFACTS or sum(row["size"] for row in rows) > _MAX_BYTES:
        raise sqlite3.IntegrityError("source leads exceed the bounded inspection inventory")
    values: list[tuple[str, BaseModel]] = []
    for row in rows:
        full = _read_execute(
            connection,
            "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
            (str(run_id), row["artifact_key"]),
        ).fetchone()
        envelope = _row_to_v2_artifact(full)
        if envelope.artifact_type not in _TYPES:
            raise sqlite3.IntegrityError("source lead stage has an unexpected artifact type")
        value = decode_v2_artifact(envelope, _TYPES[envelope.artifact_type])
        _same_run(value, run_id)
        if not _key_matches(envelope.artifact_key, value):
            raise sqlite3.IntegrityError("source lead artifact has conflicting stage identity")
        if isinstance(value, V2DiscoveryOperation):
            read_discovery_operation(connection, run_id, value.identity_key)
        if isinstance(value, V2QueryPageCheckpoint):
            validate_page(connection, value)
        values.append((envelope.artifact_key, value))
    _validate_capture_journal(values)
    return values


def _validate_capture_journal(values: list[tuple[str, BaseModel]]) -> None:
    journals: dict[str, dict[str, BaseModel]] = {}
    for key, value in values:
        if isinstance(
            value,
            (
                V2AcquisitionCaptureStart,
                V2AcquisitionCaptureResponse,
                V2AcquisitionCaptureCompletion,
            ),
        ):
            prefix, suffix = key.rsplit("/", 1)
            journals.setdefault(prefix, {})[suffix] = value
    for entries in journals.values():
        start = entries.get("start")
        if not isinstance(start, V2AcquisitionCaptureStart):
            raise sqlite3.IntegrityError("source capture lacks its saved dispatch")
        response = entries.get("response")
        completion = entries.get("completion")
        if response is not None and (
            response.start != start
            or response.attempt.cluster_id != start.cluster_id
            or response.attempt.url != start.url
            or response.attempt.provider != start.provider
            or response.attempt.succeeded
            != (response.response is not None and bool(response.response.text.strip()))
        ):
            raise sqlite3.IntegrityError("source capture response differs from its dispatch")
        if completion is not None and (
            not isinstance(response, V2AcquisitionCaptureResponse)
            or completion.start != start
            or completion.attempt != response.attempt
            or completion.response != response.response
        ):
            raise sqlite3.IntegrityError("source capture completion differs from its response")


def _event(stage: str, status: str, reason: str | None = None) -> SourceLeadStage:
    return SourceLeadStage(stage=stage, status=status, reason=reason)


def _analysis_reason(result: V2EvidenceAnalystSourceResult) -> str | None:
    if result.failure:
        return result.failure
    assessment = result.assessment
    if assessment is None:
        return None
    reason = (
        f"Recorded assessment: relationship {assessment.relationship_to_claim.value}; "
        f"Evidence Quality {assessment.evidence_quality}/5; Claim Fit {assessment.claim_fit}/5. "
        f"{assessment.reasoning}"
    )
    if result.score_decision and result.score_decision.rationale != assessment.reasoning:
        reason += f" {result.score_decision.rationale}"
    return reason


def _record_capture(outcomes: dict[str, str], url: str, status: str) -> None:
    # An independently readable capture is not erased by a later failed/unknown method.
    if outcomes.get(url) != "readable":
        outcomes[url] = status


def _record_admission(
    admission: dict[UUID, list[V2EvidenceAdmissionSourceResult]],
    result: V2EvidenceAdmissionSourceResult,
) -> None:
    recorded = admission.setdefault(result.source_id, [])
    if recorded and result != recorded[0]:
        raise sqlite3.IntegrityError("source admission records disagree")
    if not recorded:
        recorded.append(result)


def _project(values: list[tuple[str, BaseModel]], run_id: UUID) -> list[SourceLead]:
    discoveries = {key: value for key, value in values if isinstance(value, V2DiscoveryScoutOutput)}
    rankings = {
        value.round_number: value
        for _, value in values
        if isinstance(value, V2MetadataRankingArtifact)
    }
    audits = {
        value.round_number: value
        for _, value in values
        if isinstance(value, V2AcquisitionRankingAudit)
    }
    probes = {key: value for key, value in values if isinstance(value, V2AcquisitionProbeOutput)}
    bindings = [value for _, value in values if isinstance(value, V2DiscoveryBinding)]
    operations = {
        value.action.artifact_id: value
        for _, value in values
        if isinstance(value, V2DiscoveryOperation)
    }
    binding = bindings[0] if len(bindings) == 1 else None
    captures: dict[UUID, list[tuple[str, BaseModel]]] = {}
    for key, value in values:
        if isinstance(
            value,
            (
                V2AcquisitionCaptureStart,
                V2AcquisitionCaptureResponse,
                V2AcquisitionCaptureCompletion,
            ),
        ):
            start = value if isinstance(value, V2AcquisitionCaptureStart) else value.start
            captures.setdefault(start.cluster_id, []).append((key, value))
    statuses = {}
    analysis: dict[UUID, list[V2EvidenceAnalystSourceResult]] = {}
    admission: dict[UUID, list[V2EvidenceAdmissionSourceResult]] = {}
    for saved_key, value in values:
        if isinstance(value, V2SourceSelectionQueueResult):
            for status in value.source_statuses:
                if status.source_id in statuses and statuses[status.source_id] != status:
                    raise sqlite3.IntegrityError("source selection records disagree")
                statuses[status.source_id] = status
        if isinstance(value, V2EvidenceAnalystSourceResult):
            if value not in analysis.setdefault(value.source_id, []):
                analysis[value.source_id].append(value)
        if isinstance(value, (V2EvidenceAnalystBatchResult, V2EvidenceAdmissionBatchResult)):
            batch = (
                value.analyst_result if isinstance(value, V2EvidenceAdmissionBatchResult) else value
            )
            for result in batch.source_results:
                if "-batch-source-" in saved_key and not saved_key.endswith(str(result.source_id)):
                    continue
                if result not in analysis.setdefault(result.source_id, []):
                    analysis[result.source_id].append(result)
        if isinstance(value, V2EvidenceAdmissionBatchResult):
            for result in value.source_results:
                if "-batch-source-" in saved_key and not saved_key.endswith(str(result.source_id)):
                    continue
                _record_admission(admission, result)
        if isinstance(value, V2EvidenceAdmissionSourceResult):
            _record_admission(admission, value)
    leads: list[SourceLead] = []
    matched: set[tuple[str | None, str, str, int, str]] = set()
    cluster_ids: set[UUID] = set()
    for number in range(1, 5):
        discovery_key, probe_key = discovery_round_keys(number)
        discovery = discoveries.get(discovery_key)
        if discovery is None:
            continue
        items = {item.item_id: item for item in discovery.items}
        if any(item.round_number != number for item in discovery.items):
            raise sqlite3.IntegrityError("source discovery round ownership differs")
        clusters = {}
        for cluster in discovery.clusters:
            cluster_ids.add(cluster.cluster_id)
            for item_id in cluster.item_ids:
                if item_id not in items or item_id in clusters:
                    raise sqlite3.IntegrityError("source cluster membership is corrupt")
                clusters[item_id] = cluster
        if set(clusters) != set(items):
            raise sqlite3.IntegrityError("source cluster inventory is incomplete")
        for key, record in values:
            if key.startswith(probe_key + "/captures/"):
                start = record if isinstance(record, V2AcquisitionCaptureStart) else record.start
                owner = next(
                    (
                        cluster
                        for cluster in discovery.clusters
                        if cluster.cluster_id == start.cluster_id
                    ),
                    None,
                )
                if owner is None or start.direction not in {
                    items[item_id].direction for item_id in owner.item_ids
                }:
                    raise sqlite3.IntegrityError("source capture direction or cluster differs")
        ranking = rankings.get(number)
        ranks = {item.item_id: item for item in ranking.ranks} if ranking else {}
        dispositions = (
            {item.item_id: item.disposition for item in ranking.scout_dispositions}
            if ranking
            else {}
        )
        if ranking and set(ranks) != set(items):
            raise sqlite3.IntegrityError("source ranking membership differs from discovery")
        scout = {item.item_id: item for batch in discovery.scout_batches for item in batch.items}
        if (
            not set(scout) <= set(items)
            or ranking
            and set(scout)
            != {key for key, disposition in dispositions.items() if disposition == "scouted"}
        ):
            raise sqlite3.IntegrityError("source Scout membership differs from discovery")
        audit = audits.get(number)
        acq = {item.cluster_id: item for item in audit.dispositions} if audit else {}
        if audit and set(acq) != {cluster.cluster_id for cluster in discovery.clusters}:
            raise sqlite3.IntegrityError("source acquisition membership differs from discovery")
        probe_output = probes.get(probe_key)
        acquired = (
            {item.cluster_id: item for item in probe_output.acquisitions} if probe_output else {}
        )
        probed = {item.cluster_id: item for item in probe_output.probes} if probe_output else {}
        for item in discovery.items:
            cluster = clusters.get(item.item_id)
            source_id = cluster.cluster_id if cluster else None
            history = [_event("normalization", "retained")]
            unknowns = ["Usefulness and study independence have not been human-judged."]
            if item.item_id in ranks:
                history.append(
                    _event(
                        "ranking",
                        f"rank_{ranks[item.item_id].rank}",
                        "; ".join(ranks[item.item_id].rationale),
                    )
                )
            else:
                unknowns.append("Metadata ranking was not recorded.")
            if item.item_id in dispositions:
                history.append(_event("Scout capacity", dispositions[item.item_id]))
            if item.item_id in scout:
                decision = scout[item.item_id]
                history.append(_event("Scout", decision.decision.value, decision.rationale))
            elif item.item_id not in dispositions:
                unknowns.append("Scout disposition was not recorded.")
            capture_outcomes: dict[str, str] = {}
            readable_urls: list[str] = []
            if source_id in acq:
                history.append(_event("acquisition", acq[source_id].disposition))
            journal = captures.get(source_id, [])
            completed_keys = {
                key.rsplit("/", 1)[0]
                for key, record in journal
                if isinstance(record, V2AcquisitionCaptureCompletion)
            }
            response_keys = {
                key.rsplit("/", 1)[0]
                for key, record in journal
                if isinstance(record, V2AcquisitionCaptureResponse)
            }
            for key, record in journal:
                prefix = key.rsplit("/", 1)[0]
                if (
                    isinstance(record, V2AcquisitionCaptureStart)
                    and prefix not in completed_keys | response_keys
                ):
                    history.append(
                        _event(
                            "capture",
                            "attempted",
                            f"{record.provider.value}: {record.url}; outcome unknown",
                        )
                    )
                    _record_capture(capture_outcomes, record.url, "attempted")
                elif (
                    isinstance(record, V2AcquisitionCaptureResponse)
                    and prefix not in completed_keys
                ):
                    history.append(
                        _event(
                            "capture",
                            "captured" if record.response else "failed",
                            record.attempt.failure_message
                            or (
                                f"{record.start.provider.value}: {record.start.url}; "
                                "readability unknown"
                            ),
                        )
                    )
                    status = "captured" if record.response else "failed"
                    _record_capture(capture_outcomes, record.start.url, status)
                    if record.response:
                        _record_capture(capture_outcomes, record.response.resolved_url, status)
                elif isinstance(record, V2AcquisitionCaptureCompletion):
                    status = (
                        "readable"
                        if record.readable
                        else "unusable"
                        if record.source or record.response
                        else "failed"
                    )
                    history.append(
                        _event(
                            "capture",
                            status,
                            record.attempt.failure_message
                            or f"{record.start.provider.value}: {record.start.url}",
                        )
                    )
                    _record_capture(capture_outcomes, record.start.url, status)
                    if record.response:
                        _record_capture(capture_outcomes, record.response.resolved_url, status)
                        if record.readable and record.response.resolved_url not in readable_urls:
                            readable_urls.append(record.response.resolved_url)
            if not journal and probe_output:
                for attempt in probe_output.attempts:
                    if attempt.cluster_id == source_id:
                        status = "captured" if attempt.succeeded else "failed"
                        _record_capture(capture_outcomes, attempt.url, status)
                        history.append(
                            _event(
                                "capture",
                                status,
                                attempt.failure_message
                                or f"{attempt.provider.value}: {attempt.url}",
                            )
                        )
            if source_id in acquired:
                source = acquired[source_id]
                probe = probed.get(source_id)
                if probe:
                    if (
                        probe.snapshot_id != source.snapshot.snapshot_id
                        or probe.snapshot_sha256 != source.snapshot.snapshot_sha256
                    ):
                        raise sqlite3.IntegrityError("source Probe differs from its snapshot")
                    if not journal and probe.preview is not None:
                        status = "readable" if probe.preview.capture_usable else "unusable"
                        for url in (source.snapshot.source_url, source.snapshot.original_url):
                            if url:
                                _record_capture(capture_outcomes, url, status)
                        if status == "readable":
                            readable_urls.append(source.snapshot.source_url)
                    history.append(
                        _event(
                            "Probe",
                            "passages_available" if probe.succeeded else "no_usable_passages",
                            probe.failure,
                        )
                    )
                if not journal and (probe is None or probe.preview is None):
                    for url in (source.snapshot.source_url, source.snapshot.original_url):
                        if url:
                            _record_capture(capture_outcomes, url, "captured")
            capture_status = capture_outcomes.get(item.source_url, "unknown")
            readable_alternate_url = (
                next((url for url in readable_urls if url != item.source_url), None)
                if capture_status != "readable"
                else None
            )
            if capture_status in {"unknown", "attempted", "captured"}:
                unknowns.append("Capture readability is unknown.")
            if source_id in statuses:
                status = statuses[source_id]
                history.append(
                    _event(
                        "selection",
                        "queued" if status.queued_for_deep_analysis else "not_queued",
                        status.budget_prevented_reason.value
                        if status.budget_prevented_reason
                        else status.selection_rationale,
                    )
                )
            else:
                unknowns.append("Selection outcome was not recorded.")
            if source_id in analysis:
                for result in analysis[source_id]:
                    history.append(_event("analysis", result.state.value, _analysis_reason(result)))
                if len(analysis[source_id]) > 1:
                    unknowns.append(
                        "Saved analysis stages differ; inspect the full research trail."
                    )
            else:
                unknowns.append("Analysis outcome was not recorded.")
            if source_id in admission:
                for result in admission[source_id]:
                    if (
                        result.direction
                        not in {items[item_id].direction for item_id in cluster.item_ids}
                        or result.provenance.discovery_round != number
                    ):
                        raise sqlite3.IntegrityError("source admission discovery ownership differs")
                    reason = result.failure
                    if result.state.value == "analyst_rejected":
                        rejected = [
                            candidate
                            for candidate in analysis.get(source_id, [])
                            if candidate.state.value == "rejected"
                        ]
                        reason = (
                            _analysis_reason(rejected[-1])
                            if rejected
                            else "Recorded Analyst rejection; its assessment reason is unavailable."
                        )
                    history.append(_event("admission", result.state.value, reason))
            else:
                unknowns.append("Admission outcome was not recorded.")
            terminal = history[-1]
            for provenance in item.provenance_chain:
                matched.add(
                    (
                        provenance.query_text,
                        provenance.provider.value,
                        provenance.direction.value,
                        provenance.round_number,
                        provenance.original_url,
                    )
                )
            leads.append(
                SourceLead(
                    lead_id=str(item.item_id),
                    source_id=source_id,
                    title=item.title,
                    url=item.source_url,
                    work_id=ranks[item.item_id].work_key if item.item_id in ranks else item.doi,
                    source_family=(
                        admission[source_id][-1].provenance.source_family_id
                        if source_id in admission
                        else None
                    ),
                    providers=tuple(
                        sorted({value.provider.value for value in item.provenance_chain})
                    ),
                    search_directions=tuple(
                        sorted({value.direction.value for value in item.provenance_chain})
                    ),
                    rounds=(number,),
                    capture_status=capture_status,
                    readable_alternate_url=readable_alternate_url,
                    disposition=terminal.status,
                    reason=terminal.reason or terminal.status.replace("_", " "),
                    confidence="recorded",
                    unknowns=tuple(unknowns),
                    history=tuple(history),
                )
            )
    if (
        set(captures) - cluster_ids
        or set(statuses) - cluster_ids
        or set(analysis) - cluster_ids
        or set(admission) - cluster_ids
    ):
        raise sqlite3.IntegrityError("source disposition refers to an unsaved discovery cluster")
    # Include page hits lost before a completed Scout handoff, without re-normalizing.
    results = {
        value.operation_id: value
        for _, value in values
        if isinstance(value, V2QueryRetrievalResult)
    }
    retained = {
        operation_id: {hit.original_url for hit in result.response.results}
        for operation_id, result in results.items()
    }
    pages = [(key, value) for key, value in values if isinstance(value, V2QueryPageCheckpoint)]
    page_ops = {page.operation_id for _, page in pages}
    raw_responses = pages + [
        (key, value)
        for key, value in values
        if isinstance(value, V2QueryRetrievalResult) and value.operation_id not in page_ops
    ]
    for key, response in raw_responses:
        operation = operations.get(response.operation_id)
        if (
            binding is None
            or response.binding_fingerprint != binding.fingerprint
            or operation is None
        ):
            raise sqlite3.IntegrityError(
                "source provider page has unknown operation or settings ownership"
            )
        action = operation.action
        concept = action.conceptual_query
        for index, hit in enumerate(response.response.results):
            if (
                action.query_text,
                concept.provider.value,
                concept.direction.value,
                concept.round_number,
                hit.original_url,
            ) in matched:
                continue
            status = "unknown"
            reason = "No completed normalization/Scout handoff was saved for this result."
            if (
                response.operation_id in retained
                and hit.original_url not in retained[response.operation_id]
            ):
                status = "metadata_not_retained"
                reason = "Provider page hit is absent from the saved retained metadata response."
            leads.append(
                SourceLead(
                    lead_id=f"{key}:{index}",
                    source_id=None,
                    title=hit.title or None,
                    url=hit.original_url,
                    work_id=hit.metadata.doi,
                    providers=(concept.provider.value,),
                    search_directions=(concept.direction.value,),
                    rounds=(concept.round_number,),
                    capture_status="unknown",
                    disposition=status,
                    reason=reason,
                    confidence="unknown" if status == "unknown" else "recorded",
                    unknowns=(
                        "Capture, selection, analysis, admission and usefulness are unknown.",
                    ),
                    history=(
                        _event("provider", "returned"),
                        _event("metadata retention", status, reason),
                    ),
                )
            )
    # Native neighbor results may be saved before a Scout aggregate exists.
    native_dispositions = {
        value.candidate_id: value
        for _, value in values
        if isinstance(value, V2CandidateDisposition)
    }
    for _, raw in values:
        if not isinstance(raw, V2RawDiscoveryCandidate):
            continue
        operation = operations.get(raw.operation_id)
        if (
            operation is None
            or binding is None
            or operation.binding_fingerprint != binding.fingerprint
        ):
            raise sqlite3.IntegrityError("native lead has unknown discovery operation ownership")
        locations = raw.locations
        if any(
            (None, raw.provider.value, raw.direction.value, raw.round_number, location.url)
            in matched
            for location in locations
        ):
            continue
        disposition = native_dispositions.get(raw.artifact_id)
        if disposition and (
            disposition.operation_id != raw.operation_id
            or disposition.round_number != raw.round_number
        ):
            raise sqlite3.IntegrityError("native lead disposition ownership differs")
        reason = disposition.reason if disposition else "No completed source handoff is recorded."
        leads.append(
            SourceLead(
                lead_id=str(raw.artifact_id),
                source_id=None,
                title=raw.work.title,
                url=locations[0].url if locations else "",
                work_id=raw.work.grouping_key,
                providers=(raw.provider.value,),
                search_directions=(raw.direction.value,),
                rounds=(raw.round_number,),
                capture_status="unknown",
                disposition=disposition.disposition if disposition else "unknown",
                reason=reason,
                confidence="recorded" if disposition else "unknown",
                unknowns=("Readability, usefulness, independence and admission are unknown.",),
                history=(
                    _event("provider", "returned"),
                    _event(
                        "discovery disposition",
                        disposition.disposition if disposition else "unknown",
                        reason,
                    ),
                ),
            )
        )
    if len(leads) > 6000:
        raise sqlite3.IntegrityError("source leads exceed the bounded projection")
    counts = Counter(item.lead_id for item in leads)
    if any(count > 1 for count in counts.values()):
        raise sqlite3.IntegrityError("source lead identities are not unique")
    return sorted(leads, key=lambda item: (item.rounds, item.lead_id))


def read_source_leads(
    db_path: str | Path, run_id: UUID, *, offset: int = 0, limit: int = 50
) -> SourceLeadsPage:
    if (
        isinstance(offset, bool)
        or isinstance(limit, bool)
        or not isinstance(offset, int)
        or not isinstance(limit, int)
        or not 0 <= offset <= 6000
        or not 1 <= limit <= 100
    ):
        raise ValueError("source lead pagination must use offset 0–6000 and limit 1–100")
    with open_read_only_store(db_path) as store:
        with read_snapshot_connection(store.connection):
            read_run(store.connection, run_id)
            values = _inventory(store.connection, run_id)
    leads = _project(values, run_id)
    return SourceLeadsPage(
        run_id=run_id,
        items=tuple(leads[offset : offset + limit]),
        total=len(leads),
        offset=offset,
        limit=limit,
        has_more=offset + limit < len(leads),
        notice=_NOTICE,
    )
