"""Serialized model reservation/completion and immutable accounting identity."""

from __future__ import annotations

import json
import math
import sqlite3
from decimal import Decimal
from uuid import UUID

from researchassistant.common.money import (
    add_usd,
    canonical_usd,
    parse_canonical_usd,
    parse_exact_usd,
)
from researchassistant.contracts.models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
)
from researchassistant.storage.store_types import (
    DatabaseReader as DatabaseReader,
)
from researchassistant.storage.store_types import ReadConnectionFactory, WriteConnectionFactory
from researchassistant.storage.store_types import (
    _dt_to_iso as _dt_to_iso,
)
from researchassistant.storage.store_types import (
    _iso_to_dt as _iso_to_dt,
)
from researchassistant.storage.store_types import (
    _read_execute as _read_execute,
)


class ModelAttemptBudgetError(RuntimeError):
    """Raised before a provider call when its persisted run budget is exhausted."""


_RESERVATION_IDENTITY_FIELDS = (
    "attempt_id",
    "run_id",
    "operation_id",
    "stage",
    "output_type",
    "model_alias",
    "pinned_model_snapshot",
    "route_index",
    "attempt_number",
    "input_artifact_ids",
    "started_at",
    "reserved_tokens",
    "reserved_cost_usd",
    "retry_reason",
    "escalation_reason",
)


def _validated_route_attempt(attempt: ModelRouteAttempt) -> ModelRouteAttempt:
    # Pydantic deliberately trusts existing instances and model_copy updates.
    # Rebuild both levels from raw fields to re-run every persistence invariant.
    values = dict(attempt.__dict__)
    if isinstance(attempt.usage, ModelUsageMetadata):
        values["usage"] = dict(attempt.usage.__dict__)
    validated = ModelRouteAttempt.model_validate(values)
    if validated.latency_ms is not None and not math.isfinite(validated.latency_ms):
        raise ValueError("model attempt latency must be finite")
    if validated.output_json is not None:
        try:
            json.loads(validated.output_json)
        except ValueError as exc:
            raise ValueError("model attempt output must be serialized JSON") from exc
    if validated.usage is not None and all(
        value is None for value in validated.usage.__dict__.values()
    ):
        validated = validated.model_copy(update={"usage": None})
    return validated


def _check_reservation_identity(existing: ModelRouteAttempt, incoming: ModelRouteAttempt) -> None:
    if any(
        getattr(existing, field) != getattr(incoming, field)
        for field in _RESERVATION_IDENTITY_FIELDS
    ):
        raise sqlite3.IntegrityError(
            f"model attempt {incoming.attempt_id} reservation identity conflicts"
        )


def validate_model_route_attempt_identity(
    existing: ModelRouteAttempt, expected: ModelRouteAttempt
) -> None:
    """Bind caller replay to its expected reservation without changing storage.

    A caller intentionally resuming a stored attempt supplies its original start
    in `expected`; all other identity and reservation fields come from the request.
    """
    _check_reservation_identity(
        _validated_route_attempt(existing), _validated_route_attempt(expected)
    )


