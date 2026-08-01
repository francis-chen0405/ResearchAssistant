"""Direct Xiaomi MiMo JSON-mode adapter for the authorized MVP-3B route."""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal
from enum import StrEnum
from threading import local
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.synthesizer import _template_for_record
from models import (
    ModelUsageMetadata,
    Placement,
    PlannerOutput,
    ProvisionalCandidate,
    ScoreDecision,
    StrictModel,
    SynthesisOutput,
    _derive_ledger_score,
    _expected_placement,
    _is_ledger_eligible,
)
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
            normalized_output = _normalize_direct_mimo_output(request, raw_output)
            output = request.requested_output_type.model_validate(normalized_output)
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
    stage_compatibility = ""
    if request.stage is LLMStage.EXTRACTOR:
        stage_compatibility = (
            "\n<DIRECT_MIMO_EXACT_QUOTE_COMPATIBILITY>\n"
            "The extracted_quote_block string must be formatted exactly: "
            '[preceding context] "exact quoted segment" [following context]\n'
            "Use literal square brackets around both context portions and literal double "
            "quotes around every exact source segment. Use only exact snapshot text or an "
            "allowed boundary marker. Do not return an unquoted sentence or plain text.\n"
            "The combined exact quoted segments must contain at least 100 whitespace-separated "
            "words. Preserve material qualifications and do not use unrelated padding.\n"
            "</DIRECT_MIMO_EXACT_QUOTE_COMPATIBILITY>\n"
        )
    elif request.stage is LLMStage.ANALYST and request.requested_output_type is ScoreDecision:
        stage_compatibility = (
            "\n<DIRECT_MIMO_ANALYST_STANCE_COMPATIBILITY>\n"
            "The candidate stance is binding. Supporting evidence must support the defined "
            "claim. Opposing evidence must contradict, limit, or materially qualify the claim. "
            "If an opposing candidate instead supports the claim, assign claim_fit at most 2 "
            "and approved=false; apply the converse rule to a supporting candidate that only "
            "opposes the claim.\n"
            "ScoreDecision.approved is the Analyst routing decision for whether the candidate "
            "may proceed to drafting. It is not final factual approval; a separate Reviewer "
            "controls that later decision. It must be true exactly when evidence_quality >= 2, "
            "claim_fit >= 3, and their sum >= 5. The application derives approved, ledger_score, "
            "and placement from the semantic scores.\n"
            "</DIRECT_MIMO_ANALYST_STANCE_COMPATIBILITY>\n"
        )
    return (
        f"{request.rendered_prompt}\n\n"
        f"{stage_compatibility}"
        "<DIRECT_MIMO_PROVENANCE_COMPATIBILITY>\n"
        f"Any *_model_name field must equal exactly: {request.model_alias.value}\n"
        f"Any *_prompt_version field must equal exactly: {request.prompt.version}\n"
        "Preserve capitalization and punctuation exactly.\n"
        "</DIRECT_MIMO_PROVENANCE_COMPATIBILITY>"
    )


_MIMO_QUOTE_BLOCK_RE = re.compile(
    r'^\s*\[(?P<before>[^\[\]]+)\]\s+"(?P<quote>.+?)"\s+\[(?P<after>[^\[\]]+)\]\s*$',
    re.DOTALL,
)
_MIMO_RELAXED_BLOCK_RE = re.compile(
    r"^\s*\[[^\[\]]+\]\s*(?P<quote>.+?)\s*\[[^\[\]]+\]\s*$",
    re.DOTALL,
)
_MIMO_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$", re.DOTALL)


