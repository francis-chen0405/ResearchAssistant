from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Literal, TypeVar, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from agents.analyst import (
    LedgerAdmissionRequest,
    ValidatedLedgerPayload,
    admit_ledger_record,
    build_analyst_llm_input,
)
from agents.opposingresearcher import retrieve_opposing
from agents.planner import PlannerLLMInput
from agents.renderer import render_brief, validate_final_release
from agents.researcher import (
    filter_provisional_candidate,
    validate_snapshot_integrity,
)
from agents.reviewer import (
    ReviewerDecision,
    build_reviewer_input,
    build_statement_review_result,
    validate_reviewer_decision,
)
from agents.supportingresearcher import (
    ATTEMPTS_PER_STANCE,
    ResearcherRetrievalBatch,
    build_extraction_llm_input,
    retrieve_supporting,
)
from agents.synthesizer import SynthesizerLLMInput
from models import (
    CandidateBatch,
    CandidateQuoteBlock,
    CheckpointStatus,
    Entailment,
    LedgerRecord,
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    OrchestrationCheckpoint,
    PersistedStageArtifact,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    RunCancellationRequest,
    RunManifest,
    RunStatus,
    ScoreDecision,
    SearchQuery,
    SourceSnapshot,
    Stage,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
    SynthesisItem,
    SynthesisOutput,
    ValidationResult,
)
from providers.llm import (
    DEFAULT_LLM_ROUTING,
    InvocationFailureCode,
    LLMInvocationError,
    LLMProvider,
    LLMRoutingConfig,
    LLMStage,
    ModelAlias,
    RetryMetadata,
    build_stage_request,
    invoke_llm,
    load_prompt,
)
from providers.scraper import RetryPolicy, ScraperProvider
from providers.search import SearchProvider
from store import (
    ModelAttemptBudgetError,
    finish_model_route_attempt,
    init_db,
    insert_analyst_decision,
    insert_cancellation_request,
    insert_candidate,
    insert_ledger_record,
    insert_planner_output,
    insert_provisional_extraction,
    insert_retrieval_attempt,
    insert_run,
    insert_snapshot,
    insert_stage_artifact,
    insert_statement_draft,
    insert_statement_review,
    insert_synthesis,
    insert_validation,
    read_analyst_decision,
    read_cancellation_request,
    read_candidate,
    read_ledger_record,
    read_model_route_attempts,
    read_orchestration_checkpoint,
    read_orchestration_checkpoints,
    read_planner_output,
    read_provisional_extractions,
    read_retrieval_attempt,
    read_run,
    read_snapshot,
    read_stage_artifact,
    read_statement_draft,
    read_statement_review,
    read_synthesis,
    read_validation,
    reserve_model_route_attempt,
    update_run,
    upsert_orchestration_checkpoint,
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


def _aware_fixture_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("fixture validation timestamps must be timezone-aware")
    return value


class FixtureValidationTimes(StrictModel):
    """Explicit deterministic validation-event times for one fixture run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    post_filter_validated_at: datetime
    ledger_validated_at: datetime

    _timestamps_are_aware = field_validator(
        "post_filter_validated_at",
        "ledger_validated_at",
    )(_aware_fixture_time)

    @model_validator(mode="after")
    def validate_order(self) -> FixtureValidationTimes:
        if self.ledger_validated_at < self.post_filter_validated_at:
            raise ValueError("Ledger validation cannot precede post-filter validation")
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
    validation_times = _load_model(
        fixture_path / "validation_times.json",
        FixtureValidationTimes,
    )
    if validation_times.run_id != planner.run_id:
        raise FixturePipelineError("fixture validation times run_id does not match Planner run_id")

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

    initial_manifest = RunManifest(
        run_id=planner.run_id,
        status=RunStatus.RUNNING,
        raw_claim=raw_claim,
        current_stage=Stage.FINAL_RENDERER_VALIDATOR,
        created_at=planner.planned_at,
        updated_at=synthesis.created_at,
    )
    try:
        existing_manifest = read_run(str(db_path), planner.run_id)
    except KeyError:
        insert_run(str(db_path), initial_manifest)
    else:
        if existing_manifest.raw_claim != raw_claim:
            raise FixturePipelineError("persisted fixture run claim does not match raw_claim.txt")
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

    candidates = _filter_candidates(
        planner,
        snapshots,
        provisionals,
        validation_clock=lambda: validation_times.post_filter_validated_at,
    )
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
        validation_clock=lambda: validation_times.ledger_validated_at,
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
        authoritative_claim=raw_claim,
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

    terminal_manifest = RunManifest(
        run_id=planner.run_id,
        status=RunStatus.COMPLETED if validation.valid else RunStatus.BLOCKED,
        raw_claim=raw_claim,
        current_stage=Stage.FINAL_RENDERER_VALIDATOR,
        created_at=planner.planned_at,
        updated_at=synthesis.created_at,
        completed_at=synthesis.created_at,
    )
    update_run(str(db_path), terminal_manifest)
    final_brief = (
        render_brief(synthesis, ledger_records, authoritative_claim=raw_claim)
        if validation.valid
        else None
    )
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
    payload: ValidatedLedgerPayload,
) -> UUID:
    review = payload.approved_review
    if not review.approved or review.reviewer_approval_id is None:
        raise FixturePipelineError(
            "approved Reviewer decision is required for Ledger ID derivation"
        )
    if review.approved_factual_statement is None:
        raise FixturePipelineError("approved Reviewer decision is missing approved text")
    return uuid5(
        URL_NAMESPACE,
        (
            f"{LEDGER_ID_VERSION}::{payload.candidate.run_id}::ledger::"
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
    *,
    validation_clock: Callable[[], datetime],
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
            validation_clock=validation_clock,
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
    *,
    validation_clock: Callable[[], datetime],
) -> list[LedgerRecord]:
    snapshot_by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    candidate_by_id = {candidate.quote_block_id: candidate for candidate in candidates}
    decision_by_quote = {decision.quote_block_id: decision for decision in analyst_decisions}
    drafts_by_quote: dict[UUID, list[StatementDraft]] = defaultdict(list)
    reviews_by_quote: dict[UUID, list[StatementReviewResult]] = defaultdict(list)
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
        synthesis_item = _synthesis_item_for_review(synthesis, final_review)
        entailment = synthesis_item.entailment if synthesis_item is not None else Entailment.STRONG
        if final_review.approved_factual_statement is None:
            raise FixturePipelineError("approved Reviewer decision is missing approved statement")
        ledger = admit_ledger_record(
            LedgerAdmissionRequest(
                candidate=candidate,
                snapshot=snapshot,
                score_decision=decision,
                statement_drafts=drafts,
                review_results=reviews,
                approved_factual_statement=final_review.approved_factual_statement,
                entailment=entailment,
            ),
            derive_ledger_claim_id=derive_fixture_ledger_claim_id,
            validation_clock=validation_clock,
        )
        ledgers.append(ledger)
    return sorted(ledgers, key=lambda ledger: str(ledger.ledger_claim_id))


def _synthesis_item_for_review(
    synthesis: SynthesisOutput,
    review: StatementReviewResult,
) -> SynthesisItem | None:
    matches: list[SynthesisItem] = []
    for section in synthesis.sections:
        for item in section.items:
            if (
                item.reviewer_approval_id == review.reviewer_approval_id
                and item.approved_factual_statement == review.approved_factual_statement
            ):
                matches.append(item)
    if len(matches) > 1:
        raise FixturePipelineError("Reviewer decision matches multiple synthesis items")
    return matches[0] if matches else None


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


# ---------------------------------------------------------------------------
# Phase 9 provider-backed orchestration
# ---------------------------------------------------------------------------

PHASE9_POST_FILTER_VERSION = "phase9-provider-post-filter-v1"
PHASE9_LEDGER_ID_VERSION = "phase9-provider-ledger-id-v1"
PHASE9_RESEARCHERS_ARTIFACT = "phase9-researchers"
PHASE9_ANALYSIS_ARTIFACT = "phase9-analysis-ledger"
PHASE9_PLANNER_CHECKPOINT = "planner"
PHASE9_RESEARCHERS_CHECKPOINT = "researchers"
PHASE9_ANALYSIS_CHECKPOINT = "analysis-ledger"
PHASE9_SYNTHESIS_CHECKPOINT = "synthesis"
PHASE9_VALIDATION_CHECKPOINT = "validation-release"

_RETRYABLE_FAILURE_CODES = frozenset(
    {
        "transient_failure",
        "timeout",
        "malformed_output",
        "schema_validation_failure",
        "deterministic_validation_failure",
        "exact_quote_failure",
        "interrupted_attempt",
    }
)
_EXTRACTOR_PRO_ESCALATION_CODES = _RETRYABLE_FAILURE_CODES | frozenset(
    {
        "explicit_ambiguity",
        "context_limit",
        "complexity_limit",
    }
)
_AVAILABILITY_FAILURE_CODES = frozenset({"transient_failure", "timeout", "interrupted_attempt"})


class ProviderRunStatus(StrEnum):
    RELEASED = "released"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RUNNING = "running"


class ResearcherSideStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class Phase9OrchestrationError(RuntimeError):
    """Explicit Phase 9 failure carrying the stage that could not complete."""

    def __init__(self, stage: Stage, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class Phase9Cancellation(RuntimeError):
    """Internal signal used only at synchronous stage boundaries."""


class ObjectiveRoutingFailure(RuntimeError):
    """Objective local failure that may authorize a configured retry or escalation."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


class OrchestrationBudget(StrictModel):
    max_model_calls: int = Field(default=256, ge=1)
    retrieval_attempts_per_side: int = Field(default=ATTEMPTS_PER_STANCE, ge=1)
    max_total_tokens: int | None = Field(default=None, ge=1)
    max_total_cost_usd: float | None = Field(default=None, ge=0.0)


class PinnedModelSnapshot(StrictModel):
    model_alias: ModelAlias
    snapshot: str = Field(min_length=1)


class OrchestrationRetryPolicy(StrictModel):
    max_attempts_per_alias: int = Field(default=2, ge=1, le=3)


class ProviderOrchestrationConfig(StrictModel):
    routing: LLMRoutingConfig = DEFAULT_LLM_ROUTING
    retries: OrchestrationRetryPolicy = OrchestrationRetryPolicy()
    retrieval_retry: RetryPolicy = RetryPolicy()
    budget: OrchestrationBudget = OrchestrationBudget()
    pinned_model_snapshots: tuple[PinnedModelSnapshot, ...] = ()

    @model_validator(mode="after")
    def validate_pinned_aliases(self) -> ProviderOrchestrationConfig:
        aliases = [item.model_alias for item in self.pinned_model_snapshots]
        if len(aliases) != len(set(aliases)):
            raise ValueError("pinned model aliases must be unique")
        return self

    def pinned_snapshot_for(self, alias: ModelAlias) -> str | None:
        for item in self.pinned_model_snapshots:
            if item.model_alias is alias:
                return item.snapshot
        return None


class ResearcherFailure(StrictModel):
    stage: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    snapshot_id: UUID | None = None


class ResearcherStageResult(StrictModel):
    run_id: UUID
    stance: Literal["supporting", "opposing"]
    status: ResearcherSideStatus
    retrieval_batch: ResearcherRetrievalBatch | None = None
    provisional_candidates: tuple[ProvisionalCandidate, ...] = ()
    candidates: tuple[CandidateQuoteBlock, ...] = ()
    failures: tuple[ResearcherFailure, ...] = ()

    @model_validator(mode="after")
    def validate_side_result(self) -> ResearcherStageResult:
        if self.retrieval_batch is not None:
            if self.retrieval_batch.run_id != self.run_id:
                raise ValueError("retrieval batch must match researcher run_id")
            if self.retrieval_batch.stance.value != self.stance:
                raise ValueError("retrieval batch stance must match researcher result")
        if any(item.run_id != self.run_id for item in self.provisional_candidates):
            raise ValueError("provisional candidate run_id must match researcher result")
        if any(item.run_id != self.run_id for item in self.candidates):
            raise ValueError("candidate run_id must match researcher result")
        if self.status is ResearcherSideStatus.FAILED and not self.failures:
            raise ValueError("failed researcher results require an explicit failure")
        if self.status is ResearcherSideStatus.COMPLETED and self.failures:
            raise ValueError("completed researcher results cannot include failures")
        return self


class ResearcherPairResult(StrictModel):
    run_id: UUID
    supporting: ResearcherStageResult
    opposing: ResearcherStageResult

    @model_validator(mode="after")
    def validate_pair(self) -> ResearcherPairResult:
        if self.supporting.run_id != self.run_id or self.opposing.run_id != self.run_id:
            raise ValueError("both researcher sides must match the run_id")
        if self.supporting.stance != "supporting" or self.opposing.stance != "opposing":
            raise ValueError("researcher pair has incorrect stance assignment")
        support_limit = (
            self.supporting.retrieval_batch.intended_attempt_count
            if self.supporting.retrieval_batch is not None
            else ATTEMPTS_PER_STANCE
        )
        oppose_limit = (
            self.opposing.retrieval_batch.intended_attempt_count
            if self.opposing.retrieval_batch is not None
            else ATTEMPTS_PER_STANCE
        )
        if support_limit != oppose_limit:
            raise ValueError("supporting and opposing retrieval limits must be equal")
        return self


class AnalysisStageResult(StrictModel):
    run_id: UUID
    analyst_decisions: tuple[ScoreDecision, ...]
    statement_drafts: tuple[StatementDraft, ...]
    reviewer_decisions: tuple[StatementReviewResult, ...]
    ledger_records: tuple[LedgerRecord, ...]
    rejected_quote_block_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_analysis_run_ids(self) -> AnalysisStageResult:
        collections: tuple[Sequence[object], ...] = (
            self.analyst_decisions,
            self.statement_drafts,
            self.reviewer_decisions,
            self.ledger_records,
        )
        for artifacts in collections:
            if any(getattr(artifact, "run_id", None) != self.run_id for artifact in artifacts):
                raise ValueError("analysis artifacts must all match the run_id")
        return self


class ProviderPipelineResult(StrictModel):
    run_id: UUID
    status: ProviderRunStatus
    raw_claim: str = Field(min_length=1)
    db_path: str = Field(min_length=1)
    current_stage: Stage
    failure_reason: str | None = None
    planner_output: PlannerOutput | None = None
    researcher_result: ResearcherPairResult | None = None
    analysis_result: AnalysisStageResult | None = None
    synthesis_output: SynthesisOutput | None = None
    validation_result: ValidationResult | None = None
    final_brief: str | None = None
    rendered_brief_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checkpoints: tuple[OrchestrationCheckpoint, ...] = ()
    model_attempts: tuple[ModelRouteAttempt, ...] = ()
    retrieval_attempts_used: int = Field(default=0, ge=0)
    model_calls_used: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> ProviderPipelineResult:
        if self.status is ProviderRunStatus.RELEASED:
            if (
                self.validation_result is None
                or not self.validation_result.valid
                or self.final_brief is None
                or self.rendered_brief_hash is None
            ):
                raise ValueError("released runs require valid validation, final brief, and hash")
        elif self.status is ProviderRunStatus.BLOCKED:
            if self.validation_result is None or self.validation_result.valid:
                raise ValueError("blocked runs require an invalid validation result")
            if self.final_brief is not None or self.rendered_brief_hash is not None:
                raise ValueError("blocked runs cannot carry a final brief or hash")
        elif self.status in {ProviderRunStatus.FAILED, ProviderRunStatus.CANCELLED}:
            if self.failure_reason is None:
                raise ValueError("failed and cancelled runs require an explicit reason")
            if self.final_brief is not None or self.rendered_brief_hash is not None:
                raise ValueError("failed and cancelled runs cannot carry a final brief or hash")
        return self


_StageHook = Callable[[UUID, str], None]
_ObjectiveValidator = Callable[[BaseModel, ModelAlias], BaseModel]


def run_provider_pipeline(
    raw_claim: str,
    *,
    db_path: str | Path,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    llm_provider: LLMProvider,
    run_id: UUID | None = None,
    config: ProviderOrchestrationConfig | None = None,
    clock: Callable[[], datetime] | None = None,
    stage_hook: _StageHook | None = None,
) -> ProviderPipelineResult:
    """Run or restart the synchronous provider-backed Phase 9 pipeline."""
    claim = raw_claim.strip()
    if not claim:
        raise ValueError("raw_claim must not be empty")
    database_path = Path(db_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    path = str(database_path)
    settings = config or ProviderOrchestrationConfig()
    now = clock or _phase9_utc_now
    resolved_run_id = run_id or uuid4()
    init_db(path)
    manifest = _create_or_resume_provider_run(path, resolved_run_id, claim, now)
    if manifest.status in {RunStatus.COMPLETED, RunStatus.BLOCKED, RunStatus.CANCELLED}:
        return inspect_provider_run(path, resolved_run_id)

    active_stage = manifest.current_stage
    try:
        planner = _run_planner_stage(
            path,
            manifest,
            llm_provider,
            settings,
            now,
        )
        active_stage = Stage.CLAIM_PLANNER
        _after_stage(path, resolved_run_id, PHASE9_PLANNER_CHECKPOINT, now, stage_hook)

        researchers = _run_researcher_stage(
            path,
            planner,
            search_provider,
            scraper_provider,
            llm_provider,
            settings,
            now,
        )
        active_stage = Stage.OPPOSING_RESEARCHER
        _after_stage(path, resolved_run_id, PHASE9_RESEARCHERS_CHECKPOINT, now, stage_hook)
        all_candidates = tuple(
            sorted(
                (*researchers.supporting.candidates, *researchers.opposing.candidates),
                key=lambda item: str(item.quote_block_id),
            )
        )
        if not all_candidates:
            raise Phase9OrchestrationError(
                Stage.OPPOSING_RESEARCHER,
                "researchers produced no candidate that passed deterministic filtering",
            )

        analysis = _run_analysis_stage(
            path,
            planner,
            researchers,
            llm_provider,
            settings,
            now,
        )
        active_stage = Stage.CLAIM_LEDGER
        _after_stage(path, resolved_run_id, PHASE9_ANALYSIS_CHECKPOINT, now, stage_hook)
        if not analysis.ledger_records:
            raise Phase9OrchestrationError(
                Stage.CLAIM_LEDGER,
                "no Reviewer-approved statement was eligible for the Ledger",
            )

        synthesis = _run_synthesis_stage(
            path,
            planner,
            analysis,
            llm_provider,
            settings,
            now,
        )
        active_stage = Stage.DEBATE_SYNTHESIZER
        _after_stage(path, resolved_run_id, PHASE9_SYNTHESIS_CHECKPOINT, now, stage_hook)

        validation = _run_validation_stage(
            path,
            synthesis,
            analysis,
            manifest.raw_claim,
            now,
        )
        active_stage = Stage.FINAL_RENDERER_VALIDATOR
        terminal_status = RunStatus.COMPLETED if validation.valid else RunStatus.BLOCKED
        _finish_run(path, resolved_run_id, terminal_status, active_stage, now)
        _checkpoint(
            path,
            resolved_run_id,
            PHASE9_VALIDATION_CHECKPOINT,
            CheckpointStatus.COMPLETED if validation.valid else CheckpointStatus.BLOCKED,
            now,
        )
    except Phase9Cancellation as exc:
        reason = str(exc)
        _finish_run(path, resolved_run_id, RunStatus.CANCELLED, active_stage, now)
        _checkpoint(
            path,
            resolved_run_id,
            f"cancelled-after-{_checkpoint_key_for_stage(active_stage)}",
            CheckpointStatus.CANCELLED,
            now,
        )
        return inspect_provider_run(path, resolved_run_id, failure_reason=reason)
    except Exception as exc:
        failed_stage = exc.stage if isinstance(exc, Phase9OrchestrationError) else active_stage
        reason = str(exc) or type(exc).__name__
        _finish_run(path, resolved_run_id, RunStatus.FAILED, failed_stage, now)
        _checkpoint(
            path,
            resolved_run_id,
            _failure_checkpoint_key(path, resolved_run_id, failed_stage),
            CheckpointStatus.FAILED,
            now,
            failure_reason=reason,
        )
        return inspect_provider_run(path, resolved_run_id, failure_reason=reason)

    return inspect_provider_run(path, resolved_run_id)


def inspect_provider_run(
    db_path: str | Path,
    run_id: UUID,
    *,
    failure_reason: str | None = None,
) -> ProviderPipelineResult:
    """Reopen and inspect a partial or terminal provider-backed run."""
    path = str(Path(db_path).resolve())
    init_db(path)
    manifest = read_run(path, run_id)
    checkpoints = tuple(read_orchestration_checkpoints(path, run_id))
    attempts = tuple(read_model_route_attempts(path, run_id))
    planner = _read_optional_planner(path, run_id)
    researchers = _read_optional_stage_result(
        path,
        run_id,
        PHASE9_RESEARCHERS_ARTIFACT,
        ResearcherPairResult,
    )
    analysis = _read_optional_stage_result(
        path,
        run_id,
        PHASE9_ANALYSIS_ARTIFACT,
        AnalysisStageResult,
    )
    synthesis = _read_optional_synthesis(path, run_id)
    validation = _read_optional_validation(path, run_id)
    status = _provider_status_from_manifest(manifest)
    resolved_failure = None
    if status is ProviderRunStatus.FAILED:
        resolved_failure = failure_reason or _latest_failure_reason(checkpoints)
    if status is ProviderRunStatus.CANCELLED and resolved_failure is None:
        resolved_failure = _cancellation_reason(path, run_id)
    final_brief = None
    rendered_hash = None
    if (
        status is ProviderRunStatus.RELEASED
        and synthesis is not None
        and analysis is not None
        and validation is not None
        and validation.valid
    ):
        final_brief = render_brief(
            synthesis,
            analysis.ledger_records,
            authoritative_claim=manifest.raw_claim,
        )
        rendered_hash = validation.rendered_brief_hash

    usages = [attempt.usage for attempt in attempts if attempt.usage is not None]
    token_values = [usage.total_tokens for usage in usages if usage.total_tokens is not None]
    cost_values = [usage.cost_usd for usage in usages if usage.cost_usd is not None]
    retrieval_count = 0
    if researchers is not None:
        for side in (researchers.supporting, researchers.opposing):
            if side.retrieval_batch is not None:
                retrieval_count += len(side.retrieval_batch.outcomes)
    return ProviderPipelineResult(
        run_id=run_id,
        status=status,
        raw_claim=manifest.raw_claim,
        db_path=path,
        current_stage=manifest.current_stage,
        failure_reason=resolved_failure,
        planner_output=planner,
        researcher_result=researchers,
        analysis_result=analysis,
        synthesis_output=synthesis,
        validation_result=validation,
        final_brief=final_brief,
        rendered_brief_hash=rendered_hash,
        checkpoints=checkpoints,
        model_attempts=attempts,
        retrieval_attempts_used=retrieval_count,
        model_calls_used=len(attempts),
        total_tokens=sum(cast(list[int], token_values)) if token_values else None,
        total_cost_usd=sum(cast(list[float], cost_values)) if cost_values else None,
    )


def request_run_cancellation(
    db_path: str | Path,
    run_id: UUID,
    *,
    reason: str = "cancellation requested by user",
    requested_at: datetime | None = None,
) -> RunCancellationRequest:
    """Persist a cancellation request that is honored at the next stage boundary."""
    path = str(Path(db_path).resolve())
    init_db(path)
    read_run(path, run_id)
    request = RunCancellationRequest(
        run_id=run_id,
        requested_at=requested_at or _phase9_utc_now(),
        reason=reason,
    )
    return insert_cancellation_request(path, request)


def _create_or_resume_provider_run(
    db_path: str,
    run_id: UUID,
    raw_claim: str,
    clock: Callable[[], datetime],
) -> RunManifest:
    try:
        existing = read_run(db_path, run_id)
    except KeyError:
        created_at = _aware_phase9_time(clock(), "created_at")
        manifest = RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim=raw_claim,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=created_at,
            updated_at=created_at,
        )
        insert_run(db_path, manifest)
        return manifest
    if existing.raw_claim != raw_claim:
        raise ValueError("existing run raw claim does not match the requested restart")
    if existing.status is RunStatus.FAILED:
        resumed = existing.model_copy(
            update={
                "status": RunStatus.RUNNING,
                "updated_at": _aware_phase9_time(clock(), "updated_at"),
                "completed_at": None,
            }
        )
        resumed = RunManifest.model_validate(resumed.model_dump(mode="python"))
        update_run(db_path, resumed)
        return resumed
    return existing


def _begin_stage(
    db_path: str,
    run_id: UUID,
    stage: Stage,
    stage_key: str,
    clock: Callable[[], datetime],
) -> None:
    manifest = read_run(db_path, run_id)
    updated_at = _aware_phase9_time(clock(), "updated_at")
    update_run(
        db_path,
        RunManifest(
            run_id=manifest.run_id,
            status=RunStatus.RUNNING,
            raw_claim=manifest.raw_claim,
            current_stage=stage,
            created_at=manifest.created_at,
            updated_at=updated_at,
        ),
    )
    _checkpoint(
        db_path,
        run_id,
        stage_key,
        CheckpointStatus.RUNNING,
        clock,
    )


def _checkpoint(
    db_path: str,
    run_id: UUID,
    stage_key: str,
    status: CheckpointStatus,
    clock: Callable[[], datetime],
    *,
    failure_reason: str | None = None,
) -> None:
    upsert_orchestration_checkpoint(
        db_path,
        OrchestrationCheckpoint(
            run_id=run_id,
            stage_key=stage_key,
            status=status,
            failure_reason=failure_reason,
            updated_at=_aware_phase9_time(clock(), "checkpoint updated_at"),
        ),
    )


def _checkpoint_is_completed(db_path: str, run_id: UUID, stage_key: str) -> bool:
    try:
        checkpoint = read_orchestration_checkpoint(db_path, run_id, stage_key)
    except KeyError:
        return False
    return checkpoint.status in {CheckpointStatus.COMPLETED, CheckpointStatus.BLOCKED}


def _finish_run(
    db_path: str,
    run_id: UUID,
    status: RunStatus,
    stage: Stage,
    clock: Callable[[], datetime],
) -> None:
    existing = read_run(db_path, run_id)
    finished_at = _aware_phase9_time(clock(), "completed_at")
    update_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=status,
            raw_claim=existing.raw_claim,
            current_stage=stage,
            created_at=existing.created_at,
            updated_at=finished_at,
            completed_at=finished_at,
        ),
    )


