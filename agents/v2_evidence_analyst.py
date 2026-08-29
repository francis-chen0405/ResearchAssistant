"""Luna semantic evidence analysis over exact fresh-v2 deep-analysis candidates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import TypeVar
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel

from agents.analyst import (
    create_statement_draft,
    score_candidate,
    statement_has_required_qualification,
)
from agents.researcher import parse_extracted_quote_block, verify_candidate_against_snapshot
from models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    ResearchDirection,
    V2CanonicalStatementModelOutput,
    V2CanonicalStatementRevisionLLMInput,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystLLMInput,
    V2EvidenceAnalystModelOutput,
    V2EvidenceAnalystRevisionResult,
    V2EvidenceAnalystSnapshotContext,
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2EvidenceRelationship,
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
    is_non_retryable_provider_error,
    load_prompt_file,
    render_stage_prompt,
)
from providers.pricing import conservative_token_estimate
from providers.v2_budget import V2CancellationRequested
from providers.v2_routing import V2RoutingConfig
from store import (
    ModelAttemptBudgetError,
    finish_model_route_attempt,
    insert_v2_artifact,
    read_model_route_attempts,
    read_v2_artifact,
    reserve_model_route_attempt,
)

V2_EVIDENCE_ANALYST_ARTIFACT_KEY = "phase-13-luna-evidence-analyst-analyzer-admission"
V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX = "phase-13-luna-evidence-analyst-source-v2"
V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX = "phase-13-luna-evidence-analyst-source"
V2_EVIDENCE_ANALYST_MAX_ATTEMPTS = 1
_PHASE9_OUTPUT_TYPES = frozenset(
    {V2EvidenceAnalystModelOutput.__name__, V2CanonicalStatementModelOutput.__name__}
)
_V2_ANALYST_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts/v2_evidence_analyst.md"
_CANONICAL_STATEMENT_RETRY_GUIDANCE = (
    "The prior attempt failed validation. Copy the input assessment's "
    "narrowest_supported_proposition character-for-character into the output "
    "narrowest_supported_proposition field. Do not paraphrase, shorten, expand, "
    "or normalize it. Only draft the canonical_factual_statement from that exact "
    "proposition and the supplied evidence limitations."
)
_CLAIM_FIT_2_RETRY_GUIDANCE = (
    "Because Claim Fit is 2, the canonical_factual_statement must explicitly scope "
    "the evidence to the source's population, sample, setting, time period, or "
    "reported association. Use a concrete scope marker such as 'among', 'within', "
    "'according to', 'reported', 'in this sample', or 'may'. Do not state the "
    "evidence as a universal claim."
)
_OutputT = TypeVar("_OutputT", bound=BaseModel)


class V2EvidenceAnalystFailure(RuntimeError):
    """Raised internally when one bounded Analyst logical operation is exhausted."""


def run_v2_evidence_analyst(
    *,
    db_path: str | Path,
    batch_input: V2EvidenceAnalystBatchInput,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    artifact_key: str = V2_EVIDENCE_ANALYST_ARTIFACT_KEY,
    clock: Callable[[], datetime] | None = None,
) -> V2EvidenceAnalystBatchResult:
    """Analyze the complete queue with Luna and persist status for every survivor."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    stored = _read_artifact(path, batch_input.run_id, artifact_key)
    if stored is not None:
        result = V2EvidenceAnalystBatchResult.model_validate_json(stored)
        if result.input != batch_input:
            raise ValueError("persisted Phase-13 input does not match the requested queue")
        return result

    analyst_route = routing_config.preflight().for_stage(LLMStage.ANALYST)
    extractor_route = routing_config.preflight().for_stage(LLMStage.EXTRACTOR)
    if analyst_route.logical_alias is not ModelAlias.GPT_5_6_LUNA_HIGH:
        raise ValueError("fresh v2 Evidence Analyst work must use GPT-5.6 Luna High")
    if extractor_route.logical_alias is not ModelAlias.MIMO_V25_PRO:
        raise ValueError("v2 exact passage selection must remain on MiMo-v2.5-Pro")
    if V2_LLM_ROUTING.for_stage(LLMStage.ANALYST).primary is not analyst_route.logical_alias:
        raise ValueError("configured Analyst route does not match the v2 routing policy")

    queued = {item.source_id: item for item in batch_input.queued_candidates}
    extraction_failures = {item.source_id: item.failure for item in batch_input.extraction_failures}
    results: list[V2EvidenceAnalystSourceResult] = []
    for survivor in batch_input.queue_result.input.survivors:
        candidate_input = queued.get(survivor.source_id)
        if candidate_input is None:
            queued_for_analysis = survivor.source_id in batch_input.queue_result.queued_source_ids
            results.append(
                V2EvidenceAnalystSourceResult(
                    run_id=batch_input.run_id,
                    source_id=survivor.source_id,
                    direction=survivor.direction,
                    state=(
                        V2EvidenceAnalystState.FAILED
                        if queued_for_analysis
                        else V2EvidenceAnalystState.NOT_QUEUED
                    ),
                    failure=(
                        extraction_failures.get(
                            survivor.source_id,
                            "Exact extraction did not produce a deterministically valid candidate.",
                        )
                        if queued_for_analysis
                        else None
                    ),
                )
            )
            continue
        source_artifact_key = _source_artifact_key(survivor.source_id)
        persisted_source = _read_source_result(path, batch_input.run_id, survivor.source_id)
        if persisted_source is not None:
            source_result = persisted_source
        else:
            source_result = _analyze_source(
                db_path=path,
                batch_input=batch_input,
                source_input=candidate_input,
                llm_provider=llm_provider,
                routing_config=routing_config,
                clock=now,
            )
            insert_v2_artifact(path, source_artifact_key, source_result, _aware_now(now))
        if source_result.source_id != survivor.source_id:
            raise ValueError("persisted Phase-13 source result does not match survivor")
        results.append(source_result)

    completed_at = _aware_now(now)
    output = V2EvidenceAnalystBatchResult(
        run_id=batch_input.run_id,
        input=batch_input,
        source_results=tuple(results),
        completed_at=completed_at,
    )
    insert_v2_artifact(path, artifact_key, output, completed_at)
    return output


