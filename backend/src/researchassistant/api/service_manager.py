"""Owned local lifecycle for pinned loopback Wigolo acquisition."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from collections import deque
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock, Thread
from time import monotonic, sleep
from typing import Literal, TextIO

import httpx
from pydantic import Field

from researchassistant.api.security import redact_text
from researchassistant.contracts.models import StrictModel
from researchassistant.platform_support.desktop_paths import application_data_dir
from researchassistant.platform_support.windows_job import WindowsJob
from researchassistant.providers.config import WigoloConfig
from researchassistant.providers.search import SearchProviderError
from researchassistant.providers.wigolo import WigoloSearchAdapter

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
    port: int = Field(default=8000, ge=1, le=65535)
    require_ownership: bool = False
    data_dir: Path | None = None
    browser_dir: Path | None = None


def default_wigolo_launch() -> WigoloLaunchConfig:
    """Use the protected, locked source runtime when this is a source checkout."""
    acquisition = Path(__file__).resolve().parents[4] / "desktop/acquisition"
    preload = acquisition / "network-preload.mjs"
    entry = acquisition / "node_modules/wigolo/dist/index.js"
    node = shutil.which("node")
    if node is not None and preload.is_file() and entry.is_file():
        return WigoloLaunchConfig(command=(node, "--import", str(preload), str(entry), "serve"))
    return WigoloLaunchConfig()


class _OwnedProcess:
    def __init__(self, process: subprocess.Popen[str], started_at: float) -> None:
        self.process = process
        self.started_at = started_at
        self.job: WindowsJob | None = None
        self.output_readers: list[Thread] = []


def _process_group_exists(process_group_id: int) -> bool:
    """Return whether a recorded owned process group still exists."""
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_owned_group(process: subprocess.Popen[str], *, timeout: float = 10) -> None:
    """Do not expose a successful start while a gated launcher still inherits our group."""
    deadline = monotonic() + timeout
    while process.poll() is None:
        try:
            if os.getpgid(process.pid) == process.pid:
                return
        except ProcessLookupError:
            break
        if monotonic() >= deadline:
            raise RuntimeError("Supervised acquisition process group timed out")
        sleep(0.01)
    raise RuntimeError("Supervised acquisition exited before its process group was ready")


class WigoloServiceManager:
    """Start, probe, monitor, and stop only the process group this instance owns."""

    def __init__(
        self,
        *,
        config: WigoloConfig | None = None,
        launch: WigoloLaunchConfig | None = None,
        popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        base_environment: Mapping[str, str] | None = None,
        ownership_changed: Callable[[int, bool], None] | None = None,
        supervisor_command: tuple[str, ...] | None = None,
    ) -> None:
        if supervisor_command is not None and (
            not supervisor_command or ownership_changed is None or sys.platform == "win32"
        ):
            raise ValueError("A POSIX supervisor requires an ownership acknowledgement callback")
        self._supervisor_command = supervisor_command
        self._ownership_changed = ownership_changed
        self._config = config or WigoloConfig()
        self._launch = launch or default_wigolo_launch()
        self._popen = popen
        self._base_environment = os.environ if base_environment is None else base_environment
        self._lock = Lock()
        self._lifecycle_lock = Lock()
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
        if self._launch.require_ownership and owned is None:
            return ServiceDiagnostic(
                state="wrong_service",
                wigolo_ready=False,
                searxng_readiness="unavailable",
                message=(
                    "The desktop acquisition port is occupied by an unowned service. "
                    "Restart the app."
                ),
            )
        return ServiceDiagnostic(
            state="healthy",
            wigolo_ready=True,
            searxng_readiness="unavailable",
            message="Pinned Wigolo 0.2.1 acquisition is healthy.",
            owned_process=owned is not None,
            pid=owned.process.pid if owned is not None else None,
            started_at_monotonic=owned.started_at if owned is not None else None,
            recent_output=recent,
        )

    def start(self) -> ServiceDiagnostic:
        """Start the approved pinned process without inheriting provider secrets."""
        with self._lifecycle_lock:
            existing = self.probe()
            if existing.wigolo_ready or existing.state == "wrong_service":
                return existing
            with self._lock:
                old_owned = self._owned
                if old_owned is not None and old_owned.process.poll() is None:
                    return self._starting_diagnostic(old_owned)
            if old_owned is not None:
                self._stop_owned(old_owned)
            with self._lock:
                self._launch_error = None
                environment = self._child_environment()
                working = self._launch.data_dir or application_data_dir() / "acquisition"
                working.mkdir(mode=0o700, parents=True, exist_ok=True)
                try:
                    supervised = self._supervisor_command is not None
                    command = (
                        (*self._supervisor_command, *self._launch.command)
                        if self._supervisor_command is not None
                        else self._launch.command
                    )
                    process = self._popen(
                        list(command),
                        cwd=str(working),
                        env=environment,
                        stdin=subprocess.PIPE if supervised else subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        start_new_session=sys.platform != "win32" and not supervised,
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
                if sys.platform == "win32":
                    try:
                        owned.job = WindowsJob()
                        owned.job.attach(int(process._handle))
                    except OSError:
                        process.kill()
                        process.wait(timeout=5)
                        if owned.job is not None:
                            owned.job.close()
                        raise
                self._owned = owned
                try:
                    if self._ownership_changed is not None:
                        self._ownership_changed(process.pid, True)
                    if supervised:
                        assert process.stdin is not None
                        process.stdin.write("start\n")
                        process.stdin.flush()
                        process.stdin.close()
                        _wait_for_owned_group(process)
                except Exception as exc:
                    # Cover both sides of a possible setsid/exec transition.
                    if sys.platform != "win32":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    if owned.job is not None:
                        owned.job.close()
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if stream is not None:
                            try:
                                stream.close()
                            except OSError:
                                pass
                    self._owned = None
                    if self._ownership_changed is not None:
                        self._ownership_changed(process.pid, False)
                    self._launch_error = redact_text(exc)
                    return ServiceDiagnostic(
                        state="launch_failed",
                        wigolo_ready=False,
                        searxng_readiness="unavailable",
                        message=f"Could not supervise pinned Wigolo: {self._launch_error}",
                    )
                for stream in (process.stdout, process.stderr):
                    reader = self._start_output_reader(stream)
                    if reader is not None:
                        owned.output_readers.append(reader)
                return self._starting_diagnostic(owned)

    def stop(self) -> ServiceDiagnostic:
        """Stop only the process group created by this manager."""
        with self._lifecycle_lock:
            with self._lock:
                owned = self._owned
            if owned is None:
                return ServiceDiagnostic(
                    state="stopped",
                    wigolo_ready=False,
                    searxng_readiness="unavailable",
                    message="No application-owned Wigolo process is running; nothing was stopped.",
                )
            return self._stop_owned(owned)

    def _stop_owned(self, owned: _OwnedProcess) -> ServiceDiagnostic:
        """Retire exactly one recorded owner and its descendants."""
        process = owned.process
        if owned.job is not None:
            owned.job.close()
            process.wait(timeout=5)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = monotonic() + 5
            while _process_group_exists(process.pid) and monotonic() < deadline:
                process.poll()
                sleep(0.05)
            if _process_group_exists(process.pid):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for reader in owned.output_readers:
            reader.join(timeout=5)
        if self._ownership_changed is not None:
            self._ownership_changed(process.pid, False)
        with self._lock:
            if self._owned is owned:
                self._owned = None
            recent = tuple(self._output)
        return ServiceDiagnostic(
            state="stopped",
            wigolo_ready=False,
            searxng_readiness="unavailable",
            message="Stopped the application-owned Wigolo process group.",
            owned_process=True,
            pid=process.pid,
            started_at_monotonic=owned.started_at,
            recent_output=recent,
        )

    def owns_running_process(self) -> bool:
        with self._lock:
            return self._owned is not None and self._owned.process.poll() is None

    def _child_environment(self) -> dict[str, str]:
        environment: dict[str, str] = {}
        for name in (
            "PATH",
            "HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "SystemRoot",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
        ):
            value = self._base_environment.get(name)
            if value:
                environment[name] = value
        environment.update(
            {
                "WIGOLO_DAEMON_HOST": self._launch.host,
                "WIGOLO_DAEMON_PORT": str(self._launch.port),
                "LOG_FORMAT": "text",
                "WIGOLO_DATA_DIR": str(
                    self._launch.data_dir or application_data_dir() / "acquisition"
                ),
                "WIGOLO_BROWSER_TYPES": "chromium",
            }
        )
        if self._launch.browser_dir is not None:
            environment["PLAYWRIGHT_BROWSERS_PATH"] = str(self._launch.browser_dir)
        return environment

    def _start_output_reader(self, stream: TextIO | None) -> Thread | None:
        if stream is None:
            return None

        def read_stream() -> None:
            try:
                for line in stream:
                    safe = redact_text(line.rstrip())
                    if safe:
                        with self._lock:
                            self._output.append(safe)
            finally:
                stream.close()

        reader = Thread(target=read_stream, daemon=True)
        reader.start()
        return reader

    def _starting_diagnostic(self, owned: _OwnedProcess) -> ServiceDiagnostic:
        return ServiceDiagnostic(
            state="starting",
            wigolo_ready=False,
            searxng_readiness="not_confirmed",
            message=(
                "Starting pinned Wigolo 0.2.1 acquisition. Health must pass before research begins."
            ),
            owned_process=True,
            pid=owned.process.pid,
            started_at_monotonic=owned.started_at,
            recent_output=tuple(self._output),
        )
