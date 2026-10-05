"""Operation-count guards for native evidence browsing."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from researchassistant.evidence import evidence_browser
from researchassistant.research.fixture_pipeline import run_fixture_pipeline
from researchassistant.storage.store import init_db

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _ROOT / "tests" / "fixtures" / "basic_valid_run"


def _add_candidates(database: Path, run_id: str, count: int) -> None:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        source = connection.execute(
            "SELECT * FROM candidates WHERE run_id = ? LIMIT 1", (run_id,)
        ).fetchone()
        assert source is not None
        columns = tuple(source.keys())
        marks = ", ".join("?" for _ in columns)
        names = ", ".join(columns)
        for _ in range(count):
            values = tuple(
                str(uuid4()) if name == "quote_block_id" else source[name] for name in columns
            )
            connection.execute(f"INSERT INTO candidates ({names}) VALUES ({marks})", values)
        connection.commit()


def test_evidence_browser_batches_related_rows_for_small_and_large_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_fixture_pipeline(_FIXTURE, output_dir=tmp_path / "release")
    database = Path(result.db_path)
    _add_candidates(database, str(result.run_id), 38)

    statements: list[str] = []
    original = evidence_browser.open_read_only_store

    @contextmanager
    def traced(path: str | Path) -> Iterator[object]:
        with original(path) as reader:
            reader.connection.set_trace_callback(statements.append)
            yield reader

    monkeypatch.setattr(evidence_browser, "open_read_only_store", traced)
    browser = evidence_browser.browse_evidence_run(database, result.run_id)

    assert len(browser.trails) == 40
    assert all(
        trail.snapshot.snapshot_id == trail.candidate.snapshot_id for trail in browser.trails
    )
    target_tables = (
        "candidates",
        "snapshots",
        "analyst_decisions",
        "statement_drafts",
        "statement_review_attempts",
        "ledger_records",
    )
    reads = {
        table: [
            sql
            for sql in statements
            if sql.lstrip().upper().startswith("SELECT") and f"FROM {table.upper()}" in sql.upper()
        ]
        for table in target_tables
    }
    assert {table: len(queries) for table, queries in reads.items()} == {
        table: 1 for table in target_tables
    }


def test_evidence_browser_chunks_candidate_keys_below_sqlite_bind_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_fixture_pipeline(_FIXTURE, output_dir=tmp_path / "release")
    database = Path(result.db_path)
    _add_candidates(database, str(result.run_id), 998)

    statements: list[str] = []
    original = evidence_browser.open_read_only_store

    @contextmanager
    def traced(path: str | Path) -> Iterator[object]:
        with original(path) as reader:
            reader.connection.set_trace_callback(statements.append)
            yield reader

    monkeypatch.setattr(evidence_browser, "open_read_only_store", traced)
    browser = evidence_browser.browse_evidence_run(database, result.run_id)

    assert len(browser.trails) == 1000
    target_tables = (
        "candidates",
        "snapshots",
        "analyst_decisions",
        "statement_drafts",
        "statement_review_attempts",
        "ledger_records",
    )
    counts = {
        table: sum(
            sql.lstrip().upper().startswith("SELECT") and f"FROM {table.upper()}" in sql.upper()
            for sql in statements
        )
        for table in target_tables
    }
    assert counts == {
        "candidates": 1,
        "snapshots": 1,
        "analyst_decisions": 2,
        "statement_drafts": 2,
        "statement_review_attempts": 2,
        "ledger_records": 2,
    }


def test_empty_candidate_set_skips_all_related_table_queries(tmp_path: Path) -> None:
    database = tmp_path / "empty.sqlite3"
    init_db(str(database))
    statements: list[str] = []
    with sqlite3.connect(database) as connection:
        connection.set_trace_callback(statements.append)
        result = evidence_browser._trails(connection, uuid4(), None, compatibility_issues=[])

    assert result == ()
    select_statements = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
    assert len(select_statements) == 1
    assert "FROM candidates" in select_statements[0]


def test_batched_artifacts_preserve_legacy_timestamp_tie_order(tmp_path: Path) -> None:
    result = run_fixture_pipeline(_FIXTURE, output_dir=tmp_path / "release")
    database = Path(result.db_path)
    quote_id = str(result.candidates[0].quote_block_id)
    run_id = str(result.run_id)
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        draft = connection.execute(
            "SELECT * FROM statement_drafts WHERE run_id=? AND quote_block_id=? LIMIT 1",
            (run_id, quote_id),
        ).fetchone()
        review = connection.execute(
            "SELECT * FROM statement_review_attempts WHERE run_id=? AND quote_block_id=? LIMIT 1",
            (run_id, quote_id),
        ).fetchone()
        assert draft is not None and review is not None
        timestamp = "2026-10-04T12:00:00+00:00"
        connection.execute(
            "UPDATE statement_drafts SET drafted_at=? WHERE statement_draft_id=?",
            (timestamp, draft["statement_draft_id"]),
        )
        connection.execute(
            "UPDATE statement_review_attempts SET reviewed_at=? WHERE statement_draft_id=?",
            (timestamp, review["statement_draft_id"]),
        )
        for _ in range(2):
            draft_id = str(uuid4())
            values = {name: draft[name] for name in draft.keys()}
            values.update(statement_draft_id=draft_id, drafted_at=timestamp)
            columns = tuple(values)
            connection.execute(
                f"INSERT INTO statement_drafts ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(values[name] for name in columns),
            )
            review_values = {name: review[name] for name in review.keys()}
            review_values.update(
                statement_draft_id=draft_id,
                reviewer_approval_id=None,
                approved=0,
                approved_factual_statement=None,
                failure_code="not_entailed",
                reviewed_at=timestamp,
            )
            columns = tuple(review_values)
            connection.execute(
                f"INSERT INTO statement_review_attempts ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(review_values[name] for name in columns),
            )
        connection.commit()
        for name in (
            "runs_updated_history",
            "candidates_run_extracted_quote",
            "statement_drafts_run_quote_drafted",
            "statement_reviews_run_quote_reviewed",
            "ledger_records_run_quote_claim",
        ):
            connection.execute(f'DROP INDEX "{name}"')
        connection.execute("DELETE FROM schema_migrations WHERE version=17")
        connection.commit()
        review_plan = tuple(
            row[3]
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT statement_draft_id FROM statement_review_attempts "
                "WHERE run_id=? AND quote_block_id=? ORDER BY reviewed_at",
                (run_id, quote_id),
            )
        )
        assert any("USE TEMP B-TREE FOR ORDER BY" in item for item in review_plan)
        expected_drafts = tuple(
            row[0]
            for row in connection.execute(
                "SELECT statement_draft_id FROM statement_drafts "
                "WHERE run_id=? AND quote_block_id=? ORDER BY drafted_at",
                (run_id, quote_id),
            )
        )
        expected_reviews = tuple(
            row[0]
            for row in connection.execute(
                "SELECT statement_draft_id FROM statement_review_attempts "
                "WHERE run_id=? AND quote_block_id=? ORDER BY reviewed_at",
                (run_id, quote_id),
            )
        )

    init_db(str(database))

    trail = next(
        item
        for item in evidence_browser.browse_evidence_run(database, result.run_id).trails
        if item.candidate.quote_block_id == result.candidates[0].quote_block_id
    )
    assert tuple(str(item.statement_draft_id) for item in trail.statement_drafts) == expected_drafts
    assert (
        tuple(str(item.statement_draft_id) for item in trail.reviewer_decisions) == expected_reviews
    )