def revise_v2_canonical_statement(
    *,
    db_path: str | Path,
    batch_input: V2EvidenceAnalystBatchInput,
    source_result: V2EvidenceAnalystSourceResult,
    reviewer_rationale: str,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime] | None = None,
) -> V2EvidenceAnalystRevisionResult:
    """Run the historical post-Reviewer Luna revision under the same physical budget."""
    now = clock or _utc_now
    if source_result.run_id != batch_input.run_id:
        raise ValueError("revision source result must match the Phase-9 run")
    if source_result.state is not V2EvidenceAnalystState.READY_FOR_REVIEWER:
        raise ValueError("only a Reviewer-ready Analyst result may be revised")
    if (
        source_result.candidate is None
        or source_result.assessment is None
        or source_result.score_decision is None
        or source_result.statement_draft is None
    ):
        raise ValueError("Reviewer-directed revision requires complete Analyst artifacts")
    source_input = next(
        (
            item
            for item in batch_input.queued_candidates
            if item.source_id == source_result.source_id
        ),
        None,
    )
    if source_input is None or source_input.candidate != source_result.candidate:
        raise ValueError("revision cannot substitute a different exact candidate")
    verify_candidate_against_snapshot(source_input.snapshot, source_result.candidate)
    path = str(Path(db_path).resolve())
    revision_key = _revision_artifact_key(source_result.source_id)
    persisted = _read_artifact(path, batch_input.run_id, revision_key)
    if persisted is not None:
        result = V2EvidenceAnalystRevisionResult.model_validate_json(persisted)
        if result.previous_statement_draft_id != source_result.statement_draft.statement_draft_id:
            raise ValueError("persisted revision does not match the Reviewer-ready statement")
        return result
    revision_input = V2CanonicalStatementRevisionLLMInput(
        run_id=batch_input.run_id,
        exact_claim=batch_input.exact_claim,
        direction=source_result.direction,
        candidate=source_result.candidate,
        assessment=source_result.assessment,
        score_decision=source_result.score_decision,
        current_statement=source_result.statement_draft,
        reviewer_rationale=reviewer_rationale,
    )
    revised, attempt_ids = _invoke_bounded_analyst(
        db_path=path,
        batch_input=batch_input,
        source_id=source_result.source_id,
        operation="canonical-statement-revision",
        input_artifact=revision_input,
        output_type=V2CanonicalStatementModelOutput,
        llm_provider=llm_provider,
        routing_config=routing_config,
        clock=now,
        objective_validator=lambda output: _validate_statement_output(
            output,
            source_result.assessment,
            source_result.score_decision.claim_fit,
        ),
        retry_guidance=_canonical_statement_retry_guidance(source_result.score_decision.claim_fit),
        max_attempts=2,
    )
    statement = create_statement_draft(
        candidate=source_result.candidate,
        score_decision=source_result.score_decision,
        statement_draft_id=uuid5(
            NAMESPACE_URL,
            f"v2-phase9-revision::{batch_input.run_id}::{source_result.candidate.quote_block_id}",
        ),
        draft_statement=revised.canonical_factual_statement,
        drafted_at=_aware_now(now),
    )
    result = V2EvidenceAnalystRevisionResult(
        run_id=batch_input.run_id,
        source_id=source_result.source_id,
        previous_statement_draft_id=source_result.statement_draft.statement_draft_id,
        revised_statement=statement,
        analyst_attempt_ids=attempt_ids,
    )
    insert_v2_artifact(path, revision_key, result, _aware_now(now))
    return result


