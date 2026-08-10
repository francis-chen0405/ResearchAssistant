from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from agents.reviewer import ReviewerDecision, ReviewerInput
from agents.supportingresearcher import ExtractionLLMInput, UntrustedSourceText
from models import (
    ClaimDefinition,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    RetrievalStatus,
    ScoreDecision,
    Stance,
)
from providers.config import MimoConfig, ProviderConfigurationError
from providers.llm import DIRECT_MIMO_ROUTING, LLMStage, ModelAlias, build_stage_request
from providers.mimo import (
    MimoExtractionResponse,
    MimoFailureCode,
    MimoPlannerResponse,
    MimoProviderError,
    MimoScoreResponse,
    XiaomiMimoAdapter,
    _assemble_direct_mimo_output,
    _direct_mimo_prompt,
)
from providers.pricing import DIRECT_MIMO_PRICE_CAP


def _request() -> object:
    return build_stage_request(
        stage=LLMStage.REVIEWER,
        input_artifact=ReviewerInput(
            extracted_quote_block='[Start of Text] "Public evidence." [End of Text]',
            preceding_context="Start of Text",
            following_context="End of Text",
            draft_statement="Public evidence.",
            claim_fit=3,
        ),
        requested_output_type=ReviewerDecision,
        input_artifact_ids=(uuid4(),),
        routing=DIRECT_MIMO_ROUTING,
        model_alias=ModelAlias.MIMO_V25_PRO,
        run_id=uuid4(),
    )


def _extractor_request() -> object:
    run_id = uuid4()
    retrieval = RetrievalRecord(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        query_id=uuid4(),
        query_round=2,
        query_text="public evidence",
        search_rank=3,
        source_url="https://search.example/result",
        resolved_url="https://source.example/evidence",
        status=RetrievalStatus.RETRIEVED,
        retrieved_at=datetime(2026, 7, 31, tzinfo=UTC),
    )
    source = UntrustedSourceText(
        snapshot_id=uuid4(),
        snapshot_sha256="a" * 64,
        text="Opening context. Exact public evidence sentence. Closing context.",
    )
    return build_stage_request(
        stage=LLMStage.EXTRACTOR,
        input_artifact=ExtractionLLMInput(
            run_id=run_id,
            stance=Stance.OPPOSING,
            claim_definition=ClaimDefinition(
                run_id=run_id,
                claim_text="Public claim.",
                population="Adults",
                jurisdiction="Global",
                time_period="Current evidence",
                comparison_baseline="No intervention",
                intervention_or_exposure="Public intervention",
                causal_or_comparative_meaning="Comparative effect",
                created_at=datetime(2026, 7, 31, tzinfo=UTC),
            ),
            source=source,
            retrieval=retrieval,
        ),
        requested_output_type=ProvisionalCandidate,
        input_artifact_ids=(source.snapshot_id,),
        routing=DIRECT_MIMO_ROUTING,
        model_alias=ModelAlias.MIMO_V25_PRO,
        run_id=run_id,
    )


