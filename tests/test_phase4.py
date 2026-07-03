from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError as PydanticValidationError

from agents.analyst import (
    SCORE_PAIR_TABLE,
    LedgerAdmissionRequest,
    admit_ledger_record,
    create_statement_draft,
    interpret_score_pair,
    score_candidate,
)
from agents.researcher import build_source_snapshot, filter_provisional_candidate
from agents.reviewer import ReviewChecks, ReviewerInput, build_reviewer_input, review_statement
from models import (
    AmbiguityRecord,
    CandidateQuoteBlock,
    ClaimDefinition,
    Entailment,
    LedgerRecord,
    Placement,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    RetrievalStatus,
    RunManifest,
    RunStatus,
    ScoreDecision,
    SearchQuery,
    SegmentOffset,
    SourceSnapshot,
    Stage,
    Stance,
    StatementDraft,
    StatementReviewResult,
)
from store import (
    init_db,
    insert_candidate,
    insert_ledger_record,
    insert_planner_output,
    insert_retrieval_attempt,
    insert_run,
    insert_snapshot,
    insert_statement_draft,
    insert_statement_review,
    read_ledger_record,
)

_NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
_RUN_ID = UUID("40000000-0000-0000-0000-000000000001")
_RETRIEVAL_ID = UUID("40000000-0000-0000-0000-000000000002")
_QUERY_ID = UUID("40000000-0000-0000-0000-000000000003")
_SNAPSHOT_ID = UUID("40000000-0000-0000-0000-000000000004")
_SOURCE_URL = "https://example.test/phase4"
_BEFORE = "Study context describes surveyed adults."
_AFTER = "Authors caution that estimates vary by subgroup."


def _uuid(value: int) -> UUID:
    return UUID(f"40000000-0000-0000-0000-{value:012d}")


_DEFAULT_DRAFT_ID = _uuid(10)
_DEFAULT_APPROVAL_ID = _uuid(11)
_DEFAULT_LEDGER_CLAIM_ID = _uuid(12)


def _words(prefix: list[str], total: int) -> str:
    return " ".join([*prefix, *["filler" for _ in range(total - len(prefix))]])


def _segment() -> str:
    return f"{_words(['policy', 'evidence', 'shows', '50%', 'growth'], 50)}."


def _snapshot_and_candidate() -> tuple[SourceSnapshot, CandidateQuoteBlock]:
    segment = _segment()
    snapshot = build_source_snapshot(
        run_id=_RUN_ID,
        retrieval_attempt_id=_RETRIEVAL_ID,
        snapshot_id=_SNAPSHOT_ID,
        source_url=_SOURCE_URL,
        retrieved_at=_NOW,
        normalized_text=f"{_BEFORE} {segment} {_AFTER}",
        truncated=False,
        created_at=_NOW,
    )
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'
    provisional = ProvisionalCandidate(
        run_id=snapshot.run_id,
        stance=Stance.SUPPORTING,
        source_url=snapshot.source_url,
        retrieval_attempt_id=snapshot.retrieval_attempt_id,
        query_id=_QUERY_ID,
        query_round=1,
        search_rank=1,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        extracted_quote_block=quote_block,
        extraction_prompt_version="extract-v1",
        extraction_model_name="fixture-model",
        extracted_at=_NOW,
    )
    result = filter_provisional_candidate(
        provisional,
        snapshot,
        claim_keywords=["policy"],
        post_filter_version="phase4-filter-v1",
        post_filter_validated_at=_NOW,
    )
    assert result.valid is True
    assert result.candidate is not None
    return snapshot, result.candidate


def _decision(candidate: CandidateQuoteBlock, *, eq: int = 4, cf: int = 4) -> ScoreDecision:
    return score_candidate(
        run_id=candidate.run_id,
        quote_block_id=candidate.quote_block_id,
        evidence_quality=eq,
        claim_fit=cf,
        rationale="Fixture score decision.",
        analyst_prompt_version="analyst-v1",
        analyst_model_name="fixture-model",
        scored_at=_NOW,
    )


def _draft(
    candidate: CandidateQuoteBlock,
    decision: ScoreDecision,
    statement: str,
    draft_id: UUID = _DEFAULT_DRAFT_ID,
) -> StatementDraft:
    return create_statement_draft(
        candidate=candidate,
        score_decision=decision,
        statement_draft_id=draft_id,
        draft_statement=statement,
        drafted_at=_NOW,
    )


def _checks_pass() -> ReviewChecks:
    return ReviewChecks(
        fully_entailed=True,
        qualifications_preserved=True,
        neutral_framing=True,
        claim_fit_scope_valid=True,
    )


