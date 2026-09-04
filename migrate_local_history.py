"""Read-only local SQLite history migration to the hosted account boundary."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import os
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse

import httpx

from hosted import (
    LocalHistoryRun,
    MigrationBundle,
    MigrationResult,
    canonical_migration_fingerprint,
    utc_now,
)
from store import CURRENT_SCHEMA_VERSION, list_runs, open_read_only_store


def file_fingerprint(path: str | Path) -> str:
    """Hash the SQLite file in read-only mode for idempotency and mutation checks."""
    digest = hashlib.sha256()
    with Path(path).expanduser().resolve().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_migration_bundle(db_path: str | Path, *, limit: int = 1_000) -> MigrationBundle:
    """Read only run metadata and create a fingerprinted history-only bundle."""
    path = Path(db_path).expanduser().resolve()
    before = file_fingerprint(path)
    with open_read_only_store(path) as store:
        schema_version = store.compatibility.schema_version or CURRENT_SCHEMA_VERSION
        manifests = list_runs(store.connection, limit=limit)
    after = file_fingerprint(path)
    if before != after:
        raise RuntimeError("local database changed during read-only migration inspection")
    runs = tuple(
        LocalHistoryRun(
            local_run_id=manifest.run_id,
            raw_claim=manifest.raw_claim,
            status=manifest.status.value,
            stage=manifest.current_stage.value,
            updated_at=manifest.updated_at,
            completed_at=manifest.completed_at,
            fingerprint=canonical_migration_fingerprint(
                (
                    LocalHistoryRun(
                        local_run_id=manifest.run_id,
                        raw_claim=manifest.raw_claim,
                        status=manifest.status.value,
                        stage=manifest.current_stage.value,
                        updated_at=manifest.updated_at,
                        completed_at=manifest.completed_at,
                        fingerprint="0" * 64,
                        complete=manifest.status.value == "completed",
                        source_schema_version=schema_version,
                    ),
                ),
                schema_version,
            ),
            complete=manifest.status.value == "completed",
            source_schema_version=schema_version,
        )
        for manifest in manifests
    )
    return MigrationBundle(
        source_fingerprint=before,
        source_schema_version=schema_version,
        created_at=utc_now(),
        runs=runs,
    )


def migrate_local_history(
    db_path: str | Path,
    endpoint: str,
    access_token: str,
    *,
    limit: int = 1_000,
    client: httpx.Client | None = None,
) -> MigrationResult:
    """POST metadata over authenticated HTTPS without modifying the local source."""
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("hosted migration endpoint must use HTTPS")
    if not access_token:
        raise ValueError("an access token is required for migration")
    bundle = build_migration_bundle(db_path, limit=limit)
    request_client = client or httpx.Client(timeout=30.0)
    should_close = client is None
    try:
        response = request_client.post(
            endpoint.rstrip("/") + "/v1/migrations/local-history",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=bundle.model_dump(mode="json"),
        )
        if response.status_code >= 400:
            raise RuntimeError("hosted migration was rejected")
        return MigrationResult.model_validate(response.json())
    finally:
        if should_close:
            request_client.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the opt-in migration command and print only safe result metadata."""
    parser = argparse.ArgumentParser(description="Import local ResearchAssistant history.")
    parser.add_argument("database", type=Path)
    parser.add_argument("endpoint")
    parser.add_argument("--limit", type=int, default=1_000)
    parser.add_argument("--access-token", default=os.environ.get("HOSTED_ACCESS_TOKEN"))
    arguments = parser.parse_args(argv)
    access_token = arguments.access_token or getpass.getpass("Hosted access token: ")
    result = migrate_local_history(
        arguments.database,
        arguments.endpoint,
        access_token,
        limit=arguments.limit,
    )
    print(result.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
