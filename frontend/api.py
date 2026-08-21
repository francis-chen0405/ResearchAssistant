"""Loopback-only typed HTTP adapter for the Next.js live product."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, MutableMapping
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field, SecretStr, model_validator
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from agents.v2_final_output import V2_FINAL_OUTPUT_ARTIFACT_KEY
from agents.v2_reviewer_ledger import V2_REVIEWER_LEDGER_ARTIFACT_KEY
from credential_store import (
    KeychainUnavailableError,
    ProviderCredentials,
    apply_credentials_to_environment,
    load_saved_credentials_into_environment,
    save_credentials,
)
from frontend.live_service import (
    DEFAULT_LIVE_DB,
    LiveHistoryItem,
    LiveResearchController,
    LiveRunRequest,
    LiveRunSnapshot,
    LiveStartResult,
    ResearchTrail,
    prepare_default_database,
)
from frontend.security import redact_text
from frontend.service_manager import ServiceDiagnostic, WigoloServiceManager
from models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirections,
    ResearchMode,
    StrictModel,
    V2EvidenceAnalystSourceResult,
    V2FinalResearchOutput,
    V2ReviewerLedgerBatchResult,
)
from store import open_read_only_store, read_v2_artifact

API_HOST = "127.0.0.1"
API_PORT = 8765
WEB_ORIGINS = ("http://127.0.0.1:3000", "http://localhost:3000")
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


class ControllerBoundary(Protocol):
    def configuration_message(self) -> str | None: ...

    def start(self, request: LiveRunRequest) -> LiveStartResult: ...

    def snapshot(self, db_path: str | Path, run_id: UUID) -> LiveRunSnapshot: ...

    def cancel(self, db_path: str | Path, run_id: UUID) -> str: ...

    def history(self, db_path: str | Path, *, limit: int = 100) -> tuple[LiveHistoryItem, ...]: ...

    def research_trail(self, db_path: str | Path, run_id: UUID) -> ResearchTrail: ...

    def has_active_runs(self) -> bool: ...


class ServiceBoundary(Protocol):
    def probe(self) -> ServiceDiagnostic: ...

    def start(self) -> ServiceDiagnostic: ...

    def stop(self) -> ServiceDiagnostic: ...

    def owns_running_process(self) -> bool: ...


class ApiRuntime:
    """Explicit application-owned services and secret boundaries."""

    def __init__(
        self,
        *,
        controller: ControllerBoundary,
        services: ServiceBoundary,
        environment: MutableMapping[str, str],
        credential_saver: Callable[[ProviderCredentials], None] = save_credentials,
        credential_applier: Callable[
            [ProviderCredentials, MutableMapping[str, str] | None], None
        ] = apply_credentials_to_environment,
        credential_loader: Callable[[MutableMapping[str, str] | None], bool] = (
            load_saved_credentials_into_environment
        ),
    ) -> None:
        self.controller = controller
        self.services = services
        self.environment = environment
        self.credential_saver = credential_saver
        self.credential_applier = credential_applier
        self.credential_loader = credential_loader


class LoopbackGuardMiddleware(BaseHTTPMiddleware):
    """Reject non-loopback hosts and unexpected browser origins."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...],
    ) -> None:
        super().__init__(app)
        self._allowed_hosts = frozenset(allowed_hosts)
        self._allowed_origins = frozenset(allowed_origins)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.hostname not in self._allowed_hosts:
            return JSONResponse(status_code=403, content={"detail": "Loopback host required."})
        origin = request.headers.get("origin")
        if origin is not None and origin not in self._allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Local origin required."})
        return await call_next(request)


class ApiHealth(StrictModel):
    status: str = "ok"
    product: str = "ResearchAssistant"
    api_version: str = "mlp-4"


class ConfigurationResponse(StrictModel):
    configured: bool
    message: str
    default_db_path: str = Field(min_length=1)
    firecrawl_enabled: bool
    saved_credentials: tuple[str, ...] = ()
    service: ServiceDiagnostic


class CredentialSetupRequest(StrictModel):
    mimo_api_key: SecretStr | None = None
    luna_api_key: SecretStr | None = None
    exa_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    serpsearch_api_key: SecretStr | None = None
    pubmed_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None


class CredentialSetupResponse(StrictModel):
    saved: bool
    configured: bool
    message: str = Field(min_length=1)


