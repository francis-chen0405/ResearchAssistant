"""Build/audit a wheel and prove wheel/editable installs from an unrelated cwd."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SOURCE = BACKEND / "src"
PACKAGES = ("researchassistant", "agents", "providers", "frontend")
MODULES = ("cli.py", "models.py", "store.py")


def expected_payloads(root: Path) -> dict[str, bytes]:
    source = root / "backend/src"
    paths = [source / name for name in MODULES]
    for name in PACKAGES:
        paths.extend((source / name).rglob("*.py"))
    paths.extend((source / "researchassistant/prompts").glob("*.md"))
    paths.extend(
        source / "researchassistant/evidence/fonts" / name
        for name in ("unifont-15.0.01.ttf", "UNIFONT-LICENSE.txt", "README.md")
    )
    result = {path.relative_to(source).as_posix(): path.read_bytes() for path in paths}
    result["researchassistant/_distribution/pyproject.toml"] = (
        root / "backend/pyproject.toml"
    ).read_bytes()
    return result


def audit_wheel(wheel: Path, root: Path) -> list[str]:
    expected = expected_payloads(root)
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), "duplicate wheel members"
        payloads = {name: archive.read(name) for name in names if ".dist-info/" not in name}
        assert payloads.keys() == expected.keys(), {
            "missing": sorted(expected.keys() - payloads.keys()),
            "unexpected": sorted(payloads.keys() - expected.keys()),
        }
        assert payloads == expected, "wheel source/resource bytes differ from checkout"
        metadata = {name.rsplit("/", 1)[1] for name in names if ".dist-info/" in name}
        assert metadata == {"METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD"}
    return sorted(names)


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def verify(work: Path, *, constraints: Path | None, wheelhouse: Path | None) -> None:
    assert not work.resolve().is_relative_to(ROOT), "verification must run outside the checkout"
    if any(work.iterdir()):
        raise ValueError("verification directory must be empty so both environments are fresh")
    # Do not inherit user credentials, custom import paths, or user-site packages.
    env = {
        key: value
        for key, value in os.environ.items()
        if not (
            key in {"PYTHONPATH", "PYTHONHOME"} or key.endswith(("_API_KEY", "_TOKEN", "_SECRET"))
        )
    }
    env["PYTHONNOUSERSITE"] = "1"
    env["RESEARCHASSISTANT_DATA_DIR"] = str(work / "app-data")
    env["PIP_CACHE_DIR"] = str(work / "pip-cache")
    if wheelhouse is not None:
        env["PIP_NO_INDEX"] = "1"
        env["PIP_FIND_LINKS"] = str(wheelhouse)
    build_command = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "-w",
        str(work / "dist"),
        str(BACKEND),
    ]
    run(build_command, cwd=work, env=env)
    wheel = next((work / "dist").glob("researchassistant-*.whl"))
    inventory = audit_wheel(wheel, ROOT)
    (work / "wheel-files.txt").write_text("\n".join(inventory) + "\n")
    source_identity = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "from researchassistant.runtime.application_runtime import "
            "repository_identity; print(repository_identity())",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    ).strip()
    payloads = expected_payloads(ROOT)
    facades = {}
    for name in payloads:
        parts = Path(name).parts
        if (
            len(parts) == 2
            and parts[0] in {"agents", "providers", "frontend"}
            and parts[1].endswith(".py")
            and parts[1] != "__init__.py"
        ):
            namespace, stem = parts[0], Path(parts[1]).stem
            owner = "api" if namespace == "frontend" else namespace
            if namespace == "agents" and stem in {"renderer", "synthesizer"}:
                owner = "evidence"
            facades[f"{namespace}.{stem}"] = f"researchassistant.{owner}.{stem}"
    expected = {
        "facades": facades,
        "identity": source_identity,
        "prompts": {
            Path(name).name: hashlib.sha256(data).hexdigest()
            for name, data in payloads.items()
            if name.startswith("researchassistant/prompts/")
        },
        "font": hashlib.sha256(
            payloads["researchassistant/evidence/fonts/unifont-15.0.01.ttf"]
        ).hexdigest(),
    }
    expected_file = work / "expected.json"
    expected_file.write_text(json.dumps(expected, indent=2) + "\n")
    fixtures = work / "fixtures"
    for name in ("basic_valid_run", "invalid_release_run"):
        shutil.copytree(ROOT / "tests/fixtures" / name, fixtures / name)
    for kind in ("wheel", "editable"):
        environment = work / f"{kind}-venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [str(python), "-m", "pip", "install"]
        if constraints is not None:
            install.extend(["-c", str(constraints)])
        install.extend(["-e", str(BACKEND)] if kind == "editable" else [str(wheel)])
        run(install, cwd=work, env=env)
        run([str(python), "-m", "pip", "check"], cwd=work, env=env)
        cwd = work / f"{kind}-unrelated-cwd"
        cwd.mkdir()
        run(
            [
                str(python),
                "-I",
                str(ROOT / "scripts/install_smoke.py"),
                "--expected",
                str(expected_file),
                "--fixtures",
                str(fixtures),
            ],
            cwd=cwd,
            env=env,
        )
    print(f"Verified exact {len(inventory)}-file wheel and both isolated installs: {work}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work-dir", type=Path, help="Keep verification artifacts outside the checkout"
    )
    parser.add_argument("--constraints", type=Path)
    parser.add_argument("--wheelhouse", type=Path, help="Optional offline dependency/build wheels")
    args = parser.parse_args()
    options = {
        "constraints": args.constraints.resolve() if args.constraints else None,
        "wheelhouse": args.wheelhouse.resolve() if args.wheelhouse else None,
    }
    if args.work_dir:
        work = args.work_dir.resolve()
        assert not work.is_relative_to(ROOT), (
            "verification environments must be outside the checkout"
        )
        work.mkdir(parents=True, exist_ok=True)
        verify(work, **options)
    else:
        with tempfile.TemporaryDirectory(prefix="researchassistant-install-") as temporary:
            verify(Path(temporary).resolve(), **options)


if __name__ == "__main__":
    main()
