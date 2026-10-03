from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError

from providers.llm import (
    GenerationSettings,
    LLMRequest,
    LLMStage,
    load_prompt,
    render_stage_prompt,
)
from providers.mimo import XiaomiMimoAdapter
from providers.model_choices import ACTIVE_MODEL_STAGES, StageModelSelections
from providers.pricing import conservative_token_estimate
from providers.v2_budget import (
    BudgetedV2LLMProvider,
    RoutedV2LLMProvider,
    V2BudgetExceededError,
    V2PhysicalCallCompletion,
    V2PhysicalCallStart,
    V2RunCeilings,
    V2SourceBudgetExceededError,
    _snapshot,
    read_v2_physical_call_audit,
)
from providers.v2_routing import V2RoutingConfig
from researchassistant.contracts.model_research import v2_payload_fingerprint
from researchassistant.contracts.models import (
    RunManifest,
    RunStatus,
    SelectedSentenceRange,
    Stage,
    StrictModel,
    V2PipelineIdentity,
    V2VerbatimQuoteSelection,
)
from researchassistant.storage.store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
)

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


class _InputArtifact(StrictModel):
    run_id: UUID
    note: str = "offline budget regression"


def _database(tmp_path: Path, run_id: UUID) -> str:
    path = str(tmp_path / "provider-budget.sqlite3")
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="Offline provider-budget regression.",
            current_stage=Stage.EVIDENCE_ANALYST,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), _NOW)
    return path


def _request(run_id: UUID, routing: V2RoutingConfig) -> LLMRequest:
    stage = LLMStage.EXTRACTOR
    artifact = _InputArtifact(run_id=run_id)
    output_type = V2VerbatimQuoteSelection
    prompt = load_prompt(stage)
    rendered_prompt = render_stage_prompt(prompt, artifact, output_type)
    return LLMRequest(
        run_id=run_id,
        stage=stage,
        prompt=prompt,
        rendered_prompt=rendered_prompt,
        input_artifact=artifact,
        input_artifact_ids=(uuid4(),),
        requested_output_type=output_type,
        model_alias=routing.preflight().for_stage(stage).logical_alias,
        generation=GenerationSettings(temperature=None),
    )


def _routed_provider(
    routing: V2RoutingConfig,
    ceilings: V2RunCeilings,
    client: httpx.Client,
) -> RoutedV2LLMProvider:
    return RoutedV2LLMProvider(
        {
            stage: XiaomiMimoAdapter(
                routing.configuration_for_stage(stage).config,
                client=client,
                price_cap=routing.configuration_for_stage(stage).route.price_cap,
                max_call_cost_usd=ceilings.max_total_cost_usd,
                max_call_tokens=ceilings.max_total_tokens,
                expected_model_alias=routing.configuration_for_stage(stage).route.logical_alias,
            )
            for stage in ACTIVE_MODEL_STAGES
        }
    )


