"""Regression coverage for service-manager ownership after a leader exits."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock

import pytest

import frontend.service_manager as service_manager_module
from frontend.service_manager import ServiceDiagnostic, WigoloLaunchConfig, WigoloServiceManager
from providers.config import WigoloConfig


def _manager_for_child(tmp_path: Path, child_code: str) -> tuple[WigoloServiceManager, Path]:
    pid_file = tmp_path / "child.pid"
    ready_file = tmp_path / "child.ready"
    launcher = (
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        f"ready = {str(ready_file)!r}\n"
        "deadline = time.monotonic() + 5\n"
        "while not __import__('os').path.exists(ready) and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
    )
    manager = WigoloServiceManager(
        config=WigoloConfig(base_url="http://127.0.0.1:1"),
        launch=WigoloLaunchConfig(
            command=(sys.executable, "-c", launcher),
            port=18000,
            require_ownership=True,
            data_dir=tmp_path,
        ),
        base_environment={"PATH": os.environ.get("PATH", "")},
    )
    return manager, pid_file


def _wait_for_exit(manager: WigoloServiceManager, child_pid: Path) -> tuple[int, int]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        owned = manager._owned
        if child_pid.exists() and owned is not None and owned.process.poll() is not None:
            return owned.process.pid, int(child_pid.read_text(encoding="utf-8"))
        time.sleep(0.01)
    raise AssertionError("isolated process leader and child did not start and exit")


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _pid_is_executing(pid: int) -> bool:
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.is_file():
        fields_after_command = proc_stat.read_text(encoding="utf-8").rpartition(")")[2].split()
        if fields_after_command and fields_after_command[0] == "Z":
            return False
    return _pid_exists(pid)


def _cleanup_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _cleanup_manager(manager: WigoloServiceManager, previous_group: int | None = None) -> None:
    owned = manager._owned
    try:
        manager.stop()
    finally:
        if owned is not None:
            _cleanup_group(owned.process.pid)
            try:
                owned.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                owned.process.kill()
                owned.process.wait(timeout=5)
        if previous_group is not None:
            _cleanup_group(previous_group)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group lifecycle")
def test_stop_signals_descendant_after_owned_leader_has_exited(tmp_path: Path) -> None:
    marker = tmp_path / "term-received"
    child_code = (
        "import pathlib, signal, time\n"
        "def on_term(*_):\n"
        f"    pathlib.Path({str(marker)!r}).write_text('yes')\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, on_term)\n"
        f"pathlib.Path({str(tmp_path / 'child.ready')!r}).write_text('ready')\n"
        "time.sleep(30)\n"
    )
    manager, child_file = _manager_for_child(tmp_path, child_code)
    leader_pid: int | None = None
    try:
        started = manager.start()
        leader_pid = started.pid
        _wait_for_exit(manager, child_file)

        manager.stop()

        assert marker.exists(), "stop must signal descendants in the exact owned process group"
    finally:
        _cleanup_manager(manager, leader_pid)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group lifecycle")
def test_stop_kills_sigterm_ignoring_descendant_after_leader_exit(tmp_path: Path) -> None:
    child_code = (
        "import pathlib, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(tmp_path / 'child.ready')!r}).write_text('ready'); time.sleep(30)"
    )
    manager, child_file = _manager_for_child(tmp_path, child_code)
    leader_pid: int | None = None
    try:
        started = manager.start()
        leader_pid = started.pid
        _leader_pid, child_pid = _wait_for_exit(manager, child_file)

        manager.stop()

        deadline = time.monotonic() + 3
        while _pid_is_executing(child_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not _pid_is_executing(child_pid), (
            "stop must escalate when an owned descendant ignores SIGTERM"
        )
    finally:
        _cleanup_manager(manager, leader_pid)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group lifecycle")
def test_restarting_after_leader_exit_retires_old_ownership(tmp_path: Path) -> None:
    child_code = (
        "import pathlib, time; "
        f"pathlib.Path({str(tmp_path / 'child.ready')!r}).write_text('ready'); time.sleep(30)"
    )
    manager, child_file = _manager_for_child(tmp_path, child_code)
    events: list[tuple[int, bool]] = []
    event_lock = Lock()

    def record_ownership(pid: int, owned: bool) -> None:
        with event_lock:
            events.append((pid, owned))

    manager._ownership_changed = record_ownership
    old_leader: int | None = None
    try:
        started = manager.start()
        old_leader = started.pid
        old_leader, _child_pid = _wait_for_exit(manager, child_file)

        manager.start()

        assert events[0] == (old_leader, True)
        assert events[1] == (old_leader, False), "dead ownership must be retired before replacement"
        assert manager._owned is not None and manager._owned.process.pid != old_leader
    finally:
        _cleanup_manager(manager, old_leader)


def test_restarting_after_windows_leader_exit_closes_old_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[tuple[str, int]] = []
    events: list[tuple[int, bool]] = []

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid
            self._handle = pid + 100
            self.stdout = None
            self.stderr = None
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float) -> int:
            self.returncode = 0
            return 0

    class FakeJob:
        def __init__(self) -> None:
            self.pid = 0

        def attach(self, handle: int) -> None:
            self.pid = handle - 100
            actions.append(("attach", self.pid))

        def close(self) -> None:
            actions.append(("close", self.pid))

    processes = iter((FakeProcess(5101), FakeProcess(5102)))

    def popen(command: list[str], **kwargs: object) -> FakeProcess:
        assert kwargs["start_new_session"] is False
        return next(processes)

    def ownership_changed(pid: int, owned: bool) -> None:
        events.append((pid, owned))

    monkeypatch.setattr(service_manager_module.sys, "platform", "win32")
    monkeypatch.setattr(service_manager_module, "WindowsJob", FakeJob)
    manager = WigoloServiceManager(
        popen=popen,
        base_environment={},
        launch=WigoloLaunchConfig(data_dir=tmp_path),
        ownership_changed=ownership_changed,
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

    manager.start()
    assert manager._owned is not None
    manager._owned.process.returncode = 1

    manager.start()

    assert actions == [("attach", 5101), ("close", 5101), ("attach", 5102)]
    assert events == [(5101, True), (5101, False), (5102, True)]

    manager.stop()

    assert actions == [
        ("attach", 5101),
        ("close", 5101),
        ("attach", 5102),
        ("close", 5102),
    ]
    assert events == [(5101, True), (5101, False), (5102, True), (5102, False)]
