"""Typed persistence facade and validated connection/session ownership."""

from __future__ import annotations

import json as json
import math as math
import sqlite3 as sqlite3
from collections.abc import Iterator as Iterator
from collections.abc import Sequence as Sequence
from contextlib import closing as closing
from contextlib import contextmanager as contextmanager
from datetime import UTC as UTC
from datetime import datetime as datetime
from decimal import Decimal as Decimal
from enum import StrEnum as StrEnum
from pathlib import Path as Path
from typing import TYPE_CHECKING as TYPE_CHECKING
from urllib.parse import quote as quote
from uuid import UUID as UUID

if TYPE_CHECKING:
    from researchassistant.storage.database_recovery import BackupPolicy

from researchassistant.common.money import add_usd as add_usd
from researchassistant.common.money import canonical_usd as canonical_usd
from researchassistant.common.money import parse_canonical_usd as parse_canonical_usd
from researchassistant.common.money import parse_exact_usd as parse_exact_usd
from researchassistant.contracts.models import BRIEF_TITLE as BRIEF_TITLE
from researchassistant.contracts.models import CLAIM_LABEL as CLAIM_LABEL
from researchassistant.contracts.models import RELEASE_SECTION_HEADINGS as RELEASE_SECTION_HEADINGS
from researchassistant.contracts.models import V2_PIPELINE_IDENTITY as V2_PIPELINE_IDENTITY
from researchassistant.contracts.models import V2_POLICY_IDENTITY as V2_POLICY_IDENTITY
from researchassistant.contracts.models import AmbiguityRecord as AmbiguityRecord
from researchassistant.contracts.models import CandidateQuoteBlock as CandidateQuoteBlock
from researchassistant.contracts.models import ClaimDefinition as ClaimDefinition
from researchassistant.contracts.models import EvidenceTrailEntry as EvidenceTrailEntry
from researchassistant.contracts.models import LedgerRecord as LedgerRecord
from researchassistant.contracts.models import MediaTypeProvenance as MediaTypeProvenance
from researchassistant.contracts.models import ModelAttemptStatus as ModelAttemptStatus
from researchassistant.contracts.models import ModelInvocationRecord as ModelInvocationRecord
from researchassistant.contracts.models import ModelRouteAttempt as ModelRouteAttempt
from researchassistant.contracts.models import ModelUsageMetadata as ModelUsageMetadata
from researchassistant.contracts.models import OrchestrationCheckpoint as OrchestrationCheckpoint
from researchassistant.contracts.models import PersistedStageArtifact as PersistedStageArtifact
from researchassistant.contracts.models import PlannerOutput as PlannerOutput
from researchassistant.contracts.models import (
    PortfolioCoverageAssessment as PortfolioCoverageAssessment,
)
from researchassistant.contracts.models import PortfolioItem as PortfolioItem
from researchassistant.contracts.models import ProviderRunContract as ProviderRunContract
from researchassistant.contracts.models import ProvisionalCandidate as ProvisionalCandidate
from researchassistant.contracts.models import ResearchGovernorDecision as ResearchGovernorDecision
from researchassistant.contracts.models import ResearchRoundRecord as ResearchRoundRecord
from researchassistant.contracts.models import ResearchRoundStatus as ResearchRoundStatus
from researchassistant.contracts.models import ResearchTerminalResult as ResearchTerminalResult
from researchassistant.contracts.models import RetrievalRecord as RetrievalRecord
from researchassistant.contracts.models import RunCancellationRequest as RunCancellationRequest
from researchassistant.contracts.models import RunManifest as RunManifest
from researchassistant.contracts.models import RunStatus as RunStatus
from researchassistant.contracts.models import ScoreDecision as ScoreDecision
from researchassistant.contracts.models import SearchQuery as SearchQuery
from researchassistant.contracts.models import SegmentOffset as SegmentOffset
from researchassistant.contracts.models import SourceSnapshot as SourceSnapshot
from researchassistant.contracts.models import Stage as Stage
from researchassistant.contracts.models import StatementDraft as StatementDraft
from researchassistant.contracts.models import StatementReviewResult as StatementReviewResult
from researchassistant.contracts.models import StrictModel as StrictModel
from researchassistant.contracts.models import SynthesisItem as SynthesisItem
from researchassistant.contracts.models import SynthesisOutput as SynthesisOutput
from researchassistant.contracts.models import SynthesisSection as SynthesisSection
from researchassistant.contracts.models import (
    V2EvidenceAdmissionRecord as V2EvidenceAdmissionRecord,
)
from researchassistant.contracts.models import (
    V2EvidenceAdmissionSourceResult as V2EvidenceAdmissionSourceResult,
)
from researchassistant.contracts.models import V2InitialPlannerOutput as V2InitialPlannerOutput
from researchassistant.contracts.models import V2LedgerProvenance as V2LedgerProvenance
from researchassistant.contracts.models import V2PersistedArtifact as V2PersistedArtifact
from researchassistant.contracts.models import V2PipelineIdentity as V2PipelineIdentity
from researchassistant.contracts.models import (
    V2ReviewerLedgerSourceResult as V2ReviewerLedgerSourceResult,
)
from researchassistant.contracts.models import ValidationError as ValidationError
from researchassistant.contracts.models import ValidationResult as ValidationResult
from researchassistant.contracts.models import (
    canonical_v2_artifact_json as canonical_v2_artifact_json,
)
from researchassistant.contracts.models import v2_artifact_fingerprint as v2_artifact_fingerprint
from researchassistant.contracts.models import v2_payload_fingerprint as v2_payload_fingerprint
from researchassistant.contracts.provider_contract import (
    parse_provider_contract_payload as parse_provider_contract_payload,
)
from researchassistant.storage.checkpoint_store import (
    _row_to_provider_run_contract as _row_to_provider_run_contract,
)
from researchassistant.storage.checkpoint_store import (
    _row_to_stage_artifact as _row_to_stage_artifact,
)
from researchassistant.storage.checkpoint_store import (
    insert_provider_run_contract as _insert_provider_run_contract_owned,
)
from researchassistant.storage.checkpoint_store import (
    insert_stage_artifact as _insert_stage_artifact_owned,
)
from researchassistant.storage.checkpoint_store import (
    read_orchestration_checkpoint as _read_orchestration_checkpoint_owned,
)
from researchassistant.storage.checkpoint_store import (
    read_orchestration_checkpoints as _read_orchestration_checkpoints_owned,
)
from researchassistant.storage.checkpoint_store import (
    read_provider_run_contract as _read_provider_run_contract_owned,
)
from researchassistant.storage.checkpoint_store import (
    read_stage_artifact as _read_stage_artifact_owned,
)
from researchassistant.storage.checkpoint_store import (
    upsert_orchestration_checkpoint as _upsert_orchestration_checkpoint_owned,
)
from researchassistant.storage.evidence_transactions import (
    _row_to_candidate as _row_to_candidate,
)
from researchassistant.storage.evidence_transactions import (
    _row_to_ledger_record as _row_to_ledger_record,
)
from researchassistant.storage.evidence_transactions import (
    _row_to_review_result as _row_to_review_result,
)
from researchassistant.storage.evidence_transactions import (
    _row_to_score_decision as _row_to_score_decision,
)
from researchassistant.storage.evidence_transactions import (
    _row_to_snapshot as _row_to_snapshot,
)
from researchassistant.storage.evidence_transactions import (
    _row_to_statement_draft as _row_to_statement_draft,
)
from researchassistant.storage.evidence_transactions import (
    insert_analyst_decision as _insert_analyst_decision_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_candidate as _insert_candidate_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_ledger_record as _insert_ledger_record_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_model_invocation as _insert_model_invocation_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_provisional_extraction as _insert_provisional_extraction_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_retrieval_attempt as _insert_retrieval_attempt_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_snapshot as _insert_snapshot_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_statement_draft as _insert_statement_draft_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_statement_review as _insert_statement_review_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_synthesis as _insert_synthesis_owned,
)
from researchassistant.storage.evidence_transactions import (
    insert_validation as _insert_validation_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_analyst_decision as _read_analyst_decision_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_candidate as _read_candidate_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_ledger_record as _read_ledger_record_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_model_invocation as _read_model_invocation_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_provisional_extractions as _read_provisional_extractions_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_retrieval_attempt as _read_retrieval_attempt_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_snapshot as _read_snapshot_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_statement_draft as _read_statement_draft_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_statement_review as _read_statement_review_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_synthesis as _read_synthesis_owned,
)
from researchassistant.storage.evidence_transactions import (
    read_validation as _read_validation_owned,
)
from researchassistant.storage.legacy_planning_store import (
    insert_planner_output as _insert_planner_output_owned,
)
from researchassistant.storage.legacy_planning_store import (
    insert_search_queries as _insert_search_queries_owned,
)
from researchassistant.storage.legacy_planning_store import (
    read_planner_output as _read_planner_output_owned,
)
from researchassistant.storage.model_accounting_store import (
    _RESERVATION_IDENTITY_FIELDS as _RESERVATION_IDENTITY_FIELDS,
)
from researchassistant.storage.model_accounting_store import (
    ModelAttemptBudgetError as ModelAttemptBudgetError,
)
from researchassistant.storage.model_accounting_store import (
    _check_reservation_identity as _check_reservation_identity,
)
from researchassistant.storage.model_accounting_store import (
    _insert_model_route_attempt_row as _insert_model_route_attempt_row,
)
from researchassistant.storage.model_accounting_store import (
    _row_to_model_route_attempt as _row_to_model_route_attempt,
)
from researchassistant.storage.model_accounting_store import (
    _validated_route_attempt as _validated_route_attempt,
)
from researchassistant.storage.model_accounting_store import (
    finish_model_route_attempt as _finish_model_route_attempt_owned,
)
from researchassistant.storage.model_accounting_store import (
    read_model_route_attempts as _read_model_route_attempts_owned,
)
from researchassistant.storage.model_accounting_store import (
    reserve_model_route_attempt as _reserve_model_route_attempt_owned,
)
from researchassistant.storage.model_accounting_store import (
    validate_model_route_attempt_identity as validate_model_route_attempt_identity,
)
from researchassistant.storage.portfolio_transactions import (
    _legacy_missing_snapshot_projection as _legacy_missing_snapshot_projection,
)
from researchassistant.storage.portfolio_transactions import (
    insert_evidence_trail_entry as _insert_evidence_trail_entry_owned,
)
from researchassistant.storage.portfolio_transactions import (
    insert_mvp10_portfolio_batch as _insert_mvp10_portfolio_batch_owned,
)
from researchassistant.storage.portfolio_transactions import (
    insert_portfolio_coverage_assessment as _insert_portfolio_coverage_assessment_owned,
)
from researchassistant.storage.portfolio_transactions import (
    insert_portfolio_item as _insert_portfolio_item_owned,
)
from researchassistant.storage.portfolio_transactions import (
    insert_source_family_member as _insert_source_family_member_owned,
)
from researchassistant.storage.portfolio_transactions import (
    read_evidence_trail_entries as _read_evidence_trail_entries_owned,
)
from researchassistant.storage.portfolio_transactions import (
    read_portfolio_coverage_assessment as _read_portfolio_coverage_assessment_owned,
)
from researchassistant.storage.portfolio_transactions import (
    read_portfolio_items as _read_portfolio_items_owned,
)
from researchassistant.storage.run_state_store import (
    _row_to_run as _row_to_run,
)
from researchassistant.storage.run_state_store import (
    insert_cancellation_request as _insert_cancellation_request_owned,
)
from researchassistant.storage.run_state_store import (
    insert_research_governor_decision as _insert_research_governor_decision_owned,
)
from researchassistant.storage.run_state_store import (
    insert_research_round_record as _insert_research_round_record_owned,
)
from researchassistant.storage.run_state_store import (
    insert_research_terminal_result as _insert_research_terminal_result_owned,
)
from researchassistant.storage.run_state_store import (
    insert_run as _insert_run_owned,
)
from researchassistant.storage.run_state_store import (
    list_runs as _list_runs_owned,
)
from researchassistant.storage.run_state_store import (
    read_cancellation_request as _read_cancellation_request_owned,
)
from researchassistant.storage.run_state_store import (
    read_research_governor_decision as _read_research_governor_decision_owned,
)
from researchassistant.storage.run_state_store import (
    read_research_round_records as _read_research_round_records_owned,
)
from researchassistant.storage.run_state_store import (
    read_research_terminal_result as _read_research_terminal_result_owned,
)
from researchassistant.storage.run_state_store import (
    read_run as _read_run_owned,
)
from researchassistant.storage.run_state_store import (
    update_run as _update_run_owned,
)
from researchassistant.storage.sqlite_policy import connect_database as connect_database
from researchassistant.storage.sqlite_policy import is_busy_error as is_busy_error
from researchassistant.storage.store_schema import _MVP10_TABLES as _MVP10_TABLES
from researchassistant.storage.store_schema import _MVP11_TABLES as _MVP11_TABLES
from researchassistant.storage.store_schema import _MVP11_TRIGGERS as _MVP11_TRIGGERS
from researchassistant.storage.store_schema import _REQUIRED_INDEXES as _REQUIRED_INDEXES
from researchassistant.storage.store_schema import _REQUIRED_TABLES as _REQUIRED_TABLES
from researchassistant.storage.store_schema import _REQUIRED_TRIGGERS as _REQUIRED_TRIGGERS
from researchassistant.storage.store_schema import (
    _SNAPSHOT_PROVENANCE_COLUMNS as _SNAPSHOT_PROVENANCE_COLUMNS,
)
from researchassistant.storage.store_schema import _V2_PHASE1_TABLES as _V2_PHASE1_TABLES
from researchassistant.storage.store_schema import _V2_PHASE1_TRIGGERS as _V2_PHASE1_TRIGGERS
from researchassistant.storage.store_schema import _V2_PHASE3_TABLES as _V2_PHASE3_TABLES
from researchassistant.storage.store_schema import _V2_PHASE3_TRIGGERS as _V2_PHASE3_TRIGGERS
from researchassistant.storage.store_schema import _V2_PHASE10_TABLES as _V2_PHASE10_TABLES
from researchassistant.storage.store_schema import _V2_PHASE10_TRIGGERS as _V2_PHASE10_TRIGGERS
from researchassistant.storage.store_schema import CURRENT_SCHEMA_VERSION as CURRENT_SCHEMA_VERSION
from researchassistant.storage.store_schema import (
    IMMUTABLE_ARTIFACT_TRIGGERS as IMMUTABLE_ARTIFACT_TRIGGERS,
)
from researchassistant.storage.store_schema import MIGRATION_DESCRIPTIONS as MIGRATION_DESCRIPTIONS
from researchassistant.storage.store_schema import MLP4_SCHEMA_VERSION as MLP4_SCHEMA_VERSION
from researchassistant.storage.store_schema import MVP10_SCHEMA_VERSION as MVP10_SCHEMA_VERSION
from researchassistant.storage.store_schema import MVP11_SCHEMA_VERSION as MVP11_SCHEMA_VERSION
from researchassistant.storage.store_schema import MVP68_SCHEMA_VERSION as MVP68_SCHEMA_VERSION
from researchassistant.storage.store_schema import MVP69_SCHEMA_VERSION as MVP69_SCHEMA_VERSION
from researchassistant.storage.store_schema import (
    RAW_CLAIM_SCHEMA_VERSION as RAW_CLAIM_SCHEMA_VERSION,
)
from researchassistant.storage.store_schema import (
    RAW_CLAIM_TRIGGER_ERROR as RAW_CLAIM_TRIGGER_ERROR,
)
from researchassistant.storage.store_schema import RAW_CLAIM_TRIGGER_NAME as RAW_CLAIM_TRIGGER_NAME
from researchassistant.storage.store_schema import (
    V2_PHASE1_SCHEMA_VERSION as V2_PHASE1_SCHEMA_VERSION,
)
from researchassistant.storage.store_schema import (
    V2_PHASE3_SCHEMA_VERSION as V2_PHASE3_SCHEMA_VERSION,
)
from researchassistant.storage.store_schema import (
    V2_PHASE10_SCHEMA_VERSION as V2_PHASE10_SCHEMA_VERSION,
)
from researchassistant.storage.store_schema import RecordedSchemaError as RecordedSchemaError
from researchassistant.storage.store_schema import (
    _apply_mlp4_discovery_query_migration as _apply_mlp4_discovery_query_migration,
)
from researchassistant.storage.store_schema import (
    _apply_mvp10_evidence_portfolio_migration as _apply_mvp10_evidence_portfolio_migration,
)
from researchassistant.storage.store_schema import (
    _apply_mvp11_research_governor_migration as _apply_mvp11_research_governor_migration,
)
from researchassistant.storage.store_schema import (
    _apply_mvp68_integrity_migration as _apply_mvp68_integrity_migration,
)
from researchassistant.storage.store_schema import (
    _apply_mvp69_provenance_migration as _apply_mvp69_provenance_migration,
)
from researchassistant.storage.store_schema import (
    _apply_raw_claim_immutability_migration as _apply_raw_claim_immutability_migration,
)
from researchassistant.storage.store_schema import (
    _apply_v2_phase1_artifact_migration as _apply_v2_phase1_artifact_migration,
)
from researchassistant.storage.store_schema import (
    _apply_v2_phase3_initial_planner_migration as _apply_v2_phase3_initial_planner_migration,
)
from researchassistant.storage.store_schema import (
    _apply_v2_phase10_reviewer_ledger_migration as _apply_v2_phase10_reviewer_ledger_migration,
)
from researchassistant.storage.store_schema import _immutable_trigger_sql as _immutable_trigger_sql
from researchassistant.storage.store_schema import (
    _is_expected_immutable_trigger as _is_expected_immutable_trigger,
)
from researchassistant.storage.store_schema import (
    _is_expected_raw_claim_trigger as _is_expected_raw_claim_trigger,
)
from researchassistant.storage.store_schema import _raw_claim_trigger_sql as _raw_claim_trigger_sql
from researchassistant.storage.store_schema import (
    _verify_mlp4_discovery_query_schema as _verify_mlp4_discovery_query_schema,
)
from researchassistant.storage.store_schema import _verify_mvp10_schema as _verify_mvp10_schema
from researchassistant.storage.store_schema import _verify_mvp11_schema as _verify_mvp11_schema
from researchassistant.storage.store_schema import _verify_mvp68_schema as _verify_mvp68_schema
from researchassistant.storage.store_schema import _verify_mvp69_schema as _verify_mvp69_schema
from researchassistant.storage.store_schema import (
    _verify_v2_phase1_artifact_schema as _verify_v2_phase1_artifact_schema,
)
from researchassistant.storage.store_schema import (
    _verify_v2_phase3_initial_planner_schema as _verify_v2_phase3_initial_planner_schema,
)
from researchassistant.storage.store_schema import (
    _verify_v2_phase10_reviewer_ledger_schema as _verify_v2_phase10_reviewer_ledger_schema,
)
from researchassistant.storage.store_schema import initialize_database as initialize_database
from researchassistant.storage.store_schema import (
    validate_recorded_database as validate_recorded_database,
)
from researchassistant.storage.store_schema import (
    validate_schema_structure as validate_schema_structure,
)
from researchassistant.storage.store_types import (
    DatabaseCompatibilityError as DatabaseCompatibilityError,
)
from researchassistant.storage.store_types import (
    DatabaseCompatibilityIssue as DatabaseCompatibilityIssue,
)
from researchassistant.storage.store_types import (
    DatabaseCompatibilityResult as DatabaseCompatibilityResult,
)
from researchassistant.storage.store_types import (
    DatabaseReader as DatabaseReader,
)
from researchassistant.storage.store_types import (
    _compatibility_error as _compatibility_error,
)
from researchassistant.storage.store_types import (
    _dt_to_iso as _dt_to_iso,
)
from researchassistant.storage.store_types import (
    _iso_to_dt as _iso_to_dt,
)
from researchassistant.storage.store_types import (
    _json_to_offsets as _json_to_offsets,
)
from researchassistant.storage.store_types import (
    _offsets_to_json as _offsets_to_json,
)
from researchassistant.storage.store_types import (
    _read_execute as _read_execute,
)
from researchassistant.storage.store_types import (
    _ReadRows as _ReadRows,
)
from researchassistant.storage.store_types import (
    _require_aware_datetime as _require_aware_datetime,
)
from researchassistant.storage.v2_transactions import (
    _insert_v2_artifact_on_connection as _insert_v2_artifact_on_connection,
)
from researchassistant.storage.v2_transactions import (
    _row_to_v2_artifact as _row_to_v2_artifact,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_artifact as _insert_v2_artifact_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_artifact_batch as _insert_v2_artifact_batch_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_evidence_admission as _insert_v2_evidence_admission_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_evidence_admission_checkpoint as _insert_v2_evidence_admission_checkpoint_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_initial_planner_output as _insert_v2_initial_planner_output_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_ledger_admission as _insert_v2_ledger_admission_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_ledger_admission_checkpoint as _insert_v2_ledger_admission_checkpoint_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_pipeline_identity as _insert_v2_pipeline_identity_owned,
)
from researchassistant.storage.v2_transactions import (
    insert_v2_terminal_artifact as _insert_v2_terminal_artifact_owned,
)
from researchassistant.storage.v2_transactions import (
    read_v2_artifact as _read_v2_artifact_owned,
)
from researchassistant.storage.v2_transactions import (
    read_v2_evidence_admission as _read_v2_evidence_admission_owned,
)
from researchassistant.storage.v2_transactions import (
    read_v2_initial_planner_output as _read_v2_initial_planner_output_owned,
)
from researchassistant.storage.v2_transactions import (
    read_v2_ledger_admission as _read_v2_ledger_admission_owned,
)
from researchassistant.storage.v2_transactions import (
    read_v2_physical_call_artifacts as _read_v2_physical_call_artifacts_owned,
)


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with foreign keys enabled."""
    conn = connect_database(db_path)
    try:
        with closing(conn.execute("PRAGMA foreign_keys = ON;")):
            pass
        conn.row_factory = sqlite3.Row
    except BaseException:
        conn.close()
        raise
    return conn


@contextmanager
def read_snapshot_connection(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Pin one committed view, preserving an existing caller-owned transaction."""
    owned = not conn.in_transaction
    try:
        if owned:
            with closing(conn.execute("BEGIN")):
                pass
        yield conn
        if owned and conn.in_transaction:
            with closing(conn.execute("COMMIT")):
                pass
    except BaseException as exc:
        if owned and conn.in_transaction:
            with closing(conn.execute("ROLLBACK")):
                pass
        if is_busy_error(exc):
            raise _compatibility_error(
                DatabaseCompatibilityIssue.BUSY,
                "Database is busy; inspection timed out. Retry shortly.",
            ) from exc
        raise


