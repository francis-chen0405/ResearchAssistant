"""Post-round reconciliation bound to admitted evidence and exact Gap provenance."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from researchassistant.agents.round_four_authorization import (
    _validate_round_four_decision_against_gap as _validate_round_four_decision_against_gap,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_GAP_AFTER_ROUND_THREE_KEY as V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_GAP_RECONCILIATION_KEY as V2_POST13_GAP_RECONCILIATION_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY as V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
)
from researchassistant.agents.round_four_handoffs import (
    _read as _read,
)
from researchassistant.agents.round_four_handoffs import (
    _utc_now as _utc_now,
)
from researchassistant.contracts.models import (
    V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
    V2_EVIDENCE_ADMISSION_PREVIOUS_POLICY_IDENTITY,
    V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
    V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY,
    V2_SOURCE_SELECTION_POLICY_IDENTITY,
    ResearchDirection,
    V2AdmissionMethod,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionState,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2GapAnalysisOutput,
    V2GapCoverageReconciliation,
    V2GapCoverageRecord,
    V2GapCoverageState,
    V2LedgerProvenance,
    V2MaterialGap,
    V2RoundFourDecisionCode,
    V2RoundFourGovernorDecision,
    V2SourceSelectionCandidate,
    validate_v2_gap_history_against_material_gaps,
)
from researchassistant.contracts.research_policy import V2_CLAIM_PREVIEW_SELECTION_POLICIES
from researchassistant.storage.store import insert_v2_artifact


def _validate_reconciliation_admission(
    *,
    run_id: UUID,
    gaps: tuple[V2MaterialGap, ...],
    admission_result: V2EvidenceAdmissionBatchResult,
) -> tuple[
    dict[UUID, V2SourceSelectionCandidate],
    dict[UUID, V2EvidenceAnalystSourceResult],
]:
    """Validate every typed identity used by post-Round-3 coverage claims."""
    if admission_result.run_id != run_id:
        raise ValueError("evidence admission batch run_id must match the Gap run")
    policy_pairs = {
        V2_EVIDENCE_ADMISSION_POLICY_IDENTITY: V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
        V2_EVIDENCE_ADMISSION_PREVIOUS_POLICY_IDENTITY: (
            V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY
        ),
    }
    if admission_result.policy_identity not in policy_pairs:
        raise ValueError("evidence admission batch uses an unexpected policy identity")

    analyst_result = admission_result.analyst_result
    if analyst_result.run_id != run_id:
        raise ValueError("nested Evidence Analyst batch run_id must match the Gap run")
    if analyst_result.policy_identity != policy_pairs[admission_result.policy_identity]:
        raise ValueError("nested Evidence Analyst batch uses an unexpected policy identity")
    analyst_input = analyst_result.input
    if analyst_input.run_id != run_id:
        raise ValueError("nested Evidence Analyst input run_id must match the Gap run")
    queue_result = analyst_input.queue_result
    if queue_result.run_id != run_id or queue_result.input.run_id != run_id:
        raise ValueError("nested source-selection run IDs must match the Gap run")
    selection_input = queue_result.input
    if selection_input.policy_identity not in {
        V2_SOURCE_SELECTION_POLICY_IDENTITY,
        *V2_CLAIM_PREVIEW_SELECTION_POLICIES,
    }:
        raise ValueError("nested source-selection input uses an unexpected policy identity")

    gap_ids = tuple(gap.gap_id for gap in gaps)
    if len(gap_ids) != len(set(gap_ids)):
        raise ValueError("post-Round-3 Gap IDs must be unique during reconciliation")
    validate_v2_gap_history_against_material_gaps(gaps, selection_input.gap_history)
    history_by_id: dict[str, tuple[ResearchDirection, ...]] = {}
    history_directions: dict[str, set[ResearchDirection]] = {}
    round_three_gap_directions: dict[str, ResearchDirection] = {}
    for history_gap in selection_input.gap_history:
        history_directions.setdefault(history_gap.gap_id, set()).add(history_gap.direction)
        if history_gap.assessed_after_round == 3:
            round_three_gap_directions[history_gap.gap_id] = history_gap.direction
    for gap in gaps:
        if gap.gap_id not in history_directions:
            raise ValueError(
                f"post-Round-3 Gap ID {gap.gap_id!r} is absent from source-selection history"
            )
        if round_three_gap_directions.get(gap.gap_id) is not gap.direction:
            raise ValueError(
                f"post-Round-3 Gap ID {gap.gap_id!r} has mismatched Round-3 provenance"
            )
    for gap_id, directions in history_directions.items():
        history_by_id[gap_id] = tuple(sorted(directions, key=lambda direction: direction.value))

    survivor_ids = tuple(item.source_id for item in selection_input.survivors)
    if len(survivor_ids) != len(set(survivor_ids)):
        raise ValueError("source-selection survivors must have unique source IDs")
    candidate_by_id = {item.source_id: item for item in selection_input.survivors}
    status_ids = tuple(item.source_id for item in queue_result.source_statuses)
    if status_ids != survivor_ids:
        raise ValueError("source-selection statuses must retain every survivor in order")
    status_by_id = {item.source_id: item for item in queue_result.source_statuses}
    for survivor in selection_input.survivors:
        status = status_by_id[survivor.source_id]
        if status.direction is not survivor.direction:
            raise ValueError("source-selection status direction cannot change")
        for gap_id in status.gap_ids:
            directions = history_by_id.get(gap_id)
            if directions is None:
                raise ValueError(f"source-selection status references unknown Gap ID {gap_id!r}")
            if survivor.direction not in directions:
                raise ValueError(
                    f"source-selection status Gap ID {gap_id!r} has mismatched direction"
                )

        for provenance in survivor.search_provenance:
            if provenance.round_number == 4 and survivor.research_round != 4:
                raise ValueError("Round-4 query provenance requires a Round-4 survivor")
            for gap_id in provenance.targeted_gap_ids:
                directions = history_by_id.get(gap_id)
                if directions is None:
                    raise ValueError(f"search provenance references unknown Gap ID {gap_id!r}")
                query_direction = provenance.direction or survivor.direction
                if query_direction not in directions:
                    raise ValueError(
                        f"search provenance Gap ID {gap_id!r} has mismatched direction"
                    )

    analyst_ids = tuple(item.source_id for item in analyst_result.source_results)
    if analyst_ids != survivor_ids:
        raise ValueError("Evidence Analyst results must retain every survivor in order")
    admission_ids = tuple(item.source_id for item in admission_result.source_results)
    if admission_ids != survivor_ids:
        raise ValueError("Evidence admission results must retain every survivor in order")

    candidate_inputs: dict[UUID, V2EvidenceAnalystCandidateInput] = {}
    for candidate_input in analyst_input.queued_candidates:
        if candidate_input.source_id in candidate_inputs:
            raise ValueError("Evidence Analyst candidate inputs must have unique source IDs")
        candidate_inputs[candidate_input.source_id] = candidate_input
        survivor = candidate_by_id.get(candidate_input.source_id)
        if survivor is None:
            raise ValueError("Evidence Analyst candidate input references an unknown survivor")
        if candidate_input.direction is not survivor.direction:
            raise ValueError("Evidence Analyst candidate direction cannot change")
        if candidate_input.candidate.run_id != run_id or candidate_input.snapshot.run_id != run_id:
            raise ValueError(
                "nested evidence candidate and snapshot run IDs must match the Gap run"
            )
        if candidate_input.candidate.source_url != survivor.source_url:
            raise ValueError("Evidence Analyst candidate source URL does not match the survivor")
        if candidate_input.snapshot.source_url != survivor.source_url:
            raise ValueError("Evidence Analyst snapshot source URL does not match the survivor")
        if not any(
            item.query_id == candidate_input.candidate.query_id
            and item.round_number == candidate_input.candidate.query_round
            for item in survivor.search_provenance
        ):
            raise ValueError("Evidence Analyst candidate query ID is absent from search provenance")

    for analyst_source in analyst_result.source_results:
        if analyst_source.run_id != run_id:
            raise ValueError("nested Evidence Analyst source run_id must match the Gap run")
        survivor = candidate_by_id[analyst_source.source_id]
        if analyst_source.direction is not survivor.direction:
            raise ValueError("Evidence Analyst source direction cannot change")
        if analyst_source.candidate is not None:
            candidate_input = candidate_inputs.get(analyst_source.source_id)
            if candidate_input is None or analyst_source.candidate != candidate_input.candidate:
                raise ValueError("Evidence Analyst source must retain its exact candidate input")
        if analyst_source.assessment is not None:
            for gap_id in analyst_source.assessment.addressed_gap_ids:
                directions = history_by_id.get(gap_id)
                if directions is None:
                    raise ValueError(f"Analyst assessment references unknown Gap ID {gap_id!r}")
                if analyst_source.direction not in directions:
                    raise ValueError(
                        f"Analyst assessment Gap ID {gap_id!r} has mismatched direction"
                    )

    for admission_source in admission_result.source_results:
        if admission_source.run_id != run_id:
            raise ValueError("nested evidence admission source run_id must match the Gap run")
        survivor = candidate_by_id[admission_source.source_id]
        status = status_by_id[admission_source.source_id]
        if admission_source.direction is not survivor.direction:
            raise ValueError("evidence admission source direction cannot change")
        expected_provenance = V2LedgerProvenance(
            source_id=survivor.source_id,
            research_direction=survivor.direction,
            discovery_round=survivor.research_round,
            source_family_id=survivor.source_family_id,
            recommended=status.recommended,
            relevant_gap_ids=status.gap_ids,
        )
        if admission_source.provenance != expected_provenance:
            raise ValueError(
                "evidence admission Round-4 provenance does not match source selection"
            )
        for gap_id in admission_source.provenance.relevant_gap_ids:
            directions = history_by_id.get(gap_id)
            if directions is None:
                raise ValueError(
                    f"evidence admission provenance references unknown Gap ID {gap_id!r}"
                )
            if admission_source.direction not in directions:
                raise ValueError(
                    f"evidence admission provenance Gap ID {gap_id!r} has mismatched direction"
                )
        analyst_source = analyst_result.source_results[survivor_ids.index(survivor.source_id)]
        if admission_source.state is V2EvidenceAdmissionState.ANALYZER_ADMITTED:
            if analyst_source.state is not V2EvidenceAnalystState.READY_FOR_ADMISSION:
                raise ValueError(
                    "analyzer-admitted evidence must come from an admission-ready Analyst result"
                )
            if analyst_source.assessment is None or analyst_source.score_decision is None:
                raise ValueError("analyzer-admitted evidence requires complete Analyst scoring")
            if analyst_source.statement_draft is None or analyst_source.candidate is None:
                raise ValueError("analyzer-admitted evidence requires a complete Analyst candidate")
            if not set(analyst_source.assessment.addressed_gap_ids).issubset(
                admission_source.provenance.relevant_gap_ids
            ):
                raise ValueError("Analyst addressed Gap IDs do not match evidence provenance")
            record = admission_source.evidence_record
            candidate_input = candidate_inputs.get(survivor.source_id)
            if record is None or candidate_input is None:
                raise ValueError("analyzer-admitted evidence requires its exact candidate input")
            candidate = candidate_input.candidate
            if record.run_id != run_id:
                raise ValueError("nested evidence record run_id must match the Gap run")
            if record.admission_method is not V2AdmissionMethod.ANALYZER_ADMITTED:
                raise ValueError("Round-4 reconciliation requires analyzer-admitted evidence")
            if record.admission_policy_identity != admission_result.policy_identity:
                raise ValueError("evidence record admission policy must match its batch")
            if record.quote_block_id != candidate.quote_block_id:
                raise ValueError(
                    "evidence record quote_block_id does not match the Analyst candidate"
                )
            if record.source_url != candidate.source_url:
                raise ValueError("evidence record source URL does not match the Analyst candidate")
            if record.retrieval_attempt_id != candidate.retrieval_attempt_id:
                raise ValueError(
                    "evidence record retrieval ID does not match the Analyst candidate"
                )
            if record.snapshot_id != candidate.snapshot_id:
                raise ValueError("evidence record snapshot ID does not match the Analyst candidate")
            if record.snapshot_sha256 != candidate.snapshot_sha256:
                raise ValueError(
                    "evidence record snapshot hash does not match the Analyst candidate"
                )
            if tuple(record.segment_offsets) != tuple(candidate.segment_offsets):
                raise ValueError(
                    "evidence record segment offsets do not match the Analyst candidate"
                )
            if record.stance is not candidate.stance:
                raise ValueError("evidence record stance does not match the Analyst candidate")
            if record.approved_claim_text != candidate.extracted_quote_block:
                raise ValueError("evidence record quote text does not match the Analyst candidate")
            if record.approved_factual_statement != analyst_source.statement_draft.draft_statement:
                raise ValueError("evidence record statement does not match the Analyst draft")
            score = analyst_source.score_decision
            if (
                record.evidence_quality != score.evidence_quality
                or record.claim_fit != score.claim_fit
                or record.ledger_score != score.ledger_score
                or record.placement is not score.placement
            ):
                raise ValueError("evidence record scoring does not match the Analyst decision")
            expected_ledger_claim_id = uuid5(
                NAMESPACE_URL,
                f"{admission_result.policy_identity}::{run_id}::"
                f"{survivor.source_id}::{analyst_source.statement_draft.draft_statement}",
            )
            if record.ledger_claim_id != expected_ledger_claim_id:
                raise ValueError("evidence record ledger_claim_id does not match its typed inputs")
        elif admission_source.evidence_record is not None:
            raise ValueError("non-admitted evidence cannot carry a nested evidence record")

    return candidate_by_id, {item.source_id: item for item in analyst_result.source_results}


def reconcile_post_round_three_gaps(
    *,
    db_path: str | Path,
    post_round_three_gap: V2GapAnalysisOutput,
    admission_result: V2EvidenceAdmissionBatchResult,
    clock: Callable[[], datetime] | None = None,
) -> V2GapCoverageReconciliation:
    """Mark only Round-4 analyzer-admitted evidence with exact Gap provenance as coverage."""
    if not isinstance(admission_result, V2EvidenceAdmissionBatchResult):
        raise TypeError("reconciliation requires a V2EvidenceAdmissionBatchResult")
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    gaps = post_round_three_gap.result.material_gaps if post_round_three_gap.result else ()
    candidates_by_id, analyst_sources_by_id = _validate_reconciliation_admission(
        run_id=post_round_three_gap.run_id,
        gaps=gaps,
        admission_result=admission_result,
    )
    persisted = _read(path, post_round_three_gap.run_id, V2_POST13_GAP_RECONCILIATION_KEY)
    if persisted is not None:
        reconciliation = V2GapCoverageReconciliation.model_validate_json(persisted)
        if reconciliation.round_four_governor_decision is not None:
            _validate_round_four_decision_against_gap(
                gap=post_round_three_gap,
                decision=reconciliation.round_four_governor_decision,
            )
        return reconciliation
    governor_payload = _read(path, post_round_three_gap.run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY)
    governor = (
        V2RoundFourGovernorDecision.model_validate_json(governor_payload)
        if governor_payload is not None
        else None
    )
    if governor is not None:
        _validate_round_four_decision_against_gap(gap=post_round_three_gap, decision=governor)
    round_four_attempted = bool(governor and governor.authorized)
    unavailable = bool(
        governor
        and governor.reason_code
        in {
            V2RoundFourDecisionCode.INSUFFICIENT_RESERVATION,
            V2RoundFourDecisionCode.GAP_ANALYSIS_UNUSABLE,
            V2RoundFourDecisionCode.NO_ELIGIBLE_PROVIDER,
        }
    )
    records: list[V2GapCoverageRecord] = []
    source_results = admission_result.source_results
    for gap in gaps:
        match = next(
            (
                source
                for source in source_results
                if source.evidence_record is not None
                and source.direction is gap.direction
                and source.provenance.discovery_round == 4
                and gap.gap_id in source.provenance.relevant_gap_ids
                and gap.gap_id
                in analyst_sources_by_id[source.source_id].assessment.addressed_gap_ids
            ),
            None,
        )
        if match is None:
            records.append(
                V2GapCoverageRecord(
                    gap=gap,
                    state=(
                        V2GapCoverageState.UNRESOLVED
                        if round_four_attempted
                        else (
                            V2GapCoverageState.UNAVAILABLE
                            if unavailable
                            else V2GapCoverageState.NOT_ATTEMPTED
                        )
                    ),
                )
            )
            continue
        query_id = next(
            (
                item.query_id
                for candidate in candidates_by_id.values()
                if candidate.source_id == match.source_id
                for item in candidate.search_provenance
                if item.round_number == 4 and gap.gap_id in item.targeted_gap_ids
            ),
            None,
        )
        if query_id is None:
            records.append(V2GapCoverageRecord(gap=gap, state=V2GapCoverageState.UNRESOLVED))
        else:
            records.append(
                V2GapCoverageRecord(
                    gap=gap,
                    state=V2GapCoverageState.COVERED,
                    source_id=match.source_id,
                    query_id=query_id,
                    ledger_claim_id=match.evidence_record.ledger_claim_id,
                )
            )
    result = V2GapCoverageReconciliation(
        run_id=post_round_three_gap.run_id,
        post_round_three_gap_artifact_key=V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
        round_four_attempted=round_four_attempted,
        records=tuple(records),
        claim_coverage_map=(
            post_round_three_gap.result.claim_coverage_map
            if post_round_three_gap.result is not None
            else ()
        ),
        round_four_governor_decision=governor,
        completed_at=now(),
    )
    insert_v2_artifact(path, V2_POST13_GAP_RECONCILIATION_KEY, result, result.completed_at)
    return result
