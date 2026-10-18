"""Order research admission and idle-only changes without locking their I/O."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock


class LifecycleConflict(ValueError):
    """A service/configuration change and research cannot own the same interval."""


class LifecycleCoordinator:
    """Reserve an operation under a short lock, then perform all work outside it.

    Pending admissions bridge configuration capture through worker registration.
    Once registered, the controller's unfinished futures remain the authority for
    ownership. Cancellation does not release ownership before a worker finishes.
    Idle operations exclude admissions until their I/O has completed or failed.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._admissions = 0
        self._changing = False

    @contextmanager
    def admission(self) -> Iterator[None]:
        with self._lock:
            if self._changing:
                raise LifecycleConflict(
                    "A service or configuration change is in progress. Retry shortly."
                )
            self._admissions += 1
        try:
            yield
        finally:
            with self._lock:
                self._admissions -= 1

    @contextmanager
    def idle_change(self, has_active_runs: Callable[[], bool], *, message: str) -> Iterator[None]:
        # The callback only reads controller ownership under its short state lock;
        # it must not inspect SQLite, wait for futures, or perform service I/O.
        with self._lock:
            if self._changing or self._admissions or has_active_runs():
                raise LifecycleConflict(message)
            self._changing = True
        try:
            yield
        finally:
            with self._lock:
                self._changing = False
