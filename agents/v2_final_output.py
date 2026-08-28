"""V2 synthesis, disclosure assembly, and closed final-release validation."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from agents.renderer import APPROVED_CONNECTIVE_TEMPLATES, validate_final_release
from agents.v2_adaptive_search import V2AdaptiveContinuationResult, V2AdaptiveStopCode
from models import (
    Placement,
    ResearchDirection,
    Stance,
    StrictModel,
    SynthesisOutput,
    V2AdmissionMethod,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionState,
    V2FinalResearchOutput,
    V2ReleaseValidation,
    V2ResearchStoppingDisclosure,
    V2ResearchStoppingReason,
    V2ResultSource,
    V2ResultSourceStatus,
    V2ReviewerLedgerBatchResult,
    V2SourceSelectionGap,
    V2SynthesizerInput,
    V2SynthesizerLedgerItem,
    V2SynthesizerRecommendationMetadata,
    V2UnresolvedMaterialGap,
    ValidationError,
    ValidationErrorCode,
)
from providers.llm import (
    V2_LLM_ROUTING,
    LLMProvider,
    LLMRequest,
    LLMStage,
    ModelAlias,
    invoke_llm,
    load_prompt,
    render_stage_prompt,
)
from providers.v2_routing import V2RoutingConfig
from research_governor import V2RoundThreeReasonCode
from store import insert_v2_artifact, read_v2_artifact

V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY = "phase-11-final-research-output"
V2_FINAL_OUTPUT_ARTIFACT_KEY = "phase-13-final-research-output-analyzer-admission"
V2_FINAL_OUTPUT_POLICY_IDENTITY = "researchassistant-v2-phase-13-final-output-analyzer-admission-v1"
V2_FINAL_VALIDATOR_CONFIG_VERSION = "researchassistant-v2-phase-13-release-validator-v1"

V2EvidenceInputResult = V2EvidenceAdmissionBatchResult | V2ReviewerLedgerBatchResult


def _choose_evidence_result(
    admission_result: V2EvidenceAdmissionBatchResult | None,
    reviewer_result: V2ReviewerLedgerBatchResult | None,
) -> V2EvidenceInputResult:
    if admission_result is not None and reviewer_result is not None:
        raise ValueError(
            "v2 final output accepts either fresh admission or historical Reviewer data"
        )
    result = admission_result or reviewer_result
    if result is None:
        raise ValueError("v2 final output requires an evidence admission result")
    return result


def _source_record(source: object) -> object | None:
    record = getattr(source, "evidence_record", None)
    if record is not None:
        return record
    return getattr(source, "ledger_record", None)


class V2FinalOutputRunResult(StrictModel):
    """Restart-safe final-output invocation result."""

    final_output: V2FinalResearchOutput
    resumed: bool = False


def run_v2_final_research_output(
    *,
    db_path: str | Path,
    admission_result: V2EvidenceAdmissionBatchResult | None = None,
    reviewer_result: V2ReviewerLedgerBatchResult | None = None,
    continuation: V2AdaptiveContinuationResult,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime] | None = None,
) -> V2FinalOutputRunResult:
    """Create and persist the v2 result using MiMo only for Ledger-item arrangement."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    evidence_result = _choose_evidence_result(admission_result, reviewer_result)
    _validate_chain(evidence_result, continuation)
    stored = None
    output_keys = (V2_FINAL_OUTPUT_ARTIFACT_KEY,)
    if isinstance(evidence_result, V2ReviewerLedgerBatchResult):
        output_keys = (V2_FINAL_OUTPUT_ARTIFACT_KEY, V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY)
    for output_key in output_keys:
        try:
            stored = read_v2_artifact(path, evidence_result.run_id, output_key)
        except KeyError:
            continue
        break
    if stored is not None:
        output = V2FinalResearchOutput.model_validate_json(stored.payload_json)
        _validate_persisted_output(output, evidence_result, continuation)
        return V2FinalOutputRunResult(final_output=output, resumed=True)

    synthesis_input = build_v2_synthesizer_input(evidence_result, continuation)
    route = routing_config.preflight().for_stage(LLMStage.SYNTHESIZER)
    if route.logical_alias is not ModelAlias.MIMO_V25_PRO:
        raise ValueError("fresh v2 synthesis must use MiMo-v2.5-Pro")
    if V2_LLM_ROUTING.for_stage(LLMStage.SYNTHESIZER).primary is not route.logical_alias:
        raise ValueError("configured Synthesizer route does not match the v2 routing policy")
    prompt = load_prompt(LLMStage.SYNTHESIZER)
    request = LLMRequest(
        run_id=evidence_result.run_id,
        stage=LLMStage.SYNTHESIZER,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, synthesis_input, SynthesisOutput),
        input_artifact=synthesis_input,
        input_artifact_ids=tuple(
            item.ledger_claim_id for item in synthesis_input.approved_ledger_items
        ),
        requested_output_type=SynthesisOutput,
        model_alias=route.logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.SYNTHESIZER).generation,
    )
    invocation = invoke_llm(llm_provider, request, clock=now)
    synthesis = invocation.output_artifact
    if not isinstance(synthesis, SynthesisOutput):
        raise TypeError("v2 Synthesizer returned an unexpected typed artifact")
    if synthesis.run_id != evidence_result.run_id:
        raise ValueError("v2 Synthesizer output run_id does not match the run")
    output = build_v2_final_research_output(
        admission_result=evidence_result,
        continuation=continuation,
        synthesis=synthesis,
        created_at=_aware(now()),
    )
    insert_v2_artifact(path, V2_FINAL_OUTPUT_ARTIFACT_KEY, output, output.created_at)
    return V2FinalOutputRunResult(final_output=output)


