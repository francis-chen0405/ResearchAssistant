from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from test_discovery_store import _init_run
from test_query_execution import CLAIM, DIRECTIONS, _action, _clock
from test_query_retrieval_depth import _body, _retrieval, _serp_adapter

from providers.arxiv import ArxivSearchAdapter
from providers.config import ArxivConfig, OpenAlexConfig, PubMedConfig, SerpSearchConfig
from providers.openalex import OpenAlexSearchAdapter
from providers.pubmed import PubMedSearchAdapter
from providers.serpsearch import SerpSearchAdapter
from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    ResearchDirection,
    V2RoundOneSearchQuery,
)
from researchassistant.research.discovery_capabilities import (
    get_neighborhood_capabilities,
    get_query_capabilities,
)
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import (
    fair_query_order,
    freeze_query_execution,
)
from researchassistant.research.v2_orchestrator import _run_round_one_search
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.query_dispatch import query_dispatch_states
from researchassistant.storage.query_retrieval_store import raw_hit_counts, read_pages


def _round_one_query(
    run_id: UUID,
    provider: DiscoveryProvider,
    term: str,
    policy: V2MetadataDiscoveryPolicy,
) -> V2RoundOneSearchQuery:
    shallow = _action(run_id, provider, term=term)
    compiled = compile_query(
        shallow.conceptual_query,
        requested_depth=policy.metadata_depth,
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
        metadata_depth=20,
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
        # Text compilation retains its frozen v3 identity; the fresh run also
        # declares separately versioned neighborhood transport for OpenAlex.
        assert query.compiled_query.capabilities == get_query_capabilities(query.provider)
        assert capability_by_provider[query.provider] == get_neighborhood_capabilities(
            query.provider
        )
        graph_fields = {
            "capability_identity",
            "executable_identity_lookup",
            "executable_relationships",
            "documentation_urls",
            "unsupported_features",
        }
        assert query.compiled_query.capabilities.model_dump(exclude=graph_fields) == (
            capability_by_provider[query.provider].model_dump(exclude=graph_fields)
        )

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


@pytest.mark.parametrize(
    ("first_provider", "headroom", "serp_empty"),
    [
        (DiscoveryProvider.OPENALEX, 20, False),
        (DiscoveryProvider.OPENALEX, 1, False),
        (DiscoveryProvider.OPENALEX, 20, True),
        (DiscoveryProvider.ARXIV, 20, True),
    ],
)
def test_first_pass_reserves_retention_and_resumes_at_the_next_rank(
    tmp_path: Path, first_provider: DiscoveryProvider, headroom: int, serp_empty: bool
) -> None:
    path = tmp_path / "first-pass-retention.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    policy = V2MetadataDiscoveryPolicy(
        metadata_depth=20,
        max_raw_per_round=headroom,
        max_raw_per_run=headroom,
        max_scout_per_round=headroom,
        max_acquisition_per_round=headroom,
    )
    enabled = (first_provider, DiscoveryProvider.SERPSEARCH)
    freeze_query_execution(
        str(path), run_id, CLAIM, DIRECTIONS, enabled, _clock(), discovery_policy=policy
    )
    planned = tuple(
        _round_one_query(run_id, provider, f"{provider.value} study", policy)
        for provider in enabled
    )
    trace: list[tuple[DiscoveryProvider, str, int]] = []
    initial_limit = max(1, headroom - 1)
    next_cursor = "bmV4dA"

    def scholarly(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if first_provider is DiscoveryProvider.OPENALEX:
            cursor = params["cursor"]
            count = int(params["per_page"])
            trace.append((first_provider, cursor, count))
            offset = 0 if cursor == "*" else initial_limit
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": f"https://openalex.org/W{index}", "title": f"Study {index}"}
                        for index in range(offset + 1, offset + count + 1)
                    ],
                    "meta": {
                        "cost_usd": "0.001",
                        "next_cursor": next_cursor if cursor == "*" else None,
                    },
                },
            )
        offset = int(params["start"])
        count = int(params["max_results"])
        trace.append((first_provider, str(offset), count))
        entries = "".join(
            f"<entry><id>https://arxiv.org/abs/2401.{index:05}</id>"
            f"<title>Study {index}</title></entry>"
            for index in range(offset + 1, offset + count + 1)
        )
        return httpx.Response(
            200, text=f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'
        )

    def web(request: httpx.Request) -> httpx.Response:
        trace.append((DiscoveryProvider.SERPSEARCH, request.url.params["page"], 10))
        return httpx.Response(200, json=_body(count=0 if serp_empty else 10))

    class Interrupted(BaseException):
        """Stop the worker after the first page's durable checkpoint."""

    def interrupt_after_page() -> bool:
        if trace:
            raise Interrupted
        return False

    base_url = (
        "https://api.openalex.org"
        if first_provider is DiscoveryProvider.OPENALEX
        else "https://export.arxiv.org"
    )
    with httpx.Client(base_url=base_url, transport=httpx.MockTransport(scholarly)) as client:
        adapter = (
            OpenAlexSearchAdapter(OpenAlexConfig(api_key="offline-openalex-key"), client=client)
            if first_provider is DiscoveryProvider.OPENALEX
            else ArxivSearchAdapter(
                ArxivConfig(), client=client, monotonic=lambda: 3.0 * len(trace)
            )
        )
        providers = {first_provider: adapter, DiscoveryProvider.SERPSEARCH: _serp_adapter(web)}
        if serp_empty:
            with pytest.raises(Interrupted):
                _run_round_one_search(str(path), planned, providers, interrupt_after_page, _clock())
            (saved_page,) = read_pages(path, run_id)
            assert saved_page.requested_records == initial_limit
        result = _run_round_one_search(str(path), planned, providers, None, _clock())

    expected_trace = [
        (
            first_provider,
            "*" if first_provider is DiscoveryProvider.OPENALEX else "0",
            initial_limit,
        )
    ]
    if headroom > 1:
        expected_trace.append((DiscoveryProvider.SERPSEARCH, "1", 10))
    if serp_empty:
        next_position = next_cursor if first_provider is DiscoveryProvider.OPENALEX else "19"
        expected_trace.append((first_provider, next_position, 1))
        assert saved_page in read_pages(path, run_id)
    assert trace == expected_trace
    assert [hit.rank for hit in result.outcomes[0].results] == list(
        range(1, (20 if serp_empty else initial_limit) + 1)
    )
    assert len(result.outcomes[1].results) == (1 if headroom > 1 and not serp_empty else 0)
    pages = read_pages(path, run_id)
    assert sum(len(page.response.results) for page in pages) == headroom
    audit = provider_attempt_audit(path, run_id)
    assert len(audit.starts) == len(trace) and not audit.interrupted_unknown
    assert _run_round_one_search(str(path), planned, {}, None, _clock()) == result


