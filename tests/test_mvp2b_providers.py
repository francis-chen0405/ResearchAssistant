from __future__ import annotations

import base64
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agents.reviewer import ReviewerDecision, ReviewerInput
from providers.acquisition import AcquisitionFailureCode, WigoloAcquisitionAdapter
from providers.config import (
    LiveSmokeConfig,
    OpenRouterConfig,
    ProviderConfigurationError,
    WigoloConfig,
)
from providers.llm import LLMStage, ModelAlias, build_stage_request
from providers.normalization import (
    NORMALIZATION_VERSION,
    PDF_POLICY_VERSION,
    NormalizationError,
    locate_exact_quotes,
    normalize_html,
    normalize_markdown,
    normalize_pdf,
)
from providers.openrouter import (
    OpenRouterAdapter,
    OpenRouterFailureCode,
    OpenRouterProviderError,
)
from providers.scraper import ScrapeRequest, ScraperProviderError
from providers.search import SearchFailureCode, SearchProviderError, SearchRequest
from providers.wigolo import WigoloSearchAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "mvp2b"


def _search_adapter(payload: object, *, status: int = 200) -> WigoloSearchAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search"
        body = json.loads(request.content)
        assert body == {
            "query": "frozen query",
            "max_results": 5,
            "max_fetches": 0,
            "include_content": False,
            "search_depth": "balanced",
            "force_refresh": True,
            "include_full_markdown": False,
        }
        return httpx.Response(status, json=payload)

    client = httpx.Client(base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler))
    return WigoloSearchAdapter(WigoloConfig(), client=client, health_verified=True)


def _valid_search_payload() -> dict[str, object]:
    return {
        "results": [
            {
                "url": "https://example.org/a?x=1#section",
                "title": "A",
                "score": 0.9,
                "published_at": "2026-07-01T12:00:00Z",
                "engine": "alpha",
                "unexpected": "discard-at-API-boundary",
            },
            {"url": "http://example.net:8080/path", "title": "B", "score": 0.8},
        ],
        "engines": {"alpha": {"status": "ok", "result_count": 2, "latency_ms": 4.5}},
        "warnings": ["one engine unavailable"],
        "degraded": True,
        "unexpected_top_level": True,
    }


def test_wigolo_search_preserves_rank_identity_telemetry_and_unusual_urls() -> None:
    response = _search_adapter(_valid_search_payload()).search(
        SearchRequest(query_text="frozen query", limit=5)
    )

    assert [item.rank for item in response.results] == [1, 2]
    assert response.results[0].original_url.endswith("?x=1#section")
    assert response.provider_name == "wigolo"
    assert response.provider_version == "0.2.1"
    assert response.degraded_pool is True
    assert response.engine_telemetry[0].engine == "alpha"
    assert "unexpected" not in response.results[0].model_dump()


def test_wigolo_search_deduplicates_urls_without_reordering_survivors() -> None:
    payload = _valid_search_payload()
    payload["results"] = [
        {"url": "https://example.org/a", "title": "first"},
        {"url": "https://example.org/a", "title": "duplicate"},
        {"url": "https://example.org/c", "title": "third"},
    ]
    response = _search_adapter(payload).search(SearchRequest(query_text="frozen query", limit=5))
    assert [(item.rank, item.title) for item in response.results] == [(1, "first"), (3, "third")]
    assert "duplicate URL omitted" in response.warnings[-1]


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"results": []}, SearchFailureCode.EMPTY_RESULTS),
        ({"results": [{"title": "missing"}]}, SearchFailureCode.INVALID_URL),
        ({"results": [{"url": "javascript:alert(1)"}]}, SearchFailureCode.INVALID_URL),
        (
            {"results": [{"url": "https://example.org", "score": "high"}]},
            SearchFailureCode.MALFORMED_RESPONSE,
        ),
        (
            {"results": [{"url": "https://example.org", "published_at": "not-a-date"}]},
            SearchFailureCode.MALFORMED_RESPONSE,
        ),
        (
            {"error": {"message": "provider failed"}, "results": []},
            SearchFailureCode.PERMANENT_FAILURE,
        ),
        ({"results": "wrong"}, SearchFailureCode.MALFORMED_RESPONSE),
    ],
)
def test_wigolo_search_normalizes_malformed_successes(
    payload: object, code: SearchFailureCode
) -> None:
    with pytest.raises(SearchProviderError) as exc_info:
        _search_adapter(payload).search(SearchRequest(query_text="frozen query", limit=5))
    assert exc_info.value.code is code


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, SearchFailureCode.AUTHENTICATION, False),
        (408, SearchFailureCode.TIMEOUT, True),
        (429, SearchFailureCode.RATE_LIMIT, True),
        (503, SearchFailureCode.TRANSIENT_OUTAGE, True),
        (422, SearchFailureCode.PERMANENT_FAILURE, False),
    ],
)
def test_wigolo_search_normalizes_http_errors(
    status: int, code: SearchFailureCode, retryable: bool
) -> None:
    with pytest.raises(SearchProviderError) as exc_info:
        _search_adapter({}, status=status).search(SearchRequest(query_text="frozen query", limit=5))
    assert (exc_info.value.code, exc_info.value.retryable) == (code, retryable)


