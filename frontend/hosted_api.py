"""Authenticated private FastAPI boundary for the hosted product."""

import os
from collections.abc import Mapping
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from hosted import (
    AuthenticatedUser,
    CredentialName,
    HostedAuthenticationError,
    HostedConflictError,
    HostedError,
    HostedHistory,
    HostedOwnershipError,
    HostedRepository,
    HostedResearchRequest,
    HostedRun,
    HostedRunDetail,
    HostedSettings,
    InMemoryHostedRepository,
    MigrationBundle,
    MigrationResult,
    ProviderCredentialResponse,
    ProviderCredentialUpdate,
    SupabaseJWTVerifier,
    build_repository_from_environment,
)
from models import StrictModel


class HostedHealth(StrictModel):
    status: str = "ok"
    service: str = "researchassistant-api"
    api_version: str = "hosted-v1"


class AuthMeResponse(StrictModel):
    user: AuthenticatedUser


class HostedRunAccepted(StrictModel):
    run_id: UUID
    status: str
    message: str


def build_auth_verifier_from_environment(
    environ: Mapping[str, str] | None = None,
) -> SupabaseJWTVerifier | None:
    """Build JWT verification from private API configuration only."""
    values = os.environ if environ is None else environ
    secret = values.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        return None
    supabase_url = values.get("SUPABASE_URL", "").rstrip("/")
    issuer = f"{supabase_url}/auth/v1" if supabase_url else None
    return SupabaseJWTVerifier(secret, issuer=issuer)


def create_hosted_app(
    *,
    repository: HostedRepository | None = None,
    verifier: SupabaseJWTVerifier | None = None,
    allowed_origins: tuple[str, ...] = (),
) -> FastAPI:
    """Create the private API with injectable typed boundaries for tests."""
    selected_repository = repository or build_repository_from_environment()
    selected_verifier = verifier or build_auth_verifier_from_environment()
    app = FastAPI(title="ResearchAssistant hosted API", version="hosted-v1")
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Authorization", "Content-Type"],
        )

    def current_user(request: Request) -> AuthenticatedUser:
        """Require a verified bearer token for every account-owned route."""
        if selected_verifier is None:
            raise HTTPException(status_code=503, detail="Hosted authentication is not configured.")
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.casefold() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="A valid bearer token is required.")
        try:
            return selected_verifier.verify(token)
        except HostedAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_dependency = Annotated[AuthenticatedUser, Depends(current_user)]

    def repository_error(exc: HostedError) -> HTTPException:
        """Map private persistence errors without leaking provider or secret details."""
        if isinstance(exc, HostedOwnershipError):
            return HTTPException(status_code=404, detail="Research run not found.")
        if isinstance(exc, HostedConflictError):
            return HTTPException(status_code=409, detail="The hosted operation is no longer valid.")
        return HTTPException(
            status_code=502,
            detail="Hosted persistence is temporarily unavailable.",
        )

    @app.get("/v1/health", response_model=HostedHealth)
    def health() -> HostedHealth:
        return HostedHealth()

    @app.get("/v1/auth/me", response_model=AuthMeResponse)
    def me(user: user_dependency) -> AuthMeResponse:
        return AuthMeResponse(user=user)

    @app.post("/v1/research", response_model=HostedRunAccepted, status_code=202)
    def start_research(
        payload: HostedResearchRequest,
        user: user_dependency,
    ) -> HostedRunAccepted:
        try:
            run = selected_repository.create_run(user.subject, payload)
        except HostedError as exc:
            raise repository_error(exc) from exc
        return HostedRunAccepted(run_id=run.run_id, status=run.status, message=run.message)

    @app.get("/v1/research/{run_id}", response_model=HostedRunDetail)
    def research_detail(run_id: UUID, user: user_dependency) -> HostedRunDetail:
        try:
            return selected_repository.get_detail(user.subject, run_id)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.post("/v1/research/{run_id}/cancel", response_model=HostedRun)
    def cancel_research(run_id: UUID, user: user_dependency) -> HostedRun:
        try:
            return selected_repository.cancel_run(user.subject, run_id)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.get("/v1/history", response_model=HostedHistory)
    def history(
        user: user_dependency,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> HostedHistory:
        try:
            return selected_repository.list_history(user.subject, limit)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.get("/v1/settings", response_model=HostedSettings)
    def settings(user: user_dependency) -> HostedSettings:
        try:
            return selected_repository.get_settings(user.subject)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.put("/v1/settings", response_model=HostedSettings)
    def update_settings(payload: HostedSettings, user: user_dependency) -> HostedSettings:
        try:
            return selected_repository.save_settings(user.subject, payload)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.get("/v1/providers/credentials", response_model=ProviderCredentialResponse)
    def credential_metadata(user: user_dependency) -> ProviderCredentialResponse:
        try:
            return selected_repository.credential_metadata(user.subject)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.put("/v1/providers/credentials", response_model=ProviderCredentialResponse)
    def update_credentials(
        payload: ProviderCredentialUpdate,
        user: user_dependency,
    ) -> ProviderCredentialResponse:
        try:
            return selected_repository.save_credentials(user.subject, payload)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.delete("/v1/providers/credentials/{name}", response_model=ProviderCredentialResponse)
    def clear_credential(name: CredentialName, user: user_dependency) -> ProviderCredentialResponse:
        try:
            return selected_repository.clear_credential(user.subject, name)
        except HostedError as exc:
            raise repository_error(exc) from exc

    @app.post("/v1/migrations/local-history", response_model=MigrationResult)
    def import_local_history(
        payload: MigrationBundle,
        user: user_dependency,
    ) -> MigrationResult:
        try:
            return selected_repository.import_history(user.subject, payload)
        except HostedError as exc:
            raise repository_error(exc) from exc

    return app


def create_test_hosted_app(verifier: SupabaseJWTVerifier) -> FastAPI:
    """Create an isolated in-memory app for regression tests."""
    return create_hosted_app(repository=InMemoryHostedRepository(), verifier=verifier)
