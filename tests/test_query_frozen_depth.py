from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from agents.v2_adaptive_search import (
    V2AdaptivePlanValidationError,
    _validate_and_assemble_plan,
)
from agents.v2_initial_planner import run_v2_initial_planner
from providers.llm import LLMProviderCapabilities
from providers.search import SearchRequest, page_parameters
from providers.v2_routing import V2RoutingConfig
from researchassistant.contracts.discovery_v2 import (
    V2ConceptGroup,
    V2ConceptualQuery,
    V2DiscoveryPolicy,
    V2MetadataDiscoveryPolicy,
    discovery_id,
)
from researchassistant.contracts.model_contracts import (
    DiscoveryProvider,
    SearchIntent,
)
from researchassistant.contracts.model_research import V2GapSearchDirection
from researchassistant.contracts.models import (
    ResearchDirection,
    ResearchDirections,
    V2AdaptiveSearchConceptsOutput,
    V2InitialPlannerConceptsOutput,
    V2MaterialGap,
    V2ProviderSearchBudget,
    V2SearchAgentInput,
)
from researchassistant.contracts.query_planning import (
    V2AdaptiveSearchConceptProposal,
    V2ConceptualAdaptiveLane,
    V2QueryConceptGroup,
    V2QueryConcepts,
)
from researchassistant.research.query_compiler import compile_query

NOW = datetime(2026, 10, 7, tzinfo=UTC)


class _ConceptPlanner:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def generate(self, request: object) -> V2InitialPlannerConceptsOutput:
        return V2InitialPlannerConceptsOutput(
            queries=tuple(
                V2QueryConcepts(
                    required_concepts=(V2QueryConceptGroup(concept="camera enforcement study"),),
                    purpose="broad",
                )
                for _ in request.input_artifact.search_lanes
            )
        )


def _routing() -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        {
            "MIMO_API_KEY": "fixture-mimo",
            "MIMO_V25_MODEL": "mimo-v2.5",
            "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
            "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
            "LUNA_API_KEY": "fixture-luna",
            "LUNA_BASE_URL": "https://luna.example.test/v1",
            "LUNA_MODEL": "deployment-owned-luna-model",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="frozen-depth-test",
    )


def _conceptual(
    run_id: UUID, identity: str, concept: str, round_number: int = 1
) -> V2ConceptualQuery:
    return V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", identity),
        identity_key=identity,
        required_concepts=(V2ConceptGroup(concept=concept),),
        purpose="broad" if round_number == 1 else "gap",
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        round_number=round_number,
    )


def _adaptive_input(run_id: UUID, prior_query: str) -> V2SearchAgentInput:
    gap = V2MaterialGap(
        gap_id="gap-outcome",
        direction=ResearchDirection.SUPPORT,
        missing_evidence="independent cohort replication",
        rationale="The available evidence does not resolve this limitation.",
    )
    return V2SearchAgentInput(
        run_id=run_id,
        exact_claim="A public claim.",
        round_number=2,
        directions=ResearchDirections(),
        eligible_providers=(DiscoveryProvider.OPENALEX,),
        material_gaps=(gap,),
        search_directions=(
            V2GapSearchDirection(
                gap_id=gap.gap_id,
                direction=ResearchDirection.SUPPORT,
                missing_evidence=gap.missing_evidence,
                search_focus="independent replication cohort",
            ),
        ),
        discovered_terms=(),
        previous_queries=(prior_query,),
        provider_budgets=(
            V2ProviderSearchBudget(
                provider=DiscoveryProvider.OPENALEX,
                attempted_calls=1,
                maximum_calls=10,
            ),
        ),
        maximum_queries=1,
    )


def _adaptive_response() -> V2AdaptiveSearchConceptsOutput:
    return V2AdaptiveSearchConceptsOutput(
        searches=(
            V2AdaptiveSearchConceptProposal(
                lane_index=0,
                concepts=V2QueryConcepts(
                    required_concepts=(
                        V2QueryConceptGroup(concept="independent randomized cohort replication"),
                    ),
                    purpose="gap",
                ),
            ),
        )
    )


