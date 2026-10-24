"""Native owned DNS helpers are bounded, retired and independent of working directory."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from researchassistant.providers import bounded_resolver
from researchassistant.providers.acquisition import WigoloAcquisitionAdapter
from researchassistant.providers.bounded_network import DeadlineHTTPTransport
from researchassistant.providers.config import WigoloConfig
from researchassistant.providers.discovery_transport import bounded_send
from researchassistant.providers.scraper import ScrapeRequest, ScraperTimeoutError


@pytest.mark.slow
def test_stalled_system_resolver_is_retired_before_late_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker, late = tmp_path / "resolver-entered", tmp_path / "late-result"
    script = (
        "import time\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('entered')\n"
        "time.sleep(10)\n"
        f"Path({str(late)!r}).write_text('late')\n"
        'print(\'{"addresses":["93.184.216.34"]}\')\n'
    )
    original = subprocess.Popen
    processes: list[subprocess.Popen[bytes]] = []

    def spawn(command: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        process = original(command, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(bounded_resolver, "_worker_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(bounded_resolver.subprocess, "Popen", spawn)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="deadline"):
        bounded_resolver.resolve_host_addresses("generated.example", timeout=1)
    assert time.monotonic() - started < 3
    assert marker.read_text() == "entered" and not late.exists()
    assert len(processes) == 1 and processes[0].poll() is not None


@pytest.mark.parametrize(
    "payload",
    [
        b"invalid json",
        b"[]",
        b'{"addresses":["not-an-address"]}',
        b"x" * 8193,
        json.dumps({"addresses": ["127.0.0.1"] * 65}).encode(),
    ],
)
def test_resolver_rejects_malformed_or_excessive_helper_output(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    script = f"import sys\nsys.stdout.buffer.write({payload!r})"
    monkeypatch.setattr(bounded_resolver, "_worker_command", lambda: [sys.executable, "-c", script])
    with pytest.raises(OSError, match="resolver"):
        bounded_resolver.resolve_host_addresses("generated.example", timeout=3)


def test_numeric_addresses_need_no_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("numeric connection must not resolve a hostname")

    monkeypatch.setattr(bounded_resolver.subprocess, "Popen", fail)
    assert bounded_resolver.resolve_host_addresses("93.184.216.34") == ("93.184.216.34",)
    assert bounded_resolver.resolve_host_addresses("2606:4700:4700::1111") == (
        "2606:4700:4700::1111",
    )


@pytest.mark.slow
def test_resolver_slot_queue_is_bounded_and_reusable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = (
        "import json,sys,time\nfrom pathlib import Path\n"
        "host=json.load(sys.stdin)['hostname']\n"
        f"Path({str(tmp_path)!r},host).write_text('entered')\n"
        "time.sleep(10)\n"
    )
    monkeypatch.setattr(bounded_resolver, "_worker_command", lambda: [sys.executable, "-c", script])
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(bounded_resolver.resolve_host_addresses, f"host{i}.example", timeout=2)
            for i in range(4)
        ]
        deadline = time.monotonic() + 1.5
        while len(list(tmp_path.iterdir())) != 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(list(tmp_path.iterdir())) == 4
        with pytest.raises(TimeoutError, match="queue"):
            bounded_resolver.resolve_host_addresses("queued.example", timeout=0.02)
        assert not (tmp_path / "queued.example").exists()
        for future in futures:
            with pytest.raises(TimeoutError):
                future.result(timeout=3)
    monkeypatch.setattr(
        bounded_resolver,
        "_worker_command",
        lambda: [sys.executable, "-c", 'print(\'{"addresses":["127.0.0.1"]}\')'],
    )
    assert bounded_resolver.resolve_host_addresses("next.example", timeout=3) == ("127.0.0.1",)


def test_installed_helper_works_from_unrelated_directory_without_path(tmp_path: Path) -> None:
    script = (
        "from researchassistant.providers.bounded_resolver import resolve_host_addresses\n"
        "import ipaddress\n"
        "assert all(ipaddress.ip_address(value).is_loopback for value in "
        "resolve_host_addresses('localhost', timeout=5))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={"PATH": ""},
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize("source", [False, True])
def test_real_transport_deadline_retires_stalled_dns_without_connecting(
    monkeypatch: pytest.MonkeyPatch, source: bool
) -> None:
    import socket

    original = subprocess.Popen
    processes: list[subprocess.Popen[bytes]] = []

    def spawn(command: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        process = original(command, **kwargs)
        processes.append(process)
        return process

    def fail_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("stalled DNS must never attempt a connection")

    monkeypatch.setattr(
        bounded_resolver,
        "_worker_command",
        lambda: [sys.executable, "-c", "import time; time.sleep(10)"],
    )
    monkeypatch.setattr(bounded_resolver.subprocess, "Popen", spawn)
    monkeypatch.setattr(socket, "socket", fail_connect)
    started = time.monotonic()
    if source:
        adapter = WigoloAcquisitionAdapter(WigoloConfig())
        try:
            with pytest.raises(ScraperTimeoutError):
                adapter._preflight(
                    ScrapeRequest(url="http://generated.example/", timeout_seconds=0.2)
                )
        finally:
            adapter._source_client.close()
            adapter._wigolo_client.close()
    else:
        with httpx.Client(transport=DeadlineHTTPTransport()) as client:
            with pytest.raises(httpx.TimeoutException):
                bounded_send(
                    client,
                    "GET",
                    "http://generated.example/",
                    expected_base_url="http://generated.example",
                    timeout=0.2,
                )
    assert time.monotonic() - started < 2
    assert len(processes) == 1 and processes[0].poll() is not None