def test_clipped_serp_page_stops_before_skipping_omitted_ranks(tmp_path: Path) -> None:
    path = tmp_path / "clipped-serp.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    enabled = (DiscoveryProvider.SERPSEARCH, DiscoveryProvider.OPENALEX, DiscoveryProvider.ARXIV)
    policy = V2MetadataDiscoveryPolicy(
        metadata_depth=20,
        max_raw_per_round=11,
        max_raw_per_run=11,
        max_scout_per_round=11,
        max_acquisition_per_round=11,
    )
    freeze_query_execution(
        str(path), run_id, CLAIM, DIRECTIONS, enabled, _clock(), discovery_policy=policy
    )
    planned = tuple(
        _round_one_query(run_id, provider, f"{provider.value} study", policy)
        for provider in enabled
    )
    trace: list[str] = []

    def web(request: httpx.Request) -> httpx.Response:
        trace.append(f"serp-{request.url.params['page']}")
        return httpx.Response(200, json=_body())

    def scholarly(request: httpx.Request) -> httpx.Response:
        trace.append("openalex")
        assert request.url.params["per_page"] == "1"
        return httpx.Response(200, json={"results": []})

    def preprints(request: httpx.Request) -> httpx.Response:
        trace.append("arxiv")
        assert request.url.params["max_results"] == "2"
        return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom"/>')

    with (
        httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(scholarly)
        ) as openalex,
        httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(preprints)
        ) as arxiv,
    ):
        result = _run_round_one_search(
            str(path),
            planned,
            {
                DiscoveryProvider.SERPSEARCH: _serp_adapter(web),
                DiscoveryProvider.OPENALEX: OpenAlexSearchAdapter(
                    OpenAlexConfig(api_key="offline-openalex-key"), client=openalex
                ),
                DiscoveryProvider.ARXIV: ArxivSearchAdapter(ArxivConfig(), client=arxiv),
            },
            None,
            _clock(),
        )

    assert trace == ["serp-1", "openalex", "arxiv"]
    assert [item.rank for item in result.outcomes[0].results] == list(range(1, 10))
    action = planned[0].compiled_query
    assert action is not None
    receipt = _retrieval(path, run_id, action)
    assert receipt.stopping_reason == "retention_cap"
    assert receipt.raw_hits == 10
    assert receipt.retained_records == receipt.effective_depth == 9


