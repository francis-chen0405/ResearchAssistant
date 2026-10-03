"""Regression cases for live v2 usage and pre-persistence worker outcomes."""

from __future__ import annotations

import json
from concurrent.futures import Future
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from frontend.live_contracts import LiveRunSnapshot, ResearchProgress
from frontend.live_service import (
    LiveResearchController,
    _ActiveRun,
    _DatabaseLock,
)
from providers.v2_budget import (
    V2BudgetSnapshot,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2RunCeilings,
)
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ModelUsageCostBasis,
    ResearchDirections,
    RunManifest,
    RunStatus,
    Stage,
    V2PipelineIdentity,
)
from researchassistant.research.v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_FINGERPRINT_KEY,
    V2ProductionFingerprint,
    V2ProductionPipelineResult,
    V2ProductionState,
)
from researchassistant.storage.store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    open_read_only_store,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _initialize_run(
    db_path: Path,
    *,
    status: RunStatus,
    directions: ResearchDirections,
    run_id: UUID,
) -> None:
    init_db(str(db_path))
    insert_run(
        str(db_path),
        RunManifest(
            run_id=run_id,
            status=status,
            raw_claim="A precise claim",
            current_stage=Stage.ADAPTIVE_SEARCH,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(db_path), run_id, V2PipelineIdentity(), NOW)
    payload = {
        "directions": directions.model_dump(mode="json"),
        "providers": [DiscoveryProvider.EXA.value],
        "ceilings": V2RunCeilings().model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = V2ProductionFingerprint(
        run_id=run_id,
        sha256="a" * 64,
        canonical_payload_json=canonical,
        created_at=NOW,
    )
    insert_v2_artifact(str(db_path), V2_PRODUCTION_FINGERPRINT_KEY, fingerprint, NOW)


def _insert_call_audit(db_path: Path, run_id: UUID) -> None:
    starts = (
        V2PhysicalCallStart(
            run_id=run_id,
            sequence=1,
            stage="planner",
            model_alias="gpt-6-luna-xhigh",
            reserved_tokens=100,
            reserved_cost_usd=Decimal("0.010"),
            started_at=NOW,
        ),
        V2PhysicalCallStart(
            run_id=run_id,
            sequence=2,
            stage="scout",
            model_alias="gpt-6-luna-high",
            reserved_tokens=200,
            reserved_cost_usd=Decimal("0.020"),
            started_at=NOW,
        ),
    )
    completions = (
        V2PhysicalCallCompletion(
            run_id=run_id,
            sequence=1,
            succeeded=True,
            usage_tokens=12,
            usage_cost_usd=Decimal("0.003"),
            completed_at=NOW,
        ),
        V2PhysicalCallCompletion(
            run_id=run_id,
            sequence=2,
            succeeded=False,
            usage_tokens=None,
            usage_cost_usd=Decimal("0.005"),
            failure="usage tokens unavailable",
            completed_at=NOW,
        ),
    )
    for start, completion in zip(starts, completions, strict=True):
        insert_v2_artifact(
            str(db_path),
            f"phase-13-physical-call-{start.sequence:03d}-start",
            start,
            NOW,
        )
        insert_v2_artifact(
            str(db_path),
            f"phase-13-physical-call-{completion.sequence:03d}-completion",
            completion,
            NOW,
        )
    uncompleted = V2PhysicalCallStart(
        run_id=run_id,
        sequence=3,
        stage="source_selection",
        model_alias="gpt-6-luna-xhigh",
        reserved_tokens=300,
        reserved_cost_usd=Decimal("0.030"),
        started_at=NOW,
    )
    insert_v2_artifact(
        str(db_path),
        "phase-13-physical-call-003-start",
        uncompleted,
        NOW,
    )


def _inconsistent_terminal_result(run_id: UUID, db_path: Path) -> V2ProductionPipelineResult:
    return V2ProductionPipelineResult(
        run_id=run_id,
        db_path=str(db_path),
        raw_claim="A precise claim",
        state=V2ProductionState.FAILED,
        current_stage=Stage.ADAPTIVE_SEARCH,
        failure_reason="fixture failure before release",
        budget=V2BudgetSnapshot(
            physical_calls_used=3,
            token_exposure=999,
            cost_exposure_usd=Decimal("9.99"),
            physical_calls_remaining=157,
            tokens_remaining=499001,
            cost_remaining_usd=Decimal("0"),
        ),
        completed_at=NOW,
    )


def _early_failed_snapshot(db_path: Path, run_id: UUID) -> LiveRunSnapshot:
    return LiveRunSnapshot(
        run_id=run_id,
        db_path=str(db_path),
        raw_claim="A precise claim",
        classification="failed",
        exit_code=1,
        stage="startup",
        message="Worker failed before persisting the run.",
        diagnostic_component="startup",
        model_calls_used=0,
        retrieval_attempts_used=0,
        supporting=ResearchProgress(
            stance="supporting",
            status="not started",
            model_attempts=0,
            retrieval_attempts=0,
            usable_snapshots=0,
            candidates=0,
        ),
        opposing=ResearchProgress(
            stance="opposing",
            status="not started",
            model_attempts=0,
            retrieval_attempts=0,
            usable_snapshots=0,
            candidates=0,
        ),
    )


@pytest.mark.parametrize("terminal", (False, True))
def test_v2_snapshot_uses_physical_audit_for_exact_and_conservative_usage(
    tmp_path: Path, terminal: bool
) -> None:
    db_path = tmp_path / ("terminal.sqlite3" if terminal else "running.sqlite3")
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=False, challenge_enabled=True)
    _initialize_run(
        db_path,
        status=RunStatus.FAILED if terminal else RunStatus.RUNNING,
        directions=directions,
        run_id=run_id,
    )
    _insert_call_audit(db_path, run_id)
    result = _inconsistent_terminal_result(run_id, db_path)
    if terminal:
        insert_v2_artifact(str(db_path), V2_PRODUCTION_ARTIFACT_KEY, result, NOW)

    controller = LiveResearchController(environment={})
    snapshot = controller.snapshot(db_path, run_id)

    assert snapshot.token_usage_complete is False
    assert snapshot.cost_usage_complete is False
    assert snapshot.total_tokens is None
    assert snapshot.total_cost_usd is None
    assert snapshot.known_token_subtotal == 12
    assert snapshot.known_cost_subtotal_usd == Decimal("0.008")
    assert snapshot.conservative_reserved_tokens == 512
    assert snapshot.conservative_reserved_cost_usd == Decimal("0.038")
    assert snapshot.model_calls_used == 3
    assert snapshot.supporting.status == "disabled"
    assert snapshot.opposing.stance == "opposing"
    if terminal:
        assert snapshot.opposing.status == "failed"
    else:
        assert snapshot.opposing.status == "running"


@pytest.mark.parametrize(
    ("second_cost", "expected_cost", "expected_cost_complete"),
    (
        (Decimal("0.007"), Decimal("0.010"), True),
        (None, Decimal("0.003"), False),
    ),
)
def test_terminal_v2_snapshot_tracks_token_and_cost_completeness_independently(
    tmp_path: Path,
    second_cost: Decimal | None,
    expected_cost: Decimal,
    expected_cost_complete: bool,
) -> None:
    db_path = tmp_path / "complete-audit.sqlite3"
    run_id = uuid4()
    _initialize_run(
        db_path,
        status=RunStatus.FAILED,
        directions=ResearchDirections(support_enabled=False, challenge_enabled=True),
        run_id=run_id,
    )
    for sequence, tokens, cost in (
        (1, 12, Decimal("0.003")),
        (2, 15, second_cost),
    ):
        start = V2PhysicalCallStart(
            run_id=run_id,
            sequence=sequence,
            stage="adaptive_search",
            model_alias="gpt-6-luna-xhigh",
            reserved_tokens=100 * sequence,
            reserved_cost_usd=Decimal(f"0.0{sequence}"),
            started_at=NOW,
        )
        completion = V2PhysicalCallCompletion(
            run_id=run_id,
            sequence=sequence,
            succeeded=True,
            usage_tokens=tokens,
            input_tokens=tokens - 2,
            output_tokens=2,
            cached_input_tokens=tokens - 2 - 7,
            uncached_input_tokens=7,
            cache_write_tokens=sequence - 1,
            usage_cost_usd=cost,
            usage_cost_basis=ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES,
            completed_at=NOW,
        )
        insert_v2_artifact(str(db_path), f"phase-13-physical-call-{sequence:03d}-start", start, NOW)
        insert_v2_artifact(
            str(db_path), f"phase-13-physical-call-{sequence:03d}-completion", completion, NOW
        )
    result = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=str(db_path),
        raw_claim="A precise claim",
        state=V2ProductionState.FAILED,
        current_stage=Stage.ADAPTIVE_SEARCH,
        failure_reason="fixture failure",
        budget=V2BudgetSnapshot(
            physical_calls_used=2,
            token_exposure=999,
            cost_exposure_usd=Decimal("9.99"),
            physical_calls_remaining=158,
            tokens_remaining=499001,
            cost_remaining_usd=Decimal("0"),
        ),
        completed_at=NOW,
    )
    insert_v2_artifact(str(db_path), V2_PRODUCTION_ARTIFACT_KEY, result, NOW)

    controller = LiveResearchController(environment={})
    with open_read_only_store(db_path) as store:
        snapshot = controller._snapshot_from_v2_result(result, source=store.connection)

    assert snapshot.token_usage_complete is True
    assert snapshot.total_tokens == 27
    assert snapshot.known_token_subtotal == 27
    assert snapshot.cost_usage_complete is expected_cost_complete
    assert snapshot.total_cost_usd == (expected_cost if expected_cost_complete else None)
    assert snapshot.known_cost_subtotal_usd == expected_cost
    assert snapshot.conservative_reserved_tokens == 27
    assert snapshot.conservative_reserved_cost_usd == (
        expected_cost if expected_cost_complete else Decimal("0.023")
    )
    assert snapshot.model_usage_details is not None
    assert snapshot.model_usage_details.input_tokens.total == 23
    assert snapshot.model_usage_details.input_tokens.complete is True
    assert snapshot.model_usage_details.output_tokens.total == 4
    assert snapshot.model_usage_details.cached_input_tokens.total == 9
    assert snapshot.model_usage_details.cache_write_tokens.total == 1