@pytest.mark.parametrize("ceiling", ["tokens", "cost"])
def test_v2_budget_reserves_selected_transport_prompt_before_http(
    tmp_path: Path,
    ceiling: str,
) -> None:
    run_id = uuid4()
    max_tokens = 500_000
    max_cost = Decimal("1.00")
    ceilings = V2RunCeilings(max_total_tokens=max_tokens, max_total_cost_usd=max_cost)
    routing = V2RoutingConfig.from_environment(
        {"LUNA_API_KEY": "offline-test-key"},
        repository_revision="offline-provider-budget-test",
        stage_models=StageModelSelections(),
    )
    request = _request(run_id, routing)
    rendered_reservation = routing.preflight().reserve(
        request.stage,
        conservative_token_estimate(request.rendered_prompt),
    )
    route = routing.preflight().for_stage(request.stage)
    with httpx.Client(transport=httpx.MockTransport(_unexpected_transport)) as probe_client:
        adapter = XiaomiMimoAdapter(
            routing.configuration_for_stage(request.stage).config,
            client=probe_client,
            price_cap=route.price_cap,
            max_call_cost_usd=max_cost,
            max_call_tokens=max_tokens,
            expected_model_alias=route.logical_alias,
        )
        direct_prompt_bytes = adapter.conservative_input_tokens(request)
    transport_reservation = routing.preflight().reserve(request.stage, direct_prompt_bytes)
    assert direct_prompt_bytes > conservative_token_estimate(request.rendered_prompt)

    if ceiling == "tokens":
        previous_tokens = max_tokens - rendered_reservation.reserved_tokens
        previous_cost = Decimal("0.10")
        assert transport_reservation.reserved_tokens > rendered_reservation.reserved_tokens
    else:
        previous_tokens = max_tokens - transport_reservation.reserved_tokens
        previous_cost = max_cost - rendered_reservation.reserved_cost_usd
        assert transport_reservation.reserved_cost_usd > rendered_reservation.reserved_cost_usd

    path = _database(tmp_path, run_id)
    start = V2PhysicalCallStart(
        run_id=run_id,
        sequence=1,
        stage="planner",
        model_alias="gpt-6-luna-xhigh",
        reserved_tokens=previous_tokens,
        reserved_cost_usd=previous_cost,
        started_at=_NOW,
    )
    completion = V2PhysicalCallCompletion(
        run_id=run_id,
        sequence=1,
        succeeded=True,
        usage_tokens=previous_tokens,
        usage_cost_usd=previous_cost,
        completed_at=_NOW,
    )
    insert_v2_artifact(path, "phase-13-physical-call-001-start", start, _NOW)
    insert_v2_artifact(path, "phase-13-physical-call-001-completion", completion, _NOW)

    requests: list[httpx.Request] = []

    def record_transport(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(record_transport)) as client:
        provider = BudgetedV2LLMProvider(
            db_path=path,
            run_id=run_id,
            provider=_routed_provider(routing, ceilings, client),
            routing_config=routing,
            ceilings=ceilings,
        )
        expected_message = "token ceiling" if ceiling == "tokens" else "cost ceiling"
        with pytest.raises(V2BudgetExceededError, match=expected_message):
            provider.generate(request)

    assert requests == []


