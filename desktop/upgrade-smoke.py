"""Verify a preceding frozen build and the new build share durable data safely."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from smoke_support import BackendMonitor, wait_for_health

EXPECTED_CONFIGURABLE_STAGE_MODELS = {
    "planner": "gpt-6-luna-xhigh",
    "scout": "gpt-6-luna-high",
    "gap_analysis": "gpt-6-luna-xhigh",
    "search_agent": "gpt-6-luna-xhigh",
    "source_selection": "gpt-6-luna-xhigh",
    "extractor": "gpt-6-luna-high",
    "analyst": "gpt-6-luna-xhigh",
}


def _prepare_schema13_fixture(database: Path) -> None:
    """Make the generated history readable by a pre-schema-14 executable."""
    with sqlite3.connect(database) as conn:
        version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        if version != 14:
            raise ValueError(f"Expected generated schema 14, found {version}")
        populated_cache_usage = conn.execute(
            "SELECT COUNT(*) FROM model_route_attempts "
            "WHERE cached_input_tokens IS NOT NULL OR uncached_input_tokens IS NOT NULL"
        ).fetchone()[0]
        if populated_cache_usage:
            raise ValueError("Cannot discard recorded cache usage from the upgrade fixture")
        for name in ("cached_input_tokens", "uncached_input_tokens"):
            conn.execute(f"ALTER TABLE model_route_attempts DROP COLUMN {name}")
        conn.execute("DELETE FROM schema_migrations WHERE version = 14")


def main() -> None:
    if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] != "--previous-schema13"):
        raise ValueError("Usage: upgrade-smoke.py PREVIOUS CURRENT [--previous-schema13]")
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
        if len(sys.argv) == 4:
            _prepare_schema13_fixture(database)
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
                monitor = BackendMonitor(process, label=f"upgrade launch {index}")
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
                    line = monitor.startup()
                    startup = json.loads(line)
                    identities.append(startup["identity"])
                    with httpx.Client(
                        base_url=startup["origin"],
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30,
                    ) as client:
                        wait_for_health(client)
                        print(
                            f"Upgrade launch {index}: authenticated health ready in "
                            f"{time.monotonic() - monitor.started:.2f}s",
                            flush=True,
                        )
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
                            assert preferences["modelProfile"] == "configurable-2026-09"
                            assert preferences["stageModels"] == EXPECTED_CONFIGURABLE_STAGE_MODELS
                    process.stdin.close()
                    monitor.wait_exit()
                finally:
                    monitor.stop()
            assert identities[0] != identities[1], "Expected distinct preceding and new executables"
            assert database.read_bytes() == original_database
            print(
                "PASS: native credential persistence, configurable model-choice preference "
                "migration, identical validated historical brief and unchanged history "
                "database; new executable identity retained."
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
