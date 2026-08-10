from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from hashlib import sha256

import httpx
import pytest

from providers.acquisition import (
    ACQUISITION_VERSION,
    AcquisitionFailureCode,
    WigoloAcquisitionAdapter,
)
from providers.config import ExaConfig, FirecrawlConfig, MimoConfig, WigoloConfig
from providers.factory import ProviderFactoryClients
from providers.firecrawl import FallbackAcquisitionAdapter, FirecrawlAcquisitionAdapter
from providers.mimo_factory import MimoProviderFactoryConfig, build_mimo_provider_bundle
from providers.scraper import ScrapeRequest, ScrapeResponse, ScraperProviderError

PUBLIC_IP = "93.184.216.34"


def _resolver_for(
    values: dict[str, Sequence[str]] | None = None,
) -> Callable[[str], Sequence[str]]:
    resolved = values or {}
    return lambda hostname: resolved.get(hostname, (PUBLIC_IP,))


def _wigolo_client(observed_urls: list[str] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if observed_urls is not None:
            observed_urls.append(body["url"])
        return httpx.Response(
            200,
            json={"status": "ok", "markdown": "# Safe\n\nPublic evidence."},
            request=request,
        )

    return httpx.Client(
        base_url="http://127.0.0.1:8000",
        transport=httpx.MockTransport(handler),
    )


def _acquisition_adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_redirects: int = 5,
    resolver: Callable[[str], Sequence[str]] | None = None,
    observed_wigolo_urls: list[str] | None = None,
) -> WigoloAcquisitionAdapter:
    return WigoloAcquisitionAdapter(
        WigoloConfig(max_redirects=max_redirects),
        source_client=httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
        ),
        wigolo_client=_wigolo_client(observed_wigolo_urls),
        host_resolver=resolver or _resolver_for(),
    )


@pytest.mark.parametrize(
    "location",
    [
        "http://10.0.0.4/secret",
        "http://localhost/admin",
        "http://user:password@public.example/secret",
        "file:///etc/passwd",
    ],
)
def test_redirect_policy_rejects_unsafe_target_before_request(location: str) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "start.example":
            return httpx.Response(302, headers={"location": location}, request=request)
        raise AssertionError("an unsafe redirect destination was requested")

    adapter = _acquisition_adapter(handler)

    with pytest.raises(ScraperProviderError) as exc_info:
        adapter.scrape(ScrapeRequest(url="https://start.example/source", timeout_seconds=10))

    assert exc_info.value.retryable is False
    assert requested == ["https://start.example/source"]


@pytest.mark.parametrize(
    "answers",
    [("10.0.0.8",), (PUBLIC_IP, "192.168.1.8")],
)
def test_redirect_hostname_dns_answers_must_all_be_public(answers: Sequence[str]) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://redirect.example/private"},
            request=request,
        )

    adapter = _acquisition_adapter(
        handler,
        resolver=_resolver_for({"redirect.example": answers}),
    )

    with pytest.raises(ScraperProviderError) as exc_info:
        adapter.scrape(ScrapeRequest(url="https://start.example/source", timeout_seconds=10))

    assert exc_info.value.code == AcquisitionFailureCode.INACCESSIBLE
    assert exc_info.value.retryable is False
    assert requested == ["https://start.example/source"]


def test_relative_redirect_uses_validated_final_url_for_wigolo() -> None:
    requested: list[str] = []
    wigolo_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"}, request=request)
        return httpx.Response(
            200,
            content=b"<html><body>Public source.</body></html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    result = _acquisition_adapter(
        handler,
        observed_wigolo_urls=wigolo_urls,
    ).scrape(ScrapeRequest(url="https://start.example/start", timeout_seconds=10))

    assert requested == ["https://start.example/start", "https://start.example/final"]
    assert result.resolved_url == "https://start.example/final"
    assert wigolo_urls == ["https://start.example/final"]


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_every_supported_redirect_status_is_followed_explicitly(status: int) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/start":
            return httpx.Response(status, headers={"location": "/final"}, request=request)
        return httpx.Response(
            200,
            content=b"public evidence",
            headers={"content-type": "text/plain"},
            request=request,
        )

    result = _acquisition_adapter(handler).scrape(
        ScrapeRequest(url="https://start.example/start", timeout_seconds=10)
    )

    assert result.resolved_url == "https://start.example/final"
    assert requested == ["/start", "/final"]


