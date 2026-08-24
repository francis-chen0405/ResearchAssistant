"""Phase-10 bridge from v2 Analyst drafts to Reviewer-approved immutable Ledger records."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from uuid import NAMESPACE_URL, UUID, uuid5

from agents.analyst import LedgerAdmissionRequest, ValidatedLedgerPayload, admit_ledger_record
from agents.reviewer import (
    ReviewerDecision,
    build_reviewer_input,
    build_statement_review_result,
    validate_reviewer_decision,
)
from models import (
    CandidateQuoteBlock,
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    StatementDraft,
    StatementReviewResult,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2LedgerProvenance,
    V2ReviewerLedgerBatchResult,
    V2ReviewerLedgerSourceResult,
    V2ReviewerLedgerState,
    entailment_for_claim_fit,
)
from money import add_usd
from providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationError,
    LLMProvider,
    LLMRequest,
    LLMStage,
    ModelAlias,
    RetryMetadata,
    invoke_llm,
    load_prompt,
    render_stage_prompt,
)
from providers.pricing import conservative_token_estimate
from providers.v2_routing import V2RoutingConfig
from store import (
    ModelAttemptBudgetError,
    finish_model_route_attempt,
    insert_v2_artifact,
    insert_v2_ledger_admission,
    read_model_route_attempts,
    read_v2_artifact,
    reserve_model_route_attempt,
)

V2_REVIEWER_LEDGER_ARTIFACT_KEY = "phase-10-reviewer-ledger"
V2_REVIEWER_LEDGER_POLICY_VERSION = "v2rledger_v2"


def run_v2_reviewer_ledger(
    *,
    db_path: str | Path,
    analyst_result: V2EvidenceAnalystBatchResult,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    artifact_key: str = V2_REVIEWER_LEDGER_ARTIFACT_KEY,
    clock: Callable[[], datetime] | None = None,
) -> V2ReviewerLedgerBatchResult:
    """Review v2 drafts with MiMo and admit only exact application-validated records."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    stored = _read_artifact(path, analyst_result.run_id, artifact_key)
    if stored is not None:
        result = V2ReviewerLedgerBatchResult.model_validate_json(stored)
        if result.analyst_result != analyst_result:
            raise ValueError("persisted Phase-10 result does not match the Phase-9 result")
        return result

    route = routing_config.preflight().for_stage(LLMStage.REVIEWER)
    if route.logical_alias is not ModelAlias.MIMO_V25_PRO:
        raise ValueError("fresh v2 Reviewer work must use MiMo-v2.5-Pro")
    if V2_LLM_ROUTING.for_stage(LLMStage.REVIEWER).primary is not route.logical_alias:
        raise ValueError("configured Reviewer route does not match the v2 routing policy")

    batch = analyst_result.input
    survivors = {item.source_id: item for item in batch.queue_result.input.survivors}
    statuses = {item.source_id: item for item in batch.queue_result.source_statuses}
    candidates = {item.source_id: item for item in batch.queued_candidates}
    results: list[V2ReviewerLedgerSourceResult] = []
    for analyst_source in analyst_result.source_results:
        survivor = survivors[analyst_source.source_id]
        if analyst_source.direction is not survivor.direction:
            raise ValueError("Phase-9 evidence direction must match its persisted survivor")
        batch.directions.require_permitted(analyst_source.direction)
        provenance = V2LedgerProvenance(
            source_id=survivor.source_id,
            research_direction=survivor.direction,
            discovery_round=survivor.research_round,
            source_family_id=survivor.source_family_id,
            recommended=statuses[survivor.source_id].recommended,
            relevant_gap_ids=statuses[survivor.source_id].gap_ids,
        )
        source_artifact_key = _source_artifact_key(analyst_source.source_id)
        existing = _read_artifact(path, analyst_result.run_id, source_artifact_key)
        if existing is not None:
            result = V2ReviewerLedgerSourceResult.model_validate_json(existing)
        else:
            result = _process_source(
                path=path,
                analyst_result=analyst_result,
                source_result=analyst_source,
                provenance=provenance,
                candidate_input=candidates.get(analyst_source.source_id),
                llm_provider=llm_provider,
                routing_config=routing_config,
                clock=now,
            )
            insert_v2_artifact(path, source_artifact_key, result, _aware_now(now))
        if result.source_id != analyst_source.source_id or result.provenance != provenance:
            raise ValueError("persisted Phase-10 source result does not match source provenance")
        results.append(result)

    completed_at = _aware_now(now)
    output = V2ReviewerLedgerBatchResult(
        run_id=analyst_result.run_id,
        analyst_result=analyst_result,
        source_results=tuple(results),
        completed_at=completed_at,
    )
    insert_v2_artifact(path, artifact_key, output, completed_at)
    return output