def build_v2_synthesizer_input(
    evidence_result: V2EvidenceInputResult,
    continuation: V2AdaptiveContinuationResult,
) -> V2SynthesizerInput:
    """Project only validated Ledger evidence and typed research disclosures to MiMo."""
    _validate_chain(evidence_result, continuation)
    selection = evidence_result.analyst_result.input.queue_result
    statements = tuple(
        _ledger_item(source.source_id, source.direction, _source_record(source))
        for source in evidence_result.source_results
        if _source_record(source) is not None
    )
    if not statements:
        raise ValueError("v2 synthesis requires at least one analyzer-admitted evidence record")
    unresolved = _unresolved_gaps(selection.input.gap_history, evidence_result)
    source_by_id = {item.source_id: item for item in selection.input.survivors}
    metadata = tuple(
        V2SynthesizerRecommendationMetadata(
            source_id=status.source_id,
            direction=source_by_id[status.source_id].direction,
            recommended=status.recommended,
            queued_for_deep_analysis=status.queued_for_deep_analysis,
            budget_prevented_reason=status.budget_prevented_reason,
        )
        for status in selection.source_statuses
    )
    stopping = _stopping_disclosure(continuation)
    return V2SynthesizerInput(
        run_id=evidence_result.run_id,
        exact_claim=selection.input.exact_claim,
        directions=selection.input.directions,
        approved_ledger_items=statements,
        qualifications=tuple(
            item for item in statements if item.placement is Placement.QUALIFIED_ONLY
        ),
        unresolved_material_gaps=unresolved,
        stopping_reason=stopping.explanation,
        recommendation_metadata=metadata,
    )


