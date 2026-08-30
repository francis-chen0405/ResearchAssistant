"""Bounded Luna Gap Analysis over persisted Probe data; it never executes searches."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict

from models import (
    ResearchDirection,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2GapAcquisitionFailure,
    V2GapAnalysisAttempt,
    V2GapAnalysisInput,
    V2GapAnalysisModelOutput,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2GapAttemptedQuery,
    V2GapBudgetState,
    V2GapDuplicatePattern,
    V2GapIdentityCollisionError,
    V2GapProbePassage,
    V2GapReservation,
    V2GapSourceFamily,
    V2GapSurvivingSourceMetadata,
    V2InitialPlannerOutput,
    V2MaterialGap,
    validate_v2_gap_identity_continuity,
)
from providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationError,
    LLMInvocationRecord,
    LLMProvider,
    LLMRequest,
    LLMStage,
    invoke_llm,
    is_non_retryable_provider_error,
    load_prompt,
    render_stage_prompt,
)
from providers.pricing import conservative_token_estimate
from providers.v2_routing import V2RoutingConfig
from store import insert_v2_artifact, read_v2_artifact

V2_GAP_ANALYSIS_ARTIFACT_KEY = "phase-6-gap-analysis"
V2_GAP_ANALYSIS_MAX_ATTEMPTS = 2
_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")
_TERM_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "against",
        "analysis",
        "claim",
        "evidence",
        "from",
        "have",
        "into",
        "more",
        "source",
        "study",
        "that",
        "their",
        "these",
        "this",
        "with",
    }
)


class V2GapAnalysisRunResult(V2GapAnalysisOutput):
    """Persisted output plus the invocation records used for successful process work."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    invocations: tuple[LLMInvocationRecord, ...] = ()
    resumed: bool = False


def build_v2_gap_analysis_input(
    *,
    planner_output: V2InitialPlannerOutput,
    discovery_output: V2DiscoveryScoutOutput,
    acquisition_output: V2AcquisitionProbeOutput,
    remaining_budget: V2GapBudgetState,
    previous_gaps: tuple[V2MaterialGap, ...] = (),
) -> V2GapAnalysisInput:
    """Project Phase-5 survivor state into a compact, bounded strategy handoff."""
    if acquisition_output.run_id != planner_output.run_id:
        raise ValueError("Gap Analysis inputs must share a run_id")
    if acquisition_output.directions != planner_output.directions:
        raise ValueError("Gap Analysis inputs must share enabled research directions")
    items = {item.item_id: item for item in discovery_output.items}
    clusters = {cluster.cluster_id: cluster for cluster in discovery_output.clusters}
    source_by_snapshot = {
        source.snapshot.snapshot_id: source for source in acquisition_output.acquisitions
    }
    survivor_sources: list[V2GapSurvivingSourceMetadata] = []
    passage_rows: list[V2GapProbePassage] = []
    for survivor in acquisition_output.survivors:
        source = source_by_snapshot[survivor.snapshot_id]
        cluster = clusters[survivor.cluster_id]
        representative = min(
            (items[item_id] for item_id in cluster.item_ids),
            key=lambda item: item.provider_rank,
        )
        family_id = f"cluster:{survivor.cluster_id}"
        survivor_sources.append(
            V2GapSurvivingSourceMetadata(
                source_cluster_id=survivor.cluster_id,
                direction=survivor.direction,
                snapshot_id=survivor.snapshot_id,
                snapshot_sha256=survivor.snapshot_sha256,
                source_url=source.snapshot.source_url,
                title=representative.title,
                source_family_id=family_id,
            )
        )
        probe = next(
            probe
            for probe in acquisition_output.probes
            if probe.snapshot_id == survivor.snapshot_id
        )
        passage_by_id = {passage.passage_id: passage for passage in probe.passages}
        for passage_id in survivor.passage_ids:
            passage = passage_by_id[passage_id]
            text = passage.text[:1200]
            passage_rows.append(
                V2GapProbePassage(
                    passage_id=passage.passage_id,
                    source_cluster_id=survivor.cluster_id,
                    direction=survivor.direction,
                    text=text,
                    truncated_for_gap_analysis=len(text) != len(passage.text),
                )
            )
    survivor_sources.sort(key=lambda item: (item.direction.value, str(item.source_cluster_id)))
    passage_rows = passage_rows[:40]
    families = tuple(
        V2GapSourceFamily(
            family_id=f"cluster:{source.source_cluster_id}",
            direction=_cluster_direction(source.source_cluster_id, discovery_output),
            source_cluster_ids=(source.source_cluster_id,),
            discovery_providers=tuple(
                dict.fromkeys(
                    reference.provider
                    for reference in clusters[source.source_cluster_id].provider_references
                )
            ),
        )
        for source in survivor_sources
    )
    duplicate_patterns = tuple(
        V2GapDuplicatePattern(
            source_cluster_id=cluster.cluster_id,
            direction=_cluster_direction(cluster.cluster_id, discovery_output),
            duplicate_discovery_count=len(cluster.item_ids),
            pattern="conservatively clustered same-source discovery records",
        )
        for cluster in discovery_output.clusters
        if len(cluster.item_ids) > 1
    )[:25]
    failures = tuple(
        V2GapAcquisitionFailure(
            source_cluster_id=attempt.cluster_id,
            direction=_cluster_direction(attempt.cluster_id, discovery_output),
            provider=attempt.provider,
            failure_code=attempt.failure_code or "unspecified_acquisition_failure",
        )
        for attempt in acquisition_output.attempts
        if not attempt.succeeded
    )[:50]
    return V2GapAnalysisInput(
        run_id=planner_output.run_id,
        exact_claim=planner_output.raw_claim,
        directions=planner_output.directions,
        attempted_queries=tuple(
            V2GapAttemptedQuery(
                query_id=query.query_id,
                direction=query.direction,
                provider=query.provider,
                strategy=query.strategy,
                query_text=query.query_text,
            )
            for query in planner_output.searches
        ),
        surviving_sources=tuple(survivor_sources),
        probe_passages=tuple(passage_rows),
        source_families=families,
        discovered_terms=_discovered_terms(discovery_output),
        duplicate_patterns=duplicate_patterns,
        acquisition_failures=failures,
        previous_gaps=previous_gaps,
        remaining_budget=remaining_budget,
    )


