"""Own and retire each potentially stalled system resolver outside research threads."""

from __future__ import annotations

import ipaddress
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import BoundedSemaphore

from researchassistant.providers.dns_worker import MAX_ADDRESSES, MAX_OUTPUT_BYTES

_RESOLVERS = BoundedSemaphore(4)
_MAX_RESOLVE_SECONDS = 30.0


def _worker_command() -> list[str]:
    return (
        [sys.executable, "--dns-worker"]
        if getattr(sys, "frozen", False)
        else [sys.executable, str(Path(__file__).with_name("dns_worker.py").resolve())]
    )


def resolve_host_addresses(hostname: str, *, timeout: float | None = None) -> tuple[str, ...]:
    """Include queue/startup/DNS in one finite budget; never leave a resolver thread."""
    if not 1 <= len(hostname) <= 253 or "\x00" in hostname:
        raise OSError("invalid resolver hostname")
    try:
        return (str(ipaddress.ip_address(hostname)),)
    except ValueError:
        pass
    budget = _MAX_RESOLVE_SECONDS if timeout is None else min(timeout, _MAX_RESOLVE_SECONDS)
    if not math.isfinite(budget) or budget <= 0:
        raise TimeoutError("hostname resolution deadline expired")
    deadline = time.monotonic() + budget
    if not _RESOLVERS.acquire(timeout=budget):
        raise TimeoutError("hostname resolution queue deadline expired")
    process = None
    job = None
    try:
        # A regular file avoids unbounded pipe buffering; only our fixed-size
        # worker response is read into the parent, even after a malformed worker.
        with tempfile.TemporaryFile() as output:
            if sys.platform == "win32":
                from researchassistant.platform_support.windows_job import WindowsJob

                job = WindowsJob(memory_limit_bytes=512 * 1024 * 1024)
            process = subprocess.Popen(
                _worker_command(),
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.DEVNULL,
            )
            if job is not None:
                job.attach(int(process._handle))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("hostname resolution startup deadline expired")
            process.communicate(
                json.dumps({"hostname": hostname}).encode("ascii"), timeout=remaining
            )
            if time.monotonic() >= deadline:
                raise TimeoutError("hostname resolution deadline expired")
            if process.returncode != 0:
                raise OSError("hostname resolver failed")
            output.seek(0)
            payload = output.read(MAX_OUTPUT_BYTES + 1)
            if len(payload) > MAX_OUTPUT_BYTES:
                raise OSError("hostname resolver output exceeds bound")
            response = json.loads(payload)
            addresses = response.get("addresses") if isinstance(response, dict) else None
            if (
                not isinstance(addresses, list)
                or not 1 <= len(addresses) <= MAX_ADDRESSES
                or any(not isinstance(value, str) for value in addresses)
            ):
                raise OSError("hostname resolver returned invalid addresses")
            return tuple(dict.fromkeys(str(ipaddress.ip_address(value)) for value in addresses))
    except subprocess.TimeoutExpired:
        raise TimeoutError("hostname resolution deadline expired") from None
    except (ValueError, TypeError) as exc:
        raise OSError("hostname resolver returned invalid data") from exc
    finally:
        try:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=1)
        finally:
            if job is not None:
                job.close()
            _RESOLVERS.release()
