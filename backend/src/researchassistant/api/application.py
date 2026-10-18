"""Single application assembly, authentication, sanitized errors and lifespan owner."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.dependencies.utils import get_flat_params
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from researchassistant.api.constants import (
    API_VERSION,
    CREDENTIAL_ACCESS_MESSAGE,
    LOOPBACK_HOSTS,
    WEB_ORIGINS,
)
from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import RequestErrorResponse
from researchassistant.api.http_security import LoopbackGuardMiddleware
from researchassistant.api.live_lifecycle import LifecycleConflict
from researchassistant.api.live_service import LiveResearchController
from researchassistant.api.routes import (
    credentials,
    health,
    history,
    inspection,
    research,
    services,
    settings,
)
from researchassistant.api.runtime import ApiRuntime
from researchassistant.platform_support.credential_store import KeychainUnavailableError


def create_app(
    runtime: ApiRuntime,
    *,
    load_keychain_on_start: bool,
    allowed_hosts: tuple[str, ...] = LOOPBACK_HOSTS,
    allowed_origins: tuple[str, ...] = WEB_ORIGINS,
    session_token: str | None = None,
    shutdown_controller_on_exit: bool = True,
    dependencies: ApiDependencies | None = None,
) -> FastAPI:
    dependencies = dependencies or ApiDependencies()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if load_keychain_on_start:
            try:
                runtime.credential_loader(runtime.environment)
            except KeychainUnavailableError:
                runtime.credential_error = CREDENTIAL_ACCESS_MESSAGE
        dependencies.prepare_default_database()
        try:
            yield
        finally:
            if shutdown_controller_on_exit and isinstance(
                runtime.controller, LiveResearchController
            ):
                completed = await asyncio.to_thread(runtime.controller.shutdown, timeout=90)
                if not completed:
                    raise RuntimeError("API shutdown could not drain research within its deadline")
            if shutdown_controller_on_exit and runtime.services.owns_running_process():
                with runtime.lifecycle.idle_change(
                    runtime.controller.has_active_runs,
                    message="The owned service cannot stop while research is active.",
                ):
                    runtime.services.stop()

    app = FastAPI(
        title="ResearchAssistant local API",
        version=API_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(
        LoopbackGuardMiddleware,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
        session_token=session_token,
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's default response includes raw input, including password fields.
        return JSONResponse(status_code=422, content={"detail": "Invalid request fields."})

    @app.exception_handler(LifecycleConflict)
    async def lifecycle_conflict(_: Request, exc: LifecycleConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    for module in (credentials, history, settings, research, inspection, services, health):
        router = module.build_router(runtime, dependencies)
        for route in router.routes:
            if isinstance(route, APIRoute) and (
                route.body_field is not None or get_flat_params(route.dependant)
            ):
                # Supply metadata before inclusion builds the response fields.
                # Match FastAPI's validation surface, including dependencies.
                route.responses[422] = {
                    "model": RequestErrorResponse,
                    "description": "Validation Error",
                }
        app.include_router(router)
    return app
