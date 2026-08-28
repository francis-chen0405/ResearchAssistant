"""Deterministic admission of fresh-v2 Analyst evidence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from agents.analyst import statement_has_required_qualification
from agents.researcher import verify_candidate_against_snapshot
from models import (
    V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
    Placement,
    V2AdmissionMethod,
    V2DeepAnalysisSourceStatus,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionRecord,
    V2EvidenceAdmissionSourceResult,
    V2EvidenceAdmissionState,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2LedgerProvenance,
    V2SourceSelectionCandidate,
    entailment_for_claim_fit,
)
from store import insert_v2_artifact, insert_v2_evidence_admission, read_v2_artifact

V2_EVIDENCE_ADMISSION_ARTIFACT_KEY = "phase-13-evidence-admission"
V2_EVIDENCE_ADMISSION_SOURCE_ARTIFACT_PREFIX = "phase-13-evidence-admission-source-v2"
V2_EVIDENCE_ADMISSION_SOURCE_LEGACY_PREFIX = "phase-13-evidence-admission-source"


def run_v2_evidence_admission(
    *,
    db_path: str | Path,
    analyst_result: V2EvidenceAnalystBatchResult,
    clock: Callable[[], datetime] | None = None,
    artifact_key: str = V2_EVIDENCE_ADMISSION_ARTIFACT_KEY,
) -> V2EvidenceAdmissionBatchResult:
    """Admit every deterministic-valid Analyst result without an LLM Reviewer call."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    stored = _read_artifact(path, analyst_result.run_id, artifact_key)
    if stored is not None:
        result = V2EvidenceAdmissionBatchResult.model_validate_json(stored)
        if result.analyst_result != analyst_result:
            raise ValueError("persisted evidence admission does not match the Analyst result")
        return result

    survivor_by_id = {
        item.source_id: item for item in analyst_result.input.queue_result.input.survivors
    }
    status_by_id = {
        item.source_id: item for item in analyst_result.input.queue_result.source_statuses
    }
    output: list[V2EvidenceAdmissionSourceResult] = []
    for analyst_source in analyst_result.source_results:
        candidate = survivor_by_id[analyst_source.source_id]
        status = status_by_id[analyst_source.source_id]
        provenance = _provenance(candidate, status)
        source_key = _source_artifact_key(analyst_source.source_id)
        persisted_source = (
            None
            if analyst_source.state is V2EvidenceAnalystState.NOT_QUEUED
            else _read_source_result(path, analyst_result.run_id, analyst_source.source_id)
        )
        if persisted_source is not None:
            source_result = persisted_source
        else:
            source_result = _admit_source(
                db_path=path,
                analyst_result=analyst_result,
                analyst_source=analyst_source,
                candidate=candidate,
                provenance=provenance,
                clock=now,
            )
            if source_result.state is not V2EvidenceAdmissionState.NOT_QUEUED:
                insert_v2_artifact(path, source_key, source_result, _aware(now()))
        if source_result.source_id != analyst_source.source_id:
            raise ValueError("persisted evidence admission source does not match the survivor")
        output.append(source_result)

    result = V2EvidenceAdmissionBatchResult(
        run_id=analyst_result.run_id,
        analyst_result=analyst_result,
        source_results=tuple(output),
        completed_at=_aware(now()),
    )
    insert_v2_artifact(path, artifact_key, result, result.completed_at)
    return result


def _admit_source(
    *,
    db_path: str,
    analyst_result: V2EvidenceAnalystBatchResult,
    analyst_source: V2EvidenceAnalystSourceResult,
    candidate: V2SourceSelectionCandidate,
    provenance: V2LedgerProvenance,
    clock: Callable[[], datetime],
) -> V2EvidenceAdmissionSourceResult:
    source = analyst_source
    state = source.state
    if state is V2EvidenceAnalystState.NOT_QUEUED:
        return V2EvidenceAdmissionSourceResult(
            run_id=analyst_result.run_id,
            source_id=source.source_id,
            direction=source.direction,
            state=V2EvidenceAdmissionState.NOT_QUEUED,
            provenance=provenance,
        )
    if state is V2EvidenceAnalystState.REJECTED:
        return V2EvidenceAdmissionSourceResult(
            run_id=analyst_result.run_id,
            source_id=source.source_id,
            direction=source.direction,
            state=V2EvidenceAdmissionState.ANALYST_REJECTED,
            provenance=provenance,
        )
    if state is V2EvidenceAnalystState.FAILED:
        return V2EvidenceAdmissionSourceResult(
            run_id=analyst_result.run_id,
            source_id=source.source_id,
            direction=source.direction,
            state=V2EvidenceAdmissionState.ANALYST_FAILED,
            provenance=provenance,
            failure=source.failure or "Analyst failed before evidence admission.",
        )
    if state is not V2EvidenceAnalystState.READY_FOR_ADMISSION:
        return V2EvidenceAdmissionSourceResult(
            run_id=analyst_result.run_id,
            source_id=source.source_id,
            direction=source.direction,
            state=V2EvidenceAdmissionState.ANALYST_FAILED,
            provenance=provenance,
            failure="Analyst result is not eligible for fresh analyzer admission.",
        )
    try:
        record = _build_record(
            analyst_result=analyst_result,
            source=source,
            candidate=candidate,
            provenance=provenance,
            clock=clock,
        )
        insert_v2_evidence_admission(db_path, record, provenance)
        return V2EvidenceAdmissionSourceResult(
            run_id=analyst_result.run_id,
            source_id=source.source_id,
            direction=source.direction,
            state=V2EvidenceAdmissionState.ANALYZER_ADMITTED,
            provenance=provenance,
            evidence_record=record,
        )
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return V2EvidenceAdmissionSourceResult(
            run_id=analyst_result.run_id,
            source_id=source.source_id,
            direction=source.direction,
            state=V2EvidenceAdmissionState.ANALYST_FAILED,
            provenance=provenance,
            failure=f"Deterministic admission failed: {exc}"[:1000],
        )


