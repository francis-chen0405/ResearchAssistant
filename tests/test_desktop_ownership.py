"""Ownership transfer must complete before POSIX acquisition can detach or execute."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from frontend.service_manager import ServiceDiagnostic, WigoloLaunchConfig, WigoloServiceManager
from researchassistant.platform_support import acquisition_supervisor
from researchassistant.platform_support.desktop_ownership import DesktopOwnership


class ReportStream(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.reported = Event()

    def flush(self) -> None:
        self.reported.set()


def test_handoff_requires_matching_pid_and_fresh_request() -> None:
    output = ReportStream()
    ownership = DesktopOwnership(output)
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(ownership, 5000, True)
        try:
            assert output.reported.wait(2)
            report = json.loads(output.getvalue())
            for line in (
                "invalid",
                "[]",
                "null",
                json.dumps({"owned_pid": 5001, "ownership_ack": report["ownership_request"]}),
                json.dumps({"owned_pid": True, "ownership_ack": report["ownership_request"]}),
                json.dumps({"owned_pid": 5000, "ownership_ack": "old-request"}),
            ):
                ownership.accept_acknowledgement(line)
                assert not future.done()
            ownership.accept_acknowledgement(
                json.dumps(
                    {
                        "owned_pid": 5000,
                        "ownership_ack": report["ownership_request"],
                    }
                )
            )
            assert future.result(timeout=2) is None
            assert not ownership._pending
            output.reported.clear()
            replacement = workers.submit(ownership, 5000, True)
            assert output.reported.wait(2)
            fresh = json.loads(output.getvalue().splitlines()[-1])
            assert fresh["ownership_request"] != report["ownership_request"]
            ownership.accept_acknowledgement(
                json.dumps(
                    {
                        "owned_pid": 5000,
                        "ownership_ack": report["ownership_request"],
                    }
                )
            )
            assert not replacement.done()
            ownership.accept_acknowledgement(
                json.dumps(
                    {
                        "owned_pid": 5000,
                        "ownership_ack": fresh["ownership_request"],
                    }
                )
            )
            assert replacement.result(timeout=2) is None
        finally:
            ownership.close()


@pytest.mark.parametrize("closed", [False, True])
def test_unacknowledged_handoff_fails_on_timeout_or_eof(closed: bool) -> None:
    output = ReportStream()
    ownership = DesktopOwnership(output, timeout=0.1 if not closed else 10)
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(ownership, 5000, True)
        try:
            assert output.reported.wait(2)
            if closed:
                ownership.close()
            with pytest.raises(RuntimeError, match="closed" if closed else "timed out"):
                future.result(timeout=2)
            assert not ownership._pending
            ownership.close()
            with pytest.raises(RuntimeError, match="closed"):
                ownership(5001, True)
        finally:
            ownership.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership gate")
@pytest.mark.parametrize("acknowledged", [False, True])
def test_manager_cannot_detach_or_execute_before_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    acknowledged: bool,
) -> None:
    report = Event()
    release = Event()
    marker = tmp_path / "executed"
    launcher = (
        "import pathlib, os, time; "
        "assert 'MIMO_API_KEY' not in os.environ; "
        f"pathlib.Path({str(marker)!r}).write_text(str(os.getpgrp())); time.sleep(30)"
    )

    def handoff(pid: int, owned: bool) -> None:
        if not owned:
            return
        report.set()
        assert release.wait(3)
        if not acknowledged:
            raise RuntimeError("Desktop ownership pipe is closed")

    manager = WigoloServiceManager(
        launch=WigoloLaunchConfig(command=(sys.executable, "-c", launcher), data_dir=tmp_path),
        base_environment={"MIMO_API_KEY": "must-not-inherit"},
        ownership_changed=handoff,
        supervisor_command=(sys.executable, str(Path(acquisition_supervisor.__file__).resolve())),
    )
    monkeypatch.setattr(
        manager,
        "probe",
        lambda: ServiceDiagnostic(
            state="unhealthy",
            wigolo_ready=False,
            searxng_readiness="unavailable",
            message="offline",
        ),
    )
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(manager.start)
        try:
            assert report.wait(3)
            assert manager._owned is not None
            process = manager._owned.process
            assert os.getpgid(process.pid) == os.getpgrp()
            assert not marker.exists()
            release.set()
            result = future.result(timeout=3)
            if acknowledged:
                assert os.getpgid(process.pid) == process.pid, (
                    "Start must establish scoped stop ownership"
                )
                deadline = time.monotonic() + 3
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert marker.read_text() == str(process.pid)
                assert result.state == "starting"
                assert process.stdin is not None and process.stdin.closed
            else:
                assert result.state == "launch_failed"
                assert process.poll() is not None
                assert manager._owned is None
                assert not marker.exists()
        finally:
            release.set()
            manager.stop()


def test_supervisor_eof_never_executes(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    process = subprocess.run(
        [
            sys.executable,
            acquisition_supervisor.__file__,
            sys.executable,
            "-c",
            f"open({str(marker)!r}, 'w').write('unsafe')",
        ],
        input="",
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert process.returncode == 1
    assert not marker.exists()