def _approved_review(
    candidate: CandidateQuoteBlock,
    draft: StatementDraft,
    approval_id: UUID = _DEFAULT_APPROVAL_ID,
) -> StatementReviewResult:
    return review_statement(
        draft,
        build_reviewer_input(candidate, draft),
        _checks_pass(),
        reviewer_prompt_version="reviewer-v1",
        reviewer_model_name="fixture-model",
        reviewed_at=_NOW,
        reviewer_approval_id=approval_id,
    )


def _rejected_review(
    candidate: CandidateQuoteBlock,
    draft: StatementDraft,
) -> StatementReviewResult:
    return review_statement(
        draft,
        build_reviewer_input(candidate, draft),
        ReviewChecks(
            fully_entailed=False,
            qualifications_preserved=True,
            neutral_framing=True,
            claim_fit_scope_valid=True,
        ),
        reviewer_prompt_version="reviewer-v1",
        reviewer_model_name="fixture-model",
        reviewed_at=_NOW,
    )


def _admission_request(
    snapshot: SourceSnapshot,
    candidate: CandidateQuoteBlock,
    decision: ScoreDecision,
    draft: StatementDraft,
    review: StatementReviewResult,
    *,
    statement: str,
    entailment: Entailment = Entailment.STRONG,
    ledger_claim_id: UUID = _DEFAULT_LEDGER_CLAIM_ID,
    placement: Placement | None = None,
) -> LedgerAdmissionRequest:
    return LedgerAdmissionRequest(
        ledger_claim_id=ledger_claim_id,
        candidate=candidate,
        snapshot=snapshot,
        score_decision=decision,
        statement_drafts=[draft],
        review_results=[review],
        approved_factual_statement=statement,
        entailment=entailment,
        ledger_validated_at=_NOW,
        placement=placement,
    )


_EXPECTED_SCORE_TABLE = [
    (1, 1, False, None, None),
    (1, 2, False, None, None),
    (1, 3, False, None, None),
    (1, 4, False, None, None),
    (1, 5, False, None, None),
    (2, 1, False, None, None),
    (2, 2, False, None, None),
    (2, 3, True, 3, Placement.QUALIFIED_ONLY),
    (2, 4, True, 3, Placement.SUPPORTING),
    (2, 5, True, 4, Placement.SECONDARY),
    (3, 1, False, None, None),
    (3, 2, False, None, None),
    (3, 3, True, 3, Placement.QUALIFIED_ONLY),
    (3, 4, True, 4, Placement.SECONDARY),
    (3, 5, True, 4, Placement.SECONDARY),
    (4, 1, False, None, None),
    (4, 2, False, None, None),
    (4, 3, True, 4, Placement.QUALIFIED_ONLY),
    (4, 4, True, 4, Placement.SECONDARY),
    (4, 5, True, 5, Placement.PRIMARY),
    (5, 1, False, None, None),
    (5, 2, False, None, None),
    (5, 3, True, 4, Placement.QUALIFIED_ONLY),
    (5, 4, True, 5, Placement.PRIMARY),
    (5, 5, True, 5, Placement.PRIMARY),
]


@pytest.mark.parametrize(
    ("evidence_quality", "claim_fit", "accepted", "ledger_score", "placement"),
    _EXPECTED_SCORE_TABLE,
)
def test_all_25_score_pairs_have_explicit_acceptance_and_placement(
    evidence_quality: int,
    claim_fit: int,
    accepted: bool,
    ledger_score: int | None,
    placement: Placement | None,
) -> None:
    assert len(SCORE_PAIR_TABLE) == 25

    policy = interpret_score_pair(evidence_quality, claim_fit)
    decision = score_candidate(
        run_id=_RUN_ID,
        quote_block_id=_uuid(99),
        evidence_quality=evidence_quality,
        claim_fit=claim_fit,
        rationale="Fixture score decision.",
        analyst_prompt_version="analyst-v1",
        analyst_model_name="fixture-model",
        scored_at=_NOW,
    )

    assert policy.accepted is accepted
    assert policy.ledger_score == ledger_score
    assert policy.placement is placement
    assert decision.approved is accepted
    assert decision.ledger_score == ledger_score
    assert decision.placement is placement


@pytest.mark.parametrize(("evidence_quality", "claim_fit"), [(0, 3), (4, 6)])
def test_score_values_are_validated_separately(evidence_quality: int, claim_fit: int) -> None:
    with pytest.raises(ValueError, match="1 through 5"):
        interpret_score_pair(evidence_quality, claim_fit)