def _analyze_source(
    *,
    db_path: str,
    batch_input: V2EvidenceAnalystBatchInput,
    source_input: V2EvidenceAnalystCandidateInput,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
) -> V2EvidenceAnalystSourceResult:
    candidate = source_input.candidate
    attempt_ids: list[UUID] = []
    assessment: V2EvidenceAnalystModelOutput | None = None
    score_decision = None
    try:
        verify_candidate_against_snapshot(source_input.snapshot, candidate)
        semantic_input = V2EvidenceAnalystLLMInput(
            run_id=batch_input.run_id,
            exact_claim=batch_input.exact_claim,
            direction=source_input.direction,
            candidate=candidate,
            snapshot_context=V2EvidenceAnalystSnapshotContext(
                snapshot_id=source_input.snapshot.snapshot_id,
                snapshot_sha256=source_input.snapshot.snapshot_sha256,
                source_url=source_input.snapshot.source_url,
                word_count=source_input.snapshot.word_count,
                truncated=source_input.snapshot.truncated,
                preceding_context=parse_extracted_quote_block(
                    candidate.extracted_quote_block
                ).preceding_context,
                following_context=parse_extracted_quote_block(
                    candidate.extracted_quote_block
                ).following_context,
            ),
            targeted_gap_ids=tuple(
                dict.fromkeys(
                    gap_id
                    for survivor in batch_input.queue_result.input.survivors
                    if survivor.source_id == source_input.source_id
                    for provenance in survivor.search_provenance
                    if provenance.round_number == 4
                    for gap_id in provenance.targeted_gap_ids
                )
            )[:3],
        )
        assessment, score_attempts = _invoke_bounded_analyst(
            db_path=db_path,
            batch_input=batch_input,
            source_id=source_input.source_id,
            operation="analysis-and-statement",
            input_artifact=semantic_input,
            output_type=V2EvidenceAnalystModelOutput,
            llm_provider=llm_provider,
            routing_config=routing_config,
            clock=clock,
            objective_validator=lambda output: _validate_assessment(
                output, source_input.direction, semantic_input.targeted_gap_ids
            ),
            retry_guidance=None,
        )
        attempt_ids.extend(score_attempts)
        route = routing_config.preflight().for_stage(LLMStage.ANALYST)
        prompt = load_prompt_file(
            _V2_ANALYST_PROMPT_PATH,
            expected_stage=LLMStage.ANALYST,
        )
        score_decision = score_candidate(
            run_id=batch_input.run_id,
            quote_block_id=candidate.quote_block_id,
            evidence_quality=assessment.evidence_quality,
            claim_fit=assessment.claim_fit,
            rationale=_assessment_rationale(assessment),
            analyst_prompt_version=prompt.version,
            analyst_model_name=route.physical_model,
            scored_at=_aware_now(clock),
        )
        if not score_decision.approved:
            return V2EvidenceAnalystSourceResult(
                run_id=batch_input.run_id,
                source_id=source_input.source_id,
                direction=source_input.direction,
                state=V2EvidenceAnalystState.REJECTED,
                candidate=candidate,
                assessment=assessment,
                score_decision=score_decision,
                analyst_attempt_ids=tuple(attempt_ids),
            )
        statement_draft = create_statement_draft(
            candidate=candidate,
            score_decision=score_decision,
            statement_draft_id=uuid5(
                NAMESPACE_URL,
                f"v2-phase13-draft::{batch_input.run_id}::{candidate.quote_block_id}",
            ),
            draft_statement=assessment.canonical_factual_statement,
            drafted_at=_aware_now(clock),
        )
        return V2EvidenceAnalystSourceResult(
            run_id=batch_input.run_id,
            source_id=source_input.source_id,
            direction=source_input.direction,
            state=V2EvidenceAnalystState.READY_FOR_ADMISSION,
            candidate=candidate,
            assessment=assessment,
            score_decision=score_decision,
            statement_draft=statement_draft,
            analyst_attempt_ids=tuple(attempt_ids),
        )
    except V2CancellationRequested:
        raise
    except (V2EvidenceAnalystFailure, ValueError, TypeError, RuntimeError) as exc:
        if isinstance(exc, LLMInvocationError) and is_non_retryable_provider_error(exc):
            raise
        attempt_ids = list(_source_attempt_ids(db_path, batch_input.run_id, source_input.source_id))
        return V2EvidenceAnalystSourceResult(
            run_id=batch_input.run_id,
            source_id=source_input.source_id,
            direction=source_input.direction,
            state=V2EvidenceAnalystState.FAILED,
            candidate=candidate,
            assessment=assessment,
            score_decision=score_decision,
            analyst_attempt_ids=tuple(attempt_ids),
            failure=f"{type(exc).__name__}: {exc}"[:1000],
        )