def test_resolution_failure_is_typed_and_fails_before_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("unresolved source was requested")

    def failed_resolver(hostname: str) -> Sequence[str]:
        raise RuntimeError("resolver unavailable")

    with pytest.raises(ScraperProviderError) as exc_info:
        _acquisition_adapter(handler, resolver=failed_resolver).scrape(
            ScrapeRequest(url="https://unresolved.example/source", timeout_seconds=10)
        )

    assert (exc_info.value.code, exc_info.value.retryable) == (
        AcquisitionFailureCode.INACCESSIBLE,
        True,
    )
    assert calls == 0


def test_safe_multi_hop_redirects_close_intermediate_responses() -> None:
    responses: list[httpx.Response] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/one":
            response = httpx.Response(301, headers={"location": "/two"}, request=request)
        elif request.url.path == "/two":
            response = httpx.Response(
                308,
                headers={"location": "https://final.example/three"},
                request=request,
            )
        else:
            response = httpx.Response(
                200,
                content=b"plain public evidence",
                headers={"content-type": "text/plain"},
                request=request,
            )
        responses.append(response)
        return response

    result = _acquisition_adapter(handler).scrape(
        ScrapeRequest(url="https://start.example/one", timeout_seconds=10)
    )

    assert result.resolved_url == "https://final.example/three"
    assert all(response.is_closed for response in responses)


def test_final_stream_is_consumed_before_it_is_closed() -> None:
    class TrackingStream(httpx.SyncByteStream):
        def __init__(self) -> None:
            self.closed = False
            self.iterated = False

        def __iter__(self):
            assert self.closed is False
            self.iterated = True
            yield b"streamed public evidence"

        def close(self) -> None:
            self.closed = True

    stream = TrackingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=stream,
            request=request,
        )

    result = _acquisition_adapter(handler).scrape(
        ScrapeRequest(url="https://start.example/source", timeout_seconds=10)
    )

    assert result.text == "streamed public evidence"
    assert stream.iterated is True
    assert stream.closed is True


@pytest.mark.parametrize("location", [None, "", "http://[invalid"])
def test_redirect_requires_well_formed_location(location: str | None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {} if location is None else {"location": location}
        return httpx.Response(302, headers=headers, request=request)

    with pytest.raises(ScraperProviderError) as exc_info:
        _acquisition_adapter(handler).scrape(
            ScrapeRequest(url="https://start.example/source", timeout_seconds=10)
        )

    assert exc_info.value.code == AcquisitionFailureCode.REDIRECT
    assert exc_info.value.retryable is False


def test_redirect_loop_is_detected_without_re_requesting_seen_url() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        target = "/two" if request.url.path == "/one" else "/one"
        return httpx.Response(302, headers={"location": target}, request=request)

    with pytest.raises(ScraperProviderError) as exc_info:
        _acquisition_adapter(handler).scrape(
            ScrapeRequest(url="https://start.example/one", timeout_seconds=10)
        )

    assert exc_info.value.code == AcquisitionFailureCode.REDIRECT
    assert requested == ["https://start.example/one", "https://start.example/two"]


@pytest.mark.parametrize(("redirects", "succeeds"), [(2, True), (3, False)])
def test_redirect_limit_has_exact_boundary(redirects: int, succeeds: bool) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        index = int(request.url.path.removeprefix("/hop"))
        if index < redirects:
            return httpx.Response(
                307,
                headers={"location": f"/hop{index + 1}"},
                request=request,
            )
        return httpx.Response(
            200,
            content=b"public evidence",
            headers={"content-type": "text/plain"},
            request=request,
        )

    def operation() -> ScrapeResponse:
        return _acquisition_adapter(handler, max_redirects=2).scrape(
            ScrapeRequest(url="https://start.example/hop0", timeout_seconds=10)
        )

    if succeeds:
        assert operation().resolved_url.endswith("/hop2")
        assert requested == ["/hop0", "/hop1", "/hop2"]
    else:
        with pytest.raises(ScraperProviderError) as exc_info:
            operation()
        assert exc_info.value.code == AcquisitionFailureCode.REDIRECT
        assert requested == ["/hop0", "/hop1", "/hop2"]


def _firecrawl_adapter(
    metadata: dict[str, object],
    *,
    resolver: Callable[[str], Sequence[str]] | None = None,
) -> FirecrawlAcquisitionAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "markdown": "# Evidence\n\nExact public evidence.",
                    "metadata": {"statusCode": 200, "contentType": "text/html", **metadata},
                },
            },
            request=request,
        )

    return FirecrawlAcquisitionAdapter(
        FirecrawlConfig(api_key="firecrawl-test-secret"),
        client=httpx.Client(
            base_url="https://api.firecrawl.dev",
            transport=httpx.MockTransport(handler),
        ),
        host_resolver=resolver or _resolver_for(),
    )


