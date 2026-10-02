"""Read-only CLI inspection must recognize persisted fresh-v2 run identity."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

from application_runtime import CLIExitCode
from cli import _inspect_run_command
from models import (
    DiscoveryProvider,
    ResearchDirections,
    RunManifest,
    RunStatus,
    Stage,
    V2PipelineIdentity,
    V2ProviderRunDiagnostics,
    V2RunDiagnostics,
)
from providers.v2_budget import (
    V2BudgetSnapshot,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2RunCeilings,
)
from store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
)
from v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_FINGERPRINT_KEY,
    V2ProductionFingerprint,
    V2ProductionPipelineResult,
    V2ProductionState,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _initialize_v2_run(db_path: Path, run_id: UUID, status: RunStatus) -> None:
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
        "directions": ResearchDirections().model_dump(mode="json"),
        "providers": [DiscoveryProvider.EXA.value],
        "ceilings": V2RunCeilings().model_dump(mode="json"),
    }
    fingerprint = V2ProductionFingerprint(
        run_id=run_id,
        sha256="b" * 64,
        canonical_payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        created_at=NOW,
    )
    insert_v2_artifact(str(db_path), V2_PRODUCTION_FINGERPRINT_KEY, fingerprint, NOW)


def _insert_started_call(db_path: Path, run_id: UUID, sequence: int) -> None:
    insert_v2_artifact(
        str(db_path),
        f"phase-13-physical-call-{sequence:03d}-start",
        V2PhysicalCallStart(
            run_id=run_id,
            sequence=sequence,
            stage="claim_planner",
            model_alias="gpt-6-luna-xhigh",
            reserved_tokens=100 * sequence,
            reserved_cost_usd=Decimal(f"0.0{sequence}"),
            started_at=NOW,
        ),
        NOW,
    )


def _inspect(db_path: Path, run_id: UUID) -> tuple[int, str]:
    output = StringIO()
    with redirect_stdout(output):
        exit_code = _inspect_run_command(db_path, run_id)
    return int(exit_code), output.getvalue()


def test_inspect_v2_running_run_reports_actual_subtotals_and_reservations(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "v2-running.sqlite3"
    run_id = uuid4()
    _initialize_v2_run(db_path, run_id, RunStatus.RUNNING)
    _insert_started_call(db_path, run_id, 1)
    insert_v2_artifact(
        str(db_path),
        "phase-13-physical-call-001-completion",
        V2PhysicalCallCompletion(
            run_id=run_id,
            sequence=1,
            succeeded=True,
            usage_tokens=12,
            usage_cost_usd=Decimal("0.003"),
            completed_at=NOW,
        ),
        NOW,
    )
    _insert_started_call(db_path, run_id, 2)

    exit_code, output = _inspect(db_path, run_id)

    assert exit_code == CLIExitCode.RUNNING
    assert "physical model calls: 2" in output
    assert "exact total tokens: unknown (usage incomplete)" in output
    assert "known token subtotal: 12" in output
    assert "exact total cost usd: unknown (usage incomplete)" in output
    assert "known cost subtotal usd: 0.003" in output
    assert "conservative token exposure: 212" in output
    assert "conservative cost exposure usd: 0.023" in output


def test_inspect_v2_terminal_result_tracks_token_and_cost_completeness_independently(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "v2-terminal.sqlite3"
    run_id = uuid4()
    _initialize_v2_run(db_path, run_id, RunStatus.FAILED)
    for sequence, tokens, cost in (
        (1, 10, Decimal("0.003")),
        (2, 15, None),
    ):
        _insert_started_call(db_path, run_id, sequence)
        insert_v2_artifact(
            str(db_path),
            f"phase-13-physical-call-{sequence:03d}-completion",
            V2PhysicalCallCompletion(
                run_id=run_id,
                sequence=sequence,
                succeeded=True,
                usage_tokens=tokens,
                usage_cost_usd=cost,
                completed_at=NOW,
            ),
            NOW,
        )
    result = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=str(db_path),
        raw_claim="A precise claim",
        state=V2ProductionState.FAILED,
        current_stage=Stage.ADAPTIVE_SEARCH,
        failure_reason="fixture failure",
        diagnostics=V2RunDiagnostics(
            configured_providers=(DiscoveryProvider.EXA,),
            provider_outcomes=(V2ProviderRunDiagnostics(provider=DiscoveryProvider.EXA),),
            acquisition_attempts=3,
            sources_acquired=1,
        ),
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

    exit_code, output = _inspect(db_path, run_id)

    assert exit_code == CLIExitCode.FAILED
    assert "physical model calls: 2" in output
    assert "retrieval attempts: 3" in output
    assert "exact total tokens: 25" in output
    assert "exact total cost usd: unknown (usage incomplete)" in output
    assert "known cost subtotal usd: 0.003" in output
    assert "conservative token exposure: 25" in output
    assert "conservative cost exposure usd: 0.023" in output
