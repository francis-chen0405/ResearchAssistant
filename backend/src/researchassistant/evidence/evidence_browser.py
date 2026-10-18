"""Typed, read-only reconstruction of a run's evidence trail."""

from __future__ import annotations

import sqlite3
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict, Field

import researchassistant.storage.store as artifact_store
from researchassistant.contracts.historical import (
    AugustLedgerRecord,
    HistoricalRead,
    RecordCompatibilityError,
    RecordCompatibilityResult,
)
from researchassistant.contracts.models import (
    CandidateQuoteBlock,
    EvidenceRole,
    EvidenceTrailEntry,
    EvidenceTrailOutcome,
    LedgerRecord,
    PortfolioCoverageAssessment,
    ProviderRunContract,
    ResearchGovernorDecision,
    ResearchRoundRecord,
    ResearchTerminalResult,
    RunManifest,
    ScoreDecision,
    SourceSnapshot,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
    ValidationResult,
)
from researchassistant.evidence.evidence_core import (
    FRESH_QUOTE_CONTEXT_FILTER_VERSION,
    parse_extracted_quote_block,
    validate_bracket_context,
    validate_snapshot_integrity,
)
from researchassistant.storage.store import (
    DatabaseCompatibilityError,
    open_read_only_store,
    read_evidence_trail_entries,
    read_portfolio_coverage_assessment,
    read_research_governor_decision,
    read_research_round_records,
    read_research_terminal_result,
    read_run,
)


class EvidenceBrowserError(ValueError):
    """Raised when an evidence trail cannot be read safely."""


class EvidenceStage(StrEnum):
    CANDIDATE = "candidate"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    LEDGER = "ledger"
    VALIDATION = "validation"


class EvidenceBrowserFilter(StrictModel):
    """Optional immutable filters for a read-only evidence trail."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stance: str | None = None
    stage: EvidenceStage | None = None
    source_url: str | None = Field(default=None, min_length=1)
    approved: bool | None = None
    released: bool | None = None
    outcome: EvidenceTrailOutcome | None = None
    role: EvidenceRole | None = None
    research_round: str | None = None
    cost_incurred: bool | None = None


DEFAULT_EVIDENCE_BROWSER_FILTER = EvidenceBrowserFilter()


class EvidenceTrailItem(StrictModel):
    """One candidate's complete, non-editable provenance and decision trail."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: CandidateQuoteBlock
    snapshot: SourceSnapshot
    analyst_decision: ScoreDecision | None = None
    statement_drafts: tuple[StatementDraft, ...] = ()
    reviewer_decisions: tuple[StatementReviewResult, ...] = ()
    ledger_records: tuple[LedgerRecord | AugustLedgerRecord, ...] = ()
    final_validation_present: bool
    released: bool
    artifact_label: str = Field(min_length=1)


class ReleasedStatementTrace(StrictModel):
    """The exact immutable chain behind one released factual statement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ledger_record: LedgerRecord | AugustLedgerRecord
    reviewer_decision: StatementReviewResult
    candidate: CandidateQuoteBlock
    snapshot: SourceSnapshot
    final_validation: ValidationResult


class EvidenceBrowserRun(StrictModel):
    """A complete local inspection result; text authority is explicitly labeled."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: RunManifest
    final_validation: ValidationResult | None = None
    trails: tuple[EvidenceTrailItem, ...]
    compatibility_issues: tuple[RecordCompatibilityResult, ...] = ()
    released_statement_traces: tuple[ReleasedStatementTrace, ...]
    evidence_trail: tuple[EvidenceTrailEntry, ...] = ()
    portfolio_coverage: PortfolioCoverageAssessment | None = None
    research_rounds: tuple[ResearchRoundRecord, ...] = ()
    governor_decision: ResearchGovernorDecision | None = None
    terminal_research_result: ResearchTerminalResult | None = None
    trusted_snapshot_text_label: str = "Trusted snapshot text (ResearchAssistant normalized)"
    provider_metadata_label: str = "Provider metadata (non-authoritative)"
    source_text_label: str = "Untrusted source text"


