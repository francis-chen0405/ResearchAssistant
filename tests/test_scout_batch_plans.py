"""Fresh Scout request boundaries and durable replay across batch-size changes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

import pytest
from test_ranked_acquisition_integration import _fresh_case
from test_v2_ranked_scout import NOW, _RecallScout, _routing, _snapshot

from researchassistant.agents import v2_discovery
from researchassistant.agents.v2_stage_checkpoint import V2ScoutRoundCheckpoint, read_checkpoint
from researchassistant.api.application_services.live_sources import read_live_sources
from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
from researchassistant.contracts.models import (
    ScoutBatch,
    StrictModel,
    V2DiscoveryScoutOutput,
    V2PersistedArtifact,
)
from researchassistant.contracts.search import SearchDiscoveryMetadata, SearchResult
from researchassistant.providers.llm import LLMRequest, LLMStage
from researchassistant.research.discovery_policy import (
    MANDATORY_DOWNSTREAM_CALLS,
    safe_optional_model_prefix,
)
from researchassistant.storage.store import read_v2_artifact


def _case(
    tmp_path: Path,
) -> tuple[Path, UUID, _RecallScout, Callable[..., v2_discovery.V2DiscoveryScoutRunResult]]:
    path = tmp_path / "batch-plan.sqlite"
    run_id, plan, _ = _fresh_case(path)
    response = v2_discovery.V2DiscoveryResponse(
        query=plan.searches[0],
        results=tuple(
            SearchResult(
                original_url=f"https://journal.example.org/study-{index}",
                title=f"Controlled intervention outcome study {index}",
                rank=index + 1,
                metadata=SearchDiscoveryMetadata(
                    doi=f"10.5000/study-{index}",
                    abstract="A randomized intervention study compared measured primary outcomes.",
                    work_type="article",
                ),
            )
            for index in range(60)
        ),
    )
    scout = _RecallScout()

    def run(**kwargs: Any) -> v2_discovery.V2DiscoveryScoutRunResult:
        return v2_discovery.run_v2_discovery_and_scout(
            db_path=path,
            planner_output=plan,
            responses=(response,),
            llm_provider=scout,
            routing_config=_routing(),
            clock=lambda: NOW,
            budget_snapshot=lambda: _snapshot(100),
            **kwargs,
        )

    return path, run_id, scout, run


def _historical_plans(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write the exact old missing-field layout while creating a 15-item fixture."""
    insert = v2_discovery.insert_v2_artifact

    def save(
        path: str, key: str, artifact: StrictModel, created_at: datetime
    ) -> V2PersistedArtifact:
        if isinstance(artifact, V2ScoutRoundCheckpoint):
            payload = artifact.model_dump(mode="json")
            payload.pop("batch_size")
            artifact = V2ScoutRoundCheckpoint.model_validate(payload)
            assert artifact.model_dump(mode="json") == payload
        return insert(path, key, artifact, created_at)

    monkeypatch.setattr(v2_discovery, "V2_FRESH_SCOUT_BATCH_SIZE", 15)
    monkeypatch.setattr(v2_discovery, "insert_v2_artifact", save)


@pytest.mark.parametrize("historical", [False, True])
def test_interrupted_scout_replays_8_or_historical_15_boundaries_without_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, historical: bool
) -> None:
    path, run_id, scout, run = _case(tmp_path)
    published = []

    def publish(
        output: V2DiscoveryScoutOutput,
        ranking: V2MetadataRankingArtifact,
        pending: tuple[LLMRequest, ...],
        first_pass_only: bool,
    ) -> None:
        done = tuple(audit.batch_number for audit in output.scout_audits)
        remaining = tuple(request.input_artifact.batch_number for request in pending)
        published.append((done, remaining))

    def interrupt(*args: object) -> NoReturn:
        raise RuntimeError("interrupted before final Scout artifacts")

    with monkeypatch.context() as patch:
        if historical:
            _historical_plans(patch)
        patch.setattr(v2_discovery, "insert_v2_artifact_batch", interrupt)
        with pytest.raises(RuntimeError, match="interrupted before final"):
            run(on_batch=publish)

    expected_sizes = [15] * 4 if historical else [8] * 7 + [4]
    requests = tuple(scout.requests)
    assert sorted(len(request.input_artifact.candidates) for request in requests) == sorted(
        expected_sizes
    )
    all_ids = [
        candidate.item_id for request in requests for candidate in request.input_artifact.candidates
    ]
    assert len(all_ids) == len(set(all_ids)) == 60
    for done, pending in published:
        assert (*done, *pending) == tuple(range(1, len(expected_sizes) + 1))
    live = read_live_sources(path, run_id, offset=0)
    assert live.total == 60
    assert all(card.state == "screened" and card.note_kind == "scout" for card in live.items)
    key = "scout-checkpoint-v1/phase-4-discovery-scout"
    before = read_v2_artifact(str(path), run_id, key)
    checkpoint = V2ScoutRoundCheckpoint.model_validate_json(before.payload_json)
    assert checkpoint.batch_size == (None if historical else 8)
    assert ("batch_size" in checkpoint.model_dump()) is not historical

    result = run()
    assert [len(batch.items) for batch in result.output.scout_batches] == expected_sizes
    assert tuple(scout.requests) == requests
    assert read_v2_artifact(str(path), run_id, key) == before
    assert run().resumed
    assert tuple(scout.requests) == requests