def run_v2_gap_analysis(
    *,
    db_path: str | Path,
    gap_input: V2GapAnalysisInput,
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    artifact_key: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2GapAnalysisRunResult:
    """Run at most two Luna attempts, persist a completed or degraded strategy state."""
    now = clock or _utc_now
    completed_at = _aware_now(now)
    path = str(Path(db_path).resolve())
    resolved_artifact_key = artifact_key or (
        V2_GAP_ANALYSIS_ARTIFACT_KEY
        if gap_input.completed_round == 1
        else f"phase-7-gap-analysis-after-round-{gap_input.completed_round}"
    )
    try:
        stored = read_v2_artifact(path, gap_input.run_id, resolved_artifact_key)
    except KeyError:
        stored = None
    if stored is not None:
        output = V2GapAnalysisOutput.model_validate_json(stored.payload_json)
        if output.input != gap_input:
            raise ValueError("persisted Gap Analysis input does not match this Round-1 state")
        return V2GapAnalysisRunResult(**output.model_dump(), resumed=True)

    route = routing_config.preflight().for_stage(LLMStage.GAP_ANALYSIS)
    if route.logical_alias is not V2_LLM_ROUTING.for_stage(LLMStage.GAP_ANALYSIS).primary:
        raise ValueError("Gap Analysis route must use GPT-5.6 Luna High")
    prompt = load_prompt(LLMStage.GAP_ANALYSIS)
    request = LLMRequest(
        run_id=gap_input.run_id,
        stage=LLMStage.GAP_ANALYSIS,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, gap_input, V2GapAnalysisModelOutput),
        input_artifact=gap_input,
        input_artifact_ids=(gap_input.run_id,),
        requested_output_type=V2GapAnalysisModelOutput,
        model_alias=route.logical_alias,
        generation=V2_LLM_ROUTING.for_stage(LLMStage.GAP_ANALYSIS).generation,
    )
    attempts: list[V2GapAnalysisAttempt] = []
    invocations: list[LLMInvocationRecord] = []
    for attempt_number in range(1, V2_GAP_ANALYSIS_MAX_ATTEMPTS + 1):
        reservation = routing_config.preflight().reserve(
            LLMStage.GAP_ANALYSIS, conservative_token_estimate(request.rendered_prompt)
        )
        recorded_reservation = V2GapReservation(
            input_tokens=reservation.input_tokens,
            output_tokens=reservation.output_tokens,
            reserved_tokens=reservation.reserved_tokens,
            reserved_cost_usd=reservation.reserved_cost_usd,
        )
        if not _budget_can_reserve(gap_input.remaining_budget, attempts, recorded_reservation):
            break
        try:
            invocation = invoke_llm(llm_provider, request, clock=now)
            invocations.append(invocation.record)
            response = invocation.output_artifact
            if not isinstance(response, V2GapAnalysisModelOutput):
                raise TypeError("Gap Analysis returned an unexpected typed artifact")
            result = V2GapAnalysisResult(
                **response.model_dump(),
                run_id=gap_input.run_id,
                directions=gap_input.directions,
                analyzed_at=completed_at,
            )
            validate_v2_gap_identity_continuity(
                gap_input.previous_gaps,
                result.material_gaps,
            )
            output = V2GapAnalysisOutput(
                run_id=gap_input.run_id,
                input=gap_input,
                state=V2GapAnalysisState.COMPLETED,
                result=result,
                attempts=tuple(
                    (
                        *attempts,
                        V2GapAnalysisAttempt(
                            attempt_number=attempt_number,
                            reservation=recorded_reservation,
                            succeeded=True,
                        ),
                    )
                ),
                stop_adaptive_continuation=not result.continue_research,
                completed_at=completed_at,
            )
            insert_v2_artifact(path, resolved_artifact_key, output, completed_at)
            return V2GapAnalysisRunResult(**output.model_dump(), invocations=tuple(invocations))
        except V2GapIdentityCollisionError:
            raise
        except (LLMInvocationError, TypeError, ValueError) as exc:
            attempts.append(
                V2GapAnalysisAttempt(
                    attempt_number=attempt_number,
                    reservation=recorded_reservation,
                    succeeded=False,
                    failure=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
            if isinstance(exc, LLMInvocationError) and is_non_retryable_provider_error(exc):
                raise
    output = V2GapAnalysisOutput(
        run_id=gap_input.run_id,
        input=gap_input,
        state=V2GapAnalysisState.DEGRADED,
        attempts=tuple(attempts),
        stop_adaptive_continuation=True,
        completed_at=completed_at,
    )
    insert_v2_artifact(path, resolved_artifact_key, output, completed_at)
    return V2GapAnalysisRunResult(**output.model_dump(), invocations=tuple(invocations))


def _budget_can_reserve(
    budget: V2GapBudgetState,
    attempts: list[V2GapAnalysisAttempt],
    reservation: V2GapReservation,
) -> bool:
    if budget.model_calls_remaining <= len(attempts):
        return False
    used_tokens = sum(item.reservation.reserved_tokens for item in attempts)
    if (
        budget.tokens_remaining is not None
        and used_tokens + reservation.reserved_tokens > budget.tokens_remaining
    ):
        return False
    used_cost = sum((item.reservation.reserved_cost_usd for item in attempts), Decimal("0"))
    return (
        budget.cost_remaining_usd is None
        or used_cost + reservation.reserved_cost_usd <= budget.cost_remaining_usd
    )


def _cluster_direction(
    cluster_id: UUID, discovery_output: V2DiscoveryScoutOutput
) -> ResearchDirection:
    cluster = next(item for item in discovery_output.clusters if item.cluster_id == cluster_id)
    items = {item.item_id: item for item in discovery_output.items}
    return min(
        (items[item_id] for item_id in cluster.item_ids),
        key=lambda item: item.provider_rank,
    ).direction


def _discovered_terms(discovery_output: V2DiscoveryScoutOutput) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for item in discovery_output.items:
        source_text = " ".join(part for part in (item.title, item.abstract, item.snippet) if part)
        for token in _TERM_RE.findall(source_text):
            normalized = token.casefold()
            if normalized in _TERM_STOPWORDS or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(token)
            if len(terms) == 40:
                return tuple(terms)
    return tuple(terms)


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 Gap Analysis clock must return a timezone-aware datetime")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