def _after_stage(
    db_path: str,
    run_id: UUID,
    stage_key: str,
    clock: Callable[[], datetime],
    stage_hook: _StageHook | None,
) -> None:
    if stage_hook is not None:
        stage_hook(run_id, stage_key)
    try:
        cancellation = read_cancellation_request(db_path, run_id)
    except KeyError:
        return
    raise Phase9Cancellation(cancellation.reason)


def _checkpoint_key_for_stage(stage: Stage) -> str:
    if stage is Stage.CLAIM_PLANNER:
        return PHASE9_PLANNER_CHECKPOINT
    if stage in {Stage.SUPPORTING_RESEARCHER, Stage.OPPOSING_RESEARCHER}:
        return PHASE9_RESEARCHERS_CHECKPOINT
    if stage in {Stage.EVIDENCE_ANALYST, Stage.STATEMENT_REVIEWER, Stage.CLAIM_LEDGER}:
        return PHASE9_ANALYSIS_CHECKPOINT
    if stage is Stage.DEBATE_SYNTHESIZER:
        return PHASE9_SYNTHESIS_CHECKPOINT
    return PHASE9_VALIDATION_CHECKPOINT


def _failure_checkpoint_key(db_path: str, run_id: UUID, stage: Stage) -> str:
    stage_key = _checkpoint_key_for_stage(stage)
    try:
        checkpoint = read_orchestration_checkpoint(db_path, run_id, stage_key)
    except KeyError:
        return stage_key
    if checkpoint.status in {CheckpointStatus.COMPLETED, CheckpointStatus.BLOCKED}:
        return f"failure-after-{stage_key}"
    return stage_key


