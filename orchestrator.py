from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal, TypeVar
from uuid import UUID, uuid5

from pydantic import Field, TypeAdapter, model_validator
from pydantic import ValidationError as PydanticValidationError

from agents.analyst import LedgerAdmissionRequest, admit_ledger_record
from agents.renderer import render_brief, validate_final_release
from agents.researcher import (
    filter_provisional_candidate,
    validate_snapshot_integrity,
)
from models import (
    CandidateBatch,
    CandidateQuoteBlock,
    Entailment,
    LedgerRecord,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    RunManifest,
    RunStatus,
    ScoreDecision,
    SearchQuery,
    SourceSnapshot,
    Stage,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
    SynthesisOutput,
    ValidationResult,
)
from store import (
    init_db,
    insert_analyst_decision,
    insert_candidate,
    insert_ledger_record,
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
from utils import URL_NAMESPACE, compute_sha256

DEFAULT_OUTPUT_DIR_NAME = ".phase6_output"
FIXTURE_DB_NAME = "fixture_pipeline.sqlite3"
AUDIT_FILE_NAME = "audit.json"
RESULT_FILE_NAME = "result.json"
POST_FILTER_VERSION = "phase6-fixture-post-filter-v1"
LEDGER_ID_VERSION = "phase6-fixture-ledger-id-v1"

_ModelT = TypeVar("_ModelT", bound=StrictModel)


class FixturePipelineError(RuntimeError):
    """Raised for malformed fixtures or unexpected fixture-pipeline failures."""


class AuditEntry(StrictModel):
    run_id: UUID
    stage: str = Field(min_length=1)
    status: Literal["loaded", "completed", "released", "blocked"]
    artifact_ref: str = Field(min_length=1)
    artifact_count: int = Field(ge=0)
    artifact_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    outcome: str = Field(min_length=1)


class FixturePipelineResult(StrictModel):
    run_id: UUID
    status: Literal["released", "blocked"]
    raw_claim: str = Field(min_length=1)
    fixture_dir: str = Field(min_length=1)
    output_dir: str = Field(min_length=1)
    db_path: str = Field(min_length=1)
    audit_path: str = Field(min_length=1)
    result_path: str = Field(min_length=1)
    planner_output: PlannerOutput
    retrievals: list[RetrievalRecord]
    snapshots: list[SourceSnapshot]
    provisional_candidates: list[ProvisionalCandidate]
    candidates: list[CandidateQuoteBlock]
    candidate_batches: list[CandidateBatch]
    analyst_decisions: list[ScoreDecision]
    statement_drafts: list[StatementDraft]
    reviewer_decisions: list[StatementReviewResult]
    ledger_records: list[LedgerRecord]
    synthesis_output: SynthesisOutput
    validation_result: ValidationResult
    rendered_brief_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    final_brief: str | None = None
    audit_trail: list[AuditEntry]

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> FixturePipelineResult:
        if self.status == "released":
            if self.final_brief is None or self.rendered_brief_hash is None:
                raise ValueError("released fixture results require final brief and rendered hash")
            if not self.validation_result.valid:
                raise ValueError("released fixture results require valid validation")
        if self.status == "blocked":
            if self.final_brief is not None or self.rendered_brief_hash is not None:
                raise ValueError("blocked fixture results cannot include final brief or hash")
            if self.validation_result.valid:
                raise ValueError("blocked fixture results require invalid validation")
        return self


def run_fixture_pipeline(
    fixture_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
) -> FixturePipelineResult:
    fixture_path = Path(fixture_dir).resolve()
    if not fixture_path.is_dir():
        raise FixturePipelineError(f"fixture directory does not exist: {fixture_path}")

    raw_claim = _read_required_text(fixture_path / "raw_claim.txt").strip()
    if raw_claim == "":
        raise FixturePipelineError("raw_claim.txt must not be empty")

    planner = _load_model(fixture_path / "planner.json", PlannerOutput)
    retrievals = _load_model_list(fixture_path / "retrievals.json", RetrievalRecord)
    snapshots = _load_model_list(fixture_path / "snapshots.json", SourceSnapshot)
    provisionals = _load_model_list(
        fixture_path / "provisional_candidates.json",
        ProvisionalCandidate,
    )
    analyst_decisions = _load_model_list(
        fixture_path / "analyst_decisions.json",
        ScoreDecision,
    )
    statement_drafts = _load_model_list(
        fixture_path / "statement_drafts.json",
        StatementDraft,
    )
    reviewer_decisions = _load_model_list(
        fixture_path / "reviewer_decisions.json",
        StatementReviewResult,
    )
    synthesis = _load_model(fixture_path / "synthesis.json", SynthesisOutput)

    _validate_fixture_run_ids(
        raw_claim,
        planner,
        retrievals,
        snapshots,
        provisionals,
        analyst_decisions,
        statement_drafts,
        reviewer_decisions,
        synthesis,
    )

    output_path = (
        Path(output_dir).resolve()
        if output_dir is not None
        else fixture_path / DEFAULT_OUTPUT_DIR_NAME
    )
    output_path.mkdir(parents=True, exist_ok=True)
    db_path = output_path / FIXTURE_DB_NAME
    audit_path = output_path / AUDIT_FILE_NAME
    result_path = output_path / RESULT_FILE_NAME

    init_db(str(db_path))

    run_manifest = RunManifest(
        run_id=planner.run_id,
        status=RunStatus.COMPLETED,
        raw_claim=raw_claim,
        current_stage=Stage.FINAL_RENDERER_VALIDATOR,
        created_at=planner.planned_at,
        updated_at=synthesis.created_at,
        completed_at=synthesis.created_at,
    )
    _persist_model(
        str(db_path),
        run_manifest,
        insert_run,
        lambda: read_run(str(db_path), run_manifest.run_id),
        "run manifest",
    )
    _persist_model(
        str(db_path),
        planner,
        insert_planner_output,
        lambda: read_planner_output(str(db_path), planner.run_id),
        "planner output",
    )

    planner_queries = {query.query_id: query for query in planner.search_queries}
    _persist_retrievals(str(db_path), retrievals, planner_queries)
    _persist_snapshots(str(db_path), snapshots, retrievals)
    _persist_provisionals(str(db_path), provisionals, planner.run_id)

    candidates = _filter_candidates(planner, snapshots, provisionals)
    candidate_batches = _candidate_batches(planner.run_id, candidates, synthesis.created_at)
    for candidate in candidates:
        _persist_model(
            str(db_path),
            candidate,
            insert_candidate,
            lambda candidate=candidate: read_candidate(str(db_path), candidate.quote_block_id),
            "candidate",
        )

    for decision in analyst_decisions:
        _persist_model(
            str(db_path),
            decision,
            insert_analyst_decision,
            lambda decision=decision: read_analyst_decision(
                str(db_path),
                decision.run_id,
                decision.quote_block_id,
            ),
            "analyst decision",
        )
    for draft in statement_drafts:
        _persist_model(
            str(db_path),
            draft,
            insert_statement_draft,
            lambda draft=draft: read_statement_draft(str(db_path), draft.statement_draft_id),
            "statement draft",
        )
    for review in reviewer_decisions:
        _persist_model(
            str(db_path),
            review,
            insert_statement_review,
            lambda review=review: read_statement_review(
                str(db_path),
                review.run_id,
                review.statement_draft_id,
            ),
            "reviewer decision",
        )

    ledger_records = _admit_ledger_records(
        candidates,
        snapshots,
        analyst_decisions,
        statement_drafts,
        reviewer_decisions,
        synthesis,
    )
    for ledger in ledger_records:
        _persist_model(
            str(db_path),
            ledger,
            insert_ledger_record,
            lambda ledger=ledger: read_ledger_record(str(db_path), ledger.ledger_claim_id),
            "ledger record",
        )

    _persist_model(
        str(db_path),
        synthesis,
        insert_synthesis,
        lambda: read_synthesis(str(db_path), synthesis.run_id),
        "synthesis output",
    )

    validation = validate_final_release(
        synthesis,
        ledger_records,
        validated_at=synthesis.created_at,
    )
    _persist_model(
        str(db_path),
        validation,
        insert_validation,
        lambda: read_validation(str(db_path), validation.run_id),
        "validation result",
    )
    _assert_expected_counts(
        str(db_path),
        planner.run_id,
        retrieval_count=len(retrievals),
        snapshot_count=len(snapshots),
        provisional_count=len(provisionals),
        candidate_count=len(candidates),
        analyst_decision_count=len(analyst_decisions),
        draft_count=len(statement_drafts),
        review_count=len(reviewer_decisions),
        ledger_count=len(ledger_records),
    )

    final_brief = render_brief(synthesis, ledger_records) if validation.valid else None
    status: Literal["released", "blocked"] = "released" if validation.valid else "blocked"
    audit_trail = _build_audit_trail(
        run_id=planner.run_id,
        raw_claim=raw_claim,
        planner=planner,
        snapshots=snapshots,
        provisionals=provisionals,
        candidates=candidates,
        analyst_decisions=analyst_decisions,
        reviewer_decisions=reviewer_decisions,
        ledger_records=ledger_records,
        synthesis=synthesis,
        validation=validation,
    )
    result = FixturePipelineResult(
        run_id=planner.run_id,
        status=status,
        raw_claim=raw_claim,
        fixture_dir=str(fixture_path),
        output_dir=str(output_path),
        db_path=str(db_path),
        audit_path=str(audit_path),
        result_path=str(result_path),
        planner_output=planner,
        retrievals=retrievals,
        snapshots=snapshots,
        provisional_candidates=provisionals,
        candidates=candidates,
        candidate_batches=candidate_batches,
        analyst_decisions=analyst_decisions,
        statement_drafts=statement_drafts,
        reviewer_decisions=reviewer_decisions,
        ledger_records=ledger_records,
        synthesis_output=synthesis,
        validation_result=validation,
        rendered_brief_hash=validation.rendered_brief_hash,
        final_brief=final_brief,
        audit_trail=audit_trail,
    )

    _write_json_idempotent(
        audit_path,
        [entry.model_dump(mode="json") for entry in audit_trail],
    )
    _write_json_idempotent(result_path, result.model_dump(mode="json"))
    return result


def derive_fixture_ledger_claim_id(
    run_id: UUID,
    review: StatementReviewResult,
) -> UUID:
    if not review.approved or review.reviewer_approval_id is None:
        raise FixturePipelineError(
            "approved Reviewer decision is required for Ledger ID derivation"
        )
    if review.approved_factual_statement is None:
        raise FixturePipelineError("approved Reviewer decision is missing approved text")
    return uuid5(
        URL_NAMESPACE,
        (
            f"{LEDGER_ID_VERSION}::{run_id}::ledger::"
            f"{review.reviewer_approval_id}::{review.approved_factual_statement}"
        ),
    )


def _read_required_text(path: Path) -> str:
    if not path.is_file():
        raise FixturePipelineError(f"missing fixture file: {path}")
    return path.read_text(encoding="utf-8")


def _load_model(path: Path, model_type: type[_ModelT]) -> _ModelT:
    try:
        return model_type.model_validate_json(_read_required_text(path))
    except PydanticValidationError as exc:
        raise FixturePipelineError(f"invalid {path.name}: {exc}") from exc


def _load_model_list(path: Path, model_type: type[_ModelT]) -> list[_ModelT]:
    try:
        adapter = TypeAdapter(list[model_type])
        return adapter.validate_json(_read_required_text(path))
    except PydanticValidationError as exc:
        raise FixturePipelineError(f"invalid {path.name}: {exc}") from exc


def _validate_fixture_run_ids(
    raw_claim: str,
    planner: PlannerOutput,
    retrievals: Sequence[RetrievalRecord],
    snapshots: Sequence[SourceSnapshot],
    provisionals: Sequence[ProvisionalCandidate],
    analyst_decisions: Sequence[ScoreDecision],
    statement_drafts: Sequence[StatementDraft],
    reviewer_decisions: Sequence[StatementReviewResult],
    synthesis: SynthesisOutput,
) -> None:
    run_id = planner.run_id
    if planner.claim_definition.claim_text != raw_claim:
        raise FixturePipelineError("raw claim must match PlannerOutput claim_definition.claim_text")
    collections: tuple[tuple[str, Sequence[object]], ...] = (
        ("retrievals", retrievals),
        ("snapshots", snapshots),
        ("provisional candidates", provisionals),
        ("analyst decisions", analyst_decisions),
        ("statement drafts", statement_drafts),
        ("reviewer decisions", reviewer_decisions),
    )
    for label, artifacts in collections:
        for index, artifact in enumerate(artifacts):
            artifact_run_id = getattr(artifact, "run_id", None)
            if artifact_run_id != run_id:
                raise FixturePipelineError(f"{label}[{index}] run_id does not match planner")
    if synthesis.run_id != run_id:
        raise FixturePipelineError("SynthesisOutput run_id does not match planner")


def _persist_retrievals(
    db_path: str,
    retrievals: Sequence[RetrievalRecord],
    planner_queries: dict[UUID, SearchQuery],
) -> None:
    for retrieval in retrievals:
        query = planner_queries.get(retrieval.query_id)
        if query is None:
            raise FixturePipelineError("retrieval references an unknown planner query")
        if retrieval.query_round != query.query_round:
            raise FixturePipelineError("retrieval query_round does not match planner query")
        if retrieval.query_text != query.query_text:
            raise FixturePipelineError("retrieval query_text does not match planner query")
        _persist_model(
            db_path,
            retrieval,
            insert_retrieval_attempt,
            lambda retrieval=retrieval: read_retrieval_attempt(
                db_path,
                retrieval.retrieval_attempt_id,
            ),
            "retrieval attempt",
        )


def _persist_snapshots(
    db_path: str,
    snapshots: Sequence[SourceSnapshot],
    retrievals: Sequence[RetrievalRecord],
) -> None:
    retrieval_by_id = {retrieval.retrieval_attempt_id: retrieval for retrieval in retrievals}
    for snapshot in snapshots:
        validate_snapshot_integrity(snapshot)
        retrieval = retrieval_by_id.get(snapshot.retrieval_attempt_id)
        if retrieval is None:
            raise FixturePipelineError("snapshot references an unknown retrieval attempt")
        if snapshot.source_url != retrieval.source_url:
            raise FixturePipelineError("snapshot source_url does not match retrieval")
        _persist_model(
            db_path,
            snapshot,
            insert_snapshot,
            lambda snapshot=snapshot: read_snapshot(db_path, snapshot.snapshot_id),
            "snapshot",
        )


def _persist_provisionals(
    db_path: str,
    provisionals: Sequence[ProvisionalCandidate],
    run_id: UUID,
) -> None:
    existing = read_provisional_extractions(db_path, run_id)
    if existing:
        if _model_dump_list(existing) != _model_dump_list(provisionals):
            raise FixturePipelineError("existing provisional extractions differ from fixture")
        return
    for provisional in provisionals:
        insert_provisional_extraction(db_path, provisional)


def _filter_candidates(
    planner: PlannerOutput,
    snapshots: Sequence[SourceSnapshot],
    provisionals: Sequence[ProvisionalCandidate],
) -> list[CandidateQuoteBlock]:
    snapshot_by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    candidates: list[CandidateQuoteBlock] = []
    claim_keywords = _claim_keywords_from_planner(planner)
    for provisional in provisionals:
        snapshot = snapshot_by_id.get(provisional.snapshot_id)
        if snapshot is None:
            raise FixturePipelineError("provisional candidate references an unknown snapshot")
        result = filter_provisional_candidate(
            provisional,
            snapshot,
            claim_keywords=claim_keywords,
            post_filter_version=POST_FILTER_VERSION,
            post_filter_validated_at=provisional.extracted_at,
        )
        if not result.valid or result.candidate is None:
            raise FixturePipelineError(
                "fixture provisional candidate failed deterministic filtering: "
                f"{result.rejection_message}"
            )
        candidates.append(result.candidate)
    return sorted(candidates, key=lambda candidate: str(candidate.quote_block_id))


def _candidate_batches(
    run_id: UUID,
    candidates: Sequence[CandidateQuoteBlock],
    created_at: datetime,
) -> list[CandidateBatch]:
    grouped: dict[tuple[object, int], list[CandidateQuoteBlock]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.stance, candidate.query_round)].append(candidate)
    return [
        CandidateBatch(
            run_id=run_id,
            stance=stance,
            query_round=query_round,
            candidates=sorted(batch, key=lambda candidate: str(candidate.quote_block_id)),
            created_at=created_at,
        )
        for (stance, query_round), batch in sorted(
            grouped.items(),
            key=lambda item: (str(item[0][0]), item[0][1]),
        )
    ]


