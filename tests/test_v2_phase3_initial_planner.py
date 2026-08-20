from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.v2_initial_planner import (
    V2InitialPlannerFingerprintMismatchError,
    run_v2_initial_planner,
)
from models import (
    DiscoveryProvider,
    ResearchDirection,
    ResearchDirections,
    V2InitialPlannerModelOutput,
    V2InitialPlannerOutput,
    V2InitialPlannerPolicy,
    V2InitialPlannerSearchResponse,
    V2RoundOneSearchQuery,
)
from providers.llm import LLMProviderCapabilities
from providers.v2_routing import V2RoutingConfig
from store import CURRENT_SCHEMA_VERSION, read_v2_artifact, read_v2_initial_planner_output

NOW = datetime(2026, 8, 20, tzinfo=UTC)


class FakeInitialPlanner:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self) -> None:
        self.requests = []

    def generate(self, request: object) -> V2InitialPlannerModelOutput:
        self.requests.append(request)
        lanes = request.input_artifact.search_lanes
        return V2InitialPlannerModelOutput(
            scope_interpretations=(),
            searches=tuple(
                V2InitialPlannerSearchResponse(
                    direction=lane.direction,
                    provider=lane.provider,
                    strategy=lane.strategy,
                    query_text=(
                        f"{lane.direction.value} {lane.provider.value} {lane.strategy} evidence"
                    ),
                )
                for lane in lanes
            ),
        )


def _environment() -> dict[str, str]:
    return {
        "MIMO_API_KEY": "mimo-secret-value",
        "MIMO_V25_MODEL": "mimo-v2.5",
        "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
        "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
        "LUNA_API_KEY": "luna-secret-value",
        "LUNA_BASE_URL": "https://luna.example.test/v1",
        "LUNA_MODEL": "deployment-owned-luna-model",
        "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
        "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
    }


def _routing(environment: dict[str, str] | None = None) -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        environment or _environment(), repository_revision="v2-phase3-test-revision"
    )


