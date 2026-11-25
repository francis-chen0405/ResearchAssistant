from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_v2_phase6_gap_analysis import _input as gap_input_fixture
from test_v2_phase8_source_selection import NOW, _budget, _candidate, _prepare_db, _routing

from researchassistant.agents import v2_deep_analysis as deep
from researchassistant.agents.pending_source_priority import (
    V2PendingSourcePriority,
    bounded_pending_order,
    freeze_pending_priority,
)
from researchassistant.agents.v2_gap_analysis import V2GapAnalysisRunResult
from researchassistant.agents.v2_source_selection import (
    V2SourceSelectionRunResult,
    calculate_v2_deep_analysis_queue,
)
from researchassistant.contracts.discovery_v2 import V2PreviewRequest, V2PreviewResult, discovery_id
from researchassistant.contracts.models import (
    ResearchDirection,
    ResearchDirections,
    SourceSnapshot,
    V2AcquiredSource,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
    V2ClaimCoverageAssessment,
    V2ClaimCoverageDimension,
    V2ClaimCoverageState,
    V2GapAnalysisOutput,
    V2GapAnalysisResult,
    V2GapAnalysisState,
    V2MaterialGap,
    V2ProbeResult,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
    V2SourceSelectionRecommendation,
    V2VerbatimQuoteSelection,
)
from researchassistant.evidence.evidence_core import build_source_snapshot
from researchassistant.providers.llm import LLMProviderCapabilities, LLMRequest
from researchassistant.providers.run_scheduler import RunScheduler, StageControl, StagePolicy
from researchassistant.providers.v2_budget import (
    BudgetedV2LLMProvider,
    V2BudgetSnapshot,
    V2CancellationRequested,
    V2RunCeilings,
    read_v2_physical_call_audit,
)
from researchassistant.storage.store import read_v2_artifact

KEY = "fixture-pending-preference-v1"
GAP_TEXT = "Measured infill replacement and repairs remain missing."


def _queue(
    *,
    count: int = 6,
    lead: int = 3,
    score: int = 80,
    source_type: str | None = "primary empirical study",
    text: str = "Measured infill replacement requires periodic maintenance.",
    both: bool = False,
    families: tuple[str, ...] | None = None,
    recommended: int = 0,
) -> tuple[V2SourceSelectionQueueResult, dict[UUID, SourceSnapshot]]:
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=both)
    candidates = []
    snapshots = {}
    for i in range(count):
        source_id = UUID(int=i + 1)
        direction = ResearchDirection.CHALLENGE if both and i % 2 else ResearchDirection.SUPPORT
        candidate = _candidate(
            source_id,
            family=families[i] if families else f"family-{i}",
            probe_score=10,
            direction=direction,
        )
        body = text if i == lead else f"Independent confirming evidence measures watering cost {i}."
        snapshot = build_source_snapshot(
            run_id=run_id,
            retrieval_attempt_id=uuid4(),
            snapshot_id=uuid4(),
            source_url=candidate.source_url,
            retrieved_at=NOW,
            normalized_text=body,
            truncated=False,
            created_at=NOW,
        )
        snapshots[source_id] = snapshot
        request = V2PreviewRequest(
            run_id=run_id,
            artifact_id=discovery_id(run_id, "V2PreviewRequest", f"req/{i}"),
            identity_key=f"req/{i}",
            exact_claim="Artificial turf requires less maintenance.",
            direction=direction,
            directions=directions,
            source_id=source_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_sha256,
            preview_identity="source-claim-preview-v2",
        )
        preview = V2PreviewResult(
            run_id=run_id,
            artifact_id=discovery_id(run_id, "V2PreviewResult", f"preview/{i}"),
            identity_key=f"preview/{i}",
            request=request,
            spans=(
                {
                    "start": 0,
                    "end": len(body),
                    "text": body,
                    "section": "results",
                    "omitted_before": False,
                    "omitted_after": False,
                },
            ),
            content_classification="full_text",
            outcome="completed",
            reason="Authored fixture",
            capture_usable=True,
            relevance_score=score if i == lead else 80,
        )
        candidates.append(
            candidate.model_copy(
                update={
                    "preview": preview,
                    "source_type": source_type if i == lead else candidate.source_type,
                }
            )
        )
    selection = V2SourceSelectionInput(
        run_id=run_id,
        exact_claim=request.exact_claim,
        directions=directions,
        survivors=tuple(candidates),
        gap_history=(),
    )
    ids = tuple(c.source_id for c in candidates)
    recommendations = tuple(
        V2SourceSelectionRecommendation(source_id=sid, rationale="Existing recommendation")
        for sid in ids[:recommended]
    )
    plan = calculate_v2_deep_analysis_queue(
        selection_input=selection,
        ordered_source_ids=ids,
        recommended_source_ids=ids[:recommended],
        recommendation_rationales=recommendations,
        routing_config=_routing(),
        budget=_budget(),
    )
    queue = V2SourceSelectionQueueResult(
        run_id=run_id,
        input=selection,
        initial_budget=_budget(),
        recommended_source_ids=ids[:recommended],
        recommendation_rationales=recommendations,
        used_fallback=False,
        selection_attempts=0,
        selection_attempt_records=(),
        priority_source_ids=ids,
        **plan.model_dump(
            exclude={
                "run_id",
                "policy_identity",
                "attempts_per_logical_operation",
                "extractor_attempts_per_source",
                "extractor_logical_calls_per_source",
                "analyst_logical_calls_per_source",
                "reviewer_logical_calls_per_source",
            }
        ),
        completed_at=NOW,
    )
    return queue, snapshots


