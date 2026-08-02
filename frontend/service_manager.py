"""Owned local lifecycle for pinned loopback Wigolo and its SearXNG sidecar."""

from __future__ import annotations

import os
import signal
import subprocess
from collections import deque
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from typing import Literal, TextIO

import httpx
from pydantic import Field

from frontend.security import redact_text
from models import StrictModel
from providers.config import WigoloConfig
from providers.search import SearchProviderError
from providers.wigolo import WigoloSearchAdapter

ServiceState = Literal[
    "healthy",
    "unhealthy",
    "wrong_service",
    "starting",
    "exited",
    "launch_failed",
    "stopped",
]


class ServiceDiagnostic(StrictModel):
    state: ServiceState
    wigolo_ready: bool
    searxng_readiness: Literal["configured", "not_confirmed", "unavailable"]
    message: str = Field(min_length=1)
    owned_process: bool = False
    pid: int | None = Field(default=None, ge=1)
    started_at_monotonic: float | None = Field(default=None, ge=0)
    recent_output: tuple[str, ...] = ()


class WigoloLaunchConfig(StrictModel):
    command: tuple[str, ...] = ("npx", "-y", "wigolo@0.2.1", "serve")
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: Literal[8000] = 8000
    search_backend: Literal["searxng"] = "searxng"
    searxng_mode: Literal["native"] = "native"
    searxng_port: Literal[8888] = 8888


class _OwnedProcess:
    def __init__(self, process: subprocess.Popen[str], started_at: float) -> None:
        self.process = process
        self.started_at = started_at


