"""Migration-17 query indexes are strict and roll back with their ledger row."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from researchassistant.storage import store_schema
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    init_db,
    open_read_only_store,
)

_QUERY_INDEXES = (
    "runs_updated_history",
    "candidates_run_extracted_quote",
    "statement_drafts_run_quote_drafted",
    "statement_reviews_run_quote_reviewed",
    "ledger_records_run_quote_claim",
)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _query_indexes(path: Path) -> dict[str, str]:
    with _connect(path) as connection:
        return {
            row["name"]: row["sql"]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
            )
            if row["name"] in store_schema._REQUIRED_INDEXES
        }


def test_query_indexes_are_required_on_committed_schema(tmp_path: Path) -> None:
    path = tmp_path / "missing-index.sqlite3"
    init_db(str(path))
    with _connect(path) as connection:
        connection.execute("DROP INDEX runs_updated_history")
        connection.commit()
    before = path.read_bytes()

    with pytest.raises(DatabaseCompatibilityError, match="runs_updated_history"):
        open_read_only_store(path)

    assert path.read_bytes() == before


def test_pending_index_migration_is_atomic_and_can_reuse_valid_indexes(tmp_path: Path) -> None:
    path = tmp_path / "pending-indexes.sqlite3"
    init_db(str(path))
    _query_indexes(path)
    with _connect(path) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = 17")
        connection.commit()
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == 16

    with _connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_query_index_migration BEFORE INSERT ON schema_migrations "
            "WHEN NEW.version = 17 BEGIN SELECT RAISE(ABORT, 'injected migration 17 failure'); END"
        )
    before = path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="injected migration 17 failure"):
        store_schema._apply_query_indexes_migration(_connect(path))
    assert path.read_bytes() == before

    with _connect(path) as connection:
        connection.execute("DROP TRIGGER reject_query_index_migration")
        for name in _QUERY_INDEXES:
            connection.execute(f'DROP INDEX "{name}"')
        connection.commit()
        store_schema._apply_query_indexes_migration(connection)

    assert set(_query_indexes(path)) >= set(store_schema._REQUIRED_INDEXES)
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == store_schema.CURRENT_SCHEMA_VERSION
