from __future__ import annotations

import gzip
from collections.abc import Iterator

import httpx
import pytest

from providers.discovery_transport import bounded_send
from providers.search import SearchFailureCode, SearchProviderError


class _TrackedStream(httpx.SyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.chunks = chunks
        self.started = False
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        self.started = True
        yield from self.chunks

    def close(self) -> None:
        self.closed = True


def test_declared_oversize_is_rejected_and_stream_is_closed() -> None:
    stream = _TrackedStream((b"small",))
    client = httpx.Client(
        base_url="https://api.example",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-length": "11"}, stream=stream)
        ),
    )

    with pytest.raises(SearchProviderError) as error:
        bounded_send(
            client,
            "GET",
            "/search",
            expected_base_url="https://api.example",
            max_response_bytes=10,
        )

    assert error.value.code is SearchFailureCode.MALFORMED_RESPONSE
    assert stream.closed
    assert not stream.started


def test_chunked_oversize_is_rejected_after_bounded_streaming_and_closed() -> None:
    stream = _TrackedStream((b"12345678", b"90123456"))
    client = httpx.Client(
        base_url="https://api.example",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"transfer-encoding": "chunked"}, stream=stream)
        ),
    )

    with pytest.raises(SearchProviderError) as error:
        bounded_send(
            client,
            "GET",
            "/search",
            expected_base_url="https://api.example",
            max_response_bytes=10,
        )

    assert error.value.code is SearchFailureCode.MALFORMED_RESPONSE
    assert stream.started
    assert stream.closed


def test_decompressed_body_limit_cannot_be_bypassed_by_small_gzip_payload() -> None:
    decompressed = b"x" * 100
    compressed = gzip.compress(decompressed)
    client = httpx.Client(
        base_url="https://api.example",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={
                    "content-encoding": "gzip",
                    "content-length": str(len(compressed)),
                },
                content=compressed,
            )
        ),
    )

    with pytest.raises(SearchProviderError) as error:
        bounded_send(
            client,
            "GET",
            "/search",
            expected_base_url="https://api.example",
            max_response_bytes=50,
        )

    assert error.value.code is SearchFailureCode.MALFORMED_RESPONSE


def test_small_gzip_response_is_returned_decoded_without_stale_encoding_headers() -> None:
    body = b'{"results":[{"title":"bounded"}]}'
    compressed = gzip.compress(body)
    client = httpx.Client(
        base_url="https://api.example",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={
                    "content-encoding": "gzip",
                    "content-length": str(len(compressed)),
                    "content-type": "application/json",
                },
                content=compressed,
            )
        ),
    )

    response = bounded_send(
        client,
        "GET",
        "/search",
        expected_base_url="https://api.example",
    )

    assert response.content == body
    assert response.json() == {"results": [{"title": "bounded"}]}
    assert "content-encoding" not in response.headers
    assert response.headers["content-length"] == str(len(body))


def test_total_read_deadline_closes_a_slow_stream() -> None:
    stream = _TrackedStream((b"one", b"two"))
    client = httpx.Client(
        base_url="https://api.example",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)),
    )
    times = iter((0.0, 0.25, 0.6))

    with pytest.raises(httpx.ReadTimeout):
        bounded_send(
            client,
            "GET",
            "/search",
            expected_base_url="https://api.example",
            timeout=0.5,
            monotonic=lambda: next(times),
        )

    assert stream.closed


def test_redirects_are_disabled_even_when_injected_client_follows_them() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"location": "https://outside.example/next"})

    client = httpx.Client(
        base_url="https://api.example",
        follow_redirects=True,
        transport=httpx.MockTransport(handler),
    )
    response = bounded_send(
        client,
        "GET",
        "/search",
        expected_base_url="https://api.example",
        headers={"Authorization": "Bearer secret-fixture-token"},
    )

    assert response.status_code == 302
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.example/search"
    assert seen[0].headers["authorization"] == "Bearer secret-fixture-token"


def test_injected_client_with_wrong_origin_is_rejected_before_transport() -> None:
    seen: list[httpx.Request] = []
    client = httpx.Client(
        base_url="https://outside.example",
        transport=httpx.MockTransport(
            lambda request: seen.append(request) or httpx.Response(200, text="unexpected")
        ),
    )

    with pytest.raises(SearchProviderError) as error:
        bounded_send(
            client,
            "GET",
            "/search",
            expected_base_url="https://api.example",
            headers={"Authorization": "Bearer secret-fixture-token"},
        )

    assert error.value.code is SearchFailureCode.PERMANENT_FAILURE
    assert "secret-fixture-token" not in str(error.value)
    assert seen == []


def test_ordinary_query_parameters_and_payload_are_preserved() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"accepted": True})

    client = httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(handler))
    response = bounded_send(
        client,
        "POST",
        "/search",
        expected_base_url="https://api.example",
        params={"query": "quoted phrase", "page": 2},
        json={"type": "auto", "numResults": 20},
    )

    assert response.json() == {"accepted": True}
    assert len(requests) == 1
    assert requests[0].url.params["query"] == "quoted phrase"
    assert requests[0].url.params["page"] == "2"
    assert requests[0].read() == b'{"type":"auto","numResults":20}'
