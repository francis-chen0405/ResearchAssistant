"""Offline desktop resource regression checks."""

import io
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

import desktop.build as build
from researchassistant.runtime.application_runtime import (
    EXECUTABLE_ROOT_MODULES,
    repository_identity,
)


def test_node_staging_ignores_old_unpack_and_resource_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop = tmp_path / "desktop"
    resources = desktop / "build/resources"
    resources.mkdir(parents=True)
    stem = f"node-v{build.NODE_VERSION}-win-arm64"
    archive = desktop / "build" / f"{stem}.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(f"{stem}/node.exe", b"verified-node")
    checksum = sha256(archive.read_bytes()).hexdigest()
    stale_unpack = desktop / "build/node-unpack" / stem
    stale_unpack.mkdir(parents=True)
    (stale_unpack / "obsolete-unpack.txt").write_text("stale")
    stale_resources = resources / "node"
    stale_resources.mkdir()
    (stale_resources / "obsolete-resource.txt").write_text("stale")
    monkeypatch.setattr(build, "DESKTOP", desktop)
    monkeypatch.setattr(build, "RESOURCES", resources)
    monkeypatch.setattr(build.sys, "platform", "win32")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        build.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(f"{checksum}  {stem}.zip\n".encode()),
    )
    node = build.stage_node()
    assert node.read_bytes() == b"verified-node"
    assert sorted(path.name for path in node.parent.iterdir()) == ["node.exe"]
    assert not list((desktop / "build").glob("node-unpack-*"))


def test_inactive_root_copies_do_not_change_execution_identity(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("# dependencies")
    wrapper = tmp_path / "cli.py"
    wrapper.write_text("# launcher")
    identity = repository_identity(tmp_path)
    (tmp_path / "v2_orchestrator.py").write_text("# inactive prior source copy")
    assert repository_identity(tmp_path) == identity
    wrapper.write_text("# changed launcher")
    assert repository_identity(tmp_path) != identity


def test_backend_bundle_excludes_inactive_root_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop = tmp_path / "desktop"
    backend = desktop / "build/python/researchassistant-backend"
    backend.mkdir(parents=True)
    (backend / "backend.exe").write_bytes(b"bundled executable")
    for name in (*EXECUTABLE_ROOT_MODULES, "v2_orchestrator.py"):
        (tmp_path / name).write_text("# source")
    commands: list[list[str]] = []
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "DESKTOP", desktop)
    monkeypatch.setattr(build, "RESOURCES", desktop / "build/resources")
    monkeypatch.setattr(build.sys, "argv", ["build.py", "--backend-only"])
    monkeypatch.setattr(build, "run", lambda command: commands.append(command))
    build.main()
    command = commands[0]
    data_paths = [
        command[index + 1] for index, value in enumerate(command) if value == "--add-data"
    ]
    assert not any("v2_orchestrator.py" in value for value in data_paths)
    for name in EXECUTABLE_ROOT_MODULES:
        assert f"{tmp_path / name}{build.os.pathsep}." in data_paths
