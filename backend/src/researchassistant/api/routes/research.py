"""Research HTTP routes; application dependencies are supplied by assembly."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from researchassistant.api.application_services.configuration import (
    _selected_discovery_providers,
)
from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import (
    CancelResponse,
    ResearchStartInput,
    RunLocator,
)
from researchassistant.api.http_errors import _inspection_http_error
from researchassistant.api.live_service import LiveRunRequest, LiveRunSnapshot, LiveStartResult
from researchassistant.api.runtime import ApiRuntime
from researchassistant.api.security import redact_text
from researchassistant.contracts.models import ResearchControls, ResearchMode
from researchassistant.storage.sqlite_policy import DatabaseBusyError
from researchassistant.storage.store import DatabaseCompatibilityError


def build_router(runtime: ApiRuntime, dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.post("/api/research/start", response_model=LiveStartResult)
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
        database = payload.db_path or str(dependencies.prepare_default_database())
        try:
            request = LiveRunRequest(
                model_profile=payload.model_profile,
                stage_models=payload.stage_models,
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
                    metadata_depth=payload.metadata_depth,
                    seed_expansion_enabled=payload.seed_expansion_enabled,
                    scholarly_search_mode=payload.scholarly_search_mode,
                    discovery_providers=_selected_discovery_providers(
                        use_serpsearch=payload.use_serpsearch,
                        use_exa=payload.use_exa,
                        use_openalex=payload.use_openalex,
                        use_arxiv=payload.use_arxiv,
                        use_pubmed=payload.use_pubmed,
                    ),
                ),
                directions=payload.directions(),
                crossref_enabled=payload.use_crossref,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Invalid request fields.") from exc
        with runtime.lifecycle.admission():
            return runtime.controller.start(request)

    @router.get("/api/research/{run_id}", response_model=LiveRunSnapshot)
    def research_snapshot(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> LiveRunSnapshot:
        try:
            return runtime.controller.snapshot(db_path, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Research run not found.") from exc
        except (DatabaseCompatibilityError, DatabaseBusyError) as exc:
            raise _inspection_http_error(exc) from exc

    @router.post("/api/research/{run_id}/cancel", response_model=CancelResponse)
    def cancel_research(run_id: UUID, payload: RunLocator) -> CancelResponse:
        try:
            message = runtime.controller.cancel(payload.db_path, run_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=redact_text(exc)) from exc
        return CancelResponse(message=message)

    return router