class WigoloServiceManager:
    """Start, probe, monitor, and stop only the process group this instance owns."""

    def __init__(
        self,
        *,
        config: WigoloConfig | None = None,
        launch: WigoloLaunchConfig | None = None,
        popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        base_environment: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config or WigoloConfig()
        self._launch = launch or WigoloLaunchConfig()
        self._popen = popen
        self._base_environment = base_environment or os.environ
        self._lock = Lock()
        self._owned: _OwnedProcess | None = None
        self._output: deque[str] = deque(maxlen=40)
        self._launch_error: str | None = None

    def probe(self) -> ServiceDiagnostic:
        """Verify exact loopback identity; a listening port alone is never healthy."""
        with self._lock:
            owned = self._owned
            launch_error = self._launch_error
            recent = tuple(self._output)
        if owned is not None and owned.process.poll() is not None:
            return ServiceDiagnostic(
                state="exited",
                wigolo_ready=False,
                searxng_readiness="unavailable",
                message=f"Owned Wigolo exited with code {owned.process.returncode}.",
                owned_process=True,
                pid=owned.process.pid,
                started_at_monotonic=owned.started_at,
                recent_output=recent,
            )
        try:
            with httpx.Client(
                base_url=self._config.base_url,
                timeout=httpx.Timeout(self._config.deadlines.health_seconds),
                follow_redirects=False,
            ) as client:
                adapter = WigoloSearchAdapter(self._config, client=client)
                adapter.verify_health()
        except SearchProviderError as exc:
            message = redact_text(exc)
            wrong = "not the configured Wigolo 0.2.1" in message
            if owned is not None:
                return ServiceDiagnostic(
                    state="starting" if not wrong else "wrong_service",
                    wigolo_ready=False,
                    searxng_readiness="not_confirmed",
                    message=(
                        "Wigolo is starting; exact health is not ready yet."
                        if not wrong
                        else message
                    ),
                    owned_process=True,
                    pid=owned.process.pid,
                    started_at_monotonic=owned.started_at,
                    recent_output=recent,
                )
            return ServiceDiagnostic(
                state="wrong_service" if wrong else "unhealthy",
                wigolo_ready=False,
                searxng_readiness="unavailable",
                message=message,
                recent_output=recent,
            )
        except Exception as exc:
            return ServiceDiagnostic(
                state="launch_failed" if launch_error else "unhealthy",
                wigolo_ready=False,
                searxng_readiness="unavailable",
                message=redact_text(launch_error or exc),
                owned_process=owned is not None,
                pid=owned.process.pid if owned is not None else None,
                started_at_monotonic=owned.started_at if owned is not None else None,
                recent_output=recent,
            )
        return ServiceDiagnostic(
            state="healthy",
            wigolo_ready=True,
            searxng_readiness="configured",
            message=(
                "Pinned Wigolo 0.2.1 is healthy. Native SearXNG is configured; "
                "the first tracked Search call remains the authoritative readiness proof."
            ),
            owned_process=owned is not None,
            pid=owned.process.pid if owned is not None else None,
            started_at_monotonic=owned.started_at if owned is not None else None,
            recent_output=recent,
        )

    def start(self) -> ServiceDiagnostic:
        """Start the approved pinned process without inheriting provider secrets."""
        existing = self.probe()
        if existing.wigolo_ready or existing.state == "wrong_service":
            return existing
        with self._lock:
            if self._owned is not None and self._owned.process.poll() is None:
                return self._starting_diagnostic(self._owned)
            self._launch_error = None
            environment = self._child_environment()
            try:
                process = self._popen(
                    list(self._launch.command),
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
            except (OSError, ValueError) as exc:
                self._launch_error = redact_text(exc)
                return ServiceDiagnostic(
                    state="launch_failed",
                    wigolo_ready=False,
                    searxng_readiness="unavailable",
                    message=f"Could not launch pinned Wigolo: {self._launch_error}",
                )
            owned = _OwnedProcess(process, monotonic())
            self._owned = owned
            self._start_output_reader(process.stdout)
            self._start_output_reader(process.stderr)
            return self._starting_diagnostic(owned)

    def stop(self) -> ServiceDiagnostic:
        """Stop only the process group created by this manager."""
        with self._lock:
            owned = self._owned
        if owned is None:
            return ServiceDiagnostic(
                state="stopped",
                wigolo_ready=False,
                searxng_readiness="unavailable",
                message="No application-owned Wigolo process is running; nothing was stopped.",
            )
        process = owned.process
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        with self._lock:
            if self._owned is owned:
                self._owned = None
        return ServiceDiagnostic(
            state="stopped",
            wigolo_ready=False,
            searxng_readiness="unavailable",
            message="Stopped the application-owned Wigolo/SearXNG process group.",
            owned_process=True,
            pid=process.pid,
            started_at_monotonic=owned.started_at,
            recent_output=tuple(self._output),
        )

    def owns_running_process(self) -> bool:
        with self._lock:
            return self._owned is not None and self._owned.process.poll() is None

    def _child_environment(self) -> dict[str, str]:
        environment: dict[str, str] = {}
        for name in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"):
            value = self._base_environment.get(name)
            if value:
                environment[name] = value
        environment.update(
            {
                "WIGOLO_DAEMON_HOST": self._launch.host,
                "WIGOLO_DAEMON_PORT": str(self._launch.port),
                "WIGOLO_SEARCH": self._launch.search_backend,
                "SEARXNG_MODE": self._launch.searxng_mode,
                "SEARXNG_PORT": str(self._launch.searxng_port),
                "WIGOLO_EAGER_WARMUP": "1",
                "LOG_FORMAT": "text",
            }
        )
        return environment

    def _start_output_reader(self, stream: TextIO | None) -> None:
        if stream is None:
            return

        def read_stream() -> None:
            for line in stream:
                safe = redact_text(line.rstrip())
                if safe:
                    with self._lock:
                        self._output.append(safe)

        Thread(target=read_stream, daemon=True).start()

    def _starting_diagnostic(self, owned: _OwnedProcess) -> ServiceDiagnostic:
        return ServiceDiagnostic(
            state="starting",
            wigolo_ready=False,
            searxng_readiness="not_confirmed",
            message=(
                "Starting pinned Wigolo 0.2.1 with native SearXNG. Health must pass "
                "before research begins."
            ),
            owned_process=True,
            pid=owned.process.pid,
            started_at_monotonic=owned.started_at,
            recent_output=tuple(self._output),
        )
