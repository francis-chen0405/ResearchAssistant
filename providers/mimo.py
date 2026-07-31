"""Direct Xiaomi MiMo JSON-mode adapter for the authorized MVP-3B route."""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal
from enum import StrEnum
from threading import local
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from models import ModelUsageMetadata, StrictModel
from providers.config import MimoConfig
from providers.llm import LLMProviderCapabilities, LLMRequest, LLMStage, ModelAlias
from providers.pricing import DIRECT_MIMO_PRICE_CAP, ModelPriceCap, conservative_token_estimate


class MimoFailureCode(StrEnum):
    MISSING_CONFIGURATION = "missing_configuration"
    AUTHENTICATION = "authentication_failure"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    TRANSIENT_OUTAGE = "transient_outage"
    PERMANENT_FAILURE = "permanent_request_failure"
    MALFORMED_RESPONSE = "malformed_success_response"
    MALFORMED_JSON = "malformed_json"
    TRUNCATED = "truncated_output"
    REFUSAL = "provider_refusal"
    SCHEMA = "schema_validation_failure"
    CAPABILITY = "capability_mismatch"
    MODEL_MISMATCH = "returned_model_mismatch"
    MALFORMED_USAGE = "malformed_usage_metadata"
    UNKNOWN_PRICING = "unknown_pricing"
    BUDGET = "cost_ceiling_exceeded"


