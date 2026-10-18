"""Offline NSIS invocation/oracle regressions; these do not run a native installer."""

from __future__ import annotations

import subprocess
from importlib import import_module
from pathlib import Path

import pytest

installer_smoke = import_module("desktop.windows-installer-smoke")


def test_uninstall_waits_for_unquoted_nsis_target_and_checks_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "RA NSIS installé 研究" / "ResearchAssistant"
    destination.mkdir(parents=True)
    uninstaller = destination / "Uninstall ResearchAssistant.exe"
    uninstaller.touch()
    executable = destination / "ResearchAssistant.exe"
    executable.touch()
    resources = destination / "resources"
    resources.mkdir()
    saved_data = tmp_path / "generated-research.json"
    saved_data.write_bytes(b"separate generated fixture\n")
    calls: list[str] = []

    def run(command: str, *, check: bool, timeout: int) -> subprocess.CompletedProcess[bytes]:
        # Model NSIS's literal unquoted-tail parser, not Windows argv splitting.
        prefix, separator, target = command.partition(" _?=")
        assert separator and target == str(destination)
        assert prefix == subprocess.list2cmdline([str(uninstaller), "/S", "/currentuser"])
        assert check and timeout == 120
        calls.append(command)
        executable.unlink()
        resources.rmdir()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(installer_smoke.subprocess, "run", run)
    installer_smoke.uninstall(destination)
    assert len(calls) == 1
    assert uninstaller.is_file(), "NSIS in-place mode may leave its own executable"
    assert saved_data.read_bytes() == b"separate generated fixture\n"


@pytest.mark.parametrize(
    "leftover", ["ResearchAssistant.exe", "resources", "chrome_100_percent.pak"]
)
def test_uninstall_rejects_zero_exit_with_remaining_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, leftover: str
) -> None:
    destination = tmp_path / "RA NSIS installé 研究"
    destination.mkdir()
    (destination / "Uninstall ResearchAssistant.exe").touch()
    if leftover == "resources":
        (destination / leftover).mkdir()
    else:
        (destination / leftover).touch()

    def run(command: str, *, check: bool, timeout: int) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(installer_smoke.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="left installed payload behind"):
        installer_smoke.uninstall(destination)
