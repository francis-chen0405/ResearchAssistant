"""Persist cooperative cancellation without loading historical execution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from researchassistant.contracts.models import RunCancellationRequest
from researchassistant.storage.store import insert_cancellation_request, read_run


def _phase9_utc_now() -> datetime:
    return datetime.now(UTC)


def request_run_cancellation(
    db_path: str | Path,
    run_id: UUID,
    *,
    reason: str = "cancellation requested by user",
    requested_at: datetime | None = None,
) -> RunCancellationRequest:
    """Persist a cancellation request that is honored at the next stage boundary."""
    path = str(Path(db_path).resolve())
    # Cooperative cancellation intentionally writes while the worker retains its
    # process lock. It must never initialize or migrate that worker's database.
    from researchassistant.storage.store import DatabaseCompatibilityError, open_read_only_store

    try:
        with open_read_only_store(path) as store:
            read_run(store.connection, run_id)
    except DatabaseCompatibilityError as exc:
        raise ValueError("Cancellation requires an initialized compatible database") from exc
    request = RunCancellationRequest(
        run_id=run_id,
        requested_at=requested_at or _phase9_utc_now(),
        reason=reason,
    )
    return insert_cancellation_request(path, request)