def _invoke_bounded_analyst(
    *,
    db_path: str,
    batch_input: V2EvidenceAnalystBatchInput,
    source_id: UUID,
    operation: str,
    input_artifact: BaseModel,
    output_type: type[_OutputT],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime],
    objective_validator: Callable[[_OutputT], None],
    retry_guidance: str | None = None,
    max_attempts: int | None = None,
) -> tuple[_OutputT, tuple[UUID, ...]]:
    route = routing_config.preflight().for_stage(LLMStage.ANALYST)
    prompt = load_prompt_file(
        _V2_ANALYST_PROMPT_PATH,
        expected_stage=LLMStage.ANALYST,
    )
    base_rendered_prompt = render_stage_prompt(prompt, input_artifact, output_type)
    attempt_limit = max_attempts or V2_EVIDENCE_ANALYST_MAX_ATTEMPTS
    operation_id = uuid5(
        NAMESPACE_URL, f"v2-phase13::{batch_input.run_id}::{source_id}::{operation}"
    )
    attempts = read_model_route_attempts(db_path, batch_input.run_id, operation_id)
    attempt_ids = [item.attempt_id for item in attempts]
    for attempt in attempts:
        if attempt.status is ModelAttemptStatus.COMPLETED:
            if attempt.output_type != output_type.__name__ or attempt.output_json is None:
                raise V2EvidenceAnalystFailure("persisted Analyst output type is incompatible")
            output = output_type.model_validate_json(attempt.output_json)
            objective_validator(output)
            return output, tuple(attempt_ids)
        if attempt.status is ModelAttemptStatus.RUNNING:
            ended_at = _aware_now(clock)
            finish_model_route_attempt(
                db_path,
                attempt.model_copy(
                    update={
                        "status": ModelAttemptStatus.FAILED,
                        "failure_code": "interrupted_attempt",
                        "failure_reason": "unfinished Analyst attempt recovered on restart",
                        "ended_at": ended_at,
                        "latency_ms": max(
                            0.0, (ended_at - attempt.started_at).total_seconds() * 1000
                        ),
                    }
                ),
            )
    if len(attempts) >= attempt_limit:
        raise V2EvidenceAnalystFailure(f"{operation} exhausted bounded Analyst retry")

    failures: list[str] = []
    for attempt_number in range(len(attempts) + 1, attempt_limit + 1):
        started_at = _aware_now(clock)
        rendered_prompt = base_rendered_prompt
        if attempt_number > 1 and retry_guidance is not None:
            rendered_prompt = (
                f"{rendered_prompt}\n\n<RETRY_VALIDATION_GUIDANCE>\n"
                f"{retry_guidance}\n</RETRY_VALIDATION_GUIDANCE>"
            )
        request = LLMRequest(
            run_id=batch_input.run_id,
            stage=LLMStage.ANALYST,
            prompt=prompt,
            rendered_prompt=rendered_prompt,
            input_artifact=input_artifact,
            input_artifact_ids=(source_id,),
            requested_output_type=output_type,
            pinned_model_snapshot=route.physical_model,
            model_alias=ModelAlias.GPT_5_6_LUNA_HIGH,
            configured_fallbacks=(),
            generation=V2_LLM_ROUTING.for_stage(LLMStage.ANALYST).generation,
            source_id=source_id,
        )
        reservation = routing_config.preflight().reserve(
            LLMStage.ANALYST, conservative_token_estimate(request.rendered_prompt)
        )
        attempt_id = uuid5(
            NAMESPACE_URL,
            f"v2-phase13-attempt::{operation_id}::{attempt_number}",
        )
        running = ModelRouteAttempt(
            run_id=batch_input.run_id,
            operation_id=operation_id,
            attempt_id=attempt_id,
            stage=LLMStage.ANALYST.value,
            output_type=output_type.__name__,
            model_alias=route.logical_alias.value,
            pinned_model_snapshot=route.physical_model,
            route_index=0,
            attempt_number=attempt_number,
            input_artifact_ids=(source_id,),
            status=ModelAttemptStatus.RUNNING,
            retry_reason=("retry after prior Analyst failure" if attempt_number > 1 else None),
            started_at=started_at,
            reserved_tokens=reservation.reserved_tokens,
            reserved_cost_usd=reservation.reserved_cost_usd,
        )
        ceilings = _attempt_budget_ceilings(db_path, batch_input)
        try:
            reserve_model_route_attempt(
                db_path,
                running,
                max_model_calls=ceilings[0],
                max_total_tokens=ceilings[1],
                max_total_cost_usd=ceilings[2],
            )
        except ModelAttemptBudgetError as exc:
            raise V2EvidenceAnalystFailure(str(exc)) from exc
        attempt_ids.append(attempt_id)
        timer = monotonic()
        try:
            invocation = invoke_llm(
                llm_provider,
                request,
                retry_metadata=RetryMetadata(
                    attempt_number=attempt_number,
                    max_attempts=attempt_limit,
                    retry_count=attempt_number - 1,
                    automatic_retry_performed=attempt_number > 1,
                ),
                clock=clock,
                invocation_id_factory=lambda attempt_id=attempt_id: attempt_id,
            )
            output = output_type.model_validate(invocation.output_artifact)
            objective_validator(output)
            usage = _provider_usage(llm_provider, request, output, invocation.record)
            completed = running.model_copy(
                update={
                    "status": ModelAttemptStatus.COMPLETED,
                    "ended_at": _aware_now(clock),
                    "latency_ms": max(0.0, (monotonic() - timer) * 1000),
                    "usage": usage,
                    "output_json": output.model_dump_json(),
                }
            )
            finish_model_route_attempt(db_path, completed)
            return output, tuple(attempt_ids)
        except V2CancellationRequested:
            raise
        except (LLMInvocationError, ValueError, TypeError, RuntimeError) as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
            failed = running.model_copy(
                update={
                    "status": ModelAttemptStatus.FAILED,
                    "failure_code": "analyst_attempt_failed",
                    "failure_reason": str(exc)[:1000],
                    "ended_at": _aware_now(clock),
                    "latency_ms": max(0.0, (monotonic() - timer) * 1000),
                    "usage": _provider_failure_usage(llm_provider),
                }
            )
            finish_model_route_attempt(db_path, failed)
            if isinstance(exc, LLMInvocationError) and is_non_retryable_provider_error(exc):
                raise
    raise V2EvidenceAnalystFailure(
        f"{operation} exhausted bounded Analyst retry: {'; '.join(failures)}"
    )


