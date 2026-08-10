from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from cli import CLIExitCode, _exit_for_status, _print_provider_result, main
from frontend.live_service import LiveResearchController, exit_code_for_status
from models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    ProviderRunContract,
    RunManifest,
    RunStatus,
    Stage,
)
from orchestrator import (
    ProviderPipelineResult,
    ProviderRunStatus,
    summarize_model_usage,
)
from provider_contract import canonical_provider_contract_payload
from store import (
    ModelAttemptBudgetError,
    finish_model_route_attempt,
    init_db,
    insert_provider_run_contract,
    insert_run,
    read_provider_run_contract,
    reserve_model_route_attempt,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)
RUN_ID = UUID("9d620030-d758-4e8e-b6d4-d4f02ff9d00f")
IDENTITIES = {
    "fingerprint_version": "mvp6.4-evidence-density-fingerprint-v1",
    "provider_identity": "provider-v1",
    "adapter_identity": "adapter-v1",
    "model_identity": "model-v1",
    "prompt_identity": "prompt-v1",
    "schema_identity": "schema-v1",
    "normalization_identity": "normalization-v1",
    "policy_identity": "policy-v1",
    "repository_revision": "source-sha256:" + "a" * 64,
}


def _manifest(run_id: UUID = RUN_ID) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_claim="Exact active claim",
        current_stage=Stage.EVIDENCE_ANALYST,
        created_at=NOW,
        updated_at=NOW,
    )


def _attempt(
    index: int,
    *,
    status: ModelAttemptStatus = ModelAttemptStatus.COMPLETED,
    usage: ModelUsageMetadata | None = None,
    reserved_tokens: int | None = 100,
    reserved_cost_usd: Decimal | None = Decimal("0.1"),
    route_index: int = 0,
) -> ModelRouteAttempt:
    started = NOW + timedelta(seconds=index)
    finished = status is not ModelAttemptStatus.RUNNING
    return ModelRouteAttempt(
        run_id=RUN_ID,
        operation_id=UUID(int=100 + index),
        attempt_id=UUID(int=200 + index),
        stage="planner",
        output_type="PlannerOutput",
        model_alias="mimo-v2.5-pro" if route_index == 0 else "minimax-m3",
        route_index=route_index,
        attempt_number=index + 1,
        input_artifact_ids=(UUID(int=300 + index),),
        status=status,
        failure_code="timeout" if status is ModelAttemptStatus.FAILED else None,
        failure_reason="request timed out" if status is ModelAttemptStatus.FAILED else None,
        started_at=started,
        ended_at=started + timedelta(seconds=1) if finished else None,
        latency_ms=1000 if finished else None,
        reserved_tokens=reserved_tokens,
        reserved_cost_usd=reserved_cost_usd,
        usage=usage,
        output_json="{}" if status is ModelAttemptStatus.COMPLETED else None,
    )


def _running_result() -> ProviderPipelineResult:
    return ProviderPipelineResult(
        run_id=RUN_ID,
        status=ProviderRunStatus.RUNNING,
        raw_claim="Exact active claim",
        db_path="/tmp/active.sqlite3",
        current_stage=Stage.EVIDENCE_ANALYST,
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ProviderRunStatus.RELEASED, CLIExitCode.RELEASED),
        (ProviderRunStatus.BLOCKED, CLIExitCode.BLOCKED),
        (ProviderRunStatus.FAILED, CLIExitCode.FAILED),
        (ProviderRunStatus.CANCELLED, CLIExitCode.CANCELLED),
        (ProviderRunStatus.RUNNING, CLIExitCode.RUNNING),
    ],
)
def test_every_provider_status_has_one_explicit_exit_code(
    status: ProviderRunStatus, expected: CLIExitCode
) -> None:
    assert _exit_for_status(status) == expected
    assert exit_code_for_status(status) == expected


def test_unknown_status_cannot_fall_through_to_success() -> None:
    with pytest.raises(ValueError, match="unsupported provider run status"):
        _exit_for_status(object())  # type: ignore[arg-type]


def test_running_result_prints_stage_without_release_implication(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _print_provider_result(_running_result()) == CLIExitCode.RUNNING
    output = capsys.readouterr().out
    assert "status: running" in output
    assert "current stage: evidence_analyst" in output
    assert "final brief:" not in output
    assert "released" not in output.lower()


def test_active_inspection_subprocess_returns_running_exit_code(tmp_path: Path) -> None:
    db_path = tmp_path / "active.sqlite3"
    init_db(str(db_path))
    insert_run(str(db_path), _manifest())

    result = subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), "inspect-run", str(db_path), str(RUN_ID)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == CLIExitCode.RUNNING
    assert "status: running" in result.stdout
    assert "current stage: evidence_analyst" in result.stdout
    assert "final brief:" not in result.stdout


def test_zero_attempt_accounting_is_exact_and_complete() -> None:
    summary = summarize_model_usage(())
    assert summary.exact_total_tokens == 0
    assert summary.exact_total_cost_usd == 0
    assert summary.known_token_subtotal == 0
    assert summary.known_cost_subtotal_usd == 0
    assert summary.token_complete is True
    assert summary.cost_complete is True
    assert summary.missing_token_attempt_ids == ()
    assert summary.missing_cost_attempt_ids == ()


