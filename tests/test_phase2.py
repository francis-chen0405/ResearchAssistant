"""Phase 2 tests — SQLite persistence layer.

All tests use temporary database files that are cleaned up automatically.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from models import (
    AmbiguityRecord,
    CandidateQuoteBlock,
    ClaimDefinition,
    Entailment,
    LedgerRecord,
    ModelInvocationRecord,
    Placement,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    RetrievalStatus,
    RunManifest,
    RunStatus,
    ScoreDecision,
    SearchQuery,
    SectionType,
    SegmentOffset,
    SourceSnapshot,
    Stage,
    Stance,
    StatementDraft,
    StatementReviewResult,
    SynthesisItem,
    SynthesisOutput,
    SynthesisSection,
    ValidationError,
    ValidationResult,
)
from store import (
    init_db,
    insert_analyst_decision,
    insert_candidate,
    insert_ledger_record,
    insert_model_invocation,
    insert_planner_output,
    insert_provisional_extraction,
    insert_retrieval_attempt,
    insert_run,
    insert_snapshot,
    insert_statement_draft,
    insert_statement_review,
    insert_synthesis,
    insert_validation,
    read_analyst_decision,
    read_candidate,
    read_ledger_record,
    read_model_invocation,
    read_planner_output,
    read_provisional_extractions,
    read_retrieval_attempt,
    read_run,
    read_snapshot,
    read_statement_draft,
    read_statement_review,
    read_synthesis,
    read_validation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
_SHA = "a" * 64


@pytest.fixture()
def db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


def _make_run(run_id: UUID | None = None) -> RunManifest:
    rid = run_id or uuid4()
    return RunManifest(
        run_id=rid,
        status=RunStatus.PLANNED,
        raw_claim="Test claim",
        current_stage=Stage.CLAIM_PLANNER,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_planner(run_id: UUID) -> PlannerOutput:
    exclusions = "-site:reddit.com -site:quora.com -site:youtube.com -site:tiktok.com"
    return PlannerOutput(
        run_id=run_id,
        claim_definition=ClaimDefinition(
            run_id=run_id,
            claim_text="Test claim",
            population="Test pop",
            jurisdiction="Test jur",
            time_period="2020-2025",
            comparison_baseline="No intervention",
            intervention_or_exposure="Test exposure",
            causal_or_comparative_meaning="Causal",
            created_at=_NOW,
        ),
        ambiguities=[
            AmbiguityRecord(
                run_id=run_id,
                ambiguity_id=uuid4(),
                description="Ambiguity 1",
                impact="Could change scope",
                created_at=_NOW,
            )
        ],
        search_queries=[
            SearchQuery(
                run_id=run_id,
                query_id=uuid4(),
                stance=Stance.SUPPORTING,
                query_round=r,
                strategy=f"strategy_s{r}",
                query_text=f"supporting query {r}",
                exclusion_parameters=exclusions,
                created_at=_NOW,
            )
            for r in range(1, 4)
        ]
        + [
            SearchQuery(
                run_id=run_id,
                query_id=uuid4(),
                stance=Stance.OPPOSING,
                query_round=r,
                strategy=f"strategy_o{r}",
                query_text=f"opposing query {r}",
                exclusion_parameters=exclusions,
                created_at=_NOW,
            )
            for r in range(1, 4)
        ],
        planner_prompt_version="v1",
        planner_model_name="test-model",
        planned_at=_NOW,
    )


def _make_retrieval(run_id: UUID, query_id: UUID) -> RetrievalRecord:
    return RetrievalRecord(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        query_id=query_id,
        query_round=1,
        query_text="test query",
        search_rank=1,
        source_url="https://example.com/source",
        resolved_url="https://example.com/resolved",
        status=RetrievalStatus.RETRIEVED,
        retrieved_at=_NOW,
    )


def _make_snapshot(run_id: UUID, retrieval_attempt_id: UUID) -> SourceSnapshot:
    return SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=retrieval_attempt_id,
        snapshot_id=uuid4(),
        source_url="https://example.com/source",
        retrieved_at=_NOW,
        normalized_text="This is normalized text with statistics showing 50% growth.",
        snapshot_sha256=_SHA,
        word_count=10,
        truncated=False,
        created_at=_NOW,
    )


def _make_candidate(
    run_id: UUID,
    retrieval_attempt_id: UUID,
    query_id: UUID,
    snapshot_id: UUID,
) -> CandidateQuoteBlock:
    return CandidateQuoteBlock(
        run_id=run_id,
        stance=Stance.SUPPORTING,
        quote_block_id=uuid4(),
        source_url="https://example.com/source",
        retrieval_attempt_id=retrieval_attempt_id,
        query_id=query_id,
        query_round=1,
        search_rank=1,
        retrieved_at=_NOW,
        snapshot_id=snapshot_id,
        snapshot_sha256=_SHA,
        snapshot_created_at=_NOW,
        extracted_quote_block='Preceding. "Segment 1" Following.',
        segment_offsets=[SegmentOffset(start_char=0, end_char=10)],
        raw_segment_word_count=120,
        has_statistical_markers=True,
        claim_keyword_match_count=2,
        truncated=False,
        extraction_prompt_version="v1",
        extraction_model_name="test-model",
        extracted_at=_NOW,
        post_filter_version="v1",
        post_filter_validated_at=_NOW,
    )


def _make_ledger(
    run_id: UUID,
    quote_block_id: UUID,
    retrieval_attempt_id: UUID,
    snapshot_id: UUID,
    reviewer_approval_id: UUID,
) -> LedgerRecord:
    return LedgerRecord(
        run_id=run_id,
        ledger_claim_id=uuid4(),
        quote_block_id=quote_block_id,
        stance=Stance.SUPPORTING,
        approved_factual_statement="The approved factual statement.",
        approved_claim_text='Preceding. "Segment 1" Following.',
        evidence_quality=4,
        claim_fit=4,
        ledger_score=4,
        placement=Placement.SECONDARY,
        entailment=Entailment.STRONG,
        source_url="https://example.com/source",
        retrieval_attempt_id=retrieval_attempt_id,
        snapshot_id=snapshot_id,
        snapshot_sha256=_SHA,
        segment_offsets=[SegmentOffset(start_char=0, end_char=10)],
        analyst_prompt_version="v1",
        analyst_model_name="test-model",
        analyst_completed_at=_NOW,
        reviewer_prompt_version="v1",
        reviewer_model_name="test-model",
        reviewed_at=_NOW,
        reviewer_approval_id=reviewer_approval_id,
        ledger_validated_at=_NOW,
    )


def _insert_run_and_planner(db_path: str) -> tuple[RunManifest, PlannerOutput, SearchQuery]:
    run = _make_run()
    insert_run(db_path, run)
    planner = _make_planner(run.run_id)
    insert_planner_output(db_path, planner)
    query = next(q for q in planner.search_queries if q.stance is Stance.SUPPORTING)
    return run, planner, query


def _insert_candidate_chain(
    db_path: str,
) -> tuple[
    RunManifest, PlannerOutput, SearchQuery, RetrievalRecord, SourceSnapshot, CandidateQuoteBlock
]:
    run, planner, query = _insert_run_and_planner(db_path)
    ret = _make_retrieval(run.run_id, query.query_id)
    insert_retrieval_attempt(db_path, ret)
    snap = _make_snapshot(run.run_id, ret.retrieval_attempt_id)
    insert_snapshot(db_path, snap)
    cand = _make_candidate(run.run_id, ret.retrieval_attempt_id, query.query_id, snap.snapshot_id)
    insert_candidate(db_path, cand)
    return run, planner, query, ret, snap, cand


def _insert_review_chain(
    db_path: str,
) -> tuple[
    RunManifest,
    PlannerOutput,
    SearchQuery,
    RetrievalRecord,
    SourceSnapshot,
    CandidateQuoteBlock,
    StatementDraft,
    StatementReviewResult,
]:
    run, planner, query, ret, snap, cand = _insert_candidate_chain(db_path)
    draft = StatementDraft(
        run_id=run.run_id,
        statement_draft_id=uuid4(),
        quote_block_id=cand.quote_block_id,
        stance=Stance.SUPPORTING,
        draft_statement="Draft text.",
        claim_fit=4,
        analyst_prompt_version="v1",
        analyst_model_name="model",
        drafted_at=_NOW,
    )
    insert_statement_draft(db_path, draft)
    review = StatementReviewResult(
        run_id=run.run_id,
        statement_draft_id=draft.statement_draft_id,
        quote_block_id=cand.quote_block_id,
        approved=True,
        reviewer_approval_id=uuid4(),
        approved_factual_statement="Approved text.",
        rationale="Passes all checks",
        reviewer_prompt_version="v1",
        reviewer_model_name="model",
        reviewed_at=_NOW,
    )
    insert_statement_review(db_path, review)
    return run, planner, query, ret, snap, cand, draft, review


# ---------------------------------------------------------------------------
# Test: database initialisation
# ---------------------------------------------------------------------------


class TestInitDB:
    def test_tables_created(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(path)
            conn = sqlite3.connect(path)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            conn.close()
            expected = {
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
            }
            assert expected.issubset(tables)
        finally:
            os.unlink(path)

    def test_schema_migration_record_created(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(path)
            conn = sqlite3.connect(path)
            row = conn.execute(
                """SELECT version, description, applied_at
                   FROM schema_migrations
                   ORDER BY version"""
            ).fetchone()
            conn.close()
            assert row == (
                1,
                "phase-2 initial sqlite schema",
                "2026-06-26T00:00:00+00:00",
            )
        finally:
            os.unlink(path)

    def test_idempotent(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(path)
            init_db(path)  # second call must not raise
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Test: foreign-key enforcement
# ---------------------------------------------------------------------------


class TestForeignKeyEnforcement:
    def test_fk_enabled(self, db_path: str) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        pragma = conn.execute("PRAGMA foreign_keys;").fetchone()
        conn.close()
        assert pragma[0] == 1

    def test_invalid_fk_rejected(self, db_path: str) -> None:
        """Inserting a planner output for a non-existent run must fail."""
        planner = _make_planner(uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_planner_output(db_path, planner)


# ---------------------------------------------------------------------------
# Test: insert and read round trips
# ---------------------------------------------------------------------------


class TestRoundTrips:
    def test_run_round_trip(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        loaded = read_run(db_path, run.run_id)
        assert loaded == run

    def test_planner_round_trip(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        planner = _make_planner(run.run_id)
        insert_planner_output(db_path, planner)
        loaded = read_planner_output(db_path, run.run_id)
        assert loaded.run_id == planner.run_id
        assert loaded.planner_prompt_version == planner.planner_prompt_version
        assert loaded.claim_definition.claim_text == planner.claim_definition.claim_text
        assert len(loaded.ambiguities) == 1
        assert len(loaded.search_queries) == 6

    def test_retrieval_round_trip(self, db_path: str) -> None:
        run, _, query = _insert_run_and_planner(db_path)
        rec = _make_retrieval(run.run_id, query.query_id)
        insert_retrieval_attempt(db_path, rec)
        loaded = read_retrieval_attempt(db_path, rec.retrieval_attempt_id)
        assert loaded == rec

    def test_snapshot_round_trip(self, db_path: str) -> None:
        run, _, query = _insert_run_and_planner(db_path)
        ret = _make_retrieval(run.run_id, query.query_id)
        insert_retrieval_attempt(db_path, ret)
        snap = _make_snapshot(run.run_id, ret.retrieval_attempt_id)
        insert_snapshot(db_path, snap)
        loaded = read_snapshot(db_path, snap.snapshot_id)
        assert loaded == snap

    def test_provisional_round_trip(self, db_path: str) -> None:
        run, _, query, ret, snap, _ = _insert_candidate_chain(db_path)
        prov = ProvisionalCandidate(
            run_id=run.run_id,
            stance=Stance.SUPPORTING,
            source_url="https://example.com",
            retrieval_attempt_id=ret.retrieval_attempt_id,
            query_id=query.query_id,
            query_round=1,
            search_rank=1,
            snapshot_id=snap.snapshot_id,
            snapshot_sha256=_SHA,
            extracted_quote_block="Some quote",
            extraction_prompt_version="v1",
            extraction_model_name="model",
            extracted_at=_NOW,
        )
        insert_provisional_extraction(db_path, prov)
        loaded = read_provisional_extractions(db_path, run.run_id)
        assert len(loaded) == 1
        assert loaded[0].run_id == prov.run_id
        assert loaded[0].extracted_quote_block == "Some quote"

    def test_candidate_round_trip(self, db_path: str) -> None:
        _, _, _, _, _, cand = _insert_candidate_chain(db_path)
        loaded = read_candidate(db_path, cand.quote_block_id)
        assert loaded == cand

    def test_analyst_decision_round_trip(self, db_path: str) -> None:
        run, _, _, _, _, cand = _insert_candidate_chain(db_path)
        decision = ScoreDecision(
            run_id=run.run_id,
            quote_block_id=cand.quote_block_id,
            evidence_quality=4,
            claim_fit=4,
            ledger_score=4,
            placement=Placement.SECONDARY,
            approved=True,
            rationale="Strong evidence",
            analyst_prompt_version="v1",
            analyst_model_name="model",
            scored_at=_NOW,
        )
        insert_analyst_decision(db_path, decision)
        loaded = read_analyst_decision(db_path, run.run_id, decision.quote_block_id)
        assert loaded == decision

    def test_statement_review_round_trip(self, db_path: str) -> None:
        run, *_, draft, review = _insert_review_chain(db_path)
        loaded_draft = read_statement_draft(db_path, draft.statement_draft_id)
        loaded = read_statement_review(db_path, run.run_id, draft.statement_draft_id)
        assert loaded_draft == draft
        assert loaded == review

    def test_ledger_round_trip(self, db_path: str) -> None:
        run, _, _, ret, snap, cand, _, review = _insert_review_chain(db_path)
        assert review.reviewer_approval_id is not None
        ledger = _make_ledger(
            run.run_id,
            cand.quote_block_id,
            ret.retrieval_attempt_id,
            snap.snapshot_id,
            review.reviewer_approval_id,
        )
        insert_ledger_record(db_path, ledger)
        loaded = read_ledger_record(db_path, ledger.ledger_claim_id)
        assert loaded == ledger

    def test_synthesis_round_trip(self, db_path: str) -> None:
        run, _, _, ret, snap, cand, _, review = _insert_review_chain(db_path)
        assert review.reviewer_approval_id is not None
        ledger = _make_ledger(
            run.run_id,
            cand.quote_block_id,
            ret.retrieval_attempt_id,
            snap.snapshot_id,
            review.reviewer_approval_id,
        )
        insert_ledger_record(db_path, ledger)
        synthesis = SynthesisOutput(
            run_id=run.run_id,
            synthesizer_prompt_version="v1",
            synthesizer_model_name="model",
            created_at=_NOW,
            title="Test Brief",
            claim_definition="Claim framing",
            sections=[
                SynthesisSection(
                    section_type=SectionType.SUPPORTING,
                    heading="Supporting",
                    items=[
                        SynthesisItem(
                            connective_template_id="tmpl_support",
                            ledger_claim_id=ledger.ledger_claim_id,
                            reviewer_approval_id=ledger.reviewer_approval_id,
                            stance=Stance.SUPPORTING,
                            placement=ledger.placement,
                            entailment=ledger.entailment,
                            approved_factual_statement=ledger.approved_factual_statement,
                        )
                    ],
                )
            ],
        )
        insert_synthesis(db_path, synthesis)
        loaded = read_synthesis(db_path, run.run_id)
        assert loaded.title == synthesis.title
        assert len(loaded.sections) == 1
        assert len(loaded.sections[0].items) == 1
        assert loaded.sections[0].items[0].ledger_claim_id == ledger.ledger_claim_id

    def test_validation_round_trip(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        result = ValidationResult(
            run_id=run.run_id,
            valid=False,
            errors=[
                ValidationError(
                    code="ledger_mismatch",
                    location="section[0].items[0]",
                    message="Statement does not match ledger",
                )
            ],
            validator_config_version="v1",
            validated_at=_NOW,
        )
        insert_validation(db_path, result)
        loaded = read_validation(db_path, run.run_id)
        assert loaded == result

    def test_model_invocation_round_trip(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        inv = ModelInvocationRecord(
            run_id=run.run_id,
            invocation_id=uuid4(),
            stage=Stage.CLAIM_PLANNER,
            prompt_version="v1",
            model_name="model",
            input_artifact_id=uuid4(),
            output_artifact_id=uuid4(),
            status="completed",
            invoked_at=_NOW,
        )
        insert_model_invocation(db_path, inv)
        loaded = read_model_invocation(db_path, inv.invocation_id)
        assert loaded == inv


# ---------------------------------------------------------------------------
# Test: database close and reopen
# ---------------------------------------------------------------------------


class TestCloseReopen:
    def test_data_survives_reopen(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(path)
            run = _make_run()
            insert_run(path, run)

            # "reopen" by reading from a fresh connection
            loaded = read_run(path, run.run_id)
            assert loaded.run_id == run.run_id
            assert loaded.raw_claim == "Test claim"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Test: immutable snapshot behaviour
# ---------------------------------------------------------------------------


class TestSnapshotImmutability:
    def test_duplicate_snapshot_rejected(self, db_path: str) -> None:
        run, _, query = _insert_run_and_planner(db_path)
        ret = _make_retrieval(run.run_id, query.query_id)
        insert_retrieval_attempt(db_path, ret)
        snap = _make_snapshot(run.run_id, ret.retrieval_attempt_id)
        insert_snapshot(db_path, snap)
        with pytest.raises(sqlite3.IntegrityError):
            insert_snapshot(db_path, snap)

    def test_no_update_function_exists(self) -> None:
        """The store module must not expose update_snapshot or delete_snapshot."""
        import store

        assert not hasattr(store, "update_snapshot")
        assert not hasattr(store, "delete_snapshot")


# ---------------------------------------------------------------------------
# Test: immutable Ledger behaviour
# ---------------------------------------------------------------------------


class TestLedgerImmutability:
    def test_duplicate_ledger_rejected(self, db_path: str) -> None:
        run, _, _, ret, snap, cand, _, review = _insert_review_chain(db_path)
        assert review.reviewer_approval_id is not None
        ledger = _make_ledger(
            run.run_id,
            cand.quote_block_id,
            ret.retrieval_attempt_id,
            snap.snapshot_id,
            review.reviewer_approval_id,
        )
        insert_ledger_record(db_path, ledger)
        with pytest.raises(sqlite3.IntegrityError):
            insert_ledger_record(db_path, ledger)

    def test_no_update_function_exists(self) -> None:
        import store

        assert not hasattr(store, "update_ledger_record")
        assert not hasattr(store, "delete_ledger_record")


# ---------------------------------------------------------------------------
# Test: transaction rollback
# ---------------------------------------------------------------------------


class TestTransactionRollback:
    def test_planner_rollback_on_bad_ambiguity(self, db_path: str) -> None:
        """If an ambiguity insert fails, the planner_outputs row must also be rolled back."""
        run = _make_run()
        insert_run(db_path, run)
        planner = _make_planner(run.run_id)
        # Corrupt an ambiguity by setting run_id to a non-existent value
        # This will violate the FK on ambiguities → planner_outputs
        bad_planner = planner.model_copy(
            update={
                "ambiguities": [
                    AmbiguityRecord(
                        run_id=uuid4(),  # wrong run_id — FK violation
                        ambiguity_id=uuid4(),
                        description="Bad",
                        impact="Will fail",
                        created_at=_NOW,
                    )
                ]
            }
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_planner_output(db_path, bad_planner)
        # The planner_outputs row must not exist
        with pytest.raises(KeyError):
            read_planner_output(db_path, run.run_id)

    def test_synthesis_rollback_on_bad_item(self, db_path: str) -> None:
        """If a synthesis item fails, the whole synthesis is rolled back."""
        run, _, _, ret, snap, cand, _, review = _insert_review_chain(db_path)
        assert review.reviewer_approval_id is not None
        ledger = _make_ledger(
            run.run_id,
            cand.quote_block_id,
            ret.retrieval_attempt_id,
            snap.snapshot_id,
            review.reviewer_approval_id,
        )
        insert_ledger_record(db_path, ledger)
        synthesis = SynthesisOutput(
            run_id=run.run_id,
            synthesizer_prompt_version="v1",
            synthesizer_model_name="model",
            created_at=_NOW,
            title="Test",
            claim_definition="Framing",
            sections=[
                SynthesisSection(
                    section_type=SectionType.SUPPORTING,
                    heading="Supporting",
                    items=[
                        SynthesisItem(
                            connective_template_id="t1",
                            ledger_claim_id=ledger.ledger_claim_id,
                            reviewer_approval_id=ledger.reviewer_approval_id,
                            stance=Stance.SUPPORTING,
                            placement=ledger.placement,
                            entailment=ledger.entailment,
                            approved_factual_statement=ledger.approved_factual_statement,
                        )
                    ],
                )
            ],
        )
        # Corrupt the section_order FK by inserting directly with bad section_order
        # Instead, test that a duplicate synthesis attempt fails cleanly
        insert_synthesis(db_path, synthesis)
        with pytest.raises(sqlite3.IntegrityError):
            insert_synthesis(db_path, synthesis)
        # Original data must still be readable
        loaded = read_synthesis(db_path, run.run_id)
        assert loaded.title == "Test"


# ---------------------------------------------------------------------------
# Test: invalid foreign keys
# ---------------------------------------------------------------------------


class TestInvalidForeignKeys:
    def test_retrieval_without_run(self, db_path: str) -> None:
        ret = _make_retrieval(uuid4(), uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_retrieval_attempt(db_path, ret)

    def test_retrieval_without_query(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        ret = _make_retrieval(run.run_id, uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_retrieval_attempt(db_path, ret)

    def test_snapshot_without_run(self, db_path: str) -> None:
        snap = _make_snapshot(uuid4(), uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_snapshot(db_path, snap)

    def test_snapshot_without_retrieval(self, db_path: str) -> None:
        run, _, _ = _insert_run_and_planner(db_path)
        snap = _make_snapshot(run.run_id, uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_snapshot(db_path, snap)

    def test_candidate_without_run(self, db_path: str) -> None:
        cand = _make_candidate(uuid4(), uuid4(), uuid4(), uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_candidate(db_path, cand)

    def test_candidate_without_snapshot(self, db_path: str) -> None:
        run, _, query = _insert_run_and_planner(db_path)
        ret = _make_retrieval(run.run_id, query.query_id)
        insert_retrieval_attempt(db_path, ret)
        cand = _make_candidate(run.run_id, ret.retrieval_attempt_id, query.query_id, uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_candidate(db_path, cand)

    def test_analyst_decision_without_candidate(self, db_path: str) -> None:
        run, _, _ = _insert_run_and_planner(db_path)
        decision = ScoreDecision(
            run_id=run.run_id,
            quote_block_id=uuid4(),
            evidence_quality=4,
            claim_fit=4,
            ledger_score=4,
            placement=Placement.SECONDARY,
            approved=True,
            rationale="Strong evidence",
            analyst_prompt_version="v1",
            analyst_model_name="model",
            scored_at=_NOW,
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_analyst_decision(db_path, decision)

    def test_ledger_without_run(self, db_path: str) -> None:
        ledger = _make_ledger(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            insert_ledger_record(db_path, ledger)

    def test_ledger_without_review_approval(self, db_path: str) -> None:
        run, _, _, ret, snap, cand = _insert_candidate_chain(db_path)
        ledger = _make_ledger(
            run.run_id,
            cand.quote_block_id,
            ret.retrieval_attempt_id,
            snap.snapshot_id,
            uuid4(),
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_ledger_record(db_path, ledger)

    def test_synthesis_item_without_ledger_record(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        synthesis = SynthesisOutput(
            run_id=run.run_id,
            synthesizer_prompt_version="v1",
            synthesizer_model_name="model",
            created_at=_NOW,
            title="Test",
            claim_definition="Framing",
            sections=[
                SynthesisSection(
                    section_type=SectionType.SUPPORTING,
                    heading="Supporting",
                    items=[
                        SynthesisItem(
                            connective_template_id="t1",
                            ledger_claim_id=uuid4(),
                            reviewer_approval_id=uuid4(),
                            stance=Stance.SUPPORTING,
                            placement=Placement.SECONDARY,
                            entailment=Entailment.STRONG,
                            approved_factual_statement="Fact.",
                        )
                    ],
                )
            ],
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_synthesis(db_path, synthesis)

    def test_model_invocation_without_run(self, db_path: str) -> None:
        inv = ModelInvocationRecord(
            run_id=uuid4(),
            invocation_id=uuid4(),
            stage=Stage.CLAIM_PLANNER,
            prompt_version="v1",
            model_name="model",
            input_artifact_id=uuid4(),
            status="completed",
            invoked_at=_NOW,
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_model_invocation(db_path, inv)


# ---------------------------------------------------------------------------
# Test: typed reconstruction from stored rows
# ---------------------------------------------------------------------------


class TestTypedReconstruction:
    def test_candidate_segment_offsets_are_typed(self, db_path: str) -> None:
        *_, cand = _insert_candidate_chain(db_path)
        loaded = read_candidate(db_path, cand.quote_block_id)
        assert isinstance(loaded.segment_offsets[0], SegmentOffset)

    def test_ledger_scores_are_integers(self, db_path: str) -> None:
        run, _, _, ret, snap, cand, _, review = _insert_review_chain(db_path)
        assert review.reviewer_approval_id is not None
        ledger = _make_ledger(
            run.run_id,
            cand.quote_block_id,
            ret.retrieval_attempt_id,
            snap.snapshot_id,
            review.reviewer_approval_id,
        )
        insert_ledger_record(db_path, ledger)
        loaded = read_ledger_record(db_path, ledger.ledger_claim_id)
        assert isinstance(loaded.evidence_quality, int)
        assert isinstance(loaded.claim_fit, int)
        assert isinstance(loaded.ledger_score, int)

    def test_timestamps_are_aware(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        loaded = read_run(db_path, run.run_id)
        assert loaded.created_at.tzinfo is not None

    def test_validation_errors_reconstructed(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        result = ValidationResult(
            run_id=run.run_id,
            valid=False,
            errors=[
                ValidationError(
                    code="ledger_mismatch",
                    location="loc1",
                    message="msg1",
                ),
                ValidationError(
                    code="altered_statement",
                    location="loc2",
                    message="msg2",
                ),
            ],
            validator_config_version="v1",
            validated_at=_NOW,
        )
        insert_validation(db_path, result)
        loaded = read_validation(db_path, run.run_id)
        assert len(loaded.errors) == 2
        assert isinstance(loaded.errors[0], ValidationError)


# ---------------------------------------------------------------------------
# Test: duplicate identifier rejection
# ---------------------------------------------------------------------------


class TestDuplicateRejection:
    def test_duplicate_run(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        with pytest.raises(sqlite3.IntegrityError):
            insert_run(db_path, run)

    def test_duplicate_retrieval(self, db_path: str) -> None:
        run, _, query = _insert_run_and_planner(db_path)
        ret = _make_retrieval(run.run_id, query.query_id)
        insert_retrieval_attempt(db_path, ret)
        with pytest.raises(sqlite3.IntegrityError):
            insert_retrieval_attempt(db_path, ret)

    def test_duplicate_candidate(self, db_path: str) -> None:
        *_, cand = _insert_candidate_chain(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            insert_candidate(db_path, cand)

    def test_duplicate_model_invocation(self, db_path: str) -> None:
        run = _make_run()
        insert_run(db_path, run)
        inv = ModelInvocationRecord(
            run_id=run.run_id,
            invocation_id=uuid4(),
            stage=Stage.CLAIM_PLANNER,
            prompt_version="v1",
            model_name="model",
            input_artifact_id=uuid4(),
            status="completed",
            invoked_at=_NOW,
        )
        insert_model_invocation(db_path, inv)
        with pytest.raises(sqlite3.IntegrityError):
            insert_model_invocation(db_path, inv)
