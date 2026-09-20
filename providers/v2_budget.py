"""Run-wide v2 physical-call and token enforcement at the provider boundary."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock, local
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    ModelUsageMetadata,
    StrictModel,
    V2PersistedArtifact,
)
from money import add_usd
from providers.llm import (
    LLMProvider,
    LLMProviderCapabilities,
    LLMRequest,
    ModelAlias,
    V2CancellationRequested,
)
from providers.pricing import conservative_token_estimate
from providers.v2_routing import V2RoutingConfig
from store import DatabaseReader, insert_v2_artifact, read_v2_physical_call_artifacts

V2_MAX_PHYSICAL_CALLS = 160
V2_MAX_TOTAL_TOKENS = 500_000
V2_DEFAULT_TOTAL_COST_USD = Decimal("0.20")
V2_BUDGET_POLICY_IDENTITY = "researchassistant-v2-phase-13-run-budget-analyzer-admission-v1"
V2_PHYSICAL_CALL_LEGACY_ARTIFACT_PREFIX = "phase-12-physical-call"
V2_PHYSICAL_CALL_ARTIFACT_PREFIX = "phase-13-physical-call"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 budget timestamps must be timezone-aware")
    return value


class V2RunCeilings(StrictModel):
    """Fresh-v2 ceilings. Configured values may be lower, never higher."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_physical_calls: int = Field(default=V2_MAX_PHYSICAL_CALLS, ge=1, le=160)
    max_total_tokens: int = Field(default=V2_MAX_TOTAL_TOKENS, ge=1, le=500_000)
    max_total_cost_usd: Decimal = Field(default=V2_DEFAULT_TOTAL_COST_USD, gt=0)
    policy_identity: str = V2_BUDGET_POLICY_IDENTITY


