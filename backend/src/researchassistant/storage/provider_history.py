"""Validated read-only inspection of historical provider runs and released artifacts.

This module never selects, initializes or invokes a research executor.
"""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from researchassistant.common.pipeline_errors import Phase9OrchestrationError
from researchassistant.contracts.artifact_keys import (
    MVP10_TARGETED_ANALYSIS_ARTIFACT,
    MVP10_TARGETED_RESEARCHERS_ARTIFACT,
    MVP11_ROUND_THREE_ANALYSIS_CHECKPOINT,
    MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
    MVP11_ROUND_TWO_ANALYSIS_CHECKPOINT,
    MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT,
    PHASE9_ANALYSIS_ARTIFACT,
    PHASE9_RESEARCHERS_ARTIFACT,
)
from researchassistant.contracts.historical import (
    HistoricalRead,
    RecordCompatibilityError,
    RecordCompatibilityResult,
)
from researchassistant.contracts.models import (
    DEFAULT_RESEARCH_CONTROLS,
    CheckpointStatus,
    OrchestrationCheckpoint,
    PlannerOutput,
    ResearchControls,
    RunManifest,
    RunStatus,
    Stage,
    StrictModel,
    SynthesisOutput,
    ValidationResult,
)
from researchassistant.contracts.provider_results import (
    AnalysisStageResult,
    ProviderPipelineResult,
    ProviderRunStatus,
    ResearcherPairResult,
    _combine_analysis_results,
    summarize_model_usage,
)
from researchassistant.evidence.renderer import render_brief
from researchassistant.storage.store import (
    DatabaseReader,
    open_read_only_store,
    read_cancellation_request,
    read_model_route_attempts,
    read_orchestration_checkpoints,
    read_planner_output,
    read_portfolio_coverage_assessment,
    read_provider_run_contract,
    read_research_governor_decision,
    read_research_round_records,
    read_research_terminal_result,
    read_run,
    read_snapshot,
    read_stage_artifact,
    read_synthesis,
    read_validation,
)

_ModelT = TypeVar("_ModelT", bound=StrictModel)


def inspect_provider_run(
    db_path: str | Path,
    run_id: UUID,
    *,
    failure_reason: str | None = None,
    source: DatabaseReader | None = None,
) -> ProviderPipelineResult:
    """Reopen and inspect a partial or terminal provider-backed run."""
    path = str(Path(db_path).resolve())
    if source is not None:
        if isinstance(source, (str, Path)):
            with open_read_only_store(source) as store:
                return _inspect_provider_run_connection(
                    store.connection, path, run_id, failure_reason=failure_reason
                )
        from researchassistant.storage.store import _read_connection

        with _read_connection(source) as reader:
            return _inspect_provider_run_connection(
                reader, path, run_id, failure_reason=failure_reason
            )
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
    compatibility_issues: list[RecordCompatibilityResult] = []
    manifest = read_run(reader, run_id)
    checkpoints = tuple(read_orchestration_checkpoints(reader, run_id))
    attempts = tuple(read_model_route_attempts(reader, run_id))
    planner = _read_optional_planner(reader, run_id)
    researchers = _read_optional_stage_result(
        reader,
        run_id,
        PHASE9_RESEARCHERS_ARTIFACT,
        ResearcherPairResult,
        historical=True,
        compatibility_issues=compatibility_issues,
    )
    researcher_rounds = tuple(item for item in (researchers,) if item is not None)
    for artifact_key in (
        MVP10_TARGETED_RESEARCHERS_ARTIFACT,
        MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT,
        MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT,
    ):
        expanded_researchers = _read_optional_stage_result(
            reader,
            run_id,
            artifact_key,
            ResearcherPairResult,
            historical=True,
            compatibility_issues=compatibility_issues,
        )
        if expanded_researchers is not None:
            researcher_rounds = (*researcher_rounds, expanded_researchers)
    analysis = _read_optional_stage_result(
        reader,
        run_id,
        PHASE9_ANALYSIS_ARTIFACT,
        AnalysisStageResult,
        historical=True,
        compatibility_issues=compatibility_issues,
    )
    for artifact_key in (
        MVP10_TARGETED_ANALYSIS_ARTIFACT,
        MVP11_ROUND_TWO_ANALYSIS_CHECKPOINT,
        MVP11_ROUND_THREE_ANALYSIS_CHECKPOINT,
    ):
        expanded_analysis = _read_optional_stage_result(
            reader,
            run_id,
            artifact_key,
            AnalysisStageResult,
            historical=True,
            compatibility_issues=compatibility_issues,
        )
        if expanded_analysis is not None:
            analysis = (
                expanded_analysis
                if analysis is None
                else _combine_analysis_results(analysis, expanded_analysis)
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
        try:
            contract = read_provider_run_contract(reader, run_id)
        except KeyError:
            contract = None
        research_mode = (
            ResearchControls.from_policy_identity(contract.policy_identity).research_mode
            if contract is not None
            else DEFAULT_RESEARCH_CONTROLS.research_mode
        )
        final_brief = render_brief(
            synthesis,
            analysis.ledger_records,
            authoritative_claim=manifest.raw_claim,
            research_mode=research_mode,
        )
        rendered_hash = validation.rendered_brief_hash
        if rendered_hash != sha256(final_brief.encode("utf-8")).hexdigest():
            legacy_brief = render_brief(
                synthesis,
                analysis.ledger_records,
                authoritative_claim=manifest.raw_claim,
            )
            if rendered_hash != sha256(legacy_brief.encode("utf-8")).hexdigest():
                from researchassistant.evidence.historical_render import (
                    render_native_historical_brief,
                )

                try:
                    legacy_brief = render_native_historical_brief(
                        synthesis,
                        analysis.ledger_records,
                        manifest.raw_claim,
                        validation,
                        contract,
                    )
                except ValueError as exc:
                    raise ValueError(
                        "persisted released brief does not match its validation hash"
                    ) from exc
            final_brief = legacy_brief

    usage_accounting = summarize_model_usage(attempts)
    retrieval_count = 0
    for researcher_round in researcher_rounds:
        for side in (researcher_round.supporting, researcher_round.opposing):
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
        compatibility_issues=tuple(compatibility_issues),
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


def _read_optional_stage_result(
    db_path: DatabaseReader,
    run_id: UUID,
    artifact_key: str,
    model_type: type[_ModelT],
    *,
    historical: bool = False,
    compatibility_issues: list[RecordCompatibilityResult] | None = None,
) -> _ModelT | None:
    try:
        artifact = read_stage_artifact(db_path, run_id, artifact_key)
    except KeyError:
        return None
    if not historical and artifact.artifact_type != model_type.__name__:
        raise Phase9OrchestrationError(
            Stage.FINAL_RENDERER_VALIDATOR,
            f"stored {artifact_key} has unexpected type {artifact.artifact_type}",
        )
    if historical:
        from researchassistant.storage.historical_decode import (
            decode_native_artifact,
            verify_historical_snapshot,
        )

        try:
            contract = read_provider_run_contract(db_path, run_id)
        except KeyError:
            contract = None
        try:
            result = decode_native_artifact(artifact, model_type, contract)
            if isinstance(result, AnalysisStageResult):
                for record in result.ledger_records:
                    if isinstance(record, HistoricalRead):
                        verify_historical_snapshot(
                            record, read_snapshot(db_path, record.snapshot_id)
                        )
            return result
        except RecordCompatibilityError as exc:
            if compatibility_issues is None:
                raise
            compatibility_issues.append(exc.result)
            return None
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
