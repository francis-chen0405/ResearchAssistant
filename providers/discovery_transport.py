"""Scoped physical-request observer for compiled discovery transports."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Literal, Protocol

import httpx

from providers.search import SearchFailureCode, SearchProviderError

if TYPE_CHECKING:
    from providers.search import SearchRequest

RequestKind = Literal["primary", "metadata"]


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
