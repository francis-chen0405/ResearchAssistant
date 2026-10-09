"""Shared executable identity and exit contracts for CLI and desktop application."""

from __future__ import annotations

import sys
from enum import IntEnum
from hashlib import sha256
from pathlib import Path

from providers.config import ProviderConfigurationError


class CLIExitCode(IntEnum):
    """Stable MVP-4 process exit codes."""

    RELEASED = 0
    BLOCKED = 10
    FAILED = 11
    CANCELLED = 12
    RUNNING = 13
    CONFIGURATION_ERROR = 20
    INVALID_INPUT = 21


def repository_identity(root: Path | None = None) -> str:
    """Hash the executable repository surface without runtime databases or secrets."""
    root = root if root is not None else Path(__file__).resolve().parent
    candidates = list(root.glob("*.py")) + [root / "pyproject.toml"]
    for directory, pattern in (
        ("agents", "*.py"),
        ("providers", "*.py"),
        ("frontend", "*.py"),
        ("prompts", "*.md"),
    ):
        candidates.extend(sorted((root / directory).rglob(pattern)))
    if getattr(sys, "frozen", False):
        if not (root / "v2_orchestrator.py").is_file() or not (root / "prompts").is_dir():
            raise ProviderConfigurationError("packaged source identity surface is incomplete")
    digest = sha256()
    found = False
    for path in sorted(set(candidates)):
        if not path.is_file():
            continue
        found = True
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    if not found:
        raise ProviderConfigurationError("repository identity surface is unavailable")
    if getattr(sys, "frozen", False):
        digest.update(Path(sys.executable).read_bytes())
    return f"source-sha256:{digest.hexdigest()}"
