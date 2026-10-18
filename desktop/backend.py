"""Frozen desktop entry point: private inherited pipe bootstrap and loopback server."""

from __future__ import annotations

import ipaddress
import os
import secrets
import socket
import sys
from pathlib import Path
from threading import Thread

import uvicorn
from fastapi.staticfiles import StaticFiles
from pydantic import Field, SecretStr

import researchassistant.platform_support.credential_store as credential_store
from researchassistant.api.api import create_app, create_default_runtime
from researchassistant.api.service_manager import WigoloLaunchConfig, WigoloServiceManager
from researchassistant.contracts.models import StrictModel
from researchassistant.platform_support import acquisition_supervisor
from researchassistant.platform_support.desktop_ownership import DesktopOwnership
from researchassistant.platform_support.desktop_paths import application_data_dir
from researchassistant.platform_support.windows_job import WindowsJob
from researchassistant.providers.config import WigoloConfig
from researchassistant.runtime.application_runtime import repository_identity


class Bootstrap(StrictModel):
    token: SecretStr
    resources: Path
    protocol: int = Field(default=1, ge=1, le=1)
    smoke_namespace: str | None = Field(default=None, pattern=r"^[a-f0-9]{24}$")
    smoke_secret: SecretStr | None = None


def smoke_phase(name: str) -> None:
    """Emit fixed diagnostic labels only; never include bootstrap values."""
    if "--self-test" in sys.argv:
        print(f"SMOKE_PHASE:{name}", file=sys.stderr, flush=True)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--dns-worker":
        from researchassistant.providers.dns_worker import main as dns_worker_main

        dns_worker_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--pdf-worker":
        from researchassistant.providers.pdf_worker import main as pdf_worker_main

        pdf_worker_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--acquisition-supervisor":
        acquisition_supervisor.run_supervised_command(sys.argv[2:])
        return
    if sys.platform == "win32":
        # Keep this non-inheritable handle alive until process exit. Electron uses
        # the owned child HANDLE to terminate us; OS handle closure then kills every
        # descendant, even during startup or a stalled acquisition Job assignment.
        # Do not close it in a finally block: closing it also terminates this process.
        backend_job = WindowsJob()
        backend_job.attach_current_process()
    smoke_phase("bootstrap")
    bootstrap = Bootstrap.model_validate_json(sys.stdin.readline())
    if len(bootstrap.token.get_secret_value()) < 32:
        raise RuntimeError("Invalid desktop session")
    resources = bootstrap.resources.resolve(strict=True)
    self_test = "--self-test" in sys.argv
    if self_test:
        from researchassistant.providers.bounded_resolver import resolve_host_addresses

        smoke_phase("dns-worker")
        if not all(
            ipaddress.ip_address(value).is_loopback
            for value in resolve_host_addresses("localhost", timeout=5)
        ):
            raise RuntimeError("Owned frozen DNS helper failed")
        credential_store.KEYCHAIN_SERVICE_PREFIX = (
            "ResearchAssistant.Smoke." + (bootstrap.smoke_namespace or secrets.token_hex(12)) + "."
        )
        if "--cleanup-smoke" in sys.argv:
            smoke_phase("credential-cleanup")
            credential_store.remove_credential("MIMO_API_KEY")
            return
        if "--verify-persistence" in sys.argv:
            smoke_phase("credential-read")
            if (
                bootstrap.smoke_secret is None
                or credential_store._read_secret("MIMO_API_KEY")
                != bootstrap.smoke_secret.get_secret_value()
            ):
                raise RuntimeError("Cross-process credential persistence failed")
        smoke_phase("credential-roundtrip")
        secret = secrets.token_hex(24)
        try:
            credential_store.save_credentials(
                credential_store.ProviderCredentials(mimo_api_key=secret)
            )
            if credential_store._read_secret("MIMO_API_KEY") != secret:
                raise RuntimeError("Native vault round-trip failed")
        finally:
            credential_store.remove_credential("MIMO_API_KEY")
        if credential_store._read_secret("MIMO_API_KEY") is not None:
            raise RuntimeError("Native vault cleanup failed")
        smoke_phase("data-roundtrip")
        data = application_data_dir()
        data.mkdir(parents=True, exist_ok=True)
        probe = data / "desktop-smoke.txt"
        probe.write_text("persistent", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "persistent":
            raise RuntimeError("Application data round-trip failed")
    smoke_phase("runtime")
    runtime = create_default_runtime()
    node = resources / "node" / ("node.exe" if sys.platform == "win32" else "bin/node")
    wigolo = resources / "acquisition/node_modules/wigolo/dist/index.js"
    if not node.is_file() or not wigolo.is_file():
        raise RuntimeError("Bundled acquisition runtime is missing")

    ownership = DesktopOwnership(sys.stdout)

    def windows_ownership_changed(pid: int, owned: bool) -> None:
        try:
            ownership.write_message({"owned_pid": pid, "owned": owned})
        except BrokenPipeError:
            # The parent may have crashed; local process cleanup must still complete.
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as acquisition_socket:
        acquisition_socket.bind(("127.0.0.1", 0))
        acquisition_port = acquisition_socket.getsockname()[1]
    runtime.environment["WIGOLO_BASE_URL"] = f"http://127.0.0.1:{acquisition_port}"
    runtime.services = WigoloServiceManager(
        config=WigoloConfig(base_url=runtime.environment["WIGOLO_BASE_URL"]),
        launch=WigoloLaunchConfig(
            command=(
                str(node),
                "--import",
                str(resources / "acquisition/network-preload.mjs"),
                str(wigolo),
                "serve",
            ),
            port=acquisition_port,
            require_ownership=True,
            browser_dir=resources / "browsers",
        ),
        base_environment=runtime.environment,
        ownership_changed=windows_ownership_changed if sys.platform == "win32" else ownership,
        supervisor_command=(
            None
            if sys.platform == "win32"
            else (sys.executable, "--acquisition-supervisor")
            if getattr(sys, "frozen", False)
            else (sys.executable, str(Path(acquisition_supervisor.__file__).resolve()))
        ),
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    app = create_app(
        runtime,
        load_keychain_on_start=True,
        allowed_hosts=("127.0.0.1",),
        allowed_origins=(origin,),
        session_token=bootstrap.token.get_secret_value(),
        shutdown_controller_on_exit=False,
    )
    app.mount("/", StaticFiles(directory=resources / "frontend", html=True), name="desktop")
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))

    def parent_closed() -> None:
        # Pipe EOF is authoritative even if the shell crashes without a shutdown message.
        try:
            for line in sys.stdin:
                ownership.accept_acknowledgement(line)
        finally:
            ownership.close()
            server.should_exit = True

    Thread(target=parent_closed, daemon=True).start()
    smoke_phase("identity")
    ownership.write_message(
        {
            "protocol": 1,
            "origin": origin,
            "self_test": self_test,
            "identity": repository_identity(),
        }
    )
    try:
        smoke_phase("server")
        server.run(sockets=[sock])
    finally:
        completed = runtime.controller.shutdown(timeout=90)
        runtime.services.stop()
        sock.close()
        if not completed:
            # Unknown provider outcomes keep their persisted reservations for explicit recovery.
            os._exit(0)


if __name__ == "__main__":
    main()
