"""Bounded, secret-free diagnostics for isolated frozen-backend checks."""

from __future__ import annotations

import subprocess
import time
from queue import Empty, Queue
from threading import Thread
from typing import TextIO

import httpx

STARTUP_PHASES = frozenset(
    {
        "bootstrap",
        "credential-read",
        "credential-roundtrip",
        "credential-cleanup",
        "data-roundtrip",
        "runtime",
        "identity",
        "server",
    }
)


class BackendMonitor:
    """Drain both pipes continuously; retain only allowlisted phase names."""

    def __init__(self, process: subprocess.Popen[str], *, label: str) -> None:
        self.process = process
        self.label = label
        self.started = time.monotonic()
        self.phase = "not-reported (pre-main startup or an older build)"
        self.stderr_characters = 0
        self.announced = False
        self.lines: Queue[str] = Queue(maxsize=1)
        assert process.stdout is not None and process.stderr is not None
        self.threads = (
            Thread(target=self._stdout, args=(process.stdout,), daemon=True),
            Thread(target=self._stderr, args=(process.stderr,), daemon=True),
        )
        for thread in self.threads:
            thread.start()

    def _stdout(self, stream: TextIO) -> None:
        self.lines.put(stream.readline(8193))
        # Ownership notifications may follow startup. Keep the pipe writable.
        while stream.read(4096):
            pass

    def _stderr(self, stream: TextIO) -> None:
        while line := stream.readline(4096):
            self.stderr_characters += len(line)
            if line.startswith("SMOKE_PHASE:"):
                phase = line.removeprefix("SMOKE_PHASE:").strip()
                if phase in STARTUP_PHASES:
                    self.phase = phase

    def failure(self, operation: str) -> RuntimeError:
        elapsed = time.monotonic() - self.started
        return RuntimeError(
            f"{self.label}: {operation}; elapsed={elapsed:.2f}s; "
            f"exit={self.process.poll()}; phase={self.phase}; "
            f"stderr_characters={self.stderr_characters}. "
            "A credential phase may require an OS vault permission response. "
            "Raw child output is omitted to protect credentials."
        )

    def startup(self, *, timeout: float = 45) -> str:
        try:
            line = self.lines.get(timeout=timeout)
        except Empty:
            raise self.failure("startup deadline exceeded") from None
        if not line:
            for thread in self.threads:
                thread.join(timeout=0.1)
            raise self.failure("exited before startup")
        if len(line) > 8192 or not line.endswith("\n"):
            raise self.failure("invalid or oversized startup line")
        self.announced = True
        return line

    def stop(self) -> None:
        """Let a running server stop owned acquisition work before forced cleanup."""
        if self.process.poll() is None:
            if self.announced and self.process.stdin is not None:
                try:
                    self.process.stdin.close()
                except BrokenPipeError:
                    pass
                try:
                    self.process.wait(timeout=100)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            else:
                self.process.kill()
            self.process.wait(timeout=10)
        self.finish_reading()

    def finish_reading(self) -> None:
        """Join readers only after the owned child has exited."""
        for thread in self.threads:
            thread.join(timeout=5)
        if any(thread.is_alive() for thread in self.threads):
            raise self.failure("pipe drain deadline exceeded")

    def wait_exit(self, *, timeout: float = 100) -> None:
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise self.failure("shutdown deadline exceeded") from None
        self.finish_reading()
        if code != 0:
            raise self.failure("backend failed")


def wait_for_health(client: httpx.Client, *, timeout: float = 10) -> None:
    """The announced socket is not ready until the API lifespan has started."""
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            response = client.get("/api/health", timeout=min(remaining, 1))
            if response.status_code == 200:
                return
            if response.status_code < 500:
                raise RuntimeError(f"Backend health rejected the request: {response.status_code}")
        except httpx.TransportError:
            pass
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    raise RuntimeError("Backend health deadline exceeded after startup announcement")
