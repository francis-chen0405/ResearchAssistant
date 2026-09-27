"""Exercise a frozen local-platform bundle without provider calls or installed runtimes."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from smoke_support import BackendMonitor, wait_for_health


def main() -> None:
    resources = Path(sys.argv[1]).resolve()
    executable = (
        resources
        / "backend"
        / (
            "researchassistant-backend.exe"
            if sys.platform == "win32"
            else "researchassistant-backend"
        )
    )
    with tempfile.TemporaryDirectory(prefix="ResearchAssistant smoke ") as temporary:
        env = {
            name: os.environ[name]
            for name in (
                "HOME",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
                "SystemRoot",
                "WINDIR",
                "TEMP",
                "TMPDIR",
            )
            if name in os.environ
        }
        env["RESEARCHASSISTANT_DATA_DIR"] = temporary
        # Deliberately no Python/Node/pnpm on PATH and an unrelated working directory.
        env["PATH"] = ""
        token = secrets.token_hex(32)
        namespace = secrets.token_hex(12)
        saved_secret = secrets.token_hex(24)
        process = subprocess.Popen(
            [str(executable), "--self-test"],
            cwd=temporary,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        monitor = BackendMonitor(process, label="frozen smoke")
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(
                json.dumps(
                    {"token": token, "resources": str(resources), "smoke_namespace": namespace}
                )
                + "\n"
            )
            process.stdin.flush()
            bootstrap = json.loads(monitor.startup())
            assert bootstrap["self_test"]
            assert bootstrap["identity"].startswith("source-sha256:")
            with httpx.Client(
                base_url=bootstrap["origin"],
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            ) as client:
                wait_for_health(client)
                assert client.get("/api/health", headers={"Authorization": ""}).status_code == 401
                assert (
                    client.get("/api/health", headers={"Origin": "https://example.com"}).status_code
                    == 403
                )
                assert client.get("/").status_code == 200
                settings = client.get("/api/preferences").json()
                settings["maxCost"] = "0.15"
                assert client.post("/api/preferences", json=settings).status_code == 200
                assert client.get("/api/preferences").json()["maxCost"] == "0.15"
                result = client.post("/api/service/start")
                if result.status_code == 404:
                    raise RuntimeError("Acquisition lifecycle route is missing")
                result.raise_for_status()
                for _attempt in range(100):
                    service = client.get("/api/configuration").json()["service"]
                    if service["wigolo_ready"]:
                        break
                    if service["state"] in ("exited", "launch_failed", "wrong_service"):
                        raise RuntimeError(f"Packaged acquisition failed: {service['message']}")
                    time.sleep(0.2)
                else:
                    raise RuntimeError("Packaged acquisition health deadline exceeded")
                assert service["owned_process"], "Smoke requires its own acquisition process"
                client.post("/api/service/stop").raise_for_status()
                assert not client.get("/api/configuration").json()["service"]["wigolo_ready"]
                client.post(
                    "/api/credentials", json={"mimo_api_key": saved_secret}
                ).raise_for_status()
            process.stdin.close()
            monitor.wait_exit()
            assert (Path(temporary) / "desktop-smoke.txt").read_text() == "persistent"
            assert (
                json.loads((Path(temporary) / "preferences.json").read_text())["interface"][
                    "maxCost"
                ]
                == "0.15"
            )
            second = subprocess.Popen(
                [str(executable), "--self-test", "--verify-persistence"],
                cwd=temporary,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            second_monitor = BackendMonitor(second, label="frozen restart")
            try:
                assert second.stdin is not None and second.stdout is not None
                second.stdin.write(
                    json.dumps(
                        {
                            "token": token,
                            "resources": str(resources),
                            "smoke_namespace": namespace,
                            "smoke_secret": saved_secret,
                        }
                    )
                    + "\n"
                )
                second.stdin.flush()
                restarted = json.loads(second_monitor.startup())
                assert restarted["identity"] == bootstrap["identity"]
                with httpx.Client(
                    base_url=restarted["origin"],
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                ) as client:
                    wait_for_health(client)
                second.stdin.close()
                second_monitor.wait_exit()
            finally:
                second_monitor.stop()
            print(
                "PASS: frozen UI/backend, authentication, native vault cleanup, "
                "durable settings, owned Wigolo lifecycle"
            )
        finally:
            try:
                monitor.stop()
            finally:
                cleanup = subprocess.run(
                    [str(executable), "--self-test", "--cleanup-smoke"],
                    input=json.dumps(
                        {"token": token, "resources": str(resources), "smoke_namespace": namespace}
                    )
                    + "\n",
                    env=env,
                    cwd=temporary,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
                if cleanup.returncode != 0:
                    raise RuntimeError("Native smoke credential cleanup failed")


if __name__ == "__main__":
    main()
