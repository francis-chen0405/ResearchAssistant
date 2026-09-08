"""Verify a preceding frozen build and the new build share durable data safely."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx
from smoke import startup_line


def main() -> None:
    previous, current = (Path(value).resolve() for value in sys.argv[1:3])
    root = Path(__file__).resolve().parents[1]
    token, vault_secret = (secrets.token_hex(24) for _ in range(2))
    namespace = secrets.token_hex(12)
    with tempfile.TemporaryDirectory(prefix="ResearchAssistant upgrade ") as temporary:
        data = Path(temporary)
        database = data / "live-runs.sqlite3"
        run_id = str(uuid4())
        result = subprocess.run(
            [
                sys.executable,
                str(root / "tests/mvp4_subprocess_driver.py"),
                "run",
                "The fixture policy improves student outcomes.",
                "--db-path",
                str(database),
                "--run-id",
                run_id,
                "--max-tokens",
                "1000000",
                "--max-cost-usd",
                "1.00",
            ],
            cwd=root,
            env={
                **os.environ,
                "MIMO_API_KEY": "offline-test",
                "EXA_API_KEY": "offline-test",
                "OPENALEX_API_KEY": "offline-test",
                "SERPSEARCH_API_KEY": "offline-test",
                "MIMO_BASE_URL": "https://api.xiaomimimo.com/v1",
                "MIMO_MODEL": "mimo-v2.5-pro",
                "MVP4_DB_PATH": str(database),
                "MVP4_RUN_ID": run_id,
                "MVP4_MOCK_SCENARIO": "released",
                "MVP4_REPOSITORY_IDENTITY": "source-sha256:" + "a" * 64,
            },
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        assert result.returncode == 0
        env = {
            key: os.environ[key]
            for key in (
                "HOME",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
                "SystemRoot",
                "WINDIR",
                "TEMP",
                "TMPDIR",
            )
            if key in os.environ
        }
        env.update({"PATH": "", "RESEARCHASSISTANT_DATA_DIR": temporary})
        original_database = database.read_bytes()
        prior_brief: str | None = None
        identities: list[str] = []
        try:
            for index, resources in enumerate((previous, current)):
                executable = (
                    resources
                    / "backend"
                    / (
                        "researchassistant-backend.exe"
                        if sys.platform == "win32"
                        else "researchassistant-backend"
                    )
                )
                args = [str(executable), "--self-test"] + (
                    ["--verify-persistence"] if index else []
                )
                process = subprocess.Popen(
                    args,
                    env=env,
                    cwd=data,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                try:
                    assert process.stdin is not None and process.stdout is not None
                    process.stdin.write(
                        json.dumps(
                            {
                                "token": token,
                                "resources": str(resources),
                                "smoke_namespace": namespace,
                                "smoke_secret": vault_secret,
                            }
                        )
                        + "\n"
                    )
                    process.stdin.flush()
                    line = startup_line(process.stdout)
                    if not line:
                        assert process.stderr is not None
                        error = process.stderr.read()
                        for value in (token, namespace, vault_secret):
                            error = error.replace(value, "[redacted]")
                        raise RuntimeError(f"Upgrade launch {index} failed: {error}")
                    startup = json.loads(line)
                    identities.append(startup["identity"])
                    with httpx.Client(
                        base_url=startup["origin"],
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30,
                    ) as client:
                        history = client.get("/api/history", params={"db_path": str(database)})
                        history.raise_for_status()
                        assert len(history.json()["items"]) == 1
                        assert history.json()["items"][0]["run_id"] == run_id
                        snapshot = client.get(
                            f"/api/research/{run_id}", params={"db_path": str(database)}
                        )
                        snapshot.raise_for_status()
                        assert snapshot.json()["classification"] == "released"
                        brief = snapshot.json()["final_brief"]
                        assert brief
                        preferences = client.get("/api/preferences").json()
                        if index == 0:
                            prior_brief = brief
                            preferences["maxCost"] = "0.15"
                            client.post("/api/preferences", json=preferences).raise_for_status()
                            client.post(
                                "/api/credentials", json={"mimo_api_key": vault_secret}
                            ).raise_for_status()
                        else:
                            assert brief == prior_brief
                            assert preferences["maxCost"] == "0.15"
                            assert preferences["modelProfile"] == "standard-2026-09"
                    process.stdin.close()
                    assert process.wait(timeout=100) == 0
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
            assert identities[0] != identities[1], "Expected distinct preceding and new executables"
            assert database.read_bytes() == original_database
            print(
                "PASS: Phase 2 to Phase 3 native credential persistence, preference migration, "
                "identical validated historical brief and unchanged history database; "
                "new executable identity retained."
            )
        finally:
            executable = (
                current
                / "backend"
                / (
                    "researchassistant-backend.exe"
                    if sys.platform == "win32"
                    else "researchassistant-backend"
                )
            )
            subprocess.run(
                [str(executable), "--self-test", "--cleanup-smoke"],
                input=json.dumps(
                    {"token": token, "resources": str(current), "smoke_namespace": namespace}
                )
                + "\n",
                env=env,
                cwd=data,
                capture_output=True,
                text=True,
                timeout=45,
                check=True,
            )


if __name__ == "__main__":
    main()
