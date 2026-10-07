from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
from test_v2_phase2_routing import _config

from providers.llm import LLMStage
from providers.v2_budget import V2BudgetSnapshot
from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryPolicy,
    V2DiscoveryProviderBudget,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import ResearchDirection, ResearchDirections
from researchassistant.research.discovery_capabilities import get_provider_capabilities
from researchassistant.research.discovery_policy import (
    build_discovery_binding,
    discovery_contract_schema_hash,
    effective_metadata_depth,
    fair_candidate_quotas,
    safe_optional_model_prefix,
    scout_candidate_capacity,
    stable_work_key,
)


def test_fair_allocation_is_independent_of_provider_and_response_order() -> None:
    providers = (DiscoveryProvider.OPENALEX, DiscoveryProvider.SERPSEARCH)
    directions = ResearchDirections(challenge_enabled=True)
    available = {(d, p): 100 for d in directions.enabled_directions for p in providers}
    policy = V2DiscoveryPolicy()
    forward = fair_candidate_quotas(
        policy=policy,
        directions=directions,
        providers=providers,
        available_by_lane=available,
        retained_run_count=997,
    )
    reversed_order = fair_candidate_quotas(
        policy=policy,
        directions=directions,
        providers=tuple(reversed(providers)),
        available_by_lane=dict(reversed(tuple(available.items()))),
        retained_run_count=997,
    )
    assert forward == reversed_order
    assert tuple(item.candidates for item in forward) == (1, 1, 1, 0)
    assert sum(item.candidates for item in forward) == 3


def test_failed_lane_share_returns_to_available_lanes_without_exceeding_round_cap() -> None:
    providers = (DiscoveryProvider.OPENALEX, DiscoveryProvider.EXA)
    quotas = fair_candidate_quotas(
        policy=V2DiscoveryPolicy(),
        directions=ResearchDirections(),
        providers=providers,
        available_by_lane={(ResearchDirection.SUPPORT, DiscoveryProvider.OPENALEX): 400},
        retained_run_count=200,
        retained_round_count=290,
    )
    assert sum(item.candidates for item in quotas) == 10
    assert quotas[0].candidates == 0
    assert quotas[1].candidates == 10


def test_exhausted_cap_and_disabled_lanes_fail_closed() -> None:
    provider = DiscoveryProvider.OPENALEX
    quotas = fair_candidate_quotas(
        policy=V2DiscoveryPolicy(),
        directions=ResearchDirections(),
        providers=(provider,),
        available_by_lane={(ResearchDirection.SUPPORT, provider): 200},
        retained_run_count=1000,
    )
    assert quotas[0].candidates == 0
    with pytest.raises(ValueError, match="disabled"):
        fair_candidate_quotas(
            policy=V2DiscoveryPolicy(),
            directions=ResearchDirections(),
            providers=(provider,),
            available_by_lane={(ResearchDirection.CHALLENGE, provider): 10},
            retained_run_count=0,
        )


@pytest.mark.parametrize(
    ("stage", "safe_candidates", "expected"),
    [("scout", 20, 20), ("acquisition", None, 20)],
)
def test_downstream_quotas_use_existing_candidates_after_raw_caps_fill(
    stage: Literal["scout", "acquisition"], safe_candidates: int | None, expected: int
) -> None:
    provider = DiscoveryProvider.OPENALEX
    quotas = fair_candidate_quotas(
        policy=V2DiscoveryPolicy(),
        directions=ResearchDirections(),
        providers=(provider,),
        available_by_lane={(ResearchDirection.SUPPORT, provider): 20},
        retained_run_count=1000,
        retained_round_count=300,
        stage=stage,
        safely_available_model_candidates=safe_candidates,
    )
    assert quotas[0].candidates == expected


@pytest.mark.parametrize(
    ("provider", "requests", "expected"),
    [
        (DiscoveryProvider.SERPSEARCH, 0, 0),
        (DiscoveryProvider.SERPSEARCH, 1, 10),
        (DiscoveryProvider.SERPSEARCH, 3, 10),
        (DiscoveryProvider.OPENALEX, 1, 50),
        (DiscoveryProvider.EXA, 3, 50),
    ],
)
def test_effective_depth_reports_physical_provider_restrictions(
    provider: DiscoveryProvider,
    requests: int,
    expected: int,
) -> None:
    assert (
        effective_metadata_depth(
            V2DiscoveryPolicy(metadata_depth=50), get_provider_capabilities(provider), 50, requests
        )
        == expected
    )


