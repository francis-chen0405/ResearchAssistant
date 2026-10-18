"""Captured evidence, admission/Ledger and immutable released-output persistence."""

from __future__ import annotations

import json
import sqlite3
from uuid import UUID

from researchassistant.contracts.models import (
    BRIEF_TITLE,
    CLAIM_LABEL,
    RELEASE_SECTION_HEADINGS,
    CandidateQuoteBlock,
    LedgerRecord,
    MediaTypeProvenance,
    ModelInvocationRecord,
    ProviderRunContract,
    ProvisionalCandidate,
    RetrievalRecord,
    ScoreDecision,
    SourceSnapshot,
    StatementDraft,
    StatementReviewResult,
    SynthesisItem,
    SynthesisOutput,
    SynthesisSection,
    ValidationError,
    ValidationResult,
)
from researchassistant.storage.checkpoint_store import (
    read_provider_run_contract as read_provider_run_contract,
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
    _json_to_offsets as _json_to_offsets,
)
from researchassistant.storage.store_types import (
    _offsets_to_json as _offsets_to_json,
)
from researchassistant.storage.store_types import (
    _read_execute as _read_execute,
)


def insert_retrieval_attempt(
    db_path: str, record: RetrievalRecord, *, _connect: WriteConnectionFactory
) -> None:
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


def read_retrieval_attempt(
    db_path: DatabaseReader, retrieval_attempt_id: UUID, *, _read_connection: ReadConnectionFactory
) -> RetrievalRecord:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
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