def _validate_assessment_direction(
    assessment: V2EvidenceAnalystModelOutput,
    direction: ResearchDirection,
) -> None:
    if assessment.canonical_factual_statement is None:
        raise ValueError("combined Analyst output requires a final factual statement")
    forbidden = (
        V2EvidenceRelationship.CHALLENGES
        if direction is ResearchDirection.SUPPORT
        else V2EvidenceRelationship.SUPPORTS
    )
    if assessment.relationship_to_claim is forbidden:
        raise ValueError("Analyst relationship cannot cross the queued evidence direction")


def _validate_assessment(
    assessment: V2EvidenceAnalystModelOutput,
    direction: ResearchDirection,
    targeted_gap_ids: tuple[str, ...],
) -> None:
    """Validate direction and restrict claimed coverage to the source's Round-4 Gap links."""
    _validate_assessment_direction(assessment, direction)
    if not set(assessment.addressed_gap_ids).issubset(targeted_gap_ids):
        raise ValueError("Analyst cannot claim coverage for an unrelated Gap")


def _validate_statement_output(
    output: V2CanonicalStatementModelOutput,
    assessment: V2EvidenceAnalystModelOutput,
    claim_fit: int,
) -> None:
    if output.narrowest_supported_proposition != assessment.narrowest_supported_proposition:
        raise ValueError("canonical drafting cannot change the supported proposition")
    if claim_fit == 2 and not statement_has_required_qualification(
        output.canonical_factual_statement
    ):
        raise ValueError("Claim Fit 2 statements require an explicit scope qualification")