@contextmanager
def _read_connection(source: DatabaseReader) -> Iterator[sqlite3.Connection]:
    if isinstance(source, sqlite3.Connection):
        with read_snapshot_connection(source):
            yield source
        return
    conn = _open_read_connection(source)
    try:
        with read_snapshot_connection(conn):
            yield conn
    finally:
        conn.close()


def _validate_read_only_schema(conn: sqlite3.Connection) -> DatabaseCompatibilityResult:
    try:
        latest = validate_recorded_database(conn, allow_pending=False)
    except sqlite3.DatabaseError as exc:
        if is_busy_error(exc):
            raise _compatibility_error(
                DatabaseCompatibilityIssue.BUSY,
                "Database is busy; validation timed out. Retry inspection shortly.",
            ) from exc
        message = str(exc)
        issue = DatabaseCompatibilityIssue.CORRUPT_SCHEMA
        version = None
        if isinstance(exc, RecordedSchemaError):
            issue = DatabaseCompatibilityIssue(exc.issue)
            version = exc.version
        elif "not a database" in message.lower() or "file is encrypted" in message.lower():
            issue = DatabaseCompatibilityIssue.INVALID_SQLITE
        raise _compatibility_error(
            issue, f"{message}; inspection made no changes", schema_version=version
        ) from exc
    if latest < MVP69_SCHEMA_VERSION:
        raise _compatibility_error(
            DatabaseCompatibilityIssue.OLDER_SCHEMA,
            f"database schema version {latest} requires migration to version "
            f"{CURRENT_SCHEMA_VERSION}; a writable run or resume is required",
            schema_version=latest,
        )
    return DatabaseCompatibilityResult(
        compatible=True,
        schema_version=latest,
        message=f"ResearchAssistant schema version {latest} is compatible",
    )