def browse_evidence_run(
    db_path: str | Path,
    run_id: UUID,
    filters: EvidenceBrowserFilter = DEFAULT_EVIDENCE_BROWSER_FILTER,
) -> EvidenceBrowserRun:
    """Read one compatible existing run without creating or mutating anything."""
    try:
        with open_read_only_store(db_path) as reader:
            manifest = read_run(reader.connection, run_id)
            validation = _optional_validation(reader.connection, run_id)
            compatibility_issues: list[RecordCompatibilityResult] = []
            trails = _trails(reader.connection, run_id, validation, compatibility_issues)
            filtered = tuple(trail for trail in trails if _matches(trail, filters))
            traces = _released_traces(filtered, validation)
            evidence_trail = tuple(
                entry
                for entry in read_evidence_trail_entries(reader.connection, run_id)
                if _matches_mvp10(entry, filters)
            )
            return EvidenceBrowserRun(
                manifest=manifest,
                final_validation=validation,
                trails=filtered,
                compatibility_issues=tuple(compatibility_issues),
                released_statement_traces=traces,
                evidence_trail=evidence_trail,
                portfolio_coverage=read_portfolio_coverage_assessment(reader.connection, run_id),
                research_rounds=read_research_round_records(reader.connection, run_id),
                governor_decision=read_research_governor_decision(reader.connection, run_id),
                terminal_research_result=read_research_terminal_result(reader.connection, run_id),
            )
    except DatabaseCompatibilityError as exc:
        raise EvidenceBrowserError(
            f"evidence browser cannot open this database safely: {exc}"
        ) from exc
    except (KeyError, ValueError) as exc:
        raise EvidenceBrowserError(
            f"evidence browser could not reconstruct run {run_id}: {exc}"
        ) from exc


def trace_released_statement(
    browser_run: EvidenceBrowserRun, ledger_claim_id: UUID
) -> ReleasedStatementTrace:
    """Return a released-statement trace or fail explicitly without inventing evidence."""
    for trace in browser_run.released_statement_traces:
        if trace.ledger_record.ledger_claim_id == ledger_claim_id:
            return trace
    raise EvidenceBrowserError(
        f"released statement {ledger_claim_id} is not available in this browser view"
    )


def _optional_validation(
    connection: artifact_store.DatabaseReader, run_id: UUID
) -> ValidationResult | None:
    try:
        return artifact_store.read_validation(connection, run_id)
    except KeyError:
        return None


