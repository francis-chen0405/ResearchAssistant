"""History HTTP routes; application dependencies are supplied by assembly."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import (
    HistoryResponse,
)
from researchassistant.api.http_errors import _inspection_http_error
from researchassistant.api.runtime import ApiRuntime
from researchassistant.storage.history_import import HistoryImportResult
from researchassistant.storage.store import DatabaseCompatibilityError


def build_router(runtime: ApiRuntime, dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.post("/api/history/import", response_model=HistoryImportResult)
    def copy_history(source: str = Query(min_length=1)) -> HistoryImportResult:
        with runtime.lifecycle.idle_change(
            runtime.controller.has_active_runs, message="Wait for active research to finish."
        ):
            try:
                return dependencies.import_history(Path(source))
            except (DatabaseCompatibilityError, OSError, ValueError) as exc:
                if isinstance(exc, DatabaseCompatibilityError) and exc.result.retryable:
                    raise _inspection_http_error(exc) from exc
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "History import failed; check the source database and ensure it is idle."
                    ),
                ) from exc

    @router.get("/api/history", response_model=HistoryResponse)
    def history(
        db_path: str = Query(default=str(dependencies.default_db_path), min_length=1),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> HistoryResponse:
        try:
            return HistoryResponse(items=runtime.controller.history(db_path, limit=limit))
        except Exception as exc:
            raise _inspection_http_error(exc) from exc

    return router