def _canonical_statement_retry_guidance(claim_fit: int) -> str:
    """Return targeted repair guidance without changing strict statement validation."""
    if claim_fit == 2:
        return f"{_CANONICAL_STATEMENT_RETRY_GUIDANCE} {_CLAIM_FIT_2_RETRY_GUIDANCE}"
    return _CANONICAL_STATEMENT_RETRY_GUIDANCE


def _assessment_rationale(assessment: V2EvidenceAnalystModelOutput) -> str:
    limitations = "; ".join(assessment.material_limitations) or "none stated"
    boundaries = "; ".join(assessment.inferential_boundaries) or "none stated"
    return (
        f"{assessment.reasoning} Relationship: {assessment.relationship_to_claim.value}. "
        f"Material limitations: {limitations}. Inferential boundaries: {boundaries}."
    )


def _attempt_budget_ceilings(
    db_path: str,
    batch_input: V2EvidenceAnalystBatchInput,
) -> tuple[int, int, Decimal]:
    attempts = read_model_route_attempts(db_path, batch_input.run_id)
    baseline = [item for item in attempts if item.output_type not in _PHASE9_OUTPUT_TYPES]
    initial = batch_input.queue_result.initial_budget
    remaining_calls = initial.physical_call_ceiling - initial.physical_calls_used
    baseline_tokens = sum(_token_exposure(item) for item in baseline)
    baseline_cost = sum((_cost_exposure(item) for item in baseline), Decimal("0"))
    return (
        len(baseline) + remaining_calls,
        baseline_tokens + initial.tokens_remaining,
        add_usd(baseline_cost, initial.cost_remaining_usd),
    )