def test_unauthorized_placement_changes_are_rejected() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate, eq=4, cf=4)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(candidate, decision, statement)
    review = _approved_review(candidate, draft)

    request = _admission_request(
        snapshot,
        candidate,
        decision,
        draft,
        review,
        statement=statement,
        placement=Placement.PRIMARY,
    )

    with pytest.raises(ValueError, match="unauthorized placement"):
        admit_ledger_record(request)


def test_missing_reviewer_approval_id_is_rejected_at_ledger_admission() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(candidate, decision, statement)
    bad_review = StatementReviewResult.model_construct(
        run_id=draft.run_id,
        statement_draft_id=draft.statement_draft_id,
        quote_block_id=draft.quote_block_id,
        approved=True,
        reviewer_approval_id=None,
        approved_factual_statement=statement,
        failure_code=None,
        rationale="Bypassed validation fixture.",
        reviewer_prompt_version="reviewer-v1",
        reviewer_model_name="fixture-model",
        reviewed_at=_NOW,
    )
    request = LedgerAdmissionRequest.model_construct(
        ledger_claim_id=_uuid(12),
        candidate=candidate,
        snapshot=snapshot,
        score_decision=decision,
        statement_drafts=[draft],
        review_results=[bad_review],
        approved_factual_statement=statement,
        entailment=Entailment.STRONG,
        ledger_validated_at=_NOW,
        placement=None,
    )

    with pytest.raises(ValueError, match="reviewer_approval_id"):
        admit_ledger_record(request)


def test_statement_altered_after_reviewer_approval_is_rejected() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(candidate, decision, statement)
    review = _approved_review(candidate, draft)
    request = _admission_request(
        snapshot,
        candidate,
        decision,
        draft,
        review,
        statement="The study proved 50% growth among surveyed adults.",
    )

    with pytest.raises(ValueError, match="exact Reviewer-approved"):
        admit_ledger_record(request)


def test_invalid_revision_count_is_rejected() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    drafts = [
        _draft(
            candidate,
            decision,
            f"The study reported 50% growth among surveyed adults {i}.",
            _uuid(20 + i),
        )
        for i in range(3)
    ]
    reviews = [_approved_review(candidate, draft, _uuid(30 + i)) for i, draft in enumerate(drafts)]
    request = LedgerAdmissionRequest(
        ledger_claim_id=_uuid(40),
        candidate=candidate,
        snapshot=snapshot,
        score_decision=decision,
        statement_drafts=drafts,
        review_results=reviews,
        approved_factual_statement=drafts[-1].draft_statement,
        entailment=Entailment.STRONG,
        ledger_validated_at=_NOW,
    )

    with pytest.raises(ValueError, match="one revision maximum"):
        admit_ledger_record(request)


def test_snapshot_hash_mismatch_blocks_ledger_admission() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    bad_snapshot = SourceSnapshot(
        run_id=snapshot.run_id,
        retrieval_attempt_id=snapshot.retrieval_attempt_id,
        snapshot_id=snapshot.snapshot_id,
        source_url=snapshot.source_url,
        retrieved_at=snapshot.retrieved_at,
        normalized_text=snapshot.normalized_text,
        snapshot_sha256="b" * 64,
        word_count=snapshot.word_count,
        truncated=snapshot.truncated,
        created_at=snapshot.created_at,
    )
    decision = _decision(candidate)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(candidate, decision, statement)
    review = _approved_review(candidate, draft)
    request = _admission_request(
        bad_snapshot,
        candidate,
        decision,
        draft,
        review,
        statement=statement,
    )

    with pytest.raises(ValueError, match="hash"):
        admit_ledger_record(request)


def test_correct_hash_but_incorrect_quote_offsets_are_rejected() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    tampered_candidate = candidate.model_copy(
        update={"segment_offsets": [SegmentOffset(start_char=0, end_char=10)]}
    )
    decision = _decision(tampered_candidate)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(tampered_candidate, decision, statement)
    review = _approved_review(tampered_candidate, draft)
    request = _admission_request(
        snapshot,
        tampered_candidate,
        decision,
        draft,
        review,
        statement=statement,
    )

    with pytest.raises(ValueError, match="offsets"):
        admit_ledger_record(request)