def _persist_stage_result(
    db_path: str,
    run_id: UUID,
    artifact_key: str,
    result: StrictModel,
    clock: Callable[[], datetime],
) -> None:
    insert_stage_artifact(
        db_path,
        PersistedStageArtifact(
            run_id=run_id,
            artifact_key=artifact_key,
            artifact_type=type(result).__name__,
            payload_json=result.model_dump_json(),
            created_at=_aware_phase9_time(clock(), "artifact created_at"),
        ),
    )


def _read_optional_stage_result(
    db_path: str,
    run_id: UUID,
    artifact_key: str,
    model_type: type[_ModelT],
) -> _ModelT | None:
    try:
        artifact = read_stage_artifact(db_path, run_id, artifact_key)
    except KeyError:
        return None
    if artifact.artifact_type != model_type.__name__:
        raise Phase9OrchestrationError(
            Stage.FINAL_RENDERER_VALIDATOR,
            f"stored {artifact_key} has unexpected type {artifact.artifact_type}",
        )
    return model_type.model_validate_json(artifact.payload_json)


def _read_optional_planner(db_path: str, run_id: UUID) -> PlannerOutput | None:
    try:
        return read_planner_output(db_path, run_id)
    except KeyError:
        return None


def _read_optional_synthesis(db_path: str, run_id: UUID) -> SynthesisOutput | None:
    try:
        return read_synthesis(db_path, run_id)
    except KeyError:
        return None