def _process_source(
    *,
    path: str,
    analyst_result: V2EvidenceAnalystBatchResult,
    source_result: V2EvidenceAnalystSourceResult,
    provenance: V2LedgerProvenance,
    candidate_input: V2EvidenceAnalystCandidateInput | None,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
) -> V2ReviewerLedgerSourceResult:
    if source_result.state is V2EvidenceAnalystState.NOT_QUEUED:
        return _terminal(source_result, provenance, V2ReviewerLedgerState.NOT_QUEUED)
    if source_result.state is V2EvidenceAnalystState.REJECTED:
        return _terminal(
            source_result,
            provenance,
            V2ReviewerLedgerState.ANALYST_REJECTED,
            source_result.failure,
        )
    if source_result.state is V2EvidenceAnalystState.FAILED:
        return _terminal(
            source_result,
            provenance,
            V2ReviewerLedgerState.ANALYST_FAILED,
            source_result.failure,
        )
    if not isinstance(candidate_input, V2EvidenceAnalystCandidateInput):
        raise ValueError("Reviewer-ready source is missing its exact Phase-9 candidate")
    if (
        source_result.candidate is None
        or source_result.score_decision is None
        or source_result.statement_draft is None
    ):
        raise ValueError("Reviewer-ready source must retain candidate, score, and draft")

    first, failure = _review_once(
        path,
        analyst_result,
        source_result.source_id,
        source_result.candidate,
        source_result.statement_draft,
        llm_provider,
        routing_config,
        clock,
        0,
    )
    if first is None:
        return _terminal(source_result, provenance, V2ReviewerLedgerState.REVIEWER_FAILED, failure)
    if not first.approved:
        return _terminal(
            source_result,
            provenance,
            V2ReviewerLedgerState.REVIEWER_REJECTED,
            reviews=(first,),
        )

    final = first
    if final.approved_factual_statement is None:
        raise ValueError("approved Reviewer result must retain its exact statement")
    record = admit_ledger_record(
        LedgerAdmissionRequest(
            candidate=source_result.candidate,
            snapshot=candidate_input.snapshot,
            score_decision=source_result.score_decision,
            statement_drafts=[source_result.statement_draft],
            review_results=[final],
            approved_factual_statement=final.approved_factual_statement,
            entailment=entailment_for_claim_fit(source_result.score_decision.claim_fit),
        ),
        derive_ledger_claim_id=_derive_v2_ledger_claim_id,
        validation_clock=clock,
    )
    insert_v2_ledger_admission(path, record, provenance)
    return V2ReviewerLedgerSourceResult(
        run_id=analyst_result.run_id,
        source_id=source_result.source_id,
        direction=source_result.direction,
        state=V2ReviewerLedgerState.ADMITTED,
        provenance=provenance,
        review_results=(final,),
        ledger_record=record,
    )


def _terminal(
    source_result: V2EvidenceAnalystSourceResult,
    provenance: V2LedgerProvenance,
    state: V2ReviewerLedgerState,
    failure: str | None = None,
    reviews: tuple[StatementReviewResult, ...] = (),
) -> V2ReviewerLedgerSourceResult:
    return V2ReviewerLedgerSourceResult(
        run_id=source_result.run_id,
        source_id=source_result.source_id,
        direction=source_result.direction,
        state=state,
        provenance=provenance,
        review_results=reviews,
        failure=failure,
    )


