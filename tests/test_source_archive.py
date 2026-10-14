"""Standalone source archives retain the files needed by their own checks."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.build_source_archive import REQUIRED_FILES, build_source_archive, source_paths


def _write(root: Path, name: str, payload: bytes = b"fixture\n", mode: int = 0o644) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)
    return path


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


@pytest.fixture
def source_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    for name in REQUIRED_FILES:
        _write(root, str(name), f"required: {name}\n".encode())
    _git(root, "add", "--all")
    return root


def test_archive_inventory_retains_documented_launchers_and_required_guidance(
    source_repository: Path, tmp_path: Path
) -> None:
    required = {
        "cli.py",
        "Launch ResearchAssistant.command",
        "AGENTS.md",
        "README.md",
        "docs/project/CONVENTIONS.md",
        "docs/project/ARCHITECTURE.md",
        "docs/project/DECISIONS.md",
        "docs/project/STATUS.md",
        "docs/project/HANDOFF.md",
        ".agent/PLANS.md",
        ".agent/plans/phase-00-foundation.md",
        ".agents/PLANS/phase-00-foundation.md",
        "tests/README.md",
        "backend/.env.example",
    }
    assert required <= {str(name) for name in REQUIRED_FILES}
    launcher = source_repository / "Launch ResearchAssistant.command"
    launcher.chmod(0o755)
    _git(source_repository, "update-index", "--chmod=+x", "--", launcher.name)
    rows = build_source_archive(
        source_repository, tmp_path / "source.tar.gz", tmp_path / "SOURCE-MANIFEST.json"
    )
    assert required <= rows.keys()
    with tarfile.open(tmp_path / "source.tar.gz", "r:gz") as archive:
        assert required <= set(archive.getnames())
        assert archive.getmember("Launch ResearchAssistant.command").mode == 0o755


def test_archive_selects_current_owned_files_from_dirty_repository(
    source_repository: Path, tmp_path: Path
) -> None:
    modified = _write(source_repository, "backend/src/researchassistant/engine.py", b"old\n")
    deleted = _write(source_repository, "backend/src/researchassistant/retired.py")
    _git(source_repository, "add", "--all")
    modified.write_bytes(b"current working-tree bytes\n")
    deleted.unlink()
    new = _write(source_repository, "backend/src/researchassistant/new.py", b"new source\n")
    historical = _write(source_repository, "docs/archive/retained/example.md")
    _write(source_repository, "unsupported-root.py")
    with (source_repository / ".gitignore").open("a", encoding="utf-8") as stream:
        stream.write("\nbackend/ignored-private.txt\n")
    _write(source_repository, "backend/ignored-private.txt")

    selected = {
        path.relative_to(source_repository).as_posix() for path in source_paths(source_repository)
    }
    assert modified.relative_to(source_repository).as_posix() in selected
    assert new.relative_to(source_repository).as_posix() in selected
    assert historical.relative_to(source_repository).as_posix() in selected
    assert "backend/src/researchassistant/retired.py" not in selected
    assert "unsupported-root.py" not in selected
    assert "backend/ignored-private.txt" not in selected

    rows = build_source_archive(
        source_repository, tmp_path / "source.tar.gz", tmp_path / "SOURCE-MANIFEST.json"
    )
    assert (
        rows["backend/src/researchassistant/engine.py"]["sha256"]
        == hashlib.sha256(b"current working-tree bytes\n").hexdigest()
    )


def test_archive_excludes_tracked_private_and_generated_files(source_repository: Path) -> None:
    excluded = {
        "backend/src/researchassistant/.env",
        "backend/src/researchassistant/.env.local",
        "frontend/.env.example",
        "backend/src/researchassistant/history.db",
        "backend/src/researchassistant/history.sqlite3",
        "backend/src/researchassistant/signing.p12",
        "backend/src/researchassistant/private.pem",
        "backend/src/researchassistant/private.key",
        "backend/src/researchassistant/__pycache__/engine.pyc",
        "backend/.venv/bin/python",
        "backend/build/engine.py",
        "desktop/build/backend.py",
        "desktop/dist/application.zip",
        "desktop/acquisition/node_modules/runtime.js",
        "frontend/.next/server.js",
        "frontend/node_modules/runtime.js",
        "frontend/out/index.html",
    }
    for name in excluded:
        _write(source_repository, name, b"private or generated fixture\n")
    legitimate = "backend/src/researchassistant/providers/config.py"
    _write(source_repository, legitimate)
    _git(source_repository, "add", "--force", "--all")

    selected = {
        path.relative_to(source_repository).as_posix() for path in source_paths(source_repository)
    }
    assert excluded.isdisjoint(selected)
    assert legitimate in selected


@pytest.mark.parametrize("missing", ["cli.py", "docs/project/STATUS.md"])
def test_missing_required_source_preserves_existing_outputs(
    source_repository: Path, tmp_path: Path, missing: str
) -> None:
    (source_repository / missing).unlink()
    archive = _write(tmp_path, "source.tar.gz", b"previous archive")
    manifest = _write(tmp_path, "SOURCE-MANIFEST.json", b"previous manifest")
    with pytest.raises(ValueError):
        build_source_archive(source_repository, archive, manifest)
    assert archive.read_bytes() == b"previous archive"
    assert manifest.read_bytes() == b"previous manifest"


@pytest.mark.parametrize("target_kind", ["internal-file", "external-file", "external-directory"])
def test_owned_symlinks_are_refused_before_output_replacement(
    source_repository: Path, tmp_path: Path, target_kind: str
) -> None:
    if target_kind == "internal-file":
        target = _write(source_repository, "backend/src/researchassistant/engine.py")
    elif target_kind == "external-file":
        target = _write(tmp_path, "outside/private.py", b"outside fixture")
    else:
        target = tmp_path / "outside-directory"
        target.mkdir()
        _write(target, "private.py", b"outside fixture")
    link = source_repository / "backend/src/researchassistant/linked"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=target.is_dir())
    _git(source_repository, "add", "--all")
    archive = _write(tmp_path, "source.tar.gz", b"previous archive")
    manifest = _write(tmp_path, "SOURCE-MANIFEST.json", b"previous manifest")
    with pytest.raises(ValueError):
        source_paths(source_repository)
    with pytest.raises(ValueError):
        build_source_archive(source_repository, archive, manifest)
    assert archive.read_bytes() == b"previous archive"
    assert manifest.read_bytes() == b"previous manifest"


def test_archive_manifest_binds_payload_bytes_and_modes(
    source_repository: Path, tmp_path: Path
) -> None:
    payload = b"binary source fixture\x00\xff\n"
    name = "backend/src/researchassistant/fixture.bin"
    path = _write(source_repository, name, payload, 0o755)
    archive_path = tmp_path / "source.tar.gz"
    manifest_path = tmp_path / "SOURCE-MANIFEST.json"
    rows = build_source_archive(source_repository, archive_path, manifest_path)
    assert json.loads(manifest_path.read_text()) == rows
    expected_mode = stat.S_IMODE(path.stat().st_mode)
    assert rows[name] == {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
        "mode": expected_mode,
    }
    with tarfile.open(archive_path, "r:gz") as archive:
        assert archive.getnames() == sorted(rows)
        for member in archive:
            assert member.isfile()
            assert member.uid == member.gid == 0
            assert member.uname == member.gname == ""
            assert member.mtime == 0
            assert member.mode == rows[member.name]["mode"]
            stream = archive.extractfile(member)
            assert stream is not None
            with stream:
                archived = stream.read()
            assert len(archived) == rows[member.name]["size"]
            assert hashlib.sha256(archived).hexdigest() == rows[member.name]["sha256"]


def test_archive_bytes_do_not_depend_on_source_mtime_or_output_name(
    source_repository: Path, tmp_path: Path
) -> None:
    source = _write(source_repository, "backend/src/researchassistant/engine.py", b"source\n")
    first_archive = tmp_path / "first.tar.gz"
    first_manifest = tmp_path / "first.json"
    build_source_archive(source_repository, first_archive, first_manifest)
    os.utime(source, (1_000_000_000, 1_000_000_000))
    second_archive = tmp_path / "different-name.tar.gz"
    second_manifest = tmp_path / "different-name.json"
    build_source_archive(source_repository, second_archive, second_manifest)
    assert first_archive.read_bytes() == second_archive.read_bytes()
    assert first_manifest.read_bytes() == second_manifest.read_bytes()
