"""Health HTTP routes; application dependencies are supplied by assembly."""

from __future__ import annotations

from fastapi import APIRouter

from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import ApiHealth
from researchassistant.api.runtime import ApiRuntime


def build_router(runtime: ApiRuntime, dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health", response_model=ApiHealth)
    def health() -> ApiHealth:
        return ApiHealth()

    return router