def test_direct_mimo_adapter_uses_compatible_prompt_estimator_before_http(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    max_tokens = 500_000
    max_cost = Decimal("1.00")
    ceilings = V2RunCeilings(max_total_tokens=max_tokens, max_total_cost_usd=max_cost)
    routing = V2RoutingConfig.from_environment(
        {"LUNA_API_KEY": "offline-test-key"},
        repository_revision="offline-direct-mimo-budget-test",
        stage_models=StageModelSelections(),
    )
    request = _request(run_id, routing)
    minimum = conservative_token_estimate(request.rendered_prompt)
    route = routing.preflight().for_stage(request.stage)
    rendered_reservation = routing.preflight().reserve(request.stage, minimum)
    path = _database(tmp_path, run_id)
    start = V2PhysicalCallStart(
        run_id=run_id,
        sequence=1,
        stage="planner",
        model_alias="gpt-6-luna-xhigh",
        reserved_tokens=max_tokens - rendered_reservation.reserved_tokens,
        reserved_cost_usd=Decimal("0.10"),
        started_at=_NOW,
    )
    completion = V2PhysicalCallCompletion(
        run_id=run_id,
        sequence=1,
        succeeded=True,
        usage_tokens=start.reserved_tokens,
        usage_cost_usd=start.reserved_cost_usd,
        completed_at=_NOW,
    )
    insert_v2_artifact(path, "phase-13-physical-call-001-start", start, _NOW)
    insert_v2_artifact(path, "phase-13-physical-call-001-completion", completion, _NOW)
    requests: list[httpx.Request] = []

    def record_transport(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(record_transport)) as client:
        adapter = XiaomiMimoAdapter(
            routing.configuration_for_stage(request.stage).config,
            client=client,
            price_cap=route.price_cap,
            max_call_cost_usd=max_cost,
            max_call_tokens=max_tokens,
            expected_model_alias=route.logical_alias,
        )
        assert adapter.conservative_input_tokens(request, minimum) > minimum
        provider = BudgetedV2LLMProvider(
            db_path=path,
            run_id=run_id,
            provider=adapter,
            routing_config=routing,
            ceilings=ceilings,
        )
        with pytest.raises(V2BudgetExceededError, match="token ceiling"):
            provider.generate(request)

    assert requests == []


@pytest.mark.parametrize("include_cache_details", [False, True])
def test_physical_call_audit_preserves_provider_usage_split(
    tmp_path: Path,
    include_cache_details: bool,
) -> None:
    run_id = uuid4()
    ceilings = V2RunCeilings(max_total_cost_usd=Decimal("1.00"))
    routing = V2RoutingConfig.from_environment(
        {"LUNA_API_KEY": "offline-test-key"},
        repository_revision="offline-usage-telemetry-test",
        stage_models=StageModelSelections(),
    )
    request = _request(run_id, routing)
    output = V2VerbatimQuoteSelection(
        selected_sentence_ranges=(SelectedSentenceRange(start_sentence=1, end_sentence=1),)
    )
    usage: dict[str, object] = {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
    if include_cache_details:
        usage["prompt_tokens_details"] = {"cached_tokens": 30, "cache_write_tokens": 20}

    def record_transport(http_request: httpx.Request) -> httpx.Response:
        payload = json.loads(http_request.content)
        return httpx.Response(
            200,
            json={
                "id": "offline-response-id",
                "model": payload["model"],
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": output.model_dump_json()},
                    }
                ],
                "usage": usage,
            },
        )

    path = _database(tmp_path, run_id)
    with httpx.Client(
        base_url="https://fixture.test", transport=httpx.MockTransport(record_transport)
    ) as client:
        provider = BudgetedV2LLMProvider(
            db_path=path,
            run_id=run_id,
            provider=_routed_provider(routing, ceilings, client),
            routing_config=routing,
            ceilings=ceilings,
        )
        assert provider.generate(request) == output

    audit = read_v2_physical_call_audit(path, run_id)
    completion = audit.completions[0]
    assert completion is not None
    assert completion.usage_tokens == 120
    assert completion.input_tokens == 100
    assert completion.output_tokens == 20
    assert completion.cached_input_tokens == (30 if include_cache_details else None)
    assert completion.uncached_input_tokens == (70 if include_cache_details else None)
    assert completion.cache_write_tokens == (20 if include_cache_details else None)
    assert completion.usage_cost_basis == (
        "published_cache_prices_reported_writes"
        if include_cache_details
        else "configured_price_cap"
    )


