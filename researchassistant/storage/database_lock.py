"""Database process lock ownership shared by writable orchestration boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from researchassistant.platform_support.file_lock import FileLock

_OWNED: ContextVar[frozenset[Path]] = ContextVar("database_locks_owned", default=frozenset())


@contextmanager
def retained_database_lock(db_path: str | Path) -> Iterator[None]:
    """Declare an outer worker's retained lock for this synchronous write scope."""
    path = Path(db_path).expanduser().resolve()
    token = _OWNED.set(_OWNED.get() | {path})
    try:
        yield
    finally:
        _OWNED.reset(token)


@contextmanager
def database_lock(
    db_path: str | Path, *, lock_owned: bool = False, blocking: bool = False
) -> Iterator[None]:
    path = Path(db_path).expanduser().resolve()
    if lock_owned or path in _OWNED.get():
        with retained_database_lock(path):
            yield
        return
    # This is an explicitly selected database path; leave existing parent modes alone.
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(path.with_name(f"{path.name}.mvp5.lock"))
    if not lock.acquire(blocking=blocking):
        raise RuntimeError("Research database is busy in another process")
    try:
        with retained_database_lock(path):
            yield
    finally:
        lock.release()
