"""SQLite persistence layer for the Debate Research Agent System.

All functions accept an explicit *db_path* (or an already-open connection
via internal helpers).  No global connections are used.  Foreign keys are
enabled on every connection.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from uuid import UUID

from models import (
    AmbiguityRecord,
    CandidateQuoteBlock,
    ClaimDefinition,
    LedgerRecord,
    ModelInvocationRecord,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    RunManifest,
    ScoreDecision,
    SearchQuery,
    SegmentOffset,
    SourceSnapshot,
    StatementDraft,
    StatementReviewResult,
    SynthesisItem,
    SynthesisOutput,
    SynthesisSection,
    ValidationError,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def init_db(db_path: str) -> None:
    """Create every table if it does not already exist."""
    conn = _connect(db_path)
    try:
        conn.executescript(
            """
            -- schema migrations -------------------------------------------
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version      INTEGER PRIMARY KEY,
                description  TEXT NOT NULL,
                applied_at   TEXT NOT NULL
            );

            INSERT OR IGNORE INTO schema_migrations
                (version, description, applied_at)
                VALUES (
                    1,
                    'phase-2 initial sqlite schema',
                    '2026-06-26T00:00:00+00:00'
                );

            -- runs --------------------------------------------------------
            CREATE TABLE IF NOT EXISTS runs (
                run_id          TEXT PRIMARY KEY,
                status          TEXT NOT NULL,
                raw_claim       TEXT NOT NULL,
                current_stage   TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                completed_at    TEXT
            );

            -- planner outputs ----------------------------------------------
            CREATE TABLE IF NOT EXISTS planner_outputs (
                run_id                  TEXT PRIMARY KEY REFERENCES runs(run_id),
                planner_prompt_version  TEXT NOT NULL,
                planner_model_name      TEXT NOT NULL,
                planned_at              TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS claim_definitions (
                run_id                          TEXT PRIMARY KEY REFERENCES planner_outputs(run_id),
                claim_text                      TEXT NOT NULL,
                population                      TEXT NOT NULL,
                jurisdiction                    TEXT NOT NULL,
                time_period                     TEXT NOT NULL,
                comparison_baseline             TEXT NOT NULL,
                intervention_or_exposure        TEXT NOT NULL,
                causal_or_comparative_meaning   TEXT NOT NULL,
                created_at                      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ambiguities (
                ambiguity_id    TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL REFERENCES planner_outputs(run_id),
                description     TEXT NOT NULL,
                impact          TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS search_queries (
                query_id            TEXT PRIMARY KEY,
                run_id              TEXT NOT NULL REFERENCES planner_outputs(run_id),
                stance              TEXT NOT NULL,
                query_round         INTEGER NOT NULL,
                strategy            TEXT NOT NULL,
                query_text          TEXT NOT NULL,
                exclusion_parameters TEXT NOT NULL,
                created_at          TEXT NOT NULL
            );

            -- retrieval attempts -------------------------------------------
            CREATE TABLE IF NOT EXISTS retrieval_attempts (
                retrieval_attempt_id TEXT PRIMARY KEY,
                run_id               TEXT NOT NULL REFERENCES runs(run_id),
                query_id             TEXT NOT NULL REFERENCES search_queries(query_id),
                query_round          INTEGER NOT NULL,
                query_text           TEXT NOT NULL,
                search_rank          INTEGER NOT NULL,
                source_url           TEXT NOT NULL,
                resolved_url         TEXT NOT NULL,
                status               TEXT NOT NULL,
                retrieved_at         TEXT NOT NULL
            );

            -- snapshots (INSERT-ONLY) --------------------------------------
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id           TEXT PRIMARY KEY,
                run_id                TEXT NOT NULL REFERENCES runs(run_id),
                retrieval_attempt_id  TEXT NOT NULL
                    REFERENCES retrieval_attempts(retrieval_attempt_id),
                source_url            TEXT NOT NULL,
                retrieved_at          TEXT NOT NULL,
                normalized_text       TEXT NOT NULL,
                snapshot_sha256       TEXT NOT NULL,
                word_count            INTEGER NOT NULL,
                truncated             INTEGER NOT NULL,
                created_at            TEXT NOT NULL
            );

            -- provisional extractions --------------------------------------
            CREATE TABLE IF NOT EXISTS provisional_extractions (
                run_id                   TEXT NOT NULL REFERENCES runs(run_id),
                stance                   TEXT NOT NULL,
                source_url               TEXT NOT NULL,
                retrieval_attempt_id     TEXT NOT NULL
                    REFERENCES retrieval_attempts(retrieval_attempt_id),
                query_id                 TEXT NOT NULL REFERENCES search_queries(query_id),
                query_round              INTEGER NOT NULL,
                search_rank              INTEGER NOT NULL,
                snapshot_id              TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                snapshot_sha256          TEXT NOT NULL,
                extracted_quote_block    TEXT NOT NULL,
                extraction_prompt_version TEXT NOT NULL,
                extraction_model_name    TEXT NOT NULL,
                extracted_at             TEXT NOT NULL
            );

            -- candidates ---------------------------------------------------
            CREATE TABLE IF NOT EXISTS candidates (
                quote_block_id            TEXT PRIMARY KEY,
                run_id                    TEXT NOT NULL REFERENCES runs(run_id),
                stance                    TEXT NOT NULL,
                source_url                TEXT NOT NULL,
                retrieval_attempt_id      TEXT NOT NULL
                    REFERENCES retrieval_attempts(retrieval_attempt_id),
                query_id                  TEXT NOT NULL REFERENCES search_queries(query_id),
                query_round               INTEGER NOT NULL,
                search_rank               INTEGER NOT NULL,
                retrieved_at              TEXT NOT NULL,
                snapshot_id               TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                snapshot_sha256           TEXT NOT NULL,
                snapshot_created_at       TEXT NOT NULL,
                extracted_quote_block     TEXT NOT NULL,
                segment_offsets           TEXT NOT NULL,
                raw_segment_word_count    INTEGER NOT NULL,
                has_statistical_markers   INTEGER NOT NULL,
                claim_keyword_match_count INTEGER NOT NULL,
                truncated                 INTEGER NOT NULL,
                extraction_prompt_version TEXT NOT NULL,
                extraction_model_name     TEXT NOT NULL,
                extracted_at              TEXT NOT NULL,
                post_filter_version       TEXT NOT NULL,
                post_filter_validated_at  TEXT NOT NULL
            );

            -- analyst decisions --------------------------------------------
            CREATE TABLE IF NOT EXISTS analyst_decisions (
                run_id                  TEXT NOT NULL REFERENCES runs(run_id),
                quote_block_id          TEXT NOT NULL REFERENCES candidates(quote_block_id),
                evidence_quality        INTEGER NOT NULL,
                claim_fit               INTEGER NOT NULL,
                ledger_score            INTEGER,
                placement               TEXT,
                approved                INTEGER NOT NULL,
                rationale               TEXT NOT NULL,
                analyst_prompt_version  TEXT NOT NULL,
                analyst_model_name      TEXT NOT NULL,
                scored_at               TEXT NOT NULL,
                PRIMARY KEY (run_id, quote_block_id)
            );

            -- statement review attempts ------------------------------------
            CREATE TABLE IF NOT EXISTS statement_drafts (
                statement_draft_id  TEXT PRIMARY KEY,
                run_id              TEXT NOT NULL REFERENCES runs(run_id),
                quote_block_id      TEXT NOT NULL REFERENCES candidates(quote_block_id),
                stance              TEXT NOT NULL,
                draft_statement     TEXT NOT NULL,
                claim_fit           INTEGER NOT NULL,
                analyst_prompt_version TEXT NOT NULL,
                analyst_model_name  TEXT NOT NULL,
                drafted_at          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS statement_review_attempts (
                run_id                       TEXT NOT NULL REFERENCES runs(run_id),
                statement_draft_id           TEXT NOT NULL
                    REFERENCES statement_drafts(statement_draft_id),
                quote_block_id               TEXT NOT NULL REFERENCES candidates(quote_block_id),
                approved                     INTEGER NOT NULL,
                reviewer_approval_id         TEXT UNIQUE,
                approved_factual_statement   TEXT,
                failure_code                 TEXT,
                rationale                    TEXT NOT NULL,
                reviewer_prompt_version      TEXT NOT NULL,
                reviewer_model_name          TEXT NOT NULL,
                reviewed_at                  TEXT NOT NULL,
                PRIMARY KEY (run_id, statement_draft_id)
            );

            -- ledger (INSERT-ONLY) -----------------------------------------
            CREATE TABLE IF NOT EXISTS ledger_records (
                ledger_claim_id              TEXT PRIMARY KEY,
                run_id                       TEXT NOT NULL REFERENCES runs(run_id),
                quote_block_id               TEXT NOT NULL REFERENCES candidates(quote_block_id),
                stance                       TEXT NOT NULL,
                approved_factual_statement   TEXT NOT NULL,
                approved_claim_text          TEXT NOT NULL,
                evidence_quality             INTEGER NOT NULL,
                claim_fit                    INTEGER NOT NULL,
                ledger_score                 INTEGER NOT NULL,
                placement                    TEXT NOT NULL,
                entailment                   TEXT NOT NULL,
                source_url                   TEXT NOT NULL,
                retrieval_attempt_id         TEXT NOT NULL
                    REFERENCES retrieval_attempts(retrieval_attempt_id),
                snapshot_id                  TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                snapshot_sha256              TEXT NOT NULL,
                segment_offsets              TEXT NOT NULL,
                analyst_prompt_version       TEXT NOT NULL,
                analyst_model_name           TEXT NOT NULL,
                analyst_completed_at         TEXT NOT NULL,
                reviewer_prompt_version      TEXT NOT NULL,
                reviewer_model_name          TEXT NOT NULL,
                reviewed_at                  TEXT NOT NULL,
                reviewer_approval_id         TEXT NOT NULL
                    REFERENCES statement_review_attempts(reviewer_approval_id),
                ledger_validated_at          TEXT NOT NULL
            );

            -- synthesis attempts -------------------------------------------
            CREATE TABLE IF NOT EXISTS synthesis_attempts (
                run_id                        TEXT PRIMARY KEY REFERENCES runs(run_id),
                synthesizer_prompt_version    TEXT NOT NULL,
                synthesizer_model_name        TEXT NOT NULL,
                created_at                    TEXT NOT NULL,
                title                         TEXT NOT NULL,
                claim_definition              TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS synthesis_sections (
                run_id          TEXT NOT NULL REFERENCES synthesis_attempts(run_id),
                section_type    TEXT NOT NULL,
                heading         TEXT NOT NULL,
                section_order   INTEGER NOT NULL,
                PRIMARY KEY (run_id, section_order)
            );

            CREATE TABLE IF NOT EXISTS synthesis_items (
                run_id                       TEXT NOT NULL REFERENCES synthesis_attempts(run_id),
                section_order                INTEGER NOT NULL,
                item_order                   INTEGER NOT NULL,
                connective_template_id       TEXT NOT NULL,
                ledger_claim_id              TEXT NOT NULL
                    REFERENCES ledger_records(ledger_claim_id),
                reviewer_approval_id         TEXT NOT NULL,
                stance                       TEXT NOT NULL,
                placement                    TEXT NOT NULL,
                entailment                   TEXT NOT NULL,
                approved_factual_statement   TEXT NOT NULL,
                PRIMARY KEY (run_id, section_order, item_order),
                FOREIGN KEY (run_id, section_order)
                    REFERENCES synthesis_sections(run_id, section_order)
            );

            -- validation runs ----------------------------------------------
            CREATE TABLE IF NOT EXISTS validation_runs (
                run_id                    TEXT PRIMARY KEY REFERENCES runs(run_id),
                valid                     INTEGER NOT NULL,
                validator_config_version  TEXT NOT NULL,
                validated_at              TEXT NOT NULL,
                rendered_brief_hash       TEXT
            );

            CREATE TABLE IF NOT EXISTS validation_errors (
                run_id          TEXT NOT NULL REFERENCES validation_runs(run_id),
                error_order     INTEGER NOT NULL,
                code            TEXT NOT NULL,
                location        TEXT NOT NULL,
                message         TEXT NOT NULL,
                PRIMARY KEY (run_id, error_order)
            );

            -- model invocations --------------------------------------------
            CREATE TABLE IF NOT EXISTS model_invocations (
                invocation_id        TEXT PRIMARY KEY,
                run_id               TEXT NOT NULL REFERENCES runs(run_id),
                stage                TEXT NOT NULL,
                prompt_version       TEXT NOT NULL,
                model_name           TEXT NOT NULL,
                input_artifact_id    TEXT NOT NULL,
                output_artifact_id   TEXT,
                status               TEXT NOT NULL,
                invoked_at           TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _dt_to_iso(dt: datetime) -> str:
    """Convert a timezone-aware datetime to an ISO-8601 string."""
    return dt.astimezone(UTC).isoformat()


def _iso_to_dt(value: str) -> datetime:
    """Parse an ISO-8601 string back to a timezone-aware datetime."""
    return datetime.fromisoformat(value)


def _offsets_to_json(offsets: list[SegmentOffset]) -> str:
    return json.dumps([{"start_char": o.start_char, "end_char": o.end_char} for o in offsets])


def _json_to_offsets(raw: str) -> list[SegmentOffset]:
    return [
        SegmentOffset(start_char=d["start_char"], end_char=d["end_char"]) for d in json.loads(raw)
    ]


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def insert_run(db_path: str, manifest: RunManifest) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO runs
               (run_id, status, raw_claim, current_stage, created_at, updated_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(manifest.run_id),
                manifest.status.value,
                manifest.raw_claim,
                manifest.current_stage.value,
                _dt_to_iso(manifest.created_at),
                _dt_to_iso(manifest.updated_at),
                _dt_to_iso(manifest.completed_at) if manifest.completed_at else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_run(db_path: str, run_id: UUID) -> RunManifest:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (str(run_id),)).fetchone()
        if row is None:
            raise KeyError(f"run {run_id} not found")
        return _row_to_run(row)
    finally:
        conn.close()


def _row_to_run(row: sqlite3.Row) -> RunManifest:
    completed = _iso_to_dt(row["completed_at"]) if row["completed_at"] else None
    return RunManifest(
        run_id=UUID(row["run_id"]),
        status=row["status"],
        raw_claim=row["raw_claim"],
        current_stage=row["current_stage"],
        created_at=_iso_to_dt(row["created_at"]),
        updated_at=_iso_to_dt(row["updated_at"]),
        completed_at=completed,
    )


# ---------------------------------------------------------------------------
# Planner outputs
# ---------------------------------------------------------------------------


def insert_planner_output(db_path: str, planner: PlannerOutput) -> None:
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
                   (query_id, run_id, stance, query_round, strategy,
                    query_text, exclusion_parameters, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(q.query_id),
                    str(q.run_id),
                    q.stance.value,
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


def read_planner_output(db_path: str, run_id: UUID) -> PlannerOutput:
    conn = _connect(db_path)
    try:
        po_row = conn.execute(
            "SELECT * FROM planner_outputs WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if po_row is None:
            raise KeyError(f"planner output for run {run_id} not found")

        cd_row = conn.execute(
            "SELECT * FROM claim_definitions WHERE run_id = ?", (str(run_id),)
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

        amb_rows = conn.execute(
            "SELECT * FROM ambiguities WHERE run_id = ? ORDER BY created_at", (str(run_id),)
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

        q_rows = conn.execute(
            "SELECT * FROM search_queries WHERE run_id = ? ORDER BY created_at", (str(run_id),)
        ).fetchall()
        queries = [
            SearchQuery(
                run_id=UUID(r["run_id"]),
                query_id=UUID(r["query_id"]),
                stance=r["stance"],
                query_round=r["query_round"],
                strategy=r["strategy"],
                query_text=r["query_text"],
                exclusion_parameters=r["exclusion_parameters"],
                created_at=_iso_to_dt(r["created_at"]),
            )
            for r in q_rows
        ]

        return PlannerOutput(
            run_id=UUID(po_row["run_id"]),
            claim_definition=claim_def,
            ambiguities=ambiguities,
            search_queries=queries,
            planner_prompt_version=po_row["planner_prompt_version"],
            planner_model_name=po_row["planner_model_name"],
            planned_at=_iso_to_dt(po_row["planned_at"]),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Retrieval attempts
# ---------------------------------------------------------------------------


def insert_retrieval_attempt(db_path: str, record: RetrievalRecord) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO retrieval_attempts
               (retrieval_attempt_id, run_id, query_id, query_round, query_text,
                search_rank, source_url, resolved_url, status, retrieved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(record.retrieval_attempt_id),
                str(record.run_id),
                str(record.query_id),
                record.query_round,
                record.query_text,
                record.search_rank,
                record.source_url,
                record.resolved_url,
                record.status.value,
                _dt_to_iso(record.retrieved_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_retrieval_attempt(db_path: str, retrieval_attempt_id: UUID) -> RetrievalRecord:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM retrieval_attempts WHERE retrieval_attempt_id = ?",
            (str(retrieval_attempt_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"retrieval attempt {retrieval_attempt_id} not found")
        return RetrievalRecord(
            run_id=UUID(row["run_id"]),
            retrieval_attempt_id=UUID(row["retrieval_attempt_id"]),
            query_id=UUID(row["query_id"]),
            query_round=row["query_round"],
            query_text=row["query_text"],
            search_rank=row["search_rank"],
            source_url=row["source_url"],
            resolved_url=row["resolved_url"],
            status=row["status"],
            retrieved_at=_iso_to_dt(row["retrieved_at"]),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Snapshots (INSERT-ONLY — no update / delete)
# ---------------------------------------------------------------------------


def insert_snapshot(db_path: str, snapshot: SourceSnapshot) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO snapshots
               (snapshot_id, run_id, retrieval_attempt_id, source_url, retrieved_at,
                normalized_text, snapshot_sha256, word_count, truncated, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(snapshot.snapshot_id),
                str(snapshot.run_id),
                str(snapshot.retrieval_attempt_id),
                snapshot.source_url,
                _dt_to_iso(snapshot.retrieved_at),
                snapshot.normalized_text,
                snapshot.snapshot_sha256,
                snapshot.word_count,
                int(snapshot.truncated),
                _dt_to_iso(snapshot.created_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_snapshot(db_path: str, snapshot_id: UUID) -> SourceSnapshot:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?", (str(snapshot_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"snapshot {snapshot_id} not found")
        return SourceSnapshot(
            run_id=UUID(row["run_id"]),
            retrieval_attempt_id=UUID(row["retrieval_attempt_id"]),
            snapshot_id=UUID(row["snapshot_id"]),
            source_url=row["source_url"],
            retrieved_at=_iso_to_dt(row["retrieved_at"]),
            normalized_text=row["normalized_text"],
            snapshot_sha256=row["snapshot_sha256"],
            word_count=row["word_count"],
            truncated=bool(row["truncated"]),
            created_at=_iso_to_dt(row["created_at"]),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Provisional extractions
# ---------------------------------------------------------------------------


def insert_provisional_extraction(db_path: str, prov: ProvisionalCandidate) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO provisional_extractions
               (run_id, stance, source_url, retrieval_attempt_id, query_id,
                query_round, search_rank, snapshot_id, snapshot_sha256,
                extracted_quote_block, extraction_prompt_version,
                extraction_model_name, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(prov.run_id),
                prov.stance.value,
                prov.source_url,
                str(prov.retrieval_attempt_id),
                str(prov.query_id),
                prov.query_round,
                prov.search_rank,
                str(prov.snapshot_id),
                prov.snapshot_sha256,
                prov.extracted_quote_block,
                prov.extraction_prompt_version,
                prov.extraction_model_name,
                _dt_to_iso(prov.extracted_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_provisional_extractions(db_path: str, run_id: UUID) -> list[ProvisionalCandidate]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM provisional_extractions WHERE run_id = ? ORDER BY extracted_at",
            (str(run_id),),
        ).fetchall()
        return [
            ProvisionalCandidate(
                run_id=UUID(r["run_id"]),
                stance=r["stance"],
                source_url=r["source_url"],
                retrieval_attempt_id=UUID(r["retrieval_attempt_id"]),
                query_id=UUID(r["query_id"]),
                query_round=r["query_round"],
                search_rank=r["search_rank"],
                snapshot_id=UUID(r["snapshot_id"]),
                snapshot_sha256=r["snapshot_sha256"],
                extracted_quote_block=r["extracted_quote_block"],
                extraction_prompt_version=r["extraction_prompt_version"],
                extraction_model_name=r["extraction_model_name"],
                extracted_at=_iso_to_dt(r["extracted_at"]),
            )
            for r in rows
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


def insert_candidate(db_path: str, candidate: CandidateQuoteBlock) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO candidates
               (quote_block_id, run_id, stance, source_url, retrieval_attempt_id,
                query_id, query_round, search_rank, retrieved_at, snapshot_id,
                snapshot_sha256, snapshot_created_at, extracted_quote_block,
                segment_offsets, raw_segment_word_count, has_statistical_markers,
                claim_keyword_match_count, truncated, extraction_prompt_version,
                extraction_model_name, extracted_at, post_filter_version,
                post_filter_validated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(candidate.quote_block_id),
                str(candidate.run_id),
                candidate.stance.value,
                candidate.source_url,
                str(candidate.retrieval_attempt_id),
                str(candidate.query_id),
                candidate.query_round,
                candidate.search_rank,
                _dt_to_iso(candidate.retrieved_at),
                str(candidate.snapshot_id),
                candidate.snapshot_sha256,
                _dt_to_iso(candidate.snapshot_created_at),
                candidate.extracted_quote_block,
                _offsets_to_json(candidate.segment_offsets),
                candidate.raw_segment_word_count,
                int(candidate.has_statistical_markers),
                candidate.claim_keyword_match_count,
                int(candidate.truncated),
                candidate.extraction_prompt_version,
                candidate.extraction_model_name,
                _dt_to_iso(candidate.extracted_at),
                candidate.post_filter_version,
                _dt_to_iso(candidate.post_filter_validated_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_candidate(db_path: str, quote_block_id: UUID) -> CandidateQuoteBlock:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM candidates WHERE quote_block_id = ?", (str(quote_block_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"candidate {quote_block_id} not found")
        return _row_to_candidate(row)
    finally:
        conn.close()


def _row_to_candidate(row: sqlite3.Row) -> CandidateQuoteBlock:
    return CandidateQuoteBlock(
        run_id=UUID(row["run_id"]),
        stance=row["stance"],
        quote_block_id=UUID(row["quote_block_id"]),
        source_url=row["source_url"],
        retrieval_attempt_id=UUID(row["retrieval_attempt_id"]),
        query_id=UUID(row["query_id"]),
        query_round=row["query_round"],
        search_rank=row["search_rank"],
        retrieved_at=_iso_to_dt(row["retrieved_at"]),
        snapshot_id=UUID(row["snapshot_id"]),
        snapshot_sha256=row["snapshot_sha256"],
        snapshot_created_at=_iso_to_dt(row["snapshot_created_at"]),
        extracted_quote_block=row["extracted_quote_block"],
        segment_offsets=_json_to_offsets(row["segment_offsets"]),
        raw_segment_word_count=row["raw_segment_word_count"],
        has_statistical_markers=bool(row["has_statistical_markers"]),
        claim_keyword_match_count=row["claim_keyword_match_count"],
        truncated=bool(row["truncated"]),
        extraction_prompt_version=row["extraction_prompt_version"],
        extraction_model_name=row["extraction_model_name"],
        extracted_at=_iso_to_dt(row["extracted_at"]),
        post_filter_version=row["post_filter_version"],
        post_filter_validated_at=_iso_to_dt(row["post_filter_validated_at"]),
    )


# ---------------------------------------------------------------------------
# Analyst decisions
# ---------------------------------------------------------------------------


def insert_analyst_decision(db_path: str, decision: ScoreDecision) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO analyst_decisions
               (run_id, quote_block_id, evidence_quality, claim_fit, ledger_score, placement,
                approved, rationale, analyst_prompt_version, analyst_model_name, scored_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(decision.run_id),
                str(decision.quote_block_id),
                decision.evidence_quality,
                decision.claim_fit,
                decision.ledger_score,
                decision.placement.value if decision.placement else None,
                int(decision.approved),
                decision.rationale,
                decision.analyst_prompt_version,
                decision.analyst_model_name,
                _dt_to_iso(decision.scored_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_analyst_decision(db_path: str, run_id: UUID, quote_block_id: UUID) -> ScoreDecision:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM analyst_decisions WHERE run_id = ? AND quote_block_id = ?",
            (str(run_id), str(quote_block_id)),
        ).fetchone()
        if row is None:
            raise KeyError(f"analyst decision for run={run_id} quote={quote_block_id} not found")
        return _row_to_score_decision(row)
    finally:
        conn.close()


def _row_to_score_decision(row: sqlite3.Row) -> ScoreDecision:
    return ScoreDecision(
        run_id=UUID(row["run_id"]),
        quote_block_id=UUID(row["quote_block_id"]),
        evidence_quality=row["evidence_quality"],
        claim_fit=row["claim_fit"],
        ledger_score=row["ledger_score"],
        placement=row["placement"],
        approved=bool(row["approved"]),
        rationale=row["rationale"],
        analyst_prompt_version=row["analyst_prompt_version"],
        analyst_model_name=row["analyst_model_name"],
        scored_at=_iso_to_dt(row["scored_at"]),
    )


# ---------------------------------------------------------------------------
# Statement drafts and review attempts
# ---------------------------------------------------------------------------


def insert_statement_draft(db_path: str, draft: StatementDraft) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO statement_drafts
               (statement_draft_id, run_id, quote_block_id, stance, draft_statement,
                claim_fit, analyst_prompt_version, analyst_model_name, drafted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(draft.statement_draft_id),
                str(draft.run_id),
                str(draft.quote_block_id),
                draft.stance.value,
                draft.draft_statement,
                draft.claim_fit,
                draft.analyst_prompt_version,
                draft.analyst_model_name,
                _dt_to_iso(draft.drafted_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_statement_draft(db_path: str, statement_draft_id: UUID) -> StatementDraft:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM statement_drafts WHERE statement_draft_id = ?",
            (str(statement_draft_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"statement draft {statement_draft_id} not found")
        return StatementDraft(
            run_id=UUID(row["run_id"]),
            statement_draft_id=UUID(row["statement_draft_id"]),
            quote_block_id=UUID(row["quote_block_id"]),
            stance=row["stance"],
            draft_statement=row["draft_statement"],
            claim_fit=row["claim_fit"],
            analyst_prompt_version=row["analyst_prompt_version"],
            analyst_model_name=row["analyst_model_name"],
            drafted_at=_iso_to_dt(row["drafted_at"]),
        )
    finally:
        conn.close()


def insert_statement_review(db_path: str, review: StatementReviewResult) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO statement_review_attempts
               (run_id, statement_draft_id, quote_block_id, approved,
                reviewer_approval_id, approved_factual_statement, failure_code,
                rationale, reviewer_prompt_version, reviewer_model_name, reviewed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(review.run_id),
                str(review.statement_draft_id),
                str(review.quote_block_id),
                int(review.approved),
                str(review.reviewer_approval_id) if review.reviewer_approval_id else None,
                review.approved_factual_statement,
                review.failure_code.value if review.failure_code else None,
                review.rationale,
                review.reviewer_prompt_version,
                review.reviewer_model_name,
                _dt_to_iso(review.reviewed_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_statement_review(
    db_path: str, run_id: UUID, statement_draft_id: UUID
) -> StatementReviewResult:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """SELECT * FROM statement_review_attempts
               WHERE run_id = ? AND statement_draft_id = ?""",
            (str(run_id), str(statement_draft_id)),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"statement review for run={run_id} draft={statement_draft_id} not found"
            )
        return _row_to_review_result(row)
    finally:
        conn.close()


def _row_to_review_result(row: sqlite3.Row) -> StatementReviewResult:
    return StatementReviewResult(
        run_id=UUID(row["run_id"]),
        statement_draft_id=UUID(row["statement_draft_id"]),
        quote_block_id=UUID(row["quote_block_id"]),
        approved=bool(row["approved"]),
        reviewer_approval_id=(
            UUID(row["reviewer_approval_id"]) if row["reviewer_approval_id"] else None
        ),
        approved_factual_statement=row["approved_factual_statement"],
        failure_code=row["failure_code"],
        rationale=row["rationale"],
        reviewer_prompt_version=row["reviewer_prompt_version"],
        reviewer_model_name=row["reviewer_model_name"],
        reviewed_at=_iso_to_dt(row["reviewed_at"]),
    )


# ---------------------------------------------------------------------------
# Ledger records (INSERT-ONLY — no update / delete)
# ---------------------------------------------------------------------------


def insert_ledger_record(db_path: str, record: LedgerRecord) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO ledger_records
               (ledger_claim_id, run_id, quote_block_id, stance,
                approved_factual_statement, approved_claim_text,
                evidence_quality, claim_fit, ledger_score, placement, entailment,
                source_url, retrieval_attempt_id, snapshot_id, snapshot_sha256,
                segment_offsets, analyst_prompt_version, analyst_model_name,
                analyst_completed_at, reviewer_prompt_version, reviewer_model_name,
                reviewed_at, reviewer_approval_id, ledger_validated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(record.ledger_claim_id),
                str(record.run_id),
                str(record.quote_block_id),
                record.stance.value,
                record.approved_factual_statement,
                record.approved_claim_text,
                record.evidence_quality,
                record.claim_fit,
                record.ledger_score,
                record.placement.value,
                record.entailment.value,
                record.source_url,
                str(record.retrieval_attempt_id),
                str(record.snapshot_id),
                record.snapshot_sha256,
                _offsets_to_json(record.segment_offsets),
                record.analyst_prompt_version,
                record.analyst_model_name,
                _dt_to_iso(record.analyst_completed_at),
                record.reviewer_prompt_version,
                record.reviewer_model_name,
                _dt_to_iso(record.reviewed_at),
                str(record.reviewer_approval_id),
                _dt_to_iso(record.ledger_validated_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_ledger_record(db_path: str, ledger_claim_id: UUID) -> LedgerRecord:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM ledger_records WHERE ledger_claim_id = ?",
            (str(ledger_claim_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"ledger record {ledger_claim_id} not found")
        return _row_to_ledger_record(row)
    finally:
        conn.close()


def _row_to_ledger_record(row: sqlite3.Row) -> LedgerRecord:
    return LedgerRecord(
        run_id=UUID(row["run_id"]),
        ledger_claim_id=UUID(row["ledger_claim_id"]),
        quote_block_id=UUID(row["quote_block_id"]),
        stance=row["stance"],
        approved_factual_statement=row["approved_factual_statement"],
        approved_claim_text=row["approved_claim_text"],
        evidence_quality=row["evidence_quality"],
        claim_fit=row["claim_fit"],
        ledger_score=row["ledger_score"],
        placement=row["placement"],
        entailment=row["entailment"],
        source_url=row["source_url"],
        retrieval_attempt_id=UUID(row["retrieval_attempt_id"]),
        snapshot_id=UUID(row["snapshot_id"]),
        snapshot_sha256=row["snapshot_sha256"],
        segment_offsets=_json_to_offsets(row["segment_offsets"]),
        analyst_prompt_version=row["analyst_prompt_version"],
        analyst_model_name=row["analyst_model_name"],
        analyst_completed_at=_iso_to_dt(row["analyst_completed_at"]),
        reviewer_prompt_version=row["reviewer_prompt_version"],
        reviewer_model_name=row["reviewer_model_name"],
        reviewed_at=_iso_to_dt(row["reviewed_at"]),
        reviewer_approval_id=UUID(row["reviewer_approval_id"]),
        ledger_validated_at=_iso_to_dt(row["ledger_validated_at"]),
    )


# ---------------------------------------------------------------------------
# Synthesis attempts
# ---------------------------------------------------------------------------


def insert_synthesis(db_path: str, synthesis: SynthesisOutput) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO synthesis_attempts
               (run_id, synthesizer_prompt_version, synthesizer_model_name,
                created_at, title, claim_definition)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(synthesis.run_id),
                synthesis.synthesizer_prompt_version,
                synthesis.synthesizer_model_name,
                _dt_to_iso(synthesis.created_at),
                synthesis.title,
                synthesis.claim_definition,
            ),
        )
        for sec_idx, section in enumerate(synthesis.sections):
            conn.execute(
                """INSERT INTO synthesis_sections
                   (run_id, section_type, heading, section_order)
                   VALUES (?, ?, ?, ?)""",
                (str(synthesis.run_id), section.section_type.value, section.heading, sec_idx),
            )
            for item_idx, item in enumerate(section.items):
                conn.execute(
                    """INSERT INTO synthesis_items
                       (run_id, section_order, item_order, connective_template_id,
                        ledger_claim_id, reviewer_approval_id, stance, placement,
                        entailment, approved_factual_statement)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(synthesis.run_id),
                        sec_idx,
                        item_idx,
                        item.connective_template_id,
                        str(item.ledger_claim_id),
                        str(item.reviewer_approval_id),
                        item.stance.value,
                        item.placement.value,
                        item.entailment.value,
                        item.approved_factual_statement,
                    ),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def read_synthesis(db_path: str, run_id: UUID) -> SynthesisOutput:
    conn = _connect(db_path)
    try:
        sa_row = conn.execute(
            "SELECT * FROM synthesis_attempts WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if sa_row is None:
            raise KeyError(f"synthesis for run {run_id} not found")

        sec_rows = conn.execute(
            "SELECT * FROM synthesis_sections WHERE run_id = ? ORDER BY section_order",
            (str(run_id),),
        ).fetchall()
        sections: list[SynthesisSection] = []
        for sec_row in sec_rows:
            item_rows = conn.execute(
                """SELECT * FROM synthesis_items
                   WHERE run_id = ? AND section_order = ? ORDER BY item_order""",
                (str(run_id), sec_row["section_order"]),
            ).fetchall()
            items = [
                SynthesisItem(
                    connective_template_id=r["connective_template_id"],
                    ledger_claim_id=UUID(r["ledger_claim_id"]),
                    reviewer_approval_id=UUID(r["reviewer_approval_id"]),
                    stance=r["stance"],
                    placement=r["placement"],
                    entailment=r["entailment"],
                    approved_factual_statement=r["approved_factual_statement"],
                )
                for r in item_rows
            ]
            sections.append(
                SynthesisSection(
                    section_type=sec_row["section_type"],
                    heading=sec_row["heading"],
                    items=items,
                )
            )

        return SynthesisOutput(
            run_id=UUID(sa_row["run_id"]),
            synthesizer_prompt_version=sa_row["synthesizer_prompt_version"],
            synthesizer_model_name=sa_row["synthesizer_model_name"],
            created_at=_iso_to_dt(sa_row["created_at"]),
            title=sa_row["title"],
            claim_definition=sa_row["claim_definition"],
            sections=sections,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Validation runs
# ---------------------------------------------------------------------------


def insert_validation(db_path: str, result: ValidationResult) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO validation_runs
               (run_id, valid, validator_config_version, validated_at, rendered_brief_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(result.run_id),
                int(result.valid),
                result.validator_config_version,
                _dt_to_iso(result.validated_at),
                result.rendered_brief_hash,
            ),
        )
        for err_idx, err in enumerate(result.errors):
            conn.execute(
                """INSERT INTO validation_errors
                   (run_id, error_order, code, location, message)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(result.run_id), err_idx, err.code.value, err.location, err.message),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def read_validation(db_path: str, run_id: UUID) -> ValidationResult:
    conn = _connect(db_path)
    try:
        vr_row = conn.execute(
            "SELECT * FROM validation_runs WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if vr_row is None:
            raise KeyError(f"validation for run {run_id} not found")

        err_rows = conn.execute(
            "SELECT * FROM validation_errors WHERE run_id = ? ORDER BY error_order",
            (str(run_id),),
        ).fetchall()
        errors = [
            ValidationError(code=r["code"], location=r["location"], message=r["message"])
            for r in err_rows
        ]

        return ValidationResult(
            run_id=UUID(vr_row["run_id"]),
            valid=bool(vr_row["valid"]),
            errors=errors,
            validator_config_version=vr_row["validator_config_version"],
            validated_at=_iso_to_dt(vr_row["validated_at"]),
            rendered_brief_hash=vr_row["rendered_brief_hash"],
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Model invocations
# ---------------------------------------------------------------------------


def insert_model_invocation(db_path: str, record: ModelInvocationRecord) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO model_invocations
               (invocation_id, run_id, stage, prompt_version, model_name,
                input_artifact_id, output_artifact_id, status, invoked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(record.invocation_id),
                str(record.run_id),
                record.stage.value,
                record.prompt_version,
                record.model_name,
                str(record.input_artifact_id),
                str(record.output_artifact_id) if record.output_artifact_id else None,
                record.status,
                _dt_to_iso(record.invoked_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_model_invocation(db_path: str, invocation_id: UUID) -> ModelInvocationRecord:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM model_invocations WHERE invocation_id = ?",
            (str(invocation_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"model invocation {invocation_id} not found")
        return ModelInvocationRecord(
            run_id=UUID(row["run_id"]),
            invocation_id=UUID(row["invocation_id"]),
            stage=row["stage"],
            prompt_version=row["prompt_version"],
            model_name=row["model_name"],
            input_artifact_id=UUID(row["input_artifact_id"]),
            output_artifact_id=(
                UUID(row["output_artifact_id"]) if row["output_artifact_id"] else None
            ),
            status=row["status"],
            invoked_at=_iso_to_dt(row["invoked_at"]),
        )
    finally:
        conn.close()
