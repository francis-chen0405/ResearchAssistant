"""Historical Planner inspection preserves recorded intent without enabling reuse."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from researchassistant.contracts.artifact_keys import PHASE9_ANALYSIS_ARTIFACT
from researchassistant.contracts.historical import HistoricalRead, RecordCompatibilityError
from researchassistant.contracts.models import (
    PersistedStageArtifact,
    PlannerOutput,
    ProviderRunContract,
)
from researchassistant.contracts.provider_results import AnalysisStageResult
from researchassistant.evidence.brief_export import BriefExportFormat, export_released_brief
from researchassistant.research.fixture_pipeline import FixturePipelineResult, run_fixture_pipeline
from researchassistant.storage.historical_decode import decode_native_planner
from researchassistant.storage.provider_history import inspect_provider_run
from researchassistant.storage.store import (
    insert_planner_output,
    insert_provider_run_contract,
    insert_search_queries,
    insert_stage_artifact,
    read_planner_output,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (ROOT / "tests/fixtures/historical_reads/legacy-researcher-trails.json").read_text()
)["cases"]


def _database(tmp_path: Path, index: int) -> tuple[Path, FixturePipelineResult]:
    result = run_fixture_pipeline(ROOT / "tests/fixtures/basic_valid_run", output_dir=tmp_path)
    database = Path(result.db_path)
    analysis = AnalysisStageResult(
        run_id=result.run_id,
        analyst_decisions=tuple(result.analyst_decisions),
        statement_drafts=tuple(result.statement_drafts),
        reviewer_decisions=tuple(result.reviewer_decisions),
        ledger_records=tuple(result.ledger_records),
    )
    insert_stage_artifact(
        str(database),
        PersistedStageArtifact(
            run_id=result.run_id,
            artifact_key=PHASE9_ANALYSIS_ARTIFACT,
            artifact_type="AnalysisStageResult",
            payload_json=analysis.model_dump_json(),
            created_at=result.planner_output.planned_at,
        ),
    )
    values = dict(CASES[index]["provider_contract"])
    values["run_id"] = str(result.run_id)
    insert_provider_run_contract(str(database), ProviderRunContract.model_validate(values))
    # Only the disposable fixture is altered to represent the recorded old contract.
    with closing(sqlite3.connect(database)) as conn:
        triggers = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='search_queries'"
        ).fetchall()
        for name, _sql in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.execute("UPDATE search_queries SET intent='academic_study' WHERE provider='exa'")
        for _name, sql in triggers:
            conn.execute(sql)
        conn.commit()
    return database, result


@pytest.mark.parametrize("index", [0, 1])
def test_historical_planner_export_preserves_intent_and_strict_resume(
    tmp_path: Path, index: int
) -> None:
    database, original = _database(tmp_path / "run", index)
    before = database.read_bytes(), database.stat().st_mtime_ns
    with pytest.raises(ValueError, match="academic-study"):
        read_planner_output(database, original.run_id)

    inspected = inspect_provider_run(database, original.run_id)
    assert inspected.final_brief == original.final_brief
    assert inspected.rendered_brief_hash == original.rendered_brief_hash
    planner = inspected.planner_output
    assert isinstance(planner, HistoricalRead)
    expected = original.planner_output.model_dump(mode="json")
    for query in expected["search_queries"]:
        if query["provider"] == "exa":
            query["intent"] = "academic_study"
    assert planner.model_dump(mode="json") == expected
    exported = export_released_brief(
        database, str(original.run_id), tmp_path / "report.md", BriefExportFormat.MARKDOWN
    )
    assert exported.metadata.rendered_brief_hash == original.rendered_brief_hash
    assert original.final_brief in Path(exported.output_path).read_text()
    with pytest.raises(ValueError, match="inspection-only"):
        insert_planner_output(str(database), planner)
    with pytest.raises(ValueError, match="academic-study"):
        PlannerOutput.model_validate(
            {**original.planner_output.model_dump(), "search_queries": planner.search_queries}
        )
    wrapped = original.planner_output.model_copy(update={"search_queries": planner.search_queries})
    with pytest.raises(ValueError, match="inspection-only"):
        insert_planner_output(str(database), wrapped)
    with pytest.raises(ValueError, match="inspection-only"):
        insert_search_queries(str(database), tuple(planner.search_queries))
    with pytest.raises(ValueError, match="academic-study"):
        read_planner_output(database, original.run_id)
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


@pytest.mark.parametrize("mutation", ["identity", "fingerprint", "run", "exclusions", "queries"])
def test_historical_planner_rejects_unrecognized_identity_and_invalid_shape(
    tmp_path: Path, mutation: str
) -> None:
    _database_path, original = _database(tmp_path / "run", 0)
    values = original.planner_output.model_dump(mode="json")
    for query in values["search_queries"]:
        if query["provider"] == "exa":
            query["intent"] = "academic_study"
    contract_values = dict(CASES[0]["provider_contract"])
    contract_values["run_id"] = str(original.run_id)
    contract = ProviderRunContract.model_validate(contract_values)
    if mutation == "identity":
        contract = contract.model_copy(update={"schema_identity": "unknown-schema"})
    elif mutation == "fingerprint":
        contract = contract.model_copy(update={"fingerprint_sha256": "0" * 64})
    elif mutation == "run":
        contract = contract.model_copy(update={"run_id": uuid4()})
    elif mutation == "exclusions":
        next(q for q in values["search_queries"] if q["provider"] == "exa")[
            "exclusion_parameters"
        ] = ""
    else:
        values["search_queries"].pop()
    with pytest.raises(RecordCompatibilityError):
        decode_native_planner(values, contract)


def test_historical_planner_without_recorded_contract_is_rejected(tmp_path: Path) -> None:
    database, original = _database(tmp_path / "run", 0)
    with closing(sqlite3.connect(database)) as conn:
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='provider_run_contracts'"
        ).fetchall()
        for (name,) in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.execute("DELETE FROM provider_run_contracts")
        conn.commit()
    before = database.read_bytes(), database.stat().st_mtime_ns
    with pytest.raises(RecordCompatibilityError, match="recorded Planner contract"):
        inspect_provider_run(database, original.run_id)
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before