def _gap(
    queue: V2SourceSelectionQueueResult,
    *,
    state: V2ClaimCoverageState = V2ClaimCoverageState.MISSING,
    closed: bool = False,
    missing: str = GAP_TEXT,
    round_number: int = 1,
) -> V2GapAnalysisOutput:
    dimension = V2ClaimCoverageDimension.COUNTEREVIDENCE_OR_ALTERNATIVES
    component = "Unmeasured maintenance requirements"
    gap = V2MaterialGap(
        gap_id="gap-1",
        direction=ResearchDirection.SUPPORT,
        missing_evidence=missing,
        rationale="A material cost component needs evidence.",
        claim_dimension=dimension,
        unsupported_claim_component=component,
    )
    assessment = V2ClaimCoverageAssessment(
        dimension=dimension,
        claim_component=component,
        coverage_state=state,
        evidence_summary="Authored coverage fixture",
        searchable=state is not V2ClaimCoverageState.UNAVAILABLE,
        unavailable_reason="Not measurable" if state is V2ClaimCoverageState.UNAVAILABLE else None,
    )
    result = V2GapAnalysisResult(
        run_id=queue.run_id,
        directions=queue.input.directions,
        analyzed_at=NOW,
        coverage_summary="Authored material gap",
        claim_coverage_map=(assessment,),
        material_gaps=() if closed else (gap,),
        continue_research=not closed,
        stop_reason="Covered" if closed else None,
        new_search_directions=()
        if closed
        else (
            {
                "gap_id": gap.gap_id,
                "direction": gap.direction,
                "missing_evidence": missing,
                "search_focus": "Measure maintenance requirements",
            },
        ),
        discovered_terms=(),
    )
    inputs = gap_input_fixture(queue.input.directions).model_copy(
        update={
            "run_id": queue.run_id,
            "exact_claim": queue.input.exact_claim,
            "completed_round": round_number,
        }
    )
    return V2GapAnalysisOutput(
        run_id=queue.run_id,
        input=inputs,
        state=V2GapAnalysisState.COMPLETED,
        result=result,
        attempts=(),
        stop_adaptive_continuation=closed,
        completed_at=NOW,
    )


def _freeze(
    path: str,
    queue: V2SourceSelectionQueueResult,
    gaps: tuple[V2GapAnalysisOutput, ...],
    *,
    started: bool = False,
) -> tuple[UUID, ...]:
    return freeze_pending_priority(
        path=path,
        key=KEY,
        queue=queue,
        baseline=queue.priority_source_ids,
        gap_outputs=gaps,
        already_started=started,
        now=NOW,
    )


@pytest.mark.parametrize(
    "state",
    [V2ClaimCoverageState.MISSING, V2ClaimCoverageState.PARTIAL, V2ClaimCoverageState.CONFLICTING],
)
def test_saved_gap_lead_gets_two_slots(tmp_path: Path, state: V2ClaimCoverageState) -> None:
    queue, _ = _queue()
    ids = queue.priority_source_ids
    path = _prepare_db(tmp_path, queue.run_id)
    gaps = (_gap(queue, state=state),)
    assert _freeze(path, queue, gaps) == (
        ids[0],
        ids[3],
        ids[1],
        ids[2],
        *ids[4:],
    )
    saved = V2PendingSourcePriority.model_validate_json(
        read_v2_artifact(path, queue.run_id, KEY).payload_json
    )
    assert saved.promising == (ids[3],)
    # Later audit state does not recalculate or disable a recorded decision.
    assert _freeze(path, queue, gaps, started=True) == saved.ordered


