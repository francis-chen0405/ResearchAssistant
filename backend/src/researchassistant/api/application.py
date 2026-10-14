"""Single application assembly, authentication, sanitized errors and lifespan owner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from researchassistant.api.constants import (
    API_VERSION,
    CREDENTIAL_ACCESS_MESSAGE,
    LOOPBACK_HOSTS,
    WEB_ORIGINS,
)
from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_security import LoopbackGuardMiddleware
from researchassistant.api.live_lifecycle import LifecycleConflict
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
        yield
        if runtime.services.owns_running_process():
            try:
                with runtime.lifecycle.idle_change(
                    runtime.controller.has_active_runs,
                    message="The owned service cannot stop while research is active.",
                ):
                    runtime.services.stop()
            except LifecycleConflict:
                pass

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

    app.include_router(credentials.build_router(runtime, dependencies))
    app.include_router(history.build_router(runtime, dependencies))
    app.include_router(settings.build_router(runtime, dependencies))
    app.include_router(research.build_router(runtime, dependencies))
    app.include_router(inspection.build_router(runtime, dependencies))
    app.include_router(services.build_router(runtime, dependencies))
    app.include_router(health.build_router(runtime, dependencies))
    return app
