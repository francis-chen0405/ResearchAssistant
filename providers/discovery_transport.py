"""Scoped physical-request observer for compiled discovery transports."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Literal, Protocol
from urllib.parse import urlsplit

import httpx

from providers.search import SearchFailureCode, SearchProviderError

if TYPE_CHECKING:
    from providers.search import SearchRequest

RequestKind = Literal["primary", "metadata"]
MAX_DISCOVERY_RESPONSE_BYTES = 5 * 1024 * 1024
_RESPONSE_CHUNK_BYTES = 64 * 1024
_MAX_TOTAL_READ_SECONDS = 120.0


class PhysicalObserver(Protocol):
    def request(
        self,
        request: SearchRequest,
        parameters: Mapping[str, str | int | bool],
        send: Callable[[], httpx.Response],
        *,
        request_kind: RequestKind,
        before_reservation: Callable[[Callable[[], bool] | None], None] | None = None,
    ) -> httpx.Response: ...


_OBSERVER: ContextVar[PhysicalObserver | None] = ContextVar(
    "discovery_physical_observer", default=None
)


def bounded_send(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    expected_base_url: str,
    max_response_bytes: int = MAX_DISCOVERY_RESPONSE_BYTES,
    monotonic: Callable[[], float] | None = None,
    **kwargs: object,
) -> httpx.Response:
    """Send one same-origin request without redirects or unbounded body reads."""
    if not 1 <= max_response_bytes <= MAX_DISCOVERY_RESPONSE_BYTES:
        raise ValueError("discovery response byte limit is outside the fixed safe bound")
    request = client.build_request(method, url, **kwargs)
    if _origin(request.url) != _origin(httpx.URL(expected_base_url)):
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "discovery request origin differs from configured provider origin",
        )
    response = client.send(request, stream=True, follow_redirects=False)
    try:
        declared = response.headers.get("content-length")
        if declared is not None:
            if not declared.isascii() or not declared.isdecimal():
                raise SearchProviderError(
                    SearchFailureCode.MALFORMED_RESPONSE,
                    "provider response has an invalid content length",
                )
            if int(declared) > max_response_bytes:
                raise SearchProviderError(
                    SearchFailureCode.MALFORMED_RESPONSE,
                    "provider response exceeds the bounded byte limit",
                )
        content = bytearray()
        clock = monotonic or time.monotonic
        started = clock()
        deadline = started + _total_read_timeout(request)
        for chunk in response.iter_bytes(chunk_size=_RESPONSE_CHUNK_BYTES):
            if clock() >= deadline:
                raise httpx.ReadTimeout(
                    "provider response exceeded bounded read deadline", request=request
                )
            if len(content) + len(chunk) > max_response_bytes:
                raise SearchProviderError(
                    SearchFailureCode.MALFORMED_RESPONSE,
                    "provider response exceeds the bounded byte limit",
                )
            content.extend(chunk)
        if clock() >= deadline:
            raise httpx.ReadTimeout(
                "provider response exceeded bounded read deadline", request=request
            )
        headers = httpx.Headers(response.headers)
        # iter_bytes yields decoded content. Preserve the remaining response
        # metadata while preventing consumers from decoding or sizing it twice.
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
            content=bytes(content),
            request=request,
            extensions=response.extensions,
        )
    finally:
        response.close()


def _total_read_timeout(request: httpx.Request) -> float:
    configured = request.extensions.get("timeout")
    read_timeout: float | None = None
    if isinstance(configured, Mapping):
        value = configured.get("read")
        if isinstance(value, (int, float)) and value > 0:
            read_timeout = float(value)
    # The transport's read timeout limits any one blocking read; this adds a
    # bounded wall-clock limit across all chunks, including an infinite stream.
    return min(read_timeout or _MAX_TOTAL_READ_SECONDS, _MAX_TOTAL_READ_SECONDS)


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    parsed = urlsplit(str(url))
    if parsed.username is not None or parsed.password is not None:
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "discovery request URL cannot contain credentials",
        )
    try:
        port = url.port
    except ValueError as exc:
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "discovery request has an invalid provider origin",
        ) from exc
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in {"https", "http"} or not hostname:
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "discovery request has an invalid provider origin",
        )
    return scheme, hostname, port


def has_physical_observer() -> bool:
    return _OBSERVER.get() is not None


@contextmanager
def observe_physical_requests(observer: PhysicalObserver) -> Iterator[None]:
    token = _OBSERVER.set(observer)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


def physical_request(
    request: SearchRequest,
    parameters: Mapping[str, str | int | bool],
    send: Callable[[], httpx.Response],
    *,
    request_kind: RequestKind = "primary",
    before_reservation: Callable[[Callable[[], bool] | None], None] | None = None,
) -> httpx.Response:
    observer = _OBSERVER.get()
    if request.compiled_query is None:
        return send()
    if observer is None:
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "compiled discovery requests require the durable query execution owner",
        )
    return observer.request(
        request,
        parameters,
        send,
        request_kind=request_kind,
        before_reservation=before_reservation,
    )