@pytest.mark.parametrize("score,kind", [(74, "primary study"), (80, "news article"), (80, None)])
def test_stronger_sources_cannot_be_displaced(
    tmp_path: Path,
    score: int,
    kind: str | None,
) -> None:
    queue, _ = _queue(score=score, source_type=kind)
    path = _prepare_db(tmp_path, queue.run_id)
    assert _freeze(path, queue, (_gap(queue),)) == queue.priority_source_ids


def test_five_point_relevance_boundary(tmp_path: Path) -> None:
    queue, _ = _queue(score=75)
    assert (
        _freeze(_prepare_db(tmp_path, queue.run_id), queue, (_gap(queue),))
        != queue.priority_source_ids
    )


@pytest.mark.parametrize(
    "mode",
    [
        "none",
        "closed",
        "covered",
        "unavailable",
        "generic",
        "query",
        "claim",
        "unknown",
        "started",
        "unlinked",
        "no_coverage",
        "ambiguous",
        "incompatible_score",
        "title_only",
        "split_phrase",
    ],
)
def test_absent_or_misleading_signals_preserve_baseline(tmp_path: Path, mode: str) -> None:
    text = {
        "generic": "This study reports research effects and evidence.",
        "query": "Repairs could be relevant but nothing specific is measured.",
        "claim": "Artificial turf is widely used for recreation.",
        "split_phrase": "Only infill. Replacement requires periodic maintenance.",
    }.get(mode, "Measured infill replacement requires periodic maintenance.")
    queue, _ = _queue(text=text)
    gap = _gap(
        queue,
        closed=mode == "closed",
        state={
            "covered": V2ClaimCoverageState.COVERED,
            "unavailable": V2ClaimCoverageState.UNAVAILABLE,
        }.get(mode, V2ClaimCoverageState.MISSING),
    )
    if mode == "unlinked":
        gap = gap.model_copy(
            update={
                "result": gap.result.model_copy(
                    update={
                        "material_gaps": (
                            gap.result.material_gaps[0].model_copy(
                                update={
                                    "claim_dimension": None,
                                    "unsupported_claim_component": None,
                                }
                            ),
                        ),
                    }
                )
            }
        )
    if mode in {"no_coverage", "ambiguous"}:
        coverage = () if mode == "no_coverage" else gap.result.claim_coverage_map * 2
        gap = gap.model_copy(
            update={
                "result": gap.result.model_copy(
                    update={
                        "claim_coverage_map": coverage,
                    }
                )
            }
        )
    if mode in {"incompatible_score", "title_only"}:
        candidates = []
        for candidate in queue.input.survivors:
            preview = candidate.preview
            if mode == "incompatible_score":
                preview = preview.model_copy(
                    update={
                        "request": preview.request.model_copy(
                            update={
                                "preview_identity": "source-claim-preview-v1",
                            }
                        )
                    }
                )
            else:
                preview = preview.model_copy(
                    update={
                        "spans": tuple(
                            span.model_copy(update={"section": "title"}) for span in preview.spans
                        )
                    }
                )
            candidates.append(candidate.model_copy(update={"preview": preview}))
        queue = queue.model_copy(
            update={
                "input": queue.input.model_copy(
                    update={
                        "survivors": tuple(candidates),
                    }
                )
            }
        )
    if mode == "claim":
        gap = _gap(queue, missing="Artificial turf evidence is missing.")
    if mode == "query":
        candidates = tuple(
            c.model_copy(
                update={
                    "search_provenance": (
                        c.search_provenance[0].model_copy(
                            update={
                                "targeted_gap_ids": ("gap-1",),
                                "query_text": GAP_TEXT,
                            }
                        ),
                    )
                }
            )
            for c in queue.input.survivors
        )
        queue = queue.model_copy(
            update={"input": queue.input.model_copy(update={"survivors": candidates})}
        )
    if mode == "unknown":
        candidates = tuple(c.model_copy(update={"preview": None}) for c in queue.input.survivors)
        queue = queue.model_copy(
            update={"input": queue.input.model_copy(update={"survivors": candidates})}
        )
    gaps = () if mode == "none" else (gap,)
    assert (
        _freeze(_prepare_db(tmp_path, queue.run_id), queue, gaps, started=mode == "started")
        == queue.priority_source_ids
    )


