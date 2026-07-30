from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from agents.reviewer import ReviewerDecision, ReviewerInput
from providers.config import MimoConfig, ProviderConfigurationError
from providers.llm import DIRECT_MIMO_ROUTING, LLMStage, ModelAlias, build_stage_request
from providers.mimo import MimoFailureCode, MimoProviderError, XiaomiMimoAdapter
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
    assert "provider" not in payload
    assert metadata.returned_model == "mimo-v2.5-pro"
    assert metadata.cost_estimated is True
    assert metadata.usage.total_tokens == 15
    expected = DIRECT_MIMO_PRICE_CAP.upper_bound(10, 5)
    assert metadata.usage.cost_usd == float(expected)


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
