"""Schema definitions, migration order and integrity checks; no artifact readers.

The caller supplies the connection factory. Initialization owns and closes that
connection; read-only inspection never invokes initialization or migrations.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from money import canonical_usd, parse_canonical_usd, parse_exact_usd

CURRENT_SCHEMA_VERSION = 13

RAW_CLAIM_SCHEMA_VERSION = 5

MVP68_SCHEMA_VERSION = 6

MVP69_SCHEMA_VERSION = 7

MVP10_SCHEMA_VERSION = 8

MVP11_SCHEMA_VERSION = 9

MLP4_SCHEMA_VERSION = 10

V2_PHASE1_SCHEMA_VERSION = 11

V2_PHASE3_SCHEMA_VERSION = 12

V2_PHASE10_SCHEMA_VERSION = 13

RAW_CLAIM_TRIGGER_NAME = "runs_raw_claim_immutable"

RAW_CLAIM_TRIGGER_ERROR = "runs.raw_claim is immutable"

IMMUTABLE_ARTIFACT_TRIGGERS = {
    "snapshots_immutable_update": ("snapshots", "UPDATE", "snapshots rows are immutable"),
    "snapshots_immutable_delete": ("snapshots", "DELETE", "snapshots rows are immutable"),
    "ledger_records_immutable_update": (
        "ledger_records",
        "UPDATE",
        "ledger_records rows are immutable",
    ),
    "ledger_records_immutable_delete": (
        "ledger_records",
        "DELETE",
        "ledger_records rows are immutable",
    ),
}

MIGRATION_DESCRIPTIONS = {
    1: "phase-2 initial sqlite schema",
    2: "phase-9 orchestration audit and checkpoint schema",
    3: "mvp-3a provider fingerprints and budget reservations",
    4: "same-run provenance protection triggers",
    5: "database-enforced immutable runs.raw_claim",
    6: "immutable snapshots and Ledger with exact decimal model costs",
    7: "snapshot acquisition and media-type provenance",
    8: "mvp-10 evidence portfolio and trail",
    9: "mvp-11 bounded research governor records",
    10: "mlp-4 provider-specific discovery query provenance",
    11: "researchassistant-v2 phase-1 artifact foundation",
    12: "researchassistant-v2 phase-3 initial planner and round-1 searches",
    13: "researchassistant-v2 phase-10 reviewer Ledger provenance",
}

_REQUIRED_TABLES = {
    "schema_migrations",
    "runs",
    "planner_outputs",
    "claim_definitions",
    "ambiguities",
    "search_queries",
    "retrieval_attempts",
    "snapshots",
    "provisional_extractions",
    "candidates",
    "analyst_decisions",
    "statement_drafts",
    "statement_review_attempts",
    "ledger_records",
    "synthesis_attempts",
    "synthesis_sections",
    "synthesis_items",
    "validation_runs",
    "validation_errors",
    "model_invocations",
    "orchestration_checkpoints",
    "orchestration_stage_artifacts",
    "provider_run_contracts",
    "model_route_attempts",
    "run_cancellations",
    "source_family_members",
    "evidence_trail_entries",
    "portfolio_items",
    "portfolio_coverage_assessments",
    "research_round_records",
    "research_governor_decisions",
    "research_terminal_results",
}

_REQUIRED_TRIGGERS = {
    "retrieval_attempt_same_run",
    "snapshot_same_run",
    "provisional_extraction_same_run",
    "candidate_same_run",
    "analyst_decision_same_run",
    "statement_draft_same_run",
    "statement_review_same_run",
    "ledger_record_same_run",
    "synthesis_item_same_run",
    RAW_CLAIM_TRIGGER_NAME,
    *IMMUTABLE_ARTIFACT_TRIGGERS,
}

_MVP11_TRIGGERS = {
    "research_round_records_immutable_update",
    "research_round_records_immutable_delete",
    "research_governor_decisions_immutable_update",
    "research_governor_decisions_immutable_delete",
    "research_terminal_results_immutable_update",
    "research_terminal_results_immutable_delete",
}

_V2_PHASE1_TABLES = {"v2_run_identities", "v2_artifacts"}

_V2_PHASE1_TRIGGERS = {
    "v2_run_identities_immutable_update",
    "v2_run_identities_immutable_delete",
    "v2_artifacts_immutable_update",
    "v2_artifacts_immutable_delete",
}

_V2_PHASE3_TABLES = {"v2_initial_planner_outputs", "v2_round_one_search_queries"}

_V2_PHASE3_TRIGGERS = {
    "v2_initial_planner_outputs_immutable_update",
    "v2_initial_planner_outputs_immutable_delete",
    "v2_round_one_search_queries_immutable_update",
    "v2_round_one_search_queries_immutable_delete",
}

_V2_PHASE10_TABLES = {"v2_ledger_admissions"}

_V2_PHASE10_TRIGGERS = {
    "v2_ledger_admissions_immutable_update",
    "v2_ledger_admissions_immutable_delete",
}

_REQUIRED_INDEXES = {
    "provisional_extractions_run_snapshot_stance",
    "model_route_attempts_run_operation",
}


def initialize_database(db_path: str, *, connect: Callable[[str], sqlite3.Connection]) -> None:
    """Create every table if it does not already exist."""
    conn = connect(db_path)
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

            INSERT OR IGNORE INTO schema_migrations
                (version, description, applied_at)
                VALUES (
                    4,
                    'same-run provenance protection triggers',
                    '2026-08-01T00:00:00+00:00'
                );

            INSERT OR IGNORE INTO schema_migrations
                (version, description, applied_at)
                VALUES (
                    2,
                    'phase-9 orchestration audit and checkpoint schema',
                    '2026-07-17T00:00:00+00:00'
                );

            INSERT OR IGNORE INTO schema_migrations
                (version, description, applied_at)
                VALUES (
                    3,
                    'mvp-3a provider fingerprints and budget reservations',
                    '2026-07-24T00:00:00+00:00'
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
                provider            TEXT NOT NULL DEFAULT 'exa',
                intent              TEXT NOT NULL DEFAULT 'broad_web',
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

            CREATE UNIQUE INDEX IF NOT EXISTS
                provisional_extractions_run_snapshot_stance
                ON provisional_extractions(run_id, snapshot_id, stance);

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

            -- Phase 9 orchestration ---------------------------------------
            CREATE TABLE IF NOT EXISTS orchestration_checkpoints (
                run_id          TEXT NOT NULL REFERENCES runs(run_id),
                stage_key       TEXT NOT NULL,
                status          TEXT NOT NULL,
                failure_reason  TEXT,
                updated_at      TEXT NOT NULL,
                PRIMARY KEY (run_id, stage_key)
            );

            CREATE TABLE IF NOT EXISTS orchestration_stage_artifacts (
                run_id          TEXT NOT NULL REFERENCES runs(run_id),
                artifact_key    TEXT NOT NULL,
                artifact_type   TEXT NOT NULL,
                payload_json    TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                PRIMARY KEY (run_id, artifact_key)
            );

            CREATE TABLE IF NOT EXISTS provider_run_contracts (
                run_id                  TEXT PRIMARY KEY REFERENCES runs(run_id),
                fingerprint_sha256      TEXT NOT NULL,
                provider_identity       TEXT NOT NULL,
                adapter_identity        TEXT NOT NULL,
                model_identity          TEXT NOT NULL,
                prompt_identity         TEXT NOT NULL,
                schema_identity         TEXT NOT NULL,
                normalization_identity  TEXT NOT NULL,
                policy_identity         TEXT NOT NULL,
                repository_revision     TEXT NOT NULL,
                payload_json            TEXT NOT NULL,
                created_at              TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS model_route_attempts (
                attempt_id              TEXT PRIMARY KEY,
                run_id                  TEXT NOT NULL REFERENCES runs(run_id),
                operation_id            TEXT NOT NULL,
                stage                   TEXT NOT NULL,
                output_type             TEXT NOT NULL,
                model_alias             TEXT NOT NULL,
                pinned_model_snapshot   TEXT,
                route_index             INTEGER NOT NULL,
                attempt_number          INTEGER NOT NULL,
                input_artifact_ids      TEXT NOT NULL,
                status                  TEXT NOT NULL,
                retry_reason            TEXT,
                escalation_reason       TEXT,
                failure_code            TEXT,
                failure_reason          TEXT,
                started_at              TEXT NOT NULL,
                ended_at                TEXT,
                latency_ms              REAL,
                reserved_tokens         INTEGER,
                reserved_cost_usd       REAL,
                input_tokens            INTEGER,
                output_tokens           INTEGER,
                total_tokens            INTEGER,
                cost_usd                REAL,
                output_json             TEXT,
                UNIQUE (
                    run_id,
                    operation_id,
                    route_index,
                    attempt_number
                )
            );

            CREATE INDEX IF NOT EXISTS model_route_attempts_run_operation
                ON model_route_attempts(run_id, operation_id, route_index, attempt_number);

            CREATE TABLE IF NOT EXISTS run_cancellations (
                run_id          TEXT PRIMARY KEY REFERENCES runs(run_id),
                requested_at    TEXT NOT NULL,
                reason          TEXT NOT NULL
            );

            -- Same-run provenance guards ------------------------------------
            CREATE TRIGGER IF NOT EXISTS retrieval_attempt_same_run
            BEFORE INSERT ON retrieval_attempts
            WHEN (SELECT run_id FROM search_queries WHERE query_id = NEW.query_id) != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'retrieval query belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS snapshot_same_run
            BEFORE INSERT ON snapshots
            WHEN (SELECT run_id FROM retrieval_attempts
                  WHERE retrieval_attempt_id = NEW.retrieval_attempt_id) != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'snapshot retrieval belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS provisional_extraction_same_run
            BEFORE INSERT ON provisional_extractions
            WHEN (SELECT run_id FROM retrieval_attempts
                  WHERE retrieval_attempt_id = NEW.retrieval_attempt_id) != NEW.run_id
              OR (SELECT run_id FROM search_queries WHERE query_id = NEW.query_id) != NEW.run_id
              OR (SELECT run_id FROM snapshots WHERE snapshot_id = NEW.snapshot_id) != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'provisional provenance belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS candidate_same_run
            BEFORE INSERT ON candidates
            WHEN (SELECT run_id FROM retrieval_attempts
                  WHERE retrieval_attempt_id = NEW.retrieval_attempt_id) != NEW.run_id
              OR (SELECT run_id FROM search_queries WHERE query_id = NEW.query_id) != NEW.run_id
              OR (SELECT run_id FROM snapshots WHERE snapshot_id = NEW.snapshot_id) != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'candidate provenance belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS analyst_decision_same_run
            BEFORE INSERT ON analyst_decisions
            WHEN (SELECT run_id FROM candidates WHERE quote_block_id = NEW.quote_block_id)
                 != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'analyst candidate belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS statement_draft_same_run
            BEFORE INSERT ON statement_drafts
            WHEN (SELECT run_id FROM candidates WHERE quote_block_id = NEW.quote_block_id)
                 != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'draft candidate belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS statement_review_same_run
            BEFORE INSERT ON statement_review_attempts
            WHEN (SELECT run_id FROM statement_drafts
                  WHERE statement_draft_id = NEW.statement_draft_id) != NEW.run_id
              OR (SELECT run_id FROM candidates WHERE quote_block_id = NEW.quote_block_id)
                 != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'review provenance belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS ledger_record_same_run
            BEFORE INSERT ON ledger_records
            WHEN (SELECT run_id FROM candidates WHERE quote_block_id = NEW.quote_block_id)
                 != NEW.run_id
              OR (SELECT run_id FROM retrieval_attempts
                  WHERE retrieval_attempt_id = NEW.retrieval_attempt_id) != NEW.run_id
              OR (SELECT run_id FROM snapshots WHERE snapshot_id = NEW.snapshot_id) != NEW.run_id
              OR (SELECT run_id FROM statement_review_attempts
                  WHERE reviewer_approval_id = NEW.reviewer_approval_id) != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'Ledger provenance belongs to another run'); END;

            CREATE TRIGGER IF NOT EXISTS synthesis_item_same_run
            BEFORE INSERT ON synthesis_items
            WHEN (SELECT run_id FROM ledger_records
                  WHERE ledger_claim_id = NEW.ledger_claim_id) != NEW.run_id
            BEGIN SELECT RAISE(ABORT, 'synthesis Ledger record belongs to another run'); END;
            """
        )
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(model_route_attempts)").fetchall()
        }
        if "reserved_tokens" not in columns:
            conn.execute("ALTER TABLE model_route_attempts ADD COLUMN reserved_tokens INTEGER")
        if "reserved_cost_usd" not in columns:
            conn.execute("ALTER TABLE model_route_attempts ADD COLUMN reserved_cost_usd REAL")
        conn.execute(
            "UPDATE schema_migrations SET description = ? WHERE version = 4",
            (MIGRATION_DESCRIPTIONS[4],),
        )
        conn.commit()
        _apply_raw_claim_immutability_migration(conn)
        _apply_mvp68_integrity_migration(conn)
        _apply_mvp69_provenance_migration(conn)
        _apply_mvp10_evidence_portfolio_migration(conn)
        _apply_mvp11_research_governor_migration(conn)
        _apply_mlp4_discovery_query_migration(conn)
        _apply_v2_phase1_artifact_migration(conn)
        _apply_v2_phase3_initial_planner_migration(conn)
        _apply_v2_phase10_reviewer_ledger_migration(conn)
    finally:
        conn.close()


