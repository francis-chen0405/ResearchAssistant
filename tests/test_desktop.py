from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import researchassistant.platform_support.credential_store as credential_store
import researchassistant.platform_support.desktop_paths as desktop_paths
from frontend.api import create_app, create_default_runtime
from frontend.live_service import LiveResearchController, LiveRunRequest
from researchassistant.contracts.models import RunManifest, RunStatus, Stage
from researchassistant.platform_support.desktop_settings import (
    InterfaceSettings,
    Preferences,
    read_preferences,
    update_preferences,
)
from researchassistant.platform_support.file_lock import FileLock
from researchassistant.storage.history_import import import_history
from researchassistant.storage.store import init_db, insert_run, open_read_only_store, read_run


def test_generated_backend_replacement_removes_obsolete_source_copies(tmp_path: Path) -> None:
    from desktop.build import replace_tree

    source = tmp_path / "fresh-backend"
    (source / "researchassistant/contracts").mkdir(parents=True)
    (source / "researchassistant/contracts/models.py").write_text("# current package source")
    destination = tmp_path / "resources/backend"
    (destination / "researchassistant/contracts").mkdir(parents=True)
    (destination / "model_evidence.py").write_text("# obsolete root source copy")

    replace_tree(source, destination)

    assert (destination / "researchassistant/contracts/models.py").read_text() == (
        "# current package source"
    )
    assert not (destination / "model_evidence.py").exists()


def test_database_lock_excludes_another_process_and_releases(tmp_path: Path) -> None:
    path = tmp_path / "database.mvp5.lock"
    lock = FileLock(path)
    assert lock.acquire()
    code = (
        "from researchassistant.platform_support.file_lock import FileLock; "
        "from pathlib import Path; import sys; "
        "lock=FileLock(Path(sys.argv[1])); acquired=lock.acquire(); "
        "lock.release(); sys.exit(0 if acquired else 3)"
    )
    assert subprocess.run([sys.executable, "-c", code, str(path)], check=False).returncode == 3
    lock.release()
    assert subprocess.run([sys.executable, "-c", code, str(path)], check=False).returncode == 0


def test_preferences_preserve_values_and_reject_secrets(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    update_preferences(interface=InterfaceSettings(maxCost="0.15"), path=path)
    update_preferences(provider_settings={"LUNA_MODEL": "example"}, path=path)
    restored = read_preferences(path)
    assert restored.interface.maxCost == "0.15"
    assert restored.provider_settings == {"LUNA_MODEL": "example"}
    with pytest.raises(ValidationError):
        update_preferences(provider_settings={"MIMO_API_KEY": "secret"}, path=path)
    assert "secret" not in path.read_text()
    assert read_preferences(path) == restored
    with pytest.raises(ValidationError):
        Preferences.model_validate({"unknown": True})


def test_provider_settings_do_not_enter_vault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCHASSISTANT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(credential_store, "_require_keychain", lambda: None)
    saved: list[tuple[str, str]] = []

    def write(name: str, value: str) -> None:
        saved.append((name, value))

    monkeypatch.setattr(credential_store, "_write_keychain_secret", write)
    credential_store.save_credentials(
        credential_store.ProviderCredentials(
            mimo_api_key="private-test-key",
            luna_model="example",
        )
    )
    assert saved == [("MIMO_API_KEY", "private-test-key")]
    assert "private-test-key" not in (tmp_path / "preferences.json").read_text()
    assert read_preferences().provider_settings["LUNA_MODEL"] == "example"


def test_desktop_auth_and_validation_do_not_echo_credentials() -> None:
    runtime = create_default_runtime()
    app = create_app(runtime, load_keychain_on_start=False, session_token="a" * 64)
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/health").status_code == 401
    headers = {"Authorization": "Bearer " + "a" * 64}
    assert client.get("/api/health", headers=headers).status_code == 200
    rejected = client.post(
        "/api/credentials", headers=headers, json={"mimo_api_key": {"secret": "do-not-echo"}}
    )
    assert rejected.status_code == 422
    assert "do-not-echo" not in rejected.text
    assert (
        client.get("/api/health", headers={**headers, "Origin": "https://example.com"}).status_code
        == 403
    )
    assert client.get("/api/health", headers={**headers, "Host": "evil.example"}).status_code == 403
    runtime.controller.shutdown(timeout=0)


def test_history_import_preserves_source_and_rejects_active_source(tmp_path: Path) -> None:
    source = tmp_path / "old.sqlite3"
    init_db(str(source))
    manifest = RunManifest(
        run_id=uuid4(),
        status=RunStatus.RUNNING,
        raw_claim="Exact historical claim",
        current_stage=Stage.DISCOVERY,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    insert_run(str(source), manifest)
    before = source.read_bytes()
    result = import_history(source, destination_dir=tmp_path / "new")
    assert result.run_count == 1
    assert read_run(result.db_path, manifest.run_id) == manifest
    assert source.read_bytes() == before
    with open_read_only_store(result.db_path) as copied:
        assert copied.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    lock = FileLock(source.with_name(source.name + ".mvp5.lock"))
    assert lock.acquire()
    try:
        with pytest.raises(ValueError, match="active research"):
            import_history(source, destination_dir=tmp_path / "new")
    finally:
        lock.release()
    assert len(list((tmp_path / "new").glob("*.sqlite3"))) == 1


def test_shutdown_prevents_new_research(tmp_path: Path) -> None:
    controller = LiveResearchController(environment={})
    assert controller.shutdown(timeout=0)
    with pytest.raises(ValueError, match="shutting down"):
        controller.start(
            LiveRunRequest(
                raw_claim="Test claim", db_path=str(tmp_path / "run.sqlite3"), max_tokens=100
            )
        )
    assert not (tmp_path / "run.sqlite3").exists()
    assert not controller.has_active_runs()


def test_platform_paths_are_independent_of_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEARCHASSISTANT_DATA_DIR", raising=False)
    monkeypatch.setattr(desktop_paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(Path.home() / "Windows Local"))
    assert (
        desktop_paths.application_data_dir()
        == Path(os.environ["LOCALAPPDATA"]) / "ResearchAssistant"
    )
    monkeypatch.setattr(desktop_paths.sys, "platform", "darwin")
    assert (
        desktop_paths.application_data_dir()
        == Path.home() / "Library/Application Support/ResearchAssistant"
    )


def test_unavailable_vault_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credential_store, "_keychain_available", lambda: True)

    def unavailable(name: str) -> str | None:
        raise credential_store.KeychainUnavailableError("Vault is locked")

    monkeypatch.setattr(credential_store, "_read_secret", unavailable)
    with pytest.raises(credential_store.KeychainUnavailableError):
        credential_store.load_saved_credentials()


def test_windows_owned_job_is_attached_and_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import frontend.service_manager as service

    actions: list[tuple[str, int]] = []

    class FakeProcess:
        pid = 4242
        _handle = 123
        stdout = None
        stderr = None
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float) -> int:
            self.returncode = 0
            return 0

    class FakeJob:
        def attach(self, handle: int) -> None:
            actions.append(("attach", handle))

        def close(self) -> None:
            actions.append(("close", 0))

    child = FakeProcess()

    def popen(command: list[str], **kwargs: object) -> FakeProcess:
        assert kwargs["start_new_session"] is False
        assert "MIMO_API_KEY" not in kwargs["env"]
        return child

    monkeypatch.setattr(service.sys, "platform", "win32")
    monkeypatch.setattr(service, "WindowsJob", FakeJob)
    manager = service.WigoloServiceManager(
        popen=popen,
        base_environment={"MIMO_API_KEY": "secret"},
        launch=service.WigoloLaunchConfig(data_dir=tmp_path),
    )
    monkeypatch.setattr(
        manager,
        "probe",
        lambda: service.ServiceDiagnostic(
            state="unhealthy",
            wigolo_ready=False,
            searxng_readiness="unavailable",
            message="offline",
        ),
    )
    assert manager.start().owned_process
    assert actions == [("attach", 123)]
    assert manager.stop().state == "stopped"
    assert actions == [("attach", 123), ("close", 0)]


