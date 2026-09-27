"""Exercise startup races and diagnostics without native vaults or paid providers."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest

from desktop.smoke_support import BackendMonitor, wait_for_health


@contextmanager
def child(code: str) -> Iterator[BackendMonitor]:
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    monitor = BackendMonitor(process, label="test child")
    try:
        yield monitor
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        monitor.finish_reading()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def test_monitor_drains_stderr_before_startup_and_stdout_afterward() -> None:
    code = (
        "import sys\n"
        "sys.stderr.write('sensitive-value' * 100000 + '\\n')\n"
        "print('SMOKE_PHASE:identity', file=sys.stderr, flush=True)\n"
        'print(\'{"origin":"http://127.0.0.1:1"}\', flush=True)\n'
        "sys.stdout.write('ownership event\\n' * 100000)\n"
    )
    with child(code) as monitor:
        assert '"origin"' in monitor.startup(timeout=5)
        monitor.wait_exit(timeout=5)
        assert monitor.phase == "identity"
        assert "sensitive-value" not in str(monitor.failure("test"))


def test_monitor_reports_early_exit_without_raw_secrets() -> None:
    with child("import sys; sys.stderr.write('private-api-key'); sys.exit(7)") as monitor:
        with pytest.raises(RuntimeError, match="exited before startup") as caught:
            monitor.startup(timeout=5)
        assert "private-api-key" not in str(caught.value)
        assert "stderr_characters=15" in str(caught.value)


def test_monitor_timeout_reports_credential_phase() -> None:
    code = (
        "import sys, time\n"
        "print('SMOKE_PHASE:credential-read', file=sys.stderr, flush=True)\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    with child(code) as monitor:
        assert monitor.startup(timeout=5) == "ready\n"
        with pytest.raises(RuntimeError, match="shutdown deadline exceeded") as caught:
            monitor.wait_exit(timeout=0.1)
        assert "phase=credential-read" in str(caught.value)
        with pytest.raises(RuntimeError, match="startup deadline exceeded"):
            monitor.startup(timeout=0.01)


def test_health_waits_for_server_after_startup_announcement() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("not listening yet", request=request)
        if calls == 2:
            return httpx.Response(503)
        return httpx.Response(200)

    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
        wait_for_health(client, timeout=2)
    assert calls == 3


def test_health_fails_auth_without_retry() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(RuntimeError, match="rejected.*401"):
            wait_for_health(client)
    assert calls == 1


def test_health_has_bounded_deadline() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("not ready", request=request)

    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(RuntimeError, match="health deadline exceeded"):
            wait_for_health(client, timeout=0.02)


def test_monitor_rejects_oversized_startup_line() -> None:
    with child("import sys; sys.stdout.write('x' * 100000); sys.stdout.flush()") as monitor:
        with pytest.raises(RuntimeError, match="oversized startup line"):
            monitor.startup(timeout=5)


def test_monitor_stops_started_backend_through_parent_pipe() -> None:
    code = "import sys; print('ready', flush=True); sys.stdin.read(); print('stopped')"
    with child(code) as monitor:
        assert monitor.startup(timeout=5) == "ready\n"
        monitor.stop()
        assert monitor.process.returncode == 0
