"""One validated read snapshot per result or evidence request, closed before projection."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from researchassistant.agents.post_analysis_round import POST_ANALYSIS_COMBINED_KEY
from researchassistant.agents.v2_deep_analysis import (
    V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
)
from researchassistant.agents.v2_evidence_admission import (
    V2_EVIDENCE_ADMISSION_ARTIFACT_KEY,
)
from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
)
from researchassistant.agents.v2_reviewer_ledger import V2_REVIEWER_LEDGER_ARTIFACT_KEY
from researchassistant.agents.v2_round_four import (
    V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
)
from researchassistant.api.application_services.evidence_projection import (
    _build_v2_evidence_display,
)
from researchassistant.api.inspection_contracts import V2EvidenceDisplay
from researchassistant.contracts.models import (
    SourceSnapshot,
    V2DeepAnalysisBackfillResult,
    V2DiscoveryScoutOutput,
    V2EvidenceAdmissionBatchResult,
    V2FinalResearchOutput,
    V2GapAnalysisOutput,
    V2PersistedArtifact,
    V2ReviewerLedgerBatchResult,
    V2RoundFourGovernorDecision,
)
from researchassistant.evidence.released_output import validate_saved_output
from researchassistant.storage.store import (
    DatabaseReader,
    open_read_only_store,
    read_run,
    read_v2_artifact,
)


def read_result(db_path: str | Path, run_id: UUID) -> V2FinalResearchOutput:
    with open_read_only_store(db_path) as store:
        manifest = read_run(store.connection, run_id)
        try:
            artifact = read_v2_artifact(store.connection, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY)
        except KeyError:
            try:
                artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY
                )
            except KeyError:
                artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY
                )
    if artifact.artifact_type != V2FinalResearchOutput.__name__:
        raise ValueError("v2 final-output artifact has an unexpected type")
    return validate_saved_output(
        V2FinalResearchOutput.model_validate_json(artifact.payload_json),
        run_id,
        manifest,
    )


def read_evidence(
    db_path: str | Path, run_id: UUID, *, source: DatabaseReader | None = None
) -> V2EvidenceDisplay:
    context = (
        open_read_only_store(db_path)
        if source is None
        else nullcontext(SimpleNamespace(connection=source))
    )
    with context as store:
        manifest = read_run(store.connection, run_id)
        from researchassistant.api.live_progress import (
            _read_v2_ceilings,
            _read_v2_usage_summary,
        )

        read_source = store.connection
        ceilings = _read_v2_ceilings(read_source, run_id)
        usage = _read_v2_usage_summary(read_source, run_id, terminal=True)
        from researchassistant.providers.v2_budget import read_v2_physical_call_audit

        audit = read_v2_physical_call_audit(read_source, run_id)
        from researchassistant.evidence.report_review import REPORT_REVIEW_KEY

        try:
            review_artifact = read_v2_artifact(store.connection, run_id, REPORT_REVIEW_KEY)
        except KeyError:
            review_artifact = None
        review_snapshots = {}
        if review_artifact is not None:
            from researchassistant.evidence.report_review import V2ReportStudyReview
            from researchassistant.storage.store import read_snapshot

            if review_artifact.artifact_type != "V2ReportStudyReview":
                raise ValueError("study review has an unexpected artifact type")
            saved_review = V2ReportStudyReview.model_validate_json(review_artifact.payload_json)
            review_snapshots = {
                publication.authority.snapshot_id: read_snapshot(
                    store.connection, publication.authority.snapshot_id
                )
                for publication in saved_review.publications
            }
        try:
            final_artifact = read_v2_artifact(
                store.connection, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY
            )
        except KeyError:
            try:
                final_artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY
                )
            except KeyError:
                final_artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY
                )
        try:
            evidence_artifact = read_v2_artifact(
                store.connection, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
            )
            evidence_type = V2EvidenceAdmissionBatchResult
            try:
                combined_artifact = read_v2_artifact(
                    store.connection, run_id, POST_ANALYSIS_COMBINED_KEY
                )
            except KeyError:
                combined_artifact = None
        except KeyError:
            evidence_artifact = read_v2_artifact(
                store.connection, run_id, V2_REVIEWER_LEDGER_ARTIFACT_KEY
            )
            evidence_type = V2ReviewerLedgerBatchResult
            combined_artifact = None
        try:
            gap_artifact = read_v2_artifact(
                store.connection, run_id, V2_POST13_GAP_AFTER_ROUND_THREE_KEY
            )
        except KeyError:
            gap_artifact = None
        try:
            governor_artifact = read_v2_artifact(
                store.connection, run_id, V2_POST13_ROUND_FOUR_GOVERNOR_KEY
            )
        except KeyError:
            governor_artifact = None
        discovery_artifacts = []
        for key in (
            "phase-4-discovery-scout",
            "phase-7-round-2-discovery-scout",
            "phase-7-round-3-discovery-scout",
            "post-phase-13-round-4-discovery-scout-v1",
        ):
            try:
                discovery_artifacts.append(read_v2_artifact(store.connection, run_id, key))
            except KeyError:
                pass
        try:
            backfill_artifact = read_v2_artifact(
                store.connection, run_id, V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY
            )
        except KeyError:
            backfill_artifact = None
    if final_artifact.artifact_type != V2FinalResearchOutput.__name__:
        raise ValueError("v2 final-output artifact has an unexpected type")
    output = validate_saved_output(
        V2FinalResearchOutput.model_validate_json(final_artifact.payload_json),
        run_id,
        manifest,
    )
    evidence_result = evidence_type.model_validate_json(evidence_artifact.payload_json)
    if combined_artifact is not None:
        if combined_artifact.artifact_type != V2EvidenceAdmissionBatchResult.__name__:
            raise ValueError("combined evidence artifact has an unexpected type")
        combined = V2EvidenceAdmissionBatchResult.model_validate_json(
            combined_artifact.payload_json
        )
        original = evidence_result
        if not isinstance(original, V2EvidenceAdmissionBatchResult) or (
            combined.run_id != original.run_id
            or combined.source_results[: len(original.source_results)] != original.source_results
            or combined.analyst_result.source_results[: len(original.analyst_result.source_results)]
            != original.analyst_result.source_results
            or combined.analyst_result.input.queued_candidates[
                : len(original.analyst_result.input.queued_candidates)
            ]
            != original.analyst_result.input.queued_candidates
        ):
            raise ValueError("combined evidence claim or quote differs from original admission")
        evidence_result = combined
    gap_analysis = (
        V2GapAnalysisOutput.model_validate_json(gap_artifact.payload_json)
        if gap_artifact is not None
        else None
    )
    governor_decision = (
        V2RoundFourGovernorDecision.model_validate_json(governor_artifact.payload_json)
        if governor_artifact is not None and gap_analysis is not None
        else None
    )
    backfill = (
        V2DeepAnalysisBackfillResult.model_validate_json(backfill_artifact.payload_json)
        if backfill_artifact is not None
        else None
    )
    if any(artifact.artifact_type != "V2DiscoveryScoutOutput" for artifact in discovery_artifacts):
        raise ValueError("discovery artifact has an unexpected type")
    display = _build_v2_evidence_display(
        output,
        evidence_result,
        gap_analysis=gap_analysis,
        governor_decision=governor_decision,
        backfill=backfill,
        discovery_outputs=tuple(
            V2DiscoveryScoutOutput.model_validate_json(artifact.payload_json)
            for artifact in discovery_artifacts
        ),
    )

    context = [
        "Configured limits describe allowances; "
        "they do not by themselves identify the cause of a stop."
    ]
    if ceilings is not None:
        context.append(
            f"Configured limits: USD {ceilings.max_total_cost_usd}; "
            f"{ceilings.max_total_tokens} tokens; {ceilings.max_physical_calls} calls."
        )
    else:
        context.append("Configured monetary, token and call limits were not recorded.")
    if usage.physical_calls_used:
        context.append(
            f"Reported spend subtotal: USD {usage.known_cost_subtotal_usd}; "
            f"reported tokens subtotal: {usage.known_token_subtotal}; "
            f"recorded calls: {usage.physical_calls_used}."
        )
        pending_cost = max(0, usage.conservative_reserved_cost_usd - usage.known_cost_subtotal_usd)
        pending_tokens = max(0, usage.conservative_reserved_tokens - usage.known_token_subtotal)
        context.append(
            f"Pending reservations: USD {pending_cost}; {pending_tokens} tokens. "
            "Reservations are not reported spend."
        )
        if not usage.cost_usage_complete or not usage.token_usage_complete:
            context.append("Usage reports are incomplete; known subtotals are not final totals.")
    else:
        context.append(
            "Reported spend, pending reservations and token usage are unknown "
            "because no call-usage records were available."
        )
    by_source = {}
    for start in audit.starts:
        if start.source_id is not None:
            by_source.setdefault(start.source_id, []).append(start)
    for source_id, starts in by_source.items():
        source_title = (
            next(
                (
                    item.title
                    for item in output.all_surviving_sources
                    if item.source_id == source_id
                ),
                None,
            )
            or "Source"
        )
        caps = {(start.source_token_cap, start.source_physical_call_cap) for start in starts}
        if not all(
            {"source_token_cap", "source_physical_call_cap"} <= start.model_fields_set
            for start in starts
        ):
            context.append(f"{source_title}: source-specific allowance amounts were not recorded.")
        elif len(caps) == 1:
            tokens, calls = next(iter(caps))
            context.append(
                f"{source_title}: recorded source allowance {tokens} tokens and "
                f"{calls} calls; {len(starts)} calls dispatched. "
                "An allowance alone does not identify the stop cause."
            )
        else:
            context.append(
                f"{source_title}: source allowances changed between calls; "
                "see the technical call history for the individual limits."
            )
    display = display.model_copy(update={"budget_context": tuple(context)})
    if review_artifact is not None:
        display = _apply_saved_review(display, review_artifact, review_snapshots)
    from researchassistant.evidence.brief_export import _v2_reading_aid
    from researchassistant.evidence.report_review import build_publication_opening

    display = build_publication_opening(display)
    return display.model_copy(update={"reading_aid_markdown": _v2_reading_aid(output, display)})


def _apply_saved_review(
    display: V2EvidenceDisplay,
    artifact: V2PersistedArtifact,
    review_snapshots: dict[UUID, SourceSnapshot],
) -> V2EvidenceDisplay:
    from researchassistant.evidence.report_review import V2ReportStudyReview, apply_review

    if artifact.artifact_type != "V2ReportStudyReview":
        raise ValueError("study review has an unexpected artifact type")
    review = V2ReportStudyReview.model_validate_json(artifact.payload_json)
    for publication in review.publications:
        if review_snapshots[publication.authority.snapshot_id] != publication.authority:
            raise ValueError("review authority differs from persisted acquisition")
    return apply_review(display, review)
