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


_SCHEMA13_MIGRATION_DESCRIPTIONS = {
    14: "persist cached and uncached model input-token usage",
    15: "persist model cache-write tokens and usage cost basis",
    16: "protect same-run provenance ownership and keys on update",
    17: "index history ordering and native evidence trail lookups",
}
_SCHEMA17_INDEXES = (
    "runs_updated_history",
    "candidates_run_extracted_quote",
    "statement_drafts_run_quote_drafted",
    "statement_reviews_run_quote_reviewed",
    "ledger_records_run_quote_claim",
)
_SCHEMA13_PROVENANCE_GUARD_TABLES = (
    "analyst_decisions",
    "candidates",
    "ledger_records",
    "provisional_extractions",
    "retrieval_attempts",
    "search_queries",
    "snapshots",
    "statement_drafts",
    "statement_review_attempts",
    "synthesis_items",
)
_SCHEMA13_USAGE_COLUMNS = (
    "cached_input_tokens",
    "uncached_input_tokens",
    "cache_write_tokens",
    "usage_cost_basis",
)


def _remove_post_schema13_objects(conn: sqlite3.Connection, version: int) -> None:
    """Remove only schema 14–17 objects from an isolated compatibility fixture."""
    if version >= 16:
        for table in _SCHEMA13_PROVENANCE_GUARD_TABLES:
            conn.execute(f"DROP TRIGGER {table}_provenance_immutable_update")
    if version >= 17:
        for index in _SCHEMA17_INDEXES:
            conn.execute(f"DROP INDEX {index}")
    for column in _SCHEMA13_USAGE_COLUMNS:
        if column in _schema13_attempt_columns(conn):
            conn.execute(f"ALTER TABLE model_route_attempts DROP COLUMN {column}")
    conn.execute("DELETE FROM schema_migrations WHERE version > 13")


def _schema13_attempt_columns(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[1]) for row in conn.execute("PRAGMA table_info(model_route_attempts)").fetchall()
    }


def _prepare_schema13_fixture(database: Path) -> None:
    """Convert a recognized generated schema 14–17 DB into a schema-13 fixture."""
    conn = sqlite3.connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT version, description FROM schema_migrations ORDER BY version"
        ).fetchall()
        if not rows:
            raise ValueError("Cannot make a schema-13 fixture without migration records")
        versions = [row[0] for row in rows]
        version = versions[-1]
        if version not in (14, 15, 16, 17) or versions != list(range(1, version + 1)):
            raise ValueError(
                f"Expected a complete recognized schema 14, 15, 16, or 17; found {version}"
            )
        descriptions = {row[0]: row[1] for row in rows}
        for introduced_version, expected in _SCHEMA13_MIGRATION_DESCRIPTIONS.items():
            if introduced_version <= version and descriptions.get(introduced_version) != expected:
                raise ValueError(f"Migration {introduced_version} description is inconsistent")

        columns = _schema13_attempt_columns(conn)
        expected_usage_columns = set(_SCHEMA13_USAGE_COLUMNS[:2])
        if version >= 15:
            expected_usage_columns.update(_SCHEMA13_USAGE_COLUMNS[2:])
        if not expected_usage_columns <= columns:
            raise ValueError("Generated schema is missing recognized model usage columns")
        if version == 14 and columns.intersection(_SCHEMA13_USAGE_COLUMNS[2:]):
            raise ValueError("Schema 14 contains usage columns from a later migration")

        if version >= 16:
            trigger_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
            trigger_names = {row[0] for row in trigger_rows}
            expected_triggers = {
                f"{table}_provenance_immutable_update"
                for table in _SCHEMA13_PROVENANCE_GUARD_TABLES
            }
            if not expected_triggers <= trigger_names:
                raise ValueError("Schema 16 is missing recognized provenance update guards")
        else:
            trigger_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
            if any(str(row[0]).endswith("_provenance_immutable_update") for row in trigger_rows):
                raise ValueError("Schema has unrecorded schema-16 provenance update guards")

        indexes = {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        if version >= 17 and not set(_SCHEMA17_INDEXES) <= indexes:
            raise ValueError("Schema 17 is missing recognized history/evidence indexes")
        if version < 17 and indexes.intersection(_SCHEMA17_INDEXES):
            raise ValueError("Schema has unrecorded schema-17 history/evidence indexes")

        existing_usage_columns = sorted(expected_usage_columns)
        populated_terms = " OR ".join(f"{column} IS NOT NULL" for column in existing_usage_columns)
        if conn.execute(
            f"SELECT 1 FROM model_route_attempts WHERE {populated_terms} LIMIT 1"
        ).fetchone():
            raise ValueError("Cannot discard recorded cache usage from the upgrade fixture")

        _remove_post_schema13_objects(conn, version)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


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
