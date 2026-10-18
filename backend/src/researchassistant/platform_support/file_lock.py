"""Nonblocking process locks shared by desktop, CLI and history import."""

from __future__ import annotations

import errno
import sys
from pathlib import Path
from time import sleep
from typing import IO

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: IO[str] | None = None

    def acquire(self, *, blocking: bool = False) -> bool:
        if self.handle is not None:
            raise RuntimeError("Lock is already held by this instance")
        handle = self.path.open("a+", encoding="utf-8")
        try:
            if sys.platform == "win32":
                handle.seek(0, 2)
                if handle.tell() == 0:
                    handle.write("0")
                    handle.flush()
                handle.seek(0)
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if not blocking or exc.errno not in (
                            errno.EACCES,
                            errno.EAGAIN,
                            errno.EDEADLK,
                        ):
                            raise
                        sleep(0.05)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except OSError as exc:
            handle.close()
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                return False
            raise
        self.handle = handle
        return True

    def release(self) -> None:
        handle = self.handle
        if handle is None:
            return
        try:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self.handle = None