def _normalize_direct_mimo_output(request: LLMRequest, raw_output: Any) -> Any:
    """Stamp application-owned identities and repair only exact Extractor source text."""
    if not isinstance(raw_output, dict):
        return raw_output
    if request.stage is LLMStage.PLANNER and request.requested_output_type is PlannerOutput:
        return _normalize_direct_mimo_planner_output(request, raw_output)
    if request.stage is LLMStage.ANALYST and request.requested_output_type is ScoreDecision:
        return _normalize_direct_mimo_score_decision(request, raw_output)
    if request.stage is LLMStage.SYNTHESIZER and request.requested_output_type is SynthesisOutput:
        return _normalize_direct_mimo_synthesis_output(request, raw_output)
    if (
        request.stage is not LLMStage.EXTRACTOR
        or request.requested_output_type is not ProvisionalCandidate
    ):
        return raw_output

    extraction_input = request.input_artifact
    source = getattr(extraction_input, "source", None)
    retrieval = getattr(extraction_input, "retrieval", None)
    stance = getattr(extraction_input, "stance", None)
    source_text = getattr(source, "text", None)
    normalized = dict(raw_output)

    normalized["run_id"] = str(request.run_id)
    if stance is not None:
        normalized["stance"] = getattr(stance, "value", stance)
    if source is not None:
        normalized["snapshot_id"] = str(source.snapshot_id)
        normalized["snapshot_sha256"] = source.snapshot_sha256
    if retrieval is not None:
        normalized.update(
            {
                "source_url": retrieval.resolved_url,
                "retrieval_attempt_id": str(retrieval.retrieval_attempt_id),
                "query_id": str(retrieval.query_id),
                "query_round": retrieval.query_round,
                "search_rank": retrieval.search_rank,
            }
        )
    normalized["extraction_prompt_version"] = request.prompt.version
    normalized["extraction_model_name"] = request.model_alias.value

    quote_block = normalized.get("extracted_quote_block")
    if isinstance(source_text, str) and isinstance(quote_block, str):
        normalized["extracted_quote_block"] = _normalize_exact_quote_block(
            quote_block,
            source_text,
        )
    return normalized


def _normalize_direct_mimo_score_decision(
    request: LLMRequest,
    raw_output: dict[str, Any],
) -> dict[str, Any]:
    """Stamp Analyst provenance and reconcile only application-owned routing fields."""
    normalized = dict(raw_output)
    candidate = getattr(request.input_artifact, "candidate", None)
    normalized["run_id"] = str(request.run_id)
    if candidate is not None:
        normalized["quote_block_id"] = str(candidate.quote_block_id)
    normalized["analyst_prompt_version"] = request.prompt.version
    normalized["analyst_model_name"] = request.model_alias.value

    evidence_quality = normalized.get("evidence_quality")
    claim_fit = normalized.get("claim_fit")
    if not (
        isinstance(evidence_quality, int)
        and not isinstance(evidence_quality, bool)
        and isinstance(claim_fit, int)
        and not isinstance(claim_fit, bool)
    ):
        return normalized

    eligible = _is_ledger_eligible(evidence_quality, claim_fit)
    normalized["approved"] = eligible
    if not eligible:
        normalized["ledger_score"] = None
        normalized["placement"] = None
    else:
        normalized["ledger_score"] = _derive_ledger_score(evidence_quality, claim_fit)
        placement: Placement = _expected_placement(evidence_quality, claim_fit)
        normalized["placement"] = placement.value
    return normalized


def _normalize_direct_mimo_synthesis_output(
    request: LLMRequest,
    raw_output: dict[str, Any],
) -> dict[str, Any]:
    """Stamp provenance and approved connective IDs without changing factual content."""
    normalized = dict(raw_output)
    normalized["run_id"] = str(request.run_id)
    normalized["synthesizer_prompt_version"] = request.prompt.version
    normalized["synthesizer_model_name"] = request.model_alias.value
    records = getattr(request.input_artifact, "ledger_records", ())
    records_by_id = {str(record.ledger_claim_id): record for record in records}
    sections = normalized.get("sections")
    if not isinstance(sections, list):
        return normalized

    normalized_sections: list[Any] = []
    for section in sections:
        if not isinstance(section, dict):
            normalized_sections.append(section)
            continue
        normalized_section = dict(section)
        items = normalized_section.get("items")
        if isinstance(items, list):
            normalized_items: list[Any] = []
            for item in items:
                if isinstance(item, dict):
                    normalized_item = dict(item)
                    record = records_by_id.get(str(item.get("ledger_claim_id")))
                    if record is not None:
                        normalized_item["connective_template_id"] = _template_for_record(record)
                    normalized_items.append(normalized_item)
                else:
                    normalized_items.append(item)
            normalized_section["items"] = normalized_items
        normalized_sections.append(normalized_section)
    normalized["sections"] = normalized_sections
    return normalized


