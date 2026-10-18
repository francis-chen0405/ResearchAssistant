"""Malformed optional metadata must not discard usable scholarly records."""

from __future__ import annotations

from uuid import uuid4
from xml.sax.saxutils import escape

import httpx
import pytest
from pydantic import SecretStr

from researchassistant.contracts.models import DiscoveryProvider, SearchIntent
from researchassistant.contracts.search import SearchFailureCode, SearchRequest
from researchassistant.providers.arxiv import ArxivSearchAdapter
from researchassistant.providers.config import ArxivConfig, OpenAlexConfig
from researchassistant.providers.openalex import OpenAlexSearchAdapter
from researchassistant.providers.search import SearchProviderError

BAD_URLS = ("http://[", "https://papers.example:invalid/paper", "https://papers.example:0/")


def _request(provider: DiscoveryProvider) -> SearchRequest:
    return SearchRequest(
        run_id=uuid4(),
        provider=provider,
        intent=SearchIntent.ACADEMIC_STUDY,
        query_text="generated scholarly query",
        limit=2,
    )


@pytest.mark.parametrize("bad_url", BAD_URLS)
@pytest.mark.parametrize("field", ("primary", "alternate", "pdf"))
def test_openalex_retains_valid_urls_and_neighboring_records(bad_url: str, field: str) -> None:
    primary = "https://papers.example/primary"
    alternate = "https://papers.example/alternate"
    first: dict[str, object] = {
        "id": "https://openalex.org/W1",
        "title": "Generated first study",
        "primary_location": {
            "landing_page_url": bad_url if field == "primary" else primary,
            "pdf_url": bad_url if field == "pdf" else None,
        },
        "best_oa_location": {
            "landing_page_url": bad_url if field == "alternate" else alternate,
            "pdf_url": "https://papers.example/valid.pdf",
        },
    }
    body = {
        "results": [
            first,
            {"title": "Generated second study", "doi": "https://doi.org/10.1234/second"},
        ]
    }
    with httpx.Client(
        base_url="https://api.openalex.org",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    ) as client:
        adapter = OpenAlexSearchAdapter(
            OpenAlexConfig(api_key=SecretStr("generated")), client=client
        )
        response = adapter.search(_request(DiscoveryProvider.OPENALEX))
    assert [item.rank for item in response.results] == [1, 2]
    assert response.results[0].original_url == (alternate if field == "primary" else primary)
    assert response.results[0].metadata.pdf_url == "https://papers.example/valid.pdf"
    assert response.results[1].original_url == "https://doi.org/10.1234/second"


@pytest.mark.parametrize("bad_url", BAD_URLS)
def test_arxiv_skips_bad_entries_and_pdf_links_without_losing_rank(bad_url: str) -> None:
    encoded = escape(bad_url, {'"': "&quot;"})
    body = f'''<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><id>{encoded}</id><title>Malformed location</title></entry>
      <entry><id>https://arxiv.org/abs/2601.00001</id><title>Valid study</title>
        <link title="pdf" href="{encoded}" />
        <link title="pdf" href="https://arxiv.org/pdf/2601.00001" />
      </entry>
    </feed>'''
    with httpx.Client(
        base_url="https://export.arxiv.org",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body)),
    ) as client:
        response = ArxivSearchAdapter(ArxivConfig(), client=client).search(
            _request(DiscoveryProvider.ARXIV)
        )
    assert len(response.results) == 1
    assert response.results[0].rank == 2
    assert response.results[0].metadata.raw_provider_rank == 2
    assert response.results[0].metadata.pdf_url == "https://arxiv.org/pdf/2601.00001"


@pytest.mark.parametrize("provider", (DiscoveryProvider.OPENALEX, DiscoveryProvider.ARXIV))
def test_entirely_unusable_scholarly_pages_have_a_typed_outcome(
    provider: DiscoveryProvider,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if provider is DiscoveryProvider.OPENALEX:
            return httpx.Response(
                200, json={"results": [{"primary_location": {"landing_page_url": "http://["}}]}
            )
        return httpx.Response(
            200,
            text='<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://[</id></entry></feed>',
        )

    base = (
        "https://api.openalex.org"
        if provider is DiscoveryProvider.OPENALEX
        else "https://export.arxiv.org"
    )
    with httpx.Client(base_url=base, transport=httpx.MockTransport(respond)) as client:
        adapter = (
            OpenAlexSearchAdapter(OpenAlexConfig(api_key=SecretStr("generated")), client=client)
            if provider is DiscoveryProvider.OPENALEX
            else ArxivSearchAdapter(ArxivConfig(), client=client)
        )
        with pytest.raises(SearchProviderError) as error:
            adapter.search(_request(provider))
    assert error.value.code is SearchFailureCode.EMPTY_RESULTS