def _token_exposure(attempt: ModelRouteAttempt) -> int:
    if attempt.usage is not None and attempt.usage.total_tokens is not None:
        return attempt.usage.total_tokens
    if attempt.reserved_tokens is not None:
        return attempt.reserved_tokens
    raise V2EvidenceAnalystFailure("existing model attempt has unprovable token exposure")


def _cost_exposure(attempt: ModelRouteAttempt) -> Decimal:
    if attempt.usage is not None and attempt.usage.cost_usd is not None:
        return attempt.usage.cost_usd
    if attempt.reserved_cost_usd is not None:
        return attempt.reserved_cost_usd
    raise V2EvidenceAnalystFailure("existing model attempt has unprovable cost exposure")


def _provider_usage(
    provider: LLMProvider,
    request: LLMRequest,
    output: BaseModel,
    invocation_record: object,
) -> ModelUsageMetadata | None:
    usage_for = getattr(provider, "usage_for", None)
    if not callable(usage_for):
        return None
    usage = usage_for(request, output, invocation_record)
    if usage is not None and not isinstance(usage, ModelUsageMetadata):
        raise TypeError("provider usage must be ModelUsageMetadata")
    return usage


def _provider_failure_usage(provider: LLMProvider) -> ModelUsageMetadata | None:
    failure_usage_for = getattr(provider, "failure_usage_for", None)
    if not callable(failure_usage_for):
        return None
    usage = failure_usage_for()
    if usage is not None and not isinstance(usage, ModelUsageMetadata):
        raise TypeError("provider failure usage must be ModelUsageMetadata")
    return usage


def _source_artifact_key(source_id: UUID) -> str:
    return f"{V2_EVIDENCE_ANALYST_SOURCE_ARTIFACT_PREFIX}-{source_id}"


def _source_artifact_keys(source_id: UUID) -> tuple[str, ...]:
    return (
        _source_artifact_key(source_id),
        f"{V2_EVIDENCE_ANALYST_SOURCE_LEGACY_PREFIX}-{source_id}",
    )


def _read_source_result(
    db_path: str,
    run_id: UUID,
    source_id: UUID,
) -> V2EvidenceAnalystSourceResult | None:
    for artifact_key in _source_artifact_keys(source_id):
        payload = _read_artifact(db_path, run_id, artifact_key)
        if payload is None:
            continue
        result = V2EvidenceAnalystSourceResult.model_validate_json(payload)
        if result.state is V2EvidenceAnalystState.NOT_QUEUED:
            # Single-source waves must not let a placeholder reserve a future wave.
            continue
        return result
    return None


def _revision_artifact_key(source_id: UUID) -> str:
    return f"phase-9-luna-evidence-analyst-revision-{source_id}"


def _source_attempt_ids(db_path: str, run_id: UUID, source_id: UUID) -> tuple[UUID, ...]:
    return tuple(
        attempt.attempt_id
        for attempt in read_model_route_attempts(db_path, run_id)
        if attempt.output_type in _PHASE9_OUTPUT_TYPES
        and attempt.input_artifact_ids == (source_id,)
    )


def _read_artifact(db_path: str, run_id: UUID, artifact_key: str) -> str | None:
    try:
        return read_v2_artifact(db_path, run_id, artifact_key).payload_json
    except KeyError:
        return None


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase-9 timestamps must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