def _build_record(
    *,
    analyst_result: V2EvidenceAnalystBatchResult,
    source: V2EvidenceAnalystSourceResult,
    candidate: V2SourceSelectionCandidate,
    provenance: V2LedgerProvenance,
    clock: Callable[[], datetime],
) -> V2EvidenceAdmissionRecord:
    if source.candidate is None or source.assessment is None or source.score_decision is None:
        raise ValueError("Analyzer-approved source is missing deterministic input artifacts")
    if source.statement_draft is None:
        raise ValueError("Analyzer-approved source is missing its final factual statement")
    if source.candidate.source_url != candidate.source_url:
        raise ValueError("Analyst candidate does not match the selected survivor")
    verify_candidate_against_snapshot(
        next(
            item.snapshot
            for item in analyst_result.input.queued_candidates
            if item.source_id == source.source_id
        ),
        source.candidate,
    )
    score = source.score_decision
    assessment = source.assessment
    statement = source.statement_draft
    if not score.approved or score.ledger_score is None or score.placement is None:
        raise ValueError("only an approved score decision may enter evidence")
    if assessment.canonical_factual_statement != statement.draft_statement:
        raise ValueError("admitted statement must match the Analyst final factual statement")
    if (
        score.claim_fit == 2
        or score.placement is Placement.QUALIFIED_ONLY
        or (score.claim_fit == 3 and score.placement is Placement.QUALIFIED_ONLY)
    ):
        if not statement_has_required_qualification(statement.draft_statement):
            raise ValueError("qualified evidence requires an explicit scope qualification")
    claim_id = uuid5(
        NAMESPACE_URL,
        f"{V2_EVIDENCE_ADMISSION_POLICY_IDENTITY}::{analyst_result.run_id}::"
        f"{source.source_id}::{statement.draft_statement}",
    )
    admitted_at = _aware(clock())
    return V2EvidenceAdmissionRecord(
        run_id=analyst_result.run_id,
        ledger_claim_id=claim_id,
        quote_block_id=source.candidate.quote_block_id,
        stance=source.candidate.stance,
        approved_factual_statement=statement.draft_statement,
        approved_claim_text=source.candidate.extracted_quote_block,
        evidence_quality=score.evidence_quality,
        claim_fit=score.claim_fit,
        ledger_score=score.ledger_score,
        placement=score.placement,
        entailment=entailment_for_claim_fit(score.claim_fit),
        source_url=source.candidate.source_url,
        retrieval_attempt_id=source.candidate.retrieval_attempt_id,
        snapshot_id=source.candidate.snapshot_id,
        snapshot_sha256=source.candidate.snapshot_sha256,
        segment_offsets=source.candidate.segment_offsets,
        analyst_prompt_version=score.analyst_prompt_version,
        analyst_model_name=score.analyst_model_name,
        analyst_completed_at=score.scored_at,
        admission_method=V2AdmissionMethod.ANALYZER_ADMITTED,
        admission_policy_identity=V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
        admitted_at=admitted_at,
        ledger_validated_at=admitted_at,
    )


def _provenance(
    candidate: V2SourceSelectionCandidate,
    status: V2DeepAnalysisSourceStatus,
) -> V2LedgerProvenance:
    return V2LedgerProvenance(
        source_id=candidate.source_id,
        research_direction=candidate.direction,
        discovery_round=candidate.research_round,
        source_family_id=candidate.source_family_id,
        recommended=status.recommended,
        relevant_gap_ids=status.gap_ids,
    )


def _source_artifact_key(source_id: UUID) -> str:
    return f"{V2_EVIDENCE_ADMISSION_SOURCE_ARTIFACT_PREFIX}-{source_id}"


def _read_source_result(
    db_path: str,
    run_id: UUID,
    source_id: UUID,
) -> V2EvidenceAdmissionSourceResult | None:
    for artifact_key in (
        _source_artifact_key(source_id),
        f"{V2_EVIDENCE_ADMISSION_SOURCE_LEGACY_PREFIX}-{source_id}",
    ):
        payload = _read_artifact(db_path, run_id, artifact_key)
        if payload is None:
            continue
        result = V2EvidenceAdmissionSourceResult.model_validate_json(payload)
        if result.state is V2EvidenceAdmissionState.NOT_QUEUED:
            continue
        return result
    return None


def _read_artifact(db_path: str, run_id: UUID, artifact_key: str) -> str | None:
    try:
        return read_v2_artifact(db_path, run_id, artifact_key).payload_json
    except KeyError:
        return None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evidence admission timestamps must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