def test_latest_completed_assessment_wins_regardless_of_iteration(tmp_path: Path) -> None:
    queue, _ = _queue()
    older, newer = _gap(queue), _gap(queue, closed=True, round_number=2)
    path = _prepare_db(tmp_path, queue.run_id)
    assert _freeze(path, queue, (newer, older)) == queue.priority_source_ids
    assert _freeze(path, queue, (older, newer)) == queue.priority_source_ids


def test_direction_recommendation_and_family_constraints(tmp_path: Path) -> None:
    queue, _ = _queue(both=True, lead=3, recommended=4)
    ids = queue.priority_source_ids
    ordered = _freeze(_prepare_db(tmp_path, queue.run_id), queue, (_gap(queue),))
    # A challenging source addresses a supporting-lane counterevidence gap.
    assert ordered == (ids[0], ids[3], ids[2], ids[1], *ids[4:])
    candidates = {c.source_id: c for c in queue.input.survivors}
    assert [candidates[x].direction for x in ordered] == [candidates[x].direction for x in ids]
    assert set(ordered[:4]) == set(queue.recommended_source_ids)
    # An unrecommended source cannot enter recommended slots.
    other, _ = _queue(recommended=3)
    assert (
        bounded_pending_order(
            other, other.priority_source_ids, frozenset({other.priority_source_ids[3]})
        )
        == other.priority_source_ids
    )
    family, _ = _queue(families=("a", "b", "c", "a", "d", "e"))
    assert (
        bounded_pending_order(
            family, family.priority_source_ids, frozenset({family.priority_source_ids[3]})
        )
        == family.priority_source_ids
    )


def test_gap_invocation_wrapper_does_not_change_replay_identity(tmp_path: Path) -> None:
    queue, _ = _queue()
    gap = _gap(queue)
    fresh = V2GapAnalysisRunResult(**gap.model_dump(), invocations=(), resumed=False)
    resumed = V2GapAnalysisRunResult(**gap.model_dump(), invocations=(), resumed=True)
    path = _prepare_db(tmp_path, queue.run_id)
    ordered = _freeze(path, queue, (fresh,))
    assert ordered != queue.priority_source_ids
    assert _freeze(path, queue, (resumed,)) == ordered


def test_selection_wrapper_does_not_change_replay_identity(tmp_path: Path) -> None:
    queue, _ = _queue()
    gaps = (_gap(queue),)
    fresh = V2SourceSelectionRunResult(**queue.model_dump(), resumed=False)
    resumed = V2SourceSelectionRunResult(**queue.model_dump(), resumed=True)
    path = _prepare_db(tmp_path, queue.run_id)
    ordered = _freeze(path, fresh, gaps)
    saved = read_v2_artifact(path, queue.run_id, KEY)
    assert ordered != queue.priority_source_ids
    assert _freeze(path, resumed, gaps) == ordered
    assert _freeze(path, queue, gaps) == ordered
    assert read_v2_artifact(path, queue.run_id, KEY) == saved
    changed = queue.model_copy(
        update={
            "initial_budget": queue.initial_budget.model_copy(
                update={"physical_calls_used": queue.initial_budget.physical_calls_used + 1}
            )
        }
    )
    with pytest.raises(ValueError, match="saved pending priority input changed"):
        _freeze(path, changed, gaps)


def test_no_compounded_movement_and_confirmation_penalty() -> None:
    queue, _ = _queue(count=9, lead=5)
    original = queue.priority_source_ids
    promising = frozenset({original[5], original[6], original[8]})
    frozen = bounded_pending_order(queue, original, promising)
    for consumed in range(len(frozen)):
        removed = set(frozen[:consumed])
        pending_baseline = tuple(x for x in original if x not in removed)
        assert all(abs(i - pending_baseline.index(x)) <= 2 for i, x in enumerate(frozen[consumed:]))
    done: set[UUID] = set()
    all_started = []
    while len(done) < len(original):
        baseline = tuple(x for x in original if x not in done)
        ordered = bounded_pending_order(queue, baseline, promising)
        assert len(ordered) == len(set(ordered)) and set(ordered) == set(baseline)
        assert all(abs(i - baseline.index(x)) <= 2 for i, x in enumerate(ordered))
        assert ordered == bounded_pending_order(queue, baseline, promising)
        assert [x for x in ordered if x not in promising] == [
            x for x in baseline if x not in promising
        ]
        done.add(ordered[0])
        all_started.append(ordered[0])
    assert set(all_started) == set(original) and len(all_started) == len(original)


