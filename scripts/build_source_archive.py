"""Build a complete, deterministic workspace source snapshot without runtime data."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_repository_boundaries import (  # noqa: E402
    SUPPORTED_ROOT_DIRECTORIES,
    SUPPORTED_ROOT_FILES,
)

REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "cli.py",
    "Launch ResearchAssistant.command",
    "pyproject.toml",
    ".gitignore",
    "backend/pyproject.toml",
    "backend/requirements.txt",
    "backend/requirements-legacy.txt",
    "backend/.env.example",
    "docs/project/ARCHITECTURE.md",
    "docs/project/CONVENTIONS.md",
    "docs/project/DECISIONS.md",
    "docs/project/STATUS.md",
    "docs/project/HANDOFF.md",
    ".agent/PLANS.md",
    ".agent/plans/phase-00-foundation.md",
    ".agents/PLANS/phase-00-foundation.md",
    "tests/README.md",
)
_EXCLUDED_PARTS = frozenset(
    {
        "node_modules",
        "build",
        "dist",
        "out",
        "__pycache__",
        ".venv",
        ".git",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".pnpm-store",
        ".researchassistant",
        ".aws",
        ".codex",
        ".ssh",
    }
)
_PRIVATE_SUFFIXES = frozenset(
    {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".p12", ".pfx", ".pem", ".key"}
)
_PRIVATE_NAMES = frozenset({".npmrc", "credentials.json", "credentials.toml"})


def source_paths(root: Path) -> list[Path]:
    """Select current owned files, including nonignored additions and guidance."""
    root = root.resolve()
    candidates = (
        subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                *sorted(SUPPORTED_ROOT_DIRECTORIES | SUPPORTED_ROOT_FILES),
            ]
        )
        .decode("utf-8")
        .split("\0")
    )
    selected: dict[str, Path] = {}
    for name in sorted(set(candidates) - {""}):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source archive path escapes its workspace")
        if (
            set(relative.parts) & _EXCLUDED_PARTS
            or (relative.name.startswith(".env") and name != "backend/.env.example")
            or relative.name in _PRIVATE_NAMES
            or relative.suffix.lower() in _PRIVATE_SUFFIXES
        ):
            continue
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"source archive cannot include a symlink: {name}")
        if path.is_file():
            selected[name] = path
    missing = sorted(set(REQUIRED_FILES) - selected.keys())
    if missing:
        raise ValueError("source archive missing required files: " + ", ".join(missing))
    return [selected[name] for name in sorted(selected)]


def build_source_archive(
    root: Path, archive: Path, manifest: Path
) -> dict[str, dict[str, int | str]]:
    """Write the archive and its external byte/mode manifest from one source snapshot."""
    root = root.resolve()
    paths = source_paths(root)
    archive = archive.resolve()
    manifest = manifest.resolve()
    if archive == manifest or archive in paths or manifest in paths:
        raise ValueError("source archive outputs must be distinct from supplied source files")
    archive.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, int | str]] = {}
    # NTFS mode bits cannot represent the executable bit of a Mac launcher.
    # Keep worktree bytes, using Git's portable tracked mode only on Windows.
    tracked_modes: dict[str, int] = {}
    if os.name == "nt":
        entries = subprocess.check_output(["git", "-C", str(root), "ls-files", "--stage", "-z"])
        for entry in entries.decode("utf-8").split("\0"):
            if not entry:
                continue
            metadata, name = entry.split("\t", 1)
            mode, _object, stage = metadata.split()
            if stage == "0" and mode in {"100644", "100755"}:
                tracked_modes[name] = int(mode[-3:], 8)
    # Prepare both outputs fully before replacing either existing artifact.
    with (
        tempfile.TemporaryDirectory(prefix=".source-archive-", dir=archive.parent) as archive_temp,
        tempfile.TemporaryDirectory(
            prefix=".source-manifest-", dir=manifest.parent
        ) as manifest_temp,
    ):
        staged_archive = Path(archive_temp) / archive.name
        staged_manifest = Path(manifest_temp) / manifest.name
        with (
            staged_archive.open("wb") as raw,
            gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as output,
        ):
            for path in paths:
                name = path.relative_to(root).as_posix()
                payload = path.read_bytes()
                mode = tracked_modes.get(name, stat.S_IMODE(path.stat().st_mode))
                rows[name] = {
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "mode": mode,
                }
                entry = tarfile.TarInfo(name)
                entry.size = len(payload)
                entry.mode = mode
                output.addfile(entry, io.BytesIO(payload))
        staged_manifest.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        os.replace(staged_archive, archive)
        os.replace(staged_manifest, manifest)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rows = build_source_archive(args.root, args.archive, args.manifest)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Source archive failed: {exc}\n")
    print(
        json.dumps(
            {"files": len(rows), "archive": str(args.archive), "manifest": str(args.manifest)}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