def test_wigolo_search_normalizes_transport_timeout_and_wrong_health_identity() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(timeout_handler)
    )
    with pytest.raises(SearchProviderError) as exc_info:
        WigoloSearchAdapter(WigoloConfig(), client=client, health_verified=True).search(
            SearchRequest(query_text="frozen query", limit=5)
        )
    assert exc_info.value.code is SearchFailureCode.TIMEOUT

    def wrong_health(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "other", "version": "0.2.1"}, request=request)

    wrong_client = httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(wrong_health)
    )
    with pytest.raises(SearchProviderError) as exc_info:
        WigoloSearchAdapter(WigoloConfig(), client=wrong_client).verify_health()
    assert exc_info.value.code is SearchFailureCode.MISSING_CONFIGURATION


def test_frozen_html_normalization_is_byte_deterministic_with_exact_offsets() -> None:
    payload = (FIXTURES / "article.html").read_bytes()
    first = normalize_html(payload, declared_charset="utf-8")
    second = normalize_html(payload, declared_charset="utf-8")
    quote = "The intervention improved completion by 12 percent in the frozen cohort."
    offsets = locate_exact_quotes(first.text, (quote,))

    assert first == second
    assert first.normalization_version == NORMALIZATION_VERSION
    assert first.sha256 == second.sha256
    assert first.text[offsets[0].start_char : offsets[0].end_char] == quote
    assert "private-destination" not in first.text
    assert "Navigation" not in first.text


def test_markdown_normalization_retains_link_text_not_destination_and_truncates_stably() -> None:
    markdown = (
        "# Study\n\n"
        + " ".join(f"word{i}" for i in range(3005))
        + "\n\n[visible](https://secret.example)"
    )
    first = normalize_markdown(markdown)
    second = normalize_markdown(markdown)
    assert first == second
    assert first.word_count == 3000
    assert first.truncated is True
    assert "secret.example" not in first.text


def test_frozen_digital_pdf_is_deterministic_with_exact_offsets() -> None:
    payload = base64.b64decode((FIXTURES / "digital.pdf.b64").read_text().strip())
    first = normalize_pdf(payload)
    second = normalize_pdf(payload)
    quote = "Deterministic PDF evidence sentence."
    offsets = locate_exact_quotes(first.text, (quote,))
    assert first == second
    assert first.pdf_policy_version == PDF_POLICY_VERSION
    assert first.text[offsets[0].start_char : offsets[0].end_char] == quote


@pytest.mark.parametrize("payload", [b"not a pdf", b"%PDF-1.4 broken"])
def test_malformed_pdf_is_explicitly_unsupported(payload: bytes) -> None:
    with pytest.raises(NormalizationError) as exc_info:
        normalize_pdf(payload)
    assert exc_info.value.code == "unsupported_pdf"


def test_frozen_image_only_pdf_is_explicitly_unsupported_without_ocr() -> None:
    payload = base64.b64decode((FIXTURES / "image_only.pdf.b64").read_text().strip())
    with pytest.raises(NormalizationError) as exc_info:
        normalize_pdf(payload)
    assert exc_info.value.code == "unsupported_pdf"


def test_acquisition_records_original_final_canonical_and_normalized_hash() -> None:
    html = (FIXTURES / "article.html").read_bytes()

    def source_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=html, headers={"content-type": "text/html; charset=utf-8"}, request=request
        )

    def wigolo_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "markdown": (
                    "# Frozen Evidence\n\nThe intervention improved completion by 12 percent "
                    "in the frozen cohort."
                ),
            },
            request=request,
        )

    adapter = WigoloAcquisitionAdapter(
        WigoloConfig(),
        source_client=httpx.Client(transport=httpx.MockTransport(source_handler)),
        wigolo_client=httpx.Client(
            base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(wigolo_handler)
        ),
    )
    result = adapter.scrape(ScrapeRequest(url="https://example.org/original", timeout_seconds=15))
    assert result.original_url == "https://example.org/original"
    assert result.resolved_url == "https://example.org/original"
    assert result.canonical_url == "https://example.org/canonical-study"
    assert result.snapshot_sha256 is not None
    assert result.text.startswith("Frozen Evidence")