def _trails(
    connection: sqlite3.Connection,
    run_id: UUID,
    validation: ValidationResult | None,
    compatibility_issues: list[RecordCompatibilityResult],
) -> tuple[EvidenceTrailItem, ...]:
    candidate_rows = artifact_store._read_execute(
        connection,
        "SELECT * FROM candidates WHERE run_id = ? ORDER BY extracted_at, quote_block_id",
        (str(run_id),),
    ).fetchall()
    if not candidate_rows:
        return ()

    quote_ids = tuple(row["quote_block_id"] for row in candidate_rows)
    ledger_rows = _group_rows_by_quote(
        _bounded_rows(connection, "ledger_records", "quote_block_id", quote_ids, run_id),
        "quote_block_id",
    )
    snapshot_rows = _rows_by_id(
        _bounded_rows(
            connection,
            "snapshots",
            "snapshot_id",
            tuple(
                dict.fromkeys(
                    [row["snapshot_id"] for row in candidate_rows]
                    + [ledger["snapshot_id"] for rows in ledger_rows.values() for ledger in rows]
                )
            ),
            run_id=None,
        ),
        "snapshot_id",
    )
    snapshots = {
        snapshot_id: artifact_store._row_to_snapshot(row)
        for snapshot_id, row in snapshot_rows.items()
    }
    analyst_rows = _rows_by_quote(
        _bounded_rows(connection, "analyst_decisions", "quote_block_id", quote_ids, run_id),
        "quote_block_id",
    )
    draft_rows = _group_rows_by_quote(
        _bounded_rows(connection, "statement_drafts", "quote_block_id", quote_ids, run_id),
        "quote_block_id",
    )
    review_rows = _group_rows_by_quote(
        _bounded_rows(connection, "statement_review_attempts", "quote_block_id", quote_ids, run_id),
        "quote_block_id",
    )
    try:
        contract = artifact_store.read_provider_run_contract(connection, run_id)
    except KeyError:
        contract = None

    trails: list[EvidenceTrailItem] = []
    for row in candidate_rows:
        candidate = artifact_store._row_to_candidate(row)
        snapshot_row = snapshots.get(str(candidate.snapshot_id))
        if snapshot_row is None:
            raise EvidenceBrowserError(f"candidate {candidate.quote_block_id} has no snapshot")
        snapshot = snapshot_row
        quote_id = str(candidate.quote_block_id)
        analyst_row = analyst_rows.get(quote_id)
        analyst = (
            artifact_store._row_to_score_decision(analyst_row) if analyst_row is not None else None
        )
        drafts = tuple(
            artifact_store._row_to_statement_draft(item) for item in draft_rows.get(quote_id, ())
        )
        reviews = tuple(
            artifact_store._row_to_review_result(item) for item in review_rows.get(quote_id, ())
        )
        try:
            _validate_trail_links(run_id, candidate, snapshot, analyst, drafts, reviews)
        except ValueError as exc:
            compatibility_issues.append(
                RecordCompatibilityResult(
                    record_key=quote_id,
                    artifact_type="CandidateQuoteBlock",
                    message=f"stored evidence provenance/hash mismatch: {exc}",
                )
            )
            continue
        ledger = _decode_ledger(
            ledger_rows.get(quote_id, ()),
            contract,
            snapshots,
            compatibility_issues,
            candidate,
            reviews,
        )
        released = bool(validation and validation.valid and ledger)
        trails.append(
            EvidenceTrailItem(
                candidate=candidate,
                snapshot=snapshot,
                analyst_decision=analyst,
                statement_drafts=drafts,
                reviewer_decisions=reviews,
                ledger_records=ledger,
                final_validation_present=validation is not None,
                released=released,
                artifact_label=_artifact_label(analyst, reviews, released),
            )
        )
    return tuple(trails)


def _validate_trail_links(
    run_id: UUID,
    candidate: CandidateQuoteBlock,
    snapshot: SourceSnapshot,
    analyst: ScoreDecision | None,
    drafts: tuple[StatementDraft, ...],
    reviews: tuple[StatementReviewResult, ...],
) -> None:
    """Verify saved source relationships without imposing new admission/scoring policy."""
    validate_snapshot_integrity(snapshot)
    if (
        candidate.run_id != run_id
        or snapshot.run_id != run_id
        or any(
            getattr(candidate, field) != getattr(snapshot, snapshot_field)
            for field, snapshot_field in (
                ("snapshot_id", "snapshot_id"),
                ("snapshot_sha256", "snapshot_sha256"),
                ("retrieval_attempt_id", "retrieval_attempt_id"),
                ("source_url", "source_url"),
                ("retrieved_at", "retrieved_at"),
                ("snapshot_created_at", "created_at"),
                ("truncated", "truncated"),
            )
        )
    ):
        raise ValueError("candidate/snapshot provenance mismatch")
    parsed = parse_extracted_quote_block(candidate.extracted_quote_block)
    if len(parsed.segments) != len(candidate.segment_offsets) or any(
        snapshot.normalized_text[offset.start_char : offset.end_char] != segment
        for segment, offset in zip(parsed.segments, candidate.segment_offsets, strict=True)
    ):
        raise ValueError("candidate quotation differs from its exact snapshot offsets")
    validate_bracket_context(
        snapshot,
        parsed,
        candidate.segment_offsets,
        fresh_sentences=candidate.post_filter_version == FRESH_QUOTE_CONTEXT_FILTER_VERSION,
    )
    for record in (*((analyst,) if analyst is not None else ()), *drafts, *reviews):
        if record.run_id != run_id or record.quote_block_id != candidate.quote_block_id:
            raise ValueError("evidence decision belongs to another run or quotation")
    drafts_by_id = {draft.statement_draft_id: draft for draft in drafts}
    for review in reviews:
        draft = drafts_by_id.get(review.statement_draft_id)
        if draft is None or (
            review.approved and review.approved_factual_statement != draft.draft_statement
        ):
            raise ValueError("Reviewer decision differs from its original statement draft")


