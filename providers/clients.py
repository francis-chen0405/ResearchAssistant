"""Provider-neutral injectable HTTP clients for offline adapter tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import httpx
from pydantic import ConfigDict

from models import StrictModel


class ProviderClients(StrictModel):
    """Optional injected clients used by offline mocked integration tests."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    search: httpx.Client | None = None
    openalex_search: httpx.Client | None = None
    serpsearch: httpx.Client | None = None
    source: httpx.Client | None = None
    acquisition: httpx.Client | None = None
    fallback_acquisition: httpx.Client | None = None
    llm: httpx.Client | None = None
    health_verified: bool = False
    host_resolver: Callable[[str], Sequence[str]] | None = None
