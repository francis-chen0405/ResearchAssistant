from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from providers.arxiv import ArxivSearchAdapter
from providers.config import ArxivConfig, ExaConfig, OpenAlexConfig, PubMedConfig, SerpSearchConfig
from providers.discovery_transport import RequestKind, observe_physical_requests
from providers.exa import ExaSearchAdapter
from providers.openalex import OpenAlexSearchAdapter
from providers.pubmed import PubMedSearchAdapter
from providers.search import (
    SearchFailureCode,
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
)
from providers.serpsearch import SerpSearchAdapter
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SearchIntent
from researchassistant.contracts.model_research import ResearchDirection
from researchassistant.research.query_compiler import compile_query


class _RecordingObserver:
    def request(
        self,
        request: SearchRequest,
        parameters: Mapping[str, str | int | bool],
        send: Callable[[], httpx.Response],
        *,
        request_kind: RequestKind = "primary",
        before_reservation: Callable[[Callable[[], bool] | None], None] | None = None,
    ) -> httpx.Response:
        if before_reservation is not None:
            before_reservation(None)
        return send()


def _search_observed(adapter: SearchProvider, request: SearchRequest) -> SearchResponse:
    with observe_physical_requests(_RecordingObserver()):
        return adapter.search(request)


def _action(provider: DiscoveryProvider, *, mode: str | None = None) -> V2CompiledQueryAction:
    run_id = uuid4()
    query = V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", "test-query"),
        identity_key="test-query",
        required_concepts=(V2ConceptGroup(concept="café study"),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=provider,
        round_number=1,
    )
    return compile_query(query, mode=mode, requested_depth=4)


def _request(action: V2CompiledQueryAction, *, semantic: bool = False) -> SearchRequest:
    return SearchRequest(
        run_id=action.run_id,
        provider=action.conceptual_query.provider,
        intent=SearchIntent.ACADEMIC_STUDY,
        semantic=semantic,
        query_text=action.query_text,
        limit=action.effective_depth,
        compiled_query=action,
    )


def test_openalex_compiled_semantic_parameters_use_native_mode_and_cap() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "meta": {"cost_usd": 0.001},
                "results": [
                    {"id": "https://openalex.org/W1", "title": "A study", "is_retracted": False}
                ],
            },
        )

    action = _action(DiscoveryProvider.OPENALEX, mode="semantic")
    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="key"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )

    response = _search_observed(adapter, _request(action, semantic=True))

    params = seen[0].url.params
    assert params["search.semantic"] == action.query_text
    assert params["per_page"] == str(action.effective_depth)
    assert "search" not in params
    assert response.cost_usd == Decimal("0.001")


def test_arxiv_compiled_fielded_query_is_sent_without_added_all_prefix() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            text=(
                '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                "<id>https://arxiv.org/abs/2401.00001</id><title>Study</title>"
                "</entry></feed>"
            ),
        )

    action = _action(DiscoveryProvider.ARXIV)
    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
        ),
    )

    _search_observed(adapter, _request(action))

    params = seen[0].url.params
    assert params["search_query"] == action.query_text
    assert params["search_query"].startswith("(")
    assert "ti:" in params["search_query"]
    assert "abs:" in params["search_query"]
    assert "all:" not in params["search_query"]
    assert "all:all:" not in params["search_query"]
    assert params["max_results"] == str(action.effective_depth)
    assert params["sortBy"] == "relevance"
    assert params["sortOrder"] == "descending"


def test_pubmed_compiled_title_abstract_expression_is_sent_to_esearch() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})
        return httpx.Response(200, json={"result": {"uids": ["123"], "123": {"title": "Study"}}})

    action = _action(DiscoveryProvider.PUBMED)
    adapter = PubMedSearchAdapter(
        PubMedConfig(),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov", transport=httpx.MockTransport(handler)
        ),
    )

    _search_observed(adapter, _request(action))

    params = seen[0].url.params
    assert params["term"] == action.query_text
    assert "[tiab]" in params["term"].lower() or "[title/abstract]" in params["term"].lower()
    assert params["retmax"] == str(action.effective_depth)
    assert params["sort"] == "relevance"
    assert len(seen) == 2


