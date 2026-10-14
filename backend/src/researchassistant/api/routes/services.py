"""Services HTTP routes; application dependencies are supplied by assembly."""

from __future__ import annotations

from fastapi import APIRouter

from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.runtime import ApiRuntime
from researchassistant.api.service_manager import ServiceDiagnostic


def build_router(runtime: ApiRuntime, dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.get("/api/service", response_model=ServiceDiagnostic)
    def service_status() -> ServiceDiagnostic:
        return runtime.services.probe()

    @router.post("/api/service/start", response_model=ServiceDiagnostic)
    def start_service() -> ServiceDiagnostic:
        # Service start remains available during research and repeated starts are
        # serialized by the manager; stop cannot overtake an in-flight start.
        with runtime.lifecycle.admission():
            return runtime.services.start()

    @router.post("/api/service/stop", response_model=ServiceDiagnostic)
    def stop_service() -> ServiceDiagnostic:
        with runtime.lifecycle.idle_change(
            runtime.controller.has_active_runs,
            message="The owned service cannot stop while research is active.",
        ):
            return runtime.services.stop()

    return router
