"""Durable, opt-in persistence and reservations for source-discovery v2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

from pydantic import ValidationError

from providers.ranking import canonical_discovery_url
from researchassistant.common.money import add_usd
from researchassistant.contracts.discovery_v2 import (
    V2CandidateDisposition,
    V2CompiledQueryAction,
    V2ConceptualQuery,
    V2DiscoveryArtifact,
    V2DiscoveryAuditCounters,
    V2DiscoveryBinding,
    V2DiscoveryOperation,
    V2ExpansionEdge,
    V2ExpansionResult,
    V2GraphNeighborAction,
    V2IdentityLookupAction,
    V2NormalizedDiscoveryCandidate,
    V2PreviewRequest,
    V2PreviewResult,
    V2ProviderAttemptCompletion,
    V2ProviderAttemptStart,
    V2RawDiscoveryCandidate,
    V2SeedEligibility,
    V2WorkResolution,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    ResearchDirection,
    V2AcquiredSource,
    V2AcquisitionProbeOutput,
    V2GapAnalysisOutput,
    V2PersistedArtifact,
    V2RoundFourGovernorDecision,
)
from researchassistant.storage.store import (
    DatabaseReader,
    _connect,
    _insert_v2_artifact_on_connection,
    _read_connection,
    _read_execute,
    _row_to_v2_artifact,
    open_read_only_store,
    read_v2_artifact,
)

_T = TypeVar("_T", bound=V2DiscoveryArtifact)
_KEY_PREFIX = "source-discovery-v1"
_MAX_REQUESTS = {
    "serpsearch": 12,
    "exa": 18,
    "openalex": 10,
    "arxiv": 6,
    "pubmed": 6,
}
_ROUND_FOUR_GOVERNOR_KEY = "post-phase-13-round-4-governor-decision-v1"


def _validated(artifact: _T) -> _T:
    """Revalidate even Pydantic `model_copy` values at the persistence boundary."""
    return type(artifact).model_validate(artifact.model_dump(mode="python"))


@dataclass(frozen=True)
class ProviderAttemptAudit:
    """Detached view of attempts; a missing completion remains visibly unknown."""

    starts: tuple[V2ProviderAttemptStart, ...]
    completions: tuple[V2ProviderAttemptCompletion | None, ...]
    interrupted_unknown: tuple[UUID, ...]


@dataclass(frozen=True)
class DiscoveryRunInspection:
    """Detached discovery artifacts and counters from one read-only snapshot."""

    run_id: UUID
    artifacts: tuple[V2DiscoveryArtifact, ...]
    counters: V2DiscoveryAuditCounters | None


def _artifact_key(artifact: V2DiscoveryArtifact) -> str:
    return f"{_KEY_PREFIX}:{type(artifact).__name__}:{artifact.identity_key}"


def _typed_read(source: DatabaseReader, run_id: UUID, key: str, model_type: type[_T]) -> _T:
    envelope = read_v2_artifact(source, run_id, key)
    try:
        value = model_type.model_validate_json(envelope.payload_json)
    except (ValidationError, ValueError) as exc:
        raise sqlite3.IntegrityError(f"invalid {model_type.__name__} payload") from exc
    if (
        envelope.artifact_key != key
        or envelope.artifact_type != type(value).__name__
        or value.run_id != run_id
    ):
        raise sqlite3.IntegrityError("discovery artifact type/run binding is corrupt")
    return value


_DISCOVERY_ARTIFACT_TYPES: dict[str, type[V2DiscoveryArtifact]] = {
    model.__name__: model
    for model in (
        V2DiscoveryBinding,
        V2ConceptualQuery,
        V2CompiledQueryAction,
        V2GraphNeighborAction,
        V2IdentityLookupAction,
        V2DiscoveryOperation,
        V2ProviderAttemptStart,
        V2ProviderAttemptCompletion,
        V2RawDiscoveryCandidate,
        V2NormalizedDiscoveryCandidate,
        V2CandidateDisposition,
        V2PreviewRequest,
        V2PreviewResult,
        V2SeedEligibility,
        V2WorkResolution,
        V2ExpansionEdge,
        V2ExpansionResult,
        V2DiscoveryAuditCounters,
    )
}


def read_discovery_artifact(
    source: DatabaseReader, run_id: UUID, artifact_type: str, identity_key: str
) -> V2DiscoveryArtifact:
    """Read a registered family through the underlying hash-verifying v2 reader."""
    model_type = _DISCOVERY_ARTIFACT_TYPES.get(artifact_type)
    if model_type is None:
        raise ValueError(f"unregistered discovery artifact type: {artifact_type}")
    with _read_connection(source) as conn:
        value = _typed_read(
            conn,
            run_id,
            f"{_KEY_PREFIX}:{artifact_type}:{identity_key}",
            model_type,
        )
        if artifact_type == "V2DiscoveryOperation":
            binding = read_discovery_binding(conn, run_id)
            _validate_policy(binding, value)
            _validate_operation_gap_targets(conn, value)
    return value


def read_discovery_artifacts(
    source: DatabaseReader, run_id: UUID
) -> tuple[V2DiscoveryArtifact, ...]:
    """Read the bounded discovery family for inspection without writing or migrating."""
    values: list[V2DiscoveryArtifact] = []
    with _read_connection(source) as conn:
        artifacts = _all_run_artifacts(conn, run_id)
        for envelope in artifacts:
            model_type = _DISCOVERY_ARTIFACT_TYPES.get(envelope.artifact_type)
            if model_type is None:
                raise sqlite3.IntegrityError("unregistered discovery artifact in family inventory")
            value = model_type.model_validate_json(envelope.payload_json)
            if value.run_id != run_id or _artifact_key(value) != envelope.artifact_key:
                raise sqlite3.IntegrityError("discovery inventory identity is corrupt")
            if isinstance(value, V2DiscoveryOperation):
                binding = read_discovery_binding(conn, run_id)
                _validate_policy(binding, value)
                _validate_operation_gap_targets(conn, value)
            values.append(value)
    return tuple(values)


def inspect_discovery_run(db_path: str, run_id: UUID) -> DiscoveryRunInspection:
    """Inspect discovery history without writes, migrations, or mixed-snapshot reads."""
    with open_read_only_store(db_path) as store:
        conn = store.connection
        artifacts = read_discovery_artifacts(conn, run_id)
        if not artifacts:
            return DiscoveryRunInspection(run_id, (), None)
        try:
            binding = read_discovery_binding(conn, run_id)
        except KeyError as exc:
            raise sqlite3.IntegrityError(
                "discovery artifacts exist without their immutable run binding"
            ) from exc
        counters = compute_discovery_audit_counters(conn, run_id)
        if binding.run_id != run_id:
            raise sqlite3.IntegrityError("inspection binding belongs to another run")
        return DiscoveryRunInspection(run_id, artifacts, counters)


def _all_run_artifacts(conn: sqlite3.Connection, run_id: UUID) -> tuple[V2PersistedArtifact, ...]:
    rows = _read_execute(
        conn,
        "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key LIKE ? "
        "ORDER BY artifact_key LIMIT 6001",
        (str(run_id), f"{_KEY_PREFIX}:%"),
    ).fetchall()
    if len(rows) > 6000:
        raise sqlite3.IntegrityError("run artifact inventory exceeds the bounded reader")
    return tuple(_row_to_v2_artifact(row) for row in rows)


def bind_discovery_run(db_path: str, binding: V2DiscoveryBinding, created_at: datetime) -> str:
    """Bind opt-in discovery settings before any prior-policy v2 artifact exists."""
    binding = _validated(binding)
    key = _artifact_key(binding)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
            (str(binding.run_id), key),
        ).fetchone()
        if existing is not None:
            envelope = _row_to_v2_artifact(existing)
            current = V2DiscoveryBinding.model_validate_json(envelope.payload_json)
            if current != binding:
                raise sqlite3.IntegrityError(
                    "discovery binding replay conflicts with stored identity"
                )
            conn.commit()
            return current.fingerprint
        other_artifacts = conn.execute(
            "SELECT artifact_key FROM v2_artifacts WHERE run_id = ? LIMIT 1",
            (str(binding.run_id),),
        ).fetchone()
        if other_artifacts is not None:
            raise ValueError(
                "new discovery policy cannot bind after prior v2 artifacts; use a new run"
            )
        manifest = conn.execute(
            "SELECT raw_claim FROM runs WHERE run_id = ?", (str(binding.run_id),)
        ).fetchone()
        if manifest is not None and manifest["raw_claim"] != binding.exact_claim:
            raise ValueError("discovery binding claim differs from immutable run claim")
        identity = conn.execute(
            "SELECT pipeline_identity, policy_identity FROM v2_run_identities WHERE run_id = ?",
            (str(binding.run_id),),
        ).fetchone()
        if identity is None:
            raise ValueError("discovery binding requires an initialized v2 run identity")
        _insert_v2_artifact_on_connection(conn, key, binding, created_at)
        conn.commit()
        return binding.fingerprint
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def read_discovery_binding(source: DatabaseReader, run_id: UUID) -> V2DiscoveryBinding:
    with _read_connection(source) as conn:
        rows = _read_execute(
            conn,
            "SELECT * FROM v2_artifacts WHERE run_id = ? AND artifact_type = ? LIMIT 2",
            (str(run_id), "V2DiscoveryBinding"),
        ).fetchall()
        if len(rows) != 1:
            raise KeyError(f"expected one discovery binding for run {run_id}")
        envelope = _row_to_v2_artifact(rows[0])
    result = V2DiscoveryBinding.model_validate_json(envelope.payload_json)
    if result.run_id != run_id or envelope.artifact_key != _artifact_key(result):
        raise sqlite3.IntegrityError("discovery binding identity is corrupt")
    return result


def _validate_policy(binding: V2DiscoveryBinding, artifact: V2DiscoveryArtifact) -> None:
    if artifact.run_id != binding.run_id:
        raise ValueError("discovery artifact belongs to another run")
    if isinstance(artifact, V2DiscoveryOperation):
        if artifact.binding_fingerprint != binding.fingerprint:
            raise ValueError("operation binding fingerprint differs from run binding")
        action = artifact.action
        if isinstance(action, V2CompiledQueryAction):
            provider = action.conceptual_query.provider
            direction = action.conceptual_query.direction
            round_number = action.conceptual_query.round_number
        else:
            provider = action.provider
            direction = action.direction
            round_number = action.round_number
        if provider not in binding.providers:
            raise ValueError("operation provider is not enabled by the run binding")
        if not binding.directions.permits(direction):
            raise ValueError("operation direction is disabled by the run binding")
        capability = next(item for item in binding.capabilities if item.provider == provider)
        if isinstance(action, V2CompiledQueryAction):
            if action.compiler_identity != binding.compiler_identity:
                raise ValueError("query compiler identity differs from frozen binding")
            if action.policy != binding.policy or action.capabilities != capability:
                raise ValueError("query policy/capability identity differs from binding")
        elif action.policy != binding.policy or action.capabilities != capability:
            raise ValueError("operation policy/capability identity differs from binding")
        if round_number > 4:
            raise ValueError("operation exceeds the authorized four-round lifecycle")
    elif isinstance(artifact, V2ProviderAttemptStart):
        if artifact.binding_fingerprint != binding.fingerprint:
            raise ValueError("attempt binding fingerprint differs from run binding")
    elif isinstance(artifact, V2PreviewRequest):
        if not binding.directions.permits(artifact.direction):
            raise ValueError("preview direction is disabled by the run binding")
        if artifact.exact_claim != binding.exact_claim:
            raise ValueError("preview claim differs from exact run claim")
        if artifact.directions != binding.directions:
            raise ValueError("preview directions differ from run binding")


def _insert_typed(
    conn: sqlite3.Connection, artifact: V2DiscoveryArtifact, created_at: datetime
) -> None:
    key = _artifact_key(artifact)
    existing = _read_execute(
        conn,
        "SELECT 1 FROM v2_artifacts WHERE run_id = ? AND artifact_key = ?",
        (str(artifact.run_id), key),
    ).fetchone()
    count = _read_execute(
        conn,
        "SELECT COUNT(*) FROM v2_artifacts WHERE run_id = ? AND artifact_key LIKE ?",
        (str(artifact.run_id), f"{_KEY_PREFIX}:%"),
    ).fetchone()[0]
    if existing is None and count >= 6000:
        raise ValueError("run discovery artifact inventory cap is exhausted")
    _insert_v2_artifact_on_connection(conn, _artifact_key(artifact), artifact, created_at)


def insert_discovery_operation(
    db_path: str, operation: V2DiscoveryOperation, created_at: datetime
) -> V2DiscoveryOperation:
    operation = _validated(operation)
    binding = read_discovery_binding(db_path, operation.run_id)
    _validate_policy(binding, operation)
    _validate_operation_gap_targets(db_path, operation)
    if isinstance(operation.action, V2GraphNeighborAction):
        seed = _typed_read(
            db_path,
            operation.run_id,
            _artifact_key(operation.action.seed),
            type(operation.action.seed),
        )
        if seed != operation.action.seed or not seed.eligible:
            raise ValueError("graph operation requires the exact stored eligible seed")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        artifacts = _all_run_artifacts(conn, operation.run_id)
        for envelope in artifacts:
            if envelope.artifact_type != "V2DiscoveryOperation":
                continue
            prior_operation = V2DiscoveryOperation.model_validate_json(envelope.payload_json)
            if prior_operation.action.artifact_id != operation.action.artifact_id:
                continue
            if prior_operation == operation:
                conn.commit()
                return operation
            raise sqlite3.IntegrityError("logical operation action ID is already owned")
        if _operation_round(operation) == 4:
            same_round = [
                V2DiscoveryOperation.model_validate_json(item.payload_json)
                for item in artifacts
                if item.artifact_type == "V2DiscoveryOperation"
                and _operation_round(V2DiscoveryOperation.model_validate_json(item.payload_json))
                == 4
            ]
            providers = {_operation_provider(item) for item in same_round}
            providers.add(_operation_provider(operation))
            if len(providers) > 2:
                raise ValueError("Round 4 provider ceiling is exhausted")
            same_lane = [
                item
                for item in same_round
                if _operation_provider(item) == _operation_provider(operation)
                and _operation_direction(item) == _operation_direction(operation)
            ]
            if len(same_lane) >= 2:
                raise ValueError("Round 4 direction/provider operation ceiling is exhausted")
        _insert_typed(conn, operation, created_at)
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
    return operation


def read_discovery_operation(
    source: DatabaseReader, run_id: UUID, identity_key: str
) -> V2DiscoveryOperation:
    result = _typed_read(
        source,
        run_id,
        f"{_KEY_PREFIX}:V2DiscoveryOperation:{identity_key}",
        V2DiscoveryOperation,
    )
    binding = read_discovery_binding(source, run_id)
    _validate_policy(binding, result)
    _validate_operation_gap_targets(source, result)
    return result


def _attempt_rows(
    conn: sqlite3.Connection, run_id: UUID, operation_id: UUID
) -> tuple[tuple[V2ProviderAttemptStart, ...], tuple[V2ProviderAttemptCompletion, ...]]:
    artifacts = _all_run_artifacts(conn, run_id)
    starts: list[V2ProviderAttemptStart] = []
    completions: list[V2ProviderAttemptCompletion] = []
    for item in artifacts:
        if item.artifact_type not in {"V2ProviderAttemptStart", "V2ProviderAttemptCompletion"}:
            continue
        cls = (
            V2ProviderAttemptStart
            if item.artifact_type == "V2ProviderAttemptStart"
            else V2ProviderAttemptCompletion
        )
        value = cls.model_validate_json(item.payload_json)
        if value.run_id != run_id:
            raise sqlite3.IntegrityError("attempt artifact has cross-run ownership")
        if value.operation_id == operation_id:
            (starts if isinstance(value, V2ProviderAttemptStart) else completions).append(value)
    return tuple(sorted(starts, key=lambda item: item.sequence)), tuple(completions)


def _unknown_request_outcome(completion: V2ProviderAttemptCompletion | None) -> bool:
    """Use the same conservative unknown boundary for execution and inspection."""
    return (
        completion is None
        or completion.status == "interrupted_unknown"
        or (
            completion.status == "failed"
            and completion.response_hash is None
            and completion.actual_cost_usd is None
        )
    )


def reserve_provider_attempt(db_path: str, start: V2ProviderAttemptStart) -> V2ProviderAttemptStart:
    """Atomically persist exposure before transport; starts are never replay permission."""
    start = _validated(start)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        binding = read_discovery_binding(conn, start.run_id)
        if start.binding_fingerprint != binding.fingerprint:
            raise ValueError("attempt has stale discovery binding")
        operation_key = _operation_key_for_id(conn, start.run_id, start.operation_id)
        operation = read_discovery_operation(conn, start.run_id, operation_key)
        action = operation.action
        if isinstance(action, V2CompiledQueryAction):
            provider = action.conceptual_query.provider
        else:
            provider = action.provider
        capability = next(item for item in binding.capabilities if item.provider == provider)
        if action.artifact_id != start.operation_id:
            raise ValueError("attempt operation ID must equal its application-owned action ID")
        if isinstance(action, V2CompiledQueryAction):
            max_depth = min(
                action.effective_depth,
                capability.max_metadata_per_operation,
                binding.policy.metadata_depth,
            )
            capability.require_search(action.mode, executable=True)
        else:
            max_depth = min(
                action.requested_depth,
                capability.max_metadata_per_operation,
                binding.policy.metadata_depth,
            )
            if isinstance(action, V2GraphNeighborAction):
                capability.require_relationship(action.relationship, executable=True)
            elif not capability.executable_identity_lookup:
                raise ValueError("provider identity lookup is not executable under this binding")
        if start.provider != provider:
            raise ValueError("attempt provider differs from parent operation")
        max_pages = binding.policy.max_pages_per_operation // capability.physical_requests_per_page
        if start.page_number > max_pages:
            raise ValueError("attempt page exceeds the complete physical operation page cap")
        if start.request_kind == "metadata" and capability.physical_requests_per_page != 2:
            raise ValueError("provider does not support a separate metadata page request")
        if start.requested_records > max_depth:
            raise ValueError("attempt result limit exceeds parent operation depth")
        if capability.executable_pagination == "none" and start.page_number > 1:
            raise ValueError("provider operation does not support multiple pages")
        budget = next(item for item in binding.provider_budgets if item.provider == provider)
        if (
            start.reserved_cost_usd != budget.reservation_per_request_usd
            or start.cost_basis != budget.cost_basis
        ):
            raise ValueError("attempt reservation differs from frozen provider budget")
        artifacts = _all_run_artifacts(conn, start.run_id)
        all_starts = [
            V2ProviderAttemptStart.model_validate_json(item.payload_json)
            for item in artifacts
            if item.artifact_type == "V2ProviderAttemptStart"
        ]
        provider_starts = [item for item in all_starts if item.provider == provider]
        if len(provider_starts) >= min(budget.max_requests, _MAX_REQUESTS[provider.value]):
            raise ValueError("provider request budget is exhausted")
        completion_by_attempt: dict[UUID, V2ProviderAttemptCompletion] = {}
        for item in artifacts:
            if item.artifact_type == "V2ProviderAttemptCompletion":
                completion = V2ProviderAttemptCompletion.model_validate_json(item.payload_json)
                completion_by_attempt[completion.attempt_id] = completion
        effective_exposures = []
        for item in provider_starts:
            completed = completion_by_attempt.get(item.artifact_id)
            known_actual = (
                completed.actual_cost_usd
                if completed and completed.actual_cost_usd is not None
                else None
            )
            effective_exposures.append(max(item.reserved_cost_usd, known_actual or Decimal("0")))
        exposure = add_usd(*effective_exposures, start.reserved_cost_usd)
        if exposure > budget.max_cost_usd:
            raise ValueError("provider cost budget is exhausted")
        starts, _ = _attempt_rows(conn, start.run_id, start.operation_id)
        if binding.policy.unknown_request_recovery == "stop" and any(
            _unknown_request_outcome(completion_by_attempt.get(item.artifact_id))
            for item in all_starts
        ):
            raise ValueError("unknown request outcome stops further provider attempts for this run")
        if len(starts) >= 3:
            raise ValueError("logical operation attempt cap is exhausted")
        if start.sequence != len(starts) + 1:
            raise ValueError("attempt sequence must be dense and newly reserved")
        if start.request_kind == "metadata":
            parent = next(
                (item for item in starts if item.artifact_id == start.parent_attempt_id), None
            )
            response = completion_by_attempt.get(start.parent_attempt_id)
            if (
                parent is None
                or parent.request_kind != "primary"
                or parent.page_number != start.page_number
                or response is None
                or response.status != "completed"
                or response.response_hash != start.parent_response_hash
            ):
                raise ValueError("metadata request parent response ownership differs")
        elif capability.physical_requests_per_page > 1:
            needed = capability.physical_requests_per_page
            if len(provider_starts) + needed > budget.max_requests:
                raise ValueError("provider request budget cannot fit a complete metadata page")
            if (
                add_usd(exposure, *(start.reserved_cost_usd for _ in range(needed - 1)))
                > budget.max_cost_usd
            ):
                raise ValueError("provider cost budget cannot fit a complete metadata page")
        previous_pages = {item.page_number: item.requested_records for item in starts}
        if start.page_number in previous_pages and any(
            prior.page_number == start.page_number
            and prior.request_kind == start.request_kind
            and (prior_completion := completion_by_attempt.get(prior.artifact_id)) is not None
            and prior_completion.status == "completed"
            for prior in starts
        ):
            raise ValueError("completed page response is cached and cannot be retried")
        if start.requested_records > capability.max_metadata_per_page:
            raise ValueError("attempt result limit exceeds provider page capability")
        highest_page = max(previous_pages, default=0)
        if start.page_number > highest_page + 1:
            raise ValueError("page sequence cannot skip a page")
        if start.page_number not in previous_pages:
            requested_so_far = sum(previous_pages.values()) + start.requested_records
            if requested_so_far > max_depth:
                raise ValueError("cumulative page depth exceeds logical operation depth")
        elif start.requested_records != previous_pages[start.page_number]:
            raise ValueError("retry page bounds differ from the original page reservation")
        if _operation_round(operation) == 4:
            try:
                decision_envelope = read_v2_artifact(conn, start.run_id, _ROUND_FOUR_GOVERNOR_KEY)
            except KeyError as exc:
                raise ValueError(
                    "Round 4 transport lacks persisted Governor authorization"
                ) from exc
            decision = V2RoundFourGovernorDecision.model_validate_json(
                decision_envelope.payload_json
            )
            if decision.run_id != start.run_id or not decision.authorized:
                raise ValueError("Round 4 transport lacks valid Governor authorization")
        _insert_typed(conn, start, start.started_at)
        conn.commit()
        return start
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _operation_key_for_id(conn: sqlite3.Connection, run_id: UUID, operation_id: UUID) -> str:
    for item in _all_run_artifacts(conn, run_id):
        if item.artifact_type == "V2DiscoveryOperation":
            operation = V2DiscoveryOperation.model_validate_json(item.payload_json)
            if operation.action.artifact_id == operation_id:
                return operation.identity_key
    raise KeyError(f"parent discovery operation {operation_id} not found")


def complete_provider_attempt(
    db_path: str, completion: V2ProviderAttemptCompletion, completed_at: datetime
) -> V2ProviderAttemptCompletion:
    completion = _validated(completion)
    if completed_at != completion.completed_at:
        raise ValueError("completion envelope time must match typed completion time")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        binding = read_discovery_binding(conn, completion.run_id)
        starts, completions = _attempt_rows(conn, completion.run_id, completion.operation_id)
        start = next((item for item in starts if item.artifact_id == completion.attempt_id), None)
        if start is None:
            raise ValueError("completion has no matching durable start")
        if completion.operation_id != start.operation_id:
            raise ValueError("completion operation differs from its reservation")
        if completion.completed_at < start.started_at:
            raise ValueError("completion precedes its reservation")
        if completion.metadata_records > start.requested_records:
            raise ValueError("completion exceeds reserved result bound")
        if len(completion.result_ids) > completion.metadata_records:
            raise ValueError("completion identities exceed returned metadata count")
        prior_completion = next(
            (item for item in completions if item.attempt_id == completion.attempt_id), None
        )
        if prior_completion is not None:
            if prior_completion == completion:
                conn.commit()
                return prior_completion
            raise sqlite3.IntegrityError("provider completion replay conflicts with stored result")
        if completion.cost_basis == "documented_free" and start.cost_basis != "documented_free":
            raise ValueError("completion claims free cost outside the frozen provider policy")
        _validate_policy(binding, completion)
        key = _artifact_key(completion)
        _insert_v2_artifact_on_connection(conn, key, completion, completed_at)
        conn.commit()
        return completion
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def provider_attempt_audit(source: DatabaseReader, run_id: UUID) -> ProviderAttemptAudit:
    starts: list[V2ProviderAttemptStart] = []
    completions: dict[UUID, V2ProviderAttemptCompletion] = {}
    with _read_connection(source) as conn:
        for item in _all_run_artifacts(conn, run_id):
            if item.artifact_type == "V2ProviderAttemptStart":
                starts.append(V2ProviderAttemptStart.model_validate_json(item.payload_json))
            elif item.artifact_type == "V2ProviderAttemptCompletion":
                result = V2ProviderAttemptCompletion.model_validate_json(item.payload_json)
                if result.attempt_id in completions:
                    raise sqlite3.IntegrityError("duplicate completion for one attempt")
                completions[result.attempt_id] = result
    start_ids = {item.artifact_id for item in starts}
    if len(start_ids) != len(starts):
        raise sqlite3.IntegrityError("duplicate provider attempt starts")
    if any(item.attempt_id not in start_ids for item in completions.values()):
        raise sqlite3.IntegrityError("provider completion has no durable start")
    operation_ids = {item.operation_id for item in starts}
    if any(item.operation_id not in operation_ids for item in completions.values()):
        raise sqlite3.IntegrityError("provider completion has conflicting operation ownership")
    if any(item.run_id != run_id for item in (*starts, *completions.values())):
        raise sqlite3.IntegrityError("attempt audit contains cross-run artifact")
    starts.sort(key=lambda item: (item.provider.value, item.started_at, item.sequence))
    aligned = tuple(completions.get(item.artifact_id) for item in starts)
    interrupted = tuple(
        item.artifact_id
        for item, completion in zip(starts, aligned, strict=True)
        if _unknown_request_outcome(completion)
    )
    return ProviderAttemptAudit(tuple(starts), aligned, interrupted)


def insert_discovery_candidate(
    db_path: str, candidate: V2NormalizedDiscoveryCandidate, created_at: datetime
) -> V2NormalizedDiscoveryCandidate:
    candidate = _validated(candidate)
    binding = read_discovery_binding(db_path, candidate.run_id)
    for raw in candidate.raw_candidates:
        _validate_raw_candidate(db_path, raw, binding)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing_artifacts = _all_run_artifacts(conn, candidate.run_id)
        raw_items = [
            V2RawDiscoveryCandidate.model_validate_json(item.payload_json)
            for item in existing_artifacts
            if item.artifact_type == "V2RawDiscoveryCandidate"
        ]
        new_raw = [
            raw
            for raw in candidate.raw_candidates
            if not any(item.artifact_id == raw.artifact_id for item in raw_items)
        ]
        rounds = {raw.round_number for raw in candidate.raw_candidates}
        if len(raw_items) + len(new_raw) > binding.policy.max_raw_per_run:
            raise ValueError("run raw-candidate cap is exhausted")
        if any(
            sum(item.round_number == round_number for item in raw_items)
            + sum(raw.round_number == round_number for raw in new_raw)
            > binding.policy.max_raw_per_round
            for round_number in rounds
        ):
            raise ValueError("round raw-candidate cap is exhausted")
        normalized = [
            V2NormalizedDiscoveryCandidate.model_validate_json(item.payload_json)
            for item in existing_artifacts
            if item.artifact_type == "V2NormalizedDiscoveryCandidate"
        ]
        if not any(item.artifact_id == candidate.artifact_id for item in normalized):
            if len(normalized) >= binding.policy.max_raw_per_run:
                raise ValueError("run normalized-candidate cap is exhausted")
            if (
                sum(
                    any(raw.round_number in rounds for raw in item.raw_candidates)
                    for item in normalized
                )
                >= binding.policy.max_raw_per_round
            ):
                raise ValueError("round normalized-candidate cap is exhausted")
        for raw in candidate.raw_candidates:
            _insert_typed(conn, raw, created_at)
        _validate_policy(binding, candidate)
        _insert_typed(conn, candidate, created_at)
        conn.commit()
        return candidate
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _validate_raw_candidate(
    db_path: str, candidate: V2RawDiscoveryCandidate, binding: V2DiscoveryBinding
) -> None:
    if candidate.provider not in binding.providers or not binding.directions.permits(
        candidate.direction
    ):
        raise ValueError("candidate provider/direction is outside run binding")
    operation_key = _operation_key_for_artifact(db_path, candidate.run_id, candidate.operation_id)
    operation = read_discovery_operation(db_path, candidate.run_id, operation_key)
    action = operation.action
    if isinstance(action, V2CompiledQueryAction):
        parent = (
            action.conceptual_query.provider,
            action.conceptual_query.direction,
            action.conceptual_query.round_number,
        )
    else:
        parent = (action.provider, action.direction, action.round_number)
    if parent != (candidate.provider, candidate.direction, candidate.round_number):
        raise ValueError("raw candidate provenance differs from its parent action")
    audit = provider_attempt_audit(db_path, candidate.run_id)
    start = next((item for item in audit.starts if item.artifact_id == candidate.attempt_id), None)
    completion = next(
        (item for item in audit.completions if item and item.attempt_id == candidate.attempt_id),
        None,
    )
    if start is None or start.operation_id != candidate.operation_id:
        raise ValueError("raw candidate must reference its operation's durable attempt")
    if completion is None or completion.status != "completed":
        raise ValueError("raw candidate requires a completed provider response")
    if candidate.response_hash != completion.response_hash:
        raise ValueError("raw candidate response hash differs from completed response")
    if candidate.artifact_id not in completion.result_ids:
        raise ValueError("raw candidate ID was not returned by completed response")


def insert_seed_eligibility(
    db_path: str,
    seed: V2SeedEligibility,
    acquisition_output: V2AcquisitionProbeOutput,
    candidate: V2NormalizedDiscoveryCandidate,
    created_at: datetime,
) -> V2SeedEligibility:
    """Persist seed status only when candidate and immutable acquisition agree."""
    seed = _validated(seed)
    candidate = _validated(candidate)
    acquisition_output = V2AcquisitionProbeOutput.model_validate(
        acquisition_output.model_dump(mode="python")
    )
    if acquisition_output.run_id != seed.run_id or candidate.run_id != seed.run_id:
        raise ValueError("seed inputs have cross-run ownership")
    if candidate.artifact_id != seed.candidate_id:
        raise ValueError("seed candidate does not match its normalized candidate artifact")
    if candidate.work != seed.work:
        raise ValueError("seed work identity differs from candidate identity")
    binding = read_discovery_binding(db_path, seed.run_id)
    stored_candidate = _typed_read(
        db_path,
        candidate.run_id,
        _artifact_key(candidate),
        V2NormalizedDiscoveryCandidate,
    )
    if stored_candidate != candidate:
        raise ValueError("seed candidate differs from stored normalized candidate")
    if seed.eligible:
        acquisition_output = _read_acquisition_for_preview(db_path, seed.run_id, acquisition_output)
    if seed.eligible:
        survivor = next(
            (item for item in acquisition_output.survivors if item.snapshot_id == seed.snapshot_id),
            None,
        )
        if survivor is None or survivor.cluster_id != seed.source_id:
            raise ValueError("eligible seed must reference an acquired usable survivor")
        acquired_source = next(
            (
                source
                for source in acquisition_output.acquisitions
                if source.snapshot.snapshot_id == seed.snapshot_id
                and source.cluster_id == seed.source_id
            ),
            None,
        )
        if acquired_source is None:
            raise ValueError("eligible seed snapshot is not linked to the acquired source")
        if not _acquisition_source_matches_candidate(acquired_source, candidate):
            raise ValueError("acquired source is not linked to the candidate work identity")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        prior = [
            V2SeedEligibility.model_validate_json(item.payload_json)
            for item in _all_run_artifacts(conn, seed.run_id)
            if item.artifact_type == "V2SeedEligibility"
            and V2SeedEligibility.model_validate_json(item.payload_json).artifact_id
            != seed.artifact_id
        ]
        prior_seed_works = {item.work.grouping_key for item in prior if item.eligible}
        if (
            seed.eligible
            and seed.work.grouping_key not in prior_seed_works
            and len(prior_seed_works) >= binding.policy.max_seeds_per_run
        ):
            raise ValueError("run seed cap is exhausted")
        _validate_policy(binding, seed)
        _insert_typed(conn, seed, created_at)
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
    return seed


def _url_identity(value: str) -> str:
    """Retain query identifiers, path case and ports under established URL grouping."""
    return canonical_discovery_url(value)


def _acquisition_source_matches_candidate(
    acquired_source: V2AcquiredSource, candidate: V2NormalizedDiscoveryCandidate
) -> bool:
    snapshot = acquired_source.snapshot
    snapshot_urls = {
        _url_identity(value)
        for value in (snapshot.source_url, snapshot.original_url, snapshot.canonical_url)
        if value
    }
    candidate_locations = [
        location
        for raw in candidate.raw_candidates
        for location in raw.locations
        if location.same_work_basis != "unverified"
    ]
    if any(_url_identity(location.url) in snapshot_urls for location in candidate_locations):
        return True
    if candidate.work.doi:
        return _url_identity(f"https://doi.org/{candidate.work.doi}") in snapshot_urls
    return False


def _operation_key_for_artifact(source: DatabaseReader, run_id: UUID, artifact_id: UUID) -> str:
    with _read_connection(source) as conn:
        return _operation_key_for_id(conn, run_id, artifact_id)


def insert_preview(
    db_path: str,
    preview: V2PreviewResult,
    snapshot_output: V2AcquisitionProbeOutput,
    created_at: datetime,
) -> V2PreviewResult:
    preview = _validated(preview)
    snapshot_output = V2AcquisitionProbeOutput.model_validate(
        snapshot_output.model_dump(mode="python")
    )
    if snapshot_output.run_id != preview.run_id:
        raise ValueError("preview acquisition output belongs to another run")
    stored_output = _read_acquisition_for_preview(db_path, preview.run_id, snapshot_output)
    snapshot = next(
        (
            source.snapshot
            for source in stored_output.acquisitions
            if source.snapshot.snapshot_id == preview.request.snapshot_id
        ),
        None,
    )
    if snapshot is None:
        raise ValueError("preview snapshot is absent from same-run acquisition output")
    preview.require_snapshot(snapshot)
    request = preview.request
    source = next(
        item
        for item in stored_output.acquisitions
        if item.snapshot.snapshot_id == request.snapshot_id
    )
    if request.direction != source.direction or request.source_id != source.cluster_id:
        raise ValueError("preview source identity/direction differs from acquired source")
    binding = read_discovery_binding(db_path, preview.run_id)
    _validate_policy(binding, request)
    if request.directions != binding.directions:
        raise ValueError("preview directions differ from run binding")
    _persist_once(db_path, preview, created_at)
    return preview


def _read_acquisition_for_preview(
    db_path: str,
    run_id: UUID,
    provided: V2AcquisitionProbeOutput,
) -> V2AcquisitionProbeOutput:
    from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY

    keys = (
        V2_ACQUISITION_PROBE_ARTIFACT_KEY,
        "phase-7-round-2-acquisition-probe",
        "phase-7-round-3-acquisition-probe",
        "post-phase-13-round-4-acquisition-probe-v1",
    )
    found = False
    for key in keys:
        try:
            envelope = read_v2_artifact(db_path, run_id, key)
        except KeyError:
            continue
        stored = V2AcquisitionProbeOutput.model_validate_json(envelope.payload_json)
        if stored.run_id != run_id:
            raise sqlite3.IntegrityError("acquisition output has cross-run ownership")
        found = True
        if stored == provided:
            return stored
    if found:
        raise ValueError("preview input differs from immutable acquisition output")
    raise ValueError("preview requires a persisted acquisition output")


def insert_expansion_result(
    db_path: str, result: V2ExpansionResult, created_at: datetime
) -> V2ExpansionResult:
    result = _validated(result)
    binding = read_discovery_binding(db_path, result.run_id)
    operation_key = _operation_key_for_artifact(db_path, result.run_id, result.action.artifact_id)
    operation = read_discovery_operation(db_path, result.run_id, operation_key)
    if operation.action != result.action:
        raise ValueError("expansion result action differs from persisted operation")
    if result.action.provider not in binding.providers:
        raise ValueError("expansion provider is outside run binding")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for edge in result.edges:
            stored_raw = _typed_read(
                db_path, result.run_id, _artifact_key(edge.candidate), V2RawDiscoveryCandidate
            )
            if stored_raw != edge.candidate:
                raise ValueError("expansion edge differs from stored raw candidate")
            _validate_raw_candidate(db_path, edge.candidate, binding)
        prior_results = [
            V2ExpansionResult.model_validate_json(item.payload_json)
            for item in _all_run_artifacts(conn, result.run_id)
            if item.artifact_type == "V2ExpansionResult"
            and V2ExpansionResult.model_validate_json(item.payload_json).artifact_id
            != result.artifact_id
        ]
        if any(
            prior.action.artifact_id == result.action.artifact_id and prior.status == "completed"
            for prior in prior_results
        ):
            raise sqlite3.IntegrityError("completed expansion result for this action is immutable")
        all_work_keys = {
            edge.candidate.work.grouping_key for prior in prior_results for edge in prior.edges
        }
        all_work_keys.update(edge.candidate.work.grouping_key for edge in result.edges)
        if len(all_work_keys) > binding.policy.max_expansion_per_run:
            raise ValueError("run expansion candidate cap is exhausted")
        seed_key = result.action.seed.work.grouping_key
        seed_work_keys = {
            edge.candidate.work.grouping_key
            for prior in prior_results
            if prior.action.seed.work.grouping_key == seed_key
            for edge in prior.edges
        }
        seed_work_keys.update(edge.candidate.work.grouping_key for edge in result.edges)
        if len(seed_work_keys) > binding.policy.max_neighbors_per_seed:
            raise ValueError("per-seed expansion cap is exhausted")
        _validate_policy(binding, result)
        _insert_typed(conn, result, created_at)
        conn.commit()
        return result
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _discovery_artifacts(db_path: str, run_id: UUID) -> tuple[V2PersistedArtifact, ...]:
    with _read_connection(db_path) as conn:
        return _all_run_artifacts(conn, run_id)


def _persist_once(db_path: str, artifact: V2DiscoveryArtifact, created_at: datetime) -> None:
    artifact = _validated(artifact)
    binding = read_discovery_binding(db_path, artifact.run_id)
    _validate_policy(binding, artifact)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _insert_typed(conn, artifact, created_at)
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _operation_provider(operation: V2DiscoveryOperation) -> DiscoveryProvider:
    action = operation.action
    return (
        action.conceptual_query.provider
        if isinstance(action, V2CompiledQueryAction)
        else action.provider
    )


def _operation_direction(operation: V2DiscoveryOperation) -> ResearchDirection:
    action = operation.action
    return (
        action.conceptual_query.direction
        if isinstance(action, V2CompiledQueryAction)
        else action.direction
    )


def _operation_round(operation: V2DiscoveryOperation) -> int:
    action = operation.action
    return (
        action.conceptual_query.round_number
        if isinstance(action, V2CompiledQueryAction)
        else action.round_number
    )


def _operation_target_gaps(operation: V2DiscoveryOperation) -> tuple[str, ...]:
    action = operation.action
    if isinstance(action, V2CompiledQueryAction):
        return action.conceptual_query.target_gap_ids
    return action.target_gap_ids


def _validate_operation_gap_targets(
    source: DatabaseReader, operation: V2DiscoveryOperation
) -> None:
    target_ids = _operation_target_gaps(operation)
    if not target_ids:
        return
    keys = (
        "phase-6-gap-analysis",
        "phase-7-gap-analysis-after-round-2",
        "phase-7-gap-analysis-after-round-3",
        "post-phase-13-gap-analysis-after-round-3-v1",
    )
    matching: dict[str, object] = {}
    for key in keys:
        try:
            envelope = read_v2_artifact(source, operation.run_id, key)
        except KeyError:
            continue
        output = V2GapAnalysisOutput.model_validate_json(envelope.payload_json)
        if output.run_id != operation.run_id:
            raise sqlite3.IntegrityError("Gap Analysis artifact has cross-run ownership")
        if (
            output.result is None
            or output.stop_adaptive_continuation
            or output.input.completed_round != _operation_round(operation) - 1
        ):
            continue
        matching.update(
            {
                gap.gap_id: gap
                for gap in output.result.material_gaps
                if gap.direction == _operation_direction(operation)
            }
        )
    if any(target_id not in matching for target_id in target_ids):
        raise ValueError("operation Gap IDs must belong to the same-run prior Gap Analysis")


def insert_candidate_disposition(
    db_path: str, disposition: V2CandidateDisposition, created_at: datetime
) -> V2CandidateDisposition:
    disposition = _validated(disposition)
    binding = read_discovery_binding(db_path, disposition.run_id)
    operation = read_discovery_operation(
        db_path,
        disposition.run_id,
        _operation_key_for_artifact(db_path, disposition.run_id, disposition.operation_id),
    )
    if _operation_round(operation) != disposition.round_number or not binding.directions.permits(
        _operation_direction(operation)
    ):
        raise ValueError("candidate disposition differs from its owned operation")
    retained = _candidate_for_id(db_path, disposition.run_id, disposition.candidate_id)
    if retained is not None:
        if isinstance(retained, V2RawDiscoveryCandidate) and (
            retained.operation_id != disposition.operation_id
            or retained.round_number != disposition.round_number
        ):
            raise ValueError("candidate disposition conflicts with retained candidate ownership")
        if isinstance(retained, V2NormalizedDiscoveryCandidate) and not any(
            raw.operation_id == disposition.operation_id
            and raw.round_number == disposition.round_number
            for raw in retained.raw_candidates
        ):
            raise ValueError("candidate disposition conflicts with normalized provenance")
    else:
        audit = provider_attempt_audit(db_path, disposition.run_id)
        owned_response = any(
            start.operation_id == disposition.operation_id
            and completion is not None
            and disposition.candidate_id in completion.result_ids
            for start, completion in zip(audit.starts, audit.completions, strict=True)
        )
        if not owned_response:
            raise ValueError("unretained candidate marker lacks completed provider ownership")
    _persist_once(db_path, disposition, created_at)
    return disposition


def _candidate_for_id(
    source: DatabaseReader, run_id: UUID, candidate_id: UUID
) -> V2RawDiscoveryCandidate | V2NormalizedDiscoveryCandidate | None:
    for item in read_discovery_artifacts(source, run_id):
        if isinstance(item, V2RawDiscoveryCandidate) and item.artifact_id == candidate_id:
            return item
        if isinstance(item, V2NormalizedDiscoveryCandidate) and item.artifact_id == candidate_id:
            return item
    return None


def insert_work_resolution(
    db_path: str, resolution: V2WorkResolution, created_at: datetime
) -> V2WorkResolution:
    resolution = _validated(resolution)
    binding = read_discovery_binding(db_path, resolution.run_id)
    if resolution.provider not in binding.providers:
        raise ValueError("work resolution provider is outside run binding")
    candidate = _candidate_for_id(db_path, resolution.run_id, resolution.candidate_id)
    if candidate is None:
        raise ValueError("work resolution requires a stored normalized candidate")
    if not isinstance(candidate, V2NormalizedDiscoveryCandidate):
        raise ValueError("work resolution must reference a normalized candidate")
    if candidate.work.grouping_key != resolution.work.grouping_key:
        raise ValueError("resolved work identity differs from candidate")
    if resolution.operation_id is not None:
        operation = read_discovery_operation(
            db_path,
            resolution.run_id,
            _operation_key_for_artifact(db_path, resolution.run_id, resolution.operation_id),
        )
        if _operation_provider(operation) != resolution.provider:
            raise ValueError("work resolution provider differs from operation")
    _persist_once(db_path, resolution, created_at)
    return resolution


def compute_discovery_audit_counters(
    source: DatabaseReader, run_id: UUID
) -> V2DiscoveryAuditCounters:
    """Derive bounded counters from retained durable artifact evidence."""
    with _read_connection(source) as conn:
        artifacts = _all_run_artifacts(conn, run_id)
        acquisition_outputs = _find_acquisition_outputs(conn, run_id)
        ledger_count = _read_execute(
            conn,
            "SELECT COUNT(*) FROM v2_ledger_admissions WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()[0]
    operations = [
        V2DiscoveryOperation.model_validate_json(item.payload_json)
        for item in artifacts
        if item.artifact_type == "V2DiscoveryOperation"
    ]
    completions = [
        V2ProviderAttemptCompletion.model_validate_json(item.payload_json)
        for item in artifacts
        if item.artifact_type == "V2ProviderAttemptCompletion"
    ]
    raws = [
        V2RawDiscoveryCandidate.model_validate_json(item.payload_json)
        for item in artifacts
        if item.artifact_type == "V2RawDiscoveryCandidate"
    ]
    starts = [
        V2ProviderAttemptStart.model_validate_json(item.payload_json)
        for item in artifacts
        if item.artifact_type == "V2ProviderAttemptStart"
    ]
    unique = {item.work.grouping_key for item in raws}
    completed_by_attempt = {item.attempt_id: item for item in completions}
    unknown_count = sum(
        _unknown_request_outcome(completed_by_attempt.get(item.artifact_id)) for item in starts
    )
    result = V2DiscoveryAuditCounters(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2DiscoveryAuditCounters", "computed"),
        identity_key="computed",
        logical_queries=sum(isinstance(op.action, V2CompiledQueryAction) for op in operations),
        graph_operations=sum(isinstance(op.action, V2GraphNeighborAction) for op in operations),
        http_requests=len(starts),
        metadata_records=sum(item.metadata_records for item in completions),
        unique_work_candidates=len(unique),
        acquisition_attempts=0,
        usable_snapshots=0,
        admitted_evidence=ledger_count,
        unknown_requests=unknown_count,
    )
    if acquisition_outputs:
        result = V2DiscoveryAuditCounters.model_validate(
            result.model_copy(
                update={
                    "acquisition_attempts": sum(
                        len(output.attempts) for output in acquisition_outputs
                    ),
                    "usable_snapshots": len(
                        {
                            survivor.snapshot_id
                            for output in acquisition_outputs
                            for survivor in output.survivors
                        }
                    ),
                }
            ).model_dump(mode="python")
        )
    return result


def _find_acquisition_outputs(
    source: DatabaseReader, run_id: UUID
) -> tuple[V2AcquisitionProbeOutput, ...]:
    keys = (
        "phase-5-acquisition-probe",
        "phase-7-round-1-acquisition-probe",
        "phase-7-round-2-acquisition-probe",
        "phase-7-round-3-acquisition-probe",
        "post-phase-13-round-4-acquisition-probe-v1",
    )
    found: list[V2AcquisitionProbeOutput] = []
    for key in keys:
        try:
            envelope = read_v2_artifact(source, run_id, key)
        except KeyError:
            continue
        found.append(V2AcquisitionProbeOutput.model_validate_json(envelope.payload_json))
    return tuple(found)


def insert_audit_counters(
    db_path: str, counters: V2DiscoveryAuditCounters, created_at: datetime
) -> V2DiscoveryAuditCounters:
    counters = _validated(counters)
    expected = compute_discovery_audit_counters(db_path, counters.run_id)
    if counters != expected:
        raise ValueError("audit counters differ from durable artifact evidence")
    _persist_once(db_path, counters, created_at)
    return counters


def insert_discovery_artifact(
    db_path: str,
    artifact: V2DiscoveryArtifact,
    created_at: datetime,
    *,
    acquisition_output: V2AcquisitionProbeOutput | None = None,
    seed_candidate: V2NormalizedDiscoveryCandidate | None = None,
) -> V2DiscoveryArtifact:
    """Strict family dispatch; callers cannot persist arbitrary discovery envelopes."""
    artifact = _validated(artifact)
    if isinstance(artifact, V2DiscoveryBinding):
        bind_discovery_run(db_path, artifact, created_at)
    elif isinstance(artifact, V2DiscoveryOperation):
        insert_discovery_operation(db_path, artifact, created_at)
    elif isinstance(artifact, V2ProviderAttemptStart):
        reserve_provider_attempt(db_path, artifact)
    elif isinstance(artifact, V2ProviderAttemptCompletion):
        complete_provider_attempt(db_path, artifact, created_at)
    elif isinstance(artifact, V2RawDiscoveryCandidate):
        insert_raw_candidate(db_path, artifact, created_at)
    elif isinstance(artifact, V2NormalizedDiscoveryCandidate):
        insert_discovery_candidate(db_path, artifact, created_at)
    elif isinstance(artifact, V2PreviewResult):
        if acquisition_output is None:
            raise ValueError("preview insertion requires its stored acquisition output")
        insert_preview(db_path, artifact, acquisition_output, created_at)
    elif isinstance(artifact, V2SeedEligibility):
        if acquisition_output is None or seed_candidate is None:
            raise ValueError("seed insertion requires candidate and acquisition ownership inputs")
        insert_seed_eligibility(db_path, artifact, acquisition_output, seed_candidate, created_at)
    elif isinstance(artifact, V2ExpansionResult):
        insert_expansion_result(db_path, artifact, created_at)
    elif isinstance(artifact, V2CandidateDisposition):
        insert_candidate_disposition(db_path, artifact, created_at)
    elif isinstance(artifact, V2WorkResolution):
        insert_work_resolution(db_path, artifact, created_at)
    elif isinstance(artifact, V2DiscoveryAuditCounters):
        insert_audit_counters(db_path, artifact, created_at)
    else:
        raise TypeError(f"unsupported discovery artifact type: {type(artifact).__name__}")
    return _validated(artifact)


def insert_raw_candidate(
    db_path: str, candidate: V2RawDiscoveryCandidate, created_at: datetime
) -> V2RawDiscoveryCandidate:
    candidate = _validated(candidate)
    binding = read_discovery_binding(db_path, candidate.run_id)
    _validate_raw_candidate(db_path, candidate, binding)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        prior_raw = [
            V2RawDiscoveryCandidate.model_validate_json(item.payload_json)
            for item in _all_run_artifacts(conn, candidate.run_id)
            if item.artifact_type == "V2RawDiscoveryCandidate"
        ]
        if not any(item.artifact_id == candidate.artifact_id for item in prior_raw):
            if len(prior_raw) >= binding.policy.max_raw_per_run:
                raise ValueError("run raw-candidate cap is exhausted")
            if (
                sum(item.round_number == candidate.round_number for item in prior_raw)
                >= binding.policy.max_raw_per_round
            ):
                raise ValueError("round raw-candidate cap is exhausted")
        _validate_policy(binding, candidate)
        _insert_typed(conn, candidate, created_at)
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
    return candidate
