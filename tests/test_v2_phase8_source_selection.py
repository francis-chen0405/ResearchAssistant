from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from agents.v2_source_selection import (
    V2_SOURCE_SELECTION_MAX_ATTEMPTS,
    V2_SOURCE_SELECTION_POOL_KEY,
    calculate_v2_deep_analysis_queue,
    run_v2_source_selection_and_queue,
)
from models import (
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    Stage,
    V2DeepAnalysisBudget,
    V2PipelineIdentity,
    V2SourceSelectionCandidate,
    V2SourceSelectionInput,
    V2SourceSelectionModelOutput,
    V2SourceSelectionRecommendation,
)
from providers.llm import LLMProviderCapabilities, LLMStage
from providers.v2_routing import V2RoutingConfig
from store import init_db, insert_run, insert_v2_pipeline_identity, read_v2_artifact

NOW = datetime(2026, 8, 21, tzinfo=UTC)


class FakeSourceSelector:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.requests: list[object] = []

    def generate(self, request: object) -> object:
        self.requests.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def _routing() -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        {
            "MIMO_API_KEY": "mimo-secret",
            "MIMO_V25_MODEL": "mimo-v2.5",
            "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
            "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
            "LUNA_API_KEY": "luna-secret",
            "LUNA_BASE_URL": "https://luna.example.test/v1",
            "LUNA_MODEL": "deployment-owned-luna-model",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="v2-phase8-tests",
    )


def _candidate(
    source_id: UUID,
    *,
    direction: ResearchDirection = ResearchDirection.SUPPORT,
    family: str,
    probe_score: int,
    research_round: int = 1,
) -> V2SourceSelectionCandidate:
    return V2SourceSelectionCandidate(
        source_id=source_id,
        direction=direction,
        source_family_id=family,
        research_round=research_round,
        source_url=f"https://example.test/{source_id}",
        title=f"Source {source_id}",
        source_type="primary empirical study",
        discovery_providers=(DiscoveryProvider.OPENALEX,),
        probe_passages=(
            {
                "passage_id": f"probe-{source_id}",
                "text": "A primary empirical result reports a measured outcome.",
                "score": probe_score,
            },
        ),
        search_provenance=(
            {
                "query_id": uuid4(),
                "provider": DiscoveryProvider.OPENALEX,
                "round_number": research_round,
                "query_text": "measured outcome empirical study",
                "targeted_gap_ids": (() if research_round == 1 else ("gap-1",)),
            },
        ),
        snapshot_word_count=800,
        deep_analysis_input_tokens=1600,
    )


def _selection_input(
    candidates: tuple[V2SourceSelectionCandidate, ...],
    *,
    directions: ResearchDirections | None = None,
) -> V2SourceSelectionInput:
    return V2SourceSelectionInput(
        run_id=uuid4(),
        exact_claim="A public claim.",
        directions=directions or ResearchDirections(),
        survivors=candidates,
        gap_history=(
            {
                "gap_id": "gap-1",
                "direction": ResearchDirection.SUPPORT,
                "missing_evidence": "Independent empirical evidence is missing.",
            },
        ),
    )


def _budget(
    *,
    physical_calls_used: int = 0,
    tokens_remaining: int = 2_000_000,
    cost_remaining_usd: str = "100",
) -> V2DeepAnalysisBudget:
    return V2DeepAnalysisBudget(
        physical_calls_used=physical_calls_used,
        tokens_remaining=tokens_remaining,
        cost_remaining_usd=Decimal(cost_remaining_usd),
    )


def _recommendation(source_id: UUID, *, gap_ids: tuple[str, ...] = ()) -> object:
    return {
        "source_id": source_id,
        "rationale": "Adds direct, credible, nonredundant empirical coverage.",
        "gap_ids": gap_ids,
    }


def _prepare_db(tmp_path: Path, run_id: UUID) -> str:
    db_path = str(tmp_path / "phase8.sqlite3")
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="A public claim.",
            current_stage=Stage.SUPPORTING_RESEARCHER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)
    return db_path


