"""Frozen desktop entry point: private inherited pipe bootstrap and loopback server."""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
from pathlib import Path
from threading import Thread

import uvicorn
from fastapi.staticfiles import StaticFiles
from pydantic import Field, SecretStr

import credential_store
from application_runtime import repository_identity
from desktop_paths import application_data_dir
from frontend.api import create_app, create_default_runtime
from frontend.service_manager import WigoloLaunchConfig, WigoloServiceManager
from models import StrictModel
from providers.config import WigoloConfig


class Bootstrap(StrictModel):
    token: SecretStr
    resources: Path
    protocol: int = Field(default=1, ge=1, le=1)
    smoke_namespace: str | None = Field(default=None, pattern=r"^[a-f0-9]{24}$")
    smoke_secret: SecretStr | None = None


def main() -> None:
    bootstrap = Bootstrap.model_validate_json(sys.stdin.readline())
    if len(bootstrap.token.get_secret_value()) < 32:
        raise RuntimeError("Invalid desktop session")
    resources = bootstrap.resources.resolve(strict=True)
    self_test = "--self-test" in sys.argv
    if self_test:
        credential_store.KEYCHAIN_SERVICE_PREFIX = (
            "ResearchAssistant.Smoke." + (bootstrap.smoke_namespace or secrets.token_hex(12)) + "."
        )
        if "--cleanup-smoke" in sys.argv:
            credential_store.remove_credential("MIMO_API_KEY")
            return
        if "--verify-persistence" in sys.argv:
            if (
                bootstrap.smoke_secret is None
                or credential_store._read_secret("MIMO_API_KEY")
                != bootstrap.smoke_secret.get_secret_value()
            ):
                raise RuntimeError("Cross-process credential persistence failed")
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
        data = application_data_dir()
        data.mkdir(parents=True, exist_ok=True)
        probe = data / "desktop-smoke.txt"
        probe.write_text("persistent", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "persistent":
            raise RuntimeError("Application data round-trip failed")
    runtime = create_default_runtime()
    node = resources / "node" / ("node.exe" if sys.platform == "win32" else "bin/node")
    wigolo = resources / "acquisition/node_modules/wigolo/dist/index.js"
    if not node.is_file() or not wigolo.is_file():
        raise RuntimeError("Bundled acquisition runtime is missing")

    def ownership_changed(pid: int, owned: bool) -> None:
        try:
            print(json.dumps({"owned_pid": pid, "owned": owned}), flush=True)
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
            command=(str(node), str(wigolo), "serve"),
            port=acquisition_port,
            require_ownership=True,
            browser_dir=resources / "browsers",
        ),
        base_environment=runtime.environment,
        ownership_changed=ownership_changed,
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
    )
    app.mount("/", StaticFiles(directory=resources / "web", html=True), name="desktop")
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))

    def parent_closed() -> None:
        # Pipe EOF is authoritative even if the shell crashes without a shutdown message.
        sys.stdin.read()
        server.should_exit = True

    Thread(target=parent_closed, daemon=True).start()
    print(
        json.dumps(
            {
                "protocol": 1,
                "origin": origin,
                "self_test": self_test,
                "identity": repository_identity(),
            }
        ),
        flush=True,
    )
    try:
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