def test_acquisition_enforces_streaming_size_and_content_type() -> None:
    config = WigoloConfig(max_html_bytes=10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"more than ten bytes",
            headers={"content-type": "text/html"},
            request=request,
        )

    adapter = WigoloAcquisitionAdapter(
        config,
        source_client=httpx.Client(transport=httpx.MockTransport(handler)),
        wigolo_client=httpx.Client(
            base_url=config.base_url, transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(ScraperProviderError) as exc_info:
        adapter.scrape(ScrapeRequest(url="https://example.org/large", timeout_seconds=15))
    assert exc_info.value.code == AcquisitionFailureCode.TOO_LARGE


def test_acquisition_allows_exactly_one_controlled_render_retry() -> None:
    html = b"<html><body><main>Visible source.</main></body></html>"
    render_modes: list[str] = []

    def source_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=html, headers={"content-type": "text/html"}, request=request
        )

    def wigolo_handler(request: httpx.Request) -> httpx.Response:
        mode = json.loads(request.content)["render_js"]
        render_modes.append(mode)
        body = (
            {"status": "challenge"}
            if mode == "never"
            else {"status": "ok", "markdown": "Rendered visible source."}
        )
        return httpx.Response(200, json=body, request=request)

    config = WigoloConfig()
    adapter = WigoloAcquisitionAdapter(
        config,
        source_client=httpx.Client(transport=httpx.MockTransport(source_handler)),
        wigolo_client=httpx.Client(
            base_url=config.base_url, transport=httpx.MockTransport(wigolo_handler)
        ),
    )
    result = adapter.scrape(ScrapeRequest(url="https://example.org/challenge", timeout_seconds=15))
    assert result.rendered is True
    assert render_modes == ["never", "always"]


def _reviewer_request() -> object:
    run_id = uuid4()
    reviewer_input = ReviewerInput(
        extracted_quote_block='[Before.] "Evidence." [After.]',
        preceding_context="Before.",
        following_context="After.",
        draft_statement="Evidence.",
        claim_fit=3,
    )
    return build_stage_request(
        stage=LLMStage.REVIEWER,
        input_artifact=reviewer_input,
        requested_output_type=ReviewerDecision,
        input_artifact_ids=(uuid4(),),
        model_alias=ModelAlias.MIMO_V25_PRO,
        run_id=run_id,
    )


def _openrouter_adapter(
    content: str,
    *,
    finish_reason: str = "stop",
    usage: object | None = None,
    message_extra: dict[str, object] | None = None,
) -> tuple[OpenRouterAdapter, list[dict[str, object]]]:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        message: dict[str, object] = {"role": "assistant", "content": content}
        message.update(message_extra or {})
        return httpx.Response(
            200,
            json={
                "id": "gen_test",
                "model": "xiaomi/mimo-v2.5-pro",
                "provider": "approved-upstream",
                "choices": [{"finish_reason": finish_reason, "message": message}],
                "usage": usage
                if usage is not None
                else {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                    "cost": 0.001,
                },
            },
            request=request,
        )

    config = OpenRouterConfig(api_key=SecretStr("super-secret-test-key"))
    client = httpx.Client(base_url=config.base_url, transport=httpx.MockTransport(handler))
    return OpenRouterAdapter(config, client=client), requests


def _valid_reviewer_json() -> str:
    return ReviewerDecision(
        reviewed_statement="Evidence.", approved=True, rationale="All checks passed."
    ).model_dump_json()


def test_openrouter_valid_structured_output_records_model_usage_cost_and_request_controls() -> None:
    adapter, requests = _openrouter_adapter(_valid_reviewer_json())
    output = adapter.generate(_reviewer_request())
    metadata = adapter.last_call_metadata()
    assert isinstance(output, ReviewerDecision)
    assert metadata.returned_model == "xiaomi/mimo-v2.5-pro"
    assert metadata.upstream_provider == "approved-upstream"
    assert metadata.usage.total_tokens == 30
    assert metadata.usage.cost_usd == 0.001
    assert metadata.cost_estimated is False
    assert requests[0]["provider"] == {"require_parameters": True, "data_collection": "deny"}
    assert requests[0]["response_format"]["json_schema"]["strict"] is True  # type: ignore[index]
    assert "plugins" not in requests[0]


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (
            '{"reviewed_statement":"Evidence.","approved":true,"rationale":"ok","extra":1}',
            OpenRouterFailureCode.SCHEMA,
        ),
        ('{"reviewed_statement":"Evidence.","approved":true}', OpenRouterFailureCode.SCHEMA),
        (
            '{"reviewed_statement":"Evidence.","approved":false,"failure_code":"bad-enum","rationale":"no"}',
            OpenRouterFailureCode.SCHEMA,
        ),
        ('{"reviewed_statement":', OpenRouterFailureCode.MALFORMED_JSON),
        (
            'Here is your JSON: {"reviewed_statement":"Evidence."}',
            OpenRouterFailureCode.MALFORMED_JSON,
        ),
        ("```json\n{}\n```", OpenRouterFailureCode.MALFORMED_JSON),
    ],
)
def test_openrouter_rejects_invalid_structured_outputs(
    content: str, code: OpenRouterFailureCode
) -> None:
    adapter, _ = _openrouter_adapter(content)
    with pytest.raises(OpenRouterProviderError) as exc_info:
        adapter.generate(_reviewer_request())
    assert exc_info.value.code is code


