"""One validated read snapshot per result or evidence request, closed before projection."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from researchassistant.agents.v2_deep_analysis import V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY
from researchassistant.agents.v2_evidence_admission import V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
)
from researchassistant.agents.v2_reviewer_ledger import V2_REVIEWER_LEDGER_ARTIFACT_KEY
from researchassistant.agents.v2_round_four import (
    V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
)
from researchassistant.api.application_services.evidence_projection import (
    _build_v2_evidence_display,
)
from researchassistant.api.inspection_contracts import V2EvidenceDisplay
from researchassistant.contracts.models import (
    V2DeepAnalysisBackfillResult,
    V2EvidenceAdmissionBatchResult,
    V2FinalResearchOutput,
    V2GapAnalysisOutput,
    V2ReviewerLedgerBatchResult,
    V2RoundFourGovernorDecision,
)
from researchassistant.evidence.released_output import validate_saved_output
from researchassistant.storage.store import open_read_only_store, read_run, read_v2_artifact


def read_result(db_path: str | Path, run_id: UUID) -> V2FinalResearchOutput:
    with open_read_only_store(db_path) as store:
        manifest = read_run(store.connection, run_id)
        try:
            artifact = read_v2_artifact(store.connection, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY)
        except KeyError:
            try:
                artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY
                )
            except KeyError:
                artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY
                )
    if artifact.artifact_type != V2FinalResearchOutput.__name__:
        raise ValueError("v2 final-output artifact has an unexpected type")
    return validate_saved_output(
        V2FinalResearchOutput.model_validate_json(artifact.payload_json), run_id, manifest
    )


def read_evidence(db_path: str | Path, run_id: UUID) -> V2EvidenceDisplay:
    with open_read_only_store(db_path) as store:
        manifest = read_run(store.connection, run_id)
        try:
            final_artifact = read_v2_artifact(
                store.connection, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY
            )
        except KeyError:
            try:
                final_artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY
                )
            except KeyError:
                final_artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY
                )
        try:
            evidence_artifact = read_v2_artifact(
                store.connection, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
            )
            evidence_type = V2EvidenceAdmissionBatchResult
        except KeyError:
            evidence_artifact = read_v2_artifact(
                store.connection, run_id, V2_REVIEWER_LEDGER_ARTIFACT_KEY
            )
            evidence_type = V2ReviewerLedgerBatchResult
        try:
            gap_artifact = read_v2_artifact(
                store.connection, run_id, V2_POST13_GAP_AFTER_ROUND_THREE_KEY
            )
        except KeyError:
            gap_artifact = None
        try:
            governor_artifact = read_v2_artifact(
                store.connection, run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY
            )
        except KeyError:
            governor_artifact = None
        try:
            backfill_artifact = read_v2_artifact(
                store.connection, run_id, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY
            )
        except KeyError:
            backfill_artifact = None
    if final_artifact.artifact_type != V2FinalResearchOutput.__name__:
        raise ValueError("v2 final-output artifact has an unexpected type")
    output = validate_saved_output(
        V2FinalResearchOutput.model_validate_json(final_artifact.payload_json), run_id, manifest
    )
    evidence_result = evidence_type.model_validate_json(evidence_artifact.payload_json)
    gap_analysis = (
        V2GapAnalysisOutput.model_validate_json(gap_artifact.payload_json)
        if gap_artifact is not None
        else None
    )
    governor_decision = (
        V2RoundFourGovernorDecision.model_validate_json(governor_artifact.payload_json)
        if governor_artifact is not None and gap_analysis is not None
        else None
    )
    backfill = (
        V2DeepAnalysisBackfillResult.model_validate_json(backfill_artifact.payload_json)
        if backfill_artifact is not None
        else None
    )
    return _build_v2_evidence_display(
        output,
        evidence_result,
        gap_analysis=gap_analysis,
        governor_decision=governor_decision,
        backfill=backfill,
    )