def _response(
    request: httpx.Request,
    *,
    content: str = (
        '{"reviewed_statement":"Public evidence.","approved":true,'
        '"failure_code":null,"rationale":"Fully entailed."}'
    ),
    model: str = "mimo-v2.5-pro",
    usage: object | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "mimo-response-1",
            "model": model,
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": usage
            or {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
        request=request,
    )


def test_direct_mimo_config_is_strict_secret_safe_and_environment_only() -> None:
    config = MimoConfig.from_environment(
        {
            "MIMO_API_KEY": "mimo-secret-value",
            "MIMO_BASE_URL": "https://api.xiaomimimo.com/v1",
            "MIMO_MODEL": "mimo-v2.5-pro",
        }
    )
    assert config.model == "mimo-v2.5-pro"
    assert "mimo-secret-value" not in repr(config)
    assert "mimo-secret-value" not in str(config)

    with pytest.raises(ProviderConfigurationError):
        MimoConfig.from_environment({})
    with pytest.raises(ValueError):
        MimoConfig(
            api_key=SecretStr("secret"),
            base_url="http://api.xiaomimimo.com/v1",
        )
    with pytest.raises(ValueError):
        MimoConfig(api_key=SecretStr("secret"), model="another-model")


def test_direct_mimo_route_has_no_cross_provider_fallback() -> None:
    for stage in LLMStage:
        route = DIRECT_MIMO_ROUTING.for_stage(stage)
        assert route.primary is ModelAlias.MIMO_V25_PRO
        assert route.fallbacks == ()


def test_direct_mimo_extractor_prompt_requires_exact_quote_envelope() -> None:
    request = _request().model_copy(update={"stage": LLMStage.EXTRACTOR})

    prompt = _direct_mimo_prompt(request)

    assert 'exactly: [preceding context] "exact quoted segment" [following context]' in prompt
    assert "Do not return an unquoted sentence or plain text." in prompt
    assert "at least 50 exact quoted words only when" in prompt
    assert "at least one digit and at least one recognized statistical marker" in prompt
    assert "Otherwise, use at least 75 exact quoted words" in prompt
    assert "Python validation is authoritative" in prompt
    assert "paraphrase, heal, expand, or invent context" in prompt


def test_direct_mimo_analyst_prompt_binds_candidate_stance() -> None:
    request = _request().model_copy(
        update={
            "stage": LLMStage.ANALYST,
            "requested_output_type": ScoreDecision,
        }
    )

    prompt = _direct_mimo_prompt(request)

    assert "The candidate stance is binding." in prompt
    assert "assign claim_fit at most 2 and approved=false" in prompt
    assert "It is not final factual approval" in prompt


def test_direct_mimo_semantic_score_schema_rejects_application_owned_fields() -> None:
    request = _request().model_copy(
        update={
            "stage": LLMStage.ANALYST,
            "requested_output_type": ScoreDecision,
        }
    )
    assert MimoScoreResponse.model_validate(
        {
            "evidence_quality": 4,
            "claim_fit": 5,
            "rationale": "The evidence directly supports the claim.",
        }
    )
    with pytest.raises(ValueError):
        MimoScoreResponse.model_validate(
            {
                "run_id": str(request.run_id),
                "evidence_quality": 4,
                "claim_fit": 5,
                "rationale": "The evidence directly supports the claim.",
            }
        )


def test_direct_mimo_assembles_extractor_identity_without_rewriting_quote() -> None:
    request = _extractor_request()
    semantic = MimoExtractionResponse(
        extracted_quote_block=(
            '[Invented context.] "Exact public evidence sentence." [Also invented.]'
        )
    )
    output = _assemble_direct_mimo_output(
        request,
        semantic,
        created_at=datetime(2026, 7, 31, tzinfo=UTC),
    )
    extractor_input = request.input_artifact

    assert isinstance(output, ProvisionalCandidate)
    assert isinstance(extractor_input, ExtractionLLMInput)
    assert output.run_id == request.run_id
    assert output.stance is Stance.OPPOSING
    assert output.source_url == extractor_input.retrieval.resolved_url
    assert output.retrieval_attempt_id == extractor_input.retrieval.retrieval_attempt_id
    assert output.query_id == extractor_input.retrieval.query_id
    assert output.query_round == extractor_input.retrieval.query_round
    assert output.search_rank == extractor_input.retrieval.search_rank
    assert output.snapshot_id == extractor_input.source.snapshot_id
    assert output.snapshot_sha256 == extractor_input.source.snapshot_sha256
    assert output.extraction_prompt_version == request.prompt.version
    assert output.extraction_model_name == request.model_alias.value
    assert output.extracted_quote_block == semantic.extracted_quote_block


def test_direct_mimo_stamps_deterministic_planner_identity() -> None:
    request = _request().model_copy(
        update={
            "stage": LLMStage.PLANNER,
            "requested_output_type": PlannerOutput,
        }
    )
    created_at = datetime(2026, 7, 31, tzinfo=UTC)
    raw = {
        "claim_definition": {
            "claim_text": "Public claim.",
            "population": "Adults",
            "jurisdiction": "Global",
            "time_period": "Current evidence",
            "comparison_baseline": "No intervention",
            "intervention_or_exposure": "Public intervention",
            "causal_or_comparative_meaning": "Comparative effect",
        },
        "ambiguities": [
            {
                "description": "Scope ambiguity.",
                "impact": "May affect interpretation.",
            }
        ],
        "search_queries": [
            {
                "stance": stance,
                "query_round": round_number,
                "strategy": "Public evidence search.",
                "query_text": f"public evidence {index}",
                "exclusion_parameters": (
                    "-site:reddit.com -site:quora.com -site:youtube.com -site:tiktok.com"
                ),
            }
            for index, (stance, round_number) in enumerate(
                [
                    ("supporting", 1),
                    ("supporting", 2),
                    ("supporting", 3),
                    ("opposing", 1),
                    ("opposing", 2),
                    ("opposing", 3),
                ],
                start=1,
            )
        ],
    }

    semantic = MimoPlannerResponse.model_validate(raw)
    first = _assemble_direct_mimo_output(request, semantic, created_at=created_at)
    second = _assemble_direct_mimo_output(request, semantic, created_at=created_at)
    output = PlannerOutput.model_validate(first)

    assert first == second
    assert output.run_id == request.run_id
    assert output.claim_definition.run_id == request.run_id
    assert all(item.run_id == request.run_id for item in output.ambiguities)
    assert all(item.run_id == request.run_id for item in output.search_queries)
    assert all(isinstance(item.query_id, UUID) for item in output.search_queries)
    assert len({item.query_id for item in output.search_queries}) == 6
    assert output.planner_prompt_version == request.prompt.version
    assert output.planner_model_name == request.model_alias.value

    with pytest.raises(ValueError):
        MimoPlannerResponse.model_validate({**raw, "run_id": str(uuid4())})


def test_direct_mimo_json_mode_returns_exact_typed_output_and_estimated_cost() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers.get("api-key")
        observed["payload"] = __import__("json").loads(request.content)
        return _response(request)

    adapter = XiaomiMimoAdapter(
        MimoConfig(api_key=SecretStr("mimo-secret-value")),
        client=httpx.Client(
            base_url="https://api.xiaomimimo.com/v1",
            transport=httpx.MockTransport(handler),
        ),
        max_call_cost_usd=Decimal("0.10"),
        max_call_tokens=25_000,
    )
    request = _request()
    output = adapter.generate(request)
    metadata = adapter.last_call_metadata()

    assert isinstance(output, ReviewerDecision)
    assert observed["authorization"] == "mimo-secret-value"
    payload = observed["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "mimo-v2.5-pro"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["stream"] is False
    assert payload["max_completion_tokens"] == 4096
    assert "Never create IDs, timestamps, model names" in payload["messages"][0]["content"]
    assert "provider" not in payload
    assert metadata.returned_model == "mimo-v2.5-pro"
    assert metadata.cost_estimated is True
    assert metadata.usage.total_tokens == 15
    expected = DIRECT_MIMO_PRICE_CAP.upper_bound(10, 5)
    assert metadata.usage.cost_usd == expected


@pytest.mark.parametrize(
    ("response_builder", "code"),
    [
        (
            lambda request: _response(request, model="mimo-v2.5"),
            MimoFailureCode.MODEL_MISMATCH,
        ),
        (
            lambda request: _response(request, content="```json\n{}\n```"),
            MimoFailureCode.MALFORMED_JSON,
        ),
        (
            lambda request: _response(request, content="{}"),
            MimoFailureCode.SCHEMA,
        ),
        (
            lambda request: _response(
                request,
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 99,
                },
            ),
            MimoFailureCode.MALFORMED_USAGE,
        ),
    ],
)
def test_direct_mimo_fails_closed_on_live_response_incompatibilities(
    response_builder: object,
    code: MimoFailureCode,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response_builder(request)  # type: ignore[operator]

    adapter = XiaomiMimoAdapter(
        MimoConfig(api_key=SecretStr("secret")),
        client=httpx.Client(
            base_url="https://api.xiaomimimo.com/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(MimoProviderError) as exc_info:
        adapter.generate(_request())
    assert exc_info.value.code is code


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "Xiaomi MiMo authentication failed (HTTP 401, request_id=req-401)"),
        (403, "Xiaomi MiMo request was forbidden (HTTP 403, request_id=req-403)"),
    ],
)
def test_direct_mimo_auth_errors_preserve_safe_diagnostic_identity(
    status: int,
    message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"message": "must never be persisted"}},
            headers={"x-request-id": f"req-{status}"},
            request=request,
        )

    adapter = XiaomiMimoAdapter(
        MimoConfig(api_key=SecretStr("secret")),
        client=httpx.Client(
            base_url="https://api.xiaomimimo.com/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(MimoProviderError) as exc_info:
        adapter.generate(_request())

    error = exc_info.value
    assert error.code is MimoFailureCode.AUTHENTICATION
    assert error.http_status == status
    assert error.request_id == f"req-{status}"
    assert str(error) == message
    assert "must never be persisted" not in str(error)


def test_direct_mimo_auth_error_omits_unsafe_request_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-request-id": "unsafe request id with spaces"},
            request=request,
        )

    adapter = XiaomiMimoAdapter(
        MimoConfig(api_key=SecretStr("secret")),
        client=httpx.Client(
            base_url="https://api.xiaomimimo.com/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(MimoProviderError) as exc_info:
        adapter.generate(_request())

    assert exc_info.value.request_id is None
    assert str(exc_info.value) == "Xiaomi MiMo request was forbidden (HTTP 403)"


def test_direct_mimo_schema_error_reports_only_redacted_locations_and_types() -> None:
    rejected_value = "must-never-be-persisted"

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, content=f'{{"unexpected":"{rejected_value}"}}')

    adapter = XiaomiMimoAdapter(
        MimoConfig(api_key=SecretStr("secret")),
        client=httpx.Client(
            base_url="https://api.xiaomimimo.com/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(MimoProviderError) as exc_info:
        adapter.generate(_request())

    message = str(exc_info.value)
    assert exc_info.value.code is MimoFailureCode.SCHEMA
    assert "schema diagnostics:" in message
    assert "reviewed_statement:missing" in message
    assert "<extra>:extra_forbidden" in message
    assert rejected_value not in message
    assert "input" not in message
