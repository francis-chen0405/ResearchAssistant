"""Install/interrupt/repair an NSIS upgrade on a disposable GitHub Windows runner.

Never run against a user's installed application. The old installer is an immutable,
SHA-256-bound artifact from the last green historical Windows run, not a release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from researchassistant.platform_support.windows_job import WindowsJob

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_ARTIFACT = 11200125179
PREVIOUS_ARCHIVE_SHA256 = "e97755b915d27e312cdfdff39cfe5e6703c16e8b23d3a807c9d5953243178286"
PREVIOUS_REVISION = "0c493385822bcebfb9939872ba24746ac2c4a6ed"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


def previous_installer(folder: Path) -> Path:
    url = (
        "https://api.github.com/repos/francis-chen0405/ResearchAssistant/actions/artifacts/"
        f"{PREVIOUS_ARTIFACT}/zip"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "User-Agent": "ResearchAssistant-Windows-installer-smoke",
        },
    )
    try:
        response = urllib.request.build_opener(NoRedirect()).open(request, timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code != 302:
            raise RuntimeError(
                f"Historical Windows artifact unavailable: HTTP {exc.code}"
            ) from None
        # Do not forward repository credentials to GitHub's signed blob URL.
        response = urllib.request.urlopen(exc.headers["Location"], timeout=60)
    archive = folder / "previous-installer.zip"
    with response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    if digest(archive) != PREVIOUS_ARCHIVE_SHA256:
        raise RuntimeError("Historical Windows artifact SHA-256 mismatch")
    with zipfile.ZipFile(archive) as bundle:
        executables = [entry for entry in bundle.infolist() if entry.filename.endswith(".exe")]
        if len(executables) != 1:
            raise RuntimeError("Historical artifact must contain exactly one installer")
        installer = folder / "previous-installer.exe"
        with bundle.open(executables[0]) as source, installer.open("wb") as output:
            shutil.copyfileobj(source, output)
    return installer


def launch_installer(
    installer: Path, destination: Path
) -> tuple[subprocess.Popen[bytes], WindowsJob]:
    # NSIS /D consumes the unquoted remainder and must be the last argument.
    command = subprocess.list2cmdline([str(installer), "/S", "/currentuser"])
    command += " /D=" + str(destination)
    job = WindowsJob()
    process = subprocess.Popen(command, cwd=installer.parent)
    try:
        job.attach(int(process._handle))
    except BaseException:
        process.kill()
        process.wait(timeout=20)
        job.close()
        raise
    return process, job


def install(installer: Path, destination: Path) -> None:
    process, job = launch_installer(installer, destination)
    try:
        if process.wait(timeout=240) != 0:
            raise RuntimeError("NSIS silent installation failed")
        if not (destination / "ResearchAssistant.exe").is_file():
            raise RuntimeError("NSIS did not install at the requested isolated path")
    finally:
        job.close()
        process.wait(timeout=20)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("This check requires a disposable GitHub Actions Windows runner")
    installer = args.installer.resolve(strict=True)
    output = args.output.resolve()
    evidence: dict[str, object] = {
        "revision": os.environ.get("GITHUB_SHA"),
        "installer_sha256": digest(installer),
        "previous_revision": PREVIOUS_REVISION,
        "previous_artifact_id": PREVIOUS_ARTIFACT,
        "previous_artifact_sha256": PREVIOUS_ARCHIVE_SHA256,
        "power_loss": "unverified",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="RA NSIS ") as temporary:
        folder = Path(temporary)
        destination = folder / "installé 研究" / "ResearchAssistant"
        old = previous_installer(folder)
        evidence["previous_installer_sha256"] = digest(old)
        install(old, destination)
        previous_resources = folder / "previous-resources"
        shutil.copytree(destination / "resources", previous_resources)
        previous_backend = previous_resources / "backend/researchassistant-backend.exe"
        evidence["previous_backend_sha256"] = digest(previous_backend)
        # NSIS interrupted upgrade: observe removal of the previous executable,
        # then terminate only the owned installer Job, including its uninstaller.
        executable = destination / "ResearchAssistant.exe"
        process, job = launch_installer(installer, destination)
        deadline = time.monotonic() + 120
        try:
            while executable.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.005)
            if executable.exists() or process.poll() is not None:
                raise RuntimeError("Could not reach repeatable NSIS interrupted-upgrade checkpoint")
            job.close()
            process.wait(timeout=20)
            evidence["interrupted_upgrade"] = "owned Job terminated after old executable removal"
        finally:
            job.close()
            process.wait(timeout=20)
        # Retain the partial tree until the same installer repairs it. This does
        # not claim NSIS rolls back an interrupted installation automatically.
        install(installer, destination)
        resources = destination / "resources"
        backend = resources / "backend/researchassistant-backend.exe"
        current_hash = digest(backend)
        assert current_hash == digest(
            ROOT / "desktop/build/resources/backend/researchassistant-backend.exe"
        )
        assert current_hash != evidence["previous_backend_sha256"]
        evidence["backend_sha256"] = current_hash
        evidence["electron_sha256"] = digest(executable)
        subprocess.run([sys.executable, str(ROOT / "desktop/smoke.py"), str(resources)], check=True)
        subprocess.run(["node", str(ROOT / "desktop/ui-smoke.cjs"), str(executable)], check=True)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "desktop/upgrade-smoke.py"),
                str(previous_resources),
                str(resources),
                "--previous-schema13",
            ],
            check=True,
        )
        evidence["installed_frozen_smoke"] = "passed"
        evidence["installed_window_smoke"] = "passed"
        evidence["historical_to_current_data_vault_upgrade"] = "passed; generated schema-13 fixture"
        # The normal uninstall preserves separately stored temporary data.
        uninstaller = destination / "Uninstall ResearchAssistant.exe"
        assert uninstaller.is_file()
        subprocess.run(
            [str(uninstaller), "/S", "/currentuser", "_?=" + str(destination)],
            check=True,
            timeout=120,
        )
    evidence["result"] = "passed"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