@pytest.mark.parametrize("historical", [False, True])
def test_first_pass_completion_preserves_batch_plan_and_candidate_membership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, historical: bool
) -> None:
    path, run_id, scout, run = _case(tmp_path)
    with monkeypatch.context() as patch:
        if historical:
            _historical_plans(patch)
        first = run(first_pass_only=True)
    size = 15 if historical else 8
    assert len(first.output.scout_batches[0].items) == size
    assert len(scout.requests) == 1
    resumed_first = run(first_pass_only=True)
    assert resumed_first.resumed
    assert len(scout.requests) == 1
    result = run(first_pass=resumed_first)
    expected_sizes = [15] * 4 if historical else [8] * 7 + [4]
    assert [len(batch.items) for batch in result.output.scout_batches] == expected_sizes
    assert [audit.batch_number for audit in result.output.scout_audits] == list(
        range(1, len(expected_sizes) + 1)
    )
    all_ids = [
        candidate.item_id
        for request in scout.requests
        for candidate in request.input_artifact.candidates
    ]
    assert len(all_ids) == len(set(all_ids)) == 60
    assert result.ranking_artifact.scouted_count == 60
    checkpoint = read_checkpoint(
        str(path), run_id, "scout-checkpoint-v1/phase-4-discovery-scout", V2ScoutRoundCheckpoint
    )
    assert checkpoint.batch_size == size
    requests = tuple(scout.requests)
    assert run(first_pass=resumed_first).resumed
    assert tuple(scout.requests) == requests


def test_historical_ranking_only_recovery_keeps_legacy_fallback_without_reissuing_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, run_id, scout, run = _case(tmp_path)
    insert = v2_discovery.insert_v2_artifact
    insert_batch = v2_discovery.insert_v2_artifact_batch

    def omit_round_plan(
        path: str, key: str, artifact: StrictModel, created_at: datetime
    ) -> V2PersistedArtifact | None:
        if not isinstance(artifact, V2ScoutRoundCheckpoint):
            return insert(path, key, artifact, created_at)

    def interrupt_after_ranking(
        path: str, artifacts: tuple[tuple[str, StrictModel, datetime], ...]
    ) -> NoReturn:
        insert_batch(path, artifacts[:1])
        raise RuntimeError("historical ranking-only interruption")

    with monkeypatch.context() as patch:
        patch.setattr(v2_discovery, "V2_FRESH_SCOUT_BATCH_SIZE", 15)
        patch.setattr(v2_discovery, "insert_v2_artifact", omit_round_plan)
        patch.setattr(v2_discovery, "insert_v2_artifact_batch", interrupt_after_ranking)
        with pytest.raises(RuntimeError, match="ranking-only interruption"):
            run()
    assert len(scout.requests) == 4
    requests = tuple(scout.requests)
    attempt_key = "scout-checkpoint-v1/phase-4-discovery-scout/batch-1/attempt-1"
    attempt = read_v2_artifact(str(path), run_id, attempt_key)
    result = run()
    assert tuple(scout.requests) == requests
    assert read_v2_artifact(str(path), run_id, attempt_key) == attempt
    assert [len(batch.items) for batch in result.output.scout_batches] == [20] * 3
    assert all(
        audit.attempted_calls == 0
        and audit.fallback_used
        and audit.recovery_policy == "partial-ranking-recovery-v1"
        for audit in result.output.scout_audits
    )


@pytest.mark.parametrize("limiting_budget", ["calls", "cost"])
def test_eight_item_batches_reserve_both_attempts_under_call_and_cost_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limiting_budget: str
) -> None:
    path, run_id, scout, run = _case(tmp_path)
    recorded = []
    route = _routing().preflight()

    def limit(**kwargs: Any) -> int:
        reservations = kwargs["optional_reservations"]
        recorded.extend(reservations)
        # Fourteen full-size reservations plus two for the final four candidates.
        assert len(reservations) == 16
        assert all(reservations[index] == reservations[index + 1] for index in range(0, 16, 2))
        snapshot = kwargs["snapshot"]
        if limiting_budget == "calls":
            snapshot = snapshot.model_copy(
                update={"physical_calls_remaining": MANDATORY_DOWNSTREAM_CALLS + 3}
            )
        else:
            protected = [
                route.reserve(stage, kwargs["downstream_input_tokens"][stage])
                for stage, _ in route.routing
            ]
            cost = MANDATORY_DOWNSTREAM_CALLS * max(item.reserved_cost_usd for item in protected)
            snapshot = snapshot.model_copy(
                update={
                    "cost_remaining_usd": cost
                    + sum((item.reserved_cost_usd for item in reservations[:3]), Decimal("0"))
                }
            )
        return safe_optional_model_prefix(**{**kwargs, "snapshot": snapshot})

    monkeypatch.setattr(v2_discovery, "safe_optional_model_prefix", limit)
    result = run()
    assert recorded and all(item.stage is LLMStage.SCOUT for item in recorded)
    assert result.ranking_artifact.scouted_count == 8
    assert len(scout.requests) == 1
    assert isinstance(scout.requests[0].input_artifact, v2_discovery.V2ClaimScoutRequest)
    assert len(scout.requests[0].input_artifact.candidates) == 8
    assert all(isinstance(batch, ScoutBatch) for batch in result.output.scout_batches)
