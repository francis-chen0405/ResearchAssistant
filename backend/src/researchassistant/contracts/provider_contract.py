"""Canonical provider-run compatibility payload handling.

This module deliberately depends only on the standard library so the Pydantic model,
provider factories, persistence reconstruction, and resume checks share one algorithm
without creating a factory/model import cycle.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

PROVIDER_CONTRACT_PAYLOAD_KEYS = frozenset(
    {
        "fingerprint_version",
        "provider_identity",
        "adapter_identity",
        "model_identity",
        "prompt_identity",
        "schema_identity",
        "normalization_identity",
        "policy_identity",
        "repository_revision",
    }
)


def canonical_provider_contract_payload(payload: Mapping[str, str]) -> str:
    """Validate and serialize the exact fingerprint payload representation."""
    normalized = _validate_payload_shape(payload)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def parse_provider_contract_payload(payload_json: str) -> dict[str, str]:
    """Load strict canonical JSON, rejecting duplicate keys and altered byte forms."""
    try:
        parsed = json.loads(payload_json, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"payload_json must be valid JSON without duplicate keys: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("payload_json must contain one JSON object")
    normalized = _validate_payload_shape(parsed)
    canonical = canonical_provider_contract_payload(normalized)
    if payload_json != canonical:
        raise ValueError("payload_json must use the canonical sorted compact JSON representation")
    return normalized


def provider_contract_fingerprint(payload_json: str) -> str:
    """Return the authoritative SHA-256 for already validated canonical payload bytes."""
    parse_provider_contract_payload(payload_json)
    return sha256(payload_json.encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _validate_payload_shape(payload: Mapping[str, Any]) -> dict[str, str]:
    actual = set(payload)
    missing = PROVIDER_CONTRACT_PAYLOAD_KEYS - actual
    extra = actual - PROVIDER_CONTRACT_PAYLOAD_KEYS
    if missing:
        raise ValueError(f"provider contract payload is missing keys: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"provider contract payload has extra keys: {', '.join(sorted(extra))}")
    normalized: dict[str, str] = {}
    for key in PROVIDER_CONTRACT_PAYLOAD_KEYS:
        value = payload[key]
        if not isinstance(value, str) or not value:
            raise ValueError(f"provider contract payload {key} must be a non-empty string")
        normalized[key] = value
    return normalized