def test_exa_compiled_query_keeps_natural_text_and_auto_mode() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.org/result", "title": "Study"}],
                "costDollars": {"total": "0.001"},
            },
        )

    action = _action(DiscoveryProvider.EXA)
    adapter = ExaSearchAdapter(
        ExaConfig(api_key="key"),
        client=httpx.Client(base_url="https://api.exa.ai", transport=httpx.MockTransport(handler)),
    )

    _search_observed(adapter, _request(action))

    payload = json.loads(seen[0].content)
    assert payload == {"query": action.query_text, "type": "auto", "numResults": 4}


def test_serpsearch_compiled_query_preserves_quotes_unicode_and_operator_mode() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"organic_results": [{"url": "https://example.org/result", "title": "Study"}]},
        )

    action = _action(DiscoveryProvider.SERPSEARCH)
    adapter = SerpSearchAdapter(
        SerpSearchConfig(api_key="key"),
        client=httpx.Client(
            base_url="https://api.serpsearch.com", transport=httpx.MockTransport(handler)
        ),
    )

    _search_observed(adapter, _request(action))

    assert len(seen) == 1
    params = seen[0].url.params
    assert params["query"] == action.query_text
    assert params["query"] == '"café study"'
    assert params["page"] == "1"
    assert params["exact_match"] == "true"


@pytest.mark.parametrize(
    "provider",
    (
        DiscoveryProvider.OPENALEX,
        DiscoveryProvider.ARXIV,
        DiscoveryProvider.PUBMED,
        DiscoveryProvider.EXA,
        DiscoveryProvider.SERPSEARCH,
    ),
)
def test_compiled_provider_adapters_fail_closed_without_execution_owner(
    provider: DiscoveryProvider,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    adapter = {
        DiscoveryProvider.OPENALEX: OpenAlexSearchAdapter(
            OpenAlexConfig(api_key="key", base_url="https://api.openalex.org"),
            client=httpx.Client(
                base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
            ),
        ),
        DiscoveryProvider.ARXIV: ArxivSearchAdapter(
            ArxivConfig(base_url="https://export.arxiv.org"),
            client=httpx.Client(
                base_url="https://export.arxiv.org", transport=httpx.MockTransport(handler)
            ),
        ),
        DiscoveryProvider.PUBMED: PubMedSearchAdapter(
            PubMedConfig(base_url="https://eutils.ncbi.nlm.nih.gov"),
            client=httpx.Client(
                base_url="https://eutils.ncbi.nlm.nih.gov", transport=httpx.MockTransport(handler)
            ),
        ),
        DiscoveryProvider.EXA: ExaSearchAdapter(
            ExaConfig(api_key="key"),
            client=httpx.Client(
                base_url="https://api.exa.ai", transport=httpx.MockTransport(handler)
            ),
        ),
        DiscoveryProvider.SERPSEARCH: SerpSearchAdapter(
            SerpSearchConfig(api_key="key"),
            client=httpx.Client(
                base_url="https://api.serpsearch.com", transport=httpx.MockTransport(handler)
            ),
        ),
    }[provider]
    request = _request(
        _action(provider, mode="semantic" if provider is DiscoveryProvider.OPENALEX else None),
        semantic=provider is DiscoveryProvider.OPENALEX,
    )

    with pytest.raises(SearchProviderError) as exc_info:
        adapter.search(request)

    assert exc_info.value.code is SearchFailureCode.PERMANENT_FAILURE
    assert "durable query execution owner" in str(exc_info.value)
    assert seen == []


def test_compiled_provider_rejects_an_action_for_a_different_request() -> None:
    action = _action(DiscoveryProvider.ARXIV)
    with pytest.raises(ValidationError, match="provider"):
        SearchRequest(
            run_id=action.run_id,
            provider=DiscoveryProvider.PUBMED,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text=action.query_text,
            limit=action.effective_depth,
            compiled_query=action,
        )


def test_compiled_mode_cannot_be_overridden_by_legacy_semantic_flag() -> None:
    action = _action(DiscoveryProvider.EXA)
    with pytest.raises(ValidationError, match="semantic search"):
        SearchRequest(
            run_id=action.run_id,
            provider=DiscoveryProvider.EXA,
            intent=SearchIntent.BROAD_WEB,
            semantic=True,
            query_text=action.query_text,
            limit=action.effective_depth,
            compiled_query=action,
        )
