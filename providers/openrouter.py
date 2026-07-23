"""Direct strict-schema OpenRouter adapter for the approved MVP-2B model route."""

from __future__ import annotations

import json
import time
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from threading import local
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from models import ModelUsageMetadata, StrictModel
from providers.config import OpenRouterConfig
from providers.llm import LLMProviderCapabilities, LLMRequest, LLMStage, ModelAlias
from providers.pricing import DEFAULT_PRICE_CAPS, ModelPriceCap, conservative_token_estimate


class OpenRouterFailureCode(StrEnum):
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


class OpenRouterProviderError(RuntimeError):
    def __init__(
        self,
        code: OpenRouterFailureCode,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class OpenRouterCallMetadata(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_version: str
    requested_model: str
    returned_model: str
    upstream_provider: str | None = None
    request_id: str | None = None
    response_id: str
    elapsed_seconds: float = Field(ge=0)
    usage: ModelUsageMetadata
    cost_estimated: bool


class OpenRouterAdapter:
    """One physical call; orchestration owns retries and fallback selection."""

    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(
        self,
        config: OpenRouterConfig,
        *,
        client: httpx.Client | None = None,
        price_caps: dict[str, ModelPriceCap] | None = None,
        max_call_cost_usd: Decimal = Decimal("1.00"),
        max_call_tokens: int = 1_000_000,
    ) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.deadlines.synthesizer_seconds),
            follow_redirects=False,
            headers={"Authorization": f"Bearer {config.api_key.get_secret_value()}"},
        )
        self._price_caps = price_caps or DEFAULT_PRICE_CAPS
        self._max_call_cost_usd = max_call_cost_usd
        self._max_call_tokens = max_call_tokens
        self._thread_state = local()

    def generate(self, request: LLMRequest) -> BaseModel:
        model = _model_for_alias(request.model_alias)
        cap = self._price_caps.get(model)
        if cap is None:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.UNKNOWN_PRICING,
                "no approved price cap exists for the requested model",
                retryable=False,
            )
        input_estimate = conservative_token_estimate(request.rendered_prompt)
        reserved_tokens = input_estimate + self._config.max_output_tokens
        reserved_cost = cap.upper_bound(input_estimate, self._config.max_output_tokens)
        if reserved_tokens > self._max_call_tokens or reserved_cost > self._max_call_cost_usd:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.BUDGET,
                "the conservative reservation exceeds the configured call ceiling",
                retryable=False,
            )
        payload = _request_payload(request, model, self._config.max_output_tokens)
        started = time.monotonic()
        try:
            response = self._client.post(
                "/chat/completions",
                json=payload,
                timeout=_deadline_for(request.stage, self._config),
                headers={"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"},
            )
        except httpx.TimeoutException as exc:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.TIMEOUT, "OpenRouter request timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.TRANSIENT_OUTAGE,
                "OpenRouter connection failed",
                retryable=True,
            ) from exc
        elapsed = time.monotonic() - started
        if response.status_code != 200:
            raise _http_error(response.status_code)
        body = _json_object(response)
        if body.get("error"):
            raise OpenRouterProviderError(
                OpenRouterFailureCode.PERMANENT_FAILURE,
                "OpenRouter returned an error payload",
                retryable=bool(body.get("error", {}).get("retryable", False))
                if isinstance(body.get("error"), dict)
                else False,
            )
        returned_model = body.get("model")
        if returned_model != model:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.MODEL_MISMATCH,
                "OpenRouter returned a different model identity",
                retryable=False,
            )
        choice = _single_choice(body)
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise OpenRouterProviderError(
                OpenRouterFailureCode.TRUNCATED,
                "OpenRouter output was truncated",
                retryable=True,
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise _malformed("OpenRouter choice did not contain a message")
        if message.get("refusal") or finish_reason == "content_filter":
            raise OpenRouterProviderError(
                OpenRouterFailureCode.REFUSAL,
                "OpenRouter or the upstream model refused the request",
                retryable=False,
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise _malformed("OpenRouter message content was missing")
        if content.lstrip().startswith("```"):
            raise OpenRouterProviderError(
                OpenRouterFailureCode.MALFORMED_JSON,
                "markdown-fenced structured output is not accepted",
                retryable=True,
            )
        try:
            raw_output = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.MALFORMED_JSON,
                "OpenRouter content was not one complete JSON value",
                retryable=True,
            ) from exc
        try:
            output = request.requested_output_type.model_validate(raw_output)
        except ValidationError as exc:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.SCHEMA,
                "OpenRouter content failed the exact requested schema",
                retryable=True,
            ) from exc
        usage, estimated = _usage(body.get("usage"), cap)
        if usage.total_tokens is None or usage.total_tokens > self._max_call_tokens:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.BUDGET,
                "reported token usage exceeds the configured call ceiling",
                retryable=False,
            )
        if usage.cost_usd is None or Decimal(str(usage.cost_usd)) > self._max_call_cost_usd:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.BUDGET,
                "reported or capped cost exceeds the configured call ceiling",
                retryable=False,
            )
        metadata = OpenRouterCallMetadata(
            adapter_version=self._config.adapter_version,
            requested_model=model,
            returned_model=returned_model,
            upstream_provider=_optional_text(body.get("provider")),
            request_id=_optional_text(response.headers.get("x-request-id")),
            response_id=str(body.get("id") or "unknown"),
            elapsed_seconds=elapsed,
            usage=usage,
            cost_estimated=estimated,
        )
        self._thread_state.last_metadata = metadata
        return output

    def usage_for(
        self, request: LLMRequest, output: BaseModel, invocation_record: object
    ) -> ModelUsageMetadata:
        del request, output, invocation_record
        metadata = getattr(self._thread_state, "last_metadata", None)
        if not isinstance(metadata, OpenRouterCallMetadata):
            raise OpenRouterProviderError(
                OpenRouterFailureCode.MALFORMED_USAGE,
                "no usage metadata is available for the current call",
                retryable=False,
            )
        return metadata.usage

    def last_call_metadata(self) -> OpenRouterCallMetadata:
        metadata = getattr(self._thread_state, "last_metadata", None)
        if not isinstance(metadata, OpenRouterCallMetadata):
            raise OpenRouterProviderError(
                OpenRouterFailureCode.MALFORMED_USAGE,
                "no completed OpenRouter call metadata is available",
                retryable=False,
            )
        return metadata