def test_complete_attempts_aggregate_exact_usage() -> None:
    attempts = (
        _attempt(
            0,
            usage=ModelUsageMetadata(
                input_tokens=2, output_tokens=3, total_tokens=5, cost_usd=0.01
            ),
        ),
        _attempt(
            1,
            usage=ModelUsageMetadata(
                input_tokens=7, output_tokens=11, total_tokens=18, cost_usd=0.02
            ),
        ),
    )
    summary = summarize_model_usage(attempts)
    assert summary.exact_total_tokens == 23
    assert summary.exact_total_cost_usd == Decimal("0.03")
    assert summary.known_token_subtotal == 23
    assert summary.known_cost_subtotal_usd == Decimal("0.03")
    assert summary.token_complete and summary.cost_complete


def test_total_tokens_are_derived_only_from_complete_input_and_output_fields() -> None:
    derived = _attempt(
        0,
        usage=ModelUsageMetadata(
            input_tokens=8, output_tokens=13, total_tokens=None, cost_usd=0.01
        ),
    )
    partial = _attempt(
        1,
        usage=ModelUsageMetadata(
            input_tokens=8, output_tokens=None, total_tokens=None, cost_usd=0.02
        ),
    )
    derived_summary = summarize_model_usage((derived,))
    mixed_summary = summarize_model_usage((derived, partial))

    assert derived_summary.exact_total_tokens == 21
    assert derived_summary.token_complete is True
    assert mixed_summary.exact_total_tokens is None
    assert mixed_summary.known_token_subtotal == 21
    assert mixed_summary.missing_token_attempt_ids == (partial.attempt_id,)
    assert mixed_summary.conservative_reserved_tokens == 121


def test_mixed_unknown_cost_is_not_presented_as_an_exact_total() -> None:
    known = _attempt(
        0,
        usage=ModelUsageMetadata(total_tokens=10, cost_usd=0.04),
    )
    unknown = _attempt(
        1,
        usage=ModelUsageMetadata(total_tokens=20, cost_usd=None),
        reserved_cost_usd=Decimal("0.2"),
    )
    summary = summarize_model_usage((known, unknown))
    assert summary.exact_total_cost_usd is None
    assert summary.known_cost_subtotal_usd == Decimal("0.04")
    assert summary.cost_complete is False
    assert summary.missing_cost_attempt_ids == (unknown.attempt_id,)
    assert summary.conservative_reserved_cost_usd == Decimal("0.24")


@pytest.mark.parametrize("status", [ModelAttemptStatus.FAILED, ModelAttemptStatus.RUNNING])
def test_failed_timed_out_and_running_attempts_are_not_assumed_free(
    status: ModelAttemptStatus,
) -> None:
    attempt = _attempt(0, status=status, usage=None)
    summary = summarize_model_usage((attempt,))
    assert summary.exact_total_tokens is None
    assert summary.exact_total_cost_usd is None
    assert summary.known_token_subtotal == 0
    assert summary.known_cost_subtotal_usd == 0
    assert summary.conservative_reserved_tokens == 100
    assert summary.conservative_reserved_cost_usd == Decimal("0.1")


def test_pipeline_compatibility_totals_are_exact_only() -> None:
    no_attempts = _running_result()
    assert no_attempts.total_tokens == 0
    assert no_attempts.total_cost_usd == 0

    incomplete_attempt = _attempt(0, status=ModelAttemptStatus.RUNNING, usage=None)
    incomplete = _running_result().model_copy(update={"model_attempts": (incomplete_attempt,)})
    with pytest.raises(ValidationError):
        ProviderPipelineResult.model_validate(incomplete.model_dump())


def test_cli_and_web_inspection_label_incomplete_usage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "incomplete-display.sqlite3"
    init_db(str(db_path))
    insert_run(str(db_path), _manifest())
    reserve_model_route_attempt(
        str(db_path), _attempt(0, status=ModelAttemptStatus.RUNNING), max_model_calls=4
    )

    assert main(["inspect-run", str(db_path), str(RUN_ID)]) == CLIExitCode.RUNNING
    output = capsys.readouterr().out
    assert "exact total tokens: unknown (usage incomplete)" in output
    assert "known token subtotal: 0" in output
    assert "exact total cost usd: unknown (usage incomplete)" in output
    snapshot = LiveResearchController(environment={}).snapshot(db_path, RUN_ID)
    assert snapshot.token_usage_complete is False
    assert snapshot.cost_usage_complete is False
    assert snapshot.total_tokens is None
    assert snapshot.total_cost_usd is None
    assert snapshot.known_token_subtotal == 0
    assert snapshot.known_cost_subtotal_usd == 0