def _adaptive_lane() -> tuple[V2ConceptualAdaptiveLane, ...]:
    return (
        V2ConceptualAdaptiveLane(
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.OPENALEX,
            strategy="independent replication cohort",
            target_gap_ids=("gap-outcome",),
            mode="lexical",
        ),
    )


def test_initial_planner_freezes_explicit_depth_and_bounds_native_page(tmp_path: Path) -> None:
    result = run_v2_initial_planner(
        "A public claim.",
        db_path=tmp_path / "initial-depth.sqlite3",
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        discovery_providers=(DiscoveryProvider.OPENALEX,),
        llm_provider=_ConceptPlanner(),
        routing_config=_routing(),
        discovery_policy=V2MetadataDiscoveryPolicy(metadata_depth=50),
        clock=lambda: NOW,
    )

    compiled = result.planner_output.searches[0].compiled_query
    assert compiled is not None
    assert compiled.requested_depth == compiled.effective_depth == 50
    request = SearchRequest(
        run_id=compiled.run_id,
        provider=DiscoveryProvider.OPENALEX,
        intent=SearchIntent.ACADEMIC_STUDY,
        query_text=compiled.query_text,
        limit=20,
        compiled_query=compiled,
    )
    assert page_parameters(request)["per_page"] == 20


def test_adaptive_assembler_inherits_successor_depth_from_previous_queries() -> None:
    run_id = uuid4()
    prior = compile_query(
        _conceptual(run_id, "prior-v2", "prior evidence synthesis"),
        requested_depth=50,
        policy=V2MetadataDiscoveryPolicy(metadata_depth=50),
    )
    request = _adaptive_input(run_id, prior.query_text)
    plan = _validate_and_assemble_plan(
        request,
        _adaptive_response(),
        "fixture-search-agent",
        NOW,
        lanes=_adaptive_lane(),
        previous_compiled_queries=(prior,),
    )

    compiled = plan.searches[0].compiled_query
    assert compiled is not None
    assert compiled.requested_depth == compiled.effective_depth == 50
    assert compiled.policy == prior.policy
    native = SearchRequest(
        run_id=run_id,
        provider=DiscoveryProvider.OPENALEX,
        intent=SearchIntent.ACADEMIC_STUDY,
        query_text=compiled.query_text,
        limit=20,
        compiled_query=compiled,
    )
    assert page_parameters(native)["per_page"] == 20


def test_adaptive_assembler_preserves_prior_v1_policy_depth() -> None:
    run_id = uuid4()
    prior = compile_query(
        _conceptual(run_id, "prior-v1", "prior evidence synthesis"),
        requested_depth=20,
        policy=V2DiscoveryPolicy(),
    )
    request = _adaptive_input(run_id, prior.query_text)
    plan = _validate_and_assemble_plan(
        request,
        _adaptive_response(),
        "fixture-search-agent",
        NOW,
        lanes=_adaptive_lane(),
        previous_compiled_queries=(prior,),
    )

    compiled = plan.searches[0].compiled_query
    assert compiled is not None
    assert compiled.policy == prior.policy
    assert compiled.requested_depth == compiled.effective_depth == 20


def test_adaptive_assembler_rejects_mixed_frozen_query_policies() -> None:
    run_id = uuid4()
    prior_v2 = compile_query(
        _conceptual(run_id, "prior-v2", "prior evidence synthesis"),
        requested_depth=50,
        policy=V2MetadataDiscoveryPolicy(metadata_depth=50),
    )
    prior_v1 = compile_query(
        _conceptual(run_id, "prior-v1", "other prior evidence"),
        requested_depth=20,
        policy=V2DiscoveryPolicy(),
    )

    try:
        _validate_and_assemble_plan(
            _adaptive_input(run_id, prior_v2.query_text),
            _adaptive_response(),
            "fixture-search-agent",
            NOW,
            lanes=_adaptive_lane(),
            previous_compiled_queries=(prior_v2, prior_v1),
        )
    except V2AdaptivePlanValidationError as error:
        assert error.code == "inconsistent_discovery_policy"
    else:
        raise AssertionError("mixed frozen policies should fail before compiling a new query")