def test_multiple_separately_reviewed_ledger_claims_can_use_one_quote_block() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    first_statement = "The study reported 50% growth among surveyed adults."
    second_statement = "The study reported policy evidence among surveyed adults."
    first_draft = _draft(candidate, decision, first_statement, _uuid(50))
    second_draft = _draft(candidate, decision, second_statement, _uuid(51))
    first_review = _approved_review(candidate, first_draft, _uuid(52))
    second_review = _approved_review(candidate, second_draft, _uuid(53))

    first = admit_ledger_record(
        _admission_request(
            snapshot,
            candidate,
            decision,
            first_draft,
            first_review,
            statement=first_statement,
            ledger_claim_id=_uuid(54),
        )
    )
    second = admit_ledger_record(
        _admission_request(
            snapshot,
            candidate,
            decision,
            second_draft,
            second_review,
            statement=second_statement,
            ledger_claim_id=_uuid(55),
        )
    )

    assert first.quote_block_id == second.quote_block_id == candidate.quote_block_id
    assert first.ledger_claim_id != second.ledger_claim_id
    assert first.reviewer_approval_id != second.reviewer_approval_id
    assert first.approved_factual_statement != second.approved_factual_statement


def test_rejected_analyst_decision_cannot_enter_ledger() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    rejected_decision = _decision(candidate, eq=1, cf=5)
    statement = "The study reported 50% growth among surveyed adults."
    draft = StatementDraft(
        run_id=candidate.run_id,
        statement_draft_id=_uuid(60),
        quote_block_id=candidate.quote_block_id,
        stance=candidate.stance,
        draft_statement=statement,
        claim_fit=rejected_decision.claim_fit,
        analyst_prompt_version="analyst-v1",
        analyst_model_name="fixture-model",
        drafted_at=_NOW,
    )
    review = _approved_review(candidate, draft, _uuid(61))
    request = _admission_request(
        snapshot,
        candidate,
        rejected_decision,
        draft,
        review,
        statement=statement,
    )

    with pytest.raises(ValueError, match="rejected Analyst"):
        admit_ledger_record(request)


def test_reviewer_rejected_draft_statement_cannot_enter_ledger() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(candidate, decision, statement)
    review = _rejected_review(candidate, draft)
    request = _admission_request(
        snapshot,
        candidate,
        decision,
        draft,
        review,
        statement=statement,
    )

    with pytest.raises(ValueError, match="Reviewer-rejected"):
        admit_ledger_record(request)


def test_reviewer_second_failure_rejects_quote_block() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    first_draft = _draft(
        candidate,
        decision,
        "First rejected statement among surveyed adults.",
        _uuid(70),
    )
    second_draft = _draft(
        candidate,
        decision,
        "Second rejected statement among surveyed adults.",
        _uuid(71),
    )
    first_review = _rejected_review(candidate, first_draft)
    second_review = _rejected_review(candidate, second_draft)
    request = LedgerAdmissionRequest(
        ledger_claim_id=_uuid(72),
        candidate=candidate,
        snapshot=snapshot,
        score_decision=decision,
        statement_drafts=[first_draft, second_draft],
        review_results=[first_review, second_review],
        approved_factual_statement=second_draft.draft_statement,
        entailment=Entailment.STRONG,
        ledger_validated_at=_NOW,
    )

    with pytest.raises(ValueError, match="second Reviewer failure"):
        admit_ledger_record(request)


def test_claim_fit_3_full_claim_overclaim_is_rejected() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate, eq=3, cf=3)
    statement = "The policy improves outcomes."
    draft = _draft(candidate, decision, statement)
    review = _approved_review(candidate, draft)
    request = _admission_request(
        snapshot,
        candidate,
        decision,
        draft,
        review,
        statement=statement,
    )

    with pytest.raises(ValueError, match="explicit qualification"):
        admit_ledger_record(request)


def test_reviewer_input_rejects_forbidden_fields() -> None:
    with pytest.raises(PydanticValidationError):
        ReviewerInput(
            extracted_quote_block='[Before.] "Quote." [After.]',
            preceding_context="Before.",
            following_context="After.",
            draft_statement="Draft.",
            claim_fit=4,
            evidence_quality=5,
        )


@pytest.mark.parametrize("entailment", [Entailment.PARTIAL, Entailment.WEAK])
def test_partial_or_weak_entailment_requires_qualification(entailment: Entailment) -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate, eq=4, cf=4)
    statement = "The policy improves outcomes."
    draft = _draft(candidate, decision, statement)
    review = _approved_review(candidate, draft)
    request = _admission_request(
        snapshot,
        candidate,
        decision,
        draft,
        review,
        statement=statement,
        entailment=entailment,
    )

    with pytest.raises(ValueError, match="explicit qualification"):
        admit_ledger_record(request)


