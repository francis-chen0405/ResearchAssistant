from __future__ import annotations

from uuid import uuid4

import httpx

from models import DiscoveryProvider, SearchIntent
from providers.arxiv import ArxivSearchAdapter
from providers.config import ArxivConfig, PubMedConfig
from providers.pubmed import PubMedSearchAdapter
from providers.search import SearchRequest


def test_arxiv_adapter_normalizes_atom_metadata_without_an_api_key() -> None:
    body = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
    <feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:arxiv=\"http://arxiv.org/schemas/atom\">
      <entry>
        <id>https://arxiv.org/abs/2401.00001</id>
        <title> Test preprint </title>
        <summary> Metadata abstract only. </summary>
        <published>2024-01-01T00:00:00Z</published>
        <author><name>Ada Example</name></author>
        <category term=\"cs.AI\" />
        <arxiv:doi>10.1000/example</arxiv:doi>
        <link title=\"pdf\" href=\"https://arxiv.org/pdf/2401.00001\" />
      </entry>
    </feed>"""
    adapter = ArxivSearchAdapter(
        ArxivConfig(),
        client=httpx.Client(
            base_url="https://export.arxiv.org",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body)),
        ),
    )

    response = adapter.search(
        SearchRequest(
            run_id=uuid4(),
            provider=DiscoveryProvider.ARXIV,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="test preprint",
            limit=5,
        )
    )

    assert response.provider_name == "arxiv"
    assert response.results[0].metadata.doi == "10.1000/example"
    assert response.results[0].metadata.work_type == "preprint"


def test_pubmed_adapter_uses_optional_key_and_returns_bibliographic_metadata() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})
        return httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["123"],
                    "123": {
                        "title": "A biomedical article",
                        "pubdate": "2025 Jan",
                        "authors": [{"name": "Ada Example"}],
                        "articleids": [{"idtype": "doi", "value": "10.1000/pubmed"}],
                    },
                }
            },
        )

    adapter = PubMedSearchAdapter(
        PubMedConfig(api_key="pubmed-key"),
        client=httpx.Client(
            base_url="https://eutils.ncbi.nlm.nih.gov",
            transport=httpx.MockTransport(handler),
        ),
    )

    response = adapter.search(
        SearchRequest(
            run_id=uuid4(),
            provider=DiscoveryProvider.PUBMED,
            intent=SearchIntent.ACADEMIC_STUDY,
            query_text="biomedical evidence",
            limit=5,
        )
    )

    assert len(requests) == 2
    assert requests[0].url.params["api_key"] == "pubmed-key"
    assert response.results[0].original_url == "https://pubmed.ncbi.nlm.nih.gov/123/"
    assert response.results[0].metadata.doi == "10.1000/pubmed"
