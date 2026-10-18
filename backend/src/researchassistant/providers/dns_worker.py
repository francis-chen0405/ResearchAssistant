"""Private one-shot DNS protocol; numeric results only, with bounded input/output."""

from __future__ import annotations

import ipaddress
import json
import socket
import sys

MAX_ADDRESSES = 64
MAX_OUTPUT_BYTES = 8192


def main() -> None:
    request = json.loads(sys.stdin.buffer.read(1025))
    hostname = request["hostname"]
    if not isinstance(hostname, str) or not 1 <= len(hostname) <= 253 or "\x00" in hostname:
        raise ValueError("invalid resolver hostname")
    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        addresses: list[str] = []
        for _, _, _, _, address in results:
            numeric = str(ipaddress.ip_address(address[0]))
            if numeric not in addresses:
                addresses.append(numeric)
                if len(addresses) > MAX_ADDRESSES:
                    raise ValueError("resolver returned too many addresses")
        if not addresses:
            raise ValueError("resolver returned no addresses")
        response = {"addresses": addresses}
    except (OSError, ValueError):
        response = {"error": "resolution_failed"}
    encoded = json.dumps(response).encode("ascii")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ValueError("resolver output exceeds bound")
    sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()