def test_fingerprint_covers_v2_prompts_and_frozen_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import researchassistant.runtime.application_runtime as application_runtime
    import researchassistant.runtime.cli as cli

    source_root = tmp_path / "source"
    source_engine = source_root / "researchassistant/research/v2_orchestrator.py"
    source_engine.parent.mkdir(parents=True)
    source_engine.write_text("# engine one")
    source_cli = source_root / "researchassistant/runtime/cli.py"
    source_cli.parent.mkdir(parents=True)
    source_cli.write_text("# cli one")
    source_policy = source_root / "researchassistant/storage/sqlite_policy.py"
    source_policy.parent.mkdir(parents=True)
    source_policy.write_text("# policy one")
    source_font = source_root / "researchassistant/evidence/fonts/unifont-15.0.01.ttf"
    source_font.parent.mkdir(parents=True)
    source_font.write_bytes(b"font one")
    (source_root / "pyproject.toml").write_text("# dependencies")
    (source_root / "prompts").mkdir()
    source_prompt = source_root / "prompts/analyst.md"
    source_prompt.write_text("exact prompt one")
    monkeypatch.setattr(
        application_runtime,
        "__file__",
        str(source_root / "researchassistant/runtime/application_runtime.py"),
    )
    original = cli.repository_identity()
    source_engine.write_text("# engine two")
    changed_engine = cli.repository_identity()
    assert changed_engine != original
    source_prompt.write_text("exact prompt two")
    changed_prompt = cli.repository_identity()
    assert changed_prompt != changed_engine
    source_policy.write_text("# policy two")
    changed_policy = cli.repository_identity()
    assert changed_policy != changed_prompt
    source_font.write_bytes(b"font two")
    changed_font = cli.repository_identity()
    assert changed_font != changed_policy
    (source_root / "history.sqlite3").write_bytes(b"runtime data")
    assert cli.repository_identity() == changed_font

    internal_root = tmp_path / "dist/_internal"
    for relative, payload in (
        ("researchassistant/research/v2_orchestrator.py", "# packaged engine"),
        ("researchassistant/runtime/cli.py", "# packaged cli one"),
        ("researchassistant/contracts/models.py", "# packaged contracts"),
        ("prompts/analyst.md", "packaged prompt"),
        ("pyproject.toml", "packaged dependencies"),
        ("researchassistant/evidence/fonts/unifont-15.0.01.ttf", "packaged font"),
    ):
        path = internal_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
    monkeypatch.setattr(application_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(application_runtime.sys, "_MEIPASS", str(internal_root), raising=False)
    executable = tmp_path / "dist/researchassistant-backend"
    executable.write_bytes(b"frozen executable one")
    monkeypatch.setattr(application_runtime.sys, "executable", str(executable))
    frozen = cli.repository_identity()
    (internal_root / "researchassistant/runtime/cli.py").write_text("# packaged cli two")
    assert cli.repository_identity() != frozen
    frozen = cli.repository_identity()
    executable.write_bytes(b"frozen executable two")
    assert cli.repository_identity() != frozen
    (internal_root / "researchassistant/research/v2_orchestrator.py").unlink()
    with pytest.raises(Exception, match="identity surface is incomplete"):
        cli.repository_identity()
