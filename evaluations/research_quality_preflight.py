"""Local, secret-free preflight receipts; this module cannot send provider requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from researchassistant.runtime.application_runtime import repository_identity

REQUIRED_KEYS = ("LUNA_API_KEY", "EXA_API_KEY", "OPENALEX_API_KEY", "SERPSEARCH_API_KEY")
CASE_DIR = Path(__file__).parent / "cases/research_quality"


def inspect_preflight(
    allowance_path: Path,
    *,
    credential_reader: Callable[[str], str | None] | None = None,
    identity: str | None = None,
) -> dict[str, Any]:
    """Bind explicit approval to frozen inputs before optional native-vault reads."""
    payload = allowance_path.read_bytes()
    allowance = json.loads(payload)
    if (
        allowance.get("status") != "approved"
        or allowance.get("aggregate_exposure_usd") != "2.48"
        or allowance.get("reference_policy") != "assistant_candidates_frozen_human_scores_pending"
        or not allowance.get("allowance_id")
        or not allowance.get("human_authorization")
    ):
        raise ValueError("explicit protocol allowance and reference-policy approval required")
    required_files = {"prepared.json", "queries.json", "reference_nominations.json"}
    frozen = allowance.get("frozen_inputs", {})
    if set(frozen) != required_files:
        raise ValueError("exact frozen input inventory required")
    for name, digest in frozen.items():
        if hashlib.sha256((allowance_path.parent / name).read_bytes()).hexdigest() != digest:
            raise ValueError("approved frozen input changed")
    current_identity = identity or repository_identity()
    baseline = json.loads((allowance_path.parent / "prepared.json").read_bytes())["baseline"]
    if current_identity != baseline["source_identity"]:
        raise ValueError("current runtime source differs from approved baseline")
    credentials: dict[str, str] = {}
    for name in REQUIRED_KEYS:
        if credential_reader is None:
            credentials[name] = "not_checked"
            continue
        try:
            # Values live only in this process; neither values nor exception messages are saved.
            secret = credential_reader(name)
            credentials[name] = "available" if secret else "missing"
            secret = None
        except Exception:
            credentials[name] = "unavailable"
    stops = []
    if any(state != "available" for state in credentials.values()):
        stops.append("required_native_credentials_unavailable_or_unchecked")
    # Dashboard terms and private capture/allowance transport are distinct manual gates.
    # This preflight never declares transport ready or substitutes a metered health test.
    stops.extend(("account_terms_unverified", "bounded_private_live_collector_unavailable"))
    return {
        "receipt_kind": "local_preflight_no_provider_transport",
        "recorded_at": datetime.now(UTC).isoformat(),
        "allowance_id": allowance["allowance_id"],
        "allowance_sha256": hashlib.sha256(payload).hexdigest(),
        "aggregate_cap_usd": "2.48",
        "source_identity": current_identity,
        "frozen_inputs": frozen,
        "reference_policy": allowance["reference_policy"],
        "human_quality_judgments": "pending",
        "native_credentials": credentials,
        "status": "stopped_before_transport",
        "stop_reasons": stops,
        "new_provider_requests": 0,
        "new_model_calls": 0,
        "reserved_exposure_usd": "0.00",
        "incremental_paid_call_cost_usd": "0.00",
        "account_invoice_total_usd": None,
        "authorized_live_observations": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allowance", type=Path, default=CASE_DIR / "allowance.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-native-credentials", action="store_true")
    args = parser.parse_args(argv)
    reader = None
    if args.check_native_credentials:
        from researchassistant.platform_support.credential_store import _read_secret

        reader = _read_secret
    try:
        report = inspect_preflight(args.allowance, credential_reader=reader)
    except (ValueError, KeyError, OSError):
        parser.exit(2, "preflight input validation failed; no provider requests sent\n")
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Refuse replacement: earlier receipts remain immutable and attributable.
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    print("Preflight stopped before transport; receipt saved; new paid-call exposure $0.00")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
