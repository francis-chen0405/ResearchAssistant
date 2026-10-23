"""Admission and source checkpoints commit together and recover old partial prefixes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import pytest
import test_product_discovery_pipeline as product
import test_v2_phase9_luna_evidence_analyst as analyst_fixture

import researchassistant.agents.v2_evidence_admission as admission
from researchassistant.agents.v2_evidence_analyst import run_v2_evidence_analyst
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    V2EvidenceAdmissionSourceResult,
    V2EvidenceAdmissionState,
)
from researchassistant.providers.llm import LLMStage
from researchassistant.research.v2_orchestrator import V2ProductionPipelineResult, V2ProductionState
from researchassistant.storage.store import (
    insert_v2_artifact,
    insert_v2_evidence_admission,
    insert_v2_evidence_admission_checkpoint,
    list_runs,
    read_v2_artifact,
    read_v2_evidence_admission,
)


@pytest.mark.parametrize("legacy_prefix", [False, True])
def test_interruption_preserves_admitted_evidence_on_unchanged_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy_prefix: bool
) -> None:
    path = tmp_path / "generated.sqlite3"
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    entry = product.run_v2_production_pipeline

    def advancing_clock(*args: Any, **kwargs: Any) -> V2ProductionPipelineResult:
        kwargs["clock"] = lambda: datetime.now(UTC)
        return entry(*args, **kwargs)

    monkeypatch.setattr(product, "run_v2_production_pipeline", advancing_clock)
    original = admission.insert_v2_evidence_admission_checkpoint
    captured: list[V2EvidenceAdmissionSourceResult] = []
    mutex = Lock()

    def interrupted_checkpoint(
        database: str, key: str, source: V2EvidenceAdmissionSourceResult, created_at: datetime
    ) -> None:
        with mutex:
            if not captured:
                captured.append(source)
                assert source.evidence_record is not None
                if legacy_prefix:
                    # Construct the previously possible committed relational prefix
                    # using its real public writer, without editing saved artifacts.
                    insert_v2_evidence_admission(
                        database, source.evidence_record, source.provenance
                    )
                else:
                    original(database, key, source, created_at)
                raise KeyboardInterrupt("generated interruption after admission commit")
        original(database, key, source, created_at)

    monkeypatch.setattr(
        admission, "insert_v2_evidence_admission_checkpoint", interrupted_checkpoint
    )
    with pytest.raises(KeyboardInterrupt):
        product._run(path, controls)
    monkeypatch.setattr(admission, "insert_v2_evidence_admission_checkpoint", original)
    partial = list_runs(path)[0]
    source = captured[0]
    assert source.evidence_record is not None and partial.status.value == "running"
    before = read_v2_evidence_admission(path, source.evidence_record.ledger_claim_id)
    result, model, search = product._run(path, controls, run_id=partial.run_id)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    # Initial source work is checkpointed. Only the newly placed Round-4
    # gap, plan and Scout may run after the interrupted admission completes.
    assert [request.stage for request in model.requests] == [
        LLMStage.GAP_ANALYSIS,
        LLMStage.SEARCH_AGENT,
        LLMStage.SCOUT,
    ]
    assert search.requests
    assert all(
        request.compiled_query is not None
        and request.compiled_query.conceptual_query.round_number == 4
        for request in search.requests
    )
    assert read_v2_evidence_admission(path, source.evidence_record.ledger_claim_id) == before
    saved = admission.V2EvidenceAdmissionBatchResult.model_validate_json(
        read_v2_artifact(
            path, partial.run_id, admission.V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
        ).payload_json
    )
    resumed_source = next(
        item for item in saved.source_results if item.source_id == source.source_id
    )
    assert resumed_source.state is V2EvidenceAdmissionState.ANALYZER_ADMITTED
    assert resumed_source.evidence_record == before[0]
    assert result.final_output is not None
    assert source.evidence_record.ledger_claim_id in {
        item.ledger_claim_id
        for section in result.final_output.synthesis.sections
        for item in section.items
    }


def _ready_source(tmp_path: Path) -> tuple[str, V2EvidenceAdmissionSourceResult, dict[str, Any]]:
    run_id = uuid4()
    request = analyst_fixture._batch_input(run_id)
    path = analyst_fixture._prepare_db(tmp_path, run_id)
    result = run_v2_evidence_analyst(
        db_path=path,
        batch_input=request,
        llm_provider=analyst_fixture.FakeLunaAnalyst([analyst_fixture._assessment()]),
        routing_config=analyst_fixture._routing(),
        clock=lambda: analyst_fixture.NOW,
    )
    candidate = request.queue_result.input.survivors[0]
    arguments = dict(
        db_path=path,
        analyst_result=result,
        analyst_source=result.source_results[0],
        candidate=candidate,
        provenance=admission._provenance(candidate, request.queue_result.source_statuses[0]),
        clock=lambda: analyst_fixture.NOW,
    )
    source = admission._admit_source(**arguments)
    assert source.evidence_record is not None
    return path, source, arguments


def test_conflicting_checkpoint_rolls_back_its_relational_admission(tmp_path: Path) -> None:
    path, source, _ = _ready_source(tmp_path)
    assert source.evidence_record is not None
    changed = source.model_copy(
        update={
            "evidence_record": source.evidence_record.model_copy(
                update={
                    "admitted_at": analyst_fixture.NOW + timedelta(seconds=1),
                    "ledger_validated_at": analyst_fixture.NOW + timedelta(seconds=1),
                }
            )
        }
    )
    key = "generated-conflicting-checkpoint"
    insert_v2_artifact(path, key, changed, analyst_fixture.NOW)
    original = read_v2_artifact(path, source.run_id, key)
    with pytest.raises(sqlite3.IntegrityError, match="already exists with different data"):
        insert_v2_evidence_admission_checkpoint(path, key, source, analyst_fixture.NOW)
    with pytest.raises(KeyError):
        read_v2_evidence_admission(path, source.evidence_record.ledger_claim_id)
    assert read_v2_artifact(path, source.run_id, key) == original


def test_recovery_rejects_a_different_saved_admission_without_overwriting_it(
    tmp_path: Path,
) -> None:
    path, source, arguments = _ready_source(tmp_path)
    assert source.evidence_record is not None
    changed = source.evidence_record.model_copy(
        update={
            "approved_factual_statement": "A different statement that does not match the Analyst.",
        }
    )
    insert_v2_evidence_admission(path, changed, source.provenance)
    original = read_v2_evidence_admission(path, changed.ledger_claim_id)
    failed = admission._admit_source(**arguments)
    assert failed.state is V2EvidenceAdmissionState.ANALYST_FAILED
    assert failed.evidence_record is None and "exact Analyst inputs" in failed.failure
    assert read_v2_evidence_admission(path, changed.ledger_claim_id) == original
