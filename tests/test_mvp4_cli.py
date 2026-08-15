from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from cli import CLIExitCode

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests" / "mvp4_subprocess_driver.py"
CLAIM = "The fixture policy improves student outcomes."
SECRET = "mvp4-test-secret-value"


def _environment(
    db_path: Path,
    run_id: UUID,
    *,
    scenario: str = "released",
    repository_identity: str = "source-sha256:" + "a" * 64,
) -> dict[str, str]:
    return {
        **os.environ,
        "MIMO_API_KEY": SECRET,
        "EXA_API_KEY": "exa-test-secret",
        "OPENALEX_API_KEY": "openalex-test-secret",
        "MIMO_BASE_URL": "https://api.xiaomimimo.com/v1",
        "MIMO_MODEL": "mimo-v2.5-pro",
        "MVP4_DB_PATH": str(db_path),
        "MVP4_RUN_ID": str(run_id),
        "MVP4_MOCK_SCENARIO": scenario,
        "MVP4_REPOSITORY_IDENTITY": repository_identity,
    }


def _command(db_path: Path, run_id: UUID, claim: str = CLAIM) -> list[str]:
    return [
        sys.executable,
        str(DRIVER),
        "run",
        claim,
        "--db-path",
        str(db_path),
        "--run-id",
        str(run_id),
        "--max-tokens",
        "1000000",
        "--max-cost-usd",
        "1.00",
    ]


def _run(
    tmp_path: Path,
    *,
    scenario: str = "released",
    claim: str = CLAIM,
    run_id: UUID | None = None,
    repository_identity: str = "source-sha256:" + "a" * 64,
) -> subprocess.CompletedProcess[str]:
    resolved_run_id = run_id or uuid4()
    db_path = tmp_path / "mvp4.sqlite3"
    return subprocess.run(
        _command(db_path, resolved_run_id, claim),
        cwd=ROOT,
        env=_environment(
            db_path,
            resolved_run_id,
            scenario=scenario,
            repository_identity=repository_identity,
        ),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    ("scenario", "exit_code", "status_text"),
    [
        ("released", CLIExitCode.RELEASED, "status: released"),
        ("blocked", CLIExitCode.BLOCKED, "status: blocked"),
        ("failed", CLIExitCode.FAILED, "status: failed"),
    ],
)
def test_run_subprocess_uses_stable_terminal_exit_codes(
    tmp_path: Path,
    scenario: str,
    exit_code: CLIExitCode,
    status_text: str,
) -> None:
    result = _run(tmp_path, scenario=scenario)

    assert result.returncode == exit_code
    assert status_text in result.stdout
    if scenario == "released":
        assert "final brief:" in result.stdout
        assert "rendered hash:" in result.stdout
    elif scenario == "blocked":
        assert "validation errors:" in result.stdout
        assert "rendered hash: none" in result.stdout
    else:
        assert "failed stage:" in result.stdout
        assert "reason:" in result.stdout