@pytest.mark.parametrize(
    ("directions", "expected_directions"),
    [
        (
            ResearchDirections(support_enabled=True, challenge_enabled=False),
            {ResearchDirection.SUPPORT},
        ),
        (
            ResearchDirections(support_enabled=False, challenge_enabled=True),
            {ResearchDirection.CHALLENGE},
        ),
        (
            ResearchDirections(support_enabled=True, challenge_enabled=True),
            {ResearchDirection.SUPPORT, ResearchDirection.CHALLENGE},
        ),
    ],
)
def test_v2_initial_planner_isolates_enabled_directions(
    tmp_path: Path,
    directions: ResearchDirections,
    expected_directions: set[ResearchDirection],
) -> None:
    provider = FakeInitialPlanner()
    result = run_v2_initial_planner(
        "A public claim.",
        db_path=tmp_path / "planner.sqlite3",
        directions=directions,
        discovery_providers=(DiscoveryProvider.EXA,),
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert {query.direction for query in result.planner_output.searches} == expected_directions
    assert {query.round_number for query in result.planner_output.searches} == {1}
    assert result.planner_output.raw_claim == "A public claim."
    assert len(provider.requests) == 1


def test_v2_initial_planner_respects_provider_toggles_and_never_plans_future_rounds(
    tmp_path: Path,
) -> None:
    result = run_v2_initial_planner(
        "A public claim.",
        db_path=tmp_path / "providers.sqlite3",
        directions=ResearchDirections(),
        discovery_providers=(DiscoveryProvider.SERPSEARCH, DiscoveryProvider.OPENALEX),
        llm_provider=FakeInitialPlanner(),
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert {query.provider for query in result.planner_output.searches} == {
        DiscoveryProvider.SERPSEARCH,
        DiscoveryProvider.OPENALEX,
    }
    assert all(query.round_number == 1 for query in result.planner_output.searches)
    assert len(result.planner_output.searches) == 3


def test_v2_initial_planner_preserves_the_exact_submitted_claim(tmp_path: Path) -> None:
    claim = "  A public claim with exact surrounding whitespace.  "
    result = run_v2_initial_planner(
        claim,
        db_path=tmp_path / "exact-claim.sqlite3",
        directions=ResearchDirections(),
        discovery_providers=(DiscoveryProvider.EXA,),
        llm_provider=FakeInitialPlanner(),
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert result.planner_output.raw_claim == claim


def test_v2_initial_planner_rejects_disabled_or_invalid_providers() -> None:
    policy = V2InitialPlannerPolicy()
    with pytest.raises(ValueError, match="discovery provider"):
        policy.search_lanes(ResearchDirections(), ())
    with pytest.raises(ValidationError):
        V2InitialPlannerSearchResponse(
            direction=ResearchDirection.SUPPORT,
            provider="not-a-provider",
            strategy="broad_web",
            query_text="claim",
        )


def test_v2_round_one_validation_rejects_invalid_round_duplicate_id_and_duplicate_query() -> None:
    directions = ResearchDirections()
    providers = (DiscoveryProvider.EXA,)
    lanes = V2InitialPlannerPolicy().search_lanes(directions, providers)
    run_id = uuid4()
    searches = tuple(
        V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=lane.direction,
            provider=lane.provider,
            strategy=lane.strategy,
            query_text="same normalized text" if index < 2 else f"query {index}",
            created_at=NOW,
        )
        for index, lane in enumerate(lanes)
    )
    with pytest.raises(ValidationError, match="query text must be unique"):
        V2InitialPlannerOutput(
            run_id=run_id,
            raw_claim="A public claim.",
            directions=directions,
            discovery_providers=providers,
            searches=searches,
            planner_prompt_version="test-v1",
            planned_at=NOW,
        )
    with pytest.raises(ValidationError, match="round_number"):
        V2RoundOneSearchQuery(
            run_id=run_id,
            query_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.EXA,
            round_number=2,
            strategy="direct_evidence",
            query_text="a query",
            created_at=NOW,
        )
    duplicate_id = uuid4()
    distinct_searches = tuple(
        item.model_copy(update={"query_id": duplicate_id}) for item in searches
    )
    with pytest.raises(ValidationError, match="query IDs must be unique"):
        V2InitialPlannerOutput(
            run_id=run_id,
            raw_claim="A public claim.",
            directions=directions,
            discovery_providers=providers,
            searches=distinct_searches,
            planner_prompt_version="test-v1",
            planned_at=NOW,
        )


def test_v2_initial_planner_persists_and_restarts_without_another_planner_call(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "restart.sqlite3"
    run_id = uuid4()
    provider = FakeInitialPlanner()
    first = run_v2_initial_planner(
        "A public claim.",
        db_path=db_path,
        directions=ResearchDirections(),
        discovery_providers=(DiscoveryProvider.EXA,),
        llm_provider=provider,
        routing_config=_routing(),
        run_id=run_id,
        clock=lambda: NOW,
    )
    second = run_v2_initial_planner(
        "A public claim.",
        db_path=db_path,
        directions=ResearchDirections(),
        discovery_providers=(DiscoveryProvider.EXA,),
        llm_provider=provider,
        routing_config=_routing(),
        run_id=run_id,
        clock=lambda: NOW,
    )

    assert not first.resumed
    assert second.resumed
    assert second.planner_output == first.planner_output
    assert len(provider.requests) == 1
    assert read_v2_initial_planner_output(str(db_path), run_id) == first.planner_output
    assert read_v2_artifact(str(db_path), run_id, "phase-3-initial-round-1-plan").artifact_type == (
        "V2InitialPlannerOutput"
    )
    assert CURRENT_SCHEMA_VERSION == 12


def test_v2_initial_planner_rejects_fingerprint_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "mismatch.sqlite3"
    run_id = uuid4()
    run_v2_initial_planner(
        "A public claim.",
        db_path=db_path,
        directions=ResearchDirections(),
        discovery_providers=(DiscoveryProvider.EXA,),
        llm_provider=FakeInitialPlanner(),
        routing_config=_routing(),
        run_id=run_id,
        clock=lambda: NOW,
    )
    changed = _environment()
    changed["LUNA_MODEL"] = "changed-luna-model"

    with pytest.raises(V2InitialPlannerFingerprintMismatchError, match="fingerprint"):
        run_v2_initial_planner(
            "A public claim.",
            db_path=db_path,
            directions=ResearchDirections(),
            discovery_providers=(DiscoveryProvider.EXA,),
            llm_provider=FakeInitialPlanner(),
            routing_config=_routing(changed),
            run_id=run_id,
            clock=lambda: NOW,
        )