def _open_read_connection(source: str | Path) -> sqlite3.Connection:
    """Non-creating path boundary; point reads do not repeat schema validation."""
    if not isinstance(source, (str, Path)):
        raise TypeError("database reader must be a path or sqlite3.Connection")
    path = Path(source).expanduser()
    conn = None
    try:
        path = path.resolve()
        if not path.exists():
            raise _compatibility_error(
                DatabaseCompatibilityIssue.MISSING_FILE,
                f"inspection database does not exist: {path}",
            )
        if not path.is_file():
            raise _compatibility_error(
                DatabaseCompatibilityIssue.OPEN_FAILED,
                f"inspection database is not a regular file: {path}",
            )
        encoded_path = quote(path.as_posix(), safe="/")
        conn = connect_database(f"file:{encoded_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        with closing(conn.execute("PRAGMA foreign_keys = ON")):
            pass
        with closing(conn.execute("PRAGMA query_only = ON")):
            pass
        return conn
    except DatabaseCompatibilityError:
        raise
    except (OSError, sqlite3.Error) as exc:
        if conn is not None:
            conn.close()
        raise _compatibility_error(
            DatabaseCompatibilityIssue.OPEN_FAILED,
            f"could not open inspection database read-only: {path}",
        ) from exc
    except BaseException:
        if conn is not None:
            conn.close()
        raise


class ReadOnlyStore:
    """One cohesive read-only SQLite session for inspection and history."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path).expanduser()
        self.path = path
        self.connection: sqlite3.Connection
        self.compatibility: DatabaseCompatibilityResult
        try:
            path = path.resolve()
            self.path = path
            self.connection = _open_read_connection(path)
            with closing(self.connection.execute("BEGIN")):
                pass
            self.compatibility = _validate_read_only_schema(self.connection)
        except DatabaseCompatibilityError:
            if hasattr(self, "connection"):
                self.connection.close()
            raise
        except (OSError, sqlite3.Error) as exc:
            if hasattr(self, "connection"):
                self.connection.close()
            raise _compatibility_error(
                DatabaseCompatibilityIssue.BUSY
                if is_busy_error(exc)
                else DatabaseCompatibilityIssue.OPEN_FAILED,
                "Database is busy; retry inspection shortly."
                if is_busy_error(exc)
                else f"could not open inspection database read-only: {path}",
            ) from exc
        except BaseException:
            if hasattr(self, "connection"):
                self.connection.close()
            raise

    def __enter__(self) -> ReadOnlyStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        # close() rolls back this locally owned read-only transaction, including
        # exception paths; it never commits application writes.
        self.connection.close()

    def read_run(self, run_id: UUID) -> RunManifest:
        return read_run(self.connection, run_id)


def open_read_only_store(db_path: str | Path) -> ReadOnlyStore:
    """Open an existing compatible database without creating or migrating it."""
    return ReadOnlyStore(db_path)


def init_db(
    db_path: str, *, lock_owned: bool = False, backup_policy: BackupPolicy | None = None
) -> None:
    """Create/validate schema through the intentional writable initialization path."""
    initialize_database(
        db_path, connect=_connect, lock_owned=lock_owned, backup_policy=backup_policy
    )


def insert_source_family_member(db_path: str, entry: EvidenceTrailEntry) -> None:
    """Persist one immutable family assignment when a source has an identified family."""
    return _insert_source_family_member_owned(
        db_path=db_path,
        entry=entry,
        _connect=_connect,
    )


def insert_evidence_trail_entry(db_path: str, entry: EvidenceTrailEntry) -> None:
    """Persist one complete source outcome without rewriting source history."""
    return _insert_evidence_trail_entry_owned(
        db_path=db_path,
        entry=entry,
        _connect=_connect,
    )


def read_evidence_trail_entries(
    db_path: DatabaseReader, run_id: UUID
) -> tuple[EvidenceTrailEntry, ...]:
    """Read appended source outcomes; a pre-MVP-10 database has no such rows."""
    return _read_evidence_trail_entries_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_portfolio_item(db_path: str, item: PortfolioItem) -> None:
    """Append one approved Ledger statement to the portfolio."""
    return _insert_portfolio_item_owned(
        db_path=db_path,
        item=item,
        _connect=_connect,
    )


def read_portfolio_items(db_path: DatabaseReader, run_id: UUID) -> tuple[PortfolioItem, ...]:
    """Read the immutable portfolio, or an empty portfolio for historical runs."""
    return _read_portfolio_items_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_mvp10_portfolio_batch(
    db_path: str, entries: Sequence[EvidenceTrailEntry], items: Sequence[PortfolioItem]
) -> None:
    """Append one portfolio phase atomically, accepting exact historical replay."""
    return _insert_mvp10_portfolio_batch_owned(
        db_path=db_path,
        entries=entries,
        items=items,
        _connect=_connect,
    )


def insert_portfolio_coverage_assessment(
    db_path: str, assessment: PortfolioCoverageAssessment
) -> None:
    """Persist the single terminal deterministic coverage assessment."""
    return _insert_portfolio_coverage_assessment_owned(
        db_path=db_path,
        assessment=assessment,
        _connect=_connect,
    )


def read_portfolio_coverage_assessment(
    db_path: DatabaseReader, run_id: UUID
) -> PortfolioCoverageAssessment | None:
    """Read terminal coverage when present, without fabricating it for history."""
    return _read_portfolio_coverage_assessment_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_research_round_record(db_path: str, record: ResearchRoundRecord) -> None:
    """Append one completed or terminal research round; SQLite enforces its 1..3 bound."""
    return _insert_research_round_record_owned(
        db_path=db_path,
        record=record,
        _connect=_connect,
    )


def read_research_round_records(
    db_path: DatabaseReader, run_id: UUID
) -> tuple[ResearchRoundRecord, ...]:
    """Read persisted bounded rounds, returning no synthetic rows for historical runs."""
    return _read_research_round_records_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_research_governor_decision(db_path: str, decision: ResearchGovernorDecision) -> None:
    """Append the single deterministic post-Round-2 authorization decision for a run."""
    return _insert_research_governor_decision_owned(
        db_path=db_path,
        decision=decision,
        _connect=_connect,
    )


def read_research_governor_decision(
    db_path: DatabaseReader, run_id: UUID
) -> ResearchGovernorDecision | None:
    """Read the immutable Governor decision without creating one for a historical run."""
    return _read_research_governor_decision_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_research_terminal_result(db_path: str, result: ResearchTerminalResult) -> None:
    """Append the terminal evidence classification after the final permitted round."""
    return _insert_research_terminal_result_owned(
        db_path=db_path,
        result=result,
        _connect=_connect,
    )


def read_research_terminal_result(
    db_path: DatabaseReader, run_id: UUID
) -> ResearchTerminalResult | None:
    """Read a persisted terminal classification without fabricating historical evidence."""
    return _read_research_terminal_result_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_run(db_path: str, manifest: RunManifest) -> None:
    return _insert_run_owned(
        db_path=db_path,
        manifest=manifest,
        _connect=_connect,
    )


def read_run(db_path: DatabaseReader, run_id: UUID) -> RunManifest:
    return _read_run_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def list_runs(db_path: DatabaseReader, *, limit: int = 100) -> list[RunManifest]:
    """Return the most recently updated runs for local inspection."""
    return _list_runs_owned(
        db_path=db_path,
        limit=limit,
        _read_connection=_read_connection,
    )


def update_run(db_path: str, manifest: RunManifest) -> None:
    """Update mutable run state while leaving insert-only evidence tables untouched."""
    return _update_run_owned(
        db_path=db_path,
        manifest=manifest,
        _connect=_connect,
    )


def insert_planner_output(db_path: str, planner: PlannerOutput) -> None:
    return _insert_planner_output_owned(
        db_path=db_path,
        planner=planner,
        _connect=_connect,
    )


def insert_search_queries(db_path: str, queries: tuple[SearchQuery, ...]) -> None:
    """Append a distinct Planner round's queries without rewriting the initial plan."""
    return _insert_search_queries_owned(
        db_path=db_path,
        queries=queries,
        _connect=_connect,
    )


def read_planner_output(db_path: DatabaseReader, run_id: UUID) -> PlannerOutput:
    return _read_planner_output_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_retrieval_attempt(db_path: str, record: RetrievalRecord) -> None:
    return _insert_retrieval_attempt_owned(
        db_path=db_path,
        record=record,
        _connect=_connect,
    )


def read_retrieval_attempt(db_path: DatabaseReader, retrieval_attempt_id: UUID) -> RetrievalRecord:
    return _read_retrieval_attempt_owned(
        db_path=db_path,
        retrieval_attempt_id=retrieval_attempt_id,
        _read_connection=_read_connection,
    )


def insert_snapshot(db_path: str, snapshot: SourceSnapshot) -> None:
    return _insert_snapshot_owned(
        db_path=db_path,
        snapshot=snapshot,
        _connect=_connect,
    )


def read_snapshot(db_path: DatabaseReader, snapshot_id: UUID) -> SourceSnapshot:
    return _read_snapshot_owned(
        db_path=db_path,
        snapshot_id=snapshot_id,
        _read_connection=_read_connection,
    )


def insert_provisional_extraction(db_path: str, prov: ProvisionalCandidate) -> None:
    return _insert_provisional_extraction_owned(
        db_path=db_path,
        prov=prov,
        _connect=_connect,
    )


def read_provisional_extractions(
    db_path: DatabaseReader, run_id: UUID
) -> list[ProvisionalCandidate]:
    return _read_provisional_extractions_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_candidate(db_path: str, candidate: CandidateQuoteBlock) -> None:
    return _insert_candidate_owned(
        db_path=db_path,
        candidate=candidate,
        _connect=_connect,
    )


def read_candidate(db_path: DatabaseReader, quote_block_id: UUID) -> CandidateQuoteBlock:
    return _read_candidate_owned(
        db_path=db_path,
        quote_block_id=quote_block_id,
        _read_connection=_read_connection,
    )


def insert_analyst_decision(db_path: str, decision: ScoreDecision) -> None:
    return _insert_analyst_decision_owned(
        db_path=db_path,
        decision=decision,
        _connect=_connect,
    )


def read_analyst_decision(
    db_path: DatabaseReader, run_id: UUID, quote_block_id: UUID
) -> ScoreDecision:
    return _read_analyst_decision_owned(
        db_path=db_path,
        run_id=run_id,
        quote_block_id=quote_block_id,
        _read_connection=_read_connection,
    )


def insert_statement_draft(db_path: str, draft: StatementDraft) -> None:
    return _insert_statement_draft_owned(
        db_path=db_path,
        draft=draft,
        _connect=_connect,
    )


def read_statement_draft(db_path: DatabaseReader, statement_draft_id: UUID) -> StatementDraft:
    return _read_statement_draft_owned(
        db_path=db_path,
        statement_draft_id=statement_draft_id,
        _read_connection=_read_connection,
    )


def insert_statement_review(db_path: str, review: StatementReviewResult) -> None:
    return _insert_statement_review_owned(
        db_path=db_path,
        review=review,
        _connect=_connect,
    )


def read_statement_review(
    db_path: DatabaseReader, run_id: UUID, statement_draft_id: UUID
) -> StatementReviewResult:
    return _read_statement_review_owned(
        db_path=db_path,
        run_id=run_id,
        statement_draft_id=statement_draft_id,
        _read_connection=_read_connection,
    )


def insert_ledger_record(db_path: str, record: LedgerRecord) -> None:
    return _insert_ledger_record_owned(
        db_path=db_path,
        record=record,
        _connect=_connect,
    )


def read_ledger_record(db_path: DatabaseReader, ledger_claim_id: UUID) -> LedgerRecord:
    return _read_ledger_record_owned(
        db_path=db_path,
        ledger_claim_id=ledger_claim_id,
        _read_connection=_read_connection,
    )


def insert_synthesis(db_path: str, synthesis: SynthesisOutput) -> None:
    return _insert_synthesis_owned(
        db_path=db_path,
        synthesis=synthesis,
        _connect=_connect,
    )


def read_synthesis(db_path: DatabaseReader, run_id: UUID) -> SynthesisOutput:
    return _read_synthesis_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_validation(db_path: str, result: ValidationResult) -> None:
    return _insert_validation_owned(
        db_path=db_path,
        result=result,
        _connect=_connect,
    )


def read_validation(db_path: DatabaseReader, run_id: UUID) -> ValidationResult:
    return _read_validation_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_model_invocation(db_path: str, record: ModelInvocationRecord) -> None:
    return _insert_model_invocation_owned(
        db_path=db_path,
        record=record,
        _connect=_connect,
    )


def read_model_invocation(db_path: DatabaseReader, invocation_id: UUID) -> ModelInvocationRecord:
    return _read_model_invocation_owned(
        db_path=db_path,
        invocation_id=invocation_id,
        _read_connection=_read_connection,
    )


def insert_provider_run_contract(db_path: str, contract: ProviderRunContract) -> None:
    """Insert one immutable provider compatibility contract or verify exact identity."""
    return _insert_provider_run_contract_owned(
        db_path=db_path,
        contract=contract,
        _connect=_connect,
    )


def read_provider_run_contract(db_path: DatabaseReader, run_id: UUID) -> ProviderRunContract:
    return _read_provider_run_contract_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def upsert_orchestration_checkpoint(db_path: str, checkpoint: OrchestrationCheckpoint) -> None:
    return _upsert_orchestration_checkpoint_owned(
        db_path=db_path,
        checkpoint=checkpoint,
        _connect=_connect,
    )


def read_orchestration_checkpoint(
    db_path: DatabaseReader, run_id: UUID, stage_key: str
) -> OrchestrationCheckpoint:
    return _read_orchestration_checkpoint_owned(
        db_path=db_path,
        run_id=run_id,
        stage_key=stage_key,
        _read_connection=_read_connection,
    )


def read_orchestration_checkpoints(
    db_path: DatabaseReader, run_id: UUID
) -> list[OrchestrationCheckpoint]:
    return _read_orchestration_checkpoints_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_stage_artifact(db_path: str, artifact: PersistedStageArtifact) -> None:
    return _insert_stage_artifact_owned(
        db_path=db_path,
        artifact=artifact,
        _connect=_connect,
    )


def read_stage_artifact(
    db_path: DatabaseReader, run_id: UUID, artifact_key: str
) -> PersistedStageArtifact:
    return _read_stage_artifact_owned(
        db_path=db_path,
        run_id=run_id,
        artifact_key=artifact_key,
        _read_connection=_read_connection,
    )


def insert_v2_pipeline_identity(
    db_path: str, run_id: UUID, identity: V2PipelineIdentity, created_at: datetime
) -> None:
    """Explicitly identify a new run as v2; historical provider contracts cannot be relabeled."""
    return _insert_v2_pipeline_identity_owned(
        db_path=db_path,
        run_id=run_id,
        identity=identity,
        created_at=created_at,
        _connect=_connect,
    )


def insert_v2_artifact(
    db_path: str, artifact_key: str, artifact: StrictModel, created_at: datetime
) -> V2PersistedArtifact:
    """Persist a canonical v2 artifact once, refusing a missing v2 identity or drift."""
    return _insert_v2_artifact_owned(
        db_path=db_path,
        artifact_key=artifact_key,
        artifact=artifact,
        created_at=created_at,
        _connect=_connect,
    )


def insert_v2_artifact_batch(
    db_path: str, artifacts: tuple[tuple[str, StrictModel, datetime], ...]
) -> tuple[V2PersistedArtifact, ...]:
    """Commit one run's mutually dependent immutable artifacts together."""
    return _insert_v2_artifact_batch_owned(db_path, artifacts, _connect=_connect)


def insert_v2_ledger_admission_checkpoint(
    db_path: str,
    artifact_key: str,
    source_result: V2ReviewerLedgerSourceResult,
    created_at: datetime,
) -> None:
    """Commit a historical Reviewer checkpoint with its exact admission."""
    return _insert_v2_ledger_admission_checkpoint_owned(
        db_path, artifact_key, source_result, created_at, _connect=_connect
    )


def insert_v2_terminal_artifact(
    db_path: str,
    artifact_key: str,
    artifact: StrictModel,
    completed_at: datetime,
    status: RunStatus,
    stage: Stage,
) -> V2PersistedArtifact:
    """Commit an immutable terminal artifact and its mutable run manifest together."""
    return _insert_v2_terminal_artifact_owned(
        db_path=db_path,
        artifact_key=artifact_key,
        artifact=artifact,
        completed_at=completed_at,
        status=status,
        stage=stage,
        _connect=_connect,
    )


def read_v2_artifact(
    db_path: DatabaseReader, run_id: UUID, artifact_key: str
) -> V2PersistedArtifact:
    """Read a persisted v2 envelope without converting it into a mutable handoff."""
    return _read_v2_artifact_owned(
        db_path=db_path,
        run_id=run_id,
        artifact_key=artifact_key,
        _read_connection=_read_connection,
    )


def read_v2_physical_call_artifacts(
    db_path: DatabaseReader, run_id: UUID
) -> tuple[V2PersistedArtifact, ...]:
    """Read every current or legacy physical-call envelope in one query."""
    return _read_v2_physical_call_artifacts_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def insert_v2_ledger_admission(
    db_path: str, record: LedgerRecord, provenance: V2LedgerProvenance
) -> None:
    """Append one v2-approved Ledger record with immutable discovery provenance."""
    return _insert_v2_ledger_admission_owned(
        db_path=db_path,
        record=record,
        provenance=provenance,
        _connect=_connect,
    )


def read_v2_ledger_admission(
    db_path: DatabaseReader, ledger_claim_id: UUID
) -> tuple[LedgerRecord, V2LedgerProvenance]:
    """Read one immutable v2 Ledger admission and its separate provenance context."""
    return _read_v2_ledger_admission_owned(
        db_path=db_path,
        ledger_claim_id=ledger_claim_id,
        _read_connection=_read_connection,
    )


def insert_v2_evidence_admission(
    db_path: str, record: V2EvidenceAdmissionRecord, provenance: V2LedgerProvenance
) -> None:
    """Append one immutable analyzer-admitted evidence record."""
    return _insert_v2_evidence_admission_owned(
        db_path=db_path,
        record=record,
        provenance=provenance,
        _connect=_connect,
    )


def insert_v2_evidence_admission_checkpoint(
    db_path: str,
    artifact_key: str,
    source_result: V2EvidenceAdmissionSourceResult,
    created_at: datetime,
) -> None:
    """Atomically append an admission and the source checkpoint used by resume."""
    return _insert_v2_evidence_admission_checkpoint_owned(
        db_path=db_path,
        artifact_key=artifact_key,
        source_result=source_result,
        created_at=created_at,
        _connect=_connect,
    )


def read_v2_evidence_admission(
    db_path: DatabaseReader, ledger_claim_id: UUID
) -> tuple[V2EvidenceAdmissionRecord, V2LedgerProvenance]:
    """Read one immutable analyzer admission and its discovery provenance."""
    return _read_v2_evidence_admission_owned(
        db_path=db_path,
        ledger_claim_id=ledger_claim_id,
        _read_connection=_read_connection,
    )


def insert_v2_initial_planner_output(db_path: str, output: V2InitialPlannerOutput) -> None:
    """Append one validated fresh-v2 initial plan and exactly its Round-1 search queries."""
    return _insert_v2_initial_planner_output_owned(
        db_path=db_path,
        output=output,
        _connect=_connect,
        _read_connection=_read_connection,
    )


def read_v2_initial_planner_output(db_path: DatabaseReader, run_id: UUID) -> V2InitialPlannerOutput:
    """Reconstruct a typed fresh-v2 Round-1 plan without creating later-round searches."""
    return _read_v2_initial_planner_output_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )


