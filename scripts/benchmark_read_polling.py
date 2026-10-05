"""Measure full validation plus a representative status poll on synthetic DBs.

Example: .venv/bin/python scripts/benchmark_read_polling.py --output /tmp/read-polling.json
All benchmark databases are created in a temporary directory and removed on exit.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

from researchassistant.storage.sqlite_policy import is_busy_error
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    init_db,
    open_read_only_store,
)


def _build_database(path: Path, rows: int, payload_bytes: int, journal_mode: str) -> list[str]:
    init_db(str(path))
    run_ids = [str(uuid4()) for _ in range(rows)]
    claim = "x" * payload_bytes
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA journal_mode = {journal_mode}")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.executemany(
            (
                "INSERT INTO runs(run_id,status,raw_claim,current_stage,created_at,"
                "updated_at,completed_at) VALUES(?,?,?,?,?,?,NULL)"
            ),
            [
                (
                    run_id,
                    "planned",
                    claim,
                    "claim_planner",
                    "2026-10-04T12:00:00+00:00",
                    f"2026-10-04T12:{index % 60:02d}:00+00:00",
                )
                for index, run_id in enumerate(run_ids)
            ],
        )
    return run_ids


def _poll(path: Path, run_id: str) -> None:
    from uuid import UUID

    with open_read_only_store(path) as reader:
        reader.read_run(UUID(run_id))


def _writer(
    path: Path,
    run_ids: list[str],
    stop: threading.Event,
    counts: dict[str, object],
) -> None:
    try:
        connection = sqlite3.connect(path, timeout=1.0)
        index = 0
        commit_ms: list[float] = counts["commit_ms"]  # type: ignore[assignment]
        while not stop.is_set():
            run_id = run_ids[index % len(run_ids)]
            try:
                started = time.perf_counter()
                connection.execute(
                    "UPDATE runs SET updated_at=? WHERE run_id=?",
                    (f"2026-10-04T13:{index % 60:02d}:00+00:00", run_id),
                )
                connection.commit()
                commit_ms.append((time.perf_counter() - started) * 1000)
                counts["commits"] = int(counts["commits"]) + 1
            except sqlite3.OperationalError as exc:
                connection.rollback()
                if not is_busy_error(exc):
                    counts["worker_error"] = f"non-busy SQLite error: {exc}"
                    break
                counts["busy"] = int(counts["busy"]) + 1
            index += 1
            time.sleep(0.002)
        connection.close()
    except BaseException as exc:  # recorded and surfaced by the harness
        counts["worker_error"] = str(exc)


def _measure(
    path: Path,
    polls: int,
    concurrent_writer: bool,
    run_ids: list[str],
) -> dict[str, object]:
    tracemalloc.start()
    start = time.perf_counter()
    first_error: str | None = None
    try:
        _poll(path, run_ids[0])
    except DatabaseCompatibilityError as exc:
        first_error = f"{exc.result.issue}: {exc}"
    cold_ms = (time.perf_counter() - start) * 1000

    counts: dict[str, object] = {"commits": 0, "busy": 0, "commit_ms": []}
    stop = threading.Event()
    worker: threading.Thread | None = None
    if concurrent_writer:
        worker = threading.Thread(target=_writer, args=(path, run_ids, stop, counts), daemon=True)
        worker.start()
        time.sleep(0.015)

    samples: list[float] = []
    poll_errors = 0
    for _ in range(polls):
        started = time.perf_counter()
        try:
            _poll(path, run_ids[0])
        except DatabaseCompatibilityError as exc:
            poll_errors += 1
            first_error = first_error or f"{exc.result.issue}: {exc}"
        samples.append((time.perf_counter() - started) * 1000)

    if worker is not None:
        stop.set()
        worker.join(timeout=3)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    commit_samples: list[float] = counts["commit_ms"]  # type: ignore[assignment]
    return {
        "first_poll_ms": round(cold_ms, 3),
        "warm_median_ms": round(statistics.median(samples), 3),
        "warm_samples_ms": [round(sample, 3) for sample in samples],
        "polls": polls,
        "poll_errors": poll_errors,
        "concurrent_writer": concurrent_writer,
        "writer_commits": counts["commits"],
        "writer_busy": counts["busy"],
        "writer_commit_median_ms": (
            round(statistics.median(commit_samples), 3) if commit_samples else None
        ),
        "worker_error": counts.get("worker_error"),
        "python_peak_traced_bytes": peak_bytes,
        "first_error": first_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rows", default="10,1000,20000", help="comma-separated synthetic run counts"
    )
    parser.add_argument("--journal-modes", default="DELETE,WAL")
    parser.add_argument("--payload-bytes", type=int, default=4096)
    parser.add_argument("--polls", type=int, default=9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    row_counts = [int(value) for value in args.rows.split(",")]
    journal_modes = [value.upper() for value in args.journal_modes.split(",")]
    if any(value not in {"DELETE", "WAL"} for value in journal_modes):
        parser.error("journal-modes may contain only DELETE and WAL")
    if any(value < 1 for value in row_counts) or args.payload_bytes < 0 or args.polls < 1:
        parser.error("rows and polls must be positive; payload-bytes cannot be negative")

    result: dict[str, object] = {
        "method": "open_read_only_store (full schema/physical validation), read_run, close",
        "reader_journal_modes": journal_modes,
        "payload_bytes_per_run": args.payload_bytes,
        "warm_poll_count": args.polls,
        "scenarios": [],
    }
    with tempfile.TemporaryDirectory(prefix="ra-read-polling-") as directory:
        for rows in row_counts:
            path = Path(directory) / f"synthetic-{rows}.sqlite3"
            for journal_mode in journal_modes:
                for suffix in ("", "-wal", "-shm"):
                    previous_file = Path(f"{path}{suffix}")
                    if previous_file.exists():
                        previous_file.unlink()
                run_ids = _build_database(path, rows, args.payload_bytes, journal_mode)
                for concurrent in (False, True):
                    scenario = _measure(path, args.polls, concurrent, run_ids)
                    if scenario["worker_error"]:
                        raise RuntimeError(str(scenario["worker_error"]))
                    sidecars = [Path(f"{path}-{suffix}") for suffix in ("wal", "shm")]
                    wal_bytes = sidecars[0].stat().st_size if sidecars[0].exists() else 0
                    shm_bytes = sidecars[1].stat().st_size if sidecars[1].exists() else 0
                    size = path.stat().st_size + wal_bytes + shm_bytes
                    result["scenarios"].append(
                        {
                            "rows": rows,
                            "journal_mode": journal_mode,
                            "database_bytes": path.stat().st_size,
                            "wal_bytes": wal_bytes,
                            "shm_bytes": shm_bytes,
                            "database_and_sidecar_bytes": size,
                            **scenario,
                        }
                    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