def _admit_ledger_records(
    candidates: Sequence[CandidateQuoteBlock],
    snapshots: Sequence[SourceSnapshot],
    analyst_decisions: Sequence[ScoreDecision],
    statement_drafts: Sequence[StatementDraft],
    reviewer_decisions: Sequence[StatementReviewResult],
    synthesis: SynthesisOutput,
) -> list[LedgerRecord]:
    snapshot_by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    candidate_by_id = {candidate.quote_block_id: candidate for candidate in candidates}
    decision_by_quote = {decision.quote_block_id: decision for decision in analyst_decisions}
    drafts_by_quote: dict[UUID, list[StatementDraft]] = defaultdict(list)
    reviews_by_quote: dict[UUID, list[StatementReviewResult]] = defaultdict(list)
    synthesis_items = _synthesis_items_by_ledger_id(synthesis)

    for draft in statement_drafts:
        drafts_by_quote[draft.quote_block_id].append(draft)
    for review in reviewer_decisions:
        reviews_by_quote[review.quote_block_id].append(review)

    extra_decisions = set(decision_by_quote) - set(candidate_by_id)
    if extra_decisions:
        raise FixturePipelineError("Analyst decisions reference unknown candidates")

    ledgers: list[LedgerRecord] = []
    for candidate in candidates:
        decision = decision_by_quote.get(candidate.quote_block_id)
        if decision is None:
            raise FixturePipelineError("candidate is missing fixture Analyst decision")
        if not decision.approved:
            continue
        snapshot = snapshot_by_id.get(candidate.snapshot_id)
        if snapshot is None:
            raise FixturePipelineError("candidate references an unknown snapshot")
        drafts = _sorted_drafts(drafts_by_quote.get(candidate.quote_block_id, []))
        reviews = _sorted_reviews(reviews_by_quote.get(candidate.quote_block_id, []))
        if not drafts or not reviews:
            raise FixturePipelineError("approved Analyst decision is missing Reviewer fixture data")
        final_review = reviews[-1]
        ledger_claim_id = derive_fixture_ledger_claim_id(candidate.run_id, final_review)
        synthesis_item = synthesis_items.get(ledger_claim_id)
        entailment = synthesis_item.entailment if synthesis_item is not None else Entailment.STRONG
        if final_review.approved_factual_statement is None:
            raise FixturePipelineError("approved Reviewer decision is missing approved statement")
        ledger = admit_ledger_record(
            LedgerAdmissionRequest(
                ledger_claim_id=ledger_claim_id,
                candidate=candidate,
                snapshot=snapshot,
                score_decision=decision,
                statement_drafts=drafts,
                review_results=reviews,
                approved_factual_statement=final_review.approved_factual_statement,
                entailment=entailment,
                ledger_validated_at=synthesis.created_at,
            )
        )
        ledgers.append(ledger)
    return sorted(ledgers, key=lambda ledger: str(ledger.ledger_claim_id))


