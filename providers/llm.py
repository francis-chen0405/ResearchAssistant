"""Vendor-neutral synchronous LLM contracts and structured invocation boundary.

Phase 8 defines one typed call at a time.  It records configured fallbacks but never
executes retry or fallback orchestration; those runtime policies belong to Phase 9.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Protocol, runtime_checkable
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from models import (
    PlannerOutput,
    ProvisionalCandidate,
    ScoreDecision,
    StatementDraft,
    StatementReviewResult,
    StrictModel,
    SynthesisOutput,
)

PROMPT_DIRECTORY = Path(__file__).resolve().parents[1] / "prompts"


class LLMStage(StrEnum):
    PLANNER = "planner"
    EXTRACTOR = "extractor"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    SYNTHESIZER = "synthesizer"


class ModelAlias(StrEnum):
    MIMO_V25_PRO = "mimo-v2.5-pro"
    MIMO_V25 = "mimo-v2.5"
    DEEPSEEK_V4_PRO = "deepseek-v4-pro"
    DEEPSEEK_V4_FLASH = "deepseek-v4-flash"


class GenerationSettings(StrictModel):
    """Provider-neutral generation controls requested by application configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: Annotated[float, Field(ge=0.0, le=2.0)] | None
    use_structured_output_control: bool = True


class StageRoute(StrictModel):
    """Exactly one primary alias plus zero, one, or two ordered availability fallbacks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    primary: ModelAlias
    fallbacks: Annotated[tuple[ModelAlias, ...], Field(max_length=2)] = ()
    generation: GenerationSettings

    @model_validator(mode="after")
    def validate_distinct_aliases(self) -> StageRoute:
        ordered_aliases = (self.primary, *self.fallbacks)
        if len(set(ordered_aliases)) != len(ordered_aliases):
            raise ValueError("primary and fallback model aliases must be distinct")
        return self


class LLMRoutingConfig(StrictModel):
    """Complete, validated routing configuration for every Phase 8 LLM stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planner: StageRoute
    extractor: StageRoute
    analyst: StageRoute
    reviewer: StageRoute
    synthesizer: StageRoute

    def for_stage(self, stage: LLMStage) -> StageRoute:
        return getattr(self, stage.value)


DEFAULT_LLM_ROUTING = LLMRoutingConfig(
    planner=StageRoute(
        primary=ModelAlias.MIMO_V25_PRO,
        fallbacks=(ModelAlias.MIMO_V25, ModelAlias.DEEPSEEK_V4_PRO),
        generation=GenerationSettings(temperature=0.2),
    ),
    extractor=StageRoute(
        primary=ModelAlias.MIMO_V25,
        fallbacks=(ModelAlias.MIMO_V25_PRO, ModelAlias.DEEPSEEK_V4_FLASH),
        generation=GenerationSettings(temperature=0.0),
    ),
    analyst=StageRoute(
        primary=ModelAlias.MIMO_V25_PRO,
        fallbacks=(ModelAlias.MIMO_V25, ModelAlias.DEEPSEEK_V4_PRO),
        generation=GenerationSettings(temperature=0.1),
    ),
    reviewer=StageRoute(
        primary=ModelAlias.MIMO_V25,
        fallbacks=(ModelAlias.MIMO_V25_PRO, ModelAlias.DEEPSEEK_V4_PRO),
        generation=GenerationSettings(temperature=0.0),
    ),
    synthesizer=StageRoute(
        primary=ModelAlias.MIMO_V25_PRO,
        fallbacks=(ModelAlias.MIMO_V25, ModelAlias.DEEPSEEK_V4_PRO),
        generation=GenerationSettings(temperature=0.15),
    ),
)


class PromptTemplate(StrictModel):
    """Loaded prompt text with application-controlled version and content hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: LLMStage
    version: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str = Field(min_length=1)


class LLMProviderCapabilities(StrictModel):
    """Controls that a concrete provider adapter can honor explicitly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_temperature: bool
    supports_structured_output_control: bool


