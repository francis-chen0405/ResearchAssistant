from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from agents.analyst import (
    AnalystLLMInput,
    LedgerAdmissionRequest,
    StatementDraftLLMInput,
    ValidatedLedgerPayload,
    admit_ledger_record,
    build_analyst_llm_input,
)
from agents.opposingresearcher import retrieve_opposing
from agents.planner import PlannerLLMInput
from agents.renderer import render_brief, validate_final_release
from agents.researcher import (
    LEGACY_FIXTURE_QUOTE_LENGTH_POLICY,
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
    AcquisitionPolicy,
    CooperativeCancellation,
    DeduplicationState,
    ExtractionLLMInput,
    ResearcherRetrievalBatch,
    build_extraction_llm_input,
    build_provisional_candidate_from_selection,
    retrieve_supporting,
)
from agents.synthesizer import SynthesizerLLMInput
from evidence_portfolio import assess_portfolio, identify_source_family
from models import (
    DEFAULT_RESEARCH_CONTROLS,
    CandidateBatch,
    CandidateQuoteBlock,
    CheckpointStatus,
    Entailment,
    EvidenceRole,
    EvidenceTrailEntry,
    EvidenceTrailOutcome,
    LedgerRecord,
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageAccounting,
    ModelUsageMetadata,
    OrchestrationCheckpoint,
    PersistedStageArtifact,
    PlannerOutput,
    PortfolioCoverageAssessment,
    PortfolioExpansionRequest,
    PortfolioItem,
    ProviderRunContract,
    ProvisionalCandidate,
    ResearchControls,
    ResearchGovernorBudgetState,
    ResearchGovernorDecision,
    ResearchGovernorEvaluationInput,
    ResearchRound,
    ResearchRoundRecord,
    ResearchRoundStatus,
    ResearchTerminalResult,
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
    VerbatimQuoteSelection,
    entailment_for_claim_fit,
)
from money import ExactUSD, add_usd
from providers.llm import (
    DEFAULT_LLM_ROUTING,
    DIRECT_MIMO_ROUTING,
    InvocationFailureCode,
    LLMInvocationError,
    LLMProvider,
    LLMRequest,
    LLMRoutingConfig,
    LLMStage,
    ModelAlias,
    RetryMetadata,
    build_stage_request,
    invoke_llm,
    load_prompt,
)
from providers.pricing import (
    COMPATIBILITY_PRICE_CAPS,
    DIRECT_MIMO_PRICE_CAP,
    conservative_token_estimate,
)
from providers.scraper import RetryPolicy, ScraperProvider
from providers.search import SearchProvider
from research_governor import (
    classify_terminal_outcome,
    evaluate_round_three_authorization,
)
from store import (
    DatabaseReader,
    ModelAttemptBudgetError,
    finish_model_route_attempt,
    init_db,
    insert_analyst_decision,
    insert_cancellation_request,
    insert_candidate,
    insert_evidence_trail_entry,
    insert_ledger_record,
    insert_planner_output,
    insert_portfolio_coverage_assessment,
    insert_portfolio_item,
    insert_provider_run_contract,
    insert_provisional_extraction,
    insert_research_governor_decision,
    insert_research_round_record,
    insert_research_terminal_result,
    insert_retrieval_attempt,
    insert_run,
    insert_search_queries,
    insert_snapshot,
    insert_source_family_member,
    insert_stage_artifact,
    insert_statement_draft,
    insert_statement_review,
    insert_synthesis,
    insert_validation,
    open_read_only_store,
    read_analyst_decision,
    read_cancellation_request,
    read_candidate,
    read_evidence_trail_entries,
    read_ledger_record,
    read_model_route_attempts,
    read_orchestration_checkpoint,
    read_orchestration_checkpoints,
    read_planner_output,
    read_portfolio_coverage_assessment,
    read_provider_run_contract,
    read_provisional_extractions,
    read_research_governor_decision,
    read_research_round_records,
    read_research_terminal_result,
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

if TYPE_CHECKING:
    from providers.clients import ProviderClients

DEFAULT_OUTPUT_DIR_NAME = ".phase6_output"
FIXTURE_DB_NAME = "fixture_pipeline.sqlite3"
AUDIT_FILE_NAME = "audit.json"
RESULT_FILE_NAME = "result.json"
POST_FILTER_VERSION = "legacy-frozen-fixture-post-filter-50-100-v1"
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
            quote_length_policy=LEGACY_FIXTURE_QUOTE_LENGTH_POLICY,
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
                quote_length_policy=LEGACY_FIXTURE_QUOTE_LENGTH_POLICY,
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

PHASE9_POST_FILTER_VERSION = "mvp9-deterministic-quote-assembly-v1"
PHASE9_LEDGER_ID_VERSION = "phase9-provider-ledger-id-v1"
PHASE9_RESEARCHERS_ARTIFACT = "phase9-researchers"
PHASE9_ANALYSIS_ARTIFACT = "phase9-analysis-ledger"
PHASE9_PLANNER_CHECKPOINT = "planner"
PHASE9_RESEARCHERS_CHECKPOINT = "researchers"
PHASE9_ANALYSIS_CHECKPOINT = "analysis-ledger"
PHASE9_SYNTHESIS_CHECKPOINT = "synthesis"
PHASE9_VALIDATION_CHECKPOINT = "validation-release"
MVP10_TARGETED_PLANNER_CHECKPOINT = "mvp10-targeted-planner"
MVP10_TARGETED_RESEARCHERS_CHECKPOINT = "mvp10-targeted-researchers"
MVP10_TARGETED_ANALYSIS_CHECKPOINT = "mvp10-targeted-analysis"
MVP10_TARGETED_PLANNER_ARTIFACT = "mvp10-targeted-planner"
MVP10_TARGETED_RESEARCHERS_ARTIFACT = "mvp10-targeted-researchers"
MVP10_TARGETED_ANALYSIS_ARTIFACT = "mvp10-targeted-analysis"
MVP11_ROUND_TWO_PLANNER_CHECKPOINT = "mvp11-round-two-planner"
MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT = "mvp11-round-two-researchers"
MVP11_ROUND_TWO_ANALYSIS_CHECKPOINT = "mvp11-round-two-analysis"
MVP11_ROUND_THREE_PLANNER_CHECKPOINT = "mvp11-round-three-planner"
MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT = "mvp11-round-three-researchers"
MVP11_ROUND_THREE_ANALYSIS_CHECKPOINT = "mvp11-round-three-analysis"

_RETRYABLE_FAILURE_CODES = frozenset(
    {
        "transient_failure",
        "timeout",
        "malformed_output",
        "schema_validation_failure",
        "deterministic_validation_failure",
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


class ClaimMismatchError(ValueError):
    """A persisted run ID was reused with a different authoritative claim."""


class FingerprintMismatchError(ValueError):
    """A persisted run ID was reused with an incompatible provider contract."""


class Phase9Cancellation(CooperativeCancellation):
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
    max_total_cost_usd: ExactUSD | None = None


class PinnedModelSnapshot(StrictModel):
    model_alias: ModelAlias
    snapshot: str = Field(min_length=1)


class OrchestrationRetryPolicy(StrictModel):
    max_attempts_per_alias: int = Field(default=2, ge=1, le=3)


class ProviderOrchestrationConfig(StrictModel):
    routing: LLMRoutingConfig = DEFAULT_LLM_ROUTING
    retries: OrchestrationRetryPolicy = OrchestrationRetryPolicy()
    retrieval_retry: RetryPolicy = RetryPolicy()
    acquisition_policy: AcquisitionPolicy = AcquisitionPolicy()
    budget: OrchestrationBudget = OrchestrationBudget()
    require_budget_reservations: bool = False
    reserved_output_tokens_per_call: int = Field(default=4096, ge=1, le=32768)
    pricing_policy: Literal["compatibility", "direct_mimo"] = "compatibility"
    pinned_model_snapshots: tuple[PinnedModelSnapshot, ...] = ()
    enable_portfolio_expansion: bool = False
    enable_research_governor: bool = False

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
        if (
            self.supporting.retrieval_batch is not None
            and self.opposing.retrieval_batch is not None
            and self.supporting.retrieval_batch.intended_attempt_count
            != self.opposing.retrieval_batch.intended_attempt_count
        ):
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


def summarize_model_usage(attempts: Sequence[ModelRouteAttempt]) -> ModelUsageAccounting:
    """Aggregate exact usage separately from conservative unknown-usage exposure."""
    known_tokens = 0
    known_cost = Decimal("0")
    missing_token_ids: list[UUID] = []
    missing_cost_ids: list[UUID] = []
    conservative_tokens = 0
    conservative_cost = Decimal("0")
    token_exposure_provable = True
    cost_exposure_provable = True
    for attempt in attempts:
        usage_tokens = _usage_token_total(attempt.usage) if attempt.usage is not None else None
        usage_cost = attempt.usage.cost_usd if attempt.usage is not None else None
        if usage_tokens is None:
            missing_token_ids.append(attempt.attempt_id)
            if attempt.reserved_tokens is None:
                token_exposure_provable = False
            else:
                conservative_tokens += attempt.reserved_tokens
        else:
            known_tokens += usage_tokens
            conservative_tokens += usage_tokens
        if usage_cost is None:
            missing_cost_ids.append(attempt.attempt_id)
            if attempt.reserved_cost_usd is None:
                cost_exposure_provable = False
            else:
                conservative_cost = add_usd(conservative_cost, attempt.reserved_cost_usd)
        else:
            known_cost = add_usd(known_cost, usage_cost)
            conservative_cost = add_usd(conservative_cost, usage_cost)
    token_complete = not missing_token_ids
    cost_complete = not missing_cost_ids
    return ModelUsageAccounting(
        exact_total_tokens=known_tokens if token_complete else None,
        exact_total_cost_usd=known_cost if cost_complete else None,
        known_token_subtotal=known_tokens,
        known_cost_subtotal_usd=known_cost,
        token_complete=token_complete,
        cost_complete=cost_complete,
        missing_token_attempt_ids=tuple(missing_token_ids),
        missing_cost_attempt_ids=tuple(missing_cost_ids),
        conservative_reserved_tokens=(conservative_tokens if token_exposure_provable else None),
        conservative_reserved_cost_usd=(conservative_cost if cost_exposure_provable else None),
    )


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
    portfolio_coverage: PortfolioCoverageAssessment | None = None
    research_rounds: tuple[ResearchRoundRecord, ...] = ()
    research_governor_decision: ResearchGovernorDecision | None = None
    terminal_research_result: ResearchTerminalResult | None = None
    synthesis_output: SynthesisOutput | None = None
    validation_result: ValidationResult | None = None
    final_brief: str | None = None
    rendered_brief_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checkpoints: tuple[OrchestrationCheckpoint, ...] = ()
    model_attempts: tuple[ModelRouteAttempt, ...] = ()
    usage_accounting: ModelUsageAccounting = Field(
        default_factory=lambda: summarize_model_usage(())
    )
    retrieval_attempts_used: int = Field(default=0, ge=0)
    model_calls_used: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(default=0, ge=0)
    total_cost_usd: ExactUSD | None = Decimal("0")

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> ProviderPipelineResult:
        expected_accounting = summarize_model_usage(self.model_attempts)
        if self.usage_accounting != expected_accounting:
            raise ValueError("usage_accounting must match every persisted physical model attempt")
        if self.total_tokens != expected_accounting.exact_total_tokens:
            raise ValueError("total_tokens must contain only the exact complete token total")
        if self.total_cost_usd != expected_accounting.exact_total_cost_usd:
            raise ValueError("total_cost_usd must contain only the exact complete cost total")
        if self.status is ProviderRunStatus.RELEASED:
            if (
                self.validation_result is None
                or not self.validation_result.valid
                or self.final_brief is None
                or self.rendered_brief_hash is None
            ):
                raise ValueError("released runs require valid validation, final brief, and hash")
            actual_hash = sha256(self.final_brief.encode("utf-8")).hexdigest()
            if self.rendered_brief_hash != actual_hash:
                raise ValueError("released final brief does not match its rendered hash")
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
        elif self.status is ProviderRunStatus.RUNNING:
            if self.final_brief is not None or self.rendered_brief_hash is not None:
                raise ValueError("running runs cannot carry a final brief or hash")
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
    provider_contract: ProviderRunContract | None = None,
    research_controls: ResearchControls = DEFAULT_RESEARCH_CONTROLS,
    clock: Callable[[], datetime] | None = None,
    stage_hook: _StageHook | None = None,
) -> ProviderPipelineResult:
    """Run or restart the synchronous provider-backed Phase 9 pipeline."""
    claim = raw_claim
    if not claim:
        raise ValueError("raw_claim must not be empty")
    if claim != claim.strip():
        raise ValueError("raw_claim must not contain leading or trailing whitespace")
    database_path = Path(db_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    path = str(database_path)
    settings = config or ProviderOrchestrationConfig()
    now = clock or _phase9_utc_now
    resolved_run_id = run_id or uuid4()
    init_db(path)
    if provider_contract is not None:
        if provider_contract.run_id != resolved_run_id:
            raise ValueError("provider contract run_id must match the requested run")
        try:
            existing_contract = read_provider_run_contract(path, resolved_run_id)
        except KeyError:
            existing_contract = None
        else:
            if (
                existing_contract.fingerprint_sha256 != provider_contract.fingerprint_sha256
                or existing_contract.payload_json != provider_contract.payload_json
            ):
                raise FingerprintMismatchError(
                    "incompatible fingerprint for existing run; use a new run ID"
                )
    manifest = _create_or_resume_provider_run(path, resolved_run_id, claim, now)
    if provider_contract is not None and existing_contract is None:
        insert_provider_run_contract(path, provider_contract)
    if settings.enable_research_governor and read_research_terminal_result(path, resolved_run_id):
        return inspect_provider_run(path, resolved_run_id)
    if manifest.status in {RunStatus.COMPLETED, RunStatus.BLOCKED, RunStatus.CANCELLED}:
        return inspect_provider_run(path, resolved_run_id)

    active_stage = manifest.current_stage
    try:
        _raise_if_cancelled(path, resolved_run_id)
        active_stage = Stage.CLAIM_PLANNER
        planner = _run_planner_stage(
            path,
            manifest,
            llm_provider,
            settings,
            now,
            research_controls,
        )
        _after_stage(path, resolved_run_id, PHASE9_PLANNER_CHECKPOINT, now, stage_hook)

        active_stage = Stage.SUPPORTING_RESEARCHER
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
        if not all_candidates and not settings.enable_research_governor:
            raise Phase9OrchestrationError(
                Stage.OPPOSING_RESEARCHER,
                "researchers produced no candidate that passed deterministic filtering",
            )

        active_stage = Stage.CLAIM_LEDGER
        analysis = _run_analysis_stage(
            path,
            planner,
            researchers,
            llm_provider,
            settings,
            now,
        )
        _after_stage(path, resolved_run_id, PHASE9_ANALYSIS_CHECKPOINT, now, stage_hook)
        initial_analysis = analysis
        targeted_round_attempted = False
        targeted_researchers: ResearcherPairResult | None = None
        targeted_analysis: AnalysisStageResult | None = None
        if settings.enable_research_governor:
            analysis = _run_mvp11_research_governor(
                path,
                manifest,
                planner,
                researchers,
                analysis,
                search_provider,
                scraper_provider,
                llm_provider,
                settings,
                now,
                research_controls,
            )
        if (
            not settings.enable_research_governor
            and settings.enable_portfolio_expansion
            and _approved_family_count(researchers, analysis) < 3
        ):
            targeted_round_attempted = True
            targeted_planner = _run_targeted_planner_stage(
                path,
                manifest,
                planner,
                researchers,
                initial_analysis,
                llm_provider,
                settings,
                now,
                research_controls,
            )
            if _targeted_queries_are_new((planner,), targeted_planner):
                targeted_researchers = _run_researcher_stage(
                    path,
                    targeted_planner,
                    search_provider,
                    scraper_provider,
                    llm_provider,
                    settings,
                    now,
                    checkpoint_key=MVP10_TARGETED_RESEARCHERS_CHECKPOINT,
                    artifact_key=MVP10_TARGETED_RESEARCHERS_ARTIFACT,
                )
                targeted_analysis = _run_analysis_stage(
                    path,
                    targeted_planner,
                    targeted_researchers,
                    llm_provider,
                    settings,
                    now,
                    checkpoint_key=MVP10_TARGETED_ANALYSIS_CHECKPOINT,
                    artifact_key=MVP10_TARGETED_ANALYSIS_ARTIFACT,
                )
                analysis = _combine_analysis_results(analysis, targeted_analysis)
        if not settings.enable_research_governor and not analysis.ledger_records:
            _persist_mvp10_portfolio(
                path,
                planner,
                researchers,
                initial_analysis,
                now,
                stopping_reason="Research stopped because no Reviewer-approved evidence passed.",
            )
            if targeted_researchers is not None and targeted_analysis is not None:
                _persist_mvp10_portfolio(
                    path,
                    planner,
                    targeted_researchers,
                    targeted_analysis,
                    now,
                    stopping_reason=(
                        "Research stopped after one targeted round without approved evidence."
                    ),
                    research_round=ResearchRound.TARGETED,
                )
            _finalize_mvp10_portfolio(
                path,
                resolved_run_id,
                research_rounds=2 if targeted_round_attempted else 1,
                stopping_reason="Research stopped because no Reviewer-approved evidence passed.",
                clock=now,
            )
            raise Phase9OrchestrationError(
                Stage.CLAIM_LEDGER,
                "insufficient evidence: no Reviewer-approved statement was eligible for the Ledger",
            )

        if not settings.enable_research_governor:
            _persist_mvp10_portfolio(
                path,
                planner,
                researchers,
                initial_analysis,
                now,
                stopping_reason="Round 1 completed.",
            )
            if targeted_researchers is not None and targeted_analysis is not None:
                _persist_mvp10_portfolio(
                    path,
                    planner,
                    targeted_researchers,
                    targeted_analysis,
                    now,
                    stopping_reason="One targeted portfolio-expansion round completed.",
                    research_round=ResearchRound.TARGETED,
                )
            _finalize_mvp10_portfolio(
                path,
                resolved_run_id,
                research_rounds=2 if targeted_round_attempted else 1,
                stopping_reason=(
                    "Coverage target met in the initial round."
                    if not targeted_round_attempted
                    else "The one permitted targeted round completed; no further search is allowed."
                ),
                clock=now,
            )

        active_stage = Stage.DEBATE_SYNTHESIZER
        synthesis = _run_synthesis_stage(
            path,
            planner,
            analysis,
            llm_provider,
            settings,
            now,
        )
        _after_stage(path, resolved_run_id, PHASE9_SYNTHESIS_CHECKPOINT, now, stage_hook)

        active_stage = Stage.FINAL_RENDERER_VALIDATOR
        validation = _run_validation_stage(
            path,
            synthesis,
            analysis,
            manifest.raw_claim,
            now,
        )
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
        if settings.enable_research_governor:
            _finalize_mvp11_governor(
                path,
                resolved_run_id,
                completed_rounds=max(len(read_research_round_records(path, resolved_run_id)), 1),
                families=0,
                explanation=reason,
                clock=now,
                cancelled=True,
            )
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
        if settings.enable_research_governor:
            _finalize_mvp11_governor(
                path,
                resolved_run_id,
                completed_rounds=max(len(read_research_round_records(path, resolved_run_id)), 1),
                families=0,
                explanation=reason,
                clock=now,
                failed=True,
            )
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


def run_mvp3b_pipeline(
    raw_claim: str,
    *,
    db_path: str | Path,
    factory_config: object,
    clients: ProviderClients | None = None,
    run_id: UUID | None = None,
    clock: Callable[[], datetime] | None = None,
    stage_hook: _StageHook | None = None,
    research_controls: ResearchControls = DEFAULT_RESEARCH_CONTROLS,
) -> ProviderPipelineResult:
    """Run the authorized Wigolo plus direct Xiaomi MiMo MVP-3B stack."""
    from providers.mimo_factory import (
        MimoProviderFactoryConfig,
        build_mimo_provider_bundle,
    )

    if not isinstance(factory_config, MimoProviderFactoryConfig):
        raise TypeError("MVP-3B requires MimoProviderFactoryConfig")
    now = clock or _phase9_utc_now
    resolved_run_id = run_id or uuid4()
    if factory_config.research_controls != research_controls:
        raise ValueError("factory research controls must match requested controls")
    bundle = build_mimo_provider_bundle(factory_config, clients=clients)
    settings = ProviderOrchestrationConfig(
        routing=DIRECT_MIMO_ROUTING,
        acquisition_policy=bundle.config.acquisition,
        budget=OrchestrationBudget(
            max_model_calls=bundle.config.ceilings.max_llm_calls,
            retrieval_attempts_per_side=bundle.config.acquisition.maximum_attempts_per_stance,
            max_total_tokens=bundle.config.ceilings.max_tokens,
            max_total_cost_usd=bundle.config.ceilings.max_cost_usd,
        ),
        require_budget_reservations=True,
        reserved_output_tokens_per_call=bundle.config.mimo.max_completion_tokens,
        pricing_policy="direct_mimo",
        enable_research_governor=True,
    )
    contract = bundle.contract(
        resolved_run_id,
        _aware_phase9_time(now(), "contract created_at"),
    )
    return run_provider_pipeline(
        raw_claim,
        db_path=db_path,
        search_provider=bundle.search,
        scraper_provider=bundle.acquisition,
        llm_provider=bundle.llm,
        run_id=resolved_run_id,
        config=settings,
        provider_contract=contract,
        clock=now,
        stage_hook=stage_hook,
        research_controls=research_controls,
    )


def inspect_provider_run(
    db_path: str | Path,
    run_id: UUID,
    *,
    failure_reason: str | None = None,
) -> ProviderPipelineResult:
    """Reopen and inspect a partial or terminal provider-backed run."""
    path = str(Path(db_path).resolve())
    with open_read_only_store(path) as store:
        return _inspect_provider_run_connection(
            store.connection,
            path,
            run_id,
            failure_reason=failure_reason,
        )


def _inspect_provider_run_connection(
    reader: DatabaseReader,
    path: str,
    run_id: UUID,
    *,
    failure_reason: str | None,
) -> ProviderPipelineResult:
    manifest = read_run(reader, run_id)
    checkpoints = tuple(read_orchestration_checkpoints(reader, run_id))
    attempts = tuple(read_model_route_attempts(reader, run_id))
    planner = _read_optional_planner(reader, run_id)
    researchers = _read_optional_stage_result(
        reader,
        run_id,
        PHASE9_RESEARCHERS_ARTIFACT,
        ResearcherPairResult,
    )
    analysis = _read_optional_stage_result(
        reader,
        run_id,
        PHASE9_ANALYSIS_ARTIFACT,
        AnalysisStageResult,
    )
    synthesis = _read_optional_synthesis(reader, run_id)
    validation = _read_optional_validation(reader, run_id)
    portfolio_coverage = read_portfolio_coverage_assessment(reader, run_id)
    research_rounds = read_research_round_records(reader, run_id)
    governor_decision = read_research_governor_decision(reader, run_id)
    terminal_research_result = read_research_terminal_result(reader, run_id)
    status = _provider_status_from_manifest(manifest)
    resolved_failure = None
    if status is ProviderRunStatus.FAILED:
        resolved_failure = failure_reason or _latest_failure_reason(checkpoints)
    if status is ProviderRunStatus.CANCELLED and resolved_failure is None:
        resolved_failure = _cancellation_reason(reader, run_id)
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
        if rendered_hash != sha256(final_brief.encode("utf-8")).hexdigest():
            raise ValueError("persisted released brief does not match its validation hash")

    usage_accounting = summarize_model_usage(attempts)
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
        portfolio_coverage=portfolio_coverage,
        research_rounds=research_rounds,
        research_governor_decision=governor_decision,
        terminal_research_result=terminal_research_result,
        synthesis_output=synthesis,
        validation_result=validation,
        final_brief=final_brief,
        rendered_brief_hash=rendered_hash,
        checkpoints=checkpoints,
        model_attempts=attempts,
        usage_accounting=usage_accounting,
        retrieval_attempts_used=retrieval_count,
        model_calls_used=len(attempts),
        total_tokens=usage_accounting.exact_total_tokens,
        total_cost_usd=usage_accounting.exact_total_cost_usd,
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
        raise ClaimMismatchError(
            "existing run raw claim is a different exact claim; use a new run ID"
        )
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
    _raise_if_cancelled(db_path, run_id)
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
    _raise_if_cancelled(db_path, run_id)


def _raise_if_cancelled(db_path: str, run_id: UUID) -> None:
    """Observe cooperative cancellation at a provider or orchestration boundary."""
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
    db_path: DatabaseReader,
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


def _read_optional_planner(db_path: DatabaseReader, run_id: UUID) -> PlannerOutput | None:
    try:
        return read_planner_output(db_path, run_id)
    except KeyError:
        return None


def _read_optional_synthesis(db_path: DatabaseReader, run_id: UUID) -> SynthesisOutput | None:
    try:
        return read_synthesis(db_path, run_id)
    except KeyError:
        return None


def _read_optional_validation(db_path: DatabaseReader, run_id: UUID) -> ValidationResult | None:
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
    if manifest.status in {RunStatus.PLANNED, RunStatus.RUNNING}:
        return ProviderRunStatus.RUNNING
    raise ValueError(f"unsupported persisted run status: {manifest.status!r}")


def _latest_failure_reason(checkpoints: Sequence[OrchestrationCheckpoint]) -> str | None:
    failures = [
        checkpoint for checkpoint in checkpoints if checkpoint.status is CheckpointStatus.FAILED
    ]
    if not failures:
        return None
    return max(failures, key=lambda item: item.updated_at).failure_reason


def _cancellation_reason(db_path: DatabaseReader, run_id: UUID) -> str:
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
    research_controls: ResearchControls,
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
    planner_input = PlannerLLMInput(
        run_id=manifest.run_id,
        raw_claim=manifest.raw_claim,
        research_controls=research_controls,
    )
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


def _run_targeted_planner_stage(
    db_path: str,
    manifest: RunManifest,
    initial_planner: PlannerOutput,
    researchers: ResearcherPairResult,
    analysis: AnalysisStageResult,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
    research_controls: ResearchControls,
    *,
    checkpoint_key: str = MVP10_TARGETED_PLANNER_CHECKPOINT,
    artifact_key: str = MVP10_TARGETED_PLANNER_ARTIFACT,
    operation_label: str = "mvp10-targeted-planner",
    attempted_planners: tuple[PlannerOutput, ...] = (),
    family_researchers: tuple[ResearcherPairResult, ...] = (),
    require_new_queries: bool = True,
) -> PlannerOutput:
    """Execute a typed bounded replanning call without replacing earlier rounds."""
    stored = _read_optional_stage_result(db_path, manifest.run_id, artifact_key, PlannerOutput)
    if stored is not None:
        return stored
    _begin_stage(db_path, manifest.run_id, Stage.CLAIM_PLANNER, checkpoint_key, clock)
    snapshots = {
        snapshot.snapshot_id: snapshot
        for researcher_pair in (researchers, *family_researchers)
        for side in (researcher_pair.supporting, researcher_pair.opposing)
        if side.retrieval_batch is not None
        for snapshot in side.retrieval_batch.snapshots
    }
    prior_trail = read_evidence_trail_entries(db_path, manifest.run_id)
    approved_families = tuple(
        sorted(
            {
                identify_source_family(snapshots[ledger.snapshot_id])
                for ledger in analysis.ledger_records
                if ledger.snapshot_id in snapshots
            },
            key=lambda item: str(item.source_family_id),
        )
    )
    attempted_queries = tuple(
        query.query_text
        for prior_planner in (initial_planner, *attempted_planners)
        for query in prior_planner.search_queries
    )
    rejected_sources = tuple(
        sorted(
            {
                *(
                    candidate.source_url
                    for side in (researchers.supporting, researchers.opposing)
                    for candidate in side.candidates
                    if candidate.quote_block_id in analysis.rejected_quote_block_ids
                ),
                *(
                    entry.resolved_url
                    for entry in prior_trail
                    if entry.outcome
                    in {
                        EvidenceTrailOutcome.ANALYST_REJECTED,
                        EvidenceTrailOutcome.REVIEWER_REJECTED,
                        EvidenceTrailOutcome.NOT_RELEVANT,
                    }
                ),
            }
        )
    )
    inaccessible_domains = tuple(
        sorted(
            {
                _mvp10_source_domain(outcome.retrieval.resolved_url)
                for side in (researchers.supporting, researchers.opposing)
                if side.retrieval_batch is not None
                for outcome in side.retrieval_batch.outcomes
                if outcome.retrieval.status.value == "failed"
                and _mvp10_source_domain(outcome.retrieval.resolved_url) != "unknown source"
            }
            | {
                entry.source_domain
                for entry in prior_trail
                if entry.outcome
                in {
                    EvidenceTrailOutcome.INACCESSIBLE,
                    EvidenceTrailOutcome.RETRIEVAL_FAILURE,
                }
            }
        )
    )
    expansion = PortfolioExpansionRequest(
        run_id=manifest.run_id,
        original_claim=manifest.raw_claim,
        approved_source_families=approved_families,
        supporting_coverage=sum(
            ledger.stance.value == "supporting" for ledger in analysis.ledger_records
        ),
        opposing_or_limitation_coverage=sum(
            ledger.stance.value == "opposing" for ledger in analysis.ledger_records
        ),
        rejected_sources=rejected_sources,
        inaccessible_domains=inaccessible_domains,
        duplicate_source_families=tuple(
            sorted(
                {
                    entry.source_family
                    for entry in prior_trail
                    if entry.outcome is EvidenceTrailOutcome.DUPLICATE
                    and entry.source_family is not None
                },
                key=lambda item: str(item.source_family_id),
            )
        ),
        attempted_queries=attempted_queries,
        evidence_gaps=(
            "Find independent primary evidence not represented by approved source families.",
            "Seek credible contradiction, alternative estimate, or methodological "
            "limitation when available.",
        ),
    )
    planner_input = PlannerLLMInput(
        run_id=manifest.run_id,
        raw_claim=manifest.raw_claim,
        research_controls=research_controls,
        portfolio_expansion=expansion,
    )
    operation_id = _operation_id(manifest.run_id, operation_label, manifest.run_id)

    def validate_targeted_planner(output: BaseModel, alias: ModelAlias) -> BaseModel:
        planner = _require_output(output, PlannerOutput)
        if (
            planner.run_id != manifest.run_id
            or planner.claim_definition.claim_text != manifest.raw_claim
        ):
            raise _validation_failure(
                "targeted Planner output does not match the existing run claim"
            )
        _validate_llm_provenance(
            planner.planner_prompt_version, planner.planner_model_name, LLMStage.PLANNER, alias
        )
        return planner

    targeted = cast(
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
            objective_validator=validate_targeted_planner,
        ),
    )
    if not require_new_queries or _targeted_queries_are_new(
        (initial_planner, *attempted_planners), targeted
    ):
        insert_search_queries(db_path, tuple(targeted.search_queries))
    elif require_new_queries:
        raise Phase9OrchestrationError(
            Stage.CLAIM_PLANNER,
            "targeted Planner did not provide a materially new search strategy",
        )
    _persist_stage_result(db_path, manifest.run_id, artifact_key, targeted, clock)
    _checkpoint(
        db_path,
        manifest.run_id,
        checkpoint_key,
        CheckpointStatus.COMPLETED,
        clock,
    )
    return targeted


def _approved_family_count(researchers: ResearcherPairResult, analysis: AnalysisStageResult) -> int:
    snapshots = _snapshot_lookup(researchers)
    return len(
        {
            identify_source_family(snapshots[ledger.snapshot_id]).source_family_id
            for ledger in analysis.ledger_records
        }
    )


def _run_mvp11_research_governor(
    db_path: str,
    manifest: RunManifest,
    round_one_planner: PlannerOutput,
    round_one_researchers: ResearcherPairResult,
    round_one_analysis: AnalysisStageResult,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
    research_controls: ResearchControls,
) -> AnalysisStageResult:
    """Run the fixed MVP-11 two-round minimum and conditionally final third round."""
    _record_mvp11_round(db_path, round_one_planner, round_one_researchers, 1, clock)
    _persist_mvp10_portfolio(
        db_path,
        round_one_planner,
        round_one_researchers,
        round_one_analysis,
        clock,
        stopping_reason="Round 1 completed.",
    )
    combined = round_one_analysis
    combined_researchers = (round_one_researchers,)
    if _approved_family_count(round_one_researchers, round_one_analysis) >= 3:
        _finalize_mvp11_governor(
            db_path,
            manifest.run_id,
            completed_rounds=1,
            families=_approved_family_count(round_one_researchers, round_one_analysis),
            explanation="Round 1 met the independent approved source-family target.",
            clock=clock,
        )
        _finalize_mvp10_portfolio(
            db_path,
            manifest.run_id,
            research_rounds=1,
            stopping_reason="Coverage target met in Round 1.",
            clock=clock,
        )
        return combined

    deduplication = _seed_mvp11_deduplication(round_one_researchers)
    round_two_planner = _run_targeted_planner_stage(
        db_path,
        manifest,
        round_one_planner,
        round_one_researchers,
        round_one_analysis,
        llm_provider,
        config,
        clock,
        research_controls,
        checkpoint_key=MVP11_ROUND_TWO_PLANNER_CHECKPOINT,
        artifact_key=MVP11_ROUND_TWO_PLANNER_CHECKPOINT,
        operation_label="mvp11-round-two-planner",
    )
    round_two_researchers = _run_researcher_stage(
        db_path,
        round_two_planner,
        search_provider,
        scraper_provider,
        llm_provider,
        config,
        clock,
        checkpoint_key=MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT,
        artifact_key=MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT,
        deduplication=deduplication,
    )
    round_two_analysis = _run_analysis_stage(
        db_path,
        round_two_planner,
        round_two_researchers,
        llm_provider,
        config,
        clock,
        checkpoint_key=MVP11_ROUND_TWO_ANALYSIS_CHECKPOINT,
        artifact_key=MVP11_ROUND_TWO_ANALYSIS_CHECKPOINT,
    )
    _record_mvp11_round(db_path, round_two_planner, round_two_researchers, 2, clock)
    _persist_mvp10_portfolio(
        db_path,
        round_two_planner,
        round_two_researchers,
        round_two_analysis,
        clock,
        stopping_reason="Round 2 completed its planned workload.",
        research_round=ResearchRound.TARGETED,
    )
    combined = _combine_analysis_results(combined, round_two_analysis)
    combined_researchers = (*combined_researchers, round_two_researchers)
    decision = evaluate_round_three_authorization(
        _mvp11_governor_input(
            db_path,
            manifest.run_id,
            combined_researchers,
            combined,
            config,
            clock,
        )
    )
    _persist_mvp11_decision(db_path, decision)
    if decision.decision.value != "begin_round_three":
        _finalize_mvp11_governor(
            db_path,
            manifest.run_id,
            completed_rounds=2,
            families=decision.independent_approved_family_count,
            explanation=decision.explanation,
            clock=clock,
        )
        _finalize_mvp10_portfolio(
            db_path,
            manifest.run_id,
            research_rounds=2,
            stopping_reason=decision.explanation,
            clock=clock,
        )
        return combined

    round_three_planner = _run_targeted_planner_stage(
        db_path,
        manifest,
        round_one_planner,
        round_two_researchers,
        combined,
        llm_provider,
        config,
        clock,
        research_controls,
        checkpoint_key=MVP11_ROUND_THREE_PLANNER_CHECKPOINT,
        artifact_key=MVP11_ROUND_THREE_PLANNER_CHECKPOINT,
        operation_label="mvp11-round-three-planner",
        attempted_planners=(round_two_planner,),
        family_researchers=(round_one_researchers,),
    )
    round_three_researchers = _run_researcher_stage(
        db_path,
        round_three_planner,
        search_provider,
        scraper_provider,
        llm_provider,
        config,
        clock,
        checkpoint_key=MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
        artifact_key=MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
        deduplication=deduplication,
    )
    round_three_analysis = _run_analysis_stage(
        db_path,
        round_three_planner,
        round_three_researchers,
        llm_provider,
        config,
        clock,
        checkpoint_key=MVP11_ROUND_THREE_ANALYSIS_CHECKPOINT,
        artifact_key=MVP11_ROUND_THREE_ANALYSIS_CHECKPOINT,
    )
    _record_mvp11_round(db_path, round_three_planner, round_three_researchers, 3, clock)
    _persist_mvp10_portfolio(
        db_path,
        round_three_planner,
        round_three_researchers,
        round_three_analysis,
        clock,
        stopping_reason="Round 3 completed its planned workload.",
        research_round=ResearchRound.TARGETED,
    )
    combined = _combine_analysis_results(combined, round_three_analysis)
    _finalize_mvp11_governor(
        db_path,
        manifest.run_id,
        completed_rounds=3,
        families=_mvp11_family_count((*combined_researchers, round_three_researchers), combined),
        explanation="Round 3 completed; no further research round is permitted.",
        clock=clock,
    )
    _finalize_mvp10_portfolio(
        db_path,
        manifest.run_id,
        research_rounds=3,
        stopping_reason="Round 3 completed; no further research round is permitted.",
        clock=clock,
    )
    return combined


def _seed_mvp11_deduplication(researchers: ResearcherPairResult) -> DeduplicationState:
    """Seed a new round with every prior snapshot identity so it cannot re-acquire them."""
    deduplication = DeduplicationState()
    for side in (researchers.supporting, researchers.opposing):
        if side.retrieval_batch is None:
            continue
        for snapshot in side.retrieval_batch.snapshots:
            family = identify_source_family(snapshot)
            deduplication.original_urls[snapshot.source_url] = snapshot.snapshot_id
            deduplication.resolved_urls[snapshot.source_url] = snapshot.snapshot_id
            deduplication.content_hashes[snapshot.snapshot_sha256] = snapshot.snapshot_id
            deduplication.source_families[family.source_family_id] = snapshot.snapshot_id
    return deduplication


def _mvp11_family_count(
    researcher_rounds: tuple[ResearcherPairResult, ...], analysis: AnalysisStageResult
) -> int:
    """Count approved families from all completed rounds without reinterpreting duplicates."""
    snapshots = {
        snapshot.snapshot_id: snapshot
        for pair in researcher_rounds
        for side in (pair.supporting, pair.opposing)
        if side.retrieval_batch is not None
        for snapshot in side.retrieval_batch.snapshots
    }
    return len(
        {
            identify_source_family(snapshots[ledger.snapshot_id]).source_family_id
            for ledger in analysis.ledger_records
            if ledger.snapshot_id in snapshots
        }
    )


def _record_mvp11_round(
    db_path: str,
    planner: PlannerOutput,
    researchers: ResearcherPairResult,
    research_round: int,
    clock: Callable[[], datetime],
) -> None:
    """Append one completed research-round record, refusing any impossible fourth round."""
    if research_round not in {1, 2, 3}:
        raise Phase9OrchestrationError(Stage.CLAIM_PLANNER, "MVP-11 forbids research Round 4")
    if any(
        item.research_round == research_round
        for item in read_research_round_records(db_path, planner.run_id)
    ):
        return
    outcomes = tuple(
        outcome
        for side in (researchers.supporting, researchers.opposing)
        if side.retrieval_batch is not None
        for outcome in side.retrieval_batch.outcomes
    )
    completed_at = _aware_phase9_time(clock(), "research round completed_at")
    insert_research_round_record(
        db_path,
        ResearchRoundRecord(
            run_id=planner.run_id,
            research_round=research_round,
            status=ResearchRoundStatus.COMPLETED,
            planned_query_count=len(planner.search_queries),
            planned_discovery_count=(
                2 * researchers.supporting.retrieval_batch.intended_attempt_count
                if researchers.supporting.retrieval_batch is not None
                else 0
            ),
            completed_query_count=len(planner.search_queries),
            completed_discovery_count=len(outcomes),
            started_at=planner.planned_at,
            completed_at=completed_at,
            stopping_reason="Completed the planned research workload.",
        ),
    )


def _mvp11_governor_input(
    db_path: str,
    run_id: UUID,
    researcher_rounds: tuple[ResearcherPairResult, ...],
    analysis: AnalysisStageResult,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
) -> ResearchGovernorEvaluationInput:
    """Derive post-Round-2 typed policy facts from persisted cumulative artifacts."""
    round_two = researcher_rounds[-1]
    outcomes = tuple(
        item
        for side in (round_two.supporting, round_two.opposing)
        if side.retrieval_batch is not None
        for item in side.retrieval_batch.outcomes
    )
    duplicate_count = sum(item.scrape_status.value == "duplicate_url" for item in outcomes)
    attempts = tuple(read_model_route_attempts(db_path, run_id))
    usage = summarize_model_usage(attempts)
    model_remaining = max(config.budget.max_model_calls - len(attempts), 0)
    retrieval_used = sum(
        len(side.retrieval_batch.outcomes)
        for pair in researcher_rounds
        for side in (pair.supporting, pair.opposing)
        if side.retrieval_batch is not None
    )
    retrieval_remaining = max(
        (config.budget.retrieval_attempts_per_side * 2) - retrieval_used,
        0,
    )
    planned_round_three_model_calls = _mvp11_round_three_model_call_reservation(config)
    planned_round_three_retrievals = config.acquisition_policy.maximum_attempts_per_stance * 2
    planned_round_three_tokens = (
        planned_round_three_model_calls * config.reserved_output_tokens_per_call
    )
    price_cap = (
        DIRECT_MIMO_PRICE_CAP
        if config.pricing_policy == "direct_mimo"
        else COMPATIBILITY_PRICE_CAPS["mimo-v2.5-pro"]
    )
    planned_round_three_cost = price_cap.upper_bound(
        planned_round_three_tokens,
        planned_round_three_tokens,
    )
    token_remaining = (
        max(config.budget.max_total_tokens - (usage.conservative_reserved_tokens or 0), 0)
        if config.budget.max_total_tokens is not None
        else None
    )
    cost_remaining = (
        config.budget.max_total_cost_usd - usage.conservative_reserved_cost_usd
        if (
            config.budget.max_total_cost_usd is not None
            and usage.conservative_reserved_cost_usd is not None
        )
        else None
    )
    full_reserve = (
        model_remaining >= planned_round_three_model_calls
        and retrieval_remaining >= planned_round_three_retrievals
        and (
            config.budget.max_total_tokens is None
            or token_remaining is not None
            and token_remaining >= planned_round_three_tokens
        )
        and (
            config.budget.max_total_cost_usd is None
            or cost_remaining is not None
            and cost_remaining >= planned_round_three_cost
        )
    )
    return ResearchGovernorEvaluationInput(
        run_id=run_id,
        independent_approved_family_count=_mvp11_family_count(researcher_rounds, analysis),
        round_two_duplicate_count=duplicate_count,
        round_two_result_count=len(outcomes),
        consecutive_unproductive_source_count=_mvp11_consecutive_unproductive(outcomes),
        remaining_search_angles=("independent source types not used in the first two rounds",),
        cumulative_budget=ResearchGovernorBudgetState(
            model_calls_used=len(attempts),
            model_calls_remaining=model_remaining,
            retrievals_used=retrieval_used,
            retrievals_remaining=retrieval_remaining,
            conservative_tokens_used=usage.conservative_reserved_tokens,
            tokens_remaining=token_remaining,
            conservative_cost_used_usd=usage.conservative_reserved_cost_usd,
            cost_remaining_usd=cost_remaining,
            round_three_model_calls_required=planned_round_three_model_calls,
            round_three_retrievals_required=planned_round_three_retrievals,
            round_three_tokens_required=planned_round_three_tokens,
            round_three_cost_required_usd=planned_round_three_cost,
            full_round_three_reserved=full_reserve,
        ),
        decided_at=_aware_phase9_time(clock(), "governor decided_at"),
    )


def _mvp11_round_three_model_call_reservation(config: ProviderOrchestrationConfig) -> int:
    """Reserve every bounded Round-3 operation and its allowed provider-level retries."""
    maximum_sources = config.acquisition_policy.maximum_attempts_per_stance * 2
    operations_per_source = 4  # Extractor, Analyst, statement draft, and Reviewer.
    logical_operations = 1 + (maximum_sources * operations_per_source)
    return logical_operations * config.retries.max_attempts_per_alias


def _mvp11_consecutive_unproductive(outcomes: Sequence[object]) -> int:
    """Count the trailing deterministic duplicate/unusable streak for Governor policy."""
    count = 0
    for outcome in reversed(outcomes):
        if getattr(getattr(outcome, "scrape_status", None), "value", None) == "retrieved":
            break
        count += 1
    return count


def _persist_mvp11_decision(db_path: str, decision: ResearchGovernorDecision) -> None:
    """Persist the one immutable Governor decision exactly once across safe resume."""
    if read_research_governor_decision(db_path, decision.run_id) is None:
        insert_research_governor_decision(db_path, decision)


def _finalize_mvp11_governor(
    db_path: str,
    run_id: UUID,
    *,
    completed_rounds: int,
    families: int,
    explanation: str,
    clock: Callable[[], datetime],
    cancelled: bool = False,
    failed: bool = False,
) -> None:
    """Persist a terminal classification that never allows a post-Round-3 resume loop."""
    if read_research_terminal_result(db_path, run_id) is None:
        insert_research_terminal_result(
            db_path,
            classify_terminal_outcome(
                run_id=run_id,
                completed_rounds=completed_rounds,
                independent_approved_family_count=families,
                cancelled=cancelled,
                failed=failed,
                explanation=explanation,
                finalized_at=_aware_phase9_time(clock(), "research terminal finalized_at"),
            ),
        )


def _targeted_queries_are_new(
    attempted_planners: tuple[PlannerOutput, ...], targeted: PlannerOutput
) -> bool:
    """Require the targeted round to offer a materially new query set before retrieval."""
    attempted = {
        query.query_text for planner in attempted_planners for query in planner.search_queries
    }
    return not bool({query.query_text for query in targeted.search_queries} & attempted)


def _combine_analysis_results(
    initial: AnalysisStageResult, targeted: AnalysisStageResult
) -> AnalysisStageResult:
    """Merge independently persisted round results without reprocessing known evidence."""
    return AnalysisStageResult(
        run_id=initial.run_id,
        analyst_decisions=(*initial.analyst_decisions, *targeted.analyst_decisions),
        statement_drafts=(*initial.statement_drafts, *targeted.statement_drafts),
        reviewer_decisions=(*initial.reviewer_decisions, *targeted.reviewer_decisions),
        ledger_records=tuple(
            sorted(
                (*initial.ledger_records, *targeted.ledger_records),
                key=lambda item: str(item.ledger_claim_id),
            )
        ),
        rejected_quote_block_ids=tuple(
            sorted((*initial.rejected_quote_block_ids, *targeted.rejected_quote_block_ids), key=str)
        ),
    )


def _run_researcher_stage(
    db_path: str,
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    llm_provider: LLMProvider,
    config: ProviderOrchestrationConfig,
    clock: Callable[[], datetime],
    *,
    checkpoint_key: str = PHASE9_RESEARCHERS_CHECKPOINT,
    artifact_key: str = PHASE9_RESEARCHERS_ARTIFACT,
    deduplication: DeduplicationState | None = None,
) -> ResearcherPairResult:
    if _checkpoint_is_completed(db_path, planner.run_id, checkpoint_key):
        stored = _read_optional_stage_result(
            db_path,
            planner.run_id,
            artifact_key,
            ResearcherPairResult,
        )
        if stored is None:
            raise Phase9OrchestrationError(
                Stage.OPPOSING_RESEARCHER,
                "completed Researcher checkpoint has no typed stage artifact",
            )
        return stored
    required_attempts = config.acquisition_policy.maximum_attempts_per_stance
    if config.budget.retrieval_attempts_per_side < required_attempts:
        raise Phase9OrchestrationError(
            Stage.SUPPORTING_RESEARCHER,
            (
                "retrieval budget exceeded: each side requires "
                f"{required_attempts} attempts but budget allows "
                f"{config.budget.retrieval_attempts_per_side}"
            ),
        )
    _begin_stage(
        db_path,
        planner.run_id,
        Stage.SUPPORTING_RESEARCHER,
        checkpoint_key,
        clock,
    )
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="phase9-researcher") as executor:
        active_deduplication = deduplication or DeduplicationState()
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
            active_deduplication,
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
            active_deduplication,
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
        artifact_key,
        pair,
        clock,
    )
    if (
        supporting.status is ResearcherSideStatus.FAILED
        and opposing.status is ResearcherSideStatus.FAILED
    ):
        messages = [
            f"{failure.code}: {failure.message}"
            for failure in (*supporting.failures, *opposing.failures)
        ]
        raise Phase9OrchestrationError(
            Stage.OPPOSING_RESEARCHER,
            f"both Researcher sides failed: {'; '.join(messages)}",
        )
    _checkpoint(
        db_path,
        planner.run_id,
        checkpoint_key,
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
    deduplication: DeduplicationState,
) -> ResearcherStageResult:
    failures: list[ResearcherFailure] = []
    try:
        if stance == "supporting":
            batch = retrieve_supporting(
                planner,
                search_provider,
                scraper_provider,
                retry_policy=config.retrieval_retry,
                acquisition_policy=config.acquisition_policy,
                clock=clock,
                boundary_check=lambda: _raise_if_cancelled(db_path, planner.run_id),
                deduplication=deduplication,
            )
        else:
            batch = retrieve_opposing(
                planner,
                search_provider,
                scraper_provider,
                retry_policy=config.retrieval_retry,
                acquisition_policy=config.acquisition_policy,
                clock=clock,
                boundary_check=lambda: _raise_if_cancelled(db_path, planner.run_id),
                deduplication=deduplication,
            )
    except Phase9Cancellation:
        raise
    except Exception as exc:
        raw_failure_code = getattr(exc, "code", None)
        failure_code = getattr(raw_failure_code, "value", raw_failure_code)
        return ResearcherStageResult(
            run_id=planner.run_id,
            stance=stance,
            status=ResearcherSideStatus.FAILED,
            failures=(
                ResearcherFailure(
                    stage=f"{stance}_retrieval",
                    code=failure_code or "retrieval_failure",
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
    failures.extend(
        ResearcherFailure(
            stage=f"{stance}_retrieval",
            code=outcome.failure_code,
            message=outcome.failure_message or outcome.failure_code,
        )
        for outcome in batch.outcomes
        if outcome.failure_code is not None
    )
    for snapshot in batch.snapshots:
        retrieval = retrievals_by_id[snapshot.retrieval_attempt_id]
        extraction_input = build_extraction_llm_input(
            planner=planner,
            snapshot=snapshot,
            stance=stance_value,
            retrieval=retrieval,
        )
        operation_id = _operation_id(planner.run_id, "extractor", snapshot.snapshot_id)
        extractor_prompt_version = load_prompt(LLMStage.EXTRACTOR).version
        successful_alias: ModelAlias | None = None

        def validate_extraction(
            output: BaseModel,
            alias: ModelAlias,
            snapshot: SourceSnapshot = snapshot,
            batch: ResearcherRetrievalBatch = batch,
            extraction_input: ExtractionLLMInput = extraction_input,
            extractor_prompt_version: str = extractor_prompt_version,
        ) -> BaseModel:
            nonlocal successful_alias
            selection = _require_output(output, VerbatimQuoteSelection)
            try:
                provisional = build_provisional_candidate_from_selection(
                    extraction_input,
                    selection,
                    extraction_prompt_version=extractor_prompt_version,
                    extraction_model_name=alias.value,
                    extracted_at=_aware_phase9_time(clock(), "extracted_at"),
                )
            except ValueError as exc:
                raise ObjectiveRoutingFailure("exact_quote_failure", str(exc)) from exc
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
            successful_alias = alias
            return selection

        try:
            selection = cast(
                VerbatimQuoteSelection,
                _invoke_routed(
                    db_path=db_path,
                    provider=llm_provider,
                    stage=LLMStage.EXTRACTOR,
                    input_artifact=extraction_input,
                    requested_output_type=VerbatimQuoteSelection,
                    input_artifact_ids=(snapshot.snapshot_id,),
                    operation_id=operation_id,
                    config=config,
                    clock=clock,
                    objective_validator=validate_extraction,
                ),
            )
            if successful_alias is None:
                raise RuntimeError("completed Extractor selection has no model identity")
            provisional = build_provisional_candidate_from_selection(
                extraction_input,
                selection,
                extraction_prompt_version=extractor_prompt_version,
                extraction_model_name=successful_alias.value,
                extracted_at=_aware_phase9_time(clock(), "extracted_at"),
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
    *,
    checkpoint_key: str = PHASE9_ANALYSIS_CHECKPOINT,
    artifact_key: str = PHASE9_ANALYSIS_ARTIFACT,
) -> AnalysisStageResult:
    if _checkpoint_is_completed(db_path, planner.run_id, checkpoint_key):
        stored = _read_optional_stage_result(
            db_path,
            planner.run_id,
            artifact_key,
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
        checkpoint_key,
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
                entailment=entailment_for_claim_fit(decision.claim_fit),
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
        artifact_key,
        result,
        clock,
    )
    _checkpoint(
        db_path,
        planner.run_id,
        checkpoint_key,
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
    if not isinstance(analyst_input, AnalystLLMInput):
        raise TypeError("analyst_input must be an AnalystLLMInput")
    draft_input = StatementDraftLLMInput(
        analyst_input=analyst_input,
        score_decision=decision,
        revision_number=revision_number,
    )
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
            input_artifact=(
                draft_input if config.pricing_policy == "direct_mimo" else analyst_input
            ),
            requested_output_type=StatementDraft,
            input_artifact_ids=(candidate.quote_block_id,),
            operation_id=operation_id,
            config=config,
            clock=clock,
            objective_validator=validate_draft,
            run_id=candidate.run_id,
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


def _persist_mvp10_portfolio(
    db_path: str,
    planner: PlannerOutput,
    researchers: ResearcherPairResult,
    analysis: AnalysisStageResult,
    clock: Callable[[], datetime],
    *,
    stopping_reason: str,
    research_round: ResearchRound = ResearchRound.INITIAL,
    finalize: bool = False,
) -> PortfolioCoverageAssessment | None:
    """Append a transparent outcome for each discovered source and final portfolio state."""
    existing = read_portfolio_coverage_assessment(db_path, planner.run_id)
    if existing is not None:
        return existing
    snapshots = _snapshot_lookup(researchers)
    candidates = {
        candidate.retrieval_attempt_id: candidate
        for side in (researchers.supporting, researchers.opposing)
        for candidate in side.candidates
    }
    decisions = {item.quote_block_id: item for item in analysis.analyst_decisions}
    reviews = {item.quote_block_id: item for item in analysis.reviewer_decisions}
    ledgers = {item.quote_block_id: item for item in analysis.ledger_records}
    attempts = tuple(read_model_route_attempts(db_path, planner.run_id))
    entries: list[EvidenceTrailEntry] = []
    for side in (researchers.supporting, researchers.opposing):
        if side.retrieval_batch is None:
            continue
        for item in side.retrieval_batch.outcomes:
            retrieval = item.retrieval
            snapshot = snapshots.get(retrieval.retrieval_attempt_id)
            candidate = candidates.get(retrieval.retrieval_attempt_id)
            role = EvidenceRole.SUPPORTING if side.stance == "supporting" else EvidenceRole.OPPOSING
            family = identify_source_family(snapshot) if snapshot is not None else None
            outcome, explanation, failure_code = _mvp10_outcome_for_retrieval(
                item, candidate, decisions, reviews, ledgers
            )
            if family is not None:
                entry_stub = EvidenceTrailEntry(
                    trail_entry_id=uuid5(
                        URL_NAMESPACE,
                        f"mvp10-trail::{planner.run_id}::{retrieval.retrieval_attempt_id}",
                    ),
                    run_id=planner.run_id,
                    retrieval_attempt_id=retrieval.retrieval_attempt_id,
                    research_round=research_round,
                    role=role,
                    source_title=_mvp10_source_title(retrieval.resolved_url),
                    source_domain=_mvp10_source_domain(retrieval.resolved_url),
                    original_url=retrieval.source_url,
                    resolved_url=retrieval.resolved_url,
                    source_family=family,
                    retrieval_method="provider acquisition",
                    snapshot_status="snapshotted",
                    outcome=outcome,
                    explanation=explanation,
                    technical_failure_code=failure_code,
                    model_attempt_ids=_mvp10_attempt_ids(attempts, snapshot, candidate),
                    accepted_statement=(
                        ledgers[candidate.quote_block_id].approved_factual_statement
                        if candidate is not None and candidate.quote_block_id in ledgers
                        else None
                    ),
                    accepted_quote=(
                        candidate.extracted_quote_block if candidate is not None else None
                    ),
                    snapshot_sha256=snapshot.snapshot_sha256,
                    cost_incurred=bool(_mvp10_attempt_ids(attempts, snapshot, candidate)),
                    created_at=_aware_phase9_time(clock(), "trail created_at"),
                )
                insert_source_family_member(db_path, entry_stub)
            else:
                entry_stub = EvidenceTrailEntry(
                    trail_entry_id=uuid5(
                        URL_NAMESPACE,
                        f"mvp10-trail::{planner.run_id}::{retrieval.retrieval_attempt_id}",
                    ),
                    run_id=planner.run_id,
                    retrieval_attempt_id=retrieval.retrieval_attempt_id,
                    research_round=research_round,
                    role=role,
                    source_title=_mvp10_source_title(retrieval.resolved_url),
                    source_domain=_mvp10_source_domain(retrieval.resolved_url),
                    original_url=retrieval.source_url,
                    resolved_url=retrieval.resolved_url,
                    retrieval_method="provider acquisition",
                    snapshot_status="not snapshotted",
                    outcome=outcome,
                    explanation=explanation,
                    technical_failure_code=failure_code,
                    created_at=_aware_phase9_time(clock(), "trail created_at"),
                )
            entries.append(entry_stub)
            insert_evidence_trail_entry(db_path, entry_stub)
    for ledger in analysis.ledger_records:
        candidate = next(
            item for item in candidates.values() if item.quote_block_id == ledger.quote_block_id
        )
        family = identify_source_family(snapshots[candidate.snapshot_id])
        insert_portfolio_item(
            db_path,
            PortfolioItem(
                run_id=planner.run_id,
                ledger_claim_id=ledger.ledger_claim_id,
                source_family_id=family.source_family_id,
                role=(
                    EvidenceRole.SUPPORTING
                    if ledger.stance.value == "supporting"
                    else EvidenceRole.OPPOSING
                ),
                research_round=research_round,
                added_at=_aware_phase9_time(clock(), "portfolio added_at"),
            ),
        )
    if not finalize:
        return None
    return _finalize_mvp10_portfolio(
        db_path,
        planner.run_id,
        research_rounds=1 if research_round is ResearchRound.INITIAL else 2,
        stopping_reason=stopping_reason,
        clock=clock,
    )


def _finalize_mvp10_portfolio(
    db_path: str,
    run_id: UUID,
    *,
    research_rounds: int,
    stopping_reason: str,
    clock: Callable[[], datetime],
) -> PortfolioCoverageAssessment:
    """Freeze the final coverage after every available source outcome is appended."""
    existing = read_portfolio_coverage_assessment(db_path, run_id)
    if existing is not None:
        return existing
    entries = read_evidence_trail_entries(db_path, run_id)
    assessment = assess_portfolio(
        run_id,
        entries,
        research_rounds=research_rounds,
        stopping_reason=stopping_reason,
        important_missing_evidence=(
            "No independent opposing or limitation source family was approved."
            if not any(
                item.role is EvidenceRole.OPPOSING
                for item in entries
                if item.outcome is EvidenceTrailOutcome.ACCEPTED
            )
            else "",
        ),
        assessed_at=_aware_phase9_time(clock(), "portfolio assessed_at"),
    )
    insert_portfolio_coverage_assessment(db_path, assessment)
    return assessment


def _mvp10_outcome_for_retrieval(
    outcome: object,
    candidate: CandidateQuoteBlock | None,
    decisions: dict[UUID, ScoreDecision],
    reviews: dict[UUID, StatementReviewResult],
    ledgers: dict[UUID, LedgerRecord],
) -> tuple[EvidenceTrailOutcome, str, str | None]:
    """Map typed retrieval and review artifacts to one plain-language source outcome."""
    scrape_status = outcome.scrape_status
    failure_code = outcome.failure_code
    if getattr(scrape_status, "value", scrape_status) in {"duplicate_url", "duplicate_content"}:
        return (
            EvidenceTrailOutcome.DUPLICATE,
            "This source belongs to an existing source family.",
            failure_code,
        )
    if getattr(scrape_status, "value", scrape_status) == "unsupported":
        return (
            EvidenceTrailOutcome.UNSUPPORTED_CONTENT,
            "The source content type is unsupported.",
            failure_code,
        )
    if candidate is None:
        if failure_code == "timeout":
            return (
                EvidenceTrailOutcome.INACCESSIBLE,
                "The source could not be accessed in time.",
                failure_code,
            )
        return (
            EvidenceTrailOutcome.RETRIEVAL_FAILURE,
            "The source could not be processed into usable evidence.",
            failure_code,
        )
    decision = decisions.get(candidate.quote_block_id)
    if decision is not None and not decision.approved:
        return (
            EvidenceTrailOutcome.ANALYST_REJECTED,
            "The evidence did not meet Analyst requirements.",
            None,
        )
    review = reviews.get(candidate.quote_block_id)
    if review is not None and not review.approved:
        return (
            EvidenceTrailOutcome.REVIEWER_REJECTED,
            "The factual statement did not pass independent review.",
            review.failure_code.value if review.failure_code else None,
        )
    if candidate.quote_block_id in ledgers:
        return (
            EvidenceTrailOutcome.ACCEPTED,
            "Accepted into the Reviewer-approved evidence portfolio.",
            None,
        )
    return (
        EvidenceTrailOutcome.NOT_RELEVANT,
        "The source was valid but did not add sufficiently relevant approved evidence.",
        None,
    )


def _mvp10_attempt_ids(
    attempts: Sequence[ModelRouteAttempt],
    snapshot: SourceSnapshot,
    candidate: CandidateQuoteBlock | None,
) -> tuple[UUID, ...]:
    artifact_ids = {snapshot.snapshot_id}
    if candidate is not None:
        artifact_ids.add(candidate.quote_block_id)
    return tuple(
        item.attempt_id for item in attempts if artifact_ids.intersection(item.input_artifact_ids)
    )


def _mvp10_source_domain(url: str) -> str:
    without_scheme = url.partition("://")[2]
    domain = without_scheme.partition("/")[0]
    return domain or "unknown source"


def _mvp10_source_title(url: str) -> str:
    return _mvp10_source_domain(url)


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
        _raise_if_cancelled(db_path, resolved_run_id)
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
        reserved_tokens, reserved_cost = _conservative_reservation(request, alias, config)
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
            reserved_tokens=reserved_tokens,
            reserved_cost_usd=reserved_cost,
        )
        try:
            reserved = reserve_model_route_attempt(
                db_path,
                reservation,
                max_model_calls=config.budget.max_model_calls,
                max_total_tokens=(
                    config.budget.max_total_tokens if config.require_budget_reservations else None
                ),
                max_total_cost_usd=(
                    config.budget.max_total_cost_usd if config.require_budget_reservations else None
                ),
            )
        except ModelAttemptBudgetError as exc:
            raise Phase9OrchestrationError(_agent_stage(stage), str(exc)) from exc
        if reserved.status is not ModelAttemptStatus.RUNNING:
            previous_failure = reserved
            continue
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
            usage = _failure_usage(provider, exc)
            finished = _finished_attempt(
                reservation,
                status=ModelAttemptStatus.FAILED,
                ended_at=exc.record.ended_at,
                usage=usage,
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
        _enforce_usage_budget(db_path, resolved_run_id, config, stage)
        _raise_if_cancelled(db_path, resolved_run_id)
        if finished.status is ModelAttemptStatus.COMPLETED:
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
        reserved_tokens=reservation.reserved_tokens,
        reserved_cost_usd=reservation.reserved_cost_usd,
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


def _conservative_reservation(
    request: LLMRequest,
    alias: ModelAlias,
    config: ProviderOrchestrationConfig,
) -> tuple[int | None, float | None]:
    if not config.require_budget_reservations:
        return None, None
    if config.budget.max_total_tokens is None or config.budget.max_total_cost_usd is None:
        raise Phase9OrchestrationError(
            _agent_stage(request.stage),
            "strict provider runs require token and cost ceilings before every call",
        )
    if config.pricing_policy == "direct_mimo":
        if alias is not ModelAlias.MIMO_V25_PRO:
            raise Phase9OrchestrationError(
                _agent_stage(request.stage),
                "direct MiMo pricing permits only MiMo Pro",
            )
        cap = DIRECT_MIMO_PRICE_CAP
    else:
        cap = COMPATIBILITY_PRICE_CAPS.get(alias.value)
    if cap is None:
        raise Phase9OrchestrationError(
            _agent_stage(request.stage),
            "route identity or pricing is unknown; reservation failed closed",
        )
    input_tokens = conservative_token_estimate(request.rendered_prompt)
    output_tokens = config.reserved_output_tokens_per_call
    return (
        input_tokens + output_tokens,
        float(cap.upper_bound(input_tokens, output_tokens)),
    )


def _failure_usage(
    provider: LLMProvider,
    exc: LLMInvocationError,
) -> ModelUsageMetadata | None:
    cause = exc.__cause__
    usage = getattr(cause, "usage", None)
    if isinstance(usage, ModelUsageMetadata):
        return usage
    reader = getattr(provider, "failure_usage_for", None)
    if callable(reader):
        usage = reader()
        if usage is not None and not isinstance(usage, ModelUsageMetadata):
            raise ValueError("provider failure usage must be ModelUsageMetadata")
        return usage
    return None


def _enforce_usage_budget(
    db_path: str,
    run_id: UUID,
    config: ProviderOrchestrationConfig,
    stage: LLMStage,
) -> None:
    attempts = read_model_route_attempts(db_path, run_id)
    accounting = summarize_model_usage(attempts)
    if (
        config.budget.max_total_tokens is not None
        and accounting.conservative_reserved_tokens is None
    ):
        raise Phase9OrchestrationError(
            _agent_stage(stage),
            "model token usage is incomplete and the remaining token budget cannot be proven",
        )
    if (
        config.budget.max_total_cost_usd is not None
        and accounting.conservative_reserved_cost_usd is None
    ):
        raise Phase9OrchestrationError(
            _agent_stage(stage),
            "model cost usage is incomplete and the remaining cost budget cannot be proven",
        )
    if (
        config.budget.max_total_tokens is not None
        and accounting.conservative_reserved_tokens is not None
        and accounting.conservative_reserved_tokens > config.budget.max_total_tokens
    ):
        raise Phase9OrchestrationError(
            _agent_stage(stage),
            (
                f"model token budget {config.budget.max_total_tokens} exceeded "
                f"with {accounting.conservative_reserved_tokens} conservative tokens"
            ),
        )
    if (
        config.budget.max_total_cost_usd is not None
        and accounting.conservative_reserved_cost_usd is not None
        and accounting.conservative_reserved_cost_usd > config.budget.max_total_cost_usd
    ):
        raise Phase9OrchestrationError(
            _agent_stage(stage),
            (
                f"model cost budget {config.budget.max_total_cost_usd} exceeded "
                f"with {accounting.conservative_reserved_cost_usd:.6f} conservative USD"
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
    provider_code = getattr(cause, "code", None)
    code_value = getattr(provider_code, "value", provider_code)
    if code_value in {"timeout", "rate_limit", "transient_outage"}:
        return "timeout" if code_value == "timeout" else "transient_failure"
    if code_value in {"malformed_json", "malformed_success_response", "truncated_output"}:
        return "malformed_output"
    if code_value == "schema_validation_failure":
        return "schema_validation_failure"
    if code_value in {
        "authentication_failure",
        "permanent_request_failure",
        "provider_refusal",
        "returned_model_mismatch",
        "unknown_pricing",
        "cost_ceiling_exceeded",
        "malformed_usage_metadata",
        "capability_mismatch",
        "missing_configuration",
    }:
        return str(code_value)
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