def _normalize_direct_mimo_planner_output(
    request: LLMRequest,
    raw_output: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(raw_output)
    normalized["run_id"] = str(request.run_id)
    normalized["planner_prompt_version"] = request.prompt.version
    normalized["planner_model_name"] = request.model_alias.value

    claim_definition = normalized.get("claim_definition")
    if isinstance(claim_definition, dict):
        normalized["claim_definition"] = {
            **claim_definition,
            "run_id": str(request.run_id),
        }
    ambiguities = normalized.get("ambiguities")
    if isinstance(ambiguities, list):
        normalized["ambiguities"] = [
            {
                **item,
                "run_id": str(request.run_id),
                "ambiguity_id": str(
                    uuid5(
                        NAMESPACE_URL,
                        f"direct-mimo-planner::{request.run_id}::ambiguity::{index}",
                    )
                ),
            }
            if isinstance(item, dict)
            else item
            for index, item in enumerate(ambiguities, start=1)
        ]
    search_queries = normalized.get("search_queries")
    if isinstance(search_queries, list):
        normalized["search_queries"] = [
            {
                **item,
                "run_id": str(request.run_id),
                "query_id": str(
                    uuid5(
                        NAMESPACE_URL,
                        f"direct-mimo-planner::{request.run_id}::query::{index}",
                    )
                ),
            }
            if isinstance(item, dict)
            else item
            for index, item in enumerate(search_queries, start=1)
        ]
    return normalized


def _normalize_exact_quote_block(raw_block: str, source_text: str) -> str:
    """Rebuild brackets only when the proposed quote is already exact source text."""
    candidates = _quote_candidates(raw_block)
    if not candidates:
        return raw_block
    exact_segments: list[str] = []
    locations: list[tuple[int, int]] = []
    search_start = 0
    for candidate in candidates:
        location = _find_exact_or_whitespace_equivalent(source_text, candidate, search_start)
        if location is None:
            return raw_block
        start, end = location
        exact_segments.append(source_text[start:end])
        locations.append(location)
        search_start = end
    start = locations[0][0]
    end = locations[-1][1]

    spans = _mimo_sentence_spans(source_text)
    before = next(
        (text for _, span_end, text in reversed(spans) if span_end <= start),
        None,
    )
    after = next(
        (text for span_start, _, text in spans if span_start >= end),
        None,
    )
    if before is None:
        if source_text[:start].strip():
            return raw_block
        before = "Start of Text"
    if after is None:
        if source_text[end:].strip():
            return raw_block
        original = _MIMO_QUOTE_BLOCK_RE.match(raw_block)
        original_after = original.group("after").strip() if original is not None else None
        if original_after not in {"End of Text", "Truncated End of Snapshot"}:
            return raw_block
        after = original_after
    if any(char in before or char in after for char in "[]"):
        return raw_block
    quoted = " ... ".join(exact_segments)
    return f'[{before}] "{quoted}" [{after}]'


def _quote_candidates(raw_block: str) -> list[str]:
    exact = _MIMO_QUOTE_BLOCK_RE.match(raw_block)
    if exact is not None:
        candidate = exact.group("quote").strip()
    else:
        relaxed = _MIMO_RELAXED_BLOCK_RE.match(raw_block)
        if relaxed is None:
            candidate = raw_block.strip().strip('"').strip()
        else:
            candidate = relaxed.group("quote").strip().strip('"').strip()
    if not candidate:
        return []
    pieces = [piece.strip().strip('"').strip() for piece in re.split(r"\s+\.\.\.\s+", candidate)]
    if len(pieces) > 1 and all(pieces):
        return pieces
    return [candidate]


def _find_exact_or_whitespace_equivalent(
    source_text: str,
    candidate: str,
    search_start: int,
) -> tuple[int, int] | None:
    start = source_text.find(candidate, search_start)
    if start >= 0:
        return start, start + len(candidate)
    words = candidate.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(pattern, source_text[search_start:])
    if match is None:
        return None
    return search_start + match.start(), search_start + match.end()


def _mimo_sentence_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in _MIMO_SENTENCE_RE.finditer(text):
        raw = match.group(0)
        if not raw.strip():
            continue
        start = match.start() + len(raw) - len(raw.lstrip())
        end = match.start() + len(raw.rstrip())
        if start < end:
            spans.append((start, end, text[start:end]))
    return spans


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