def test_openrouter_normalizes_truncation_refusal_and_malformed_usage() -> None:
    truncated, _ = _openrouter_adapter(_valid_reviewer_json(), finish_reason="length")
    with pytest.raises(OpenRouterProviderError) as exc_info:
        truncated.generate(_reviewer_request())
    assert exc_info.value.code is OpenRouterFailureCode.TRUNCATED

    refused, _ = _openrouter_adapter(
        _valid_reviewer_json(), message_extra={"refusal": "cannot comply"}
    )
    with pytest.raises(OpenRouterProviderError) as exc_info:
        refused.generate(_reviewer_request())
    assert exc_info.value.code is OpenRouterFailureCode.REFUSAL

    malformed, _ = _openrouter_adapter(
        _valid_reviewer_json(),
        usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 999},
    )
    with pytest.raises(OpenRouterProviderError) as exc_info:
        malformed.generate(_reviewer_request())
    assert exc_info.value.code is OpenRouterFailureCode.MALFORMED_USAGE


def test_openrouter_estimates_cost_from_approved_cap_when_provider_cost_is_absent() -> None:
    adapter, _ = _openrouter_adapter(
        _valid_reviewer_json(),
        usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    )
    adapter.generate(_reviewer_request())
    metadata = adapter.last_call_metadata()
    assert metadata.cost_estimated is True
    assert metadata.usage.cost_usd == pytest.approx(0.0003)


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, OpenRouterFailureCode.AUTHENTICATION, False),
        (408, OpenRouterFailureCode.TIMEOUT, True),
        (429, OpenRouterFailureCode.RATE_LIMIT, True),
        (503, OpenRouterFailureCode.TRANSIENT_OUTAGE, True),
        (422, OpenRouterFailureCode.PERMANENT_FAILURE, False),
    ],
)
def test_openrouter_normalizes_http_failures(
    status: int, code: OpenRouterFailureCode, retryable: bool
) -> None:
    config = OpenRouterConfig(api_key=SecretStr("test-secret"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "details"}}, request=request)

    adapter = OpenRouterAdapter(
        config,
        client=httpx.Client(base_url=config.base_url, transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(OpenRouterProviderError) as exc_info:
        adapter.generate(_reviewer_request())
    assert (exc_info.value.code, exc_info.value.retryable) == (code, retryable)


def test_configuration_is_secret_safe_and_does_not_silently_load_files(tmp_path: Path) -> None:
    secret = "never-print-this-key"
    config = OpenRouterConfig.from_environment({"OPENROUTER_API_KEY": secret})
    assert secret not in repr(config)
    assert secret not in config.model_dump_json()
    with pytest.raises(ProviderConfigurationError) as exc_info:
        OpenRouterConfig.from_environment({})
    assert "OPENROUTER_API_KEY" in str(exc_info.value)
    assert secret not in str(exc_info.value)
    (tmp_path / ".env").write_text(f"OPENROUTER_API_KEY={secret}\n", encoding="utf-8")
    with pytest.raises(ProviderConfigurationError):
        OpenRouterConfig.from_environment({})


def test_loopback_and_live_smoke_gates_are_strict(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        WigoloConfig(base_url="http://0.0.0.0:8000")
    smoke = LiveSmokeConfig(
        enabled=True,
        approved_now=False,
        max_search_calls=1,
        max_acquisition_calls=1,
        max_llm_calls=1,
        max_tokens=10_000,
        max_cost_usd=Decimal("0.05"),
        output_path=(tmp_path / "dedicated-smoke.json").resolve(),
    )
    with pytest.raises(ProviderConfigurationError):
        smoke.require_enabled()