def build_v2_final_research_output(
    *,
    admission_result: V2EvidenceInputResult | None = None,
    reviewer_result: V2ReviewerLedgerBatchResult | None = None,
    continuation: V2AdaptiveContinuationResult,
    synthesis: SynthesisOutput,
    created_at: datetime,
) -> V2FinalResearchOutput:
    """Build the complete deterministic disclosure envelope around a typed synthesis."""
    evidence_result = _choose_evidence_result(admission_result, reviewer_result)
    _validate_chain(evidence_result, continuation)
    selection = evidence_result.analyst_result.input.queue_result
    records = tuple(
        _source_record(source)
        for source in evidence_result.source_results
        if _source_record(source) is not None
    )
    stopping = _stopping_disclosure(continuation)
    all_sources = _result_sources(evidence_result)
    recommended_ids = selection.recommended_source_ids
    by_id = {item.source_id: item for item in all_sources}
    output_without_validation = {
        "run_id": evidence_result.run_id,
        "exact_claim": selection.input.exact_claim,
        "directions": selection.input.directions,
        "synthesis": synthesis,
        "recommended_source_ids": recommended_ids,
        "recommended_sources": tuple(by_id[source_id] for source_id in recommended_ids),
        "all_surviving_sources": all_sources,
        "unresolved_material_gaps": tuple(
            V2UnresolvedMaterialGap(
                gap_id=gap.gap_id,
                direction=gap.direction,
                missing_evidence=gap.missing_evidence,
                assessed_after_round=gap.assessed_after_round,
            )
            for gap in _unresolved_gaps(selection.input.gap_history, evidence_result)
        ),
        "stopping": stopping,
        "created_at": _aware(created_at),
    }
    validation = validate_v2_final_release(
        synthesis=synthesis,
        ledger_records=records,
        admission_result=evidence_result,
        continuation=continuation,
        output_fields=output_without_validation,
        validated_at=_aware(created_at),
    )
    return V2FinalResearchOutput(**output_without_validation, release_validation=validation)


def validate_v2_final_release(
    *,
    synthesis: SynthesisOutput,
    ledger_records: tuple[object, ...],
    admission_result: V2EvidenceInputResult | None = None,
    reviewer_result: V2ReviewerLedgerBatchResult | None = None,
    continuation: V2AdaptiveContinuationResult,
    output_fields: Mapping[str, object],
    validated_at: datetime,
) -> V2ReleaseValidation:
    """Fail closed unless the evidence brief and every v2 disclosure are internally exact."""
    evidence_result = _choose_evidence_result(admission_result, reviewer_result)
    selection = evidence_result.analyst_result.input.queue_result
    evidence = validate_final_release(
        synthesis,
        ledger_records,
        authoritative_claim=selection.input.exact_claim,
        validated_at=validated_at,
    )
    errors = list(evidence.errors)
    errors.extend(_v2_integrity_errors(synthesis, evidence_result, continuation, output_fields))
    if errors:
        return V2ReleaseValidation(
            evidence_validation=evidence,
            valid=False,
            errors=tuple(errors),
            validator_config_version=V2_FINAL_VALIDATOR_CONFIG_VERSION,
            validated_at=validated_at,
        )
    rendered = _render_v2_components(
        synthesis=synthesis,
        directions=selection.input.directions,
        exact_claim=selection.input.exact_claim,
        recommended_sources=output_fields["recommended_sources"],
        all_surviving_sources=output_fields["all_surviving_sources"],
        unresolved_material_gaps=output_fields["unresolved_material_gaps"],
        stopping=output_fields["stopping"],
    )
    return V2ReleaseValidation(
        evidence_validation=evidence,
        valid=True,
        errors=(),
        validator_config_version=V2_FINAL_VALIDATOR_CONFIG_VERSION,
        validated_at=validated_at,
        rendered_output_hash=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    )


def render_v2_final_output(output: V2FinalResearchOutput) -> str:
    """Render v2 disclosures mechanically after successful final validation only."""
    if not output.release_validation.valid:
        raise ValueError("invalid v2 final output cannot be rendered")
    return _render_v2_components(
        synthesis=output.synthesis,
        directions=output.directions,
        exact_claim=output.exact_claim,
        recommended_sources=output.recommended_sources,
        all_surviving_sources=output.all_surviving_sources,
        unresolved_material_gaps=output.unresolved_material_gaps,
        stopping=output.stopping,
    )