class MimoProviderError(RuntimeError):
    def __init__(
        self,
        code: MimoFailureCode,
        message: str,
        *,
        retryable: bool,
        http_status: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status
        self.request_id = request_id


class MimoCallMetadata(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_version: str
    requested_model: str
    returned_model: str
    request_id: str | None = None
    response_id: str
    elapsed_seconds: float = Field(ge=0)
    usage: ModelUsageMetadata
    cost_estimated: bool


class XiaomiMimoAdapter:
    """One direct physical MiMo call; orchestration owns the one allowed retry."""

    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(
        self,
        config: MimoConfig,
        *,
        client: httpx.Client | None = None,
        price_cap: ModelPriceCap = DIRECT_MIMO_PRICE_CAP,
        max_call_cost_usd: Decimal = Decimal("1.00"),
        max_call_tokens: int = 1_000_000,
    ) -> None:
        if price_cap.model != config.model:
            raise MimoProviderError(
                MimoFailureCode.UNKNOWN_PRICING,
                "direct MiMo pricing does not cover the configured model",
                retryable=False,
            )
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.synthesizer_seconds),
            follow_redirects=False,
            headers={"api-key": config.api_key.get_secret_value()},
        )
        self._price_cap = price_cap
        self._max_call_cost_usd = max_call_cost_usd
        self._max_call_tokens = max_call_tokens
        self._thread_state = local()

    def generate(self, request: LLMRequest) -> BaseModel:
        self._thread_state.last_failure_usage = None
        if request.model_alias is not ModelAlias.MIMO_V25_PRO:
            raise MimoProviderError(
                MimoFailureCode.CAPABILITY,
                "direct Xiaomi MiMo supports only the approved MiMo Pro alias",
                retryable=False,
            )
        input_estimate = conservative_token_estimate(_direct_mimo_prompt(request))
        reserved_tokens = input_estimate + self._config.max_completion_tokens
        reserved_cost = self._price_cap.upper_bound(
            input_estimate,
            self._config.max_completion_tokens,
        )
        if reserved_tokens > self._max_call_tokens or reserved_cost > self._max_call_cost_usd:
            raise MimoProviderError(
                MimoFailureCode.BUDGET,
                "the conservative direct MiMo reservation exceeds the call ceiling",
                retryable=False,
            )
        started = time.monotonic()
        try:
            response = self._client.post(
                "/chat/completions",
                json=_request_payload(request, self._config),
                timeout=_deadline_for(request.stage, self._config),
                headers={"api-key": self._config.api_key.get_secret_value()},
            )
        except httpx.TimeoutException as exc:
            raise MimoProviderError(
                MimoFailureCode.TIMEOUT,
                "Xiaomi MiMo request timed out",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise MimoProviderError(
                MimoFailureCode.TRANSIENT_OUTAGE,
                "Xiaomi MiMo connection failed",
                retryable=True,
            ) from exc
        elapsed = time.monotonic() - started
        self._record_failure_usage(response)
        if response.status_code != 200:
            raise _http_error(response)
        body = _json_object(response)
        if body.get("error"):
            raise MimoProviderError(
                MimoFailureCode.PERMANENT_FAILURE,
                "Xiaomi MiMo returned an error payload",
                retryable=False,
            )
        returned_model = body.get("model")
        if returned_model != self._config.model:
            raise MimoProviderError(
                MimoFailureCode.MODEL_MISMATCH,
                "Xiaomi MiMo returned a different model identity",
                retryable=False,
            )
        choice = _single_choice(body)
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise MimoProviderError(
                MimoFailureCode.TRUNCATED,
                "Xiaomi MiMo output was truncated",
                retryable=True,
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise _malformed("Xiaomi MiMo choice did not contain a message")
        if message.get("refusal") or finish_reason == "content_filter":
            raise MimoProviderError(
                MimoFailureCode.REFUSAL,
                "Xiaomi MiMo refused the request",
                retryable=False,
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise _malformed("Xiaomi MiMo message content was missing")
        if content.lstrip().startswith("```"):
            raise MimoProviderError(
                MimoFailureCode.MALFORMED_JSON,
                "markdown-fenced JSON is not accepted",
                retryable=True,
            )
        try:
            raw_output = json.loads(content)
        except json.JSONDecodeError as exc:
            raise MimoProviderError(
                MimoFailureCode.MALFORMED_JSON,
                "Xiaomi MiMo content was not one complete JSON value",
                retryable=True,
            ) from exc
        try:
            output = request.requested_output_type.model_validate(raw_output)
        except ValidationError as exc:
            raise MimoProviderError(
                MimoFailureCode.SCHEMA,
                (
                    "Xiaomi MiMo content failed the exact requested schema "
                    f"(schema diagnostics: {_schema_diagnostics(exc)})"
                ),
                retryable=True,
            ) from exc
        usage = _usage(body.get("usage"), self._price_cap)
        if usage.total_tokens is None or usage.total_tokens > self._max_call_tokens:
            raise MimoProviderError(
                MimoFailureCode.BUDGET,
                "reported token usage exceeds the configured call ceiling",
                retryable=False,
            )
        if usage.cost_usd is None or Decimal(str(usage.cost_usd)) > self._max_call_cost_usd:
            raise MimoProviderError(
                MimoFailureCode.BUDGET,
                "estimated cost exceeds the configured call ceiling",
                retryable=False,
            )
        self._thread_state.last_metadata = MimoCallMetadata(
            adapter_version=self._config.adapter_version,
            requested_model=self._config.model,
            returned_model=returned_model,
            request_id=_optional_text(response.headers.get("x-request-id")),
            response_id=str(body.get("id") or "unknown"),
            elapsed_seconds=elapsed,
            usage=usage,
            cost_estimated=True,
        )
        self._thread_state.last_failure_usage = None
        return output

    def usage_for(
        self,
        request: LLMRequest,
        output: BaseModel,
        invocation_record: object,
    ) -> ModelUsageMetadata:
        del request, output, invocation_record
        return self.last_call_metadata().usage

    def last_call_metadata(self) -> MimoCallMetadata:
        metadata = getattr(self._thread_state, "last_metadata", None)
        if not isinstance(metadata, MimoCallMetadata):
            raise MimoProviderError(
                MimoFailureCode.MALFORMED_USAGE,
                "no completed Xiaomi MiMo call metadata is available",
                retryable=False,
            )
        return metadata

    def failure_usage_for(self) -> ModelUsageMetadata | None:
        usage = getattr(self._thread_state, "last_failure_usage", None)
        return usage if isinstance(usage, ModelUsageMetadata) else None

    def _record_failure_usage(self, response: httpx.Response) -> None:
        try:
            body = response.json()
            if not isinstance(body, dict) or body.get("usage") is None:
                return
            usage = _usage(body["usage"], self._price_cap)
        except Exception:
            return
        self._thread_state.last_failure_usage = usage


def _request_payload(request: LLMRequest, config: MimoConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [{"role": "user", "content": _direct_mimo_prompt(request)}],
        "response_format": {"type": "json_object"},
        "stream": False,
        "max_completion_tokens": config.max_completion_tokens,
    }
    if request.generation.temperature is not None:
        payload["temperature"] = request.generation.temperature
    return payload


def _direct_mimo_prompt(request: LLMRequest) -> str:
    return (
        f"{request.rendered_prompt}\n\n"
        "<DIRECT_MIMO_PROVENANCE_COMPATIBILITY>\n"
        f"Any *_model_name field must equal exactly: {request.model_alias.value}\n"
        f"Any *_prompt_version field must equal exactly: {request.prompt.version}\n"
        "Preserve capitalization and punctuation exactly.\n"
        "</DIRECT_MIMO_PROVENANCE_COMPATIBILITY>"
    )


def _deadline_for(stage: LLMStage, config: MimoConfig) -> float:
    return getattr(config.deadlines, f"{stage.value}_seconds")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise _malformed("Xiaomi MiMo success response was not valid JSON") from exc
    if not isinstance(body, dict):
        raise _malformed("Xiaomi MiMo success response was not an object")
    return body


def _single_choice(body: dict[str, Any]) -> dict[str, Any]:
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise _malformed("Xiaomi MiMo response must contain exactly one choice")
    return choices[0]


def _usage(raw: Any, cap: ModelPriceCap) -> ModelUsageMetadata:
    if not isinstance(raw, dict):
        raise MimoProviderError(
            MimoFailureCode.MALFORMED_USAGE,
            "Xiaomi MiMo usage metadata was missing or malformed",
            retryable=False,
        )
    prompt = raw.get("prompt_tokens")
    completion = raw.get("completion_tokens")
    total = raw.get("total_tokens")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 0
        for item in (prompt, completion, total)
    ):
        raise MimoProviderError(
            MimoFailureCode.MALFORMED_USAGE,
            "Xiaomi MiMo token usage fields were malformed",
            retryable=False,
        )
    if total != prompt + completion:
        raise MimoProviderError(
            MimoFailureCode.MALFORMED_USAGE,
            "Xiaomi MiMo total token usage was inconsistent",
            retryable=False,
        )
    return ModelUsageMetadata(
        input_tokens=prompt,
        output_tokens=completion,
        total_tokens=total,
        cost_usd=float(cap.upper_bound(prompt, completion)),
    )


def _http_error(response: httpx.Response) -> MimoProviderError:
    status = response.status_code
    request_id = _safe_request_id(response.headers.get("x-request-id"))
    diagnostic = f"HTTP {status}"
    if request_id is not None:
        diagnostic += f", request_id={request_id}"
    if status == 401:
        return MimoProviderError(
            MimoFailureCode.AUTHENTICATION,
            f"Xiaomi MiMo authentication failed ({diagnostic})",
            retryable=False,
            http_status=status,
            request_id=request_id,
        )
    if status == 403:
        return MimoProviderError(
            MimoFailureCode.AUTHENTICATION,
            f"Xiaomi MiMo request was forbidden ({diagnostic})",
            retryable=False,
            http_status=status,
            request_id=request_id,
        )
    if status == 408:
        return MimoProviderError(
            MimoFailureCode.TIMEOUT,
            "Xiaomi MiMo request timed out",
            retryable=True,
        )
    if status == 429:
        return MimoProviderError(
            MimoFailureCode.RATE_LIMIT,
            "Xiaomi MiMo rate limit was reached",
            retryable=True,
        )
    if 500 <= status < 600:
        return MimoProviderError(
            MimoFailureCode.TRANSIENT_OUTAGE,
            "Xiaomi MiMo transient outage",
            retryable=True,
        )
    return MimoProviderError(
        MimoFailureCode.PERMANENT_FAILURE,
        "Xiaomi MiMo request failed permanently",
        retryable=False,
    )


def _malformed(message: str) -> MimoProviderError:
    return MimoProviderError(
        MimoFailureCode.MALFORMED_RESPONSE,
        message,
        retryable=True,
    )


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_request_id(value: Any) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return None
    return value if re.fullmatch(r"[A-Za-z0-9._:-]+", value) else None


def _schema_diagnostics(exc: ValidationError) -> str:
    diagnostics: list[str] = []
    errors = exc.errors(include_url=False, include_input=False)
    for error in errors[:8]:
        error_type = str(error.get("type") or "validation_error")
        if not re.fullmatch(r"[a-z0-9_]{1,64}", error_type):
            error_type = "validation_error"
        location = _redacted_error_location(error.get("loc"), error_type)
        diagnostics.append(f"{location}:{error_type}")
    if len(errors) > len(diagnostics):
        diagnostics.append(f"+{len(errors) - len(diagnostics)}_more")
    summary = ", ".join(diagnostics) or "validation_error"
    return summary[:400]


def _redacted_error_location(raw: Any, error_type: str) -> str:
    if error_type == "extra_forbidden":
        return "<extra>"
    if not isinstance(raw, tuple):
        return "<root>"
    segments: list[str] = []
    for segment in raw:
        if isinstance(segment, int) and not isinstance(segment, bool):
            segments.append(f"[{segment}]")
        elif isinstance(segment, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", segment):
            segments.append(segment)
        else:
            segments.append("<field>")
    return ".".join(segments) if segments else "<root>"