def _saved_credential_names(environment: MutableMapping[str, str]) -> tuple[str, ...]:
    """Expose presence only; browser clients never receive credential values."""
    labels = (
        ("mimo", "MIMO_API_KEY"),
        ("openai", "LUNA_API_KEY"),
        ("serpsearch", "SERPSEARCH_API_KEY"),
        ("exa", "EXA_API_KEY"),
        ("openalex", "OPENALEX_API_KEY"),
        ("pubmed", "PUBMED_API_KEY"),
        ("firecrawl", "FIRECRAWL_API_KEY"),
    )
    return tuple(label for label, key in labels if environment.get(key, "").strip())


class ResearchStartInput(StrictModel):
    raw_claim: str = Field(min_length=1)
    acknowledged_public: bool
    db_path: str | None = None
    run_id: UUID | None = None
    max_tokens: int = Field(default=200_000, ge=1, le=300_000)
    max_cost_usd: Decimal = Field(default=Decimal("0.15"), gt=0, le=Decimal("1.00"))
    max_llm_calls: int = Field(default=160, ge=1, le=160)
    support_enabled: bool = True
    challenge_enabled: bool = False
    include_counterevidence: bool = False
    sources_per_stance_per_round: Literal[5, 10, 15, 20] = 10
    use_serpsearch: bool = True
    use_exa: bool = True
    use_openalex: bool = True
    use_arxiv: bool = False
    use_pubmed: bool = False
    use_crossref: bool = True

    @model_validator(mode="after")
    def validate_research_directions(self) -> ResearchStartInput:
        if not self.support_enabled and not (
            self.challenge_enabled or self.include_counterevidence
        ):
            raise ValueError("Enable Support, Challenge, or both research directions.")
        return self

    def directions(self) -> ResearchDirections:
        """Resolve the legacy counterevidence control without changing old clients."""
        return ResearchDirections(
            support_enabled=self.support_enabled,
            challenge_enabled=self.challenge_enabled or self.include_counterevidence,
        )


class RunLocator(StrictModel):
    db_path: str = Field(min_length=1)


class CancelResponse(StrictModel):
    cancelled: bool = True
    message: str = Field(min_length=1)


class HistoryResponse(StrictModel):
    items: tuple[LiveHistoryItem, ...]


class V2EvidenceDisplayItem(StrictModel):
    """Read-only evidence detail suitable for the v2 result page."""

    source_id: UUID
    title: str | None = None
    source_url: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    recommendation_status: str = Field(min_length=1)
    selection_rationale: str | None = None
    gap_ids: tuple[str, ...] = ()
    evidence_summary: str = Field(min_length=1)
    supporting_proposition: str = Field(min_length=1)
    quote_passage: str = Field(min_length=1)
    limitations: tuple[str, ...] = ()
    validation_status: str = Field(min_length=1)


class V2EvidenceDisplay(StrictModel):
    run_id: UUID
    items: tuple[V2EvidenceDisplayItem, ...]


def _build_v2_evidence_display(
    output: V2FinalResearchOutput,
    reviewer: V2ReviewerLedgerBatchResult,
) -> V2EvidenceDisplay:
    """Project persisted v2 evidence into a read-only result-page view."""
    sources = {source.source_id: source for source in output.all_surviving_sources}
    analyst_results: dict[UUID, V2EvidenceAnalystSourceResult] = {
        source.source_id: source for source in reviewer.analyst_result.source_results
    }
    selections = {
        status.source_id: status
        for status in reviewer.analyst_result.input.queue_result.source_statuses
    }
    items: list[V2EvidenceDisplayItem] = []
    for review in reviewer.source_results:
        analyst = analyst_results[review.source_id]
        if analyst.candidate is None or analyst.assessment is None:
            continue
        source = sources[review.source_id]
        selection = selections[review.source_id]
        limitations = (
            *analyst.assessment.material_limitations,
            *analyst.assessment.inferential_boundaries,
        )
        items.append(
            V2EvidenceDisplayItem(
                source_id=source.source_id,
                title=source.title,
                source_url=source.source_url,
                source_family=review.provenance.source_family_id,
                direction=source.direction.value,
                recommendation_status=(
                    "Recommended for deeper analysis"
                    if selection.recommended
                    else "Survived source evaluation"
                ),
                selection_rationale=selection.selection_rationale,
                gap_ids=selection.gap_ids,
                evidence_summary=analyst.assessment.reasoning,
                supporting_proposition=analyst.assessment.narrowest_supported_proposition,
                quote_passage=analyst.candidate.extracted_quote_block,
                limitations=limitations,
                validation_status=review.state.value,
            )
        )
    return V2EvidenceDisplay(run_id=output.run_id, items=tuple(items))