def test_physical_call_audit_reads_legacy_combined_only_payload(tmp_path: Path) -> None:
    run_id = uuid4()
    legacy_payload = {
        "run_id": str(run_id),
        "sequence": 1,
        "succeeded": True,
        "usage_tokens": 120,
        "usage_cost_usd": "0.0012",
        "failure": None,
        "completed_at": _NOW.isoformat(),
    }

    path = _database(tmp_path, run_id)
    payload_json = json.dumps(legacy_payload, separators=(",", ":"), sort_keys=True)
    start_payload = json.dumps(
        V2PhysicalCallStart(
            run_id=run_id,
            sequence=1,
            stage="analyst",
            model_alias="gpt-6-luna-xhigh",
            reserved_tokens=120,
            reserved_cost_usd=Decimal("0.0012"),
            started_at=_NOW,
        ).model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT INTO v2_artifacts
               (run_id, artifact_key, artifact_type, payload_json, payload_sha256, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(run_id),
                "phase-13-physical-call-001-start",
                "V2PhysicalCallStart",
                start_payload,
                v2_payload_fingerprint(start_payload),
                _NOW.isoformat(),
            ),
        )
        connection.execute(
            """INSERT INTO v2_artifacts
               (run_id, artifact_key, artifact_type, payload_json, payload_sha256, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(run_id),
                "phase-13-physical-call-001-completion",
                "V2PhysicalCallCompletion",
                payload_json,
                v2_payload_fingerprint(payload_json),
                _NOW.isoformat(),
            ),
        )

    restored = read_v2_physical_call_audit(path, run_id).completions[0]
    assert restored is not None

    assert restored.usage_tokens == 120
    assert restored.input_tokens is None
    assert restored.output_tokens is None
    assert restored.cached_input_tokens is None
    assert restored.uncached_input_tokens is None
    assert restored.cache_write_tokens is None
    assert restored.usage_cost_basis is None


@pytest.mark.parametrize(
    "changes",
    [
        {"input_tokens": 100, "output_tokens": 20, "usage_tokens": 121},
        {"input_tokens": 100, "usage_tokens": 120},
        {"output_tokens": 20, "usage_tokens": 120},
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "usage_tokens": 120,
            "cached_input_tokens": 30,
            "uncached_input_tokens": 69,
        },
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "usage_tokens": 120,
            "cached_input_tokens": 30,
        },
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "usage_tokens": 120,
            "cache_write_tokens": 10,
        },
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "usage_tokens": 120,
            "cached_input_tokens": 30,
            "uncached_input_tokens": 70,
            "cache_write_tokens": 71,
        },
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "usage_tokens": 120,
            "cached_input_tokens": 30,
            "uncached_input_tokens": 70,
            "usage_cost_basis": "published_cache_prices_reported_writes",
        },
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "usage_tokens": 120,
            "cached_input_tokens": 30,
            "uncached_input_tokens": 70,
            "cache_write_tokens": 10,
            "usage_cost_basis": "published_cache_prices_assumed_all_uncached_writes",
        },
    ],
)
def test_physical_call_completion_rejects_inconsistent_usage_split(
    changes: dict[str, int],
) -> None:
    payload = V2PhysicalCallCompletion(
        run_id=uuid4(),
        sequence=1,
        succeeded=True,
        usage_tokens=120,
        completed_at=_NOW,
    ).model_dump()
    payload.update(changes)

    with pytest.raises(ValidationError):
        V2PhysicalCallCompletion.model_validate(payload)


def _unexpected_transport(http_request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected transport request: {http_request.method}")


def test_unknown_provider_usage_keeps_reserved_exposure() -> None:
    run_id = uuid4()
    start = V2PhysicalCallStart(
        run_id=run_id,
        sequence=1,
        stage="analyst",
        model_alias="gpt-6-luna-xhigh",
        reserved_tokens=12_500,
        reserved_cost_usd=Decimal("0.25"),
        started_at=_NOW,
    )
    completion = V2PhysicalCallCompletion(
        run_id=run_id,
        sequence=1,
        succeeded=True,
        completed_at=_NOW,
    )

    snapshot = _snapshot(
        [start],
        {1: completion},
        V2RunCeilings(max_total_tokens=500_000, max_total_cost_usd=Decimal("1.00")),
    )

    assert snapshot.token_exposure == 12_500
    assert snapshot.cost_exposure_usd == Decimal("0.25")


def test_source_physical_call_cap_has_a_distinct_budget_error(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    source_id = uuid4()
    ceilings = V2RunCeilings(max_total_cost_usd=Decimal("1.00"))
    routing = V2RoutingConfig.from_environment(
        {"LUNA_API_KEY": "offline-test-key"},
        repository_revision="offline-source-budget-error-test",
        stage_models=StageModelSelections(),
    )
    request = _request(run_id, routing).model_copy(
        update={
            "source_id": source_id,
            "source_token_cap": 60_000,
            "source_physical_call_cap": 3,
        }
    )
    path = _database(tmp_path, run_id)
    for sequence in range(1, 4):
        insert_v2_artifact(
            path,
            f"phase-13-physical-call-{sequence:03d}-start",
            V2PhysicalCallStart(
                run_id=run_id,
                sequence=sequence,
                stage="extractor",
                model_alias="gpt-6-luna-xhigh",
                reserved_tokens=1,
                reserved_cost_usd=Decimal("0.000001"),
                source_id=source_id,
                source_token_cap=60_000,
                source_physical_call_cap=3,
                started_at=_NOW,
            ),
            _NOW,
        )

    requests: list[httpx.Request] = []

    def record_transport(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(record_transport)) as client:
        provider = BudgetedV2LLMProvider(
            db_path=path,
            run_id=run_id,
            provider=_routed_provider(routing, ceilings, client),
            routing_config=routing,
            ceilings=ceilings,
        )
        with pytest.raises(V2SourceBudgetExceededError, match="source .* physical-call cap"):
            provider.generate(request)

    assert requests == []