def test_run_subprocess_validates_configuration_before_creating_database(tmp_path: Path) -> None:
    db_path = tmp_path / "missing-config.sqlite3"
    environment = {**os.environ}
    environment.pop("MIMO_API_KEY", None)
    result = subprocess.run(
        _command(db_path, uuid4()),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == CLIExitCode.CONFIGURATION_ERROR
    assert "configuration error:" in result.stderr
    assert not db_path.exists()


def test_run_subprocess_rejects_invalid_input_and_budget(tmp_path: Path) -> None:
    run_id = uuid4()
    db_path = tmp_path / "invalid.sqlite3"
    empty = subprocess.run(
        _command(db_path, run_id, "   "),
        cwd=ROOT,
        env=_environment(db_path, run_id),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    excessive = subprocess.run(
        [*_command(db_path, run_id)[:-2], "1.01"],
        cwd=ROOT,
        env=_environment(db_path, run_id),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert empty.returncode == CLIExitCode.INVALID_INPUT
    assert excessive.returncode == CLIExitCode.INVALID_INPUT
    assert not db_path.exists()


@pytest.mark.parametrize(
    ("option", "value", "expected_reason"),
    [
        ("--max-tokens", "100", "token budget"),
        ("--max-cost-usd", "0.000001", "cost budget"),
    ],
)
def test_budget_failure_is_failed_without_a_physical_call(
    tmp_path: Path,
    option: str,
    value: str,
    expected_reason: str,
) -> None:
    run_id = uuid4()
    db_path = tmp_path / "budget.sqlite3"
    command = _command(db_path, run_id)
    command[command.index(option) + 1] = value
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=_environment(db_path, run_id),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == CLIExitCode.FAILED
    assert expected_reason in result.stdout
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_route_attempts").fetchone()[0] == 0


@pytest.mark.parametrize("firecrawl_enabled", [False, True])
def test_launch_reports_current_stack_and_never_discloses_secrets(
    tmp_path: Path,
    firecrawl_enabled: bool,
) -> None:
    run_id = uuid4()
    db_path = tmp_path / "mvp4.sqlite3"
    environment = _environment(db_path, run_id)
    firecrawl_secret = "firecrawl-test-secret"
    if firecrawl_enabled:
        environment["FIRECRAWL_API_KEY"] = firecrawl_secret
        environment["FIRECRAWL_BASE_URL"] = "https://firecrawl.example.test"
    environment["EXA_BASE_URL"] = "https://exa.example.test"
    environment["WIGOLO_BASE_URL"] = "http://127.0.0.1:8123"
    result = subprocess.run(
        _command(db_path, run_id),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    db_bytes = db_path.read_bytes()

    assert result.returncode == CLIExitCode.RELEASED
    assert (
        "approved provider stack: Exa Search auto discovery + Wigolo 0.2.1 primary "
        "acquisition + optional Firecrawl fallback + direct Xiaomi MiMo"
    ) in result.stdout
    assert "exa discovery endpoint: https://exa.example.test" in result.stdout
    assert "wigolo endpoint: http://127.0.0.1:8123" in result.stdout
    expected_firecrawl = "enabled" if firecrawl_enabled else "disabled"
    assert f"firecrawl acquisition fallback: {expected_firecrawl}" in result.stdout
    if firecrawl_enabled:
        assert "firecrawl endpoint: https://firecrawl.example.test" in result.stdout
    else:
        assert "firecrawl endpoint:" not in result.stdout
    assert "mimo endpoint: https://api.xiaomimimo.com/v1" in result.stdout
    assert "model alias: mimo-v2.5-pro" in result.stdout
    assert SECRET not in result.stdout
    assert SECRET not in result.stderr
    assert SECRET.encode() not in db_bytes
    assert "exa-test-secret" not in result.stdout
    assert "exa-test-secret" not in result.stderr
    assert b"exa-test-secret" not in db_bytes
    assert firecrawl_secret not in result.stdout
    assert firecrawl_secret not in result.stderr
    assert firecrawl_secret.encode() not in db_bytes


def test_inspect_run_reports_authoritative_audit_and_release(tmp_path: Path) -> None:
    run_id = uuid4()
    run = _run(tmp_path, run_id=run_id)
    assert run.returncode == CLIExitCode.RELEASED

    inspected = subprocess.run(
        [sys.executable, "cli.py", "inspect-run", str(tmp_path / "mvp4.sqlite3"), str(run_id)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert inspected.returncode == CLIExitCode.RELEASED
    for expected in (
        f"claim: {CLAIM}",
        "checkpoints:",
        "model attempts:",
        "usage:",
        "provider identity:",
        "prompt identity:",
        "schema identity:",
        "normalization identity:",
        "final brief:",
        "rendered hash:",
    ):
        assert expected in inspected.stdout


def test_restart_reuses_terminal_release_and_rejects_changed_claim_and_identity(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    first = _run(tmp_path, run_id=run_id)
    second = _run(tmp_path, run_id=run_id)
    changed_claim = _run(tmp_path, run_id=run_id, claim="A changed exact claim.")
    changed_identity = _run(
        tmp_path,
        run_id=run_id,
        repository_identity="source-sha256:" + "b" * 64,
    )

    assert first.returncode == second.returncode == CLIExitCode.RELEASED
    assert first.stdout.split("final brief:\n", 1)[1] == second.stdout.split("final brief:\n", 1)[1]
    assert changed_claim.returncode == CLIExitCode.INVALID_INPUT
    assert "different exact claim" in changed_claim.stderr
    assert changed_identity.returncode == CLIExitCode.CONFIGURATION_ERROR
    assert "incompatible fingerprint" in changed_identity.stderr
    with sqlite3.connect(tmp_path / "mvp4.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 14
        assert connection.execute("SELECT COUNT(*) FROM validation_runs").fetchone()[0] == 1


def test_budget_change_requires_new_run_and_never_resets_usage(tmp_path: Path) -> None:
    run_id = uuid4()
    first = _run(tmp_path, run_id=run_id)
    command = _command(tmp_path / "mvp4.sqlite3", run_id)
    command[command.index("--max-tokens") + 1] = "999999"
    changed = subprocess.run(
        command,
        cwd=ROOT,
        env=_environment(tmp_path / "mvp4.sqlite3", run_id),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert first.returncode == CLIExitCode.RELEASED
    assert changed.returncode == CLIExitCode.CONFIGURATION_ERROR
    with sqlite3.connect(tmp_path / "mvp4.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_route_attempts").fetchone()[0] > 0


def test_second_process_cancellation_observes_active_call_boundary(tmp_path: Path) -> None:
    run_id = uuid4()
    db_path = tmp_path / "cancel.sqlite3"
    environment = _environment(db_path, run_id, scenario="second-process-cancel")
    process = subprocess.Popen(
        _command(db_path, run_id),
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if db_path.exists():
            try:
                with sqlite3.connect(db_path) as connection:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM model_route_attempts WHERE status = 'running'"
                    ).fetchone()[0]
                if count == 1:
                    break
            except sqlite3.OperationalError:
                pass
        time.sleep(0.05)
    else:
        process.kill()
        pytest.fail("run never reached an active provider call")

    cancelled = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "cancel-run",
            str(db_path),
            str(run_id),
            "--reason",
            "second process stop",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    stdout, stderr = process.communicate(timeout=20)

    assert cancelled.returncode == CLIExitCode.RELEASED
    assert "persisted: yes" in cancelled.stdout
    assert process.returncode == CLIExitCode.CANCELLED, stderr
    assert "status: cancelled" in stdout
    assert "observed cooperative boundary:" in stdout
    assert "immediate interruption" not in stdout
    with sqlite3.connect(db_path) as connection:
        statuses = connection.execute("SELECT status FROM model_route_attempts").fetchall()
    assert statuses == [("completed",)]


@pytest.mark.skipif(
    os.environ.get("RUN_MVP4_LIVE_CLI_SMOKE") != "1"
    or os.environ.get("MVP4_LIVE_CLI_APPROVED") != "I_APPROVE_ONE_MVP4_LIVE_CLI_RUN",
    reason="requires explicit enable and execution-time approval",
)
def test_optional_budget_capped_live_cli_smoke(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "run",
            "For adults with hypertension, regular aerobic exercise lowers resting "
            "systolic blood pressure.",
            "--db-path",
            str(tmp_path / "live-cli.sqlite3"),
            "--max-tokens",
            "200000",
            "--max-cost-usd",
            "0.15",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert result.returncode in {
        CLIExitCode.RELEASED,
        CLIExitCode.BLOCKED,
        CLIExitCode.FAILED,
    }
