"""Compare native evidence query scale at migration 16 and current schema.

Run from the repository root with ``.venv/bin/python scripts/benchmark_database_query_scale.py``.
The command creates only disposable databases in a temporary directory and prints JSON.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from shutil import copyfile
from sqlite3 import Connection, Row, connect
from tempfile import TemporaryDirectory
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import researchassistant.evidence.evidence_browser as current_browser  # noqa: E402
from researchassistant.research.fixture_pipeline import run_fixture_pipeline  # noqa: E402
from researchassistant.storage.store import init_db, list_runs  # noqa: E402

BASE_REVISION = "b25df1d"
QUERY_INDEXES = (
    "runs_updated_history",
    "candidates_run_extracted_quote",
    "statement_drafts_run_quote_drafted",
    "statement_reviews_run_quote_reviewed",
    "ledger_records_run_quote_claim",
)
TABLES = (
    "candidates",
    "snapshots",
    "analyst_decisions",
    "statement_drafts",
    "statement_review_attempts",
    "ledger_records",
)


def _legacy_browser() -> ModuleType:
    name = "researchassistant.evidence.evidence_browser_before_query_indexes"
    spec = importlib.util.spec_from_loader(name, loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    source = subprocess.check_output(
        ["git", "show", f"{BASE_REVISION}:researchassistant/evidence/evidence_browser.py"],
        cwd=ROOT,
        text=True,
    )
    exec(compile(source, f"{BASE_REVISION}:evidence_browser.py", "exec"), module.__dict__)
    return module


def _columns(connection: Connection, table: str) -> tuple[str, ...]:
    return tuple(row[1] for row in connection.execute(f'PRAGMA table_info("{table}")'))


def _row(connection: Connection, table: str, where: str, parameters: tuple[str, ...]) -> Row:
    connection.row_factory = Row
    result = connection.execute(f'SELECT * FROM "{table}" WHERE {where} LIMIT 1', parameters)
    row = result.fetchone()
    if row is None:
        raise RuntimeError(f"benchmark seed has no {table} row")
    return row


def _insert(connection: Connection, table: str, values: dict[str, object]) -> None:
    columns = tuple(values)
    marks = ", ".join("?" for _ in columns)
    names = ", ".join(f'"{name}"' for name in columns)
    connection.execute(
        f'INSERT INTO "{table}" ({names}) VALUES ({marks})',
        tuple(values[name] for name in columns),
    )


def _set_long_snapshot_text(database: Path, run_id: str, text_bytes: int) -> None:
    padding = " Synthetic supplemental source text for query scaling. " * (text_bytes // 56 + 2)
    with connect(database) as connection:
        trigger_sql = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
                "AND name IN ('snapshots_immutable_update', 'ledger_records_immutable_update')"
            )
        }
        for name in trigger_sql:
            connection.execute(f'DROP TRIGGER "{name}"')
        snapshots = tuple(
            (row[0], row[1])
            for row in connection.execute(
                "SELECT snapshot_id, normalized_text FROM snapshots WHERE run_id=?", (run_id,)
            )
        )
        for snapshot_id, original_text in snapshots:
            text = (original_text + padding)[:text_bytes]
            digest = hashlib.sha256(text.encode()).hexdigest()
            connection.execute(
                "UPDATE snapshots SET normalized_text=?, snapshot_sha256=?, word_count=? "
                "WHERE snapshot_id=?",
                (text, digest, len(text.split()), snapshot_id),
            )
            connection.execute(
                "UPDATE candidates SET snapshot_sha256=? WHERE run_id=? AND snapshot_id=?",
                (digest, run_id, snapshot_id),
            )
            connection.execute(
                "UPDATE provisional_extractions SET snapshot_sha256=? "
                "WHERE run_id=? AND snapshot_id=?",
                (digest, run_id, snapshot_id),
            )
            connection.execute(
                "UPDATE ledger_records SET snapshot_sha256=? WHERE run_id=? AND snapshot_id=?",
                (digest, run_id, snapshot_id),
            )
        for sql in trigger_sql.values():
            connection.execute(sql)


def _clone_candidate_chain(connection: Connection, run_id: str, count: int) -> None:
    candidate = _row(connection, "candidates", "run_id=?", (run_id,))
    source_quote_id = candidate["quote_block_id"]
    source_analyst = _row(
        connection,
        "analyst_decisions",
        "run_id=? AND quote_block_id=?",
        (run_id, source_quote_id),
    )
    source_drafts = tuple(
        connection.execute(
            "SELECT * FROM statement_drafts WHERE run_id=? AND quote_block_id=?",
            (run_id, source_quote_id),
        )
    )
    source_reviews = tuple(
        connection.execute(
            "SELECT * FROM statement_review_attempts WHERE run_id=? AND quote_block_id=?",
            (run_id, source_quote_id),
        )
    )
    source_ledgers = tuple(
        connection.execute(
            "SELECT * FROM ledger_records WHERE run_id=? AND quote_block_id=?",
            (run_id, source_quote_id),
        )
    )
    for _ in range(count - 2):
        quote_id = str(uuid.uuid4())
        values = dict(candidate)
        values["quote_block_id"] = quote_id
        _insert(connection, "candidates", values)

        analyst = dict(source_analyst)
        analyst["quote_block_id"] = quote_id
        _insert(connection, "analyst_decisions", analyst)

        draft_ids: dict[str, str] = {}
        for row in source_drafts:
            values = dict(row)
            draft_id = str(uuid.uuid4())
            draft_ids[row["statement_draft_id"]] = draft_id
            values.update(statement_draft_id=draft_id, quote_block_id=quote_id)
            _insert(connection, "statement_drafts", values)

        approval_ids: dict[str, str] = {}
        for row in source_reviews:
            values = dict(row)
            old_approval = row["reviewer_approval_id"]
            new_approval = str(uuid.uuid4()) if old_approval is not None else None
            if old_approval is not None:
                approval_ids[old_approval] = new_approval
            values.update(
                statement_draft_id=draft_ids[row["statement_draft_id"]],
                quote_block_id=quote_id,
                reviewer_approval_id=new_approval,
            )
            _insert(connection, "statement_review_attempts", values)

        for row in source_ledgers:
            values = dict(row)
            values.update(
                ledger_claim_id=str(uuid.uuid4()),
                quote_block_id=quote_id,
                reviewer_approval_id=approval_ids[row["reviewer_approval_id"]],
            )
            _insert(connection, "ledger_records", values)


def _add_history_runs(connection: Connection, count: int) -> None:
    row = connection.execute(
        "SELECT status, raw_claim, current_stage, created_at, updated_at, completed_at "
        "FROM runs LIMIT 1"
    ).fetchone()
    for index in range(count):
        values = (
            str(uuid.uuid4()),
            ("running", "completed", "failed", "cancelled")[index % 4],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
        )
        connection.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)", values)


def _downgrade_to_16(database: Path) -> None:
    with connect(database) as connection:
        for name in QUERY_INDEXES:
            connection.execute(f'DROP INDEX "{name}"')
        connection.execute("DELETE FROM schema_migrations WHERE version=17")


def _traced_browser(
    module: ModuleType, database: Path, run_id: uuid.UUID
) -> tuple[object, int, dict[str, int]]:
    trace: list[str] = []
    original = module.open_read_only_store

    @contextmanager
    def traced(path: str | Path) -> Iterator[object]:
        with original(path) as reader:
            reader.connection.set_trace_callback(trace.append)
            yield reader

    module.open_read_only_store = traced
    try:
        result = module.browse_evidence_run(database, run_id)
    finally:
        module.open_read_only_store = original
    selects = [sql for sql in trace if sql.lstrip().upper().startswith("SELECT")]
    related_counts = {
        table: sum(f"FROM {table.upper()}" in sql.upper() for sql in selects) for table in TABLES
    }
    return result, len(selects), related_counts


def _timing(module: ModuleType, database: Path, run_id: uuid.UUID) -> dict[str, float]:
    values: list[float] = []
    tracemalloc.start()
    for _ in range(4):
        started = time.perf_counter()
        module.browse_evidence_run(database, run_id)
        values.append((time.perf_counter() - started) * 1000)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "first_call_ms": round(values[0], 2),
        "warm_median_ms": round(statistics.median(values[1:]), 2),
        "peak_python_mib": round(peak / (1024 * 1024), 2),
    }


def _plans(database: Path, run_id: str, quote_id: str) -> dict[str, list[str]]:
    queries = {
        "history": (
            "SELECT * FROM runs ORDER BY updated_at DESC, run_id ASC LIMIT ?",
            (100,),
        ),
        "candidates": (
            "SELECT * FROM candidates WHERE run_id=? ORDER BY extracted_at, quote_block_id",
            (run_id,),
        ),
        "drafts": (
            "SELECT * FROM statement_drafts WHERE run_id=? AND quote_block_id=? "
            "ORDER BY drafted_at",
            (run_id, quote_id),
        ),
        "reviews": (
            "SELECT * FROM statement_review_attempts WHERE run_id=? AND quote_block_id=? "
            "ORDER BY reviewed_at",
            (run_id, quote_id),
        ),
        "ledger": (
            "SELECT * FROM ledger_records WHERE run_id=? AND quote_block_id=? "
            "ORDER BY ledger_claim_id",
            (run_id, quote_id),
        ),
    }
    with connect(f"file:{database}?mode=ro", uri=True) as connection:
        return {
            name: [row[3] for row in connection.execute(f"EXPLAIN QUERY PLAN {sql}", args)]
            for name, (sql, args) in queries.items()
        }


def main() -> None:
    legacy = _legacy_browser()
    report: dict[str, object] = {
        "baseline_revision": BASE_REVISION,
        "fixture": "tests/fixtures/basic_valid_run",
        "history_runs": 501,
        "source_text_bytes_per_snapshot": 65536,
        "filesystem_cache": "uncontrolled; first call is not described as a cold-cache run",
        "candidate_runs": {},
    }
    with TemporaryDirectory(prefix="ra-db-query-scale-") as temporary:
        root = Path(temporary)
        seeded = run_fixture_pipeline(
            ROOT / "tests/fixtures/basic_valid_run", output_dir=root / "seed"
        )
        base = root / "schema16-seed.sqlite3"
        copyfile(seeded.db_path, base)
        _downgrade_to_16(base)
        with connect(base) as connection:
            _set_long_snapshot_text(base, str(seeded.run_id), 65536)
            _add_history_runs(connection, 500)
        run_id = seeded.run_id
        quote_id = str(seeded.candidates[0].quote_block_id)

        for candidate_count in (2, 10, 40, 1000):
            before = root / f"schema16-{candidate_count}.sqlite3"
            after = root / f"schema17-{candidate_count}.sqlite3"
            copyfile(base, before)
            with connect(before) as connection:
                connection.row_factory = Row
                _clone_candidate_chain(connection, str(run_id), candidate_count)
            copyfile(before, after)

            prior, prior_selects, prior_related = _traced_browser(legacy, before, run_id)
            init_db(str(after))
            current, current_selects, current_related = _traced_browser(
                current_browser, after, run_id
            )
            if prior.model_dump(mode="json") != current.model_dump(mode="json"):
                raise AssertionError(f"browser output changed at {candidate_count} candidates")
            report["candidate_runs"][str(candidate_count)] = {
                "artifacts": "one Analyst, draft, Reviewer decision, and Ledger row per candidate",
                "legacy_total_selects": prior_selects,
                "indexed_total_selects": current_selects,
                "legacy_related_selects": prior_related,
                "indexed_related_selects": current_related,
                "typed_outputs_equal": True,
                "legacy_measurement": _timing(legacy, before, run_id),
                "indexed_measurement": _timing(current_browser, after, run_id),
            }

        report["schema16_query_plans"] = _plans(before, str(run_id), quote_id)
        report["schema17_query_plans"] = _plans(after, str(run_id), quote_id)
        started = time.perf_counter()
        returned = len(list_runs(str(after), limit=100))
        report["history_listing"] = {
            "history_rows": 501,
            "returned_rows": returned,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