_BROWSER_QUERY_CHUNK_SIZE = 500


def _bounded_rows(
    connection: sqlite3.Connection,
    table: str,
    key_column: str,
    keys: tuple[str, ...],
    run_id: UUID | None,
) -> tuple[sqlite3.Row, ...]:
    """Read only selected IDs, with headroom below old SQLite bind limits."""
    if not keys:
        return ()
    rows: list[sqlite3.Row] = []
    for offset in range(0, len(keys), _BROWSER_QUERY_CHUNK_SIZE):
        chunk = keys[offset : offset + _BROWSER_QUERY_CHUNK_SIZE]
        marks = ", ".join("?" for _ in chunk)
        if run_id is None:
            query = f"SELECT * FROM {table} WHERE {key_column} IN ({marks})"
            parameters: tuple[object, ...] = chunk
        else:
            order_by = {
                "analyst_decisions": "",
                "statement_drafts": " ORDER BY quote_block_id, drafted_at",
                "statement_review_attempts": (
                    " ORDER BY quote_block_id, reviewed_at, statement_draft_id"
                ),
                "ledger_records": " ORDER BY quote_block_id, ledger_claim_id",
            }[table]
            query = (
                f"SELECT * FROM {table} WHERE run_id = ? AND {key_column} IN ({marks}){order_by}"
            )
            parameters = (str(run_id), *chunk)
        rows.extend(artifact_store._read_execute(connection, query, parameters).fetchall())
    return tuple(rows)


def _rows_by_id(rows: tuple[sqlite3.Row, ...], key: str) -> dict[str, sqlite3.Row]:
    return {row[key]: row for row in rows}


def _rows_by_quote(rows: tuple[sqlite3.Row, ...], key: str) -> dict[str, sqlite3.Row]:
    return _rows_by_id(rows, key)


