"""Read-only export of saved historical handoffs; no transport or guessed physical audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from evaluations.observation_safety import validate_artifact_content
from evaluations.research_quality import evaluate, summary
from evaluations.research_quality_contracts import (
    Artifact,
    Attempt,
    Benchmark,
    Observation,
    ReferenceSet,
    Topic,
)
from researchassistant.agents.v2_discovery import V2DiscoveryResponse
from researchassistant.contracts.research_acquisition import V2AcquisitionProbeOutput
from researchassistant.contracts.research_planning import V2InitialPlannerOutput
from researchassistant.platform_support.private_files import create_private_file, private_directory
from researchassistant.providers.v2_budget import read_v2_physical_call_audit
from researchassistant.storage.store import (
    open_read_only_store,
    read_v2_artifact,
    read_v2_physical_call_artifacts,
)


@contextmanager
def _private_export(output: Path) -> Iterator[Callable[[str, bytes, str], None]]:
    """Own exclusively created private files, removing only those on failure."""
    output.mkdir(parents=True, mode=0o700)
    directory_stat = output.stat()
    owned: list[tuple[Path, int, int]] = []

    def write(name: str, payload: bytes, media_type: str) -> None:
        validate_artifact_content(payload, media_type)
        path = output / name
        descriptor = create_private_file(path)
        file_stat = os.fstat(descriptor)
        owned.append((path, file_stat.st_dev, file_stat.st_ino))
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)

    try:
        private_directory(output)
        yield write
    except BaseException:
        for path, device, inode in reversed(owned):
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (device, inode):
                    path.unlink()
            except OSError:
                pass
        try:
            current = output.lstat()
            if (current.st_dev, current.st_ino) == (
                directory_stat.st_dev,
                directory_stat.st_ino,
            ):
                output.rmdir()
        except OSError:
            pass
        raise


def _saved_payload(
    connection: sqlite3.Connection,
    run_id: UUID,
    key: str,
    *,
    expected_type: str | None = None,
) -> str:
    try:
        saved = read_v2_artifact(connection, run_id, key)
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"saved {key} artifact checksum mismatch") from exc
    if saved.run_id != run_id or saved.artifact_key != key:
        raise ValueError(f"saved {key} artifact envelope belongs to another run or stage")
    if expected_type is not None and saved.artifact_type != expected_type:
        raise ValueError(f"saved {key} artifact type differs from its stage contract")
    validate_artifact_content(saved.payload_json.encode("utf-8"), "application/json")
    return saved.payload_json


def import_history(
    database: Path, output: Path, *, origin: Literal["fixture", "replayed_observation"]
) -> dict[str, object]:
    if output.exists() or output.is_symlink():
        raise ValueError("use a fresh private output directory; frozen observations are immutable")
    before = (hashlib.sha256(database.read_bytes()).hexdigest(), database.stat().st_mtime_ns)
    with _private_export(output) as write:
        artifacts: list[Artifact] = []

        def save(name: str, payload: str, role: str = "stage") -> Artifact:
            write(name, payload.encode("utf-8"), "application/json")
            artifact = Artifact(
                path=name,
                sha256=hashlib.sha256(payload.encode()).hexdigest(),
                media_type="application/json",
                role=role,
            )
            artifacts.append(artifact)
            return artifact

        topics = []
        observations = []
        with open_read_only_store(database) as reader:
            if not reader.connection.in_transaction:
                raise ValueError("saved history requires a pinned read-only snapshot")
            rows = reader.connection.execute(
                "SELECT a.run_id, a.created_at, r.raw_claim, "
                "r.created_at AS run_started, r.completed_at AS run_completed "
                "FROM v2_artifacts a JOIN runs r ON a.run_id=r.run_id "
                "WHERE a.artifact_key='phase-13-round-1-search' ORDER BY a.created_at, a.run_id"
            ).fetchall()
            snapshot_sha256 = hashlib.sha256(reader.connection.serialize()).hexdigest()
            schema = reader.compatibility.schema_version
            for index, row in enumerate(rows, 1):
                artifacts.clear()
                run_id = UUID(row["run_id"])
                search_payload = _saved_payload(
                    reader.connection, run_id, "phase-13-round-1-search"
                )
                stage = json.loads(search_payload)
                if UUID(stage["run_id"]) != run_id:
                    raise ValueError("saved search artifact belongs to another run")
                save(f"run-{index}-original-search.json", search_payload)
                for key, label, contract in [
                    ("phase-5-acquisition-probe", "acquisition", V2AcquisitionProbeOutput),
                    ("phase-3-initial-round-1-plan", "plan", V2InitialPlannerOutput),
                ]:
                    try:
                        payload = _saved_payload(
                            reader.connection, run_id, key, expected_type=contract.__name__
                        )
                    except KeyError:
                        continue
                    parsed = contract.model_validate_json(payload)
                    if parsed.run_id != run_id:
                        raise ValueError(f"saved {label} artifact belongs to another run")
                    save(f"run-{index}-original-{label}.json", payload)
                audit = read_v2_physical_call_audit(reader.connection, run_id)
                receipts = {
                    a.artifact_key: a
                    for a in read_v2_physical_call_artifacts(reader.connection, run_id)
                }
                attempts = []
                for start, completion in zip(audit.starts, audit.completions, strict=True):
                    prefix = f"phase-13-physical-call-{start.sequence:03d}"
                    if prefix + "-start" not in receipts:
                        prefix = f"phase-12-physical-call-{start.sequence:03d}"
                    request = save(
                        f"run-{index}-model-{start.sequence}-start.json",
                        receipts[prefix + "-start"].payload_json,
                        "request",
                    )
                    response = (
                        save(
                            f"run-{index}-model-{start.sequence}-completion.json",
                            receipts[prefix + "-completion"].payload_json,
                        )
                        if completion
                        else None
                    )
                    attempts.append(
                        Attempt(
                            attempt_id=f"model-{start.sequence}",
                            category="model",
                            provider="historical alias only",
                            endpoint="unavailable historical endpoint",
                            settings={
                                "stage": start.stage,
                                "model_alias": start.model_alias,
                                "exact_model_and_effort": None,
                                "raw_prompt_available": False,
                            },
                            started_at=start.started_at,
                            finished_at=completion.completed_at if completion else None,
                            outcome="unknown"
                            if completion is None
                            else "success"
                            if completion.succeeded
                            else "failure",
                            request=request,
                            request_kind="reservation_receipt",
                            response=response,
                            response_kind="completion_receipt",
                            reserved_usd=start.reserved_cost_usd,
                            actual_usd=completion.usage_cost_usd if completion else None,
                            cost_basis=str(
                                completion.usage_cost_basis
                                or "historical usage-cost field; invoice basis unavailable"
                            )
                            if completion and completion.usage_cost_usd is not None
                            else None,
                            tokens=completion.usage_tokens if completion else None,
                        )
                    )
                handoffs = []
                for number, outcome in enumerate(stage["outcomes"], 1):
                    response = V2DiscoveryResponse(
                        query=outcome["query"], results=outcome["results"]
                    )
                    if response.query.run_id != UUID(row["run_id"]):
                        raise ValueError("saved query belongs to another run")
                    if origin != "fixture" and any(
                        ".invalid" in result.original_url for result in response.results
                    ):
                        raise ValueError(
                            "saved fixture URLs cannot be imported as real observations"
                        )
                    handoffs.append(
                        save(
                            f"run-{index}-handoff-{number}.json",
                            response.model_dump_json(indent=2) + "\n",
                        ).path
                    )
                settings = save(
                    f"run-{index}-settings.json",
                    json.dumps(
                        {
                            "historical": True,
                            "raw_http_available": False,
                            "source_identity": None,
                            "model_settings": None,
                            "locale": None,
                            "physical_audit": (
                                "model receipts available; search/acquisition counts incomplete"
                            ),
                            "origin_basis": (
                                "caller-attested saved metadata; transport authenticity unverified"
                            ),
                            "query_settings": [o["query"] for o in stage["outcomes"]],
                        },
                        indent=2,
                    )
                    + "\n",
                    "request",
                )
                topic_id = f"historical-{index}"
                topics.append(
                    Topic(
                        topic_id=topic_id,
                        split="development",
                        claim=row["raw_claim"],
                        rationale=(
                            "Historical availability sample outside the representative pilot."
                        ),
                        short_query="unavailable",
                        concepts=("historical",),
                        reference=ReferenceSet(
                            status="pending",
                            method="No human useful reference set; no recall claim.",
                        ),
                    )
                )
                observations.append(
                    Observation(
                        observation_id=topic_id,
                        topic_id=topic_id,
                        arm="saved-round-one",
                        origin=origin,
                        collector="read-only saved-history importer",
                        provenance_note=(
                            f"Committed read snapshot SHA-256 {snapshot_sha256}, schema {schema}. "
                            "The pinned snapshot includes committed WAL contents; the separately "
                            "recorded main-file checksum does not identify the read snapshot. "
                            "Exact saved search JSON "
                            "preserved; typed query/result projection is derived. Original HTTP "
                            "bodies, full search/acquisition audit, exact source/model settings "
                            "and human judgments are unavailable in this export. Saved metadata "
                            "does not prove current live quality."
                        ),
                        source_identity="unavailable historical identity",
                        settings_sha256=settings.sha256,
                        settings_path=settings.path,
                        input_sha256=hashlib.sha256(row["raw_claim"].encode()).hexdigest(),
                        started_at=row["run_started"],
                        completed_at=row["run_completed"],
                        audit_complete=False,
                        candidate_inventory_complete=False,
                        final_inventory_complete=False,
                        attempts=tuple(attempts),
                        artifacts=tuple(artifacts),
                        discovery_handoff_paths=tuple(handoffs),
                    )
                )
        after = (hashlib.sha256(database.read_bytes()).hexdigest(), database.stat().st_mtime_ns)
        benchmark = Benchmark(
            schema_version="research-quality-v1",
            prepared_on="2026-10-11",
            baseline={
                "historical_availability_sample": True,
                "database_snapshot_sha256": snapshot_sha256,
                "database_snapshot_digest_method": "sqlite3 serialize of pinned read transaction",
                "database_read_snapshot_pinned": True,
                "database_main_file_sha256": before[0],
                "database_main_file_sha256_after": after[0],
                "database_main_file_mtime_ns": before[1],
                "database_main_file_mtime_ns_after": after[1],
                "schema": schema,
                "database_main_file_bytes_and_mtime_unchanged": before == after,
            },
            topics=tuple(topics),
            observations=tuple(observations),
        )
        manifest = output / "manifest.json"
        write(
            "manifest.json",
            (benchmark.model_dump_json(indent=2) + "\n").encode(),
            "application/json",
        )
        report = evaluate(manifest, replay=True)
        write(
            "results.json",
            (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(),
            "application/json",
        )
        write("summary.md", summary(report).encode(), "text/markdown")
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--origin", required=True, choices=["fixture", "replayed_observation"])
    args = parser.parse_args(argv)
    try:
        report = import_history(args.database, args.output_dir, origin=args.origin)
    except (ValueError, OSError, KeyError, sqlite3.Error):
        print("Saved-history import failed validation; no transport or database writes performed.")
        return 2
    print(f"Replayed {len(report['observations'])} saved observations; no new paid calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
