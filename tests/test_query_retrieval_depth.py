from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from test_discovery_store import _init_run
from test_query_execution import CLAIM, DIRECTIONS, _action, _clock, _freeze

from providers.config import SerpSearchConfig
from providers.search import SearchFailureCode, SearchProviderError, SearchResponse
from providers.serpsearch import SerpSearchAdapter
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2DiscoveryProviderBudget,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.query_retrieval import V2QueryRetrievalResult
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import execute_query, freeze_query_execution
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.query_retrieval_store import read_pages
from researchassistant.storage.store import read_v2_artifact


def _deep_action(run_id: UUID) -> V2CompiledQueryAction:
    shallow = _action(run_id, DiscoveryProvider.SERPSEARCH)
    return compile_query(shallow.conceptual_query, requested_depth=20)


def _serp_adapter(handler: Callable[[httpx.Request], httpx.Response]) -> SerpSearchAdapter:
    return SerpSearchAdapter(
        SerpSearchConfig(api_key="offline-fixture-key"),
        client=httpx.Client(
            base_url="https://api.serpsearch.com",
            transport=httpx.MockTransport(handler),
        ),
    )


def _body(start: int = 1, count: int = 10, *, rank_start: int | None = None) -> dict[str, object]:
    first_rank = 1 if rank_start is None else rank_start
    return {
        "organic_results": [
            {
                "url": f"https://papers.example/{index}",
                "title": f"Research paper {index}",
                "position": first_rank + index - start,
                "description": "Offline metadata fixture",
            }
            for index in range(start, start + count)
        ]
    }


def _execute(
    path: Path,
    run_id: UUID,
    action: V2CompiledQueryAction,
    adapter: SerpSearchAdapter,
    *,
    cancellation_requested: Callable[[], bool] | None = None,
) -> SearchResponse:
    return execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.SERPSEARCH,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.SERPSEARCH: adapter},
        clock=_clock(),
        cancellation_requested=cancellation_requested,
    )


def _retrieval(path: Path, run_id: UUID, action: V2CompiledQueryAction) -> V2QueryRetrievalResult:
    artifact = read_v2_artifact(
        str(path), run_id, f"metadata-retrieval-v2:{action.artifact_id}:result"
    )
    return V2QueryRetrievalResult.model_validate_json(artifact.payload_json)


def test_serp_depth_fetches_two_pages_deduplicates_and_accounts_every_page(
    tmp_path: Path,
) -> None:
    path = tmp_path / "serp-two-pages.sqlite"
    run_id, binding = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _deep_action(run_id)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params["page"])
        body = _body(1, 10) if page == 1 else _body(11, 10)
        if page == 2:
            # The first page-two hit repeats page one's final record.
            body["organic_results"][0]["url"] = "https://papers.example/10"  # type: ignore[index]
        return httpx.Response(200, json=body)

    response = _execute(path, run_id, action, _serp_adapter(handler))

    assert [request.url.params["page"] for request in seen] == ["1", "2"]
    assert len(response.results) == 19
    result = _retrieval(path, run_id, action)
    assert (result.requested_depth, result.effective_depth) == (20, 20)
    assert (result.raw_hits, result.retained_records, result.page_count) == (20, 19, 2)
    assert result.stopping_reason == "depth_reached"
    assert len(read_pages(str(path), run_id)) == 2
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == len(audit.completions) == 2
    assert all(
        start.reserved_cost_usd == binding.provider_budgets[0].reservation_per_request_usd
        for start in audit.starts
    )


def test_empty_second_page_stops_early_without_losing_first_page(tmp_path: Path) -> None:
    path = tmp_path / "serp-empty-second.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _deep_action(run_id)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(page)
        return httpx.Response(200, json=_body() if page == 1 else {"organic_results": []})

    response = _execute(path, run_id, action, _serp_adapter(handler))

    assert seen == [1, 2]
    assert len(response.results) == 10
    result = _retrieval(path, run_id, action)
    assert result.stopping_reason == "empty_page"
    assert (result.raw_hits, result.retained_records, result.page_count) == (10, 10, 2)


