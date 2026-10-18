"""Shared executable identity and exit contracts for CLI and desktop application."""

from __future__ import annotations

import sys
from enum import IntEnum
from hashlib import sha256
from pathlib import Path

from researchassistant.common.resources import PROMPT_NAMES
from researchassistant.providers.config import ProviderConfigurationError

# Installed compatibility modules belong to the backend source surface. The root
# cli.py is a transition launcher, outside the distribution implementation.
EXECUTABLE_ROOT_MODULES = ("cli.py", "models.py", "orchestrator.py", "store.py")
EXECUTABLE_PACKAGES = ("researchassistant", "agents", "providers", "frontend")


class CLIExitCode(IntEnum):
    """Stable MVP-4 process exit codes."""

    RELEASED = 0
    BLOCKED = 10
    FAILED = 11
    CANCELLED = 12
    RUNNING = 13
    CONFIGURATION_ERROR = 20
    INVALID_INPUT = 21


def source_directory(root: Path) -> Path:
    """Locate backend sources in a workspace, backend, install or frozen bundle."""
    for candidate in (root / "backend/src", root / "src"):
        if candidate.is_dir():
            return candidate
    return root


def repository_identity(root: Path | None = None) -> str:
    """Hash the current backend layout and bytes, never relabel a stored identity."""
    root = root if root is not None else _default_source_root()
    source = source_directory(root)
    configuration = next(
        (
            path
            for path in (
                root / "backend/pyproject.toml",
                source.parent / "pyproject.toml"
                if source.name == "src"
                else root / "pyproject.toml",
                source / "researchassistant/_distribution/pyproject.toml",
            )
            if path.is_file()
        ),
        source / "researchassistant/_distribution/pyproject.toml",
    )
    candidates = [source / name for name in EXECUTABLE_ROOT_MODULES] + [configuration]
    candidates.extend(sorted((source / "researchassistant/evidence/fonts").glob("*.ttf")))
    candidates.extend(sorted((source / "researchassistant/prompts").glob("*.md")))
    for directory in EXECUTABLE_PACKAGES:
        candidates.extend(sorted((source / directory).rglob("*.py")))
    if getattr(sys, "frozen", False):
        required = (
            *(source / name for name in EXECUTABLE_ROOT_MODULES),
            source / "researchassistant/research/v2_orchestrator.py",
            source / "researchassistant/runtime/cli.py",
            source / "researchassistant/evidence/fonts/unifont-15.0.01.ttf",
            *(source / "researchassistant/prompts" / name for name in PROMPT_NAMES),
            configuration,
        )
        if any(not path.is_file() for path in required):
            raise ProviderConfigurationError("packaged source identity surface is incomplete")

    def identity_path(path: Path) -> str:
        # The installed surface carries the *new* backend source paths. This is
        # an install mapping, never a conversion of historical run fingerprints.
        if path == configuration:
            return "backend/pyproject.toml"
        return "backend/src/" + path.relative_to(source).as_posix()

    digest = sha256()
    found = False
    for path in sorted(set(candidates), key=identity_path):
        if not path.is_file():
            continue
        found = True
        relative = identity_path(path).encode("utf-8")
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


def _default_source_root() -> Path:
    if getattr(sys, "frozen", False):
        internal_root = getattr(sys, "_MEIPASS", None)
        if internal_root is not None:
            return Path(internal_root).resolve()
        executable_root = Path(sys.executable).resolve().parent
        nested_root = executable_root / "_internal"
        return nested_root if nested_root.is_dir() else executable_root
    return Path(__file__).resolve().parents[2]