def reserve_model_route_attempt(
    db_path: str,
    attempt: ModelRouteAttempt,
    *,
    max_model_calls: int,
    max_total_tokens: int | None = None,
    max_total_cost_usd: Decimal | None = None,
) -> ModelRouteAttempt:
    return _reserve_model_route_attempt_owned(
        db_path=db_path,
        attempt=attempt,
        max_model_calls=max_model_calls,
        max_total_tokens=max_total_tokens,
        max_total_cost_usd=max_total_cost_usd,
        _connect=_connect,
    )


def finish_model_route_attempt(db_path: str, attempt: ModelRouteAttempt) -> None:
    return _finish_model_route_attempt_owned(
        db_path=db_path,
        attempt=attempt,
        _connect=_connect,
    )


def read_model_route_attempts(
    db_path: DatabaseReader, run_id: UUID, operation_id: UUID | None = None
) -> list[ModelRouteAttempt]:
    return _read_model_route_attempts_owned(
        db_path=db_path,
        run_id=run_id,
        operation_id=operation_id,
        _read_connection=_read_connection,
    )


def insert_cancellation_request(
    db_path: str, request: RunCancellationRequest
) -> RunCancellationRequest:
    return _insert_cancellation_request_owned(
        db_path=db_path,
        request=request,
        _connect=_connect,
        _read_connection=_read_connection,
    )


def read_cancellation_request(db_path: DatabaseReader, run_id: UUID) -> RunCancellationRequest:
    return _read_cancellation_request_owned(
        db_path=db_path,
        run_id=run_id,
        _read_connection=_read_connection,
    )
