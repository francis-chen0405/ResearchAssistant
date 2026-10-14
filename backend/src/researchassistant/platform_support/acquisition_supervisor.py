"""Keep a POSIX acquisition launcher supervised until the shell owns its group."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence


def run_supervised_command(command: Sequence[str]) -> None:
    """Detach/exec only after the backend releases the acknowledged ownership gate."""
    if not command or sys.stdin.readline(7) != "start\n":
        raise SystemExit(1)
    # Until now we inherit the backend group. Electron already records our PID
    # before setsid; it remains the group ID through exec and all descendants.
    os.setsid()
    null = os.open(os.devnull, os.O_RDONLY)
    try:
        os.dup2(null, 0)
    finally:
        if null != 0:
            os.close(null)
    os.execvpe(command[0], list(command), os.environ)


if __name__ == "__main__":
    run_supervised_command(sys.argv[1:])