@pytest.mark.parametrize(
    "source_url",
    [
        "http://10.0.0.4/private",
        "http://localhost/admin",
        "https://user:password@public.example/source",
        "file:///etc/passwd",
    ],
)
def test_firecrawl_rejects_unsafe_source_url(source_url: str) -> None:
    with pytest.raises(ScraperProviderError) as exc_info:
        _firecrawl_adapter({"sourceURL": source_url}).scrape(
            ScrapeRequest(url="https://request.example/source", timeout_seconds=10)
        )

    assert exc_info.value.code == AcquisitionFailureCode.INACCESSIBLE
    assert exc_info.value.retryable is False
    assert "firecrawl-test-secret" not in str(exc_info.value)


def test_firecrawl_rejects_privately_resolved_source_url() -> None:
    with pytest.raises(ScraperProviderError) as exc_info:
        _firecrawl_adapter(
            {"sourceURL": "https://returned.example/source"},
            resolver=_resolver_for({"returned.example": ("192.168.4.2",)}),
        ).scrape(ScrapeRequest(url="https://request.example/source", timeout_seconds=10))

    assert exc_info.value.code == AcquisitionFailureCode.INACCESSIBLE


def test_firecrawl_missing_source_url_uses_only_validated_request_url() -> None:
    request_url = "https://request.example/source"
    result = _firecrawl_adapter({}).scrape(ScrapeRequest(url=request_url, timeout_seconds=10))
    assert result.resolved_url == request_url


def test_firecrawl_accepts_distinct_valid_public_source_and_canonical_urls() -> None:
    result = _firecrawl_adapter(
        {
            "sourceURL": "https://redirected.example/final",
            "canonicalURL": "https://canonical.example/article",
        }
    ).scrape(ScrapeRequest(url="https://request.example/source", timeout_seconds=10))

    assert result.resolved_url == "https://redirected.example/final"
    assert result.canonical_url == "https://canonical.example/article"


def test_firecrawl_rejects_unsafe_canonical_provenance() -> None:
    with pytest.raises(ScraperProviderError) as exc_info:
        _firecrawl_adapter(
            {
                "sourceURL": "https://redirected.example/final",
                "canonicalURL": "http://127.0.0.1/admin",
            }
        ).scrape(ScrapeRequest(url="https://request.example/source", timeout_seconds=10))

    assert exc_info.value.code == AcquisitionFailureCode.INACCESSIBLE


def test_firecrawl_validates_direct_request_before_provider_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe direct request reached Firecrawl")

    adapter = FirecrawlAcquisitionAdapter(
        FirecrawlConfig(api_key="firecrawl-test-secret"),
        client=httpx.Client(
            base_url="https://api.firecrawl.dev",
            transport=httpx.MockTransport(handler),
        ),
        host_resolver=_resolver_for(),
    )
    with pytest.raises(ScraperProviderError) as exc_info:
        adapter.scrape(ScrapeRequest(url="http://localhost/private", timeout_seconds=10))

    assert exc_info.value.code == AcquisitionFailureCode.INACCESSIBLE
    assert calls == 0


class _CountingFallback:
    def __init__(self) -> None:
        self.calls = 0

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.calls += 1
        raise AssertionError("redirect-policy failure activated fallback")


def test_unsafe_redirect_never_activates_firecrawl_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
            request=request,
        )

    fallback = _CountingFallback()
    adapter = FallbackAcquisitionAdapter(
        primary=_acquisition_adapter(handler),
        fallback=fallback,
    )
    with pytest.raises(ScraperProviderError) as exc_info:
        adapter.scrape(ScrapeRequest(url="https://start.example/source", timeout_seconds=10))

    assert exc_info.value.code == AcquisitionFailureCode.INACCESSIBLE
    assert fallback.calls == 0


def test_mvp6_3_acquisition_identity_is_incompatible_with_pre_phase_identity() -> None:
    config = MimoProviderFactoryConfig(
        exa=ExaConfig(api_key="exa-test-secret"),
        mimo=MimoConfig(api_key="mimo-test-secret"),
        repository_revision="test-revision",
    )
    bundle = build_mimo_provider_bundle(
        config,
        clients=ProviderFactoryClients(host_resolver=_resolver_for()),
    )

    assert ACQUISITION_VERSION == "mvp6.3-public-acquisition-v2"
    assert ACQUISITION_VERSION in bundle.fingerprint_payload_json
    old_payload = bundle.fingerprint_payload_json.replace(
        ACQUISITION_VERSION,
        "mvp2b-acquisition-v1",
    )
    assert sha256(old_payload.encode()).hexdigest() != bundle.fingerprint_sha256