def _v2_integrity_errors(
    synthesis: SynthesisOutput,
    evidence_result: V2EvidenceInputResult,
    continuation: V2AdaptiveContinuationResult,
    output_fields: Mapping[str, object],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    selection = evidence_result.analyst_result.input.queue_result
    source_by_id = {item.source_id: item for item in selection.input.survivors}
    status_by_id = {item.source_id: item for item in selection.source_statuses}
    admission_by_id = {item.source_id: item for item in evidence_result.source_results}
    source_by_claim = {
        record.ledger_claim_id: source
        for source in evidence_result.source_results
        if (record := _source_record(source)) is not None
    }
    for section in synthesis.sections:
        for item in section.items:
            source = source_by_claim.get(item.ledger_claim_id)
            if source is None:
                errors.append(
                    _error("synthesis.ledger_claim_id", "Synthesis claim is not v2 Ledger-backed.")
                )
                continue
            if not selection.input.directions.permits(source.direction):
                errors.append(
                    _error("synthesis.direction", "Disabled-direction evidence cannot appear.")
                )
            if item.stance is not _stance_for_direction(source.direction):
                errors.append(
                    _error(
                        "synthesis.stance", "Synthesis stance disagrees with v2 Ledger direction."
                    )
                )
    all_sources = output_fields.get("all_surviving_sources")
    if not isinstance(all_sources, tuple):
        return [*errors, _error("all_surviving_sources", "Final output source list is malformed.")]
    listed_ids = tuple(item.source_id for item in all_sources if isinstance(item, V2ResultSource))
    if set(listed_ids) != set(source_by_id) or len(listed_ids) != len(source_by_id):
        errors.append(
            _error(
                "all_surviving_sources", "Final output must expose every persisted survivor once."
            )
        )
    for source in all_sources:
        if not isinstance(source, V2ResultSource):
            errors.append(_error("all_surviving_sources", "Final output source item is malformed."))
            continue
        expected = source_by_id.get(source.source_id)
        status = status_by_id.get(source.source_id)
        admission = admission_by_id.get(source.source_id)
        if expected is None or status is None or admission is None:
            errors.append(_error("all_surviving_sources.source_id", "Source ID does not exist."))
            continue
        if source.direction is not expected.direction:
            errors.append(
                _error(
                    "all_surviving_sources.direction", "Source direction does not match survivor."
                )
            )
        if source.recommended is not status.recommended:
            errors.append(
                _error(
                    "all_surviving_sources.recommended",
                    "Recommendation state does not match selection.",
                )
            )
        record = _source_record(admission)
        expected_claims = (record.ledger_claim_id,) if record is not None else ()
        if source.ledger_claim_ids != expected_claims:
            errors.append(
                _error(
                    "all_surviving_sources.ledger_claim_ids",
                    "Source Ledger IDs do not match admission.",
                )
            )
    recommended_ids = output_fields.get("recommended_source_ids")
    if recommended_ids != selection.recommended_source_ids:
        errors.append(
            _error("recommended_source_ids", "Recommendation IDs do not match source selection.")
        )
    stopping = output_fields.get("stopping")
    if stopping != _stopping_disclosure(continuation):
        errors.append(_error("stopping", "Stopping disclosure does not match continuation state."))
    return errors


def _result_sources(evidence_result: V2EvidenceInputResult) -> tuple[V2ResultSource, ...]:
    selection = evidence_result.analyst_result.input.queue_result
    status_by_id = {item.source_id: item for item in selection.source_statuses}
    admission_by_id = {item.source_id: item for item in evidence_result.source_results}
    sources: list[V2ResultSource] = []
    for survivor in selection.input.survivors:
        status = status_by_id[survivor.source_id]
        admission = admission_by_id[survivor.source_id]
        record = _source_record(admission)
        claims = (record.ledger_claim_id,) if record is not None else ()
        display_status = _source_status(
            status.recommended,
            status.budget_prevented_reason,
            claims,
            analyzer_admitted=isinstance(evidence_result, V2EvidenceAdmissionBatchResult),
            admission_state=admission.state,
        )
        sources.append(
            V2ResultSource(
                source_id=survivor.source_id,
                direction=survivor.direction,
                source_url=survivor.source_url,
                title=survivor.title,
                source_type=survivor.source_type,
                publication_date=survivor.publication_date,
                discovery_providers=survivor.discovery_providers,
                discovery_round=survivor.research_round,
                recommended=status.recommended,
                recommendation_rank=status.recommendation_rank,
                queue_rank=status.queue_rank,
                status=display_status,
                ledger_claim_ids=claims,
                budget_prevented_reason=status.budget_prevented_reason,
            )
        )
    return tuple(sources)


def _source_status(
    recommended: bool,
    budget_reason: object,
    claim_ids: tuple[UUID, ...],
    *,
    analyzer_admitted: bool,
    admission_state: object,
) -> V2ResultSourceStatus:
    if analyzer_admitted:
        if admission_state is V2EvidenceAdmissionState.ANALYST_REJECTED:
            return (
                V2ResultSourceStatus.RECOMMENDED_ANALYZER_REJECTED
                if recommended
                else V2ResultSourceStatus.SURVIVING_ANALYZER_REJECTED
            )
        if admission_state is V2EvidenceAdmissionState.ANALYST_FAILED:
            return (
                V2ResultSourceStatus.RECOMMENDED_ANALYZER_FAILED
                if recommended
                else V2ResultSourceStatus.SURVIVING_ANALYZER_FAILED
            )
    if budget_reason is not None:
        return V2ResultSourceStatus.BUDGET_PREVENTED_ANALYSIS
    if recommended and claim_ids:
        return (
            V2ResultSourceStatus.RECOMMENDED_ANALYZER_ADMITTED
            if analyzer_admitted
            else V2ResultSourceStatus.RECOMMENDED_ANALYZED
        )
    if recommended:
        return V2ResultSourceStatus.RECOMMENDED_NO_LEDGER_EVIDENCE
    if claim_ids:
        return (
            V2ResultSourceStatus.SURVIVING_ANALYZER_ADMITTED
            if analyzer_admitted
            else V2ResultSourceStatus.SURVIVING_ANALYZED
        )
    return V2ResultSourceStatus.SURVIVING_NOT_DEEPLY_ANALYZED


def _ledger_item(
    source_id: UUID,
    direction: ResearchDirection,
    record: object,
) -> V2SynthesizerLedgerItem:
    if record is None:
        raise ValueError("admitted v2 source is missing a Ledger record")
    return V2SynthesizerLedgerItem(
        source_id=source_id,
        direction=direction,
        ledger_claim_id=record.ledger_claim_id,
        reviewer_approval_id=getattr(record, "reviewer_approval_id", None),
        admission_method=getattr(record, "admission_method", V2AdmissionMethod.REVIEWER_APPROVED),
        stance=record.stance,
        placement=record.placement,
        entailment=record.entailment,
        approved_factual_statement=record.approved_factual_statement,
    )


def _unresolved_gaps(
    gaps: tuple[V2SourceSelectionGap, ...], evidence_result: V2EvidenceInputResult
) -> tuple[V2SourceSelectionGap, ...]:
    covered = {
        gap_id
        for source in evidence_result.source_results
        if _source_record(source) is not None
        for gap_id in source.provenance.relevant_gap_ids
    }
    return tuple(gap for gap in gaps if gap.gap_id not in covered)


def _stopping_disclosure(
    continuation: V2AdaptiveContinuationResult,
) -> V2ResearchStoppingDisclosure:
    decision = continuation.stopping_decision
    direct_reasons = {
        V2AdaptiveStopCode.ROUND_ONE_COMPLETE: V2ResearchStoppingReason.SUFFICIENT_SOURCE_POOL,
        V2AdaptiveStopCode.ROUND_TWO_COMPLETE: V2ResearchStoppingReason.SUFFICIENT_SOURCE_POOL,
        V2AdaptiveStopCode.ROUND_THREE_COMPLETE: V2ResearchStoppingReason.HARD_ROUND_LIMIT,
        V2AdaptiveStopCode.NO_ELIGIBLE_PROVIDER: (
            V2ResearchStoppingReason.PROVIDER_ELIGIBILITY_EXHAUSTED
        ),
        V2AdaptiveStopCode.NO_NEW_QUERY: V2ResearchStoppingReason.NO_USEFUL_NEW_DIRECTION,
        V2AdaptiveStopCode.BUDGET: V2ResearchStoppingReason.BUDGET,
        V2AdaptiveStopCode.GAP_ANALYSIS_DEGRADED: (
            V2ResearchStoppingReason.DEGRADED_GAP_SEARCH_AGENT
        ),
        V2AdaptiveStopCode.CANCELLED: V2ResearchStoppingReason.HARD_ROUND_LIMIT,
        V2AdaptiveStopCode.PROVIDER_FAILURE: (
            V2ResearchStoppingReason.PROVIDER_ELIGIBILITY_EXHAUSTED
        ),
        V2AdaptiveStopCode.INVALID_SEARCH_AGENT_PLAN: (
            V2ResearchStoppingReason.INVALID_SEARCH_AGENT_PLAN
        ),
    }
    reason = (
        _governor_stopping_reason(continuation)
        if decision.stop_code is V2AdaptiveStopCode.GOVERNOR_REJECTED
        else direct_reasons[decision.stop_code]
    )
    return V2ResearchStoppingDisclosure(
        reason=reason,
        explanation=decision.stopping_reason,
        completed_rounds=decision.completed_rounds,
    )


def _governor_stopping_reason(
    continuation: V2AdaptiveContinuationResult,
) -> V2ResearchStoppingReason:
    governor = continuation.governor_decision
    if governor is None:
        raise ValueError("Governor-rejected continuation must retain its Governor decision")
    if governor.reason_code is V2RoundThreeReasonCode.INVALID_SEARCH_AGENT_PLAN:
        return V2ResearchStoppingReason.INVALID_SEARCH_AGENT_PLAN
    if governor.reason_code is V2RoundThreeReasonCode.DUPLICATE_HEAVY:
        return V2ResearchStoppingReason.DUPLICATE_HEAVY
    if governor.reason_code in {
        V2RoundThreeReasonCode.NO_NEW_DIRECTION,
        V2RoundThreeReasonCode.NO_NEW_QUERY,
        V2RoundThreeReasonCode.NO_MATERIAL_GAP,
        V2RoundThreeReasonCode.LUNA_STOP,
    }:
        return V2ResearchStoppingReason.NO_USEFUL_NEW_DIRECTION
    if governor.reason_code in {
        V2RoundThreeReasonCode.PROTECTED_BUDGET,
        V2RoundThreeReasonCode.INSUFFICIENT_RESERVATION,
    }:
        return V2ResearchStoppingReason.BUDGET
    if governor.reason_code in {
        V2RoundThreeReasonCode.NO_ELIGIBLE_PROVIDER,
        V2RoundThreeReasonCode.PROVIDER_CEILING,
        V2RoundThreeReasonCode.TERMINAL_FAILURE,
    }:
        return V2ResearchStoppingReason.PROVIDER_ELIGIBILITY_EXHAUSTED
    return V2ResearchStoppingReason.HARD_ROUND_LIMIT


def _validate_chain(
    evidence_result: V2EvidenceInputResult,
    continuation: V2AdaptiveContinuationResult,
) -> None:
    if continuation.run_id != evidence_result.run_id:
        raise ValueError("v2 final output artifacts must match the same run")
    selection = evidence_result.analyst_result.input.queue_result
    if selection.input.run_id != evidence_result.run_id:
        raise ValueError("v2 final output selection must match the same run")
    if continuation.merged_survivors.run_id != evidence_result.run_id:
        raise ValueError("v2 final output survivor pool must match the same run")


def _validate_persisted_output(
    output: V2FinalResearchOutput,
    evidence_result: V2EvidenceInputResult,
    continuation: V2AdaptiveContinuationResult,
) -> None:
    expected = build_v2_synthesizer_input(evidence_result, continuation)
    if output.run_id != expected.run_id or output.exact_claim != expected.exact_claim:
        raise ValueError("persisted v2 final output does not match the current inputs")
    if output.directions != expected.directions:
        raise ValueError("persisted v2 final output directions do not match the current inputs")


def _render_v2_components(
    *,
    synthesis: SynthesisOutput,
    directions: object,
    exact_claim: str,
    recommended_sources: object,
    all_surviving_sources: object,
    unresolved_material_gaps: object,
    stopping: object,
) -> str:
    if not isinstance(recommended_sources, tuple) or not isinstance(all_surviving_sources, tuple):
        raise ValueError("v2 final output source lists must be tuples")
    if not isinstance(unresolved_material_gaps, tuple) or not isinstance(
        stopping, V2ResearchStoppingDisclosure
    ):
        raise ValueError("v2 final output disclosures are malformed")
    support = getattr(directions, "support_enabled", None)
    challenge = getattr(directions, "challenge_enabled", None)
    if not isinstance(support, bool) or not isinstance(challenge, bool):
        raise ValueError("v2 final output directions are malformed")
    lines = ["# Research Brief", "", f"Claim under review: {exact_claim}", ""]
    lines.append(f"Research direction: {_direction_label(support, challenge)}")
    if any(
        item.admission_method is V2AdmissionMethod.ANALYZER_ADMITTED
        for section in synthesis.sections
        for item in section.items
    ):
        lines.append("Evidence admission: Analyzer-admitted; not independently reviewed.")
    for section in synthesis.sections:
        if section.section_type.value == "supporting":
            heading = "Supporting Evidence"
        elif section.section_type.value == "opposing":
            heading = "Challenging Evidence"
        else:
            heading = "Evidence Qualifications"
        lines.extend(("", f"## {heading}"))
        for item in section.items:
            template = APPROVED_CONNECTIVE_TEMPLATES[item.connective_template_id]
            lines.append(f"- {template.text} {item.approved_factual_statement}")
    lines.extend(("", "## Recommended Sources"))
    lines.extend(_source_lines(recommended_sources))
    lines.extend(("", "## All Surviving Sources"))
    lines.extend(_source_lines(all_surviving_sources))
    lines.extend(("", "## Remaining Gaps"))
    for gap in unresolved_material_gaps:
        if not isinstance(gap, V2UnresolvedMaterialGap):
            raise ValueError("v2 final output gap is malformed")
        lines.append(f"- {gap.direction.value}: {gap.missing_evidence}")
    if not unresolved_material_gaps:
        lines.append("- No unresolved material gaps were recorded.")
    lines.extend(("", "## Research Stopping Reason"))
    lines.append(f"- {stopping.reason.value}: {stopping.explanation}")
    return "\n".join(lines)


def _source_lines(sources: tuple[V2ResultSource, ...]) -> list[str]:
    if not sources:
        return ["- None."]
    return [
        f"- {source.status.value}: {source.title or source.source_url} ({source.source_url})"
        for source in sources
    ]


def _direction_label(support: bool, challenge: bool) -> str:
    if support and challenge:
        return "supporting and challenging evidence"
    if support:
        return "supporting evidence only"
    return "challenging evidence only"


def _stance_for_direction(direction: ResearchDirection) -> Stance:
    return Stance.SUPPORTING if direction is ResearchDirection.SUPPORT else Stance.OPPOSING


def _error(location: str, message: str) -> ValidationError:
    return ValidationError(
        code=ValidationErrorCode.LEDGER_MISMATCH,
        location=location,
        message=message,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 final output timestamps must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
