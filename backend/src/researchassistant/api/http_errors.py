"""Shared redacted and retryable inspection error mapping."""

from __future__ import annotations

from fastapi import HTTPException

from researchassistant.api.security import redact_text
from researchassistant.storage.sqlite_policy import is_busy_error
from researchassistant.storage.store import DatabaseCompatibilityError


def _inspection_http_error(exc: Exception) -> HTTPException:
    """Transient contention has a retryable diagnostic distinct from invalid data."""
    busy = is_busy_error(exc) or (
        isinstance(exc, DatabaseCompatibilityError) and exc.result.retryable
    )
    if busy:
        return HTTPException(
            status_code=503,
            headers={"Retry-After": "1"},
            detail={
                "issue": "busy",
                "retryable": True,
                "message": "Database is busy. Retry inspection shortly.",
            },
        )
    if isinstance(exc, DatabaseCompatibilityError):
        return HTTPException(
            status_code=400,
            detail={
                "issue": exc.result.issue,
                "retryable": False,
                "message": redact_text(exc),
            },
        )
    return HTTPException(status_code=400, detail=redact_text(exc))