def test_work_key_is_stable_and_does_not_merge_unresolved_titles() -> None:
    assert stable_work_key(
        doi="https://doi.org/10.1000/AbC", canonical_url="https://one.test/a"
    ) == (stable_work_key(doi="10.1000/abc", canonical_url="https://two.test/b"))
    assert stable_work_key(doi=None, canonical_url="https://one.test/a?utm_source=x") == (
        stable_work_key(doi=None, canonical_url="https://one.test/a")
    )
    assert stable_work_key(doi=None, canonical_url="https://one.test/a") != (
        stable_work_key(doi=None, canonical_url="https://one.test/b")
    )
    with pytest.raises(ValueError, match="malformed"):
        stable_work_key(doi="not-a-doi", canonical_url="https://one.test/a")


def _snapshot(calls: int, tokens: int, cost: Decimal) -> V2BudgetSnapshot:
    return V2BudgetSnapshot(
        physical_calls_used=160 - calls,
        token_exposure=500000 - tokens,
        cost_exposure_usd=Decimal("20") - cost,
        physical_calls_remaining=calls,
        tokens_remaining=tokens,
        cost_remaining_usd=cost,
    )


@pytest.mark.parametrize(
    ("calls", "tokens", "cost"),
    [
        (0, 500000, Decimal("20")),
        (8, 500000, Decimal("20")),
        (160, 0, Decimal("20")),
        (160, 500000, Decimal("0")),
    ],
)
def test_optional_scout_cannot_consume_downstream_capacity(
    calls: int,
    tokens: int,
    cost: Decimal,
) -> None:
    routing = _config()
    preflight = routing.preflight()
    reservations = (preflight.reserve(LLMStage.SCOUT, 100),)
    inputs = {stage: 100 for stage, _ in preflight.routing}
    assert (
        safe_optional_model_prefix(
            snapshot=_snapshot(calls, tokens, cost),
            routing=routing,
            downstream_input_tokens=inputs,
            optional_reservations=reservations,
        )
        == 0
    )


def test_optional_scout_admits_only_budget_safe_prefix_and_caps_candidates() -> None:
    routing = _config()
    preflight = routing.preflight()
    inputs = {stage: 100 for stage, _ in preflight.routing}
    reservations = (preflight.reserve(LLMStage.SCOUT, 100),) * 3
    assert (
        safe_optional_model_prefix(
            snapshot=_snapshot(10, 500000, Decimal("20")),
            routing=routing,
            downstream_input_tokens=inputs,
            optional_reservations=reservations,
        )
        == 2
    )
    assert scout_candidate_capacity(V2DiscoveryPolicy(), 2, 100) == 40
    assert scout_candidate_capacity(V2DiscoveryPolicy(), 10, 100) == 60
    assert scout_candidate_capacity(V2DiscoveryPolicy(), 0, 100) == 0
    assert scout_candidate_capacity(V2DiscoveryPolicy(), 3, 8) == 8
    with pytest.raises(ValueError, match="complete"):
        safe_optional_model_prefix(
            snapshot=_snapshot(160, 500000, Decimal("20")),
            routing=routing,
            downstream_input_tokens={},
            optional_reservations=reservations,
        )


