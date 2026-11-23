from __future__ import annotations

import httpx
import pytest

from researchassistant.contracts.search import SearchRequest
from researchassistant.providers.config import WigoloConfig
from researchassistant.providers.wigolo import WigoloSearchAdapter


def test_wigolo_loopback_client_ignores_socks_proxy_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:9999")
    monkeypatch.setenv("all_proxy", "socks5://127.0.0.1:9999")
    monkeypatch.setenv("HTTP_PROXY", "socks5://127.0.0.1:9999")
    monkeypatch.setenv("http_proxy", "socks5://127.0.0.1:9999")
    real_client = httpx.Client
    requests: list[str] = []
    client_options: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={"name": "Wigolo", "version": "0.2.1"})
        return httpx.Response(
            200,
            json={"results": [{"url": "https://example.org/paper", "title": "Paper"}]},
        )

    def mock_client(**kwargs: object) -> httpx.Client:
        client_options.append(kwargs)
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", mock_client)
    adapter = WigoloSearchAdapter(WigoloConfig())
    try:
        result = adapter.search(SearchRequest(query_text="a paper", limit=5))
    finally:
        adapter._client.close()

    assert requests == ["/health", "/v1/search"]
    assert client_options[0]["trust_env"] is False
    assert result.results[0].title == "Paper"
