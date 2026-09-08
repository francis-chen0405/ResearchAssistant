"""Explicit, non-generating credential checks for existing model providers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import httpx

from models import StrictModel


class ConnectionCheck(StrictModel):
    provider: str
    state: Literal["missing", "connected", "rejected", "unavailable", "saved"]
    message: str


def check_connection(
    name: str, environment: Mapping[str, str], *, client: httpx.Client | None = None
) -> ConnectionCheck:
    names = {
        "mimo": "MIMO_API_KEY",
        "openai": "LUNA_API_KEY",
        "serpsearch": "SERPSEARCH_API_KEY",
        "exa": "EXA_API_KEY",
        "openalex": "OPENALEX_API_KEY",
        "pubmed": "PUBMED_API_KEY",
        "firecrawl": "FIRECRAWL_API_KEY",
    }
    if name not in names:
        raise ValueError("Unknown provider")
    key = environment.get(names[name], "").strip()
    if not key:
        return ConnectionCheck(provider=name, state="missing", message="Save an API key first.")
    if name not in ("mimo", "openai"):
        return ConnectionCheck(
            provider=name,
            state="saved",
            message=(
                "Key is saved. This source has no configured free authentication "
                "check; access is checked during an explicit research run."
            ),
        )
    base = "https://api.xiaomimimo.com/v1" if name == "mimo" else "https://api.openai.com/v1"
    configured = environment.get("MIMO_BASE_URL" if name == "mimo" else "LUNA_BASE_URL", base)
    if configured.rstrip("/") != base:
        return ConnectionCheck(
            provider=name,
            state="unavailable",
            message=(
                "The saved custom endpoint is outside the supported profile. "
                "Restore the standard route first."
            ),
        )
    owned = client is None
    transport = client or httpx.Client(timeout=10, follow_redirects=False, trust_env=False)
    try:
        response = transport.get(
            base + "/models",
            headers={"api-key": key} if name == "mimo" else {"Authorization": f"Bearer {key}"},
        )
        if response.status_code in (401, 403):
            return ConnectionCheck(
                provider=name,
                state="rejected",
                message="The provider rejected this key. Replace it and check account access.",
            )
        if response.status_code != 200:
            return ConnectionCheck(
                provider=name,
                state="unavailable",
                message="The provider could not confirm access. Try again later.",
            )
        payload = response.json()
        available = {item.get("id") for item in payload.get("data", []) if isinstance(item, dict)}
        required = {"mimo-v2.5", "mimo-v2.5-pro"} if name == "mimo" else {"gpt-5.6-luna"}
        if not required.issubset(available):
            return ConnectionCheck(
                provider=name,
                state="unavailable",
                message=(
                    "The key was accepted, but the supported models were not listed "
                    "for this account."
                ),
            )
        return ConnectionCheck(
            provider=name,
            state="connected",
            message=(
                "Key accepted and supported models listed. No text was generated. "
                "Account quota and research output are checked during a run."
            ),
        )
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return ConnectionCheck(
            provider=name,
            state="unavailable",
            message="Connection could not be confirmed. Check your network and try again.",
        )
    finally:
        if owned:
            transport.close()
