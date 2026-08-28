from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_v2_phase9_luna_evidence_analyst import (
    NOW,
    FakeLunaAnalyst,
    _assessment,
    _batch_input,
    _prepare_db,
    _routing,
)

from agents.v2_adaptive_search import V2AdaptiveContinuationResult
from agents.v2_evidence_admission import (
    V2_EVIDENCE_ADMISSION_SOURCE_ARTIFACT_PREFIX,
    run_v2_evidence_admission,
)
from agents.v2_evidence_analyst import (
    V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX,
    run_v2_evidence_analyst,
)
from agents.v2_final_output import _result_sources, build_v2_synthesizer_input
from models import (
    V2AdmissionMethod,
    V2DeepAnalysisBudgetReason,
    V2EvidenceAdmissionState,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystState,
    V2SourceSelectionRecommendation,
)
from store import read_v2_artifact, read_v2_evidence_admission


def test_analyzer_admission_has_no_reviewer_metadata_and_enters_synthesis(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    provider = FakeLunaAnalyst([_assessment()])
    db_path = _prepare_db(tmp_path, run_id)

    analyst = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    admission = run_v2_evidence_admission(
        db_path=db_path,
        analyst_result=analyst,
        clock=lambda: NOW,
    )

    assert len(provider.requests) == 1
    assert analyst.source_results[0].state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    source = admission.source_results[0]
    assert source.state is V2EvidenceAdmissionState.ANALYZER_ADMITTED
    assert source.evidence_record is not None
    record = source.evidence_record
    assert record.admission_method is V2AdmissionMethod.ANALYZER_ADMITTED
    assert record.reviewer_prompt_version is None
    assert record.reviewer_model_name is None
    assert record.reviewed_at is None
    assert record.reviewer_approval_id is None
    restored, provenance = read_v2_evidence_admission(db_path, record.ledger_claim_id)
    assert restored == record
    assert provenance == source.provenance

    synthesis_input = build_v2_synthesizer_input(
        admission,
        _continuation(run_id),
    )
    assert synthesis_input.approved_ledger_items[0].admission_method is (
        V2AdmissionMethod.ANALYZER_ADMITTED
    )
    assert synthesis_input.approved_ledger_items[0].reviewer_approval_id is None


def test_rejected_and_failed_sources_never_create_evidence_records(tmp_path: Path) -> None:
    rejected_run_id = uuid4()
    rejected_batch = _batch_input(rejected_run_id)
    rejected_dir = tmp_path / "rejected"
    rejected_dir.mkdir()
    rejected_analyst = run_v2_evidence_analyst(
        db_path=_prepare_db(rejected_dir, rejected_run_id),
        batch_input=rejected_batch,
        llm_provider=FakeLunaAnalyst([_assessment(claim_fit=1)]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    rejected = run_v2_evidence_admission(
        db_path=str(rejected_dir / "phase9.sqlite3"),
        analyst_result=rejected_analyst,
        clock=lambda: NOW,
    )
    assert rejected.source_results[0].state is V2EvidenceAdmissionState.ANALYST_REJECTED
    assert rejected.source_results[0].evidence_record is None
    assert _result_sources(rejected)[0].status.value == "recommended_analyzer_rejected"

    failed_run_id = uuid4()
    failed_batch = _batch_input(failed_run_id).model_copy(
        update={"queued_candidates": (), "extraction_failures": ()}
    )
    failed_dir = tmp_path / "failed"
    failed_dir.mkdir()
    failed_analyst = run_v2_evidence_analyst(
        db_path=_prepare_db(failed_dir, failed_run_id),
        batch_input=failed_batch,
        llm_provider=FakeLunaAnalyst([]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    failed = run_v2_evidence_admission(
        db_path=str(failed_dir / "phase9.sqlite3"),
        analyst_result=failed_analyst,
        clock=lambda: NOW,
    )
    assert failed.source_results[0].state is V2EvidenceAdmissionState.ANALYST_FAILED
    assert failed.source_results[0].evidence_record is None
    assert _result_sources(failed)[0].status.value == "recommended_analyzer_failed"


def test_legacy_reviewer_ready_state_cannot_enter_analyzer_admission(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    db_path = _prepare_db(tmp_path, run_id)
    analyst = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=FakeLunaAnalyst([_assessment()]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    legacy_ready = analyst.source_results[0].model_copy(
        update={"state": V2EvidenceAnalystState.READY_FOR_REVIEWER}
    )
    legacy_result = analyst.model_copy(update={"source_results": (legacy_ready,)})

    admission = run_v2_evidence_admission(
        db_path=db_path,
        analyst_result=legacy_result,
        artifact_key="phase-13-evidence-admission-legacy-state-guard",
        clock=lambda: NOW,
    )

    assert admission.source_results[0].state is V2EvidenceAdmissionState.ANALYST_FAILED
    assert admission.source_results[0].evidence_record is None


def test_per_source_artifacts_prevent_not_queued_collisions_and_resume_cleanly(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    base = _batch_input(run_id)
    first_survivor = base.queue_result.input.survivors[0]
    second_id = uuid4()
    second_survivor = first_survivor.model_copy(
        update={"source_id": second_id, "source_family_id": "family-second"}
    )
    selection_input = base.queue_result.input.model_copy(
        update={"survivors": (first_survivor, second_survivor)}
    )
    recommendation = V2SourceSelectionRecommendation(
        source_id=second_id,
        rationale="A second independent source fixture.",
    )
    queue = base.queue_result.model_copy(
        update={
            "input": selection_input,
            "recommended_source_ids": (first_survivor.source_id, second_id),
            "recommendation_rationales": (
                base.queue_result.recommendation_rationales[0],
                recommendation,
            ),
            "queued_source_ids": (first_survivor.source_id, second_id),
            "source_statuses": (
                base.queue_result.source_statuses[0],
                base.queue_result.source_statuses[0].model_copy(
                    update={
                        "source_id": second_id,
                        "recommendation_rank": 2,
                        "selection_rationale": recommendation.rationale,
                    }
                ),
            ),
            "queue_capacity": 2,
            "physical_calls_after_reserve": base.queue_result.physical_calls_after_reserve + 3,
            "token_reservations": (
                *base.queue_result.token_reservations,
                base.queue_result.token_reservations[0].model_copy(
                    update={
                        "source_id": second_id,
                        "queue_size": 2,
                        "cumulative_reserved_tokens": (
                            base.queue_result.token_reservations[0].cumulative_reserved_tokens * 2
                        ),
                        "cumulative_reserved_cost_usd": (
                            base.queue_result.token_reservations[0].cumulative_reserved_cost_usd * 2
                        ),
                    }
                ),
            ),
        }
    )
    candidate = base.queued_candidates[0]
    batch = base.model_copy(
        update={
            "queue_result": queue,
            "queued_candidates": (
                candidate,
                V2EvidenceAnalystCandidateInput(
                    source_id=second_id,
                    direction=second_survivor.direction,
                    candidate=candidate.candidate,
                    snapshot=candidate.snapshot,
                ),
            ),
        }
    )

    def single_source_batch(source_id: UUID) -> tuple[str, V2EvidenceAnalystBatchInput]:
        statuses = tuple(
            status.model_copy(
                update={
                    "queued_for_deep_analysis": status.source_id == source_id,
                    "queue_rank": 1 if status.source_id == source_id else None,
                    "budget_prevented_reason": (
                        None
                        if status.source_id == source_id
                        else V2DeepAnalysisBudgetReason.BACKFILL_REPLACED
                    ),
                }
            )
            for status in queue.source_statuses
        )
        single_queue = queue.model_copy(
            update={
                "queued_source_ids": (source_id,),
                "source_statuses": statuses,
                "queue_capacity": 1,
                "physical_calls_after_reserve": queue.physical_calls_after_reserve - 3,
                "total_reserved_tokens": queue.token_reservations[0].cumulative_reserved_tokens,
                "total_reserved_cost_usd": queue.token_reservations[0].cumulative_reserved_cost_usd,
                "token_reservations": (
                    queue.token_reservations[0].model_copy(update={"source_id": source_id}),
                ),
            }
        )
        selected_candidate = next(
            item for item in batch.queued_candidates if item.source_id == source_id
        )
        return (
            f"phase-13-luna-evidence-analyst-batch-source-{source_id}",
            batch.model_copy(
                update={
                    "queue_result": single_queue,
                    "queued_candidates": (selected_candidate,),
                }
            ),
        )

    first_artifact_key, first_batch = single_source_batch(first_survivor.source_id)
    second_artifact_key, second_batch = single_source_batch(second_id)
    db_path = _prepare_db(tmp_path, run_id)
    provider = FakeLunaAnalyst([_assessment(), _assessment()])
    first_analyst = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=first_batch,
        llm_provider=provider,
        routing_config=_routing(),
        artifact_key=first_artifact_key,
        clock=lambda: NOW,
    )

    assert first_analyst.source_results[0].state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    assert first_analyst.source_results[1].state is V2EvidenceAnalystState.NOT_QUEUED
    assert read_v2_artifact(
        db_path,
        run_id,
        f"{V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX}-{first_survivor.source_id}",
    )
    with pytest.raises(KeyError):
        read_v2_artifact(
            db_path, run_id, f"{V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX}-{second_id}"
        )

    first_admission = run_v2_evidence_admission(
        db_path=db_path,
        analyst_result=first_analyst,
        artifact_key=f"phase-13-evidence-admission-batch-source-{first_survivor.source_id}",
        clock=lambda: NOW,
    )
    assert first_admission.source_results[0].evidence_record is not None
    assert first_admission.source_results[1].evidence_record is None

    second_analyst = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=second_batch,
        llm_provider=provider,
        routing_config=_routing(),
        artifact_key=second_artifact_key,
        clock=lambda: NOW,
    )
    assert len(provider.requests) == 2
    assert second_analyst.source_results[0].state is V2EvidenceAnalystState.NOT_QUEUED
    assert second_analyst.source_results[1].state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    assert read_v2_artifact(
        db_path, run_id, f"{V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX}-{second_id}"
    )

    second_admission = run_v2_evidence_admission(
        db_path=db_path,
        analyst_result=second_analyst,
        artifact_key=f"phase-13-evidence-admission-batch-source-{second_id}",
        clock=lambda: NOW,
    )
    assert second_admission.source_results[0].evidence_record is None
    assert second_admission.source_results[1].evidence_record is not None
    assert read_v2_artifact(
        db_path, run_id, f"{V2_EVIDENCE_ADMISSION_SOURCE_ARTIFACT_PREFIX}-{second_id}"
    )


def _continuation(run_id: UUID) -> V2AdaptiveContinuationResult:
    from test_v2_phase11_final_output import _continuation as build_continuation

    return build_continuation(run_id)
