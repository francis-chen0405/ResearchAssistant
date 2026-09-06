"""Stable writable locations outside the source checkout and application bundle."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def application_data_dir() -> Path:
    """Return the per-user data directory independently of executable placement."""
    override = os.environ.get("RESEARCHASSISTANT_DATA_DIR")
    if override:
        path = Path(override)
        if not path.is_absolute():
            raise RuntimeError("Application data override must be absolute")
        return path
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ResearchAssistant"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            raise RuntimeError("Windows local application data directory is unavailable")
        return Path(local) / "ResearchAssistant"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / (
        "ResearchAssistant"
    )
