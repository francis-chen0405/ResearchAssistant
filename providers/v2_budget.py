"""Run-wide v2 physical-call and token enforcement at the provider boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock, local
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    ModelUsageMetadata,
    StrictModel,
)
from money import add_usd
from providers.llm import LLMProvider, LLMProviderCapabilities, LLMRequest, ModelAlias
from providers.pricing import conservative_token_estimate
from providers.v2_routing import V2RoutingConfig
from store import insert_v2_artifact, read_v2_artifact

V2_MAX_PHYSICAL_CALLS = 160
V2_MAX_TOTAL_TOKENS = 500_000
V2_DEFAULT_TOTAL_COST_USD = Decimal("0.20")
V2_BUDGET_POLICY_IDENTITY = "researchassistant-v2-phase-12-run-budget-v1"


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
    source_token_cap: int = Field(
        default=V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
        ge=1,
        le=V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
    )
    source_physical_call_cap: int = Field(
        default=V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
        ge=1,
        le=V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
    )
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
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = str(Path(db_path).resolve())
        self._run_id = run_id
        self._provider = provider
        self._routing = routing_config
        self._ceilings = ceilings
        self._clock = clock or _utc_now
        self._lock = Lock()
        self._starts, self._completions = _read_audit(self._path, run_id)

    def snapshot(self) -> V2BudgetSnapshot:
        with self._lock:
            return _snapshot(self._starts, self._completions, self._ceilings)

    def generate(self, request: LLMRequest) -> BaseModel:
        if request.run_id != self._run_id:
            raise ValueError("budgeted provider request must match its v2 run")
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
                source_token_cap=(request.source_token_cap or V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP),
                source_physical_call_cap=(
                    request.source_physical_call_cap or V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP
                ),
                started_at=_aware(self._clock()),
            )
            insert_v2_artifact(
                self._path,
                _start_key(sequence),
                started,
                started.started_at,
            )
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


def _read_audit(
    path: str,
    run_id: UUID,
) -> tuple[list[V2PhysicalCallStart], dict[int, V2PhysicalCallCompletion]]:
    starts: list[V2PhysicalCallStart] = []
    completions: dict[int, V2PhysicalCallCompletion] = {}
    for sequence in range(1, V2_MAX_PHYSICAL_CALLS + 1):
        try:
            start_row = read_v2_artifact(path, run_id, _start_key(sequence))
        except KeyError:
            break
        starts.append(V2PhysicalCallStart.model_validate_json(start_row.payload_json))
        try:
            completion_row = read_v2_artifact(path, run_id, _completion_key(sequence))
        except KeyError:
            continue
        completions[sequence] = V2PhysicalCallCompletion.model_validate_json(
            completion_row.payload_json
        )
    return starts, completions


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
    return f"phase-12-physical-call-{sequence:03d}-start"


def _completion_key(sequence: int) -> str:
    return f"phase-12-physical-call-{sequence:03d}-completion"


def _utc_now() -> datetime:
    return datetime.now(UTC)
