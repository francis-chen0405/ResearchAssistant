"""Build local-platform desktop resources with bundled Python, Node and Chromium."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
RESOURCES = DESKTOP / "build/resources"
NODE_VERSION = "24.18.0"


def run(args: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def stage_node() -> Path:
    architecture = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "AMD64": "x64"}[
        platform.machine()
    ]
    system = {"darwin": "darwin", "win32": "win"}[sys.platform]
    suffix = "zip" if sys.platform == "win32" else "tar.gz"
    stem = f"node-v{NODE_VERSION}-{system}-{architecture}"
    filename = f"{stem}.{suffix}"
    base = f"https://nodejs.org/dist/v{NODE_VERSION}/"
    archive = DESKTOP / "build" / filename
    with urllib.request.urlopen(base + "SHASUMS256.txt", timeout=60) as response:
        checksums = response.read().decode("utf-8")
    expected = next(line.split()[0] for line in checksums.splitlines() if line.endswith(filename))
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        urllib.request.urlretrieve(base + filename, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise RuntimeError("Bundled Node checksum mismatch")
    unpack = DESKTOP / "build/node-unpack"
    unpack.mkdir(exist_ok=True)
    if suffix == "zip":
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(unpack)
    else:
        with tarfile.open(archive) as tar:
            tar.extractall(unpack, filter="data")
    shutil.copytree(unpack / stem, RESOURCES / "node", dirs_exist_ok=True)
    return RESOURCES / "node" / ("node.exe" if sys.platform == "win32" else "bin/node")


def main() -> None:
    RESOURCES.mkdir(parents=True, exist_ok=True)
    if "--backend-only" not in sys.argv:
        node = stage_node()
        node_bin = node.parent
        env = {**os.environ, "PATH": str(node_bin) + os.pathsep + os.environ.get("PATH", "")}
        npm_cli = (node_bin if sys.platform == "win32" else node_bin.parent / "lib") / (
            "node_modules/npm/bin/npm-cli.js"
        )
        acquisition = DESKTOP / "acquisition"
        run([str(node), str(npm_cli), "ci", "--no-audit", "--no-fund"], cwd=acquisition, env=env)
        browser_env = {**env, "PLAYWRIGHT_BROWSERS_PATH": str(RESOURCES / "browsers")}
        run(
            [str(node), str(acquisition / "node_modules/playwright/cli.js"), "install", "chromium"],
            env=browser_env,
        )
        shutil.copytree(acquisition, RESOURCES / "acquisition", dirs_exist_ok=True)
        run(
            [str(node), str(ROOT / "web/node_modules/next/dist/bin/next"), "build"],
            cwd=ROOT / "web",
            env={
                **env,
                "RESEARCHASSISTANT_DESKTOP": "1",
                "NEXT_PUBLIC_RESEARCH_API_URL": "",
                "NEXT_TELEMETRY_DISABLED": "1",
            },
        )
        shutil.copytree(ROOT / "web/out", RESOURCES / "web", dirs_exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "researchassistant-backend",
        "--paths",
        str(ROOT),
        "--distpath",
        str(DESKTOP / "build/python"),
        "--workpath",
        str(DESKTOP / "build/pyinstaller"),
        "--specpath",
        str(DESKTOP / "build"),
        "--exclude-module",
        "streamlit",
        "--exclude-module",
        "pytest",
    ]
    for path in sorted(ROOT.glob("*.py")):
        command.extend(["--add-data", f"{path}{os.pathsep}."])
    command.extend(["--add-data", f"{ROOT / 'pyproject.toml'}{os.pathsep}."])
    for name in ("agents", "providers", "frontend", "prompts"):
        command.extend(["--add-data", f"{ROOT / name}{os.pathsep}{name}"])
    command.append(str(DESKTOP / "backend.py"))
    run(command)
    shutil.copytree(
        DESKTOP / "build/python/researchassistant-backend",
        RESOURCES / "backend",
        dirs_exist_ok=True,
    )
    print(f"Desktop resources prepared: {RESOURCES}")


if __name__ == "__main__":
    main()