def _group_rows_by_quote(
    rows: tuple[sqlite3.Row, ...], key: str
) -> dict[str, tuple[sqlite3.Row, ...]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return {quote_id: tuple(items) for quote_id, items in grouped.items()}


def _decode_ledger(
    rows: tuple[sqlite3.Row, ...],
    contract: ProviderRunContract | None,
    snapshots: dict[str, SourceSnapshot],
    compatibility_issues: list[RecordCompatibilityResult],
    candidate: CandidateQuoteBlock,
    reviews: tuple[StatementReviewResult, ...],
) -> tuple[LedgerRecord | AugustLedgerRecord, ...]:
    records: list[LedgerRecord | AugustLedgerRecord] = []
    for row in rows:
        try:
            record = artifact_store._row_to_ledger_record(row, contract)
            snapshot = snapshots.get(str(record.snapshot_id))
            try:
                if snapshot is None:
                    raise ValueError("Ledger has no snapshot")
                validate_snapshot_integrity(snapshot)
                if (
                    record.run_id != candidate.run_id
                    or snapshot.run_id != candidate.run_id
                    or record.quote_block_id != candidate.quote_block_id
                    or (
                        not isinstance(record, HistoricalRead)
                        and record.snapshot_id != candidate.snapshot_id
                    )
                    or record.retrieval_attempt_id != snapshot.retrieval_attempt_id
                    or record.snapshot_sha256 != snapshot.snapshot_sha256
                    or record.snapshot_sha256 != candidate.snapshot_sha256
                    or record.source_url != snapshot.source_url
                    or record.source_url != candidate.source_url
                    or record.stance != candidate.stance
                    or tuple(record.segment_offsets) != tuple(candidate.segment_offsets)
                    or record.approved_claim_text != candidate.extracted_quote_block
                ):
                    raise ValueError("Ledger source/quotation provenance mismatch")
                if not any(
                    review.approved
                    and review.reviewer_approval_id == record.reviewer_approval_id
                    and review.approved_factual_statement == record.approved_factual_statement
                    for review in reviews
                ):
                    raise ValueError("Ledger statement differs from its original approved review")
            except ValueError as exc:
                raise RecordCompatibilityError(
                    RecordCompatibilityResult(
                        record_key=str(record.ledger_claim_id),
                        artifact_type="LedgerRecord",
                        message=f"stored Ledger provenance/hash mismatch: {exc}",
                    )
                ) from exc
            records.append(record)
        except RecordCompatibilityError as exc:
            compatibility_issues.append(exc.result)
    return tuple(records)


def _artifact_label(
    analyst: ScoreDecision | None, reviews: tuple[StatementReviewResult, ...], released: bool
) -> str:
    if released:
        return "Released factual evidence"
    if any(not review.approved for review in reviews):
        return "Rejected by Reviewer — not released"
    if analyst is not None and not analyst.approved:
        return "Rejected by Analyst — not released"
    return "Not released"


def _matches(trail: EvidenceTrailItem, filters: EvidenceBrowserFilter) -> bool:
    if filters.stance is not None and trail.candidate.stance.value != filters.stance:
        return False
    if filters.source_url is not None and trail.candidate.source_url != filters.source_url:
        return False
    if filters.released is not None and trail.released != filters.released:
        return False
    if filters.approved is not None:
        # This filter means an explicit outcome at either persisted stage.
        # A missing Analyst/Reviewer decision remains pending.
        decisions = (trail.analyst_decision.approved,) if trail.analyst_decision else ()
        decisions += tuple(review.approved for review in trail.reviewer_decisions)
        if filters.approved not in decisions:
            return False
    if filters.stage is not None and not _has_stage(trail, filters.stage):
        return False
    return True


def _has_stage(trail: EvidenceTrailItem, stage: EvidenceStage) -> bool:
    return {
        EvidenceStage.CANDIDATE: True,
        EvidenceStage.ANALYST: trail.analyst_decision is not None,
        EvidenceStage.REVIEWER: bool(trail.reviewer_decisions),
        EvidenceStage.LEDGER: bool(trail.ledger_records),
        EvidenceStage.VALIDATION: trail.final_validation_present,
    }[stage]


def _matches_mvp10(entry: EvidenceTrailEntry, filters: EvidenceBrowserFilter) -> bool:
    if filters.outcome is not None and entry.outcome is not filters.outcome:
        return False
    if filters.role is not None and entry.role is not filters.role:
        return False
    if filters.research_round is not None and entry.research_round.value != filters.research_round:
        return False
    if filters.cost_incurred is not None and entry.cost_incurred != filters.cost_incurred:
        return False
    return True


def _released_traces(
    trails: tuple[EvidenceTrailItem, ...], validation: ValidationResult | None
) -> tuple[ReleasedStatementTrace, ...]:
    if validation is None or not validation.valid:
        return ()
    traces: list[ReleasedStatementTrace] = []
    for trail in trails:
        for ledger in trail.ledger_records:
            review = next(
                (
                    item
                    for item in trail.reviewer_decisions
                    if item.approved and item.reviewer_approval_id == ledger.reviewer_approval_id
                ),
                None,
            )
            if review is None:
                raise EvidenceBrowserError(
                    f"ledger record {ledger.ledger_claim_id} has no matching approved review"
                )
            traces.append(
                ReleasedStatementTrace(
                    ledger_record=ledger,
                    reviewer_decision=review,
                    candidate=trail.candidate,
                    snapshot=trail.snapshot,
                    final_validation=validation,
                )
            )
    return tuple(traces)