def _synthesis_items_by_ledger_id(synthesis: SynthesisOutput) -> dict[UUID, object]:
    items: dict[UUID, object] = {}
    for section in synthesis.sections:
        for item in section.items:
            items[item.ledger_claim_id] = item
    return items


def _sorted_drafts(drafts: Sequence[StatementDraft]) -> list[StatementDraft]:
    return sorted(drafts, key=lambda draft: (draft.drafted_at, str(draft.statement_draft_id)))


def _sorted_reviews(reviews: Sequence[StatementReviewResult]) -> list[StatementReviewResult]:
    return sorted(reviews, key=lambda review: (review.reviewed_at, str(review.statement_draft_id)))


def _claim_keywords_from_planner(planner: PlannerOutput) -> tuple[str, ...]:
    text = " ".join(
        (
            planner.claim_definition.claim_text,
            planner.claim_definition.population,
            planner.claim_definition.intervention_or_exposure,
        )
    )
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "for",
        "in",
        "of",
        "or",
        "the",
        "to",
    }
    words = [word.strip(".,;:!?()[]{}\"'").casefold() for word in text.replace("-", " ").split()]
    keywords = tuple(
        dict.fromkeys(word for word in words if len(word) > 2 and word not in stop_words)
    )
    if not keywords:
        raise FixturePipelineError("PlannerOutput did not yield deterministic claim keywords")
    return keywords