class V2PhysicalCallStart(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    sequence: int = Field(ge=1, le=160)
    stage: str = Field(min_length=1)
    model_alias: str = Field(min_length=1)
    reserved_tokens: int = Field(ge=1)
    reserved_cost_usd: Decimal = Field(ge=0)
    source_id: UUID | None = None
    input_artifact_ids: tuple[UUID, ...] = ()
    source_token_cap: int = Field(
        default=V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
        ge=1,
        le=V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    )
    source_physical_call_cap: Literal[3, 7] = V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
    started_at: datetime

    _started_at_is_aware = field_validator("started_at")(_aware)


class V2PhysicalCallCompletion(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    sequence: int = Field(ge=1, le=160)
    succeeded: bool
    usage_tokens: int | None = Field(default=None, ge=0)
    usage_cost_usd: Decimal | None = Field(default=None, ge=0)
    failure: str | None = None
    completed_at: datetime

    _completed_at_is_aware = field_validator("completed_at")(_aware)

    @model_validator(mode="after")
    def validate_failure(self) -> V2PhysicalCallCompletion:
        if self.succeeded == (self.failure is not None):
            raise ValueError("physical-call success and failure fields must agree")
        return self


class V2PhysicalCallAudit(StrictModel):
    """One dense, globally ordered physical-call audit with unknown completions retained."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    starts: tuple[V2PhysicalCallStart, ...]
    completions: tuple[V2PhysicalCallCompletion | None, ...]

    @model_validator(mode="after")
    def validate_sequences(self) -> V2PhysicalCallAudit:
        if len(self.starts) != len(self.completions):
            raise ValueError("physical-call starts and completions must be aligned")
        sequences = tuple(item.sequence for item in self.starts)
        expected = tuple(range(1, len(sequences) + 1))
        if sequences != expected:
            raise ValueError("physical-call audit start sequence must be dense")
        for start, completion in zip(self.starts, self.completions, strict=True):
            if completion is not None and completion.sequence != start.sequence:
                raise ValueError("physical-call completion sequence does not match its start")
        return self


class V2BudgetSnapshot(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    physical_calls_used: int = Field(ge=0, le=160)
    token_exposure: int = Field(ge=0)
    cost_exposure_usd: Decimal = Field(ge=0)
    physical_calls_remaining: int = Field(ge=0, le=160)
    tokens_remaining: int = Field(ge=0)
    cost_remaining_usd: Decimal = Field(ge=0)


class V2BudgetExceededError(RuntimeError):
    """Raised before a physical call whose conservative exposure cannot fit."""


class RoutedV2LLMProvider:
    """Dispatch logical aliases to explicitly configured physical adapters."""

    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self, providers: Mapping[ModelAlias, LLMProvider]) -> None:
        required = {
            ModelAlias.MIMO_V25,
            ModelAlias.MIMO_V25_PRO,
            ModelAlias.GPT_5_6_LUNA_HIGH,
        }
        if set(providers) != required:
            raise ValueError("v2 routed provider requires exact normal, Pro, and Luna aliases")
        self._providers = dict(providers)
        self._thread_state = local()

    def generate(self, request: LLMRequest) -> BaseModel:
        provider = self._providers[request.model_alias]
        self._thread_state.provider = provider
        return provider.generate(request)

    def usage_for(
        self,
        request: LLMRequest,
        output: BaseModel,
        invocation_record: object,
    ) -> ModelUsageMetadata | None:
        provider = getattr(self._thread_state, "provider", None)
        method = getattr(provider, "usage_for", None)
        if not callable(method):
            return None
        usage = method(request, output, invocation_record)
        return usage if isinstance(usage, ModelUsageMetadata) else None

    def failure_usage_for(self) -> ModelUsageMetadata | None:
        provider = getattr(self._thread_state, "provider", None)
        method = getattr(provider, "failure_usage_for", None)
        if not callable(method):
            return None
        usage = method()
        return usage if isinstance(usage, ModelUsageMetadata) else None


class BudgetedV2LLMProvider:
    """Count and persist every physical attempt, including provider failures and retries."""

    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(
        self,
        *,
        db_path: str | Path,
        run_id: UUID,
        provider: LLMProvider,
        routing_config: V2RoutingConfig,
        ceilings: V2RunCeilings,
        cancellation_requested: Callable[[], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = str(Path(db_path).resolve())
        self._run_id = run_id
        self._provider = provider
        self._routing = routing_config
        self._ceilings = ceilings
        self._cancellation_requested = cancellation_requested
        self._clock = clock or _utc_now
        self._lock = Lock()
        self._starts, self._completions = _read_audit(self._path, run_id)

    def snapshot(self) -> V2BudgetSnapshot:
        with self._lock:
            return _snapshot(self._starts, self._completions, self._ceilings)

    def generate(self, request: LLMRequest) -> BaseModel:
        if request.run_id != self._run_id:
            raise ValueError("budgeted provider request must match its v2 run")
        if self._cancellation_requested is not None and self._cancellation_requested():
            raise V2CancellationRequested("v2 cancellation was observed before a model call")
        reservation = self._routing.preflight().reserve(
            request.stage,
            conservative_token_estimate(request.rendered_prompt),
        )
        with self._lock:
            current = _snapshot(self._starts, self._completions, self._ceilings)
            if current.physical_calls_remaining < 1:
                raise V2BudgetExceededError("v2 physical-call ceiling is exhausted")
            if reservation.reserved_tokens > current.tokens_remaining:
                raise V2BudgetExceededError("v2 total-token ceiling cannot cover this call")
            if reservation.reserved_cost_usd > current.cost_remaining_usd:
                raise V2BudgetExceededError("v2 cost ceiling cannot cover this call")
            if request.source_id is not None:
                source_starts = [
                    item for item in self._starts if item.source_id == request.source_id
                ]
                source_tokens, _source_cost = _source_exposure(source_starts, self._completions)
                source_token_cap = request.source_token_cap or V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP
                source_call_cap = (
                    request.source_physical_call_cap or V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
                )
                if len(source_starts) >= source_call_cap:
                    raise V2BudgetExceededError(
                        f"source {request.source_id} physical-call cap is exhausted"
                    )
                if source_tokens + reservation.reserved_tokens > source_token_cap:
                    raise V2BudgetExceededError(
                        f"source {request.source_id} token cap cannot cover this call"
                    )
            sequence = len(self._starts) + 1
            started = V2PhysicalCallStart(
                run_id=self._run_id,
                sequence=sequence,
                stage=request.stage.value,
                model_alias=request.model_alias.value,
                reserved_tokens=reservation.reserved_tokens,
                reserved_cost_usd=reservation.reserved_cost_usd,
                source_id=request.source_id,
                input_artifact_ids=request.input_artifact_ids,
                source_token_cap=(request.source_token_cap or V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP),
                source_physical_call_cap=(
                    request.source_physical_call_cap or V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
                ),
                started_at=_aware(self._clock()),
            )
            try:
                insert_v2_artifact(
                    self._path,
                    _start_key(sequence),
                    started,
                    started.started_at,
                )
            except Exception:
                # A persistence error may occur after SQLite has committed the
                # immutable start row.  Refresh before propagating so the caller
                # fails closed with conservative exposure rather than losing a
                # reservation from its audit view.
                try:
                    self._starts, self._completions = _read_audit(self._path, self._run_id)
                except Exception:
                    pass
                raise
            self._starts.append(started)
        try:
            output = self._provider.generate(request)
        except Exception as exc:
            usage = _failure_usage(self._provider)
            self._complete(sequence, False, usage, f"{type(exc).__name__}: {exc}"[:1000])
            raise
        usage = _completed_usage(self._provider, request, output)
        self._complete(sequence, True, usage, None)
        return output

    def usage_for(
        self,
        request: LLMRequest,
        output: BaseModel,
        invocation_record: object,
    ) -> ModelUsageMetadata | None:
        method = getattr(self._provider, "usage_for", None)
        if not callable(method):
            return None
        usage = method(request, output, invocation_record)
        return usage if isinstance(usage, ModelUsageMetadata) else None

    def failure_usage_for(self) -> ModelUsageMetadata | None:
        return _failure_usage(self._provider)

    def _complete(
        self,
        sequence: int,
        succeeded: bool,
        usage: ModelUsageMetadata | None,
        failure: str | None,
    ) -> None:
        completion = V2PhysicalCallCompletion(
            run_id=self._run_id,
            sequence=sequence,
            succeeded=succeeded,
            usage_tokens=_usage_tokens(usage),
            usage_cost_usd=(usage.cost_usd if usage is not None else None),
            failure=failure,
            completed_at=_aware(self._clock()),
        )
        with self._lock:
            insert_v2_artifact(
                self._path,
                _completion_key(sequence),
                completion,
                completion.completed_at,
            )
            self._completions[sequence] = completion


def _snapshot(
    starts: list[V2PhysicalCallStart],
    completions: dict[int, V2PhysicalCallCompletion],
    ceilings: V2RunCeilings,
) -> V2BudgetSnapshot:
    tokens = 0
    cost = Decimal("0")
    for started in starts:
        completed = completions.get(started.sequence)
        tokens += (
            completed.usage_tokens
            if completed is not None and completed.usage_tokens is not None
            else started.reserved_tokens
        )
        cost = add_usd(
            cost,
            (
                completed.usage_cost_usd
                if completed is not None and completed.usage_cost_usd is not None
                else started.reserved_cost_usd
            ),
        )
    remaining_cost = max(Decimal("0"), ceilings.max_total_cost_usd - cost)
    return V2BudgetSnapshot(
        physical_calls_used=len(starts),
        token_exposure=tokens,
        cost_exposure_usd=cost,
        physical_calls_remaining=ceilings.max_physical_calls - len(starts),
        tokens_remaining=max(0, ceilings.max_total_tokens - tokens),
        cost_remaining_usd=remaining_cost,
    )


def _source_exposure(
    starts: list[V2PhysicalCallStart],
    completions: dict[int, V2PhysicalCallCompletion],
) -> tuple[int, Decimal]:
    tokens = 0
    cost = Decimal("0")
    for started in starts:
        completed = completions.get(started.sequence)
        tokens += (
            completed.usage_tokens
            if completed is not None and completed.usage_tokens is not None
            else started.reserved_tokens
        )
        cost = add_usd(
            cost,
            (
                completed.usage_cost_usd
                if completed is not None and completed.usage_cost_usd is not None
                else started.reserved_cost_usd
            ),
        )
    return tokens, cost


_PHYSICAL_CALL_ARTIFACT_KEY = re.compile(
    r"^(?P<prefix>phase-(?:12|13)-physical-call)-(?P<sequence>[0-9]{3})-"
    r"(?P<kind>start|completion)$"
)


def read_v2_physical_call_audit(
    db_path: DatabaseReader,
    run_id: UUID,
) -> V2PhysicalCallAudit:
    """Read and validate the complete current/legacy physical-call audit in one query."""
    rows = read_v2_physical_call_artifacts(db_path, run_id)
    selected: dict[tuple[int, str], tuple[int, V2PersistedArtifact]] = {}
    for row in rows:
        match = _PHYSICAL_CALL_ARTIFACT_KEY.fullmatch(row.artifact_key)
        if match is None:
            raise ValueError(f"invalid physical-call artifact key: {row.artifact_key}")
        sequence = int(match["sequence"])
        kind = match["kind"]
        prefix = match["prefix"]
        prefix_rank = 0 if prefix == V2_PHYSICAL_CALL_ARTIFACT_PREFIX else 1
        key = (sequence, kind)
        previous = selected.get(key)
        if previous is None or prefix_rank < previous[0]:
            selected[key] = (prefix_rank, row)

    starts_by_sequence: dict[int, V2PhysicalCallStart] = {}
    completions_by_sequence: dict[int, V2PhysicalCallCompletion] = {}
    for (sequence, kind), (_prefix_rank, row) in selected.items():
        if row.run_id != run_id:
            raise ValueError(f"physical-call artifact {row.artifact_key} has the wrong run_id")
        expected_type = "V2PhysicalCallStart" if kind == "start" else "V2PhysicalCallCompletion"
        if row.artifact_type != expected_type:
            raise ValueError(
                f"physical-call artifact {row.artifact_key} has type {row.artifact_type!r}"
            )
        if kind == "start":
            start = V2PhysicalCallStart.model_validate_json(row.payload_json)
            if start.run_id != run_id:
                raise ValueError(f"physical-call artifact {row.artifact_key} has the wrong run_id")
            if start.sequence != sequence:
                raise ValueError(
                    f"physical-call artifact {row.artifact_key} has the wrong sequence"
                )
            starts_by_sequence[sequence] = start
        else:
            completion = V2PhysicalCallCompletion.model_validate_json(row.payload_json)
            if completion.run_id != run_id:
                raise ValueError(f"physical-call artifact {row.artifact_key} has the wrong run_id")
            if completion.sequence != sequence:
                raise ValueError(
                    f"physical-call artifact {row.artifact_key} has the wrong sequence"
                )
            completions_by_sequence[sequence] = completion

    if set(completions_by_sequence).difference(starts_by_sequence):
        raise ValueError("physical-call completion has no corresponding start")
    sequences = tuple(sorted(starts_by_sequence))
    starts = tuple(starts_by_sequence[sequence] for sequence in sequences)
    completions = tuple(completions_by_sequence.get(sequence) for sequence in sequences)
    return V2PhysicalCallAudit(starts=starts, completions=completions)


def _read_audit(
    path: str,
    run_id: UUID,
) -> tuple[list[V2PhysicalCallStart], dict[int, V2PhysicalCallCompletion]]:
    """Preserve the historical mutable audit projection for the budget provider."""
    audit = read_v2_physical_call_audit(path, run_id)
    return list(audit.starts), {
        completion.sequence: completion
        for completion in audit.completions
        if completion is not None
    }


def _completed_usage(
    provider: LLMProvider,
    request: LLMRequest,
    output: BaseModel,
) -> ModelUsageMetadata | None:
    method = getattr(provider, "usage_for", None)
    if not callable(method):
        return None
    try:
        usage = method(request, output, None)
    except Exception:
        return None
    return usage if isinstance(usage, ModelUsageMetadata) else None


def _failure_usage(provider: LLMProvider) -> ModelUsageMetadata | None:
    method = getattr(provider, "failure_usage_for", None)
    if not callable(method):
        return None
    try:
        usage = method()
    except Exception:
        return None
    return usage if isinstance(usage, ModelUsageMetadata) else None


def _usage_tokens(usage: ModelUsageMetadata | None) -> int | None:
    if usage is None:
        return None
    if usage.total_tokens is not None:
        return usage.total_tokens
    if usage.input_tokens is not None and usage.output_tokens is not None:
        return usage.input_tokens + usage.output_tokens
    return None


def _start_key(sequence: int) -> str:
    return f"{V2_PHYSICAL_CALL_ARTIFACT_PREFIX}-{sequence:03d}-start"


def _completion_key(sequence: int) -> str:
    return f"{V2_PHYSICAL_CALL_ARTIFACT_PREFIX}-{sequence:03d}-completion"


def _utc_now() -> datetime:
    return datetime.now(UTC)