def insert_snapshot(
    db_path: str, snapshot: SourceSnapshot, *, _connect: WriteConnectionFactory
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO snapshots
               (snapshot_id, run_id, retrieval_attempt_id, source_url, retrieved_at,
                normalized_text, snapshot_sha256, word_count, truncated, created_at,
                original_url, canonical_url, normalization_version, acquisition_version,
                provider_name, provider_version, media_type_provenance_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                snapshot.original_url,
                snapshot.canonical_url,
                snapshot.normalization_version,
                snapshot.acquisition_version,
                snapshot.provider_name,
                snapshot.provider_version,
                json.dumps(
                    snapshot.media_type_provenance.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_snapshot(
    db_path: DatabaseReader, snapshot_id: UUID, *, _read_connection: ReadConnectionFactory
) -> SourceSnapshot:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn, "SELECT * FROM snapshots WHERE snapshot_id = ?", (str(snapshot_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"snapshot {snapshot_id} not found")
        return _row_to_snapshot(row)


def _row_to_snapshot(row: sqlite3.Row) -> SourceSnapshot:
    return SourceSnapshot(
        run_id=UUID(row["run_id"]),
        retrieval_attempt_id=UUID(row["retrieval_attempt_id"]),
        snapshot_id=UUID(row["snapshot_id"]),
        source_url=row["source_url"],
        original_url=row["original_url"],
        canonical_url=row["canonical_url"],
        retrieved_at=_iso_to_dt(row["retrieved_at"]),
        normalized_text=row["normalized_text"],
        snapshot_sha256=row["snapshot_sha256"],
        word_count=row["word_count"],
        truncated=bool(row["truncated"]),
        normalization_version=row["normalization_version"],
        acquisition_version=row["acquisition_version"],
        provider_name=row["provider_name"],
        provider_version=row["provider_version"],
        media_type_provenance=(
            MediaTypeProvenance.model_validate_json(row["media_type_provenance_json"])
            if row["media_type_provenance_json"] is not None
            else MediaTypeProvenance()
        ),
        created_at=_iso_to_dt(row["created_at"]),
    )


def insert_provisional_extraction(
    db_path: str, prov: ProvisionalCandidate, *, _connect: WriteConnectionFactory
) -> None:
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


def read_provisional_extractions(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> list[ProvisionalCandidate]:
    with _read_connection(db_path) as conn:
        rows = _read_execute(
            conn,
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


def insert_candidate(
    db_path: str, candidate: CandidateQuoteBlock, *, _connect: WriteConnectionFactory
) -> None:
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


def read_candidate(
    db_path: DatabaseReader, quote_block_id: UUID, *, _read_connection: ReadConnectionFactory
) -> CandidateQuoteBlock:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn, "SELECT * FROM candidates WHERE quote_block_id = ?", (str(quote_block_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"candidate {quote_block_id} not found")
        return _row_to_candidate(row)


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


def insert_analyst_decision(
    db_path: str, decision: ScoreDecision, *, _connect: WriteConnectionFactory
) -> None:
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


def read_analyst_decision(
    db_path: DatabaseReader,
    run_id: UUID,
    quote_block_id: UUID,
    *,
    _read_connection: ReadConnectionFactory,
) -> ScoreDecision:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT * FROM analyst_decisions WHERE run_id = ? AND quote_block_id = ?",
            (str(run_id), str(quote_block_id)),
        ).fetchone()
        if row is None:
            raise KeyError(f"analyst decision for run={run_id} quote={quote_block_id} not found")
        return _row_to_score_decision(row)


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


def insert_statement_draft(
    db_path: str, draft: StatementDraft, *, _connect: WriteConnectionFactory
) -> None:
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


def read_statement_draft(
    db_path: DatabaseReader, statement_draft_id: UUID, *, _read_connection: ReadConnectionFactory
) -> StatementDraft:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT * FROM statement_drafts WHERE statement_draft_id = ?",
            (str(statement_draft_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"statement draft {statement_draft_id} not found")
        return _row_to_statement_draft(row)


def _row_to_statement_draft(row: sqlite3.Row) -> StatementDraft:
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


def insert_statement_review(
    db_path: str, review: StatementReviewResult, *, _connect: WriteConnectionFactory
) -> None:
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
    db_path: DatabaseReader,
    run_id: UUID,
    statement_draft_id: UUID,
    *,
    _read_connection: ReadConnectionFactory,
) -> StatementReviewResult:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            """SELECT * FROM statement_review_attempts
               WHERE run_id = ? AND statement_draft_id = ?""",
            (str(run_id), str(statement_draft_id)),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"statement review for run={run_id} draft={statement_draft_id} not found"
            )
        return _row_to_review_result(row)


def _row_to_review_result(row: sqlite3.Row) -> StatementReviewResult:
    return StatementReviewResult(
        run_id=UUID(row["run_id"]),
        statement_draft_id=UUID(row["statement_draft_id"]),
        quote_block_id=UUID(row["quote_block_id"]),
        approved=bool(row["approved"]),
        reviewer_approval_id=row["reviewer_approval_id"],
        approved_factual_statement=row["approved_factual_statement"],
        failure_code=row["failure_code"],
        rationale=row["rationale"],
        reviewer_prompt_version=row["reviewer_prompt_version"],
        reviewer_model_name=row["reviewer_model_name"],
        reviewed_at=_iso_to_dt(row["reviewed_at"]),
    )


def insert_ledger_record(
    db_path: str, record: LedgerRecord, *, _connect: WriteConnectionFactory
) -> None:
    # Inspection types and forged model_copy values never authorize a fresh admission.
    record = LedgerRecord.model_validate(record.model_dump())
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


def read_ledger_record(
    db_path: DatabaseReader, ledger_claim_id: UUID, *, _read_connection: ReadConnectionFactory
) -> LedgerRecord:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
            "SELECT * FROM ledger_records WHERE ledger_claim_id = ?",
            (str(ledger_claim_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"ledger record {ledger_claim_id} not found")
        try:
            contract = read_provider_run_contract(
                conn, UUID(row["run_id"]), _read_connection=_read_connection
            )
        except KeyError:
            contract = None
        record = _row_to_ledger_record(row, contract)
        from researchassistant.contracts.historical import HistoricalRead
        from researchassistant.storage.historical_decode import verify_historical_snapshot

        if isinstance(record, HistoricalRead):
            verify_historical_snapshot(
                record, read_snapshot(conn, record.snapshot_id, _read_connection=_read_connection)
            )
        return record


def _row_to_ledger_record(
    row: sqlite3.Row,
    contract: ProviderRunContract | None = None,
) -> LedgerRecord:
    from researchassistant.storage.historical_decode import decode_ledger

    return decode_ledger(
        dict(
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
            reviewer_approval_id=row["reviewer_approval_id"],
            ledger_validated_at=_iso_to_dt(row["ledger_validated_at"]),
        ),
        contract,
    )


def insert_synthesis(
    db_path: str, synthesis: SynthesisOutput, *, _connect: WriteConnectionFactory
) -> None:
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
                BRIEF_TITLE,
                CLAIM_LABEL,
            ),
        )
        for sec_idx, section in enumerate(synthesis.sections):
            conn.execute(
                """INSERT INTO synthesis_sections
                   (run_id, section_type, heading, section_order)
                   VALUES (?, ?, ?, ?)""",
                (
                    str(synthesis.run_id),
                    section.section_type.value,
                    RELEASE_SECTION_HEADINGS.get(section.section_type, section.section_type.value),
                    sec_idx,
                ),
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


def read_synthesis(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> SynthesisOutput:
    with _read_connection(db_path) as conn:
        sa_row = _read_execute(
            conn, "SELECT * FROM synthesis_attempts WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if sa_row is None:
            raise KeyError(f"synthesis for run {run_id} not found")

        sec_rows = _read_execute(
            conn,
            "SELECT * FROM synthesis_sections WHERE run_id = ? ORDER BY section_order",
            (str(run_id),),
        ).fetchall()
        sections: list[SynthesisSection] = []
        for sec_row in sec_rows:
            item_rows = _read_execute(
                conn,
                """SELECT * FROM synthesis_items
                   WHERE run_id = ? AND section_order = ? ORDER BY item_order""",
                (str(run_id), sec_row["section_order"]),
            ).fetchall()
            items = [
                SynthesisItem(
                    connective_template_id=r["connective_template_id"],
                    ledger_claim_id=UUID(r["ledger_claim_id"]),
                    reviewer_approval_id=r["reviewer_approval_id"],
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
                    items=items,
                )
            )

        return SynthesisOutput(
            run_id=UUID(sa_row["run_id"]),
            synthesizer_prompt_version=sa_row["synthesizer_prompt_version"],
            synthesizer_model_name=sa_row["synthesizer_model_name"],
            created_at=_iso_to_dt(sa_row["created_at"]),
            sections=sections,
        )


def insert_validation(
    db_path: str, result: ValidationResult, *, _connect: WriteConnectionFactory
) -> None:
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


def read_validation(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> ValidationResult:
    with _read_connection(db_path) as conn:
        vr_row = _read_execute(
            conn, "SELECT * FROM validation_runs WHERE run_id = ?", (str(run_id),)
        ).fetchone()
        if vr_row is None:
            raise KeyError(f"validation for run {run_id} not found")

        err_rows = _read_execute(
            conn,
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


def insert_model_invocation(
    db_path: str, record: ModelInvocationRecord, *, _connect: WriteConnectionFactory
) -> None:
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


def read_model_invocation(
    db_path: DatabaseReader, invocation_id: UUID, *, _read_connection: ReadConnectionFactory
) -> ModelInvocationRecord:
    with _read_connection(db_path) as conn:
        row = _read_execute(
            conn,
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