def test_ledger_records_remain_append_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = str(tmp_path / "phase4.db")
    init_db(db_path)
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(candidate, decision, statement)
    review = _approved_review(candidate, draft)
    ledger = admit_ledger_record(
        _admission_request(
            snapshot,
            candidate,
            decision,
            draft,
            review,
            statement=statement,
        )
    )
    _insert_store_chain(db_path, snapshot, candidate, draft, review)

    insert_ledger_record(db_path, ledger)
    with pytest.raises(sqlite3.IntegrityError):
        insert_ledger_record(
            db_path,
            ledger.model_copy(update={"approved_factual_statement": "Altered statement."}),
        )

    loaded = read_ledger_record(db_path, ledger.ledger_claim_id)
    assert loaded.approved_factual_statement == ledger.approved_factual_statement


def test_no_composite_score_is_produced_or_stored() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    decision = _decision(candidate)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(candidate, decision, statement)
    review = _approved_review(candidate, draft)
    ledger = admit_ledger_record(
        _admission_request(
            snapshot,
            candidate,
            decision,
            draft,
            review,
            statement=statement,
        )
    )

    forbidden_fields = {"total_score", "composite_score", "evidence_score"}
    assert forbidden_fields.isdisjoint(ScoreDecision.model_fields)
    assert forbidden_fields.isdisjoint(LedgerRecord.model_fields)
    assert forbidden_fields.isdisjoint(decision.model_dump())
    assert forbidden_fields.isdisjoint(ledger.model_dump())


def _insert_store_chain(
    db_path: str,
    snapshot: SourceSnapshot,
    candidate: CandidateQuoteBlock,
    draft: StatementDraft,
    review: StatementReviewResult,
) -> None:
    run = RunManifest(
        run_id=candidate.run_id,
        status=RunStatus.RUNNING,
        raw_claim="Fixture claim",
        current_stage=Stage.CLAIM_LEDGER,
        created_at=_NOW,
        updated_at=_NOW,
    )
    insert_run(db_path, run)
    planner = _planner(candidate.run_id)
    insert_planner_output(db_path, planner)
    retrieval = RetrievalRecord(
        run_id=candidate.run_id,
        retrieval_attempt_id=candidate.retrieval_attempt_id,
        query_id=candidate.query_id,
        query_round=candidate.query_round,
        query_text="fixture query",
        search_rank=candidate.search_rank,
        source_url=candidate.source_url,
        resolved_url=candidate.source_url,
        status=RetrievalStatus.RETRIEVED,
        retrieved_at=candidate.retrieved_at,
    )
    insert_retrieval_attempt(db_path, retrieval)
    insert_snapshot(db_path, snapshot)
    insert_candidate(db_path, candidate)
    insert_statement_draft(db_path, draft)
    insert_statement_review(db_path, review)


def _planner(run_id: UUID) -> PlannerOutput:
    exclusions = "-site:reddit.com -site:quora.com -site:youtube.com -site:tiktok.com"
    queries = [
        SearchQuery(
            run_id=run_id,
            query_id=(
                _QUERY_ID
                if stance is Stance.SUPPORTING and round_number == 1
                else _uuid(100 + index)
            ),
            stance=stance,
            query_round=round_number,
            strategy=f"{stance.value}-{round_number}",
            query_text=f"{stance.value} query {round_number}",
            exclusion_parameters=exclusions,
            created_at=_NOW,
        )
        for index, (stance, round_number) in enumerate(
            [
                (Stance.SUPPORTING, 1),
                (Stance.SUPPORTING, 2),
                (Stance.SUPPORTING, 3),
                (Stance.OPPOSING, 1),
                (Stance.OPPOSING, 2),
                (Stance.OPPOSING, 3),
            ]
        )
    ]
    return PlannerOutput(
        run_id=run_id,
        claim_definition=ClaimDefinition(
            run_id=run_id,
            claim_text="Fixture claim",
            population="Fixture population",
            jurisdiction="Fixture jurisdiction",
            time_period="2020-2026",
            comparison_baseline="Fixture baseline",
            intervention_or_exposure="Fixture exposure",
            causal_or_comparative_meaning="Fixture meaning",
            created_at=_NOW,
        ),
        ambiguities=[
            AmbiguityRecord(
                run_id=run_id,
                ambiguity_id=_uuid(98),
                description="Fixture ambiguity",
                impact="Fixture impact",
                created_at=_NOW,
            )
        ],
        search_queries=queries,
        planner_prompt_version="planner-v1",
        planner_model_name="fixture-model",
        planned_at=_NOW,
    )
