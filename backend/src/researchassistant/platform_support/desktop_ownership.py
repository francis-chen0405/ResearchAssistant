"""Private desktop pipe ownership handoff, bounded and fail closed on EOF."""

from __future__ import annotations

import json
import secrets
from threading import Event, Lock
from typing import TextIO


class DesktopOwnership:
    def __init__(self, output: TextIO, *, timeout: float = 10) -> None:
        self._output = output
        self._timeout = timeout
        self._lock = Lock()
        self._write_lock = Lock()
        self._pending: dict[str, tuple[int, Event]] = {}
        self._closed = False

    def write_message(self, message: dict[str, object]) -> None:
        with self._write_lock:
            self._output.write(json.dumps(message) + "\n")
            self._output.flush()

    def __call__(self, pid: int, owned: bool) -> None:
        if not owned:
            try:
                self.write_message({"owned_pid": pid, "owned": False})
            except OSError:
                pass
            return
        request = secrets.token_hex(16)
        ready = Event()
        with self._lock:
            if self._closed:
                raise RuntimeError("Desktop ownership pipe is closed")
            self._pending[request] = (pid, ready)
        try:
            self.write_message({"owned_pid": pid, "owned": True, "ownership_request": request})
            if not ready.wait(self._timeout):
                raise RuntimeError("Desktop ownership acknowledgement timed out")
            with self._lock:
                if self._closed:
                    raise RuntimeError("Desktop ownership pipe is closed")
        finally:
            with self._lock:
                self._pending.pop(request, None)

    def accept_acknowledgement(self, line: str) -> None:
        try:
            message = json.loads(line)
        except (ValueError, TypeError):
            return
        if not isinstance(message, dict):
            return
        request = message.get("ownership_ack")
        pid = message.get("owned_pid")
        if not isinstance(request, str) or type(pid) is not int:
            return
        with self._lock:
            pending = self._pending.get(request)
            if pending is not None and pending[0] == pid and not self._closed:
                pending[1].set()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for _pid, event in self._pending.values():
                event.set()