@pytest.mark.parametrize("serp_end", ["empty", "connection", "partial", "unknown", "complete"])
def test_first_pass_completes_logical_pages_before_deeper_transport(
    tmp_path: Path, serp_end: str
) -> None:
    path = tmp_path / "first-pass.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    enabled = (
        DiscoveryProvider.SERPSEARCH,
        DiscoveryProvider.PUBMED,
        DiscoveryProvider.OPENALEX,
    )
    policy = V2MetadataDiscoveryPolicy(metadata_depth=50)
    freeze_query_execution(
        str(path), run_id, CLAIM, DIRECTIONS, enabled, _clock(), discovery_policy=policy
    )
    serp, pubmed, openalex = (
        _round_one_query(run_id, provider, f"{provider.value} study", policy)
        for provider in enabled
    )
    more_serp = _round_one_query(run_id, DiscoveryProvider.SERPSEARCH, "other web study", policy)
    planned = (serp, more_serp, pubmed, openalex)
    assert serp.compiled_query is not None
    assert pubmed.compiled_query is not None
    assert more_serp.compiled_query is not None
    trace: list[str] = []

    def web(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if request.url.params["query"] == more_serp.query_text:
            trace.append(f"other-serp-{page}")
            return httpx.Response(200, json=_body(100, 1))
        trace.append(f"serp-{page}")
        if serp_end == "empty":
            return httpx.Response(200, json={"organic_results": []})
        if serp_end == "connection":
            raise httpx.ConnectError("offline pre-dispatch failure")
        if page == 2 and serp_end == "partial":
            return httpx.Response(200, text="malformed metadata")
        if page == 3 and serp_end == "unknown":
            raise httpx.ReadTimeout("offline unknown after dispatch")
        return httpx.Response(200, json=_body(10 * (page - 1) + 1))

    def pubmed_metadata(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        trace.append(endpoint)
        if endpoint == "esearch.fcgi":
            if serp_end not in {"empty", "connection"}:
                pages = read_pages(path, run_id)
                assert [(page.operation_id, page.page_number) for page in pages] == [
                    (serp.compiled_query.artifact_id, 1)
                ]
                with pytest.raises(KeyError):
                    _retrieval(path, run_id, serp.compiled_query)
            return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})
        assert request.url.params["id"] == "123"
        return httpx.Response(
            200, json={"result": {"123": {"uid": "123", "title": "Health study"}}}
        )

    def scholarly(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params["cursor"]
        trace.append(f"openalex-{cursor}")
        if cursor == "page-2":
            return httpx.Response(200, json={"results": [], "meta": {"cost_usd": "0.001"}})
        assert cursor == "*"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"id": f"https://openalex.org/W{i}", "title": f"Study {i}"}
                    for i in range(1, 21)
                ],
                "meta": {"cost_usd": "0.001", "next_cursor": "page-2"},
            },
        )

    with (
        httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov",
            transport=httpx.MockTransport(pubmed_metadata),
        ) as pubmed_client,
        httpx.Client(
            base_url="https://api.openalex.org",
            transport=httpx.MockTransport(scholarly),
        ) as openalex_client,
    ):
        providers = {
            DiscoveryProvider.SERPSEARCH: _serp_adapter(web),
            DiscoveryProvider.PUBMED: PubMedSearchAdapter(
                PubMedConfig(), client=pubmed_client, monotonic=lambda: 3.0 * len(trace)
            ),
            DiscoveryProvider.OPENALEX: OpenAlexSearchAdapter(
                OpenAlexConfig(api_key="offline-openalex-key"),
                client=openalex_client,
            ),
        }
        result = _run_round_one_search(str(path), planned, providers, None, _clock())

    assert trace[:4] == ["serp-1", "esearch.fcgi", "esummary.fcgi", "openalex-*"]
    assert [outcome.query for outcome in result.outcomes] == [serp, pubmed, openalex, more_serp]
    assert [len(item.results) for item in result.outcomes] == [
        {"empty": 0, "connection": 0, "partial": 10, "unknown": 20, "complete": 30}[serp_end],
        1,
        20,
        0 if serp_end == "unknown" else 1,
    ]
    audit = provider_attempt_audit(path, run_id)
    assert len(audit.starts) == len(trace)
    primary, metadata = (
        s for s in audit.starts if s.operation_id == pubmed.compiled_query.artifact_id
    )
    assert (primary.request_kind, metadata.request_kind) == ("primary", "metadata")
    assert primary.page_number == metadata.page_number == 1
    assert metadata.parent_attempt_id == primary.artifact_id
    if serp_end == "unknown":
        assert trace[4:] == ["serp-2", "serp-3"]
        assert query_dispatch_states(path, run_id) == {
            serp.compiled_query.artifact_id: "unknown",
            more_serp.compiled_query.artifact_id: "blocked",
        }
        assert len(audit.interrupted_unknown) == 1
        unknown_id = audit.interrupted_unknown[0]
        for start, completion in zip(audit.starts, audit.completions, strict=True):
            if start.artifact_id == unknown_id:
                assert start.reserved_cost_usd > 0
                assert completion is not None and completion.actual_cost_usd is None
    else:
        assert trace[4:] == {
            "empty": [],
            "connection": [],
            "partial": ["serp-2"],
            "complete": ["serp-2", "serp-3"],
        }[serp_end] + ["openalex-page-2", "other-serp-1"]
        assert not audit.interrupted_unknown
    assert result.outcomes[0].succeeded == (serp_end != "connection")
    assert (
        _retrieval(path, run_id, serp.compiled_query).stopping_reason
        == {
            "empty": "empty_page",
            "connection": "provider_failure",
            "partial": "malformed_page",
            "unknown": "unknown_outcome",
            "complete": "provider_limit",
        }[serp_end]
    )
    assert _run_round_one_search(str(path), planned, {}, None, _clock()) == result


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