def _raw_claim_trigger_sql() -> str:
    return f"""CREATE TRIGGER {RAW_CLAIM_TRIGGER_NAME}
        BEFORE UPDATE OF raw_claim ON runs
        WHEN NEW.raw_claim IS NOT OLD.raw_claim
        BEGIN
            SELECT RAISE(ABORT, '{RAW_CLAIM_TRIGGER_ERROR}');
        END"""


def _is_expected_raw_claim_trigger(sql: str | None) -> bool:
    if sql is None:
        return False
    normalized = " ".join(sql.lower().split())
    return all(
        fragment in normalized
        for fragment in (
            f"create trigger {RAW_CLAIM_TRIGGER_NAME}",
            "before update of raw_claim on runs",
            "when new.raw_claim is not old.raw_claim",
            f"raise(abort, '{RAW_CLAIM_TRIGGER_ERROR}')",
        )
    )


def _apply_raw_claim_immutability_migration(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (RAW_CLAIM_SCHEMA_VERSION,),
    ).fetchone()
    trigger = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (RAW_CLAIM_TRIGGER_NAME,),
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[RAW_CLAIM_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 5 description is inconsistent")
        if trigger is None or not _is_expected_raw_claim_trigger(trigger["sql"]):
            raise sqlite3.DatabaseError("migration 5 trigger is missing or inconsistent")
        return

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(_raw_claim_trigger_sql())
        installed = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (RAW_CLAIM_TRIGGER_NAME,),
        ).fetchone()
        if installed is None or not _is_expected_raw_claim_trigger(installed["sql"]):
            raise sqlite3.DatabaseError("migration 5 trigger installation verification failed")
        conn.execute(
            """INSERT INTO schema_migrations (version, description, applied_at)
               VALUES (?, ?, ?)""",
            (
                RAW_CLAIM_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[RAW_CLAIM_SCHEMA_VERSION],
                "2026-08-09T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _immutable_trigger_sql(
    name: str,
    table: str,
    operation: str,
    error: str,
) -> str:
    return f"""CREATE TRIGGER {name}
        BEFORE {operation} ON {table}
        BEGIN
            SELECT RAISE(ABORT, '{error}');
        END"""


def _is_expected_immutable_trigger(
    sql: str | None,
    name: str,
    table: str,
    operation: str,
    error: str,
) -> bool:
    if sql is None:
        return False
    normalized = " ".join(sql.lower().split())
    return all(
        fragment in normalized
        for fragment in (
            f"create trigger {name}",
            f"before {operation.lower()} on {table}",
            f"raise(abort, '{error}')",
        )
    )


def _verify_mvp68_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(model_route_attempts)").fetchall()
    }
    if not {"reserved_cost_usd_exact", "cost_usd_exact"} <= columns:
        raise sqlite3.DatabaseError("migration 6 exact-cost columns are missing")
    for name, (table, operation, error) in IMMUTABLE_ARTIFACT_TRIGGERS.items():
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?", (name,)
        ).fetchone()
        if row is None or not _is_expected_immutable_trigger(
            row["sql"], name, table, operation, error
        ):
            raise sqlite3.DatabaseError(f"migration 6 trigger {name} is missing or inconsistent")