def test_all_survivors_are_retained_and_complementary_recommendations_are_queued(
    tmp_path: Path,
) -> None:
    source_ids = tuple(uuid4() for _ in range(4))
    selection_input = _selection_input(
        (
            _candidate(source_ids[0], family="family-a", probe_score=12),
            _candidate(source_ids[1], family="family-b", probe_score=10),
            _candidate(source_ids[2], family="family-a", probe_score=9),
            _candidate(source_ids[3], family="family-c", probe_score=8),
        )
    )
    provider = FakeSourceSelector(
        [
            V2SourceSelectionModelOutput(
                recommendations=tuple(
                    V2SourceSelectionRecommendation.model_validate(item)
                    for item in (
                        _recommendation(source_ids[0], gap_ids=("gap-1",)),
                        _recommendation(source_ids[1]),
                        _recommendation(source_ids[3]),
                    )
                )
            )
        ]
    )
    db_path = _prepare_db(tmp_path, selection_input.run_id)

    result = run_v2_source_selection_and_queue(
        db_path=db_path,
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: NOW,
    )

    assert len(result.source_statuses) == len(selection_input.survivors)
    assert {status.source_id for status in result.source_statuses} == set(source_ids)
    assert result.recommended_source_ids == (source_ids[0], source_ids[1], source_ids[3])
    assert result.queued_source_ids[:3] == result.recommended_source_ids
    assert result.queued_source_ids[3] == source_ids[2]
    assert all(status.queued_for_deep_analysis for status in result.source_statuses)
    assert all(status.budget_prevented_reason is None for status in result.source_statuses)
    persisted_pool = V2SourceSelectionInput.model_validate_json(
        read_v2_artifact(
            db_path,
            selection_input.run_id,
            V2_SOURCE_SELECTION_POOL_KEY,
        ).payload_json
    )
    assert tuple(item.source_id for item in persisted_pool.survivors) == source_ids


def test_duplicate_family_domination_retries_then_accepts_diverse_prefix(tmp_path: Path) -> None:
    source_ids = tuple(uuid4() for _ in range(3))
    selection_input = _selection_input(
        (
            _candidate(source_ids[0], family="family-a", probe_score=12),
            _candidate(source_ids[1], family="family-a", probe_score=11),
            _candidate(source_ids[2], family="family-b", probe_score=10),
        )
    )
    provider = FakeSourceSelector(
        [
            V2SourceSelectionModelOutput(
                recommendations=tuple(
                    V2SourceSelectionRecommendation.model_validate(item)
                    for item in (
                        _recommendation(source_ids[0]),
                        _recommendation(source_ids[1]),
                        _recommendation(source_ids[2]),
                    )
                )
            ),
            V2SourceSelectionModelOutput(
                recommendations=tuple(
                    V2SourceSelectionRecommendation.model_validate(item)
                    for item in (
                        _recommendation(source_ids[0]),
                        _recommendation(source_ids[2]),
                        _recommendation(source_ids[1]),
                    )
                )
            ),
        ]
    )

    result = run_v2_source_selection_and_queue(
        db_path=_prepare_db(tmp_path, selection_input.run_id),
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: NOW,
    )

    assert len(provider.requests) == V2_SOURCE_SELECTION_MAX_ATTEMPTS
    assert result.recommended_source_ids[:2] == (source_ids[0], source_ids[2])
    assert result.used_fallback is False


def test_selection_failure_falls_back_without_dropping_survivors(tmp_path: Path) -> None:
    source_ids = tuple(uuid4() for _ in range(4))
    selection_input = _selection_input(
        (
            _candidate(source_ids[0], family="family-a", probe_score=12),
            _candidate(source_ids[1], family="family-a", probe_score=11),
            _candidate(source_ids[2], family="family-b", probe_score=10),
            _candidate(source_ids[3], family="family-c", probe_score=9),
        )
    )
    provider = FakeSourceSelector([RuntimeError("offline failure"), RuntimeError("retry failure")])

    result = run_v2_source_selection_and_queue(
        db_path=_prepare_db(tmp_path, selection_input.run_id),
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: NOW,
    )

    assert result.used_fallback is True
    assert result.recommended_source_ids[:3] == (source_ids[0], source_ids[2], source_ids[3])
    assert set(result.queued_source_ids) == set(source_ids)
    assert len(provider.requests) == V2_SOURCE_SELECTION_MAX_ATTEMPTS


def test_queue_math_protects_the_160_call_ceiling_and_synthesis() -> None:
    source_ids = tuple(uuid4() for _ in range(3))
    selection_input = _selection_input(
        tuple(
            _candidate(source_id, family=f"family-{index}", probe_score=10 - index)
            for index, source_id in enumerate(source_ids)
        )
    )
    result = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=source_ids,
        recommended_source_ids=source_ids,
        routing_config=_routing(),
        budget=_budget(physical_calls_used=151),
    )

    assert result.physical_calls_per_source == 7
    assert result.mandatory_synthesis_physical_calls == 2
    assert result.queue_capacity == 1
    assert result.physical_calls_after_reserve == 160
    assert result.queued_source_ids == (source_ids[0],)
    assert all(
        status.budget_prevented_reason == "physical_call_ceiling"
        for status in result.source_statuses[1:]
    )


def test_six_survivors_fit_the_500k_ceiling_with_60k_source_allowances() -> None:
    source_ids = tuple(uuid4() for _ in range(6))
    selection_input = _selection_input(
        tuple(
            _candidate(source_id, family=f"family-{index}", probe_score=10 - index)
            for index, source_id in enumerate(source_ids)
        )
    )

    result = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=source_ids,
        recommended_source_ids=source_ids,
        routing_config=_routing(),
        budget=_budget(tokens_remaining=500_000),
    )

    assert result.queued_source_ids == source_ids
    assert result.queue_capacity == 6
    assert result.physical_calls_after_reserve == 44
    assert result.total_reserved_tokens < 500_000