def test_repeated_page_results_stop_without_duplicate_retained_records(tmp_path: Path) -> None:
    path = tmp_path / "serp-repeated-page.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _deep_action(run_id)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(page)
        # SERP's position field is local to each physical page.
        return httpx.Response(200, json=_body(1, 10, rank_start=1))

    response = _execute(path, run_id, action, _serp_adapter(handler))

    assert seen == [1, 2]
    assert len(response.results) == 10
    result = _retrieval(path, run_id, action)
    assert result.stopping_reason == "no_new_results"
    assert (result.raw_hits, result.retained_records) == (20, 10)


def test_malformed_second_page_preserves_first_page_and_is_cached(tmp_path: Path) -> None:
    path = tmp_path / "serp-malformed-second.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _deep_action(run_id)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(page)
        return (
            httpx.Response(200, json=_body()) if page == 1 else httpx.Response(200, text="not json")
        )

    adapter = _serp_adapter(handler)
    first = _execute(path, run_id, action, adapter)
    replay = _execute(path, run_id, action, adapter)

    assert seen == [1, 2]
    assert len(first.results) == len(replay.results) == 10
    result = _retrieval(path, run_id, action)
    assert result.stopping_reason == "malformed_page"
    assert result.response.degraded_pool
    assert len(read_pages(str(path), run_id)) == 1


def test_cancellation_before_second_page_resumes_from_completed_checkpoint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "serp-cancel-resume.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _deep_action(run_id)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(page)
        return httpx.Response(200, json=_body(1, 10) if page == 1 else _body(11, 10))

    checks = 0

    def cancel_before_page_two() -> bool:
        nonlocal checks
        checks += 1
        return checks == 3

    adapter = _serp_adapter(handler)
    with pytest.raises(SearchProviderError) as cancelled:
        _execute(path, run_id, action, adapter, cancellation_requested=cancel_before_page_two)
    assert cancelled.value.code is SearchFailureCode.CANCELLED
    assert seen == [1]
    assert len(read_pages(str(path), run_id)) == 1

    response = _execute(path, run_id, action, adapter)

    assert seen == [1, 2]
    assert len(response.results) == 20
    assert len(provider_attempt_audit(str(path), run_id).starts) == 2


def test_unknown_second_page_keeps_completed_page_and_cannot_replay_transport(
    tmp_path: Path,
) -> None:
    path = tmp_path / "serp-unknown-resume.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    action = _deep_action(run_id)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(page)
        if page == 2:
            raise httpx.ReadTimeout("fixture timeout after request start")
        return httpx.Response(200, json=_body())

    adapter = _serp_adapter(handler)
    response = _execute(path, run_id, action, adapter)
    replay = _execute(path, run_id, action, adapter)

    assert seen == [1, 2]
    assert len(response.results) == len(replay.results) == 10
    result = _retrieval(path, run_id, action)
    assert result.stopping_reason == "unknown_outcome"
    assert result.response.degraded_pool
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == len(audit.completions) == 2
    assert audit.completions[0].status == "completed"
    assert audit.completions[1].status == "interrupted_unknown"
    assert audit.completions[1].actual_cost_usd is None


def test_one_request_budget_limits_retrieval_depth_and_preserves_first_page(
    tmp_path: Path,
) -> None:
    path = tmp_path / "serp-one-request-budget.sqlite"
    run_id = UUID("45d0ece0-3f0b-4ac0-a24d-18d30e4c90f4")
    _init_run(path, run_id)
    budget = V2DiscoveryProviderBudget(
        provider=DiscoveryProvider.SERPSEARCH,
        max_requests=1,
        max_cost_usd=Decimal("0.01"),
        cost_policy_identity="query-serpsearch-lexical-2026-10-06-v2",
        reservation_per_request_usd=Decimal("0.01"),
        cost_basis="configured_upper_bound",
    )
    freeze_query_execution(
        str(path),
        run_id,
        CLAIM,
        DIRECTIONS,
        (DiscoveryProvider.SERPSEARCH,),
        _clock(),
        provider_budgets=(budget,),
    )
    action = _deep_action(run_id)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(int(request.url.params["page"]))
        return httpx.Response(200, json=_body())

    response = _execute(path, run_id, action, _serp_adapter(handler))

    assert seen == [1]
    assert len(response.results) == 10
    result = _retrieval(path, run_id, action)
    assert result.effective_depth == 10
    assert result.stopping_reason == "provider_budget"
    assert len(provider_attempt_audit(str(path), run_id).starts) == 1
