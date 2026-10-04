from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import researchassistant.storage.history_import as history_import_module
from researchassistant.runtime import cli
from researchassistant.runtime.application_runtime import CLIExitCode


def _install_recovery_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    list_function: object,
    restore_function: object,
) -> None:
    module = ModuleType("researchassistant.storage.database_recovery")
    module.list_backups = list_function  # type: ignore[attr-defined]
    module.restore_backup = restore_function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_list_backups_cli_prints_verified_backup_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "live.sqlite3"
    backup = SimpleNamespace(
        path=tmp_path / "live.sqlite3.backups" / "backup.sqlite3",
        schema_version=14,
        created_at=datetime(2026, 10, 3, tzinfo=UTC).isoformat(),
    )
    calls: list[Path] = []
    _install_recovery_module(
        monkeypatch,
        list_function=lambda path: calls.append(Path(path)) or [backup],
        restore_function=lambda *_: None,
    )

    result = cli.main(["list-backups", "--db-path", str(database)])

    output = capsys.readouterr()
    assert result == CLIExitCode.RELEASED
    assert calls == [database]
    assert "backup_count: 1" in output.out
    assert f"backup: {backup.path}" in output.out
    assert "schema_version: 14" in output.out
    assert f"created_at: {backup.created_at}" in output.out


def test_restore_backup_cli_passes_paths_and_prints_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backup = tmp_path / "verified.sqlite3"
    destination = tmp_path / "restored.sqlite3"
    calls: list[tuple[Path, Path]] = []

    def restore(source: Path, output: Path) -> Path:
        calls.append((Path(source), Path(output)))
        return Path(output)

    _install_recovery_module(monkeypatch, list_function=lambda _: [], restore_function=restore)

    result = cli.main(
        [
            "restore-backup",
            "--backup-path",
            str(backup),
            "--output-path",
            str(destination),
        ]
    )

    output = capsys.readouterr()
    assert result == CLIExitCode.RELEASED
    assert calls == [(backup, destination)]
    assert f"restored_database: {destination}" in output.out


def test_import_history_cli_prints_destination_and_run_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.sqlite3"
    destination_dir = tmp_path / "imports"
    calls: list[tuple[Path, Path | None]] = []

    def import_history(path: Path, *, destination_dir: Path | None) -> SimpleNamespace:
        calls.append((Path(path), destination_dir))
        return SimpleNamespace(db_path=str(tmp_path / "imports" / "history.sqlite3"), run_count=3)

    monkeypatch.setattr(history_import_module, "import_history", import_history)

    result = cli.main(
        [
            "import-history",
            "--source-path",
            str(source),
            "--destination-dir",
            str(destination_dir),
        ]
    )

    output = capsys.readouterr()
    assert result == CLIExitCode.RELEASED
    assert calls == [(source, destination_dir)]
    assert "database: " + str(tmp_path / "imports" / "history.sqlite3") in output.out
    assert "imported_runs: 3" in output.out


def test_recovery_cli_sanitizes_invalid_database_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_path = tmp_path / "private-source.sqlite3"

    def fail(_: Path) -> list[object]:
        raise ValueError(f"bad database at {private_path}")

    _install_recovery_module(monkeypatch, list_function=fail, restore_function=lambda *_: None)

    result = cli.main(["list-backups", "--db-path", str(private_path)])

    output = capsys.readouterr()
    assert result == CLIExitCode.INVALID_INPUT
    assert str(private_path) not in output.err
    assert "database path or contents could not be used" in output.err
