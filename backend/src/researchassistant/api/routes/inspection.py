"""Inspection HTTP routes; application dependencies are supplied by assembly."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from researchassistant.api.application_services.result_reads import read_evidence, read_result
from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_errors import _inspection_http_error
from researchassistant.api.inspection_contracts import V2EvidenceDisplay
from researchassistant.api.live_service import ResearchTrail
from researchassistant.api.runtime import ApiRuntime
from researchassistant.contracts.models import V2FinalResearchOutput
from researchassistant.contracts.source_leads import SourceLeadsPage
from researchassistant.storage.source_leads import read_source_leads


def build_router(runtime: ApiRuntime, dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.get("/api/research/{run_id}/trail", response_model=ResearchTrail)
    def research_trail(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> ResearchTrail:
        try:
            return runtime.controller.research_trail(db_path, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Research run not found.") from exc
        except Exception as exc:
            raise _inspection_http_error(exc) from exc

    @router.get("/api/research/{run_id}/v2-result", response_model=V2FinalResearchOutput)
    def v2_result(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> V2FinalResearchOutput:
        try:
            return read_result(db_path, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="V2 research result not found.") from exc
        except Exception as exc:
            raise _inspection_http_error(exc) from exc

    @router.get("/api/research/{run_id}/v2-evidence", response_model=V2EvidenceDisplay)
    def v2_evidence(
        run_id: UUID,
        db_path: str = Query(min_length=1),
    ) -> V2EvidenceDisplay:
        try:
            return read_evidence(db_path, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="V2 evidence details not found.") from exc
        except Exception as exc:
            raise _inspection_http_error(exc) from exc

    @router.get("/api/research/{run_id}/source-leads", response_model=SourceLeadsPage)
    def source_leads(
        run_id: UUID,
        db_path: str = Query(min_length=1),
        offset: int = Query(default=0, ge=0, le=6000),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> SourceLeadsPage:
        try:
            return read_source_leads(db_path, run_id, offset=offset, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Research run not found.") from exc
        except Exception as exc:
            raise _inspection_http_error(exc) from exc

    return router
