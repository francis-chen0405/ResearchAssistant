"""Pure projections of persisted evidence, provenance and research diagnostics."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from researchassistant.agents.v2_post_analysis import (
    V2_POST_ANALYSIS_ASSESSMENT_POLICY,
    build_v2_post_analysis_assessment,
)
from researchassistant.api.inspection_contracts import (
    V2EvidenceDisplay,
    V2EvidenceDisplayItem,
    V2ResearchStatusDisplay,
    V2SharedWebsiteGroup,
    V2SourceBudgetOutcomeDisplay,
    V2SourceTitleDisplay,
)
from researchassistant.contracts.models import (
    CandidateQuoteBlock,
    LedgerRecord,
    SourceSnapshot,
    V2AdmissionMethod,
    V2ClaimCoverageState,
    V2DeepAnalysisBackfillResult,
    V2DeepAnalysisSourceExecution,
    V2DeepAnalysisSourceExecutionState,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionRecord,
    V2EvidenceAnalystSourceResult,
    V2FinalResearchOutput,
    V2GapAnalysisOutput,
    V2ReviewerLedgerBatchResult,
    V2RoundFourGovernorDecision,
)
from researchassistant.evidence.evidence_core import (
    parse_extracted_quote_block,
    validate_snapshot_integrity,
)
from researchassistant.evidence.source_display import display_source_title
from researchassistant.evidence.study_lineage import build_study_lineage_notices


def _build_shared_website_groups(
    items: tuple[V2EvidenceDisplayItem, ...],
) -> tuple[V2SharedWebsiteGroup, ...]:
    by_host: dict[str, list[UUID]] = {}
    for item in items:
        parsed = urlsplit(item.source_url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            continue
        host = parsed.hostname.lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        by_host.setdefault(host, []).append(item.source_id)
    return tuple(
        V2SharedWebsiteGroup(
            host=host,
            source_ids=tuple(source_ids),
            explanation=(
                f"These {len(source_ids)} admitted pages share the {host} website. "
                "A shared website alone does not establish independent corroboration. "
                "This does not show they are duplicates."
            ),
        )
        for host, source_ids in sorted(by_host.items())
        if len(source_ids) > 1
    )


def _source_context_notice(
    *, source_type: str | None, exact_claim: str, title: str | None, statement: str
) -> str | None:
    context = " ".join((exact_claim, title or "", statement)).casefold()
    legal_topic = any(
        re.search(rf"\b{term}\b", context)
        for term in ("law", "legal", "illegal", "gdpr", "statute")
    )
    broad_state_assertion = "all 50 states" in statement.casefold() or "all fifty states" in (
        statement.casefold()
    )
    legal_web_context = source_type == "general_web" and legal_topic
    untyped_legal_context = source_type is None and legal_topic
    if not (legal_web_context or untyped_legal_context or broad_state_assertion):
        return None
    notice = (
        "Legal scope has not been independently verified; check jurisdiction, dates and "
        "exceptions against primary sources."
    )
    if broad_state_assertion:
        notice += (
            " The all-50-states statement has not been independently verified; check "
            "whether its scope and conditions apply in each jurisdiction."
        )
    return notice


def _build_v2_evidence_display(
    output: V2FinalResearchOutput,
    evidence_result: V2EvidenceAdmissionBatchResult | V2ReviewerLedgerBatchResult,
    *,
    gap_analysis: V2GapAnalysisOutput | None = None,
    governor_decision: V2RoundFourGovernorDecision | None = None,
    backfill: V2DeepAnalysisBackfillResult | None = None,
) -> V2EvidenceDisplay:
    """Project persisted v2 evidence into a read-only result-page view."""
    _validate_evidence_display_consistency(output, evidence_result)
    sources = {source.source_id: source for source in output.all_surviving_sources}
    analyst_results: dict[UUID, V2EvidenceAnalystSourceResult] = {
        source.source_id: source for source in evidence_result.analyst_result.source_results
    }
    selections = {
        status.source_id: status
        for status in evidence_result.analyst_result.input.queue_result.source_statuses
    }
    items: list[V2EvidenceDisplayItem] = []
    queued_candidates = {
        item.source_id: item for item in evidence_result.analyst_result.input.queued_candidates
    }
    for admission in evidence_result.source_results:
        record = getattr(admission, "evidence_record", None) or getattr(
            admission, "ledger_record", None
        )
        if record is None:
            continue
        analyst = analyst_results[admission.source_id]
        if analyst.candidate is None or analyst.assessment is None:
            raise ValueError("admitted source is missing its Analyst candidate or assessment")
        queued = queued_candidates.get(admission.source_id)
        if queued is None:
            raise ValueError("admitted source is missing its queued candidate and snapshot")
        _validate_evidence_display_provenance(
            run_id=output.run_id,
            candidate=analyst.candidate,
            queued_candidate=queued.candidate,
            snapshot=queued.snapshot,
            record=record,
        )
        source = sources[admission.source_id]
        selection = selections[admission.source_id]
        limitations = (
            *analyst.assessment.material_limitations,
            *analyst.assessment.inferential_boundaries,
        )
        items.append(
            V2EvidenceDisplayItem(
                source_id=source.source_id,
                ledger_claim_id=record.ledger_claim_id,
                title=source.title,
                source_url=record.source_url,
                source_type=source.source_type,
                claim_fit=record.claim_fit,
                source_context_notice=_source_context_notice(
                    source_type=source.source_type,
                    exact_claim=output.exact_claim,
                    title=source.title,
                    statement=record.approved_factual_statement,
                ),
                source_family=admission.provenance.source_family_id,
                direction=source.direction.value,
                relationship_to_claim=analyst.assessment.relationship_to_claim,
                approved_factual_statement=record.approved_factual_statement,
                recommendation_status=(
                    "Recommended for deeper analysis"
                    if selection.recommended
                    else "Survived source evaluation"
                ),
                selection_rationale=selection.selection_rationale,
                gap_ids=selection.gap_ids,
                evidence_summary=analyst.assessment.reasoning,
                supporting_proposition=analyst.assessment.narrowest_supported_proposition,
                quote_passage=analyst.candidate.extracted_quote_block,
                limitations=limitations,
                validation_status=(
                    "analyzer_admitted_not_independently_reviewed"
                    if getattr(admission, "evidence_record", None) is not None
                    else admission.state.value
                ),
            )
        )
    candidates = evidence_result.analyst_result.input.queue_result.input.survivors
    research_status = _build_research_status_display(
        output, gap_analysis=gap_analysis, governor_decision=governor_decision
    )
    source_budget_outcomes = _build_source_budget_outcomes(output, backfill)
    post_analysis_assessment = (
        build_v2_post_analysis_assessment(
            admission_result=evidence_result,
            coverage=output.claim_coverage_map,
            unresolved_gap_count=len(output.unresolved_material_gaps),
            policy_identity=(
                output.post_analysis_assessment.policy_identity
                if output.post_analysis_assessment is not None
                else V2_POST_ANALYSIS_ASSESSMENT_POLICY
            ),
        )
        if isinstance(evidence_result, V2EvidenceAdmissionBatchResult)
        else None
    )
    return V2EvidenceDisplay(
        run_id=output.run_id,
        items=tuple(items),
        source_titles=tuple(
            V2SourceTitleDisplay(
                source_id=source.source_id,
                display_title=display_source_title(
                    title=source.title,
                    source_url=source.source_url,
                ),
                captured_title=source.title,
            )
            for source in output.all_surviving_sources
        ),
        study_lineage=build_study_lineage_notices(candidates),
        source_budget_outcomes=source_budget_outcomes,
        shared_website_groups=_build_shared_website_groups(tuple(items)),
        research_status=research_status,
        post_analysis_assessment=post_analysis_assessment,
    )


def _validate_evidence_display_consistency(
    output: V2FinalResearchOutput,
    evidence_result: V2EvidenceAdmissionBatchResult | V2ReviewerLedgerBatchResult,
) -> None:
    """Join saved artifacts without rerunning or changing historical release policy."""
    analyst_input = evidence_result.analyst_result.input
    if evidence_result.run_id != output.run_id:
        raise ValueError("supplemental evidence must match the final-output run")
    if analyst_input.exact_claim != output.exact_claim:
        raise ValueError("supplemental evidence exact claim differs from the released claim")
    if analyst_input.directions != output.directions:
        raise ValueError("supplemental evidence directions differ from the final output")
    sources = {source.source_id: source for source in output.all_surviving_sources}
    if len(sources) != len(output.all_surviving_sources) or set(sources) != {
        source.source_id for source in evidence_result.source_results
    }:
        raise ValueError("supplemental evidence sources differ from the final output")
    records: dict[UUID, LedgerRecord | V2EvidenceAdmissionRecord] = {}
    for admission in evidence_result.source_results:
        source = sources[admission.source_id]
        if admission.run_id != output.run_id or admission.direction is not source.direction:
            raise ValueError("supplemental evidence source ownership differs from the final output")
        record = getattr(admission, "evidence_record", None) or getattr(
            admission, "ledger_record", None
        )
        expected_ids = (record.ledger_claim_id,) if record is not None else ()
        if source.ledger_claim_ids != expected_ids:
            raise ValueError("supplemental evidence Ledger IDs differ from the final output")
        if record is not None:
            if record.ledger_claim_id in records:
                raise ValueError("supplemental evidence Ledger IDs must be unique")
            if source.source_url != record.source_url:
                raise ValueError("supplemental evidence source URL differs from the final output")
            records[record.ledger_claim_id] = record
    for section in output.synthesis.sections:
        for item in section.items:
            record = records.get(item.ledger_claim_id)
            if record is None:
                raise ValueError("released statement is missing its supplemental evidence record")
            for field in (
                "approved_factual_statement",
                "stance",
                "placement",
                "entailment",
                "reviewer_approval_id",
                "admission_method",
            ):
                recorded = getattr(
                    record,
                    field,
                    V2AdmissionMethod.REVIEWER_APPROVED if field == "admission_method" else None,
                )
                if getattr(item, field) != recorded:
                    raise ValueError(
                        f"supplemental evidence {field} differs from the released statement"
                    )


def _build_source_budget_outcomes(
    output: V2FinalResearchOutput,
    backfill: V2DeepAnalysisBackfillResult | None,
) -> tuple[V2SourceBudgetOutcomeDisplay, ...]:
    if backfill is None:
        return ()
    if backfill.run_id != output.run_id:
        raise ValueError("source execution backfill must match the result run")
    source_ids = {source.source_id for source in output.all_surviving_sources}
    results: list[V2SourceBudgetOutcomeDisplay] = []
    for execution in backfill.source_executions:
        if execution.source_id not in source_ids:
            raise ValueError("source execution backfill contains an unknown result source")
        outcome = _source_budget_outcome(execution)
        if outcome is not None:
            results.append(
                V2SourceBudgetOutcomeDisplay(source_id=execution.source_id, outcome=outcome)
            )
    return tuple(results)


def _source_budget_outcome(
    execution: V2DeepAnalysisSourceExecution,
) -> Literal["source_budget_blocked", "token_cap_blocked", "physical_call_cap_blocked"] | None:
    if execution.state is V2DeepAnalysisSourceExecutionState.SOURCE_BUDGET_BLOCKED:
        return "source_budget_blocked"
    reason = execution.failure_reason
    if (
        execution.state is not V2DeepAnalysisSourceExecutionState.EXTRACTION_FAILED
        or reason is None
    ):
        return None
    source = re.escape(str(execution.source_id))
    prefix = r"(?:LLMProviderExecutionError: LLM provider failed: )?"
    if re.fullmatch(rf"{prefix}source {source} token cap cannot cover this call", reason):
        return "token_cap_blocked"
    if re.fullmatch(rf"{prefix}source {source} physical-call cap is exhausted", reason):
        return "physical_call_cap_blocked"
    return None


def _validate_evidence_display_provenance(
    *,
    run_id: UUID,
    candidate: CandidateQuoteBlock,
    queued_candidate: CandidateQuoteBlock,
    snapshot: SourceSnapshot,
    record: LedgerRecord | V2EvidenceAdmissionRecord,
) -> None:
    """Bind displayed quote text to its queued snapshot and admitted Ledger record."""
    if candidate != queued_candidate:
        raise ValueError("admitted quote candidate differs from the queued candidate")
    if candidate.run_id != run_id or record.run_id != run_id or snapshot.run_id != run_id:
        raise ValueError("admitted quote provenance must match the result run")
    # approved_claim_text historically stores the exact extracted quotation,
    # rather than the research question; retain that recorded meaning.
    if record.approved_claim_text != candidate.extracted_quote_block:
        raise ValueError("admitted approved claim text differs from its exact quote candidate")
    if record.stance is not candidate.stance:
        raise ValueError("admitted evidence stance differs from its quote candidate")
    if (
        candidate.quote_block_id != record.quote_block_id
        or candidate.source_url != record.source_url
        or candidate.snapshot_id != record.snapshot_id
        or candidate.snapshot_sha256 != record.snapshot_sha256
        or candidate.retrieval_attempt_id != record.retrieval_attempt_id
        or tuple(candidate.segment_offsets) != record.segment_offsets
    ):
        raise ValueError("admitted quote provenance does not match its Ledger record")
    if (
        candidate.source_url != snapshot.source_url
        or candidate.snapshot_id != snapshot.snapshot_id
        or candidate.snapshot_sha256 != snapshot.snapshot_sha256
        or candidate.retrieval_attempt_id != snapshot.retrieval_attempt_id
    ):
        raise ValueError("admitted quote provenance does not match its queued snapshot")
    validate_snapshot_integrity(snapshot)
    parsed_quote = parse_extracted_quote_block(candidate.extracted_quote_block)
    if len(parsed_quote.segments) != len(candidate.segment_offsets):
        raise ValueError("admitted quote segments do not match their snapshot offsets")
    for segment, offset in zip(parsed_quote.segments, candidate.segment_offsets, strict=True):
        if snapshot.normalized_text[offset.start_char : offset.end_char] != segment:
            raise ValueError("admitted quote text does not match its queued snapshot")


def _build_research_status_display(
    output: V2FinalResearchOutput,
    *,
    gap_analysis: V2GapAnalysisOutput | None,
    governor_decision: V2RoundFourGovernorDecision | None,
) -> V2ResearchStatusDisplay:
    if gap_analysis is not None:
        if gap_analysis.run_id != output.run_id or gap_analysis.input.run_id != output.run_id:
            raise ValueError("latest gap analysis must match the final-output run")
        if gap_analysis.input.completed_round != 3:
            raise ValueError("latest gap analysis must describe completed Round 3")
        if gap_analysis.input.directions != output.directions:
            raise ValueError("latest gap analysis directions must match the final output")
    if governor_decision is not None:
        if governor_decision.run_id != output.run_id:
            raise ValueError("latest Governor decision must match the final-output run")
        if gap_analysis is None:
            raise ValueError("latest Governor decision requires its post-Round-3 gap analysis")
        if governor_decision.authorized and output.stopping.completed_rounds < 4:
            raise ValueError("authorized Round 4 cannot precede its completed research round")

    coverage = output.claim_coverage_map
    decision = governor_decision
    if decision is None and output.gap_reconciliation is not None:
        decision = output.gap_reconciliation.round_four_governor_decision
    if decision is not None and decision.authorized:
        # Authorization describes a planned round, not the outcome of completed Round 4.
        decision = None
    if output.stopping.completed_rounds >= 4:
        actionable_gap_count = len(output.unresolved_material_gaps)
    elif gap_analysis is not None and gap_analysis.result is not None:
        actionable_gap_count = len(gap_analysis.result.material_gaps)
    else:
        actionable_gap_count = len(output.unresolved_material_gaps)
    reason_code = (
        decision.reason_code.value if decision is not None else output.stopping.reason.value
    )
    explanation = decision.explanation if decision is not None else output.stopping.explanation
    if (
        decision is not None
        and decision.reason_code.value == "no_material_gaps"
        and gap_analysis is not None
        and gap_analysis.result is not None
        and not gap_analysis.result.continue_research
    ):
        reason_code = "no_productive_search"
        explanation = gap_analysis.result.stop_reason or (
            "The latest gap review did not identify an actionable search direction."
        )
        explanation += " Research coverage may remain partial or unavailable."
    return V2ResearchStatusDisplay(
        reason_code=reason_code,
        explanation=explanation,
        actionable_gap_count=actionable_gap_count,
        partial_coverage_count=sum(
            item.coverage_state is V2ClaimCoverageState.PARTIAL for item in coverage
        ),
        unavailable_coverage_count=sum(
            item.coverage_state is V2ClaimCoverageState.UNAVAILABLE for item in coverage
        ),
        source=(
            "persisted_governor"
            if decision is not None and governor_decision is not None
            else "final_output"
        ),
    )