def test_new_binding_freezes_source_schemas_and_effective_settings(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()
    for name in ("v2_initial_planner.md", "v2_scout.md", "search_agent.md"):
        (tmp_path / "prompts" / name).write_text("test executable prompt", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("# isolated source", encoding="utf-8")
    run_id = uuid4()
    provider = DiscoveryProvider.OPENALEX
    budget = V2DiscoveryProviderBudget(
        provider=provider,
        max_requests=10,
        max_cost_usd=Decimal("0.01"),
        cost_policy_identity="fixture-upper-bound-v1",
        reservation_per_request_usd=Decimal("0.001"),
        cost_basis="configured_upper_bound",
    )
    arguments = dict(
        run_id=run_id,
        exact_claim=" Exact submitted claim. ",
        directions=ResearchDirections(),
        providers=(provider,),
        capabilities=(get_provider_capabilities(provider),),
        provider_budgets=(budget,),
        provider_configuration_hash="a" * 64,
        source_root=tmp_path,
    )
    original = build_discovery_binding(**arguments, policy=V2DiscoveryPolicy())
    assert original.exact_claim == " Exact submitted claim. "
    assert original.prompt_schema_hash == discovery_contract_schema_hash(tmp_path)
    assert (
        original.fingerprint
        != build_discovery_binding(
            **arguments, policy=V2DiscoveryPolicy(metadata_depth=30)
        ).fingerprint
    )
    (tmp_path / "prompts" / "v2_scout.md").write_text("changed executable", encoding="utf-8")
    changed = build_discovery_binding(**arguments, policy=V2DiscoveryPolicy())
    assert original.prompt_schema_hash != changed.prompt_schema_hash
    assert original.source_identity_hash != changed.source_identity_hash
    assert original.fingerprint != changed.fingerprint


def test_scout_and_acquisition_fair_quotas_remain_independent_ceilings() -> None:
    providers = (DiscoveryProvider.SERPSEARCH, DiscoveryProvider.OPENALEX)
    demand = {(ResearchDirection.SUPPORT, p): 100 for p in providers}
    arguments = dict(
        policy=V2DiscoveryPolicy(),
        directions=ResearchDirections(),
        providers=providers,
        available_by_lane=demand,
        retained_run_count=0,
    )
    quotas = fair_candidate_quotas(**arguments, stage="scout", safely_available_model_candidates=7)
    assert tuple(item.candidates for item in quotas) == (4, 3)
    assert sum(q.candidates for q in fair_candidate_quotas(**arguments, stage="acquisition")) == 25
    with pytest.raises(ValueError, match="safely available"):
        fair_candidate_quotas(**arguments, stage="scout")


def test_near_exhausted_cost_protects_downstream_to_last_decimal() -> None:
    from researchassistant.common.money import add_usd

    routing = _config()
    preflight = routing.preflight()
    inputs = {stage: 100 for stage, _ in preflight.routing}
    downstream = max(
        preflight.reserve(stage, 100).reserved_cost_usd for stage, _ in preflight.routing
    )
    optional = preflight.reserve(LLMStage.SCOUT, 100)
    exact_fit = add_usd(*(downstream for _ in range(8)), optional.reserved_cost_usd)
    arguments = dict(
        routing=routing, downstream_input_tokens=inputs, optional_reservations=(optional,)
    )
    assert safe_optional_model_prefix(**arguments, snapshot=_snapshot(9, 500000, exact_fit)) == 1
    assert (
        safe_optional_model_prefix(
            **arguments,
            snapshot=_snapshot(9, 500000, exact_fit - Decimal("0.000000000000000000000001")),
        )
        == 0
    )


def test_candidate_order_does_not_compare_provider_relevance_scores() -> None:
    from test_discovery_foundations_contracts import artifact

    from researchassistant.contracts.discovery_v2 import V2RawDiscoveryCandidate, V2WorkIdentity
    from researchassistant.research.discovery_policy import stable_candidate_order

    run_id = uuid4()
    operation_id = uuid4()
    work = V2WorkIdentity(grouping_key="fixture-work", resolution="unresolved")
    common = dict(
        operation_id=operation_id,
        attempt_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        response_hash="a" * 64,
        work=work,
    )
    first = artifact(
        V2RawDiscoveryCandidate,
        run_id,
        "first",
        **common,
        provider=DiscoveryProvider.EXA,
        provider_rank=1,
        provider_relevance=-100.0,
    )
    second = artifact(
        V2RawDiscoveryCandidate,
        run_id,
        "second",
        **common,
        provider=DiscoveryProvider.OPENALEX,
        provider_rank=1,
        provider_relevance=10000.0,
    )
    assert stable_candidate_order((second, first)) == (first, second)
    assert stable_candidate_order((first, second)) == (first, second)
    with pytest.raises(ValueError, match="duplicate"):
        stable_candidate_order((first, first))


@pytest.mark.parametrize("invalid_count", [True, 299.5, -1])
def test_fractional_or_boolean_counts_cannot_break_the_fair_cap(invalid_count: object) -> None:
    with pytest.raises(ValueError, match="nonnegative integers"):
        fair_candidate_quotas(
            policy=V2DiscoveryPolicy(),
            directions=ResearchDirections(),
            providers=(DiscoveryProvider.OPENALEX,),
            available_by_lane={(ResearchDirection.SUPPORT, DiscoveryProvider.OPENALEX): 500},
            retained_run_count=invalid_count,
        )  # type: ignore[arg-type]
