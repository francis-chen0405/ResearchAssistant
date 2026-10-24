"""Historical planner aggregate and immutable query persistence."""

from __future__ import annotations

from uuid import UUID

from researchassistant.contracts.historical import HistoricalRead
from researchassistant.contracts.models import (
    AmbiguityRecord,
    ClaimDefinition,
    PlannerOutput,
    SearchQuery,
)
from researchassistant.storage.store_types import (
    DatabaseReader as DatabaseReader,
)
from researchassistant.storage.store_types import ReadConnectionFactory, WriteConnectionFactory
from researchassistant.storage.store_types import (
    _dt_to_iso as _dt_to_iso,
)
from researchassistant.storage.store_types import (
    _iso_to_dt as _iso_to_dt,
)
from researchassistant.storage.store_types import (
    _read_execute as _read_execute,
)


def insert_planner_output(
    db_path: str, planner: PlannerOutput, *, _connect: WriteConnectionFactory
) -> None:
    if isinstance(planner, HistoricalRead) or any(
        isinstance(query, HistoricalRead) for query in planner.search_queries
    ):
        raise ValueError("historical Planner output is inspection-only")
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO planner_outputs
               (run_id, planner_prompt_version, planner_model_name, planned_at)
               VALUES (?, ?, ?, ?)""",
            (
                str(planner.run_id),
                planner.planner_prompt_version,
                planner.planner_model_name,
                _dt_to_iso(planner.planned_at),
            ),
        )
        cd = planner.claim_definition
        conn.execute(
            """INSERT INTO claim_definitions
               (run_id, claim_text, population, jurisdiction, time_period,
                comparison_baseline, intervention_or_exposure,
                causal_or_comparative_meaning, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(cd.run_id),
                cd.claim_text,
                cd.population,
                cd.jurisdiction,
                cd.time_period,
                cd.comparison_baseline,
                cd.intervention_or_exposure,
                cd.causal_or_comparative_meaning,
                _dt_to_iso(cd.created_at),
            ),
        )
        for amb in planner.ambiguities:
            conn.execute(
                """INSERT INTO ambiguities
                   (ambiguity_id, run_id, description, impact, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    str(amb.ambiguity_id),
                    str(amb.run_id),
                    amb.description,
                    amb.impact,
                    _dt_to_iso(amb.created_at),
                ),
            )
        for q in planner.search_queries:
            conn.execute(
                """INSERT INTO search_queries
                   (query_id, run_id, stance, provider, intent, query_round, strategy,
                    query_text, exclusion_parameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(q.query_id),
                    str(q.run_id),
                    q.stance.value,
                    q.provider.value,
                    q.intent.value,
                    q.query_round,
                    q.strategy,
                    q.query_text,
                    q.exclusion_parameters,
                    _dt_to_iso(q.created_at),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_search_queries(
    db_path: str, queries: tuple[SearchQuery, ...], *, _connect: WriteConnectionFactory
) -> None:
    """Append a distinct Planner round's queries without rewriting the initial plan."""
    if any(isinstance(query, HistoricalRead) for query in queries):
        raise ValueError("historical Planner queries are inspection-only")
    conn = _connect(db_path)
    try:
        for query in queries:
            conn.execute(
                """INSERT INTO search_queries
                   (query_id, run_id, stance, provider, intent, query_round, strategy,
                    query_text, exclusion_parameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(query.query_id),
                    str(query.run_id),
                    query.stance.value,
                    query.provider.value,
                    query.intent.value,
                    query.query_round,
                    query.strategy,
                    query.query_text,
                    query.exclusion_parameters,
                    _dt_to_iso(query.created_at),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def read_planner_output(
    db_path: DatabaseReader,
    run_id: UUID,
    *,
    _read_connection: ReadConnectionFactory,
    historical: bool = False,
) -> PlannerOutput:
    with _read_connection(db_path) as conn:
        po_row = _read_execute(
            conn, "SELECT * FROM planner_outputs WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if po_row is None:
            raise KeyError(f"planner output for run {run_id} not found")

        cd_row = _read_execute(
            conn, "SELECT * FROM claim_definitions WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        claim_def = ClaimDefinition(
            run_id=UUID(cd_row["run_id"]),
            claim_text=cd_row["claim_text"],
            population=cd_row["population"],
            jurisdiction=cd_row["jurisdiction"],
            time_period=cd_row["time_period"],
            comparison_baseline=cd_row["comparison_baseline"],
            intervention_or_exposure=cd_row["intervention_or_exposure"],
            causal_or_comparative_meaning=cd_row["causal_or_comparative_meaning"],
            created_at=_iso_to_dt(cd_row["created_at"]),
        )

        amb_rows = _read_execute(
            conn, "SELECT * FROM ambiguities WHERE run_id = ? ORDER BY created_at", (str(run_id),)
        ).fetchall()
        ambiguities = [
            AmbiguityRecord(
                run_id=UUID(r["run_id"]),
                ambiguity_id=UUID(r["ambiguity_id"]),
                description=r["description"],
                impact=r["impact"],
                created_at=_iso_to_dt(r["created_at"]),
            )
            for r in amb_rows
        ]

        query_columns = {
            row["name"]
            for row in _read_execute(conn, "PRAGMA table_info(search_queries)").fetchall()
        }
        provider_specific = {"provider", "intent"} <= query_columns
        partition = "stance, provider, query_round" if provider_specific else "stance, query_round"
        provider_order = ", provider" if provider_specific else ""
        q_rows = _read_execute(
            conn,
            f"""SELECT * FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY {partition}
                               ORDER BY rowid
                           ) AS planner_position
                    FROM search_queries
                    WHERE run_id = ?
                )
                WHERE planner_position = 1
                ORDER BY CASE stance WHEN 'supporting' THEN 0 ELSE 1 END
                         {provider_order}, query_round""",
            (str(run_id),),
        ).fetchall()
        queries = [
            dict(
                run_id=UUID(r["run_id"]),
                query_id=UUID(r["query_id"]),
                stance=r["stance"],
                provider=r["provider"] if provider_specific else "exa",
                intent=r["intent"] if provider_specific else "broad_web",
                query_round=r["query_round"],
                strategy=r["strategy"],
                query_text=r["query_text"],
                exclusion_parameters=r["exclusion_parameters"],
                created_at=_iso_to_dt(r["created_at"]),
            )
            for r in q_rows
        ]

        values = dict(
            run_id=UUID(po_row["run_id"]),
            claim_definition=claim_def,
            ambiguities=ambiguities,
            search_queries=queries,
            planner_prompt_version=po_row["planner_prompt_version"],
            planner_model_name=po_row["planner_model_name"],
            planned_at=_iso_to_dt(po_row["planned_at"]),
        )
        try:
            return PlannerOutput.model_validate(values)
        except ValueError:
            if not historical:
                raise
        from researchassistant.storage.historical_decode import decode_native_planner
        from researchassistant.storage.store import read_provider_run_contract

        try:
            contract = read_provider_run_contract(conn, run_id)
        except KeyError:
            contract = None
        return decode_native_planner(values, contract)