def test_live_usage_details_keep_partial_splits_and_cost_basis_provenance(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage-details.sqlite3"
    run_id = uuid4()
    _initialize_run(
        db_path,
        status=RunStatus.FAILED,
        directions=ResearchDirections(support_enabled=False, challenge_enabled=True),
        run_id=run_id,
    )
    cases = (
        (
            1,
            V2PhysicalCallCompletion(
                run_id=run_id,
                sequence=1,
                succeeded=True,
                usage_tokens=12,
                input_tokens=10,
                output_tokens=2,
                cached_input_tokens=4,
                uncached_input_tokens=6,
                cache_write_tokens=0,
                usage_cost_usd=Decimal("0.003"),
                usage_cost_basis=ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES,
                completed_at=NOW,
            ),
        ),
        (
            2,
            V2PhysicalCallCompletion(
                run_id=run_id,
                sequence=2,
                succeeded=False,
                usage_tokens=6,
                input_tokens=5,
                output_tokens=1,
                cached_input_tokens=2,
                uncached_input_tokens=3,
                cache_write_tokens=1,
                usage_cost_usd=Decimal("0.005"),
                usage_cost_basis=ModelUsageCostBasis.CONFIGURED_PRICE_CAP,
                failure="semantic output validation failed",
                completed_at=NOW,
            ),
        ),
        (
            4,
            V2PhysicalCallCompletion(
                run_id=run_id,
                sequence=4,
                succeeded=True,
                usage_tokens=5,
                input_tokens=4,
                output_tokens=1,
                cached_input_tokens=1,
                uncached_input_tokens=3,
                usage_cost_usd=Decimal("0.002"),
                usage_cost_basis=(
                    ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_ASSUMED_ALL_UNCACHED_WRITES
                ),
                completed_at=NOW,
            ),
        ),
    )
    for sequence, completion in cases:
        start = V2PhysicalCallStart(
            run_id=run_id,
            sequence=sequence,
            stage="analyst",
            model_alias="gpt-6-luna-xhigh",
            reserved_tokens=20,
            reserved_cost_usd=Decimal("0.01"),
            started_at=NOW,
        )
        insert_v2_artifact(str(db_path), f"phase-13-physical-call-{sequence:03d}-start", start, NOW)
        insert_v2_artifact(
            str(db_path),
            f"phase-13-physical-call-{sequence:03d}-completion",
            completion,
            NOW,
        )
    missing_start = V2PhysicalCallStart(
        run_id=run_id,
        sequence=3,
        stage="analyst",
        model_alias="gpt-6-luna-xhigh",
        reserved_tokens=20,
        reserved_cost_usd=Decimal("0.01"),
        started_at=NOW,
    )
    insert_v2_artifact(str(db_path), "phase-13-physical-call-003-start", missing_start, NOW)

    snapshot = LiveResearchController(environment={}).snapshot(db_path, run_id)

    assert snapshot.model_usage_details is not None
    details = snapshot.model_usage_details
    assert details.input_tokens.known_subtotal == 19
    assert details.input_tokens.total is None
    assert details.input_tokens.complete is False
    assert details.output_tokens.known_subtotal == 4
    assert details.cached_input_tokens.known_subtotal == 7
    assert details.cache_write_tokens.known_subtotal == 1
    assert details.cache_write_tokens.complete is False
    assert tuple((item.basis, item.physical_calls) for item in details.cost_basis_counts) == (
        (None, 1),
        (ModelUsageCostBasis.CONFIGURED_PRICE_CAP, 1),
        (ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_ASSUMED_ALL_UNCACHED_WRITES, 1),
        (ModelUsageCostBasis.PUBLISHED_CACHE_PRICES_REPORTED_WRITES, 1),
    )


@pytest.mark.parametrize(
    ("state", "classification"),
    (
        (V2ProductionState.BLOCKED, "blocked"),
        (V2ProductionState.CANCELLED, "cancelled"),
    ),
)
def test_v2_terminal_snapshot_preserves_terminal_direction_labels(
    tmp_path: Path,
    state: V2ProductionState,
    classification: str,
) -> None:
    db_path = tmp_path / f"{classification}.sqlite3"
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=False, challenge_enabled=True)
    _initialize_run(db_path, status=RunStatus.FAILED, directions=directions, run_id=run_id)
    result = _inconsistent_terminal_result(run_id, db_path).model_copy(update={"state": state})
    insert_v2_artifact(str(db_path), V2_PRODUCTION_ARTIFACT_KEY, result, NOW)

    snapshot = LiveResearchController(environment={}).snapshot(db_path, run_id)

    assert snapshot.classification == classification
    assert snapshot.supporting.status == "disabled"
    assert snapshot.opposing.status == classification