class LLMRequest(StrictModel):
    """Immutable application-owned request passed to one vendor adapter call."""

    # BaseModel instances and BaseModel classes are intentionally carried without
    # converting them to dictionaries.  The exception only enables those Python types;
    # unknown fields remain forbidden and the request remains frozen.
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    run_id: UUID
    stage: LLMStage
    prompt: PromptTemplate
    rendered_prompt: str = Field(min_length=1)
    input_artifact: object
    input_artifact_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    requested_output_type: type[BaseModel]
    model_alias: ModelAlias
    pinned_model_snapshot: str | None = None
    configured_fallbacks: Annotated[tuple[ModelAlias, ...], Field(max_length=2)] = ()
    generation: GenerationSettings

    @field_validator("input_artifact")
    @classmethod
    def validate_input_artifact(cls, value: object) -> object:
        if not isinstance(value, BaseModel):
            raise ValueError("input_artifact must be a Pydantic model instance")
        return value

    @field_validator("input_artifact_ids")
    @classmethod
    def validate_input_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("input_artifact_ids must be unique")
        return value

    @field_validator("pinned_model_snapshot")
    @classmethod
    def validate_pinned_snapshot(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("pinned_model_snapshot cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_application_controls(self) -> LLMRequest:
        if self.prompt.stage is not self.stage:
            raise ValueError("prompt stage must match the requested stage")
        if self.model_alias in self.configured_fallbacks:
            raise ValueError("primary model alias cannot also be a configured fallback")
        if self.requested_output_type not in _allowed_output_types(self.stage):
            raise ValueError("requested output type is not allowed for this stage")
        return self


@runtime_checkable
class LLMProvider(Protocol):
    """Vendor-isolated synchronous provider.  Normal tests inject deterministic fakes."""

    capabilities: LLMProviderCapabilities

    def generate(self, request: LLMRequest) -> BaseModel:
        """Return one Pydantic artifact; raw dictionaries are invalid provider output."""


class InvocationStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class InvocationFailureCode(StrEnum):
    UNSUPPORTED_PARAMETER = "unsupported_parameter"
    PROVIDER_ERROR = "provider_error"
    NON_PYDANTIC_RESPONSE = "non_pydantic_response"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"


class RetryMetadata(StrictModel):
    """Audit metadata only; Phase 8 never performs an automatic retry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=1, ge=1)
    retry_count: int = Field(default=0, ge=0)
    automatic_retry_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_counts(self) -> RetryMetadata:
        if self.attempt_number > self.max_attempts:
            raise ValueError("attempt_number cannot exceed max_attempts")
        if self.retry_count != self.attempt_number - 1:
            raise ValueError("retry_count must equal attempt_number minus one")
        return self


class InvocationFailure(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: InvocationFailureCode
    message: str = Field(min_length=1)
    retryable: bool


class LLMInvocationRecord(StrictModel):
    """Complete success/failure provenance for one and only one provider call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    invocation_id: UUID
    stage: LLMStage
    prompt_version: str = Field(min_length=1)
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_output_type: str = Field(min_length=1)
    model_alias: ModelAlias
    pinned_model_snapshot: str | None = None
    configured_fallbacks: tuple[ModelAlias, ...]
    fallback_executed: Literal[False] = False
    input_artifact_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    started_at: datetime
    ended_at: datetime
    status: InvocationStatus
    retry: RetryMetadata
    failure: InvocationFailure | None = None

    @field_validator("started_at", "ended_at")
    @classmethod
    def validate_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("invocation timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_result_shape(self) -> LLMInvocationRecord:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at cannot precede started_at")
        if self.status is InvocationStatus.COMPLETED and self.failure is not None:
            raise ValueError("completed invocations cannot include failure metadata")
        if self.status is InvocationStatus.FAILED and self.failure is None:
            raise ValueError("failed invocations require failure metadata")
        return self


class LLMInvocationResult(StrictModel):
    """Successful typed output paired with its immutable invocation record."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    record: LLMInvocationRecord
    output_artifact: object

    @field_validator("output_artifact")
    @classmethod
    def validate_output_artifact(cls, value: object) -> object:
        if not isinstance(value, BaseModel):
            raise ValueError("output_artifact must be a Pydantic model instance")
        return value

    @model_validator(mode="after")
    def validate_completed_record(self) -> LLMInvocationResult:
        if self.record.status is not InvocationStatus.COMPLETED:
            raise ValueError("successful invocation results require a completed record")
        if type(self.output_artifact).__name__ != self.record.requested_output_type:
            raise ValueError("output artifact type must match invocation provenance")
        return self


class LLMInvocationError(RuntimeError):
    """Raised for a failed invocation while preserving its typed audit record."""

    def __init__(self, message: str, record: LLMInvocationRecord) -> None:
        super().__init__(message)
        self.record = record


class LLMInvocationCapabilityError(LLMInvocationError):
    """Raised when configured controls exceed declared provider capabilities."""


class LLMResponseValidationError(LLMInvocationError):
    """Raised when provider output is raw, malformed, or violates the requested schema."""


class LLMProviderExecutionError(LLMInvocationError):
    """Raised when the provider adapter itself fails."""


class _InvocationProblem(RuntimeError):
    def __init__(
        self,
        code: InvocationFailureCode,
        message: str,
        *,
        retryable: bool,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.cause = cause


def compute_prompt_hash(text: str) -> str:
    """Return a stable SHA-256 for the exact UTF-8 prompt file contents."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_prompt_file(
    path: Path,
    *,
    expected_stage: LLMStage | None = None,
) -> PromptTemplate:
    """Load and validate the version/stage header of one structured prompt file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 3 or not lines[0].startswith("Prompt-Version: "):
        raise ValueError(f"prompt {path} must start with a Prompt-Version header")
    if not lines[1].startswith("Stage: "):
        raise ValueError(f"prompt {path} must include a Stage header on line 2")

    version = lines[0].removeprefix("Prompt-Version: ").strip()
    stage = LLMStage(lines[1].removeprefix("Stage: ").strip())
    if expected_stage is not None and stage is not expected_stage:
        raise ValueError(
            f"prompt {path} declares stage {stage.value}, expected {expected_stage.value}"
        )
    return PromptTemplate(
        stage=stage,
        version=version,
        sha256=compute_prompt_hash(text),
        text=text,
    )


def load_prompt(
    stage: LLMStage,
    *,
    prompt_directory: Path = PROMPT_DIRECTORY,
) -> PromptTemplate:
    """Load the application-selected prompt for a stage."""
    return load_prompt_file(
        prompt_directory / f"{stage.value}.md",
        expected_stage=stage,
    )


def render_stage_prompt(
    prompt: PromptTemplate,
    input_artifact: BaseModel,
    requested_output_type: type[BaseModel],
) -> str:
    """Render typed input and the application-selected schema at the provider boundary."""
    input_json = input_artifact.model_dump_json(indent=2)
    schema_json = json.dumps(
        requested_output_type.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        f"{prompt.text.rstrip()}\n\n"
        "<APPLICATION_CONTROLLED_OUTPUT_CONTRACT>\n"
        f"Requested Pydantic artifact: {requested_output_type.__name__}\n"
        "Return only data matching this schema. Do not add fields or choose another schema.\n"
        f"{schema_json}\n"
        "</APPLICATION_CONTROLLED_OUTPUT_CONTRACT>\n\n"
        "<APPLICATION_CONTROLLED_STAGE_INPUT>\n"
        f"{input_json}\n"
        "</APPLICATION_CONTROLLED_STAGE_INPUT>"
    )


def build_stage_request(
    *,
    stage: LLMStage,
    input_artifact: BaseModel,
    requested_output_type: type[BaseModel],
    input_artifact_ids: Sequence[UUID],
    routing: LLMRoutingConfig = DEFAULT_LLM_ROUTING,
    prompt_directory: Path = PROMPT_DIRECTORY,
    generation_settings: GenerationSettings | None = None,
    pinned_model_snapshot: str | None = None,
) -> LLMRequest:
    """Select only the configured primary route and build one immutable request."""
    if not isinstance(input_artifact, BaseModel):
        raise TypeError("input_artifact must be a Pydantic model instance")
    if not isinstance(requested_output_type, type) or not issubclass(
        requested_output_type, BaseModel
    ):
        raise TypeError("requested_output_type must be a Pydantic model class")

    stage = LLMStage(stage)
    route = routing.for_stage(stage)
    prompt = load_prompt(stage, prompt_directory=prompt_directory)
    settings = generation_settings or route.generation
    run_id = getattr(input_artifact, "run_id", None)
    if not isinstance(run_id, UUID):
        raise ValueError("input artifact must carry a UUID run_id")
    return LLMRequest(
        run_id=run_id,
        stage=stage,
        prompt=prompt,
        rendered_prompt=render_stage_prompt(prompt, input_artifact, requested_output_type),
        input_artifact=input_artifact,
        input_artifact_ids=tuple(input_artifact_ids),
        requested_output_type=requested_output_type,
        model_alias=route.primary,
        pinned_model_snapshot=pinned_model_snapshot,
        configured_fallbacks=route.fallbacks,
        generation=settings,
    )


def validate_provider_capabilities(
    capabilities: LLMProviderCapabilities,
    generation: GenerationSettings,
) -> None:
    """Reject unsupported controls explicitly; never drop parameters silently."""
    if generation.temperature is not None and not capabilities.supports_temperature:
        raise _InvocationProblem(
            InvocationFailureCode.UNSUPPORTED_PARAMETER,
            "provider does not support the configured temperature parameter",
            retryable=False,
        )
    if (
        generation.use_structured_output_control
        and not capabilities.supports_structured_output_control
    ):
        raise _InvocationProblem(
            InvocationFailureCode.UNSUPPORTED_PARAMETER,
            "provider does not support the configured structured-output control",
            retryable=False,
        )


def invoke_llm(
    provider: LLMProvider,
    request: LLMRequest,
    *,
    retry_metadata: RetryMetadata | None = None,
    clock: Callable[[], datetime] | None = None,
    invocation_id_factory: Callable[[], UUID] = uuid4,
) -> LLMInvocationResult:
    """Execute one primary-model call, validate it, and record success or failure."""
    now = clock or _utc_now
    started_at = _aware_timestamp(now(), "started_at")
    retry = retry_metadata or RetryMetadata()

    try:
        capabilities = provider.capabilities
        if not isinstance(capabilities, LLMProviderCapabilities):
            raise _InvocationProblem(
                InvocationFailureCode.PROVIDER_ERROR,
                "provider capabilities must be an LLMProviderCapabilities artifact",
                retryable=False,
            )
        validate_provider_capabilities(capabilities, request.generation)
        try:
            response = provider.generate(request)
        except Exception as exc:
            raise _InvocationProblem(
                InvocationFailureCode.PROVIDER_ERROR,
                f"LLM provider failed: {exc}",
                retryable=True,
                cause=exc,
            ) from exc

        if not isinstance(response, BaseModel):
            raise _InvocationProblem(
                InvocationFailureCode.NON_PYDANTIC_RESPONSE,
                "LLM provider returned a non-Pydantic response",
                retryable=False,
            )
        try:
            output_artifact = request.requested_output_type.model_validate(
                response.model_dump(mode="python", round_trip=True)
            )
        except ValidationError as exc:
            raise _InvocationProblem(
                InvocationFailureCode.SCHEMA_VALIDATION_FAILED,
                f"LLM response failed {request.requested_output_type.__name__} validation: {exc}",
                retryable=False,
                cause=exc,
            ) from exc
    except _InvocationProblem as problem:
        ended_at = _aware_timestamp(now(), "ended_at")
        record = _invocation_record(
            request=request,
            invocation_id=invocation_id_factory(),
            started_at=started_at,
            ended_at=ended_at,
            retry=retry,
            status=InvocationStatus.FAILED,
            failure=InvocationFailure(
                code=problem.code,
                message=str(problem),
                retryable=problem.retryable,
            ),
        )
        error_type: type[LLMInvocationError]
        if problem.code is InvocationFailureCode.UNSUPPORTED_PARAMETER:
            error_type = LLMInvocationCapabilityError
        elif problem.code in {
            InvocationFailureCode.NON_PYDANTIC_RESPONSE,
            InvocationFailureCode.SCHEMA_VALIDATION_FAILED,
        }:
            error_type = LLMResponseValidationError
        else:
            error_type = LLMProviderExecutionError
        raise error_type(str(problem), record) from problem.cause

    ended_at = _aware_timestamp(now(), "ended_at")
    record = _invocation_record(
        request=request,
        invocation_id=invocation_id_factory(),
        started_at=started_at,
        ended_at=ended_at,
        retry=retry,
        status=InvocationStatus.COMPLETED,
        failure=None,
    )
    return LLMInvocationResult(record=record, output_artifact=output_artifact)


def _allowed_output_types(stage: LLMStage) -> tuple[type[BaseModel], ...]:
    if stage is LLMStage.PLANNER:
        return (PlannerOutput,)
    if stage is LLMStage.EXTRACTOR:
        return (ProvisionalCandidate,)
    if stage is LLMStage.ANALYST:
        return (ScoreDecision, StatementDraft)
    if stage is LLMStage.REVIEWER:
        return (StatementReviewResult,)
    return (SynthesisOutput,)


def _invocation_record(
    *,
    request: LLMRequest,
    invocation_id: UUID,
    started_at: datetime,
    ended_at: datetime,
    retry: RetryMetadata,
    status: InvocationStatus,
    failure: InvocationFailure | None,
) -> LLMInvocationRecord:
    return LLMInvocationRecord(
        run_id=request.run_id,
        invocation_id=invocation_id,
        stage=request.stage,
        prompt_version=request.prompt.version,
        prompt_hash=request.prompt.sha256,
        requested_output_type=request.requested_output_type.__name__,
        model_alias=request.model_alias,
        pinned_model_snapshot=request.pinned_model_snapshot,
        configured_fallbacks=request.configured_fallbacks,
        input_artifact_ids=request.input_artifact_ids,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        retry=retry,
        failure=failure,
    )


def _aware_timestamp(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