def create_default_runtime() -> ApiRuntime:
    environment = os.environ
    controller = LiveResearchController(environment=environment)
    services = WigoloServiceManager(base_environment=environment)
    return ApiRuntime(controller=controller, services=services, environment=environment)


def create_app(
    runtime: ApiRuntime,
    *,
    load_keychain_on_start: bool,
    allowed_hosts: tuple[str, ...] = LOOPBACK_HOSTS,
    allowed_origins: tuple[str, ...] = WEB_ORIGINS,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if load_keychain_on_start:
            runtime.credential_loader(runtime.environment)
        prepare_default_database()
        yield
        if runtime.services.owns_running_process() and not runtime.controller.has_active_runs():
            runtime.services.stop()

    app = FastAPI(
        title="ResearchAssistant local API",
        version="mlp-4",
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
    )

    @app.get("/api/health", response_model=ApiHealth)
    def health() -> ApiHealth:
        return ApiHealth()

    @app.get("/api/configuration", response_model=ConfigurationResponse)
    def configuration() -> ConfigurationResponse:
        config_message = runtime.controller.configuration_message()
        return ConfigurationResponse(
            configured=config_message is None,
            message=config_message or "MiMo and your selected research sources are connected.",
            default_db_path=str(prepare_default_database()),
            firecrawl_enabled=bool(runtime.environment.get("FIRECRAWL_API_KEY", "").strip()),
            saved_credentials=_saved_credential_names(runtime.environment),
            service=runtime.services.probe(),
        )

    @app.post("/api/credentials", response_model=CredentialSetupResponse)
    def store_credentials(payload: CredentialSetupRequest) -> CredentialSetupResponse:
        if not any(
            (
                payload.mimo_api_key,
                payload.luna_api_key,
                payload.serpsearch_api_key,
                payload.exa_api_key,
                payload.openalex_api_key,
                payload.firecrawl_api_key,
                payload.pubmed_api_key,
            )
        ):
            raise HTTPException(status_code=422, detail="Enter at least one API key to save.")
        credentials = ProviderCredentials(
            mimo_api_key=(
                payload.mimo_api_key.get_secret_value()
                if payload.mimo_api_key is not None
                else None
            ),
            luna_api_key=(
                payload.luna_api_key.get_secret_value()
                if payload.luna_api_key is not None
                else None
            ),
            exa_api_key=(
                payload.exa_api_key.get_secret_value() if payload.exa_api_key is not None else None
            ),
            openalex_api_key=(
                payload.openalex_api_key.get_secret_value()
                if payload.openalex_api_key is not None
                else None
            ),
            serpsearch_api_key=(
                payload.serpsearch_api_key.get_secret_value()
                if payload.serpsearch_api_key is not None
                else None
            ),
            pubmed_api_key=(
                payload.pubmed_api_key.get_secret_value()
                if payload.pubmed_api_key is not None
                else None
            ),
            firecrawl_api_key=(
                payload.firecrawl_api_key.get_secret_value()
                if payload.firecrawl_api_key is not None
                else None
            ),
        )
        try:
            runtime.credential_saver(credentials)
            runtime.credential_applier(credentials, runtime.environment)
        except KeychainUnavailableError as exc:
            raise HTTPException(status_code=503, detail=redact_text(exc)) from exc
        config_message = runtime.controller.configuration_message()
        return CredentialSetupResponse(
            saved=True,
            configured=config_message is None,
            message=(
                "Provider keys saved securely in macOS Keychain."
                if config_message is None
                else "Provider keys saved securely in macOS Keychain. "
                + redact_text(config_message)
            ),
        )

    @app.post("/api/research/start", response_model=LiveStartResult)
    def start_research(payload: ResearchStartInput) -> LiveStartResult:
        if not payload.acknowledged_public:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Confirm that the claim is public and non-sensitive and that you will "
                    "review the result."
                ),
            )
        if not (
            payload.use_serpsearch
            or payload.use_exa
            or payload.use_openalex
            or payload.use_arxiv
            or payload.use_pubmed
        ):
            raise HTTPException(status_code=422, detail="Select at least one research source.")
        database = payload.db_path or str(prepare_default_database())
        request = LiveRunRequest(
            raw_claim=payload.raw_claim,
            db_path=database,
            run_id=payload.run_id,
            max_tokens=payload.max_tokens,
            max_cost_usd=payload.max_cost_usd,
            max_llm_calls=payload.max_llm_calls,
            research_controls=ResearchControls(
                research_mode=(
                    ResearchMode.BALANCED
                    if payload.directions().challenge_enabled
                    else ResearchMode.FOCUSED
                ),
                sources_per_stance_per_round=payload.sources_per_stance_per_round,
                discovery_providers=tuple(
                    provider
                    for provider, enabled in (
                        (DiscoveryProvider.SERPSEARCH, payload.use_serpsearch),
                        (DiscoveryProvider.EXA, payload.use_exa),
                        (DiscoveryProvider.OPENALEX, payload.use_openalex),
                        (DiscoveryProvider.ARXIV, payload.use_arxiv),
                        (DiscoveryProvider.PUBMED, payload.use_pubmed),
                    )
                    if enabled
                ),
            ),
            directions=payload.directions(),
            crossref_enabled=payload.use_crossref,
        )
        return runtime.controller.start(request)

    @app.get("/api/research/{run_id}", response_model=LiveRunSnapshot)
    def research_snapshot(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> LiveRunSnapshot:
        try:
            return runtime.controller.snapshot(db_path, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Research run not found.") from exc

    @app.post("/api/research/{run_id}/cancel", response_model=CancelResponse)
    def cancel_research(run_id: UUID, payload: RunLocator) -> CancelResponse:
        try:
            message = runtime.controller.cancel(payload.db_path, run_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=redact_text(exc)) from exc
        return CancelResponse(message=message)

    @app.get("/api/research/{run_id}/trail", response_model=ResearchTrail)
    def research_trail(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> ResearchTrail:
        try:
            return runtime.controller.research_trail(db_path, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Research run not found.") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=redact_text(exc)) from exc

    @app.get("/api/research/{run_id}/v2-result", response_model=V2FinalResearchOutput)
    def v2_result(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> V2FinalResearchOutput:
        try:
            with open_read_only_store(db_path) as store:
                artifact = read_v2_artifact(store.connection, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY)
            if artifact.artifact_type != V2FinalResearchOutput.__name__:
                raise ValueError("v2 final-output artifact has an unexpected type")
            return V2FinalResearchOutput.model_validate_json(artifact.payload_json)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="V2 research result not found.") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=redact_text(exc)) from exc

    @app.get("/api/research/{run_id}/v2-evidence", response_model=V2EvidenceDisplay)
    def v2_evidence(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> V2EvidenceDisplay:
        try:
            with open_read_only_store(db_path) as store:
                final_artifact = read_v2_artifact(
                    store.connection, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY
                )
                reviewer_artifact = read_v2_artifact(
                    store.connection, run_id, V2_REVIEWER_LEDGER_ARTIFACT_KEY
                )
            output = V2FinalResearchOutput.model_validate_json(final_artifact.payload_json)
            reviewer = V2ReviewerLedgerBatchResult.model_validate_json(
                reviewer_artifact.payload_json
            )
            return _build_v2_evidence_display(output, reviewer)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="V2 evidence details not found.") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=redact_text(exc)) from exc

    @app.get("/api/history", response_model=HistoryResponse)
    def history(
        db_path: str = Query(default=str(DEFAULT_LIVE_DB), min_length=1),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> HistoryResponse:
        try:
            return HistoryResponse(items=runtime.controller.history(db_path, limit=limit))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=redact_text(exc)) from exc

    @app.get("/api/service", response_model=ServiceDiagnostic)
    def service_status() -> ServiceDiagnostic:
        return runtime.services.probe()

    @app.post("/api/service/start", response_model=ServiceDiagnostic)
    def start_service() -> ServiceDiagnostic:
        return runtime.services.start()

    @app.post("/api/service/stop", response_model=ServiceDiagnostic)
    def stop_service() -> ServiceDiagnostic:
        if runtime.controller.has_active_runs():
            raise HTTPException(
                status_code=409,
                detail="The owned service cannot stop while research is active.",
            )
        return runtime.services.stop()

    return app


runtime = create_default_runtime()
app = create_app(runtime, load_keychain_on_start=True)


def main() -> None:
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")


if __name__ == "__main__":
    main()
