"""Explicit, non-generating credential checks for existing model providers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import httpx

from models import StrictModel
from providers.model_choices import ACTIVE_MODEL_STAGES, StageModelSelections, option_for
from providers.model_profiles import STANDARD_PROFILE, ProfileId


class ConnectionCheck(StrictModel):
    provider: str
    state: Literal["missing", "connected", "rejected", "unavailable", "saved"]
    message: str


def check_connection(
    name: str,
    environment: Mapping[str, str],
    *,
    model_profile: ProfileId,
    stage_models: StageModelSelections,
    client: httpx.Client | None = None,
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
    if model_profile == STANDARD_PROFILE.id:
        profile_models = (
            STANDARD_PROFILE.models[:2] if name == "mimo" else STANDARD_PROFILE.models[2:]
        )
        required = {model.model for model in profile_models}
    else:
        required = {
            option.model
            for stage in ACTIVE_MODEL_STAGES
            if (option := option_for(stage_models.for_stage(stage))).provider == name
        }
    if not required:
        return ConnectionCheck(
            provider=name,
            state="unavailable",
            message="This provider is not selected for any research step.",
        )
    if name == "openai":
        default_model = "gpt-5.6-luna" if model_profile == STANDARD_PROFILE.id else "gpt-6-luna"
        allowed_overrides = (
            {"gpt-5.6-luna"}
            if model_profile == STANDARD_PROFILE.id
            else {"gpt-5.6-luna", "gpt-6-luna"}
        )
        if environment.get("LUNA_MODEL", default_model) not in allowed_overrides:
            return ConnectionCheck(
                provider=name,
                state="unavailable",
                message="The saved custom model route is outside the supported profile.",
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
        missing = required - available
        if missing:
            return ConnectionCheck(
                provider=name,
                state="unavailable",
                message=(
                    "The key was accepted, but the selected model access could not be "
                    "confirmed. Not listed for this account: " + ", ".join(sorted(missing)) + "."
                ),
            )
        return ConnectionCheck(
            provider=name,
            state="connected",
            message=(
                "Key accepted and all selected model IDs listed. No text was generated. "
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
