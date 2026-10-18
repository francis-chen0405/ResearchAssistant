"""Publish fresh offline reports without replacing inputs or another writer's files."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from researchassistant.platform_support.private_files import create_private_file


def validate_output_paths(paths: Sequence[Path]) -> None:
    resolved = tuple(path.resolve() for path in paths)
    if len(set(resolved)) != len(resolved):
        raise ValueError("machine and human reports require distinct output paths")
    if any(path.exists() or path.is_symlink() for path in paths):
        raise FileExistsError("report output exists; choose fresh output paths")


def publish_outputs(payloads: Sequence[tuple[Path, bytes]]) -> None:
    """Check again at publication, then remove only our own files on failure."""
    validate_output_paths(tuple(path for path, _ in payloads))
    owned: list[tuple[Path, int, int]] = []
    try:
        for path, payload in payloads:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = create_private_file(path)
            info = os.fstat(descriptor)
            owned.append((path, info.st_dev, info.st_ino))
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for path, device, inode in reversed(owned):
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (device, inode):
                    path.unlink()
            except FileNotFoundError:
                pass
        raise
