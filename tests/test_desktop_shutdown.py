"""Offline desktop ownership regressions; all native processes/data are disposable."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

import pytest

from desktop import backend
from desktop.smoke_support import BackendMonitor
from providers.v2_budget import (
    V2PhysicalCallStart,
    V2RunCeilings,
    _snapshot,
    read_v2_physical_call_audit,
)
from researchassistant.contracts.models import RunManifest, RunStatus, Stage, V2PipelineIdentity
from researchassistant.storage.store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_run,
)


@pytest.mark.parametrize("journal_mode", ["delete", "wal"])
def test_forced_owned_process_preserves_sqlite_unknown_reservation(
    tmp_path: Path, journal_mode: str
) -> None:
    """Kill a writer mid-transaction; never infer completion or refund missing usage."""
    path = tmp_path / "isolated.sqlite3"
    run_id = uuid4()
    now = datetime.now(UTC)
    init_db(path)
    manifest = RunManifest(
        run_id=run_id,
        status=RunStatus.RUNNING,
        raw_claim="Offline shutdown fixture.",
        current_stage=Stage.EVIDENCE_ANALYST,
        created_at=now,
        updated_at=now,
    )
    insert_run(path, manifest)
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), now)
    reservation = V2PhysicalCallStart(
        run_id=run_id,
        sequence=1,
        stage="analyst",
        model_alias="gpt-6-luna-xhigh",
        reserved_tokens=12500,
        reserved_cost_usd=Decimal("0.25"),
        started_at=now,
    )
    insert_v2_artifact(path, "phase-13-physical-call-001-start", reservation, now)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(f"PRAGMA journal_mode={journal_mode}").fetchone()[0] == journal_mode
        )
    before = read_v2_physical_call_audit(path, run_id)
    code = (
        "import sqlite3, sys, time\n"
        "c = sqlite3.connect(sys.argv[1]); c.execute('BEGIN IMMEDIATE')\n"
        "c.execute(\"UPDATE runs SET status='completed' WHERE run_id=?\", (sys.argv[2],))\n"
        "print('ready', flush=True)\n"
        "time.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", code, str(path), str(run_id)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=sys.platform != "win32",
    )
    monitor = BackendMonitor(process, label="isolated SQLite shutdown")
    try:
        assert monitor.startup(timeout=5) == "ready\n"
        if sys.platform == "win32":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) != 0
        monitor.finish_reading()
        assert read_run(path, run_id) == manifest
        after = read_v2_physical_call_audit(path, run_id)
        assert after == before
        assert after.completions == (None,)
        exposure = _snapshot(list(after.starts), {}, V2RunCeilings())
        assert exposure.token_exposure == 12500
        assert exposure.cost_exposure_usd == Decimal("0.25")
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        monitor.finish_reading()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def test_windows_backend_owns_job_before_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    actions: list[str] = []

    class Job:
        def __init__(self) -> None:
            actions.append("create")

        def attach_current_process(self) -> None:
            actions.append("attach")

    def bootstrap(name: str) -> NoReturn:
        assert name == "bootstrap"
        assert actions == ["create", "attach"]
        raise RuntimeError("test stops before bootstrap/data/vault")

    monkeypatch.setattr(backend.sys, "platform", "win32")
    monkeypatch.setattr(backend, "WindowsJob", Job)
    monkeypatch.setattr(backend, "smoke_phase", bootstrap)
    with pytest.raises(RuntimeError, match="test stops before bootstrap"):
        backend.main()


def test_windows_backend_job_failure_prevents_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    class DeniedJob:
        def attach_current_process(self) -> NoReturn:
            raise OSError("job assignment denied")

    def forbidden(name: str) -> NoReturn:
        pytest.fail("Bootstrap must not run without Windows process ownership")

    monkeypatch.setattr(backend.sys, "platform", "win32")
    monkeypatch.setattr(backend, "WindowsJob", DeniedJob)
    monkeypatch.setattr(backend, "smoke_phase", forbidden)
    with pytest.raises(OSError, match="job assignment denied"):
        backend.main()


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows Job Objects")
@pytest.mark.parametrize("forced", [False, True])
def test_native_windows_backend_job_cleans_all_generations(tmp_path: Path, forced: bool) -> None:
    import ctypes
    from ctypes import wintypes

    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "owned_backend.py"
    script.write_text(
        "import json, subprocess, sys, time\n"
        "from researchassistant.platform_support.windows_job import WindowsJob\n"
        "backend_job = WindowsJob(); backend_job.attach_current_process()\n"
        "children = []; jobs = []; pids = []\n"
        'code = ("import subprocess, sys, time; "\n'
        "\"c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); \"\n"
        '"print(c.pid, flush=True); time.sleep(60)")\n'
        "for _ in range(2):\n"
        "    child = subprocess.Popen([sys.executable, '-u', '-c', code], "
        "stdout=subprocess.PIPE, text=True)\n"
        "    job = WindowsJob(); job.attach(int(child._handle)); jobs.append(job)\n"
        "    children.append(child); pids.extend([child.pid, int(child.stdout.readline())])\n"
        "print(json.dumps(pids), flush=True)\n"
        "sys.stdin.read()\n"
        "if '--stuck' in sys.argv: time.sleep(60)\n",
        encoding="utf-8",
    )
    # Exact handles keep the asserted processes identified even after PID recycling.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handles: list[int] = []
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    process = subprocess.Popen(
        [sys.executable, "-u", str(script), *(["--stuck"] if forced else [])],
        cwd=root,
        env={"PYTHONPATH": str(root)},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None and process.stdin is not None
        # communicate-like timeout without waiting for stdin EOF/normal exit.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as reader:
            line = reader.submit(process.stdout.readline)
            try:
                pids = json.loads(line.result(timeout=10))
            except BaseException:
                process.kill()
                raise
        assert len(pids) == 4
        for pid in pids:
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            assert handle
            handles.append(handle)
        process.stdin.close()
        if forced:
            process.kill()  # TerminateProcess on this owned HANDLE, as Electron does.
        process.wait(timeout=5)
        for handle in handles:
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        assert unrelated.poll() is None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        unrelated.kill()
        unrelated.wait(timeout=5)
        for handle in handles:
            kernel.CloseHandle(handle)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
