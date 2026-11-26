"""Complete captured report mirrors spend only one deep-analysis envelope."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from test_capture_overlap import _run as _run_progressive
from test_capture_overlap import _Works
from test_query_production import _ConceptModel
from test_v2_phase8_source_selection import NOW, _candidate, _prepare_db, _selection_input
from test_v2_phase12_production import SOURCE_TEXT, _run, _Scraper, _Search, _V2Model

from researchassistant.agents import v2_deep_analysis
from researchassistant.agents.evidence_checkpoint import (
    CHECKPOINT_KEY,
    EarlyAssessment,
    V2EvidenceCheckpoint,
)
from researchassistant.agents.v2_deep_analysis import (
    V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
    V2ExactBodyMirrorPlan,
    _exact_body_mirror_plan,
    exact_body_mirror_policy,
)
from researchassistant.contracts.models import (
    ResearchDirection,
    ResearchDirections,
    V2AcquisitionProbeOutput,
    V2DeepAnalysisBackfillResult,
    V2EvidenceAdmissionBatchResult,
)
from researchassistant.evidence.evidence_core import build_source_snapshot
from researchassistant.providers.llm import LLMStage
from researchassistant.providers.scraper import ScrapeRequest, ScrapeResponse
from researchassistant.storage.store import read_v2_artifact


class _MirroredReport(_Scraper):
    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        return super().scrape(request).model_copy(update={"text": SOURCE_TEXT})


def test_interrupted_mirror_backfill_replays_saved_plan_without_new_model_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, run_id = tmp_path / "mirror-interrupted.sqlite3", uuid4()
    model = _V2Model(completed_rounds=2)
    original = v2_deep_analysis.run_v2_evidence_admission

    class SimulatedProcessExit(BaseException):
        pass

    def interrupt_final_admission(**kwargs: Any) -> V2EvidenceAdmissionBatchResult:
        if kwargs.get("artifact_key") == v2_deep_analysis.V2_EVIDENCE_ADMISSION_ARTIFACT_KEY:
            raise SimulatedProcessExit("fixture interruption before backfill completes")
        return original(**kwargs)

    monkeypatch.setattr(v2_deep_analysis, "run_v2_evidence_admission", interrupt_final_admission)
    with pytest.raises(SimulatedProcessExit):
        _run(path, model, _Search(unique_results=True), _MirroredReport(), run_id=run_id)
    assert sum(request.stage is LLMStage.EXTRACTOR for request in model.requests) == 1
    key = f"{V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY}-exact-body-mirrors-v1"
    saved = read_v2_artifact(path, run_id, key)
    monkeypatch.setattr(v2_deep_analysis, "run_v2_evidence_admission", original)
    replay_model = _V2Model(completed_rounds=2)
    replay = _run(
        path, replay_model, _Search(unique_results=True), _MirroredReport(), run_id=run_id
    )
    assert replay.failure_reason is None
    assert not replay_model.requests
    assert read_v2_artifact(path, run_id, key) == saved


@pytest.mark.parametrize("already_assessed", [False, True])
def test_body_mirror_policy_freezes_new_or_historical_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    already_assessed: bool,
) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    starts = [SimpleNamespace(stage=LLMStage.EXTRACTOR.value)] if already_assessed else []
    monkeypatch.setattr(
        v2_deep_analysis,
        "read_v2_physical_call_audit",
        lambda *args: SimpleNamespace(starts=starts),
    )
    assert exact_body_mirror_policy(str(path), run_id, NOW) is not already_assessed
    starts.append(SimpleNamespace(stage=LLMStage.ANALYST.value))
    assert exact_body_mirror_policy(str(path), run_id, NOW) is not already_assessed


def test_progressive_mirrors_keep_one_early_wave_and_skip_later_backfill(tmp_path: Path) -> None:
    model = _ConceptModel()
    result = _run_progressive(
        tmp_path / "early-mirrors.sqlite3", uuid4(), model, _Works(3), _MirroredReport(), target=5
    )
    assert result.failure_reason is None
    checkpoint = V2EvidenceCheckpoint.model_validate_json(
        read_v2_artifact(
            result.db_path,
            result.run_id,
            CHECKPOINT_KEY,
        ).payload_json
    )
    assert len(checkpoint.waves) == 1
    backfill = V2DeepAnalysisBackfillResult.model_validate_json(
        read_v2_artifact(
            result.db_path,
            result.run_id,
            V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
        ).payload_json
    )
    plan = V2ExactBodyMirrorPlan.model_validate_json(
        read_v2_artifact(
            result.db_path,
            result.run_id,
            f"{V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY}-exact-body-mirrors-v1",
        ).payload_json
    )
    assert plan.enabled and len(plan.mirrors) == 2
    assert backfill.final_execution_order == (checkpoint.waves[0].source_id,)
    assert sum(request.stage is LLMStage.EXTRACTOR for request in model.requests) == 1
    assert sum(request.stage is LLMStage.ANALYST for request in model.requests) == 1

    acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(
            result.db_path,
            result.run_id,
            "phase-5-acquisition-probe",
        ).payload_json
    )
    captures = {
        source.cluster_id: SimpleNamespace(
            survivors=tuple(s for s in acquisition.survivors if s.cluster_id == source.cluster_id),
            acquisitions=(source,),
        )
        for source in acquisition.acquisitions
    }
    coordinator = EarlyAssessment.__new__(EarlyAssessment)
    coordinator.path, coordinator.run_id = result.db_path, result.run_id
    coordinator.clock, coordinator.deduplicate_bodies = lambda: NOW, True
    duplicate, additional = (item.source_id for item in plan.mirrors)
    retained = plan.mirrors[0].retained_source_id
    mirror_key = f"{CHECKPOINT_KEY}/exact-body-mirror/{duplicate}"
    saved = read_v2_artifact(result.db_path, result.run_id, mirror_key)
    # A later capture, changed mapping order, and the source itself must not
    # change the first persisted owner or reinsert with a new timestamp.
    assert not coordinator._unique_work(
        None,
        {
            additional: captures[additional],
            duplicate: captures[duplicate],
            retained: captures[retained],
        },
        duplicate,
        captures[duplicate],
    )
    assert read_v2_artifact(result.db_path, result.run_id, mirror_key) == saved


def test_complete_body_mirrors_preserve_locations_but_make_one_physical_analysis(
    tmp_path: Path,
) -> None:
    model = _V2Model(completed_rounds=2)
    result = _run(
        tmp_path / "mirrors.sqlite3", model, _Search(unique_results=True), _MirroredReport()
    )
    assert result.failure_reason is None
    backfill = V2DeepAnalysisBackfillResult.model_validate_json(
        read_v2_artifact(
            result.db_path, result.run_id, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY
        ).payload_json
    )
    plan = V2ExactBodyMirrorPlan.model_validate_json(
        read_v2_artifact(
            result.db_path,
            result.run_id,
            f"{V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY}-exact-body-mirrors-v1",
        ).payload_json
    )
    assert len(plan.mirrors) >= 1
    assert len(backfill.final_queue_result.input.survivors) == len(plan.mirrors) + 1
    assert len({item.source_url for item in backfill.final_queue_result.input.survivors}) > 1
    assert len(backfill.final_execution_order) == 1
    assert sum(request.stage is LLMStage.EXTRACTOR for request in model.requests) == 1
    assert sum(request.stage is LLMStage.ANALYST for request in model.requests) == 1
    mirror_ids = {item.source_id for item in plan.mirrors}
    for source in result.final_output.all_surviving_sources:
        if source.source_id in mirror_ids:
            assert source.analysis_skip_reason == "exact_body_mirror"
            assert source.budget_prevented_reason is None
            assert source.status.value != "budget_prevented_analysis"
            assert source.ledger_claim_ids == ()
    assert all(
        not item.physical_call_sequences
        for item in backfill.source_executions
        if item.source_id in mirror_ids
    )
    assert {item.source_id for item in backfill.source_executions} == {
        item.source_id for item in backfill.final_queue_result.input.survivors
    }
    replay_model = _V2Model(completed_rounds=2)
    replay = _run(
        Path(result.db_path),
        replay_model,
        _Search(unique_results=True),
        _MirroredReport(),
        run_id=result.run_id,
    )
    assert replay.failure_reason is None
    assert not replay_model.requests


@pytest.mark.parametrize("difference", ["body", "direction", "truncated", "invalid_hash"])
def test_mirror_proof_requires_complete_validated_same_direction_body(difference: str) -> None:
    first, second = uuid4(), uuid4()
    candidates = (
        _candidate(first, family="verona", probe_score=5),
        _candidate(
            second,
            family="natick",
            probe_score=5,
            direction=(
                ResearchDirection.CHALLENGE
                if difference == "direction"
                else ResearchDirection.SUPPORT
            ),
        ),
    )
    selection_input = _selection_input(
        candidates,
        directions=ResearchDirections(
            support_enabled=True,
            challenge_enabled=True,
        ),
    )
    # Matching quoted sentences or report titles alone are insufficient. The
    # independently captured body must match from beginning to end.
    body = (
        "The 2024 Verona Centennial report describes local housing policy. "
        "metric for what field condition makes a field playable, and both natural grass "
        "and artificial turf fields may lose field quality when played on for higher hours. "
        "The appendix records limitations and regional sampling methods."
    )
    snapshots = {
        source_id: build_source_snapshot(
            run_id=selection_input.run_id,
            retrieval_attempt_id=uuid4(),
            snapshot_id=uuid4(),
            source_url=candidate.source_url,
            retrieved_at=NOW,
            created_at=NOW,
            normalized_text=body
            + (" Different appendix." if index and difference == "body" else ""),
            truncated=bool(index and difference == "truncated"),
        )
        for index, (source_id, candidate) in enumerate(
            zip((first, second), candidates, strict=True)
        )
    }
    if difference == "invalid_hash":
        snapshots[second] = snapshots[second].model_copy(update={"snapshot_sha256": "0" * 64})
        with pytest.raises(ValueError, match="snapshot hash"):
            _exact_body_mirror_plan(
                SimpleNamespace(input=selection_input, run_id=selection_input.run_id),
                (first, second),
                snapshots,
                enabled=True,
            )
    else:
        plan = _exact_body_mirror_plan(
            SimpleNamespace(input=selection_input, run_id=selection_input.run_id),
            (first, second),
            snapshots,
            enabled=True,
        )
        assert plan.mirrors == ()