def test_incidental_candidate_iteration_does_not_change_decision() -> None:
    queue, _ = _queue()
    baseline = queue.priority_source_ids
    leads = frozenset({baseline[3]})
    reordered = queue.model_copy(
        update={
            "input": queue.input.model_copy(
                update={
                    "survivors": tuple(reversed(queue.input.survivors)),
                }
            )
        }
    )
    assert bounded_pending_order(queue, baseline, leads) == bounded_pending_order(
        reordered,
        baseline,
        leads,
    )


def test_same_time_conflicting_assessments_have_no_preference(tmp_path: Path) -> None:
    queue, _ = _queue()
    gaps = (_gap(queue), _gap(queue, closed=True))
    path = _prepare_db(tmp_path, queue.run_id)
    assert _freeze(path, queue, gaps) == queue.priority_source_ids
    assert _freeze(path, queue, tuple(reversed(gaps))) == queue.priority_source_ids


class _SnapshotProvider:
    def __init__(self, source_capacity: int) -> None:
        self.capacity = source_capacity
        self.scheduler = _serial_scheduler()

    def snapshot(self) -> V2BudgetSnapshot:
        return V2BudgetSnapshot(
            physical_calls_used=0,
            token_exposure=0,
            cost_exposure_usd=Decimal("0"),
            physical_calls_remaining=self.capacity * 3,
            tokens_remaining=self.capacity * 60_000,
            cost_remaining_usd=Decimal("100"),
        )


def _serial_scheduler() -> RunScheduler:
    scheduler = RunScheduler()
    for stage in ("extraction", "analysis"):
        scheduler.stages[stage] = StageControl(StagePolicy(1, 1, 1, None))
    return scheduler


@pytest.mark.parametrize("capacity", [1, 6])
def test_actual_scheduler_freezes_before_dispatch_and_replays_after_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capacity: int,
) -> None:
    queue, snapshots = _queue(lead=2)
    path = _prepare_db(tmp_path, queue.run_id)
    monkeypatch.setattr(deep, "snapshots_by_source", lambda _outputs: snapshots)
    # One worker makes dispatch order observable; the ordinary budget-safe prefix
    # and all source envelopes still execute through the real coordinator.
    seen: list[UUID] = []
    provider = _SnapshotProvider(capacity)
    insert = deep.insert_v2_artifact

    def interrupt(db_path: str, key: str, artifact: object, created_at: object) -> object:
        if not key.endswith("rolling-v1/dispatch-1"):
            return insert(db_path, key, artifact, created_at)
        saved = V2PendingSourcePriority.model_validate_json(
            read_v2_artifact(
                path,
                queue.run_id,
                f"{deep.V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY}-pending-gap-preference-v1",
            ).payload_json
        )
        assert saved.ordered[0] == artifact.source_id
        seen.append(artifact.source_id)
        raise V2CancellationRequested("interrupted before dispatch")

    monkeypatch.setattr(deep, "insert_v2_artifact", interrupt)
    kwargs = dict(
        db_path=path,
        queue_result=queue,
        discovery_outputs=(),
        acquisition_outputs=(),
        llm_provider=provider,
        routing_config=_routing(),
        gap_outputs=(_gap(queue),),
        clock=lambda: NOW,
    )
    with pytest.raises(V2CancellationRequested):
        deep.run_v2_deep_analysis_with_backfill(**kwargs)
    assert seen == [queue.priority_source_ids[2]]
    seen.clear()

    def failed_wave(**kwargs: object) -> deep.V2DeepAnalysisWave:
        seen.append(kwargs["source_id"])
        provider.capacity -= 1
        raise RuntimeError("authored terminal failure without model calls")

    provider.scheduler = _serial_scheduler()
    monkeypatch.setattr(deep, "insert_v2_artifact", insert)
    monkeypatch.setattr(deep, "_run_source_extraction", failed_wave)
    result = deep.run_v2_deep_analysis_with_backfill(**kwargs)
    saved = V2PendingSourcePriority.model_validate_json(
        read_v2_artifact(
            path,
            queue.run_id,
            f"{deep.V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY}-pending-gap-preference-v1",
        ).payload_json
    )
    assert seen == list(saved.ordered[:capacity])
    assert saved.ordered != saved.baseline
    assert len(seen) == len(set(seen))
    assert result.final_execution_order[:capacity] == saved.ordered[:capacity]
    seen.clear()
    assert deep.run_v2_deep_analysis_with_backfill(**kwargs) == result
    assert seen == []


