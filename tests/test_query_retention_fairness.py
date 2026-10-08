from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import httpx
from test_discovery_store import _init_run
from test_query_execution import CLAIM, DIRECTIONS, _action, _clock

from providers.config import OpenAlexConfig, SerpSearchConfig
from providers.openalex import OpenAlexSearchAdapter
from providers.serpsearch import SerpSearchAdapter
from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    ResearchDirection,
    V2RoundOneSearchQuery,
)
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import (
    fair_query_order,
    freeze_query_execution,
)
from researchassistant.research.v2_orchestrator import _run_round_one_search
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.query_retrieval_store import raw_hit_counts


def _round_one_query(
    run_id: UUID,
    provider: DiscoveryProvider,
    term: str,
    policy: V2MetadataDiscoveryPolicy,
) -> V2RoundOneSearchQuery:
    shallow = _action(run_id, provider, term=term)
    compiled = compile_query(
        shallow.conceptual_query,
        requested_depth=10,
        policy=policy,
    )
    return V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        provider=provider,
        strategy=term,
        query_text=compiled.query_text,
        compiled_query=compiled,
        created_at=_clock()(),
    )


def test_initial_round_fair_order_preserves_sparse_provider_within_retention_cap(
    tmp_path: Path,
) -> None:
    path = tmp_path / "initial-query-retention-fairness.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    policy = V2MetadataDiscoveryPolicy(
        metadata_depth=10,
        max_raw_per_round=20,
        max_raw_per_run=20,
        max_scout_per_round=20,
        max_acquisition_per_round=20,
    )
    binding = freeze_query_execution(
        str(path),
        run_id,
        CLAIM,
        DIRECTIONS,
        (DiscoveryProvider.SERPSEARCH, DiscoveryProvider.OPENALEX),
        _clock(),
        discovery_policy=policy,
    )
    planned = (
        _round_one_query(run_id, DiscoveryProvider.SERPSEARCH, "common SERP strategy one", policy),
        _round_one_query(run_id, DiscoveryProvider.SERPSEARCH, "common SERP strategy two", policy),
        _round_one_query(run_id, DiscoveryProvider.OPENALEX, "scarce OpenAlex lane", policy),
    )
    original_order = tuple(query.query_id for query in planned)
    assert tuple(query.provider for query in fair_query_order(planned)) == (
        DiscoveryProvider.SERPSEARCH,
        DiscoveryProvider.OPENALEX,
        DiscoveryProvider.SERPSEARCH,
    )
    capability_by_provider = {item.provider: item for item in binding.capabilities}
    for query in planned:
        assert query.compiled_query is not None
        assert query.compiled_query.policy == binding.policy
        assert query.compiled_query.capabilities == capability_by_provider[query.provider]

    requests: list[DiscoveryProvider] = []

    def serp_handler(_: httpx.Request) -> httpx.Response:
        requests.append(DiscoveryProvider.SERPSEARCH)
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "url": f"https://serp.example/paper-{index}",
                        "title": f"Common web paper {index}",
                        "position": index,
                    }
                    for index in range(1, 11)
                ]
            },
        )

    def openalex_handler(_: httpx.Request) -> httpx.Response:
        requests.append(DiscoveryProvider.OPENALEX)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": f"https://openalex.org/W{index}",
                        "title": f"Scarce academic paper {index}",
                        "is_retracted": False,
                    }
                    for index in range(1, 11)
                ],
                "meta": {"cost_usd": "0.001", "next_cursor": None},
            },
        )

    providers = {
        DiscoveryProvider.SERPSEARCH: SerpSearchAdapter(
            SerpSearchConfig(api_key="offline-serp-key"),
            client=httpx.Client(
                base_url="https://api.serpsearch.com",
                transport=httpx.MockTransport(serp_handler),
            ),
        ),
        DiscoveryProvider.OPENALEX: OpenAlexSearchAdapter(
            OpenAlexConfig(api_key="offline-openalex-key"),
            client=httpx.Client(
                base_url="https://api.openalex.org",
                transport=httpx.MockTransport(openalex_handler),
            ),
        ),
    }

    result = _run_round_one_search(str(path), planned, providers, None, _clock())

    assert tuple(query.query_id for query in planned) == original_order
    assert requests == [DiscoveryProvider.SERPSEARCH, DiscoveryProvider.OPENALEX]
    assert tuple(outcome.query.query_id for outcome in result.outcomes) == tuple(
        query.query_id for query in fair_query_order(planned)
    )
    assert [len(outcome.results) for outcome in result.outcomes] == [10, 10, 0]
    assert raw_hit_counts(str(path), run_id) == {1: 20}
    audit = provider_attempt_audit(str(path), run_id)
    assert len(audit.starts) == 2
    assert {start.provider for start in audit.starts} == {
        DiscoveryProvider.SERPSEARCH,
        DiscoveryProvider.OPENALEX,
    }
    assert all(completion is not None for completion in audit.completions)


def test_historical_compiled_none_queries_keep_their_original_order() -> None:
    run_id = uuid4()
    policy = V2MetadataDiscoveryPolicy(metadata_depth=10)
    planned = (
        _round_one_query(run_id, DiscoveryProvider.SERPSEARCH, "serp one", policy),
        _round_one_query(run_id, DiscoveryProvider.SERPSEARCH, "serp two", policy),
        _round_one_query(run_id, DiscoveryProvider.OPENALEX, "openalex", policy),
    )
    historical = tuple(query.model_copy(update={"compiled_query": None}) for query in planned)

    assert fair_query_order(historical) == historical
