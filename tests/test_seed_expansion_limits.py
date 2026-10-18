"""Offline regressions for capacity exhaustion and exact graph-response replay."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from test_seed_expansion_runtime import (
    CLAIM,
    NOW,
    RUN,
    _adapter,
    _authorize_round_four,
    _binding,
    _clock,
    _identity,
    _install_gap_analysis,
    _install_round_one,
    _json_response,
    _lane,
    _manual_action,
    _openalex_work,
)

from agents.v2_adaptive_search import _execute_searches
from providers.config import OpenAlexConfig
from providers.openalex import OpenAlexSearchAdapter
from providers.openalex_neighborhood import NeighborhoodRelation, OpenAlexNeighborhoodAdapter
from providers.search import SearchProviderError, SearchRequest, SearchResponse, SearchResult
from researchassistant.contracts.discovery_v2 import (
    SearchMode,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2DiscoveryBinding,
    V2DiscoveryPolicy,
    V2ExpansionResult,
    V2GraphNeighborAction,
    V2MetadataDiscoveryPolicy,
    V2RawDiscoveryCandidate,
    V2SeedEligibility,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    ResearchDirection,
    ResearchDirections,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchQuery,
    V2PipelineIdentity,
)
from researchassistant.contracts.neighborhood import V2NeighborhoodCheckpoint
from researchassistant.research import seed_expansion as expansion
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import (
    available_query_budgets,
    execute_query,
    freeze_query_execution,
)
from researchassistant.storage.discovery_store import (
    bind_discovery_run,
    provider_attempt_audit,
    read_discovery_artifacts,
    read_discovery_binding,
)
from researchassistant.storage.query_retrieval_store import retention_headroom
from researchassistant.storage.store import (
    RunManifest,
    RunStatus,
    Stage,
    init_db,
    insert_run,
    insert_v2_pipeline_identity,
)


def _slot(action: V2GraphNeighborAction, key: str, **updates: Any) -> V2GraphNeighborAction:
    return V2GraphNeighborAction.model_validate(
        {
            **action.model_dump(),
            "identity_key": key,
            "artifact_id": discovery_id(RUN, "V2GraphNeighborAction", key),
            **updates,
        }
    )


@pytest.mark.parametrize("scope", ("round", "run"))
def test_graph_retention_capacity_is_shared_and_exhaustion_is_clean(
    tmp_path: Path, scope: str
) -> None:
    path = tmp_path / "retention.sqlite"
    policy = V2DiscoveryPolicy(
        max_raw_per_round=25,
        max_raw_per_run=25 if scope == "run" else 1000,
        max_scout_per_round=25,
    )
    _binding(path, policy=policy, seed_identity="source-seed-expansion-v3")
    _install_round_one(
        path,
        tuple(
            {
                "doi": f"10.5555/seed-{index}",
                "external_id": f"W{index}",
                "title": f"Seed {index}",
                "score": 90 - index,
            }
            for index in range(1, 4)
        ),
    )
    base = _manual_action(path)
    seeds = expansion.select_seeds(str(path), RUN, 1, _clock).seeds
    sends: list[httpx.Request] = []
    for index, seed in enumerate(seeds):
        round_number = 3 if scope == "run" and index == 2 else 2
        _install_gap_analysis(path, round_number - 1)
        action = _slot(
            base,
            f"retention-{index}",
            seed=seed,
            requested_depth=10,
            round_number=round_number,
        )
        ids = tuple(f"W{100 + index * 10 + value}" for value in range(10))

        def handler(
            request: httpx.Request,
            seed: V2SeedEligibility = seed,
            ids: tuple[str, ...] = ids,
        ) -> httpx.Response:
            sends.append(request)
            if request.url.path.endswith(seed.work.provider_work_id.rsplit("/", 1)[-1]):
                return _json_response(request, _identity(seed, refs=ids))
            selected = request.url.params["filter"].split(":", 1)[1].split("|")
            return _json_response(
                request,
                {
                    "results": [
                        _openalex_work(wid, doi=f"10.5555/{wid}", title=wid) for wid in selected
                    ]
                },
            )

        adapter, client = _adapter(handler)
        try:
            result = expansion.execute_expansion(
                path=str(path), action=action, adapter=adapter, clock=_clock
            )
            assert len(result) == min(10, 25 - index * 10)
            assert (
                expansion.execute_expansion(
                    path=str(path), action=action, adapter=None, clock=_clock
                )
                == result
            )
        finally:
            client.close()
    assert len(sends) == 6
    assert retention_headroom(str(path), RUN, 2) == 0
    artifacts = read_discovery_artifacts(str(path), RUN)
    assert len([item for item in artifacts if isinstance(item, V2RawDiscoveryCandidate)]) == 25
    exhausted = _slot(base, "retention-exhausted", relationship="citing", round_number=round_number)
    adapter, client = _adapter(handler)
    try:
        assert (
            expansion.execute_expansion(
                path=str(path), action=exhausted, adapter=adapter, clock=_clock
            )
            == ()
        )
    finally:
        client.close()
    assert len(sends) == 6
    assert any(
        isinstance(item, V2ExpansionResult)
        and item.action == exhausted
        and item.status in {"pending", "skipped"}
        for item in read_discovery_artifacts(str(path), RUN)
    )


@pytest.mark.parametrize("consumed", (3, 10))
def test_exact_response_replay_uses_original_limit_after_other_work_consumes_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, consumed: int
) -> None:
    path = tmp_path / "replay.sqlite"
    _binding(path, seed_identity="source-seed-expansion-v3")
    _install_round_one(path, ({"score": 90},))
    first = _slot(_manual_action(path), "interrupted-references", requested_depth=10)
    second = _slot(
        _manual_action(path, relationship="related"), "consuming-related", requested_depth=consumed
    )
    refs = tuple(f"W{100 + index}" for index in range(10))
    related = tuple(f"W{200 + index}" for index in range(consumed))
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if request.url.path.endswith("/W1"):
            return _json_response(request, _identity(first.seed, refs=refs, related=related))
        ids = request.url.params["filter"].split(":", 1)[1].split("|")
        return _json_response(
            request,
            {"results": [_openalex_work(wid, doi=f"10.5555/{wid}", title=wid) for wid in ids]},
        )

    adapter, client = _adapter(handler)
    persist = expansion._persist_once

    def crash(db_path: str, artifact: Any, created_at: datetime) -> None:
        if isinstance(artifact, V2NeighborhoodCheckpoint) and artifact.phase == "neighbors":
            raise RuntimeError("process loss before neighbor parser")
        persist(db_path, artifact, created_at)

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(expansion, "_persist_once", crash)
            with pytest.raises(RuntimeError, match="process loss"):
                expansion.execute_expansion(
                    path=str(path), action=first, adapter=adapter, clock=_clock
                )
        audit_before = provider_attempt_audit(str(path), RUN)
        assert len(audit_before.starts) == 2
        assert (
            len(
                expansion.execute_expansion(
                    path=str(path), action=second, adapter=adapter, clock=_clock
                )
            )
            == consumed
        )
        resumed = expansion.execute_expansion(
            path=str(path), action=first, adapter=adapter, clock=_clock
        )
        assert len(resumed) == 10 - consumed
        assert (
            expansion.execute_expansion(path=str(path), action=first, adapter=None, clock=_clock)
            == resumed
        )
    finally:
        client.close()
    assert len(sends) == 3
    audit_after = provider_attempt_audit(str(path), RUN)
    assert all(start in audit_after.starts for start in audit_before.starts)
    assert all(completion in audit_after.completions for completion in audit_before.completions)
    checkpoint = next(
        item
        for item in read_discovery_artifacts(str(path), RUN)
        if isinstance(item, V2NeighborhoodCheckpoint)
        and item.action == first
        and item.phase == "neighbors"
    )
    assert len(checkpoint.results) == 10


def _fresh_binding(
    path: Path,
    policy: V2MetadataDiscoveryPolicy | None = None,
    *,
    providers: tuple[DiscoveryProvider, ...] = (DiscoveryProvider.OPENALEX,),
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
) -> V2DiscoveryBinding:
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=RUN,
            raw_claim=CLAIM,
            status=RunStatus.PLANNED,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(path), RUN, V2PipelineIdentity(), NOW)
    return freeze_query_execution(
        str(path),
        RUN,
        CLAIM,
        ResearchDirections(support_enabled=True, challenge_enabled=False),
        providers,
        _clock,
        discovery_policy=policy,
        query_modes=query_modes,
    )


def _text_search(
    path: Path,
    index: int,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    requested_depth: int = 1,
) -> tuple[SearchResult, ...]:
    binding = read_discovery_binding(str(path), RUN)
    key = f"text-{index}"
    conceptual = V2ConceptualQuery(
        run_id=RUN,
        artifact_id=discovery_id(RUN, "V2ConceptualQuery", key),
        identity_key=key,
        provider=DiscoveryProvider.OPENALEX,
        direction=ResearchDirection.SUPPORT,
        round_number=2,
        target_gap_ids=("gap-outcome",),
        purpose="gap",
        required_concepts=(V2ConceptGroup(concept=f"outcome {index}"),),
    )
    action = compile_query(conceptual, requested_depth=requested_depth, policy=binding.policy)
    with httpx.Client(
        base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
    ) as client:
        provider = OpenAlexSearchAdapter(OpenAlexConfig(api_key="offline-test-key"), client=client)
        response = execute_query(
            path=str(path),
            run_id=RUN,
            provider=DiscoveryProvider.OPENALEX,
            query_text=action.query_text,
            compiled_query=action,
            providers={DiscoveryProvider.OPENALEX: provider},
            clock=_clock,
        )
    return tuple(response.results)


@pytest.mark.parametrize("depth", range(1, 11))
def test_each_requested_depth_is_bounded_and_replay_never_sends(tmp_path: Path, depth: int) -> None:
    path = tmp_path / "depth.sqlite"
    _binding(path, seed_identity="source-seed-expansion-v3")
    _install_round_one(path, ({"score": 90},))
    action = _slot(_manual_action(path), "depth", requested_depth=depth)
    ids = tuple(f"W{100 + index}" for index in range(10))
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if request.url.path.endswith("/W1"):
            return _json_response(request, _identity(action.seed, refs=ids))
        assert int(request.url.params["per_page"]) == depth
        # An upstream over-return cannot enlarge the persisted/accepted batch.
        return _json_response(
            request,
            {"results": [_openalex_work(wid, doi=f"10.5555/{wid}", title=wid) for wid in ids]},
        )

    adapter, client = _adapter(handler)
    try:
        result = expansion.execute_expansion(
            path=str(path), action=action, adapter=adapter, clock=_clock
        )
        assert len(result) == depth
        assert (
            expansion.execute_expansion(path=str(path), action=action, adapter=None, clock=_clock)
            == result
        )
    finally:
        client.close()
    assert len(sends) == 2
    assert retention_headroom(str(path), RUN, 2) == 300 - depth


@pytest.mark.parametrize("depth", (0, 11, True, 1.5))
def test_action_rejects_invalid_requested_depth_before_transport(
    tmp_path: Path, depth: Any
) -> None:
    path = tmp_path / "invalid-depth.sqlite"
    _binding(path, seed_identity="source-seed-expansion-v3")
    _install_round_one(path, ({"score": 90},))
    with pytest.raises(ValidationError):
        _slot(_manual_action(path), "invalid-depth", requested_depth=depth)
    assert provider_attempt_audit(str(path), RUN).starts == ()


@pytest.mark.parametrize("depth", (0, 11))
def test_adapter_rejects_out_of_range_limit_without_request(depth: int) -> None:
    work = OpenAlexNeighborhoodAdapter.parse_resolution(
        "W1", httpx.Response(200, json=_openalex_work("W1", doi=None, title="Seed"))
    ).work
    assert work is not None

    def unexpected_request(parameters: Any, send: Callable[[], httpx.Response]) -> httpx.Response:
        raise AssertionError("invalid depth started a request")

    adapter, client = _adapter(lambda _: pytest.fail("unexpected physical request"))
    try:
        with pytest.raises(ValueError, match="between 1 and 10"):
            adapter.expand(
                work, NeighborhoodRelation.CITING, requester=unexpected_request, limit=depth
            )
    finally:
        client.close()


@pytest.mark.parametrize("text_calls", (8, 9, 10))
def test_text_and_graph_share_the_ten_request_and_one_cent_ceiling(
    tmp_path: Path, text_calls: int
) -> None:
    path = tmp_path / "shared-requests.sqlite"
    _fresh_binding(path, V2MetadataDiscoveryPolicy(metadata_depth=1))
    _install_round_one(path, ({"score": 90},))
    action = _manual_action(path)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if "search" in request.url.params:
            return _json_response(request, {"results": [], "meta": {"cost_usd": "0"}})
        if request.url.path.endswith("/W1"):
            return _json_response(request, _identity(action.seed))
        return _json_response(
            request, {"results": [_openalex_work("W2", doi="10.5555/neighbor", title="Neighbor")]}
        )

    for index in range(text_calls):
        assert _text_search(path, index, handler) == ()
    if text_calls > 8:
        assert expansion.offer_expansions(str(path), RUN, 2, (_lane(),), _clock) == ()
    adapter, client = _adapter(handler)
    try:
        result = expansion.execute_expansion(
            path=str(path), action=action, adapter=adapter, clock=_clock
        )
        assert len(result) == (1 if text_calls == 8 else 0)
        assert (
            expansion.execute_expansion(
                path=str(path), action=action, adapter=adapter, clock=_clock
            )
            == result
        )
    finally:
        client.close()
    audit = provider_attempt_audit(str(path), RUN)
    assert len(sends) == len(audit.starts) == 10
    assert sum(start.reserved_cost_usd for start in audit.starts) == Decimal("0.01")
    assert available_query_budgets(str(path), RUN) == ()


def test_reported_cost_can_exhaust_ceiling_before_request_count(tmp_path: Path) -> None:
    path = tmp_path / "shared-cost.sqlite"
    _fresh_binding(path)
    _install_round_one(path, ({"score": 90},))
    action = _manual_action(path)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        return _json_response(request, {"results": [], "meta": {"cost_usd": "0.005"}})

    for index in range(2):
        assert _text_search(path, index, handler) == ()
    adapter, client = _adapter(handler)
    try:
        assert (
            expansion.execute_expansion(
                path=str(path), action=action, adapter=adapter, clock=_clock
            )
            == ()
        )
    finally:
        client.close()
    assert len(sends) == 2
    assert len(provider_attempt_audit(str(path), RUN).starts) == 2
    assert available_query_budgets(str(path), RUN) == ()


@pytest.mark.parametrize("first", ("text", "graph"))
def test_text_pages_and_graph_responses_share_retention_in_both_orders(
    tmp_path: Path, first: str
) -> None:
    path = tmp_path / "shared-retention.sqlite"
    _fresh_binding(
        path,
        V2MetadataDiscoveryPolicy(max_raw_per_round=25, max_scout_per_round=25),
    )
    _install_round_one(path, ({"score": 90},))
    action = _slot(_manual_action(path), "shared-retention", requested_depth=10)
    ids = tuple(f"W{100 + index}" for index in range(10))
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if request.url.path.endswith("/W1"):
            return _json_response(request, _identity(action.seed, refs=ids))
        count = int(request.url.params["per_page"])
        prefix = 1000 if "search" in request.url.params else 100
        return _json_response(
            request,
            {
                "results": [
                    _openalex_work(f"W{prefix + index}", doi=None, title=f"Paper {index}")
                    for index in range(count)
                ],
                "meta": {"cost_usd": "0.001"},
            },
        )

    adapter, client = _adapter(handler)
    try:
        if first == "text":
            assert len(_text_search(path, 1, handler, requested_depth=20)) == 20
        graph = expansion.execute_expansion(
            path=str(path), action=action, adapter=adapter, clock=_clock
        )
        assert len(graph) == (5 if first == "text" else 10)
        if first == "graph":
            assert len(_text_search(path, 1, handler, requested_depth=20)) == 15
        assert retention_headroom(str(path), RUN, 2) == 0
        assert _text_search(path, 2, handler) == ()
        assert (
            expansion.execute_expansion(path=str(path), action=action, adapter=None, clock=_clock)
            == graph
        )
    finally:
        client.close()
    assert len(sends) == 3


@pytest.mark.parametrize("later_round", (3, 4))
def test_previously_expanded_seed_can_use_another_relation_in_an_allowed_round(
    tmp_path: Path, later_round: int
) -> None:
    path = tmp_path / "later-round.sqlite"
    _binding(path, seed_identity="source-seed-expansion-v3")
    _install_round_one(path, ({"score": 90},))
    first = _slot(_manual_action(path), "first-six", requested_depth=6)
    if later_round == 4:
        _authorize_round_four(path)
    second = _slot(
        _manual_action(path, later_round, "related"), "later-relation", requested_depth=10
    )
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if request.url.path.endswith("/W1"):
            return _json_response(
                request,
                _identity(
                    first.seed,
                    refs=tuple(f"W{100 + index}" for index in range(6)),
                    related=tuple(f"W{200 + index}" for index in range(10)),
                ),
            )
        ids = request.url.params["filter"].split(":", 1)[1].split("|")
        return _json_response(
            request,
            {"results": [_openalex_work(wid, doi=f"10.5555/{wid}", title=wid) for wid in ids]},
        )

    adapter, client = _adapter(handler)
    try:
        assert (
            len(
                expansion.execute_expansion(
                    path=str(path), action=first, adapter=adapter, clock=_clock
                )
            )
            == 6
        )
        assert (
            len(
                expansion.execute_expansion(
                    path=str(path), action=second, adapter=adapter, clock=_clock
                )
            )
            == 4
        )
        assert expansion.offer_expansions(str(path), RUN, later_round, (_lane(),), _clock) == ()
        exhausted = _manual_action(path, later_round, "citing")
        assert (
            expansion.execute_expansion(
                path=str(path), action=exhausted, adapter=adapter, clock=_clock
            )
            == ()
        )
    finally:
        client.close()
    assert len(sends) == 3
    assert sends[-1].url.params["per_page"] == "4"
    assert expansion.offer_expansions(str(path), RUN, 5, (_lane(),), _clock) == ()


@pytest.mark.parametrize("round_number", (2, 3, 4))
def test_exhausted_graph_capacity_does_not_fail_the_round_caller(
    tmp_path: Path, round_number: int
) -> None:
    path = tmp_path / "round-caller.sqlite"
    _binding(path, max_requests=1, seed_identity="source-seed-expansion-v3")
    _install_round_one(path, ({"score": 90},))
    _manual_action(path)  # Establish the eligible seed pool from completed Round 1.
    if round_number == 4:
        _authorize_round_four(path)
    action = _manual_action(path, round_number)
    policy_identity = (
        "researchassistant-v2-post-phase-13-round-four-v1"
        if round_number == 4
        else "researchassistant-v2-phase-7-adaptive-search-v1"
    )
    query = V2AdaptiveSearchQuery(
        run_id=RUN,
        query_id=action.artifact_id,
        round_number=round_number,
        provider=action.provider,
        direction=action.direction,
        targeted_gap_ids=action.target_gap_ids,
        strategy="Bounded graph slot",
        query_text=None,
        graph_action=action,
        policy_identity=policy_identity,
        created_at=NOW,
    )
    plan = V2AdaptiveRoundPlan(
        run_id=RUN,
        round_number=round_number,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        enabled_providers=(action.provider,),
        targeted_gap_ids=action.target_gap_ids,
        discovered_terms=(),
        search_agent_prompt_version="offline-limit-probe-v1",
        policy_identity=policy_identity,
        searches=(query,),
        planned_at=NOW,
    )
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        return _json_response(request, _identity(action.seed))

    adapter, client = _adapter(handler)
    try:
        result = _execute_searches(
            str(path),
            plan,
            {action.provider: SimpleNamespace(neighborhood_adapter=adapter)},
            None,
            _clock,
        )
    finally:
        client.close()
    assert len(sends) == 1
    assert result.outcomes[0].succeeded
    assert result.outcomes[0].results == ()


def test_historical_binding_dispatch_and_incompatible_resume_are_preserved(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "historical-binding.sqlite"
    _binding(path)
    binding = read_discovery_binding(str(path), RUN)
    original = binding.model_dump_json()
    with pytest.raises(sqlite3.IntegrityError, match="replay conflicts"):
        bind_discovery_run(
            str(path), binding.model_copy(update={"seed_identity": "source-seed-expansion-v3"}), NOW
        )
    assert read_discovery_binding(str(path), RUN).model_dump_json() == original
    assert binding.seed_identity == "source-seed-expansion-v2"


@pytest.mark.parametrize("cost_known", (True, False))
def test_text_retries_cannot_escape_the_shared_ceiling(tmp_path: Path, cost_known: bool) -> None:
    path = tmp_path / "retry-ceiling.sqlite"
    _fresh_binding(path)
    _install_gap_analysis(path, 1)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if len(sends) <= 8:
            return _json_response(request, {"results": [], "meta": {"cost_usd": "0.001"}})
        body: dict[str, Any] = {"error": "temporary outage"}
        if cost_known:
            body["meta"] = {"cost_usd": "0.001"}
        return _json_response(request, body, status=503)

    for index in range(8):
        assert _text_search(path, index, handler) == ()
    with pytest.raises(SearchProviderError):
        _text_search(path, 8, handler)
    audit = provider_attempt_audit(str(path), RUN)
    assert len(sends) == len(audit.starts) == (10 if cost_known else 9)
    assert sum(start.reserved_cost_usd for start in audit.starts) == (
        Decimal("0.01") if cost_known else Decimal("0.009")
    )
    assert available_query_budgets(str(path), RUN) == ()


@pytest.mark.parametrize("outcome", ("timeout", "rate_limit"))
def test_graph_failed_or_unknown_request_is_never_reissued(tmp_path: Path, outcome: str) -> None:
    path = tmp_path / "failed-graph.sqlite"
    _binding(path, seed_identity="source-seed-expansion-v3")
    _install_round_one(path, ({"score": 90},))
    first = _manual_action(path)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout("unknown after physical start", request=request)
        return _json_response(
            request, {"error": "rate limit", "meta": {"cost_usd": "0.001"}}, status=429
        )

    adapter, client = _adapter(handler)
    try:
        for _ in range(2):
            assert (
                expansion.execute_expansion(
                    path=str(path), action=first, adapter=adapter, clock=_clock
                )
                == ()
            )
        assert expansion.offer_expansions(str(path), RUN, 3, (_lane(),), _clock) == ()
        if outcome == "timeout":
            second = _manual_action(path, 3, "related")
            assert (
                expansion.execute_expansion(
                    path=str(path), action=second, adapter=adapter, clock=_clock
                )
                == ()
            )
    finally:
        client.close()
    audit = provider_attempt_audit(str(path), RUN)
    assert len(sends) == len(audit.starts) == 1
    assert audit.starts[0].reserved_cost_usd == Decimal("0.001")
    assert bool(audit.interrupted_unknown) == (outcome == "timeout")


def test_default_three_hundred_record_round_retention_includes_graph_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "default-retention.sqlite"
    binding = _fresh_binding(
        path,
        V2MetadataDiscoveryPolicy(metadata_depth=50),
        providers=(
            DiscoveryProvider.OPENALEX,
            DiscoveryProvider.ARXIV,
            DiscoveryProvider.SERPSEARCH,
        ),
        query_modes={DiscoveryProvider.OPENALEX: "semantic"},
    )
    _install_round_one(path, ({"score": 90},))
    action = _slot(_manual_action(path), "default-retention", requested_depth=10)
    calls: list[DiscoveryProvider] = []

    def graph_handler(request: httpx.Request) -> httpx.Response:
        calls.append(DiscoveryProvider.OPENALEX)
        ids = tuple(f"W{100 + index}" for index in range(10))
        return _json_response(
            request,
            _identity(action.seed, refs=ids)
            if request.url.path.endswith("/W1")
            else {"results": [_openalex_work(wid, doi=None, title=wid) for wid in ids]},
        )

    adapter, client = _adapter(graph_handler)
    try:
        assert (
            len(
                expansion.execute_expansion(
                    path=str(path), action=action, adapter=adapter, clock=_clock
                )
            )
            == 10
        )
    finally:
        client.close()

    class FakeMetadataTransport:
        def search(self, request: SearchRequest) -> SearchResponse:
            calls.append(request.provider)
            return SearchResponse(
                provider_name=request.provider.value,
                results=[
                    SearchResult(
                        original_url=f"https://fixture.example/{len(calls)}/{index}",
                        title=f"Offline paper {index}",
                        rank=index + 1,
                    )
                    for index in range(request.limit)
                ],
            )

    providers = dict.fromkeys(binding.providers, FakeMetadataTransport())
    schedule = (
        *((DiscoveryProvider.OPENALEX, 50) for _ in range(2)),
        *((DiscoveryProvider.ARXIV, 20) for _ in range(6)),
        *((DiscoveryProvider.SERPSEARCH, 10) for _ in range(7)),
        (DiscoveryProvider.OPENALEX, 50),
    )
    for index, (provider, depth) in enumerate(schedule):
        key = f"default-cap-{index}"
        conceptual = V2ConceptualQuery(
            run_id=RUN,
            artifact_id=discovery_id(RUN, "V2ConceptualQuery", key),
            identity_key=key,
            provider=provider,
            direction=ResearchDirection.SUPPORT,
            round_number=2,
            target_gap_ids=("gap-outcome",),
            purpose="gap",
            required_concepts=(V2ConceptGroup(concept=f"outcome {index}"),),
        )
        compiled = compile_query(
            conceptual,
            requested_depth=depth,
            policy=binding.policy,
            mode="semantic" if provider is DiscoveryProvider.OPENALEX else None,
        )
        result = execute_query(
            path=str(path),
            run_id=RUN,
            provider=provider,
            query_text=compiled.query_text,
            compiled_query=compiled,
            providers=providers,
            clock=_clock,
        )
        assert len(result.results) == (0 if index == len(schedule) - 1 else depth)
    assert len(calls) == 17
    assert retention_headroom(str(path), RUN, 2) == 0
    assert retention_headroom(str(path), RUN, 3) == 300
    assert len(provider_attempt_audit(str(path), RUN).starts) == 17
