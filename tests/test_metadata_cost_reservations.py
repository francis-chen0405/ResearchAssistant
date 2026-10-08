from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_discovery_store import _init_run
from test_query_execution import CLAIM, DIRECTIONS, _action, _clock

from providers.config import ExaConfig
from providers.exa import ExaSearchAdapter
from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import (
    available_query_budgets,
    execute_query,
    freeze_query_execution,
    query_provider_budgets,
)
from researchassistant.storage.discovery_store import provider_attempt_audit


@pytest.mark.parametrize(
    ("depth", "effective", "reservation", "actual"),
    [(20, 20, Decimal("0.02"), "0.017"), (50, 25, Decimal("0.03"), "0.022")],
)
def test_exa_deeper_counts_reserve_documented_cost_without_widening_total(
    tmp_path: Path, depth: int, effective: int, reservation: Decimal, actual: str
) -> None:
    path = tmp_path / "metadata-cost.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    policy = V2MetadataDiscoveryPolicy(metadata_depth=depth)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "costDollars": {"total": actual},
                "results": [
                    {"url": f"https://papers.example/{index}", "title": f"Paper {index}"}
                    for index in range(effective)
                ],
            },
        )

    adapter = ExaSearchAdapter(
        ExaConfig(api_key="offline-fixture-key"),
        client=httpx.Client(base_url="https://api.exa.ai", transport=httpx.MockTransport(handler)),
    )
    configured = query_provider_budgets(
        (DiscoveryProvider.EXA,), {DiscoveryProvider.EXA: adapter}, None, discovery_policy=policy
    )
    binding = freeze_query_execution(
        str(path),
        run_id,
        CLAIM,
        DIRECTIONS,
        (DiscoveryProvider.EXA,),
        _clock(),
        provider_budgets=configured,
        discovery_policy=policy,
    )
    budget = binding.provider_budgets[0]
    assert budget.reservation_per_request_usd == reservation
    assert (budget.max_requests, budget.max_cost_usd) == (18, Decimal("0.18"))
    assert available_query_budgets(str(path), run_id)[0].remaining_calls == int(
        Decimal("0.18") / reservation
    )
    action = compile_query(
        _action(run_id, DiscoveryProvider.EXA).conceptual_query,
        requested_depth=depth,
        policy=policy,
    )
    assert action.effective_depth == effective
    response = execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.EXA,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.EXA: adapter},
        clock=_clock(),
    )
    assert len(response.results) == effective
    assert len(seen) == 1
    audit = provider_attempt_audit(str(path), run_id)
    assert audit.starts[0].reserved_cost_usd == reservation
    assert audit.completions[0].actual_cost_usd == Decimal(actual)