def _missing_inspector(db_path: str, run_id: UUID) -> object:
    raise KeyError(f"run {run_id} is not persisted in {db_path}")


def test_completed_pre_persistence_failure_remains_pollable_with_existing_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "existing.sqlite3"
    init_db(str(db_path))
    run_id = uuid4()
    controller = LiveResearchController(environment={}, inspector=_missing_inspector)
    snapshot = _early_failed_snapshot(db_path, run_id)
    future: Future[LiveRunSnapshot] = Future()
    future.set_result(snapshot)
    key = (str(db_path.resolve()), run_id)
    controller._active[key] = _ActiveRun(future, _DatabaseLock(db_path.resolve()))

    controller._evict_completed_run(key, future)

    assert controller.snapshot(db_path, run_id) == snapshot
    assert controller.snapshot(db_path, run_id) == snapshot


def test_terminal_v2_progress_preserves_direction_and_incomplete_usage(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "terminal-progress.sqlite3"
    run_id = uuid4()
    _initialize_run(
        db_path,
        status=RunStatus.FAILED,
        directions=ResearchDirections(support_enabled=False, challenge_enabled=True),
        run_id=run_id,
    )
    _insert_call_audit(db_path, run_id)

    snapshot = LiveResearchController(environment={}).snapshot(db_path, run_id)

    assert snapshot.classification == "failed"
    assert snapshot.supporting.status == "disabled"
    assert snapshot.opposing.status == "failed"
    assert snapshot.total_tokens is None
    assert snapshot.total_cost_usd is None
    assert snapshot.known_token_subtotal == 12
    assert snapshot.known_cost_subtotal_usd == Decimal("0.008")