def reserve_model_route_attempt(
    db_path: str,
    attempt: ModelRouteAttempt,
    *,
    max_model_calls: int,
    max_total_tokens: int | None = None,
    max_total_cost_usd: Decimal | None = None,
    _connect: WriteConnectionFactory,
) -> ModelRouteAttempt:
    attempt = _validated_route_attempt(attempt)
    if attempt.status is not ModelAttemptStatus.RUNNING:
        raise ValueError("only running model attempts may be reserved")
    exact_cost_ceiling = (
        parse_exact_usd(max_total_cost_usd) if max_total_cost_usd is not None else None
    )
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM model_route_attempts WHERE attempt_id = ?",
            (str(attempt.attempt_id),),
        ).fetchone()
        if row is not None:
            existing = _row_to_model_route_attempt(row)
            _check_reservation_identity(existing, attempt)
            conn.commit()
            return existing
        count = conn.execute(
            "SELECT COUNT(*) FROM model_route_attempts WHERE run_id = ?",
            (str(attempt.run_id),),
        ).fetchone()[0]
        if count >= max_model_calls:
            raise ModelAttemptBudgetError(
                f"model call budget {max_model_calls} exhausted for run {attempt.run_id}"
            )
        if max_total_tokens is not None:
            reserved_tokens = attempt.reserved_tokens
            if reserved_tokens is None:
                raise ModelAttemptBudgetError(
                    "token budget requires a conservative reservation before every call"
                )
            rows = conn.execute(
                """SELECT attempt_id, status, input_tokens, output_tokens, total_tokens,
                          reserved_tokens
                   FROM model_route_attempts WHERE run_id = ?""",
                (str(attempt.run_id),),
            ).fetchall()
            used_tokens = 0
            for existing_attempt in rows:
                terminal = existing_attempt["status"] != ModelAttemptStatus.RUNNING.value
                actual_tokens = existing_attempt["total_tokens"] if terminal else None
                if (
                    terminal
                    and actual_tokens is None
                    and existing_attempt["input_tokens"] is not None
                    and existing_attempt["output_tokens"] is not None
                ):
                    actual_tokens = (
                        existing_attempt["input_tokens"] + existing_attempt["output_tokens"]
                    )
                exposure = (
                    actual_tokens
                    if actual_tokens is not None
                    else existing_attempt["reserved_tokens"]
                )
                if exposure is None:
                    raise ModelAttemptBudgetError(
                        "model usage is incomplete and the remaining token budget cannot be "
                        f"proven after attempt {existing_attempt['attempt_id']}"
                    )
                used_tokens += exposure
            if used_tokens + reserved_tokens > max_total_tokens:
                raise ModelAttemptBudgetError(
                    f"model token budget {max_total_tokens} cannot reserve the next call"
                )
        if exact_cost_ceiling is not None:
            reserved_cost = attempt.reserved_cost_usd
            if reserved_cost is None:
                raise ModelAttemptBudgetError(
                    "cost budget requires a conservative reservation before every call"
                )
            rows = conn.execute(
                """SELECT attempt_id, status, cost_usd, reserved_cost_usd,
                          cost_usd_exact, reserved_cost_usd_exact
                   FROM model_route_attempts WHERE run_id = ?""",
                (str(attempt.run_id),),
            ).fetchall()
            used_cost = Decimal("0")
            for existing_attempt in rows:
                terminal = existing_attempt["status"] != ModelAttemptStatus.RUNNING.value
                cost_text = existing_attempt["cost_usd_exact"]
                reserved_text = existing_attempt["reserved_cost_usd_exact"]
                exposure = None
                if terminal and cost_text is not None:
                    exposure = parse_canonical_usd(cost_text)
                elif terminal and existing_attempt["cost_usd"] is not None:
                    exposure = parse_exact_usd(existing_attempt["cost_usd"])
                elif reserved_text is not None:
                    exposure = parse_canonical_usd(reserved_text)
                elif existing_attempt["reserved_cost_usd"] is not None:
                    exposure = parse_exact_usd(existing_attempt["reserved_cost_usd"])
                if exposure is None:
                    raise ModelAttemptBudgetError(
                        "model usage is incomplete and the remaining cost budget cannot be "
                        f"proven after attempt {existing_attempt['attempt_id']}"
                    )
                used_cost = add_usd(used_cost, exposure)
            if add_usd(used_cost, reserved_cost) > exact_cost_ceiling:
                raise ModelAttemptBudgetError(
                    f"model cost budget {exact_cost_ceiling} cannot reserve the next call"
                )
        _insert_model_route_attempt_row(conn, attempt)
        conn.commit()
        return attempt
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def finish_model_route_attempt(
    db_path: str, attempt: ModelRouteAttempt, *, _connect: WriteConnectionFactory
) -> None:
    attempt = _validated_route_attempt(attempt)
    if attempt.status is ModelAttemptStatus.RUNNING:
        raise ValueError("finished model attempt cannot remain running")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM model_route_attempts WHERE attempt_id = ?",
            (str(attempt.attempt_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"model attempt {attempt.attempt_id} not found")
        existing = _row_to_model_route_attempt(row)
        _check_reservation_identity(existing, attempt)
        if existing.status is not ModelAttemptStatus.RUNNING:
            if existing != attempt:
                raise sqlite3.IntegrityError(
                    f"model attempt {attempt.attempt_id} already finished differently"
                )
            conn.commit()
            return
        usage = attempt.usage
        conn.execute(
            """UPDATE model_route_attempts SET
                   status = ?, failure_code = ?, failure_reason = ?, ended_at = ?,
                   latency_ms = ?, input_tokens = ?, output_tokens = ?, total_tokens = ?,
                   cached_input_tokens = ?, uncached_input_tokens = ?,
                   cache_write_tokens = ?, usage_cost_basis = ?,
                   cost_usd = NULL, cost_usd_exact = ?, output_json = ?
               WHERE attempt_id = ?""",
            (
                attempt.status.value,
                attempt.failure_code,
                attempt.failure_reason,
                _dt_to_iso(attempt.ended_at),
                attempt.latency_ms,
                usage.input_tokens if usage else None,
                usage.output_tokens if usage else None,
                usage.total_tokens if usage else None,
                usage.cached_input_tokens if usage else None,
                usage.uncached_input_tokens if usage else None,
                usage.cache_write_tokens if usage else None,
                usage.usage_cost_basis.value if usage and usage.usage_cost_basis else None,
                canonical_usd(usage.cost_usd) if usage and usage.cost_usd is not None else None,
                attempt.output_json,
                str(attempt.attempt_id),
            ),
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def read_model_route_attempts(
    db_path: DatabaseReader,
    run_id: UUID,
    operation_id: UUID | None = None,
    *,
    _read_connection: ReadConnectionFactory,
) -> list[ModelRouteAttempt]:
    with _read_connection(db_path) as conn:
        if operation_id is None:
            rows = _read_execute(
                conn,
                """SELECT * FROM model_route_attempts WHERE run_id = ?
                   ORDER BY started_at, operation_id, route_index, attempt_number""",
                (str(run_id),),
            ).fetchall()
        else:
            rows = _read_execute(
                conn,
                """SELECT * FROM model_route_attempts
                   WHERE run_id = ? AND operation_id = ?
                   ORDER BY route_index, attempt_number""",
                (str(run_id), str(operation_id)),
            ).fetchall()
        return [_row_to_model_route_attempt(row) for row in rows]


def _insert_model_route_attempt_row(
    conn: sqlite3.Connection,
    attempt: ModelRouteAttempt,
) -> None:
    usage = attempt.usage
    conn.execute(
        """INSERT INTO model_route_attempts
           (attempt_id, run_id, operation_id, stage, output_type, model_alias,
            pinned_model_snapshot, route_index, attempt_number, input_artifact_ids,
            status, retry_reason, escalation_reason, failure_code, failure_reason,
            started_at, ended_at, latency_ms, reserved_tokens, reserved_cost_usd,
            reserved_cost_usd_exact, input_tokens, output_tokens, total_tokens,
            cached_input_tokens, uncached_input_tokens, cache_write_tokens, usage_cost_basis,
            cost_usd, cost_usd_exact, output_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL,
                   ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
        (
            str(attempt.attempt_id),
            str(attempt.run_id),
            str(attempt.operation_id),
            attempt.stage,
            attempt.output_type,
            attempt.model_alias,
            attempt.pinned_model_snapshot,
            attempt.route_index,
            attempt.attempt_number,
            json.dumps([str(item) for item in attempt.input_artifact_ids]),
            attempt.status.value,
            attempt.retry_reason,
            attempt.escalation_reason,
            attempt.failure_code,
            attempt.failure_reason,
            _dt_to_iso(attempt.started_at),
            _dt_to_iso(attempt.ended_at) if attempt.ended_at else None,
            attempt.latency_ms,
            attempt.reserved_tokens,
            canonical_usd(attempt.reserved_cost_usd)
            if attempt.reserved_cost_usd is not None
            else None,
            usage.input_tokens if usage else None,
            usage.output_tokens if usage else None,
            usage.total_tokens if usage else None,
            usage.cached_input_tokens if usage else None,
            usage.uncached_input_tokens if usage else None,
            usage.cache_write_tokens if usage else None,
            usage.usage_cost_basis.value if usage and usage.usage_cost_basis else None,
            canonical_usd(usage.cost_usd) if usage and usage.cost_usd is not None else None,
            attempt.output_json,
        ),
    )


def _row_to_model_route_attempt(row: sqlite3.Row) -> ModelRouteAttempt:
    row_columns = set(row.keys())
    cached_input_tokens = (
        row["cached_input_tokens"] if "cached_input_tokens" in row_columns else None
    )
    uncached_input_tokens = (
        row["uncached_input_tokens"] if "uncached_input_tokens" in row_columns else None
    )
    cache_write_tokens = row["cache_write_tokens"] if "cache_write_tokens" in row_columns else None
    usage_cost_basis = row["usage_cost_basis"] if "usage_cost_basis" in row_columns else None
    usage_values = (
        row["input_tokens"],
        cached_input_tokens,
        uncached_input_tokens,
        cache_write_tokens,
        usage_cost_basis,
        row["output_tokens"],
        row["total_tokens"],
        row["cost_usd_exact"],
        row["cost_usd"],
    )
    usage = None
    if any(value is not None for value in usage_values):
        usage = ModelUsageMetadata(
            input_tokens=row["input_tokens"],
            cached_input_tokens=cached_input_tokens,
            uncached_input_tokens=uncached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            usage_cost_basis=usage_cost_basis,
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            cost_usd=(
                parse_canonical_usd(row["cost_usd_exact"])
                if row["cost_usd_exact"] is not None
                else parse_exact_usd(row["cost_usd"])
                if row["cost_usd"] is not None
                else None
            ),
        )
    return ModelRouteAttempt(
        run_id=UUID(row["run_id"]),
        operation_id=UUID(row["operation_id"]),
        attempt_id=UUID(row["attempt_id"]),
        stage=row["stage"],
        output_type=row["output_type"],
        model_alias=row["model_alias"],
        pinned_model_snapshot=row["pinned_model_snapshot"],
        route_index=row["route_index"],
        attempt_number=row["attempt_number"],
        input_artifact_ids=tuple(UUID(value) for value in json.loads(row["input_artifact_ids"])),
        status=row["status"],
        retry_reason=row["retry_reason"],
        escalation_reason=row["escalation_reason"],
        failure_code=row["failure_code"],
        failure_reason=row["failure_reason"],
        started_at=_iso_to_dt(row["started_at"]),
        ended_at=_iso_to_dt(row["ended_at"]) if row["ended_at"] else None,
        latency_ms=row["latency_ms"],
        reserved_tokens=row["reserved_tokens"],
        reserved_cost_usd=(
            parse_canonical_usd(row["reserved_cost_usd_exact"])
            if row["reserved_cost_usd_exact"] is not None
            else parse_exact_usd(row["reserved_cost_usd"])
            if row["reserved_cost_usd"] is not None
            else None
        ),
        usage=usage,
        output_json=row["output_json"],
    )


# Preserve the historical public class identity for persisted consumers.
ModelAttemptBudgetError.__module__ = "researchassistant.storage.store"
