"""The generated benchmark uses real historical declarations and preserves payloads."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run

from researchassistant.research.fixture_pipeline import run_fixture_pipeline
from researchassistant.storage.store import (
    init_db,
    insert_v2_ledger_admission,
    open_read_only_store,
)
from researchassistant.storage.store_schema import CURRENT_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "query_scale_fixture", ROOT / "scripts/benchmark_database_query_scale.py"
)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def _payloads(path: Path) -> dict[str, tuple[tuple[Any, ...], ...]]:
    with sqlite3.connect(path) as connection:
        tables = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'"
            )
        )
        return {
            table: tuple(tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"'))
            for table in tables
        }


def test_benchmark_fixture_is_actual_schema16_and_upgrades_without_payload_loss(
    tmp_path: Path,
) -> None:
    result = run_fixture_pipeline(ROOT / "tests/fixtures/basic_valid_run", output_dir=tmp_path)
    path = Path(result.db_path)
    before = _payloads(path)
    benchmark._downgrade_to_16(path)
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == 16
    assert _payloads(path) == before
    with sqlite3.connect(path) as connection:
        assert [
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
        ] == list(range(1, 17))
        assert (
            "BETWEEN 1 AND 3"
            in connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='v2_ledger_admissions'"
            ).fetchone()[0]
        )
    init_db(str(path))
    with open_read_only_store(path) as reader:
        assert reader.compatibility.schema_version == CURRENT_SCHEMA_VERSION
    assert _payloads(path) == before


def test_benchmark_refuses_to_discard_round_four_admission(tmp_path: Path) -> None:
    database, result = _run(tmp_path, Phase10Provider([_approved()]))
    source = result.source_results[0]
    assert source.ledger_record is not None
    insert_v2_ledger_admission(
        database,
        source.ledger_record.model_copy(update={"ledger_claim_id": uuid4()}),
        source.provenance.model_copy(update={"source_id": uuid4(), "discovery_round": 4}),
    )
    path = Path(database)
    before = path.read_bytes(), path.stat().st_mtime_ns
    with pytest.raises(ValueError, match="Round-4"):
        benchmark._downgrade_to_16(path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_benchmark_downgrade_rolls_back_on_final_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_fixture_pipeline(ROOT / "tests/fixtures/basic_valid_run", output_dir=tmp_path)
    path = Path(result.db_path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    original = benchmark.validate_recorded_database
    calls = []

    def fail_second(*args: Any, **kwargs: Any) -> int:
        calls.append(True)
        if len(calls) == 2:
            raise sqlite3.DatabaseError("generated final-validation failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(benchmark, "validate_recorded_database", fail_second)
    with pytest.raises(sqlite3.DatabaseError, match="final-validation failure"):
        benchmark._downgrade_to_16(path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