class _InvalidQuoteProvider:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> V2VerbatimQuoteSelection:
        self.requests.append(request)
        return V2VerbatimQuoteSelection(
            selected_sentence_ranges=({"start_sentence": 99, "end_sentence": 99},),
        )


def test_promoted_physical_attempts_are_not_repeated_on_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, snapshots = _queue()
    path = _prepare_db(tmp_path, queue.run_id)
    acquisition = V2AcquisitionProbeOutput(
        run_id=queue.run_id,
        directions=queue.input.directions,
        acquisitions=tuple(
            V2AcquiredSource(
                cluster_id=sid,
                direction=ResearchDirection.SUPPORT,
                snapshot=snapshot,
                provider=V2AcquisitionProvider.WIGOLO,
            )
            for sid, snapshot in snapshots.items()
        ),
        attempts=(),
        probes=tuple(
            V2ProbeResult(
                cluster_id=sid,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot.snapshot_sha256,
                succeeded=True,
            )
            for sid, snapshot in snapshots.items()
        ),
        survivors=(),
        completed_at=NOW,
    )
    model = _InvalidQuoteProvider()
    provider = BudgetedV2LLMProvider(
        db_path=path,
        run_id=queue.run_id,
        provider=model,
        routing_config=_routing(),
        ceilings=V2RunCeilings(
            max_physical_calls=30, max_total_tokens=500_000, max_total_cost_usd=Decimal("20")
        ),
        clock=lambda: NOW,
    )
    from researchassistant.agents import v2_extraction

    monkeypatch.setattr(v2_extraction, "_search_rank", lambda *_: 1)
    provider.scheduler = _serial_scheduler()
    batches = 0
    insert = deep.insert_v2_artifact

    def interrupt_after_promoted_source(
        db_path: str, key: str, artifact: object, created_at: object
    ) -> object:
        nonlocal batches
        result = insert(db_path, key, artifact, created_at)
        if "/rolling-v1/result/" in key:
            batches += 1
            if batches == 2:
                raise V2CancellationRequested("interrupt after promoted source checkpoints")
        return result

    monkeypatch.setattr(deep, "insert_v2_artifact", interrupt_after_promoted_source)
    kwargs = dict(
        db_path=path,
        queue_result=queue,
        discovery_outputs=(),
        acquisition_outputs=(acquisition,),
        llm_provider=provider,
        routing_config=_routing(),
        gap_outputs=(_gap(queue),),
        clock=lambda: NOW,
    )
    with pytest.raises(V2CancellationRequested):
        deep.run_v2_deep_analysis_with_backfill(**kwargs)
    prefix = read_v2_physical_call_audit(path, queue.run_id)
    assert {r.source_id for r in prefix.starts} == {
        queue.priority_source_ids[0],
        queue.priority_source_ids[3],
    }
    prefix_requests = tuple(model.requests)
    monkeypatch.setattr(deep, "insert_v2_artifact", insert)
    provider.scheduler = _serial_scheduler()
    result = deep.run_v2_deep_analysis_with_backfill(**kwargs)
    audit = read_v2_physical_call_audit(path, queue.run_id)
    assert audit.starts[: len(prefix.starts)] == prefix.starts
    assert not any(
        r.source_id in {x.source_id for x in prefix.starts}
        for r in model.requests[len(prefix_requests) :]
    )
    # An out-of-range sentence selection is terminal under the existing policy.
    assert len(audit.starts) == 6
    assert sorted(r.source_id for r in audit.starts) == sorted(queue.priority_source_ids)
    assert [r.sequence for r in audit.starts] == list(range(1, 7))
    assert result.final_execution_order == (
        queue.priority_source_ids[0],
        queue.priority_source_ids[3],
        queue.priority_source_ids[1],
        queue.priority_source_ids[2],
        *queue.priority_source_ids[4:],
    )
    assert len(audit.starts) <= 30
    assert provider.snapshot().token_exposure <= 500_000
    assert provider.snapshot().cost_exposure_usd <= Decimal("20")
    assert deep.run_v2_deep_analysis_with_backfill(**kwargs) == result
    assert len(model.requests) == 6
    assert read_v2_physical_call_audit(path, queue.run_id) == audit