def _request_payload(request: LLMRequest, model: str, max_tokens: int) -> dict[str, Any]:
    schema = request.requested_output_type.model_json_schema()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": request.rendered_prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": request.requested_output_type.__name__,
                "strict": True,
                "schema": schema,
            },
        },
        "provider": {"require_parameters": True, "data_collection": "deny"},
        "stream": False,
        "max_tokens": max_tokens,
    }
    if request.generation.temperature is not None:
        payload["temperature"] = request.generation.temperature
    return payload


def _model_for_alias(alias: ModelAlias) -> str:
    if alias is ModelAlias.MIMO_V25_PRO:
        return "xiaomi/mimo-v2.5-pro"
    if alias is ModelAlias.MINIMAX_M3:
        return "minimax/minimax-m3"
    raise OpenRouterProviderError(
        OpenRouterFailureCode.CAPABILITY,
        "model alias is not part of the approved MVP-2B route",
        retryable=False,
    )


def _deadline_for(stage: LLMStage, config: OpenRouterConfig) -> float:
    return getattr(config.deadlines, f"{stage.value}_seconds")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise _malformed("OpenRouter success response was not valid JSON") from exc
    if not isinstance(body, dict):
        raise _malformed("OpenRouter success response was not an object")
    return body


def _single_choice(body: dict[str, Any]) -> dict[str, Any]:
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise _malformed("OpenRouter success response must contain exactly one choice")
    return choices[0]


def _usage(raw: Any, cap: ModelPriceCap) -> tuple[ModelUsageMetadata, bool]:
    if not isinstance(raw, dict):
        raise OpenRouterProviderError(
            OpenRouterFailureCode.MALFORMED_USAGE,
            "OpenRouter usage metadata was missing or malformed",
            retryable=False,
        )
    prompt = raw.get("prompt_tokens")
    completion = raw.get("completion_tokens")
    total = raw.get("total_tokens")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 0
        for item in (prompt, completion, total)
    ):
        raise OpenRouterProviderError(
            OpenRouterFailureCode.MALFORMED_USAGE,
            "OpenRouter token usage fields were malformed",
            retryable=False,
        )
    if total != prompt + completion:
        raise OpenRouterProviderError(
            OpenRouterFailureCode.MALFORMED_USAGE,
            "OpenRouter total token usage was inconsistent",
            retryable=False,
        )
    cost = raw.get("cost")
    estimated = cost is None
    if cost is None:
        cost_decimal = cap.upper_bound(prompt, completion)
    else:
        try:
            cost_decimal = Decimal(str(cost))
        except (InvalidOperation, ValueError) as exc:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.MALFORMED_USAGE,
                "OpenRouter cost metadata was malformed",
                retryable=False,
            ) from exc
        if not cost_decimal.is_finite() or cost_decimal < 0:
            raise OpenRouterProviderError(
                OpenRouterFailureCode.MALFORMED_USAGE,
                "OpenRouter cost metadata was malformed",
                retryable=False,
            )
    return (
        ModelUsageMetadata(
            input_tokens=prompt,
            output_tokens=completion,
            total_tokens=total,
            cost_usd=float(cost_decimal),
        ),
        estimated,
    )


def _http_error(status: int) -> OpenRouterProviderError:
    if status in {401, 403}:
        return OpenRouterProviderError(
            OpenRouterFailureCode.AUTHENTICATION,
            "OpenRouter authentication failed",
            retryable=False,
        )
    if status == 408:
        return OpenRouterProviderError(
            OpenRouterFailureCode.TIMEOUT, "OpenRouter request timed out", retryable=True
        )
    if status == 429:
        return OpenRouterProviderError(
            OpenRouterFailureCode.RATE_LIMIT, "OpenRouter rate limited the request", retryable=True
        )
    if 500 <= status < 600:
        return OpenRouterProviderError(
            OpenRouterFailureCode.TRANSIENT_OUTAGE,
            "OpenRouter is temporarily unavailable",
            retryable=True,
        )
    return OpenRouterProviderError(
        OpenRouterFailureCode.PERMANENT_FAILURE,
        "OpenRouter request failed permanently",
        retryable=False,
    )


def _malformed(message: str) -> OpenRouterProviderError:
    return OpenRouterProviderError(
        OpenRouterFailureCode.MALFORMED_RESPONSE, message, retryable=True
    )


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
