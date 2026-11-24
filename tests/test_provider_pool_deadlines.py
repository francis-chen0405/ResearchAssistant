"""Pool acquisition spends the same absolute budget as provider socket work."""

from __future__ import annotations

import time

import httpx
import pytest
from test_public_source_transport import WireSocket

from researchassistant.providers import bounded_network
from researchassistant.providers.bounded_network import DeadlineHTTPTransport, network_deadline


def test_saturated_provider_pool_wait_uses_remaining_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = WireSocket()
    monkeypatch.setattr(bounded_network.socket, "socket", lambda *args, **kwargs: wire)
    monkeypatch.setattr(
        bounded_network, "resolve_host_addresses", lambda host, **kwargs: ("93.184.216.34",)
    )
    transport = DeadlineHTTPTransport()
    # Leave an unread streaming response holding the only connection, so the
    # second request exercises real httpcore pool acquisition without a server.
    transport._pool._max_connections = 1
    with httpx.Client(transport=transport, timeout=0.5) as client:
        held = client.send(client.build_request("GET", "http://api.example/held"), stream=True)
        try:
            started = time.monotonic()
            with network_deadline(time.monotonic, started + 0.03):
                with pytest.raises(httpx.PoolTimeout):
                    client.get("http://api.example/queued")
            assert time.monotonic() - started < 0.25
            assert wire.sent.count(b"GET ") == 1
        finally:
            held.close()


def test_expired_provider_pool_deadline_fails_before_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_send(*args: object, **kwargs: object) -> None:
        pytest.fail("expired request entered the connection pool")

    transport = DeadlineHTTPTransport()
    monkeypatch.setattr(transport._pool, "handle_request", unexpected_send)
    with httpx.Client(transport=transport) as client:
        with network_deadline(lambda: 5.0, 4.0):
            with pytest.raises(httpx.ReadTimeout, match="absolute network deadline"):
                client.get("http://api.example/expired")