def _persist_model(
    db_path: str,
    model: _ModelT,
    insert_fn: Callable[[str, _ModelT], None],
    read_existing: Callable[[], _ModelT],
    label: str,
) -> None:
    try:
        existing = read_existing()
    except KeyError:
        try:
            insert_fn(db_path, model)
        except sqlite3.IntegrityError as exc:
            raise FixturePipelineError(f"could not persist {label}: {exc}") from exc
        return
    _assert_same_model(existing, model, label)


def _assert_same_model(existing: StrictModel, expected: StrictModel, label: str) -> None:
    if existing.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise FixturePipelineError(f"existing {label} differs from fixture artifact")


def _assert_expected_counts(
    db_path: str,
    run_id: UUID,
    *,
    retrieval_count: int,
    snapshot_count: int,
    provisional_count: int,
    candidate_count: int,
    analyst_decision_count: int,
    draft_count: int,
    review_count: int,
    ledger_count: int,
) -> None:
    expected = {
        "retrieval_attempts": retrieval_count,
        "snapshots": snapshot_count,
        "provisional_extractions": provisional_count,
        "candidates": candidate_count,
        "analyst_decisions": analyst_decision_count,
        "statement_drafts": draft_count,
        "statement_review_attempts": review_count,
        "ledger_records": ledger_count,
    }
    with sqlite3.connect(db_path) as conn:
        for table, count in expected.items():
            actual = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE run_id = ?",
                (str(run_id),),
            ).fetchone()[0]
            if actual != count:
                raise FixturePipelineError(
                    f"{table} has {actual} records for run {run_id}; expected {count}"
                )


