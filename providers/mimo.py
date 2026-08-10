"""Direct Xiaomi MiMo JSON-mode adapter for the authorized MVP-3B route."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from threading import local
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.analyst import AnalystLLMInput, StatementDraftLLMInput
from agents.supportingresearcher import ExtractionLLMInput
from agents.synthesizer import SynthesizerLLMInput, _item_from_ledger
from models import (
    AmbiguityRecord,
    ClaimDefinition,
    ModelUsageMetadata,
    PlannerOutput,
    ProvisionalCandidate,
    Score,
    ScoreDecision,
    SearchQuery,
    SectionType,
    Stance,
    StatementDraft,
    StrictModel,
    SynthesisOutput,
    SynthesisSection,
    _derive_ledger_score,
    _expected_placement,
    _is_ledger_eligible,
)
from money import parse_exact_usd
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


class MimoClaimDefinitionResponse(StrictModel):
    claim_text: str = Field(min_length=1)
    population: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    time_period: str = Field(min_length=1)
    comparison_baseline: str = Field(min_length=1)
    intervention_or_exposure: str = Field(min_length=1)
    causal_or_comparative_meaning: str = Field(min_length=1)


class MimoAmbiguityResponse(StrictModel):
    description: str = Field(min_length=1)
    impact: str = Field(min_length=1)


class MimoSearchQueryResponse(StrictModel):
    stance: Stance
    query_round: int = Field(ge=1, le=3)
    strategy: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    exclusion_parameters: str = Field(min_length=1)


class MimoPlannerResponse(StrictModel):
    claim_definition: MimoClaimDefinitionResponse
    ambiguities: tuple[MimoAmbiguityResponse, ...]
    search_queries: tuple[MimoSearchQueryResponse, ...] = Field(min_length=6, max_length=6)


class MimoExtractionResponse(StrictModel):
    extracted_quote_block: str = Field(min_length=1)


class MimoScoreResponse(StrictModel):
    evidence_quality: Score
    claim_fit: Score
    rationale: str = Field(min_length=1)


class MimoStatementDraftResponse(StrictModel):
    draft_statement: str = Field(min_length=1)


class MimoSynthesisSectionResponse(StrictModel):
    section_type: SectionType
    ledger_claim_ids: tuple[UUID, ...] = Field(min_length=1)


class MimoSynthesisResponse(StrictModel):
    sections: tuple[MimoSynthesisSectionResponse, ...] = Field(min_length=1)


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
        self._max_call_cost_usd = parse_exact_usd(max_call_cost_usd)
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
            semantic_type = _semantic_response_type(request)
            semantic_output = semantic_type.model_validate(raw_output)
            output = _assemble_direct_mimo_output(
                request,
                semantic_output,
                created_at=datetime.now(UTC),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            diagnostics = (
                _schema_diagnostics(exc)
                if isinstance(exc, ValidationError)
                else "semantic_assembly:validation_error"
            )
            raise MimoProviderError(
                MimoFailureCode.SCHEMA,
                (
                    "Xiaomi MiMo content failed the semantic response contract "
                    f"(schema diagnostics: {diagnostics})"
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
        if usage.cost_usd is None or usage.cost_usd > self._max_call_cost_usd:
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
            "Use at least 50 exact quoted words only when the quotation contains at least "
            "one digit and at least one recognized statistical marker: %, percent, rate, "
            "ratio, average, median, index, p-value, million, billion, growth, or decline. "
            "Marker matching uses whole word/token boundaries; incidental substrings do not "
            "count. Otherwise, use at least 75 exact quoted words. A digit without a marker "
            "and a marker without a digit both require 75 words. Preserve material "
            "qualifications and do not use unrelated padding. Return exact source text; never "
            "paraphrase, heal, expand, or invent context. Never repair a short quote. Python "
            "validation is authoritative.\n"
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
    response_type = _semantic_response_type(request)
    schema_json = json.dumps(
        response_type.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        f"{request.prompt.text.rstrip()}\n\n"
        f"{stage_compatibility}"
        "<DIRECT_MIMO_SEMANTIC_OUTPUT_CONTRACT>\n"
        f"Requested Pydantic artifact: {response_type.__name__}\n"
        f"Return only one JSON object matching {response_type.__name__}.\n"
        "Return semantic judgments and text only. Never create IDs, timestamps, model names, "
        "prompt versions, provenance, scores derived by policy, or connective templates. "
        "When the schema accepts an existing ledger_claim_id, copy it exactly from the input; "
        "do not invent one. Extra fields are forbidden.\n"
        f"{schema_json}\n"
        "</DIRECT_MIMO_SEMANTIC_OUTPUT_CONTRACT>\n\n"
        "<APPLICATION_CONTROLLED_STAGE_INPUT>\n"
        f"{request.input_artifact.model_dump_json(indent=2)}\n"
        "</APPLICATION_CONTROLLED_STAGE_INPUT>"
    )


def _semantic_response_type(request: LLMRequest) -> type[BaseModel]:
    if request.stage is LLMStage.PLANNER and request.requested_output_type is PlannerOutput:
        return MimoPlannerResponse
    if (
        request.stage is LLMStage.EXTRACTOR
        and request.requested_output_type is ProvisionalCandidate
    ):
        return MimoExtractionResponse
    if request.stage is LLMStage.ANALYST and request.requested_output_type is ScoreDecision:
        return MimoScoreResponse
    if request.stage is LLMStage.ANALYST and request.requested_output_type is StatementDraft:
        return MimoStatementDraftResponse
    if request.stage is LLMStage.SYNTHESIZER and request.requested_output_type is SynthesisOutput:
        return MimoSynthesisResponse
    return request.requested_output_type


def _assemble_direct_mimo_output(
    request: LLMRequest,
    response: BaseModel,
    *,
    created_at: datetime,
) -> BaseModel:
    if isinstance(response, MimoPlannerResponse):
        return _assemble_planner(request, response, created_at)
    if isinstance(response, MimoExtractionResponse):
        return _assemble_extraction(request, response, created_at)
    if isinstance(response, MimoScoreResponse):
        return _assemble_score(request, response, created_at)
    if isinstance(response, MimoStatementDraftResponse):
        return _assemble_statement_draft(request, response, created_at)
    if isinstance(response, MimoSynthesisResponse):
        return _assemble_synthesis(request, response, created_at)
    return request.requested_output_type.model_validate(response)


def _assemble_planner(
    request: LLMRequest,
    response: MimoPlannerResponse,
    created_at: datetime,
) -> PlannerOutput:
    claim = ClaimDefinition(
        run_id=request.run_id,
        created_at=created_at,
        **response.claim_definition.model_dump(),
    )
    ambiguities = [
        AmbiguityRecord(
            run_id=request.run_id,
            ambiguity_id=uuid5(
                NAMESPACE_URL,
                f"direct-mimo-planner::{request.run_id}::ambiguity::{index}",
            ),
            created_at=created_at,
            **item.model_dump(),
        )
        for index, item in enumerate(response.ambiguities, start=1)
    ]
    queries = [
        SearchQuery(
            run_id=request.run_id,
            query_id=uuid5(
                NAMESPACE_URL,
                f"direct-mimo-planner::{request.run_id}::query::{index}",
            ),
            created_at=created_at,
            **item.model_dump(),
        )
        for index, item in enumerate(response.search_queries, start=1)
    ]
    return PlannerOutput(
        run_id=request.run_id,
        claim_definition=claim,
        ambiguities=ambiguities,
        search_queries=queries,
        planner_prompt_version=request.prompt.version,
        planner_model_name=request.model_alias.value,
        planned_at=created_at,
    )


def _assemble_extraction(
    request: LLMRequest,
    response: MimoExtractionResponse,
    created_at: datetime,
) -> ProvisionalCandidate:
    artifact = request.input_artifact
    if not isinstance(artifact, ExtractionLLMInput) or artifact.retrieval is None:
        raise TypeError("direct MiMo extraction requires a retrieval-backed ExtractionLLMInput")
    return ProvisionalCandidate(
        run_id=request.run_id,
        stance=artifact.stance,
        source_url=artifact.retrieval.resolved_url,
        retrieval_attempt_id=artifact.retrieval.retrieval_attempt_id,
        query_id=artifact.retrieval.query_id,
        query_round=artifact.retrieval.query_round,
        search_rank=artifact.retrieval.search_rank,
        snapshot_id=artifact.source.snapshot_id,
        snapshot_sha256=artifact.source.snapshot_sha256,
        extracted_quote_block=response.extracted_quote_block,
        extraction_prompt_version=request.prompt.version,
        extraction_model_name=request.model_alias.value,
        extracted_at=created_at,
    )


def _assemble_score(
    request: LLMRequest,
    response: MimoScoreResponse,
    created_at: datetime,
) -> ScoreDecision:
    artifact = request.input_artifact
    if not isinstance(artifact, AnalystLLMInput):
        raise TypeError("direct MiMo scoring requires AnalystLLMInput")
    eligible = _is_ledger_eligible(response.evidence_quality, response.claim_fit)
    return ScoreDecision(
        run_id=request.run_id,
        quote_block_id=artifact.candidate.quote_block_id,
        evidence_quality=response.evidence_quality,
        claim_fit=response.claim_fit,
        ledger_score=(
            _derive_ledger_score(response.evidence_quality, response.claim_fit)
            if eligible
            else None
        ),
        placement=(
            _expected_placement(response.evidence_quality, response.claim_fit) if eligible else None
        ),
        approved=eligible,
        rationale=response.rationale,
        analyst_prompt_version=request.prompt.version,
        analyst_model_name=request.model_alias.value,
        scored_at=created_at,
    )


def _assemble_statement_draft(
    request: LLMRequest,
    response: MimoStatementDraftResponse,
    created_at: datetime,
) -> StatementDraft:
    artifact = request.input_artifact
    if not isinstance(artifact, StatementDraftLLMInput):
        raise TypeError("direct MiMo drafting requires StatementDraftLLMInput")
    candidate = artifact.analyst_input.candidate
    return StatementDraft(
        run_id=request.run_id,
        statement_draft_id=uuid5(
            NAMESPACE_URL,
            f"phase9-draft::{candidate.quote_block_id}::{artifact.revision_number}",
        ),
        quote_block_id=candidate.quote_block_id,
        stance=candidate.stance,
        draft_statement=response.draft_statement,
        claim_fit=artifact.score_decision.claim_fit,
        analyst_prompt_version=request.prompt.version,
        analyst_model_name=request.model_alias.value,
        drafted_at=created_at,
    )


def _assemble_synthesis(
    request: LLMRequest,
    response: MimoSynthesisResponse,
    created_at: datetime,
) -> SynthesisOutput:
    artifact = request.input_artifact
    if not isinstance(artifact, SynthesizerLLMInput):
        raise TypeError("direct MiMo synthesis requires SynthesizerLLMInput")
    records = {record.ledger_claim_id: record for record in artifact.ledger_records}
    selected = [claim_id for section in response.sections for claim_id in section.ledger_claim_ids]
    if len(selected) != len(set(selected)) or set(selected) != set(records):
        raise ValueError("synthesis must reference every input Ledger ID exactly once")
    sections = tuple(
        SynthesisSection(
            section_type=section.section_type,
            items=tuple(
                _item_from_ledger(records[claim_id]) for claim_id in section.ledger_claim_ids
            ),
        )
        for section in response.sections
    )
    return SynthesisOutput(
        run_id=request.run_id,
        synthesizer_prompt_version=request.prompt.version,
        synthesizer_model_name=request.model_alias.value,
        created_at=created_at,
        sections=sections,
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
        cost_usd=cap.upper_bound(prompt, completion),
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