def _read_optional_validation(db_path: str, run_id: UUID) -> ValidationResult | None:
    try:
        return read_validation(db_path, run_id)
    except KeyError:
        return None


def _provider_status_from_manifest(manifest: RunManifest) -> ProviderRunStatus:
    if manifest.status is RunStatus.COMPLETED:
        return ProviderRunStatus.RELEASED
    if manifest.status is RunStatus.BLOCKED:
        return ProviderRunStatus.BLOCKED
    if manifest.status is RunStatus.CANCELLED:
        return ProviderRunStatus.CANCELLED
    if manifest.status is RunStatus.FAILED:
        return ProviderRunStatus.FAILED
    return ProviderRunStatus.RUNNING


def _latest_failure_reason(checkpoints: Sequence[OrchestrationCheckpoint]) -> str | None:
    failures = [
        checkpoint for checkpoint in checkpoints if checkpoint.status is CheckpointStatus.FAILED
    ]
    if not failures:
        return None
    return max(failures, key=lambda item: item.updated_at).failure_reason


def _cancellation_reason(db_path: str, run_id: UUID) -> str:
    try:
        return read_cancellation_request(db_path, run_id).reason
    except KeyError:
        return "run was cancelled between stages"


def _run_planner_stage(
    db_path: str,
    manifest: RunManifest,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> PlannerOutput:
    if _checkpoint_is_completed(db_path, manifest.run_id, PHASE9_PLANNER_CHECKPOINT):
        return read_planner_output(db_path, manifest.run_id)
    _begin_stage(
        db_path,
        manifest.run_id,
        Stage.CLAIM_PLANNER,
        PHASE9_PLANNER_CHECKPOINT,
        clock,
    )
    planner_input = PlannerLLMInput(run_id=manifest.run_id, raw_claim=manifest.raw_claim)
    operation_id = _operation_id(manifest.run_id, "planner", manifest.run_id)

    def validate_planner(output: BaseModel, alias: ModelAlias) -> BaseModel:
        planner = _require_output(output, PlannerOutput)
        if planner.run_id != manifest.run_id:
            raise _validation_failure("Planner output run_id does not match the run")
        if planner.claim_definition.claim_text != manifest.raw_claim:
            raise _validation_failure("Planner claim text does not match the raw claim")
        _validate_llm_provenance(
            planner.planner_prompt_version,
            planner.planner_model_name,
            LLMStage.PLANNER,
            alias,
        )
        return planner

    planner = cast(
        PlannerOutput,
        _invoke_routed(
            db_path=db_path,
            provider=llm_provider,
            stage=LLMStage.PLANNER,
            input_artifact=planner_input,
            requested_output_type=PlannerOutput,
            input_artifact_ids=(manifest.run_id,),
            operation_id=operation_id,
            config=config,
            clock=clock,
            objective_validator=validate_planner,
        ),
    )
    _persist_model(
        db_path,
        planner,
        insert_planner_output,
        lambda: read_planner_output(db_path, manifest.run_id),
        "Phase 9 Planner output",
    )
    _checkpoint(
        db_path,
        manifest.run_id,
        PHASE9_PLANNER_CHECKPOINT,
        CheckpointStatus.COMPLETED,
        clock,
    )
    return planner


def _run_researcher_stage(
    db_path: str,
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> ResearcherPairResult:
    if _checkpoint_is_completed(db_path, planner.run_id, PHASE9_RESEARCHERS_CHECKPOINT):
        stored = _read_optional_stage_result(
            db_path,
            planner.run_id,
            PHASE9_RESEARCHERS_ARTIFACT,
            ResearcherPairResult,
        )
        if stored is None:
            raise Phase9OrchestrationError(
                Stage.OPPOSING_RESEARCHER,
                "completed Researcher checkpoint has no typed stage artifact",
            )
        return stored
    if config.budget.retrieval_attempts_per_side < ATTEMPTS_PER_STANCE:
        raise Phase9OrchestrationError(
            Stage.SUPPORTING_RESEARCHER,
            (
                "retrieval budget exceeded: each side requires "
                f"{ATTEMPTS_PER_STANCE} attempts but budget allows "
                f"{config.budget.retrieval_attempts_per_side}"
            ),
        )
    _begin_stage(
        db_path,
        planner.run_id,
        Stage.SUPPORTING_RESEARCHER,
        PHASE9_RESEARCHERS_CHECKPOINT,
        clock,
    )
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="phase9-researcher") as executor:
        supporting_future = executor.submit(
            _run_researcher_side,
            db_path,
            planner,
            "supporting",
            search_provider,
            scraper_provider,
            llm_provider,
            config,
            clock,
        )
        opposing_future = executor.submit(
            _run_researcher_side,
            db_path,
            planner,
            "opposing",
            search_provider,
            scraper_provider,
            llm_provider,
            config,
            clock,
        )
        supporting = supporting_future.result()
        opposing = opposing_future.result()

    pair = ResearcherPairResult(
        run_id=planner.run_id,
        supporting=supporting,
        opposing=opposing,
    )
    _persist_researcher_artifacts(db_path, planner, pair)
    _persist_stage_result(
        db_path,
        planner.run_id,
        PHASE9_RESEARCHERS_ARTIFACT,
        pair,
        clock,
    )
    if (
        supporting.status is ResearcherSideStatus.FAILED
        and opposing.status is ResearcherSideStatus.FAILED
    ):
        messages = [failure.message for failure in (*supporting.failures, *opposing.failures)]
        raise Phase9OrchestrationError(
            Stage.OPPOSING_RESEARCHER,
            f"both Researcher sides failed: {'; '.join(messages)}",
        )
    _checkpoint(
        db_path,
        planner.run_id,
        PHASE9_RESEARCHERS_CHECKPOINT,
        CheckpointStatus.COMPLETED,
        clock,
    )
    return pair


def _run_researcher_side(
    db_path: str,
    planner: PlannerOutput,
    stance: Literal["supporting", "opposing"],
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> ResearcherStageResult:
    failures: list[ResearcherFailure] = []
    try:
        if stance == "supporting":
            batch = retrieve_supporting(
                planner,
                search_provider,
                scraper_provider,
                retry_policy=config.retrieval_retry,
                clock=clock,
            )
        else:
            batch = retrieve_opposing(
                planner,
                search_provider,
                scraper_provider,
                retry_policy=config.retrieval_retry,
                clock=clock,
            )
    except Exception as exc:
        return ResearcherStageResult(
            run_id=planner.run_id,
            stance=stance,
            status=ResearcherSideStatus.FAILED,
            failures=(
                ResearcherFailure(
                    stage=f"{stance}_retrieval",
                    code="retrieval_failure",
                    message=str(exc) or type(exc).__name__,
                ),
            ),
        )

    provisionals: list[ProvisionalCandidate] = []
    candidates: list[CandidateQuoteBlock] = []
    claim_keywords = _claim_keywords_from_planner(planner)
    stance_value = batch.stance
    retrievals_by_id = {
        outcome.retrieval.retrieval_attempt_id: outcome.retrieval for outcome in batch.outcomes
    }
    for snapshot in batch.snapshots:
        retrieval = retrievals_by_id[snapshot.retrieval_attempt_id]
        extraction_input = build_extraction_llm_input(
            planner=planner,
            snapshot=snapshot,
            stance=stance_value,
            retrieval=retrieval,
        )
        operation_id = _operation_id(planner.run_id, "extractor", snapshot.snapshot_id)

        def validate_extraction(
            output: BaseModel,
            alias: ModelAlias,
            snapshot: SourceSnapshot = snapshot,
            batch: ResearcherRetrievalBatch = batch,
        ) -> BaseModel:
            provisional = _require_output(output, ProvisionalCandidate)
            _validate_provisional_for_snapshot(provisional, snapshot, batch, alias)
            filtered = filter_provisional_candidate(
                provisional,
                snapshot,
                claim_keywords=claim_keywords,
                post_filter_version=PHASE9_POST_FILTER_VERSION,
                validation_clock=clock,
            )
            if not filtered.valid or filtered.candidate is None:
                message = filtered.rejection_message or "deterministic extraction filter failed"
                code = _post_filter_failure_code(message)
                raise ObjectiveRoutingFailure(
                    code,
                    message,
                )
            return provisional

        try:
            provisional = cast(
                ProvisionalCandidate,
                _invoke_routed(
                    db_path=db_path,
                    provider=llm_provider,
                    stage=LLMStage.EXTRACTOR,
                    input_artifact=extraction_input,
                    requested_output_type=ProvisionalCandidate,
                    input_artifact_ids=(snapshot.snapshot_id,),
                    operation_id=operation_id,
                    config=config,
                    clock=clock,
                    objective_validator=validate_extraction,
                ),
            )
            filtered = filter_provisional_candidate(
                provisional,
                snapshot,
                claim_keywords=claim_keywords,
                post_filter_version=PHASE9_POST_FILTER_VERSION,
                validation_clock=clock,
            )
            if not filtered.valid or filtered.candidate is None:
                raise RuntimeError("completed Extractor output failed deterministic revalidation")
            provisionals.append(provisional)
            candidates.append(filtered.candidate)
        except Exception as exc:
            failures.append(
                ResearcherFailure(
                    stage=f"{stance}_extraction",
                    code="extraction_failure",
                    message=str(exc) or type(exc).__name__,
                    snapshot_id=snapshot.snapshot_id,
                )
            )

    retrieval_failed = any(outcome.retrieval.status.value == "failed" for outcome in batch.outcomes)
    if not candidates:
        failures.append(
            ResearcherFailure(
                stage=f"{stance}_extraction",
                code="no_passing_candidates",
                message="no Extractor output passed deterministic post-extraction filtering",
            )
        )
        side_status = ResearcherSideStatus.FAILED
    elif failures or retrieval_failed:
        side_status = ResearcherSideStatus.PARTIAL
    else:
        side_status = ResearcherSideStatus.COMPLETED
    return ResearcherStageResult(
        run_id=planner.run_id,
        stance=stance,
        status=side_status,
        retrieval_batch=batch,
        provisional_candidates=tuple(provisionals),
        candidates=tuple(candidates),
        failures=tuple(failures),
    )


def _persist_researcher_artifacts(
    db_path: str,
    planner: PlannerOutput,
    pair: ResearcherPairResult,
) -> None:
    planner_queries = {query.query_id: query for query in planner.search_queries}
    seen_snapshots: dict[UUID, SourceSnapshot] = {}
    for side in (pair.supporting, pair.opposing):
        batch = side.retrieval_batch
        if batch is None:
            continue
        retrieval_by_id = {
            outcome.retrieval.retrieval_attempt_id: outcome.retrieval for outcome in batch.outcomes
        }
        for outcome in batch.outcomes:
            retrieval = outcome.retrieval
            query = planner_queries.get(retrieval.query_id)
            if query is None or query.query_round != retrieval.query_round:
                raise Phase9OrchestrationError(
                    Stage.OPPOSING_RESEARCHER,
                    "Researcher retrieval does not match a Planner query",
                )
            _persist_model(
                db_path,
                retrieval,
                insert_retrieval_attempt,
                lambda retrieval=retrieval: read_retrieval_attempt(
                    db_path,
                    retrieval.retrieval_attempt_id,
                ),
                "Phase 9 retrieval attempt",
            )
        for snapshot in batch.snapshots:
            validate_snapshot_integrity(snapshot)
            retrieval = retrieval_by_id.get(snapshot.retrieval_attempt_id)
            if retrieval is None or snapshot.source_url != retrieval.resolved_url:
                raise Phase9OrchestrationError(
                    Stage.OPPOSING_RESEARCHER,
                    "snapshot provenance does not match its resolved retrieval",
                )
            duplicate = seen_snapshots.get(snapshot.snapshot_id)
            if duplicate is not None and duplicate != snapshot:
                raise Phase9OrchestrationError(
                    Stage.OPPOSING_RESEARCHER,
                    "duplicate snapshot ID carries different immutable content",
                )
            seen_snapshots[snapshot.snapshot_id] = snapshot
            _persist_model(
                db_path,
                snapshot,
                insert_snapshot,
                lambda snapshot=snapshot: read_snapshot(db_path, snapshot.snapshot_id),
                "Phase 9 snapshot",
            )
        for provisional in side.provisional_candidates:
            _persist_provisional_once(db_path, provisional)
        for candidate in side.candidates:
            _persist_model(
                db_path,
                candidate,
                insert_candidate,
                lambda candidate=candidate: read_candidate(db_path, candidate.quote_block_id),
                "Phase 9 candidate",
            )


def _persist_provisional_once(db_path: str, provisional: ProvisionalCandidate) -> None:
    existing = [
        item
        for item in read_provisional_extractions(db_path, provisional.run_id)
        if item.snapshot_id == provisional.snapshot_id and item.stance is provisional.stance
    ]
    if existing:
        if len(existing) != 1 or existing[0].model_dump(mode="json") != provisional.model_dump(
            mode="json"
        ):
            raise Phase9OrchestrationError(
                Stage.OPPOSING_RESEARCHER,
                "existing provisional extraction differs from the restart artifact",
            )
        return
    insert_provisional_extraction(db_path, provisional)


def _validate_provisional_for_snapshot(
    provisional: ProvisionalCandidate,
    snapshot: SourceSnapshot,
    batch: ResearcherRetrievalBatch,
    alias: ModelAlias,
) -> None:
    retrievals = {
        outcome.retrieval.retrieval_attempt_id: outcome.retrieval for outcome in batch.outcomes
    }
    retrieval = retrievals.get(snapshot.retrieval_attempt_id)
    if retrieval is None:
        raise _validation_failure("snapshot has no Researcher retrieval outcome")
    required_pairs = (
        (provisional.run_id, snapshot.run_id, "run_id"),
        (provisional.snapshot_id, snapshot.snapshot_id, "snapshot_id"),
        (provisional.snapshot_sha256, snapshot.snapshot_sha256, "snapshot hash"),
        (
            provisional.retrieval_attempt_id,
            snapshot.retrieval_attempt_id,
            "retrieval_attempt_id",
        ),
        (provisional.query_id, retrieval.query_id, "query_id"),
        (provisional.query_round, retrieval.query_round, "query_round"),
        (provisional.search_rank, retrieval.search_rank, "search_rank"),
        (provisional.source_url, snapshot.source_url, "source_url"),
        (provisional.stance, batch.stance, "stance"),
    )
    for actual, expected, label in required_pairs:
        if actual != expected:
            raise _validation_failure(f"Extractor output {label} does not match its snapshot")
    _validate_llm_provenance(
        provisional.extraction_prompt_version,
        provisional.extraction_model_name,
        LLMStage.EXTRACTOR,
        alias,
    )


def _post_filter_failure_code(message: str) -> str:
    lowered = message.casefold()
    exact_quote_markers = (
        "segment",
        "offset",
        "bracket",
        "surround",
        "quote",
        "snapshot text",
        "end of text",
    )
    if any(marker in lowered for marker in exact_quote_markers):
        return "exact_quote_failure"
    return "deterministic_validation_failure"


def _run_analysis_stage(
    db_path: str,
    planner: PlannerOutput,
    researchers: ResearcherPairResult,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> AnalysisStageResult:
    if _checkpoint_is_completed(db_path, planner.run_id, PHASE9_ANALYSIS_CHECKPOINT):
        stored = _read_optional_stage_result(
            db_path,
            planner.run_id,
            PHASE9_ANALYSIS_ARTIFACT,
            AnalysisStageResult,
        )
        if stored is None:
            raise Phase9OrchestrationError(
                Stage.CLAIM_LEDGER,
                "completed analysis checkpoint has no typed stage artifact",
            )
        return stored
    _begin_stage(
        db_path,
        planner.run_id,
        Stage.EVIDENCE_ANALYST,
        PHASE9_ANALYSIS_CHECKPOINT,
        clock,
    )
    snapshots = _snapshot_lookup(researchers)
    candidates = sorted(
        (*researchers.supporting.candidates, *researchers.opposing.candidates),
        key=lambda item: str(item.quote_block_id),
    )
    decisions: list[ScoreDecision] = []
    drafts: list[StatementDraft] = []
    reviews: list[StatementReviewResult] = []
    ledgers: list[LedgerRecord] = []
    rejected: list[UUID] = []

    for candidate in candidates:
        snapshot = snapshots.get(candidate.snapshot_id)
        if snapshot is None:
            raise Phase9OrchestrationError(
                Stage.EVIDENCE_ANALYST,
                f"candidate {candidate.quote_block_id} has no trusted snapshot",
            )
        analyst_input = build_analyst_llm_input(
            claim_definition=planner.claim_definition,
            candidate=candidate,
            snapshot=snapshot,
        )
        score_operation = _operation_id(
            planner.run_id,
            "analyst-score",
            candidate.quote_block_id,
        )

        def validate_score(
            output: BaseModel,
            alias: ModelAlias,
            candidate: CandidateQuoteBlock = candidate,
        ) -> BaseModel:
            decision = _require_output(output, ScoreDecision)
            if (
                decision.run_id != candidate.run_id
                or decision.quote_block_id != candidate.quote_block_id
            ):
                raise _validation_failure("Analyst score output does not match the candidate")
            _validate_llm_provenance(
                decision.analyst_prompt_version,
                decision.analyst_model_name,
                LLMStage.ANALYST,
                alias,
            )
            return decision

        decision = cast(
            ScoreDecision,
            _invoke_routed(
                db_path=db_path,
                provider=llm_provider,
                stage=LLMStage.ANALYST,
                input_artifact=analyst_input,
                requested_output_type=ScoreDecision,
                input_artifact_ids=(candidate.quote_block_id, candidate.snapshot_id),
                operation_id=score_operation,
                config=config,
                clock=clock,
                objective_validator=validate_score,
            ),
        )
        decisions.append(decision)
        _persist_model(
            db_path,
            decision,
            insert_analyst_decision,
            lambda decision=decision: read_analyst_decision(
                db_path,
                decision.run_id,
                decision.quote_block_id,
            ),
            "Phase 9 Analyst decision",
        )
        if not decision.approved:
            rejected.append(candidate.quote_block_id)
            continue

        candidate_drafts: list[StatementDraft] = []
        candidate_reviews: list[StatementReviewResult] = []
        first_draft = _invoke_statement_draft(
            db_path,
            llm_provider,
            analyst_input,
            candidate,
            decision,
            revision_number=0,
            previous_draft_ids=(),
            config=config,
            clock=clock,
        )
        candidate_drafts.append(first_draft)
        drafts.append(first_draft)
        _persist_model(
            db_path,
            first_draft,
            insert_statement_draft,
            lambda draft=first_draft: read_statement_draft(db_path, draft.statement_draft_id),
            "Phase 9 statement draft",
        )
        first_review = _invoke_statement_review(
            db_path,
            llm_provider,
            candidate,
            first_draft,
            revision_number=0,
            config=config,
            clock=clock,
        )
        candidate_reviews.append(first_review)
        reviews.append(first_review)
        _persist_model(
            db_path,
            first_review,
            insert_statement_review,
            lambda review=first_review: read_statement_review(
                db_path,
                review.run_id,
                review.statement_draft_id,
            ),
            "Phase 9 Reviewer decision",
        )

        final_review = first_review
        if not first_review.approved:
            revised_draft = _invoke_statement_draft(
                db_path,
                llm_provider,
                analyst_input,
                candidate,
                decision,
                revision_number=1,
                previous_draft_ids=(first_draft.statement_draft_id,),
                config=config,
                clock=clock,
            )
            candidate_drafts.append(revised_draft)
            drafts.append(revised_draft)
            _persist_model(
                db_path,
                revised_draft,
                insert_statement_draft,
                lambda draft=revised_draft: read_statement_draft(
                    db_path,
                    draft.statement_draft_id,
                ),
                "Phase 9 revised statement draft",
            )
            second_review = _invoke_statement_review(
                db_path,
                llm_provider,
                candidate,
                revised_draft,
                revision_number=1,
                config=config,
                clock=clock,
            )
            candidate_reviews.append(second_review)
            reviews.append(second_review)
            _persist_model(
                db_path,
                second_review,
                insert_statement_review,
                lambda review=second_review: read_statement_review(
                    db_path,
                    review.run_id,
                    review.statement_draft_id,
                ),
                "Phase 9 second Reviewer decision",
            )
            final_review = second_review

        if not final_review.approved or final_review.approved_factual_statement is None:
            rejected.append(candidate.quote_block_id)
            continue
        ledger = admit_ledger_record(
            LedgerAdmissionRequest(
                candidate=candidate,
                snapshot=snapshot,
                score_decision=decision,
                statement_drafts=candidate_drafts,
                review_results=candidate_reviews,
                approved_factual_statement=final_review.approved_factual_statement,
                entailment=(Entailment.PARTIAL if decision.claim_fit == 3 else Entailment.STRONG),
            ),
            derive_ledger_claim_id=derive_phase9_ledger_claim_id,
            validation_clock=clock,
        )
        ledgers.append(ledger)
        _persist_model(
            db_path,
            ledger,
            insert_ledger_record,
            lambda ledger=ledger: read_ledger_record(db_path, ledger.ledger_claim_id),
            "Phase 9 Ledger record",
        )

    result = AnalysisStageResult(
        run_id=planner.run_id,
        analyst_decisions=tuple(decisions),
        statement_drafts=tuple(drafts),
        reviewer_decisions=tuple(reviews),
        ledger_records=tuple(sorted(ledgers, key=lambda item: str(item.ledger_claim_id))),
        rejected_quote_block_ids=tuple(sorted(set(rejected), key=str)),
    )
    _persist_stage_result(
        db_path,
        planner.run_id,
        PHASE9_ANALYSIS_ARTIFACT,
        result,
        clock,
    )
    _checkpoint(
        db_path,
        planner.run_id,
        PHASE9_ANALYSIS_CHECKPOINT,
        CheckpointStatus.COMPLETED,
        clock,
    )
    return result


def _invoke_statement_draft(
    db_path: str,
    provider: LLMProvider,
    analyst_input: BaseModel,
    candidate: CandidateQuoteBlock,
    decision: ScoreDecision,
    *,
    revision_number: int,
    previous_draft_ids: tuple[UUID, ...],
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> StatementDraft:
    operation_id = _operation_id(
        candidate.run_id,
        f"analyst-draft-{revision_number}",
        candidate.quote_block_id,
    )

    def validate_draft(output: BaseModel, alias: ModelAlias) -> BaseModel:
        draft = _require_output(output, StatementDraft)
        if (
            draft.run_id != candidate.run_id
            or draft.quote_block_id != candidate.quote_block_id
            or draft.stance is not candidate.stance
            or draft.claim_fit != decision.claim_fit
        ):
            raise _validation_failure("Analyst statement draft does not match the candidate")
        if draft.statement_draft_id in previous_draft_ids:
            raise _validation_failure("revised statement draft must use a new deterministic ID")
        _validate_llm_provenance(
            draft.analyst_prompt_version,
            draft.analyst_model_name,
            LLMStage.ANALYST,
            alias,
        )
        return draft

    return cast(
        StatementDraft,
        _invoke_routed(
            db_path=db_path,
            provider=provider,
            stage=LLMStage.ANALYST,
            input_artifact=analyst_input,
            requested_output_type=StatementDraft,
            input_artifact_ids=(candidate.quote_block_id,),
            operation_id=operation_id,
            config=config,
            clock=clock,
            objective_validator=validate_draft,
        ),
    )


def _invoke_statement_review(
    db_path: str,
    provider: LLMProvider,
    candidate: CandidateQuoteBlock,
    draft: StatementDraft,
    *,
    revision_number: int,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> StatementReviewResult:
    reviewer_input = build_reviewer_input(candidate, draft)
    operation_id = _operation_id(
        candidate.run_id,
        f"reviewer-{revision_number}",
        draft.statement_draft_id,
    )

    validated_alias: ModelAlias | None = None

    def validate_review(output: BaseModel, alias: ModelAlias) -> BaseModel:
        nonlocal validated_alias
        decision = _require_output(output, ReviewerDecision)
        try:
            validate_reviewer_decision(draft, reviewer_input, decision)
        except ValueError as exc:
            raise _validation_failure(str(exc)) from exc
        prompt_version = load_prompt(LLMStage.REVIEWER).version
        _validate_llm_provenance(
            prompt_version,
            alias.value,
            LLMStage.REVIEWER,
            alias,
        )
        validated_alias = alias
        return decision

    decision = cast(
        ReviewerDecision,
        _invoke_routed(
            db_path=db_path,
            provider=provider,
            stage=LLMStage.REVIEWER,
            input_artifact=reviewer_input,
            requested_output_type=ReviewerDecision,
            input_artifact_ids=(draft.statement_draft_id, candidate.quote_block_id),
            operation_id=operation_id,
            config=config,
            clock=clock,
            objective_validator=validate_review,
            run_id=candidate.run_id,
        ),
    )
    if validated_alias is None:
        raise RuntimeError("Reviewer route validation did not record the selected model alias")
    return build_statement_review_result(
        draft,
        reviewer_input,
        decision,
        reviewer_prompt_version=load_prompt(LLMStage.REVIEWER).version,
        reviewer_model_name=validated_alias.value,
        reviewed_at=_aware_phase9_time(clock(), "reviewed_at"),
    )


def derive_phase9_ledger_claim_id(
    payload: ValidatedLedgerPayload,
) -> UUID:
    review = payload.approved_review
    if (
        not review.approved
        or review.reviewer_approval_id is None
        or review.approved_factual_statement is None
    ):
        raise ValueError("an approved Reviewer result is required for Ledger ID derivation")
    return uuid5(
        URL_NAMESPACE,
        (
            f"{PHASE9_LEDGER_ID_VERSION}::{payload.candidate.run_id}::"
            f"{review.reviewer_approval_id}::{review.approved_factual_statement}"
        ),
    )


def _snapshot_lookup(researchers: ResearcherPairResult) -> dict[UUID, SourceSnapshot]:
    snapshots: dict[UUID, SourceSnapshot] = {}
    for side in (researchers.supporting, researchers.opposing):
        if side.retrieval_batch is None:
            continue
        for snapshot in side.retrieval_batch.snapshots:
            existing = snapshots.get(snapshot.snapshot_id)
            if existing is not None and existing != snapshot:
                raise Phase9OrchestrationError(
                    Stage.EVIDENCE_ANALYST,
                    "duplicate snapshot ID carries conflicting immutable data",
                )
            snapshots[snapshot.snapshot_id] = snapshot
    return snapshots


def _run_synthesis_stage(
    db_path: str,
    planner: PlannerOutput,
    analysis: AnalysisStageResult,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> SynthesisOutput:
    if _checkpoint_is_completed(db_path, planner.run_id, PHASE9_SYNTHESIS_CHECKPOINT):
        return read_synthesis(db_path, planner.run_id)
    _begin_stage(
        db_path,
        planner.run_id,
        Stage.DEBATE_SYNTHESIZER,
        PHASE9_SYNTHESIS_CHECKPOINT,
        clock,
    )
    synthesis_input = SynthesizerLLMInput(
        run_id=planner.run_id,
        ledger_records=analysis.ledger_records,
    )
    ledger_ids = tuple(record.ledger_claim_id for record in analysis.ledger_records)
    operation_id = _operation_id(planner.run_id, "synthesizer", planner.run_id)

    def validate_synthesis(output: BaseModel, alias: ModelAlias) -> BaseModel:
        synthesis = _require_output(output, SynthesisOutput)
        if synthesis.run_id != planner.run_id:
            raise _validation_failure("Synthesizer output run_id does not match the run")
        _validate_llm_provenance(
            synthesis.synthesizer_prompt_version,
            synthesis.synthesizer_model_name,
            LLMStage.SYNTHESIZER,
            alias,
        )
        return synthesis

    synthesis = cast(
        SynthesisOutput,
        _invoke_routed(
            db_path=db_path,
            provider=llm_provider,
            stage=LLMStage.SYNTHESIZER,
            input_artifact=synthesis_input,
            requested_output_type=SynthesisOutput,
            input_artifact_ids=ledger_ids,
            operation_id=operation_id,
            config=config,
            clock=clock,
            objective_validator=validate_synthesis,
        ),
    )
    _persist_model(
        db_path,
        synthesis,
        insert_synthesis,
        lambda: read_synthesis(db_path, planner.run_id),
        "Phase 9 synthesis output",
    )
    _checkpoint(
        db_path,
        planner.run_id,
        PHASE9_SYNTHESIS_CHECKPOINT,
        CheckpointStatus.COMPLETED,
        clock,
    )
    return synthesis


def _run_validation_stage(
    db_path: str,
    synthesis: SynthesisOutput,
    analysis: AnalysisStageResult,
    authoritative_claim: str,
    clock: Callable[[], datetime],
) -> ValidationResult:
    existing = _read_optional_validation(db_path, synthesis.run_id)
    if existing is not None:
        return existing
    _begin_stage(
        db_path,
        synthesis.run_id,
        Stage.FINAL_RENDERER_VALIDATOR,
        PHASE9_VALIDATION_CHECKPOINT,
        clock,
    )
    validation = validate_final_release(
        synthesis,
        analysis.ledger_records,
        authoritative_claim=authoritative_claim,
        validated_at=_aware_phase9_time(clock(), "validated_at"),
    )
    _persist_model(
        db_path,
        validation,
        insert_validation,
        lambda: read_validation(db_path, synthesis.run_id),
        "Phase 9 validation result",
    )
    return validation


def _invoke_routed(
    *,
    db_path: str,
    provider: LLMProvider,
    stage: LLMStage,
    input_artifact: BaseModel,
    requested_output_type: type[_ModelT],
    input_artifact_ids: tuple[UUID, ...],
    operation_id: UUID,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
    objective_validator: _ObjectiveValidator,
    run_id: UUID | None = None,
) -> _ModelT:
    resolved_run_id = run_id or getattr(input_artifact, "run_id", None)
    if not isinstance(resolved_run_id, UUID):
        raise ValueError("routed invocation requires an explicit UUID run_id")
    _enforce_usage_budget(db_path, resolved_run_id, config, stage)
    aliases = (
        config.routing.for_stage(stage).primary,
        *config.routing.for_stage(stage).fallbacks,
    )
    route_index = 0
    attempt_number = 1
    previous_failure: ModelRouteAttempt | None = None

    while route_index < len(aliases):
        alias = aliases[route_index]
        attempts = read_model_route_attempts(db_path, resolved_run_id, operation_id)
        existing = next(
            (
                item
                for item in attempts
                if item.route_index == route_index and item.attempt_number == attempt_number
            ),
            None,
        )
        if existing is not None and existing.status is ModelAttemptStatus.RUNNING:
            existing = _fail_interrupted_attempt(db_path, existing, clock)
        if existing is not None and existing.status is ModelAttemptStatus.COMPLETED:
            if existing.output_type != requested_output_type.__name__:
                raise Phase9OrchestrationError(
                    _agent_stage(stage),
                    "cached route attempt output type does not match the requested schema",
                )
            output = requested_output_type.model_validate_json(existing.output_json)
            validated = objective_validator(output, alias)
            _enforce_usage_budget(db_path, resolved_run_id, config, stage)
            return requested_output_type.model_validate(
                validated.model_dump(mode="python", round_trip=True)
            )
        if existing is not None:
            previous_failure = existing
            next_position = _next_route_position(
                stage,
                route_index,
                attempt_number,
                existing.failure_code or "non_retryable_failure",
                len(aliases),
                config.retries.max_attempts_per_alias,
            )
            if next_position is None:
                raise Phase9OrchestrationError(
                    _agent_stage(stage),
                    (
                        f"{stage.value} exhausted configured route after "
                        f"{existing.failure_code}: {existing.failure_reason}"
                    ),
                )
            route_index, attempt_number = next_position
            continue

        retry_reason = None
        escalation_reason = None
        if previous_failure is not None:
            reason = f"{previous_failure.failure_code}: {previous_failure.failure_reason}"
            if previous_failure.route_index == route_index:
                retry_reason = reason
            else:
                escalation_reason = reason
        attempt_id = _attempt_id(
            resolved_run_id,
            operation_id,
            alias,
            route_index,
            attempt_number,
        )
        started_at = _aware_phase9_time(clock(), "attempt started_at")
        reservation = ModelRouteAttempt(
            run_id=resolved_run_id,
            operation_id=operation_id,
            attempt_id=attempt_id,
            stage=stage.value,
            output_type=requested_output_type.__name__,
            model_alias=alias.value,
            pinned_model_snapshot=config.pinned_snapshot_for(alias),
            route_index=route_index,
            attempt_number=attempt_number,
            input_artifact_ids=input_artifact_ids,
            status=ModelAttemptStatus.RUNNING,
            retry_reason=retry_reason,
            escalation_reason=escalation_reason,
            started_at=started_at,
        )
        try:
            reserved = reserve_model_route_attempt(
                db_path,
                reservation,
                max_model_calls=config.budget.max_model_calls,
            )
        except ModelAttemptBudgetError as exc:
            raise Phase9OrchestrationError(_agent_stage(stage), str(exc)) from exc
        if reserved.status is not ModelAttemptStatus.RUNNING:
            previous_failure = reserved
            continue
        request = build_stage_request(
            stage=stage,
            input_artifact=input_artifact,
            requested_output_type=requested_output_type,
            input_artifact_ids=input_artifact_ids,
            routing=config.routing,
            pinned_model_snapshot=config.pinned_snapshot_for(alias),
            model_alias=alias,
            run_id=resolved_run_id,
        )
        output: _ModelT | None = None
        usage: ModelUsageMetadata | None = None
        try:
            invocation = invoke_llm(
                provider,
                request,
                retry_metadata=RetryMetadata(
                    attempt_number=attempt_number,
                    max_attempts=config.retries.max_attempts_per_alias,
                    retry_count=attempt_number - 1,
                    automatic_retry_performed=attempt_number > 1,
                ),
                clock=clock,
                invocation_id_factory=lambda attempt_id=attempt_id: attempt_id,
            )
            output = requested_output_type.model_validate(
                invocation.output_artifact.model_dump(mode="python", round_trip=True)
            )
            usage = _read_provider_usage(provider, request, output, invocation.record)
            validated = objective_validator(output, alias)
            finished = _finished_attempt(
                reservation,
                status=ModelAttemptStatus.COMPLETED,
                ended_at=invocation.record.ended_at,
                usage=usage,
                output_json=validated.model_dump_json(),
            )
        except LLMInvocationError as exc:
            code = _invocation_failure_code(exc)
            finished = _finished_attempt(
                reservation,
                status=ModelAttemptStatus.FAILED,
                ended_at=exc.record.ended_at,
                failure_code=code,
                failure_reason=exc.record.failure.message if exc.record.failure else str(exc),
            )
        except ObjectiveRoutingFailure as exc:
            finished = _finished_attempt(
                reservation,
                status=ModelAttemptStatus.FAILED,
                ended_at=_aware_phase9_time(clock(), "attempt ended_at"),
                usage=usage,
                failure_code=exc.code,
                failure_reason=str(exc),
                output_json=output.model_dump_json(),
            )
        except Exception as exc:
            finished = _finished_attempt(
                reservation,
                status=ModelAttemptStatus.FAILED,
                ended_at=_aware_phase9_time(clock(), "attempt ended_at"),
                usage=usage,
                failure_code="deterministic_validation_failure",
                failure_reason=str(exc) or type(exc).__name__,
                output_json=output.model_dump_json() if output is not None else None,
            )
        finish_model_route_attempt(db_path, finished)
        if finished.status is ModelAttemptStatus.COMPLETED:
            _enforce_usage_budget(db_path, resolved_run_id, config, stage)
            return requested_output_type.model_validate_json(finished.output_json)
        previous_failure = finished
        next_position = _next_route_position(
            stage,
            route_index,
            attempt_number,
            finished.failure_code or "non_retryable_failure",
            len(aliases),
            config.retries.max_attempts_per_alias,
        )
        if next_position is None:
            raise Phase9OrchestrationError(
                _agent_stage(stage),
                (
                    f"{stage.value} exhausted configured route after "
                    f"{finished.failure_code}: {finished.failure_reason}"
                ),
            )
        route_index, attempt_number = next_position

    raise Phase9OrchestrationError(_agent_stage(stage), f"{stage.value} route is exhausted")


def _next_route_position(
    stage: LLMStage,
    route_index: int,
    attempt_number: int,
    failure_code: str,
    route_length: int,
    max_attempts_per_alias: int,
) -> tuple[int, int] | None:
    if failure_code in _RETRYABLE_FAILURE_CODES and attempt_number < max_attempts_per_alias:
        return route_index, attempt_number + 1
    next_index = route_index + 1
    if next_index >= route_length:
        return None
    if stage is LLMStage.EXTRACTOR:
        if route_index == 0 and failure_code in _EXTRACTOR_PRO_ESCALATION_CODES:
            return next_index, 1
        if route_index == 1 and failure_code in _AVAILABILITY_FAILURE_CODES:
            return next_index, 1
        return None
    if failure_code in _RETRYABLE_FAILURE_CODES:
        return next_index, 1
    return None


def _finished_attempt(
    reservation: ModelRouteAttempt,
    *,
    status: ModelAttemptStatus,
    ended_at: datetime,
    usage: ModelUsageMetadata | None = None,
    output_json: str | None = None,
    failure_code: str | None = None,
    failure_reason: str | None = None,
) -> ModelRouteAttempt:
    latency_ms = max(0.0, (ended_at - reservation.started_at).total_seconds() * 1_000)
    return ModelRouteAttempt(
        run_id=reservation.run_id,
        operation_id=reservation.operation_id,
        attempt_id=reservation.attempt_id,
        stage=reservation.stage,
        output_type=reservation.output_type,
        model_alias=reservation.model_alias,
        pinned_model_snapshot=reservation.pinned_model_snapshot,
        route_index=reservation.route_index,
        attempt_number=reservation.attempt_number,
        input_artifact_ids=reservation.input_artifact_ids,
        status=status,
        retry_reason=reservation.retry_reason,
        escalation_reason=reservation.escalation_reason,
        failure_code=failure_code,
        failure_reason=failure_reason,
        started_at=reservation.started_at,
        ended_at=ended_at,
        latency_ms=latency_ms,
        usage=usage,
        output_json=output_json,
    )


def _fail_interrupted_attempt(
    db_path: str,
    attempt: ModelRouteAttempt,
    clock: Callable[[], datetime],
) -> ModelRouteAttempt:
    finished = _finished_attempt(
        attempt,
        status=ModelAttemptStatus.FAILED,
        ended_at=_aware_phase9_time(clock(), "interrupted attempt ended_at"),
        failure_code="interrupted_attempt",
        failure_reason="attempt was interrupted before a completion record was persisted",
    )
    finish_model_route_attempt(db_path, finished)
    return finished


def _read_provider_usage(
    provider: LLMProvider,
    request: object,
    output: BaseModel,
    invocation_record: object,
) -> ModelUsageMetadata | None:
    usage_reader = getattr(provider, "usage_for", None)
    if usage_reader is None:
        return None
    if not callable(usage_reader):
        raise ValueError("provider usage_for attribute must be callable")
    usage = usage_reader(request, output, invocation_record)
    if usage is None:
        return None
    if not isinstance(usage, ModelUsageMetadata):
        raise ValueError("provider usage metadata must be a ModelUsageMetadata artifact")
    return usage


def _enforce_usage_budget(
    db_path: str,
    run_id: UUID,
    config: ProviderOrchestrationConfig,
    stage: LLMStage,
) -> None:
    attempts = read_model_route_attempts(db_path, run_id)
    total_tokens = 0
    any_tokens = False
    total_cost = 0.0
    any_cost = False
    for attempt in attempts:
        if attempt.usage is None:
            continue
        usage_tokens = _usage_token_total(attempt.usage)
        if usage_tokens is not None:
            total_tokens += usage_tokens
            any_tokens = True
        if attempt.usage.cost_usd is not None:
            total_cost += attempt.usage.cost_usd
            any_cost = True
    if (
        config.budget.max_total_tokens is not None
        and any_tokens
        and total_tokens > config.budget.max_total_tokens
    ):
        raise Phase9OrchestrationError(
            _agent_stage(stage),
            (
                f"model token budget {config.budget.max_total_tokens} exceeded "
                f"with {total_tokens} recorded tokens"
            ),
        )
    if (
        config.budget.max_total_cost_usd is not None
        and any_cost
        and total_cost > config.budget.max_total_cost_usd
    ):
        raise Phase9OrchestrationError(
            _agent_stage(stage),
            (
                f"model cost budget {config.budget.max_total_cost_usd} exceeded "
                f"with {total_cost:.6f} recorded USD"
            ),
        )


def _usage_token_total(usage: ModelUsageMetadata) -> int | None:
    if usage.total_tokens is not None:
        return usage.total_tokens
    if usage.input_tokens is not None and usage.output_tokens is not None:
        return usage.input_tokens + usage.output_tokens
    return None


def _invocation_failure_code(exc: LLMInvocationError) -> str:
    failure = exc.record.failure
    if failure is None:
        return "transient_failure"
    if failure.code is InvocationFailureCode.UNSUPPORTED_PARAMETER:
        return "configuration_error"
    if failure.code is InvocationFailureCode.NON_PYDANTIC_RESPONSE:
        return "malformed_output"
    if failure.code is InvocationFailureCode.SCHEMA_VALIDATION_FAILED:
        return "schema_validation_failure"
    cause = exc.__cause__
    if isinstance(cause, TimeoutError):
        return "timeout"
    return "transient_failure"


def _require_output(output: BaseModel, model_type: type[_ModelT]) -> _ModelT:
    if not isinstance(output, model_type):
        raise _validation_failure(
            f"stage returned {type(output).__name__}; expected {model_type.__name__}"
        )
    return output


def _validate_llm_provenance(
    artifact_prompt_version: str,
    artifact_model_name: str,
    stage: LLMStage,
    alias: ModelAlias,
) -> None:
    expected_prompt = load_prompt(stage)
    if artifact_prompt_version != expected_prompt.version:
        raise _validation_failure(
            f"{stage.value} artifact prompt version does not match the loaded prompt"
        )
    if artifact_model_name != alias.value:
        raise _validation_failure(
            f"{stage.value} artifact model provenance does not match the routed alias"
        )


def _validation_failure(message: str) -> ObjectiveRoutingFailure:
    return ObjectiveRoutingFailure(
        "deterministic_validation_failure",
        message,
    )


def _operation_id(run_id: UUID, operation: str, artifact_id: UUID) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"phase9-operation::{run_id}::{operation}::{artifact_id}",
    )


def _attempt_id(
    run_id: UUID,
    operation_id: UUID,
    alias: ModelAlias,
    route_index: int,
    attempt_number: int,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        (
            f"phase9-attempt::{run_id}::{operation_id}::{alias.value}::"
            f"{route_index}::{attempt_number}"
        ),
    )


def _agent_stage(stage: LLMStage) -> Stage:
    if stage is LLMStage.PLANNER:
        return Stage.CLAIM_PLANNER
    if stage is LLMStage.EXTRACTOR:
        return Stage.SUPPORTING_RESEARCHER
    if stage is LLMStage.ANALYST:
        return Stage.EVIDENCE_ANALYST
    if stage is LLMStage.REVIEWER:
        return Stage.STATEMENT_REVIEWER
    return Stage.DEBATE_SYNTHESIZER


def _aware_phase9_time(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _phase9_utc_now() -> datetime:
    return datetime.now(UTC)