def _build_audit_trail(
    *,
    run_id: UUID,
    raw_claim: str,
    planner: PlannerOutput,
    snapshots: Sequence[SourceSnapshot],
    provisionals: Sequence[ProvisionalCandidate],
    candidates: Sequence[CandidateQuoteBlock],
    analyst_decisions: Sequence[ScoreDecision],
    reviewer_decisions: Sequence[StatementReviewResult],
    ledger_records: Sequence[LedgerRecord],
    synthesis: SynthesisOutput,
    validation: ValidationResult,
) -> list[AuditEntry]:
    validation_status: Literal["released", "blocked"] = (
        "released" if validation.valid else "blocked"
    )
    validation_outcome = (
        f"released with rendered hash {validation.rendered_brief_hash}"
        if validation.valid
        else f"blocked with {len(validation.errors)} validation error(s)"
    )
    return [
        _audit(
            run_id,
            "raw_fixture_input",
            "loaded",
            "raw_claim.txt",
            1,
            compute_sha256(raw_claim),
            "raw claim loaded",
        ),
        _audit(
            run_id,
            Stage.CLAIM_PLANNER.value,
            "completed",
            "planner.json",
            len(planner.search_queries),
            _model_hash(planner),
            "typed PlannerOutput loaded",
        ),
        _audit(
            run_id,
            "fixture_snapshots",
            "completed",
            "snapshots.json",
            len(snapshots),
            _models_hash(snapshots),
            "fixture snapshots validated",
        ),
        _audit(
            run_id,
            "fixture_provisional_candidates",
            "completed",
            "provisional_candidates.json",
            len(provisionals),
            _models_hash(provisionals),
            "fixture provisional candidates loaded",
        ),
        _audit(
            run_id,
            "deterministic_candidate_filter",
            "completed",
            "CandidateQuoteBlock",
            len(candidates),
            _models_hash(candidates),
            "provisional candidates passed deterministic filtering",
        ),
        _audit(
            run_id,
            Stage.EVIDENCE_ANALYST.value,
            "completed",
            "analyst_decisions.json",
            len(analyst_decisions),
            _models_hash(analyst_decisions),
            "fixture Analyst decisions loaded",
        ),
        _audit(
            run_id,
            Stage.STATEMENT_REVIEWER.value,
            "completed",
            "reviewer_decisions.json",
            len(reviewer_decisions),
            _models_hash(reviewer_decisions),
            "fixture Reviewer decisions loaded",
        ),
        _audit(
            run_id,
            Stage.CLAIM_LEDGER.value,
            "completed",
            "LedgerRecord",
            len(ledger_records),
            _models_hash(ledger_records),
            "Reviewer-approved statements admitted to the Ledger",
        ),
        _audit(
            run_id,
            Stage.DEBATE_SYNTHESIZER.value,
            "completed",
            "synthesis.json",
            1,
            _model_hash(synthesis),
            "fixture SynthesisOutput loaded",
        ),
        _audit(
            run_id,
            Stage.FINAL_RENDERER_VALIDATOR.value,
            validation_status,
            "ValidationResult",
            1,
            _model_hash(validation),
            validation_outcome,
        ),
    ]


def _audit(
    run_id: UUID,
    stage: str,
    status: Literal["loaded", "completed", "released", "blocked"],
    artifact_ref: str,
    artifact_count: int,
    artifact_hash: str | None,
    outcome: str,
) -> AuditEntry:
    return AuditEntry(
        run_id=run_id,
        stage=stage,
        status=status,
        artifact_ref=artifact_ref,
        artifact_count=artifact_count,
        artifact_hash=artifact_hash,
        outcome=outcome,
    )


def _write_json_idempotent(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != encoded:
            raise FixturePipelineError(f"existing output differs from deterministic result: {path}")
        return
    path.write_text(encoded, encoding="utf-8")


def _model_hash(model: StrictModel) -> str:
    return _json_hash(model.model_dump(mode="json"))


def _models_hash(models: Sequence[StrictModel]) -> str:
    return _json_hash(_model_dump_list(models))


def _model_dump_list(models: Sequence[StrictModel]) -> list[dict[str, object]]:
    return [model.model_dump(mode="json") for model in models]


def _json_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