def test_token_reserve_shrinks_queue_as_a_deterministic_prefix() -> None:
    source_ids = tuple(uuid4() for _ in range(3))
    selection_input = _selection_input(
        tuple(
            _candidate(source_id, family=f"family-{index}", probe_score=10 - index)
            for index, source_id in enumerate(source_ids)
        )
    )
    generous = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=source_ids,
        recommended_source_ids=source_ids,
        routing_config=_routing(),
        budget=_budget(),
    )
    one_source_tokens = generous.token_reservations[0].cumulative_reserved_tokens
    constrained = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=source_ids,
        recommended_source_ids=source_ids,
        routing_config=_routing(),
        budget=_budget(tokens_remaining=one_source_tokens),
    )
    repeated = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=source_ids,
        recommended_source_ids=source_ids,
        routing_config=_routing(),
        budget=_budget(tokens_remaining=one_source_tokens),
    )

    assert constrained.queue_capacity == 1
    assert constrained.queued_source_ids == (source_ids[0],)
    assert constrained == repeated
    assert constrained.source_statuses[1].budget_prevented_reason == "token_reserve"


def test_cost_reserve_protects_the_same_deterministic_queue_prefix() -> None:
    source_ids = tuple(uuid4() for _ in range(2))
    selection_input = _selection_input(
        tuple(
            _candidate(source_id, family=f"family-{index}", probe_score=10 - index)
            for index, source_id in enumerate(source_ids)
        )
    )
    generous = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=source_ids,
        recommended_source_ids=source_ids,
        routing_config=_routing(),
        budget=_budget(),
    )
    one_source_cost = generous.token_reservations[0].cumulative_reserved_cost_usd

    constrained = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=source_ids,
        recommended_source_ids=source_ids,
        routing_config=_routing(),
        budget=_budget(cost_remaining_usd=str(one_source_cost)),
    )

    assert constrained.queued_source_ids == (source_ids[0],)
    assert constrained.source_statuses[1].budget_prevented_reason == "cost_reserve"


def test_two_direction_recommendations_and_queue_are_interleaved(tmp_path: Path) -> None:
    support_ids = (uuid4(), uuid4())
    challenge_ids = (uuid4(), uuid4())
    directions = ResearchDirections(support_enabled=True, challenge_enabled=True)
    selection_input = _selection_input(
        (
            _candidate(support_ids[0], family="support-a", probe_score=12),
            _candidate(support_ids[1], family="support-b", probe_score=10),
            _candidate(
                challenge_ids[0],
                direction=ResearchDirection.CHALLENGE,
                family="challenge-a",
                probe_score=11,
            ),
            _candidate(
                challenge_ids[1],
                direction=ResearchDirection.CHALLENGE,
                family="challenge-b",
                probe_score=9,
            ),
        ),
        directions=directions,
    )
    provider = FakeSourceSelector(
        [
            V2SourceSelectionModelOutput(
                recommendations=tuple(
                    V2SourceSelectionRecommendation.model_validate(_recommendation(source_id))
                    for source_id in (
                        support_ids[0],
                        support_ids[1],
                        challenge_ids[0],
                        challenge_ids[1],
                    )
                )
            )
        ]
    )
    result = run_v2_source_selection_and_queue(
        db_path=_prepare_db(tmp_path, selection_input.run_id),
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: NOW,
    )

    assert result.recommended_source_ids == (
        support_ids[0],
        challenge_ids[0],
        support_ids[1],
        challenge_ids[1],
    )
    assert result.queued_source_ids == result.recommended_source_ids


def test_completed_selection_and_queue_resume_without_another_call(tmp_path: Path) -> None:
    source_id = uuid4()
    selection_input = _selection_input((_candidate(source_id, family="family-a", probe_score=12),))
    provider = FakeSourceSelector(
        [
            V2SourceSelectionModelOutput(
                recommendations=(
                    V2SourceSelectionRecommendation.model_validate(
                        _recommendation(source_id, gap_ids=("gap-1",))
                    ),
                )
            )
        ]
    )
    db_path = _prepare_db(tmp_path, selection_input.run_id)
    first = run_v2_source_selection_and_queue(
        db_path=db_path,
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: NOW,
    )
    resumed = run_v2_source_selection_and_queue(
        db_path=db_path,
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: NOW,
    )

    assert resumed.result == first.result
    assert resumed.resumed is True
    assert len(provider.requests) == 1
    assert resumed.result.selection_attempts == 1
    assert resumed.result.selection_stage == LLMStage.SOURCE_SELECTION.value
