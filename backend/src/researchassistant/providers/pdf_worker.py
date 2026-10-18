"""Private bounded PDF subprocess protocol; stdin never contains credentials."""

from __future__ import annotations

import json
import math
import sys

from researchassistant.providers.normalization import NormalizationError, _normalize_pdf_in_worker


def main() -> None:
    header = sys.stdin.buffer.readline(4096)
    options = json.loads(header)
    seconds = float(options["deadline_seconds"])
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(seconds) + 1, math.ceil(seconds) + 1))
        # macOS does not reliably implement address-space limits; the wall/CPU
        # deadline still applies. Linux bounds the worker's decompression memory.
        if sys.platform.startswith("linux"):
            limit = 1024 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    payload = sys.stdin.buffer.read(25 * 1024 * 1024 + 1)
    if len(payload) > 25 * 1024 * 1024:
        raise ValueError("PDF worker byte limit exceeded")
    try:
        document = _normalize_pdf_in_worker(payload, **options)
        result = document.model_dump_json().encode()
        if len(result) > 8 * 1024 * 1024:
            raise ValueError("PDF worker output exceeds bound")
    except NormalizationError as exc:
        result = json.dumps({"error": exc.code}).encode()
    sys.stdout.buffer.write(result)


if __name__ == "__main__":
    main()