def test_unknown_usage_with_reservation_is_retained_for_next_atomic_budget_check(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "reserved.sqlite3"
    init_db(str(db_path))
    insert_run(str(db_path), _manifest())
    first = _attempt(0, status=ModelAttemptStatus.RUNNING, usage=None)
    reserve_model_route_attempt(
        str(db_path), first, max_model_calls=4, max_total_tokens=200, max_total_cost_usd=0.2
    )
    finish_model_route_attempt(
        str(db_path),
        _attempt(0, status=ModelAttemptStatus.FAILED, usage=None),
    )
    second = _attempt(1, status=ModelAttemptStatus.RUNNING, usage=None)

    reserved = reserve_model_route_attempt(
        str(db_path), second, max_model_calls=4, max_total_tokens=200, max_total_cost_usd=0.2
    )
    assert reserved.attempt_id == second.attempt_id


def test_unknown_usage_without_reservation_refuses_retry_or_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "unprovable.sqlite3"
    init_db(str(db_path))
    insert_run(str(db_path), _manifest())
    first = _attempt(
        0,
        status=ModelAttemptStatus.RUNNING,
        usage=None,
        reserved_tokens=None,
        reserved_cost_usd=None,
    )
    reserve_model_route_attempt(str(db_path), first, max_model_calls=4)
    finish_model_route_attempt(
        str(db_path),
        _attempt(
            0,
            status=ModelAttemptStatus.FAILED,
            usage=None,
            reserved_tokens=None,
            reserved_cost_usd=None,
        ),
    )
    fallback = _attempt(1, status=ModelAttemptStatus.RUNNING, route_index=1)

    with pytest.raises(
        ModelAttemptBudgetError,
        match="usage is incomplete.*remaining token budget cannot be proven",
    ):
        reserve_model_route_attempt(
            str(db_path),
            fallback,
            max_model_calls=4,
            max_total_tokens=500,
            max_total_cost_usd=1.0,
        )


def _contract(
    payload_json: str | None = None, fingerprint: str | None = None
) -> ProviderRunContract:
    canonical = payload_json or canonical_provider_contract_payload(IDENTITIES)
    return ProviderRunContract(
        run_id=RUN_ID,
        fingerprint_sha256=fingerprint or sha256(canonical.encode("utf-8")).hexdigest(),
        provider_identity=IDENTITIES["provider_identity"],
        adapter_identity=IDENTITIES["adapter_identity"],
        model_identity=IDENTITIES["model_identity"],
        prompt_identity=IDENTITIES["prompt_identity"],
        schema_identity=IDENTITIES["schema_identity"],
        normalization_identity=IDENTITIES["normalization_identity"],
        policy_identity=IDENTITIES["policy_identity"],
        repository_revision=IDENTITIES["repository_revision"],
        payload_json=canonical,
        created_at=NOW,
    )


def test_valid_contract_is_frozen_and_round_trips() -> None:
    contract = _contract()
    with pytest.raises(ValidationError):
        contract.provider_identity = "changed"  # type: ignore[misc]
    assert ProviderRunContract.model_validate_json(contract.model_dump_json()) == contract


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        '{"fingerprint_version":"v1","fingerprint_version":"v2"}',
        json.dumps(
            {key: value for key, value in IDENTITIES.items() if key != "policy_identity"},
            sort_keys=True,
            separators=(",", ":"),
        ),
        json.dumps(
            {**IDENTITIES, "extra_identity": "no"},
            sort_keys=True,
            separators=(",", ":"),
        ),
    ],
)
def test_contract_rejects_invalid_duplicate_missing_and_extra_payloads(payload: str) -> None:
    with pytest.raises(ValidationError):
        _contract(payload_json=payload)


@pytest.mark.parametrize(
    "field",
    [
        "provider_identity",
        "adapter_identity",
        "model_identity",
        "prompt_identity",
        "schema_identity",
        "normalization_identity",
        "policy_identity",
        "repository_revision",
    ],
)
def test_every_duplicated_contract_identity_is_checked(field: str) -> None:
    payload = canonical_provider_contract_payload({**IDENTITIES, field: "mismatch"})
    with pytest.raises(ValidationError, match=field):
        _contract(payload_json=payload)


def test_contract_rejects_wrong_hash_and_noncanonical_bytes() -> None:
    canonical = canonical_provider_contract_payload(IDENTITIES)
    with pytest.raises(ValidationError, match="fingerprint_sha256"):
        _contract(payload_json=canonical, fingerprint="0" * 64)
    noncanonical = json.dumps(IDENTITIES, sort_keys=False, indent=2)
    with pytest.raises(ValidationError, match="canonical"):
        _contract(
            payload_json=noncanonical,
            fingerprint=sha256(noncanonical.encode("utf-8")).hexdigest(),
        )


def test_persisted_contract_tampering_fails_on_read(tmp_path: Path) -> None:
    db_path = tmp_path / "tampered.sqlite3"
    init_db(str(db_path))
    insert_run(str(db_path), _manifest())
    insert_provider_run_contract(str(db_path), _contract())
    tampered = canonical_provider_contract_payload(
        {**IDENTITIES, "repository_revision": "source-sha256:" + "b" * 64}
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE provider_run_contracts SET payload_json = ? WHERE run_id = ?",
            (tampered, str(RUN_ID)),
        )

    with pytest.raises(ValidationError, match="repository_revision"):
        read_provider_run_contract(str(db_path), RUN_ID)
