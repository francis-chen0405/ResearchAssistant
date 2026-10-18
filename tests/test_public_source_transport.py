"""DNS validation constrains the actual socket while Host and TLS SNI stay original."""

from __future__ import annotations

import socket
import ssl
from typing import Any

import pytest

from researchassistant.providers.acquisition import WigoloAcquisitionAdapter
from researchassistant.providers.config import WigoloConfig
from researchassistant.providers.scraper import ScrapeRequest, ScraperProviderError


class WireSocket:
    def __init__(self, *, peer: str | None = None) -> None:
        self.peer = peer
        self.destination: tuple[str, int] | None = None
        self.sent = b""
        self.closed = False
        self.pending = (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 12\r\n\r\nPublic text."
        )

    def connect(self, destination: tuple[str, int]) -> None:
        self.destination = destination

    def getpeername(self) -> tuple[str, int]:
        assert self.destination is not None
        return self.peer or self.destination[0], self.destination[1]

    def settimeout(self, timeout: float | None) -> None:
        pass

    def setsockopt(self, *args: object) -> None:
        pass

    def fileno(self) -> int:
        return -1

    def send(self, buffer: bytes) -> int:
        self.sent += buffer
        return len(buffer)

    def recv(self, count: int) -> bytes:
        value, self.pending = self.pending[:count], self.pending[count:]
        return value

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "case", ["rebind", "mixed", "wrong_peer", "valid_https", "bad_certificate"]
)
def test_public_source_socket_and_tls_boundary(monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    wire = WireSocket(peer="127.0.0.1" if case == "wrong_peer" else None)
    connected: list[WireSocket] = []
    sni: list[str] = []
    resolutions = 0

    def resolve(host: str) -> tuple[str, ...]:
        nonlocal resolutions
        resolutions += 1
        assert host == "source.example"
        if case == "rebind" and resolutions > 1:
            return ("127.0.0.1",)
        if case == "mixed":
            return ("93.184.216.34", "127.0.0.1")
        return ("93.184.216.34",)

    def make_socket(*args: object, **kwargs: object) -> WireSocket:
        connected.append(wire)
        return wire

    def wrap(context: ssl.SSLContext, sock: Any, *, server_hostname: str) -> WireSocket:
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        sni.append(server_hostname)
        if case == "bad_certificate":
            raise ssl.SSLCertVerificationError("fixture mismatched certificate")
        return wire

    monkeypatch.setattr(socket, "socket", make_socket)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap)
    adapter = WigoloAcquisitionAdapter(WigoloConfig(), host_resolver=resolve)
    try:
        if case == "valid_https":
            result = adapter.scrape(
                ScrapeRequest(url="https://source.example/article", timeout_seconds=1)
            )
            assert result.text == "Public text."
            assert wire.destination == ("93.184.216.34", 443)
            assert b"Host: source.example" in wire.sent
            assert sni == ["source.example"]
        else:
            with pytest.raises(ScraperProviderError):
                adapter.scrape(
                    ScrapeRequest(url="https://source.example/article", timeout_seconds=1)
                )
            if case in {"rebind", "mixed"}:
                assert connected == []
            assert wire.sent == b""
    finally:
        adapter._source_client.close()
        adapter._wigolo_client.close()


def test_public_ipv6_candidate_is_acquired_over_numeric_ipv6_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = WireSocket()
    families: list[int] = []

    def make_socket(family: int, kind: int) -> WireSocket:
        families.append(family)
        assert kind == socket.SOCK_STREAM
        return wire

    monkeypatch.setattr(socket, "socket", make_socket)
    adapter = WigoloAcquisitionAdapter(WigoloConfig())
    try:
        result = adapter.scrape(
            ScrapeRequest(url="http://[2606:4700:4700::1111]:8443/paper", timeout_seconds=1)
        )
        assert result.text == "Public text."
        assert result.resolved_url == "http://[2606:4700:4700::1111]:8443/paper"
        assert wire.destination == ("2606:4700:4700::1111", 8443)
        assert families == [socket.AF_INET6]
        assert b"Host: [2606:4700:4700::1111]:8443" in wire.sent
    finally:
        adapter._source_client.close()
        adapter._wigolo_client.close()
    assert wire.closed
