"""Conservative evidence assessment after source analysis, separate from search yield."""

from __future__ import annotations

from uuid import UUID

from models import (
    V2ClaimCoverageAssessment,
    V2ClaimCoverageState,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionState,
    V2EvidenceRelationship,
    V2PostAnalysisAssessment,
)

V2_POST_ANALYSIS_ASSESSMENT_POLICY = "researchassistant-v2-post-analysis-evidence-v1"


def build_v2_post_analysis_assessment(
    *,
    admission_result: V2EvidenceAdmissionBatchResult,
    coverage: tuple[V2ClaimCoverageAssessment, ...],
    unresolved_gap_count: int,
) -> V2PostAnalysisAssessment:
    """Reassess admitted evidence without altering strategy decisions or evidence text.

    Call after the admission chain has been validated. Counts describe observations,
    not independence, causal strength, coverage closure or proof of a universal claim.
    """
    run_id = admission_result.run_id
    analyst = admission_result.analyst_result
    if analyst.run_id != run_id or analyst.input.run_id != run_id:
        raise ValueError("post-analysis inputs must belong to the same run")
    by_id = {source.source_id: source for source in analyst.source_results}
    if len(by_id) != len(analyst.source_results):
        raise ValueError("post-analysis Analyst source IDs must be unique")
    admitted_ids: list[UUID] = []
    relationships: list[V2EvidenceRelationship] = []
    source_ids = tuple(source.source_id for source in admission_result.source_results)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("post-analysis admission source IDs must be unique")
    for source in admission_result.source_results:
        if source.run_id != run_id:
            raise ValueError("post-analysis source must belong to the same run")
        record = source.evidence_record
        if record is None:
            continue
        if source.state is not V2EvidenceAdmissionState.ANALYZER_ADMITTED:
            raise ValueError("post-analysis record requires an admitted source")
        if record.run_id != run_id:
            raise ValueError("post-analysis record must belong to the same run")
        assessed = by_id.get(source.source_id)
        if assessed is None or assessed.assessment is None:
            raise ValueError("post-analysis admitted source requires its Analyst assessment")
        if assessed.run_id != run_id or assessed.direction is not source.direction:
            raise ValueError("post-analysis Analyst source identity must match admission")
        if record.claim_fit != assessed.assessment.claim_fit:
            raise ValueError("post-analysis admitted Claim Fit must match assessment")
        admitted_ids.append(source.source_id)
        relationships.append(assessed.assessment.relationship_to_claim)
    support = relationships.count(V2EvidenceRelationship.SUPPORTS)
    challenge = relationships.count(V2EvidenceRelationship.CHALLENGES)
    qualifies = relationships.count(V2EvidenceRelationship.QUALIFIES)
    unrelated = relationships.count(V2EvidenceRelationship.UNRELATED)
    partial = sum(item.coverage_state is V2ClaimCoverageState.PARTIAL for item in coverage)
    unavailable = sum(item.coverage_state is V2ClaimCoverageState.UNAVAILABLE for item in coverage)
    unadmitted = len(source_ids) - len(admitted_ids)
    limitations: list[str] = []
    if support == 0:
        limitations.append(
            "No admitted finding was classified as supporting the claim. "
            "This does not establish that the claim is false."
        )
    if qualifies and support == 0 and challenge == 0 and unrelated == 0:
        limitations.append("The admitted findings provide qualifications, not proof of the claim.")
    if unadmitted:
        limitations.append(
            f"{unadmitted} selected source(s) produced no admitted evidence; "
            "selection is not evidence sufficiency."
        )
    if unresolved_gap_count or any(
        item.coverage_state
        not in {V2ClaimCoverageState.COVERED, V2ClaimCoverageState.NOT_APPLICABLE}
        for item in coverage
    ):
        limitations.append(
            "Research coverage remains limited. The earlier decision to stop searching "
            "does not resolve incomplete coverage."
        )
    if not coverage:
        limitations.append("No claim-coverage assessment was recorded; completeness is unknown.")
    directions = analyst.input.directions
    if not directions.support_enabled or not directions.challenge_enabled:
        limitations.append(
            "A research direction was disabled; the claim was not examined both ways."
        )
    if unrelated:
        limitations.append("Historical unrelated items do not provide evidence for this claim.")
    return V2PostAnalysisAssessment(
        run_id=run_id,
        admitted_source_ids=tuple(admitted_ids),
        supporting_count=support,
        challenging_count=challenge,
        qualifying_count=qualifies,
        unrelated_count=unrelated,
        unadmitted_source_count=unadmitted,
        partial_coverage_count=partial,
        unavailable_coverage_count=unavailable,
        unresolved_gap_count=unresolved_gap_count,
        claim_support_observed=support > 0,
        limitations=tuple(limitations),
    )