def _review_once(
    path: str,
    batch: V2EvidenceAnalystBatchResult,
    source_id: UUID,
    candidate: CandidateQuoteBlock,
    draft: StatementDraft,
    provider: LLMProvider,
    routing: V2RoutingConfig,
    clock: Callable[[], datetime],
    revision_number: int,
) -> tuple[StatementReviewResult | None, str | None]:
    reviewer_input = build_reviewer_input(candidate, draft)
    route = routing.preflight().for_stage(LLMStage.REVIEWER)
    prompt = load_prompt(LLMStage.REVIEWER)
    request = LLMRequest(
        run_id=batch.run_id,
        stage=LLMStage.REVIEWER,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, reviewer_input, ReviewerDecision),
        input_artifact=reviewer_input,
        input_artifact_ids=(draft.statement_draft_id, candidate.quote_block_id),
        requested_output_type=ReviewerDecision,
        model_alias=ModelAlias.MIMO_V25_PRO,
        pinned_model_snapshot=route.physical_model,
        configured_fallbacks=(),
        generation=V2_LLM_ROUTING.for_stage(LLMStage.REVIEWER).generation,
        source_id=source_id,
    )
    operation_id = uuid5(
        NAMESPACE_URL, f"v2-phase10::{batch.run_id}::{source_id}::reviewer::{revision_number}"
    )
    attempts = read_model_route_attempts(path, batch.run_id, operation_id)
    if attempts:
        attempt = attempts[0]
        if attempt.status is ModelAttemptStatus.COMPLETED and attempt.output_json is not None:
            decision = ReviewerDecision.model_validate_json(attempt.output_json)
            validate_reviewer_decision(draft, reviewer_input, decision)
            return build_statement_review_result(
                draft,
                reviewer_input,
                decision,
                reviewer_prompt_version=prompt.version,
                reviewer_model_name=route.physical_model,
                reviewed_at=_aware_now(clock),
            ), None
        return None, "Reviewer attempt was already exhausted before restart"
    reservation = routing.preflight().reserve(
        LLMStage.REVIEWER, conservative_token_estimate(request.rendered_prompt)
    )
    attempt_id = uuid5(NAMESPACE_URL, f"v2-phase10-attempt::{operation_id}::1")
    running = ModelRouteAttempt(
        run_id=batch.run_id,
        operation_id=operation_id,
        attempt_id=attempt_id,
        stage=LLMStage.REVIEWER.value,
        output_type=ReviewerDecision.__name__,
        model_alias=route.logical_alias.value,
        pinned_model_snapshot=route.physical_model,
        route_index=0,
        attempt_number=1,
        input_artifact_ids=(draft.statement_draft_id, candidate.quote_block_id),
        status=ModelAttemptStatus.RUNNING,
        started_at=_aware_now(clock),
        reserved_tokens=reservation.reserved_tokens,
        reserved_cost_usd=reservation.reserved_cost_usd,
    )
    try:
        ceiling = _budget_ceiling(path, batch)
        reserve_model_route_attempt(
            path,
            running,
            max_model_calls=ceiling[0],
            max_total_tokens=ceiling[1],
            max_total_cost_usd=ceiling[2],
        )
    except ModelAttemptBudgetError as exc:
        return None, str(exc)
    timer = monotonic()
    try:
        invocation = invoke_llm(
            provider,
            request,
            retry_metadata=RetryMetadata(),
            clock=clock,
            invocation_id_factory=lambda: attempt_id,
        )
        decision = ReviewerDecision.model_validate(invocation.output_artifact)
        validate_reviewer_decision(draft, reviewer_input, decision)
        usage = _usage(provider, request, decision, invocation.record)
        finish_model_route_attempt(
            path,
            running.model_copy(
                update={
                    "status": ModelAttemptStatus.COMPLETED,
                    "ended_at": _aware_now(clock),
                    "latency_ms": max(0.0, (monotonic() - timer) * 1000),
                    "usage": usage,
                    "output_json": decision.model_dump_json(),
                }
            ),
        )
        return build_statement_review_result(
            draft,
            reviewer_input,
            decision,
            reviewer_prompt_version=prompt.version,
            reviewer_model_name=route.physical_model,
            reviewed_at=_aware_now(clock),
        ), None
    except (LLMInvocationError, ValueError, TypeError, RuntimeError) as exc:
        finish_model_route_attempt(
            path,
            running.model_copy(
                update={
                    "status": ModelAttemptStatus.FAILED,
                    "failure_code": "reviewer_attempt_failed",
                    "failure_reason": str(exc)[:1000],
                    "ended_at": _aware_now(clock),
                    "latency_ms": max(0.0, (monotonic() - timer) * 1000),
                }
            ),
        )
        return None, f"{type(exc).__name__}: {exc}"[:1000]


def _derive_v2_ledger_claim_id(payload: ValidatedLedgerPayload) -> UUID:
    review = payload.approved_review
    if review.reviewer_approval_id is None:
        raise ValueError("approved Reviewer result is required for Ledger ID derivation")
    return uuid5(
        NAMESPACE_URL,
        f"{V2_REVIEWER_LEDGER_POLICY_VERSION}::{payload.candidate.run_id}::{review.reviewer_approval_id}::{payload.approved_factual_statement}",
    )


def _budget_ceiling(path: str, batch: V2EvidenceAnalystBatchResult) -> tuple[int, int, Decimal]:
    attempts = read_model_route_attempts(path, batch.run_id)
    initial = batch.input.queue_result.initial_budget
    token_exposure = sum(
        item.usage.total_tokens
        if item.usage is not None and item.usage.total_tokens is not None
        else item.reserved_tokens or 0
        for item in attempts
    )
    cost_exposure = sum(
        (
            item.usage.cost_usd
            if item.usage is not None and item.usage.cost_usd is not None
            else item.reserved_cost_usd or Decimal("0")
            for item in attempts
        ),
        Decimal("0"),
    )
    return (
        len(attempts) + initial.physical_call_ceiling - initial.physical_calls_used,
        token_exposure + initial.tokens_remaining,
        add_usd(cost_exposure, initial.cost_remaining_usd),
    )


def _usage(
    provider: LLMProvider,
    request: LLMRequest,
    decision: ReviewerDecision,
    record: object,
) -> ModelUsageMetadata | None:
    usage_for = getattr(provider, "usage_for", None)
    if not callable(usage_for):
        return None
    usage = usage_for(request, decision, record)
    if usage is not None and not isinstance(usage, ModelUsageMetadata):
        raise TypeError("provider usage must be ModelUsageMetadata")
    return usage


def _source_artifact_key(source_id: UUID) -> str:
    return f"phase-10-reviewer-ledger-source-{source_id}"


def _read_artifact(path: str, run_id: UUID, key: str) -> str | None:
    try:
        return read_v2_artifact(path, run_id, key).payload_json
    except KeyError:
        return None


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase-10 timestamps must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