def _apply_mvp68_integrity_migration(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (MVP68_SCHEMA_VERSION,),
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[MVP68_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 6 description is inconsistent")
        _verify_mvp68_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        columns = {
            item["name"]
            for item in conn.execute("PRAGMA table_info(model_route_attempts)").fetchall()
        }
        if "reserved_cost_usd_exact" not in columns:
            conn.execute("ALTER TABLE model_route_attempts ADD COLUMN reserved_cost_usd_exact TEXT")
        if "cost_usd_exact" not in columns:
            conn.execute("ALTER TABLE model_route_attempts ADD COLUMN cost_usd_exact TEXT")
        rows = conn.execute(
            """SELECT attempt_id, reserved_cost_usd, cost_usd,
                      reserved_cost_usd_exact, cost_usd_exact
               FROM model_route_attempts"""
        ).fetchall()
        for existing in rows:
            reserved_exact = existing["reserved_cost_usd_exact"]
            cost_exact = existing["cost_usd_exact"]
            if reserved_exact is not None:
                parse_canonical_usd(reserved_exact)
            elif existing["reserved_cost_usd"] is not None:
                reserved_exact = canonical_usd(parse_exact_usd(existing["reserved_cost_usd"]))
            if cost_exact is not None:
                parse_canonical_usd(cost_exact)
            elif existing["cost_usd"] is not None:
                cost_exact = canonical_usd(parse_exact_usd(existing["cost_usd"]))
            conn.execute(
                """UPDATE model_route_attempts
                   SET reserved_cost_usd_exact = ?, cost_usd_exact = ?
                   WHERE attempt_id = ?""",
                (reserved_exact, cost_exact, existing["attempt_id"]),
            )
        for name, (table, operation, error) in IMMUTABLE_ARTIFACT_TRIGGERS.items():
            conn.execute(_immutable_trigger_sql(name, table, operation, error))
        _verify_mvp68_schema(conn)
        conn.execute(
            """INSERT INTO schema_migrations (version, description, applied_at)
               VALUES (?, ?, ?)""",
            (
                MVP68_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[MVP68_SCHEMA_VERSION],
                "2026-08-10T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


_SNAPSHOT_PROVENANCE_COLUMNS = {
    "original_url": "TEXT",
    "canonical_url": "TEXT",
    "normalization_version": "TEXT",
    "acquisition_version": "TEXT",
    "provider_name": "TEXT",
    "provider_version": "TEXT",
    "media_type_provenance_json": "TEXT",
}


def _verify_mvp69_schema(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(snapshots)").fetchall()}
    missing = sorted(set(_SNAPSHOT_PROVENANCE_COLUMNS) - columns)
    if missing:
        raise sqlite3.DatabaseError(
            f"migration 7 snapshot provenance columns are missing: {', '.join(missing)}"
        )


def _apply_mvp69_provenance_migration(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (MVP69_SCHEMA_VERSION,),
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[MVP69_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 7 description is inconsistent")
        _verify_mvp69_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        columns = {item["name"] for item in conn.execute("PRAGMA table_info(snapshots)").fetchall()}
        for name, declaration in _SNAPSHOT_PROVENANCE_COLUMNS.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE snapshots ADD COLUMN {name} {declaration}")
        _verify_mvp69_schema(conn)
        conn.execute(
            """INSERT INTO schema_migrations (version, description, applied_at)
               VALUES (?, ?, ?)""",
            (
                MVP69_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[MVP69_SCHEMA_VERSION],
                "2026-08-10T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


_MVP10_TABLES = {
    "source_family_members",
    "evidence_trail_entries",
    "portfolio_items",
    "portfolio_coverage_assessments",
}

_MVP11_TABLES = {
    "research_round_records",
    "research_governor_decisions",
    "research_terminal_results",
}


def _verify_mvp10_schema(conn: sqlite3.Connection) -> None:
    present = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    missing = sorted(_MVP10_TABLES - present)
    if missing:
        raise sqlite3.DatabaseError(
            f"migration 8 portfolio tables are missing: {', '.join(missing)}"
        )


def _apply_mvp10_evidence_portfolio_migration(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?", (MVP10_SCHEMA_VERSION,)
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[MVP10_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 8 description is inconsistent")
        _verify_mvp10_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        statements = (
            """CREATE TABLE IF NOT EXISTS source_family_members (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                retrieval_attempt_id TEXT NOT NULL
                    REFERENCES retrieval_attempts(retrieval_attempt_id),
                source_family_id TEXT NOT NULL,
                family_key TEXT NOT NULL,
                identification_basis TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, retrieval_attempt_id)
            )""",
            """CREATE TABLE IF NOT EXISTS evidence_trail_entries (
                trail_entry_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                retrieval_attempt_id TEXT NOT NULL
                    REFERENCES retrieval_attempts(retrieval_attempt_id),
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (run_id, retrieval_attempt_id)
            )""",
            """CREATE TABLE IF NOT EXISTS portfolio_items (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                ledger_claim_id TEXT NOT NULL REFERENCES ledger_records(ledger_claim_id),
                source_family_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, ledger_claim_id)
            )""",
            """CREATE TABLE IF NOT EXISTS portfolio_coverage_assessments (
                run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                payload_json TEXT NOT NULL,
                assessed_at TEXT NOT NULL
            )""",
        )
        for statement in statements:
            conn.execute(statement)
        _verify_mvp10_schema(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (
                MVP10_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[MVP10_SCHEMA_VERSION],
                "2026-08-11T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _verify_mvp11_schema(conn: sqlite3.Connection) -> None:
    """Verify the bounded append-only Research Governor tables and constraints."""
    present = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    missing = sorted(_MVP11_TABLES - present)
    if missing:
        raise sqlite3.DatabaseError(
            f"migration 9 research governor tables are missing: {', '.join(missing)}"
        )
    sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'research_round_records'"
    ).fetchone()
    normalized = " ".join((sql_row["sql"] if sql_row is not None else "").lower().split())
    if "check (research_round between 1 and 3)" not in normalized:
        raise sqlite3.DatabaseError("migration 9 research round bound is missing or inconsistent")


def _apply_mvp11_research_governor_migration(conn: sqlite3.Connection) -> None:
    """Install idempotent append-only MVP-11 Governor persistence transactionally."""
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?", (MVP11_SCHEMA_VERSION,)
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[MVP11_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 9 description is inconsistent")
        _verify_mvp11_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        statements = (
            """CREATE TABLE IF NOT EXISTS research_round_records (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                research_round INTEGER NOT NULL CHECK (research_round BETWEEN 1 AND 3),
                payload_json TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (run_id, research_round)
            )""",
            """CREATE TABLE IF NOT EXISTS research_governor_decisions (
                run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                payload_json TEXT NOT NULL,
                decided_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS research_terminal_results (
                run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                payload_json TEXT NOT NULL,
                finalized_at TEXT NOT NULL
            )""",
            """CREATE TRIGGER IF NOT EXISTS research_round_records_immutable_update
                BEFORE UPDATE ON research_round_records
                BEGIN SELECT RAISE(ABORT, 'research round records are append-only'); END""",
            """CREATE TRIGGER IF NOT EXISTS research_round_records_immutable_delete
                BEFORE DELETE ON research_round_records
                BEGIN SELECT RAISE(ABORT, 'research round records are append-only'); END""",
            """CREATE TRIGGER IF NOT EXISTS research_governor_decisions_immutable_update
                BEFORE UPDATE ON research_governor_decisions
                BEGIN SELECT RAISE(ABORT, 'research governor decisions are append-only'); END""",
            """CREATE TRIGGER IF NOT EXISTS research_governor_decisions_immutable_delete
                BEFORE DELETE ON research_governor_decisions
                BEGIN SELECT RAISE(ABORT, 'research governor decisions are append-only'); END""",
            """CREATE TRIGGER IF NOT EXISTS research_terminal_results_immutable_update
                BEFORE UPDATE ON research_terminal_results
                BEGIN SELECT RAISE(ABORT, 'research terminal results are append-only'); END""",
            """CREATE TRIGGER IF NOT EXISTS research_terminal_results_immutable_delete
                BEFORE DELETE ON research_terminal_results
                BEGIN SELECT RAISE(ABORT, 'research terminal results are append-only'); END""",
        )
        for statement in statements:
            conn.execute(statement)
        _verify_mvp11_schema(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (
                MVP11_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[MVP11_SCHEMA_VERSION],
                "2026-08-11T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _verify_mlp4_discovery_query_schema(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(search_queries)").fetchall()}
    missing = sorted({"provider", "intent"} - columns)
    if missing:
        raise sqlite3.DatabaseError(
            f"migration 10 search query columns are missing: {', '.join(missing)}"
        )


def _apply_mlp4_discovery_query_migration(conn: sqlite3.Connection) -> None:
    """Persist provider and intent without rewriting legacy Planner artifacts."""
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (MLP4_SCHEMA_VERSION,),
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[MLP4_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 10 description is inconsistent")
        _verify_mlp4_discovery_query_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        columns = {
            item["name"] for item in conn.execute("PRAGMA table_info(search_queries)").fetchall()
        }
        if "provider" not in columns:
            conn.execute(
                "ALTER TABLE search_queries ADD COLUMN provider TEXT NOT NULL DEFAULT 'exa'"
            )
        if "intent" not in columns:
            conn.execute(
                "ALTER TABLE search_queries ADD COLUMN intent TEXT NOT NULL DEFAULT 'broad_web'"
            )
        _verify_mlp4_discovery_query_schema(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (
                MLP4_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[MLP4_SCHEMA_VERSION],
                "2026-08-15T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _verify_v2_phase1_artifact_schema(conn: sqlite3.Connection) -> None:
    """Verify the additive, immutable v2 artifact persistence boundary."""
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    missing = sorted(_V2_PHASE1_TABLES - tables)
    if missing:
        raise sqlite3.DatabaseError(f"migration 11 v2 tables are missing: {', '.join(missing)}")
    triggers = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    }
    missing_triggers = sorted(_V2_PHASE1_TRIGGERS - triggers)
    if missing_triggers:
        raise sqlite3.DatabaseError(
            f"migration 11 v2 immutable triggers are missing: {', '.join(missing_triggers)}"
        )


def _apply_v2_phase1_artifact_migration(conn: sqlite3.Connection) -> None:
    """Add v2 identities and append-only artifacts without touching historical rows."""
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (V2_PHASE1_SCHEMA_VERSION,),
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[V2_PHASE1_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 11 description is inconsistent")
        _verify_v2_phase1_artifact_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        statements = (
            """CREATE TABLE IF NOT EXISTS v2_run_identities (
                run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                pipeline_identity TEXT NOT NULL,
                policy_identity TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS v2_artifacts (
                run_id TEXT NOT NULL REFERENCES v2_run_identities(run_id),
                artifact_key TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, artifact_key)
            )""",
            """CREATE TRIGGER IF NOT EXISTS v2_run_identities_immutable_update
                BEFORE UPDATE ON v2_run_identities
                BEGIN SELECT RAISE(ABORT, 'v2 run identities are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS v2_run_identities_immutable_delete
                BEFORE DELETE ON v2_run_identities
                BEGIN SELECT RAISE(ABORT, 'v2 run identities are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS v2_artifacts_immutable_update
                BEFORE UPDATE ON v2_artifacts
                BEGIN SELECT RAISE(ABORT, 'v2 artifacts are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS v2_artifacts_immutable_delete
                BEFORE DELETE ON v2_artifacts
                BEGIN SELECT RAISE(ABORT, 'v2 artifacts are immutable'); END""",
        )
        for statement in statements:
            conn.execute(statement)
        _verify_v2_phase1_artifact_schema(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (
                V2_PHASE1_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[V2_PHASE1_SCHEMA_VERSION],
                "2026-08-20T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _verify_v2_phase3_initial_planner_schema(conn: sqlite3.Connection) -> None:
    """Verify v2 Round-1 planner persistence without altering historical artifacts."""
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    missing = sorted(_V2_PHASE3_TABLES - tables)
    if missing:
        raise sqlite3.DatabaseError(
            f"migration 12 v2 planner tables are missing: {', '.join(missing)}"
        )
    triggers = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    }
    missing_triggers = sorted(_V2_PHASE3_TRIGGERS - triggers)
    if missing_triggers:
        raise sqlite3.DatabaseError(
            f"migration 12 v2 planner triggers are missing: {', '.join(missing_triggers)}"
        )


def _apply_v2_phase3_initial_planner_migration(conn: sqlite3.Connection) -> None:
    """Persist only fresh-v2 initial plans and their Round-1 queries append-only."""
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (V2_PHASE3_SCHEMA_VERSION,),
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[V2_PHASE3_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 12 description is inconsistent")
        _verify_v2_phase3_initial_planner_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        statements = (
            """CREATE TABLE IF NOT EXISTS v2_initial_planner_outputs (
                run_id TEXT PRIMARY KEY REFERENCES v2_run_identities(run_id),
                raw_claim TEXT NOT NULL,
                directions_json TEXT NOT NULL,
                discovery_providers_json TEXT NOT NULL,
                policy_identity TEXT NOT NULL,
                scope_interpretations_json TEXT NOT NULL,
                planner_prompt_version TEXT NOT NULL,
                planner_model_name TEXT NOT NULL,
                planned_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS v2_round_one_search_queries (
                query_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES v2_initial_planner_outputs(run_id),
                direction TEXT NOT NULL,
                provider TEXT NOT NULL,
                round_number INTEGER NOT NULL CHECK (round_number = 1),
                strategy TEXT NOT NULL,
                query_text TEXT NOT NULL,
                policy_identity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (run_id, direction, provider, round_number, strategy)
            )""",
            """CREATE TRIGGER IF NOT EXISTS v2_initial_planner_outputs_immutable_update
                BEFORE UPDATE ON v2_initial_planner_outputs
                BEGIN SELECT RAISE(ABORT, 'v2 initial planner outputs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS v2_initial_planner_outputs_immutable_delete
                BEFORE DELETE ON v2_initial_planner_outputs
                BEGIN SELECT RAISE(ABORT, 'v2 initial planner outputs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS v2_round_one_search_queries_immutable_update
                BEFORE UPDATE ON v2_round_one_search_queries
                BEGIN SELECT RAISE(ABORT, 'v2 Round-1 search queries are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS v2_round_one_search_queries_immutable_delete
                BEFORE DELETE ON v2_round_one_search_queries
                BEGIN SELECT RAISE(ABORT, 'v2 Round-1 search queries are immutable'); END""",
        )
        for statement in statements:
            conn.execute(statement)
        _verify_v2_phase3_initial_planner_schema(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (
                V2_PHASE3_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[V2_PHASE3_SCHEMA_VERSION],
                "2026-08-20T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _verify_v2_phase10_reviewer_ledger_schema(conn: sqlite3.Connection) -> None:
    """Verify the isolated immutable v2 Ledger-provenance boundary."""
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    triggers = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    }
    missing = sorted((_V2_PHASE10_TABLES - tables) | (_V2_PHASE10_TRIGGERS - triggers))
    if missing:
        raise sqlite3.DatabaseError(
            f"migration 13 v2 Reviewer/Ledger schema is missing: {', '.join(missing)}"
        )


def _apply_v2_phase10_reviewer_ledger_migration(conn: sqlite3.Connection) -> None:
    """Add append-only v2 Ledger provenance without altering historical Ledger rows."""
    row = conn.execute(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (V2_PHASE10_SCHEMA_VERSION,),
    ).fetchone()
    if row is not None:
        if row["description"] != MIGRATION_DESCRIPTIONS[V2_PHASE10_SCHEMA_VERSION]:
            raise sqlite3.DatabaseError("migration 13 description is inconsistent")
        _verify_v2_phase10_reviewer_ledger_schema(conn)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        statements = (
            """CREATE TABLE IF NOT EXISTS v2_ledger_admissions (
                ledger_claim_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES v2_run_identities(run_id),
                source_id TEXT NOT NULL,
                research_direction TEXT NOT NULL,
                discovery_round INTEGER NOT NULL CHECK (discovery_round BETWEEN 1 AND 3),
                source_family_id TEXT NOT NULL,
                recommended INTEGER NOT NULL CHECK (recommended IN (0, 1)),
                relevant_gap_ids_json TEXT NOT NULL,
                ledger_record_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                admitted_at TEXT NOT NULL,
                UNIQUE (run_id, source_id)
            )""",
            """CREATE TRIGGER IF NOT EXISTS v2_ledger_admissions_immutable_update
                BEFORE UPDATE ON v2_ledger_admissions
                BEGIN SELECT RAISE(ABORT, 'v2 Ledger admission rows are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS v2_ledger_admissions_immutable_delete
                BEFORE DELETE ON v2_ledger_admissions
                BEGIN SELECT RAISE(ABORT, 'v2 Ledger admission rows are immutable'); END""",
        )
        for statement in statements:
            conn.execute(statement)
        _verify_v2_phase10_reviewer_ledger_schema(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (
                V2_PHASE10_SCHEMA_VERSION,
                MIGRATION_DESCRIPTIONS[V2_PHASE10_SCHEMA_VERSION],
                "2026-08-20T00:00:00+00:00",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
