"""Connect directly to validated numeric public addresses with original TLS SNI."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from typing import Any

import httpcore
from httpcore._backends.sync import SyncStream

from researchassistant.providers.bounded_network import (
    DeadlineBackend,
    DeadlineHTTPTransport,
    DeadlineStream,
    remaining_timeout,
)


class PublicDestinationBackend(DeadlineBackend):
    def __init__(self, resolve_public: Callable[[str], Sequence[str]]) -> None:
        self._resolve_public = resolve_public

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> DeadlineStream:
        if local_address is not None:
            raise httpcore.ConnectError("public source transport cannot bind a custom interface")
        addresses = tuple(ipaddress.ip_address(value) for value in self._resolve_public(host))
        if not addresses or any(not address.is_global for address in addresses):
            raise httpcore.ConnectError("source destination is not exclusively public")
        last_error: OSError | None = None
        for address in addresses:
            connection = socket.socket(
                socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM
            )
            try:
                connection.settimeout(remaining_timeout(timeout))
                connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                for option in socket_options or ():
                    connection.setsockopt(*option)
                # Numeric socket.connect performs no hostname lookup. Do not use
                # create_connection/getaddrinfo here, even for numeric addresses.
                connection.connect((str(address), port))
                peer = ipaddress.ip_address(connection.getpeername()[0])
                if peer != address or not peer.is_global:
                    raise httpcore.ConnectError(
                        "source connected peer differs from validated address"
                    )
                return DeadlineStream(SyncStream(connection))
            except OSError as exc:
                connection.close()
                last_error = exc
            except BaseException:
                connection.close()
                raise
        if isinstance(last_error, TimeoutError):
            raise httpcore.ConnectTimeout("public source connection timed out") from last_error
        raise httpcore.ConnectError("public source connection failed") from last_error


class PublicDestinationHTTPTransport(DeadlineHTTPTransport):
    def __init__(self, resolve_public: Callable[[str], Sequence[str]]) -> None:
        super().__init__(backend=PublicDestinationBackend(resolve_public))
