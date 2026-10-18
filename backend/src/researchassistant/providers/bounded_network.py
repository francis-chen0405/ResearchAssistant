"""HTTP/1 transport with per-operation remaining wall-clock budgets.

The small httpcore integration is covered against the locked runtime version.
Streams consult request-local context on each read, including pooled connections.
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend, SyncStream

from researchassistant.providers.bounded_resolver import resolve_host_addresses

_DEADLINE: ContextVar[tuple[Callable[[], float], float] | None] = ContextVar(
    "provider_network_deadline", default=None
)


@contextmanager
def network_deadline(clock: Callable[[], float], deadline: float) -> Iterator[None]:
    token = _DEADLINE.set((clock, deadline))
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def remaining_timeout(timeout: float | None) -> float | None:
    active = _DEADLINE.get()
    if active is None:
        return timeout
    clock, deadline = active
    remaining = deadline - clock()
    if remaining <= 0:
        raise httpcore.ReadTimeout("provider exceeded absolute network deadline")
    return min(timeout, remaining) if timeout is not None else remaining


class DeadlineStream(httpcore.NetworkStream):
    def __init__(self, stream: httpcore.NetworkStream) -> None:
        self._stream = stream

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._stream.read(max_bytes, timeout=remaining_timeout(timeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._stream.write(buffer, timeout=remaining_timeout(timeout))

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> DeadlineStream:
        return DeadlineStream(
            self._stream.start_tls(
                ssl_context, server_hostname=server_hostname, timeout=remaining_timeout(timeout)
            )
        )

    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)

    def close(self) -> None:
        self._stream.close()


class DeadlineBackend(SyncBackend):
    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> DeadlineStream:
        try:
            addresses = resolve_host_addresses(host, timeout=remaining_timeout(timeout))
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout("hostname resolution timed out") from exc
        except OSError as exc:
            raise httpcore.ConnectError("hostname resolution failed") from exc
        last_error: OSError | None = None
        for numeric in addresses:
            address = ipaddress.ip_address(numeric)
            connection = None
            try:
                connection = socket.socket(
                    socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM
                )
                connection.settimeout(remaining_timeout(timeout))
                connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                for option in socket_options or ():
                    connection.setsockopt(*option)
                if local_address is not None:
                    connection.bind((str(ipaddress.ip_address(local_address)), 0))
                # The helper already resolved the name. Numeric connect must not
                # call create_connection/getaddrinfo a second time.
                connection.connect((str(address), port))
                return DeadlineStream(SyncStream(connection))
            except OSError as exc:
                if connection is not None:
                    connection.close()
                last_error = exc
            except BaseException:
                if connection is not None:
                    connection.close()
                raise
        if isinstance(last_error, TimeoutError):
            raise httpcore.ConnectTimeout("provider connection timed out") from last_error
        raise httpcore.ConnectError("provider connection failed") from last_error


class DeadlineHTTPTransport(httpx.HTTPTransport):
    def __init__(self, *, backend: httpcore.NetworkBackend | None = None) -> None:
        super().__init__(trust_env=False)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=backend or DeadlineBackend(),
            http2=False,
            retries=0,
        )
