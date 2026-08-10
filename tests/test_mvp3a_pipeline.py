from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
import pytest
from pydantic import ValidationError

from agents.analyst import AnalystLLMInput, StatementDraftLLMInput
from agents.planner import PlannerLLMInput
from agents.researcher import EVIDENCE_POLICY_VERSION
from agents.reviewer import ReviewerDecision, ReviewerInput
from agents.supportingresearcher import ExtractionLLMInput
from agents.synthesizer import SynthesizerLLMInput, build_synthesis_output
from models import (
    REQUIRED_QUERY_EXCLUSIONS,
    AmbiguityRecord,
    ClaimDefinition,
    PlannerOutput,
    ProviderRunContract,
    ProvisionalCandidate,
    ScoreDecision,
    SearchQuery,
    Stance,
    StatementDraft,
)
from orchestrator import (
    ProviderPipelineResult,
    ProviderRunStatus,
    inspect_provider_run,
    request_run_cancellation,
    run_mvp3a_pipeline,
    run_mvp3b_pipeline,
)
from providers.config import (
    ExaConfig,
    MimoConfig,
    OpenRouterConfig,
    ProviderConfigurationError,
    RunCeilings,
)
from providers.factory import (
    FINGERPRINT_VERSION,
    ProviderFactoryClients,
    ProviderFactoryConfig,
    build_provider_bundle,
)
from providers.llm import ModelAlias
from providers.mimo_factory import (
    MIMO_FINGERPRINT_VERSION,
    MimoProviderFactoryConfig,
    build_mimo_provider_bundle,
)
from store import read_provider_run_contract, read_run

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
RUN_ID = UUID("a0000000-0000-0000-0000-000000000001")
CLAIM = "The fixture policy improves student outcomes."
EXCLUSIONS = " ".join(REQUIRED_QUERY_EXCLUSIONS)
SUPPORT_TEXT = (
    "District report introduces the fixture policy evaluation. "
    "policy evidence shows 50% growth in student outcomes across a controlled fixture "
    "cohort because schools reported higher completion rates compared with baseline "
    "classes, and the authors state the improvement was consistent across participating "
    "campuses during the measured term while noting implementation quality remained "
    "important for interpreting the observed gains across multiple reporting periods, "
    "institutional settings, implementation teams, demographic groups, and operational "
    "conditions documented in the evaluation during the full observation window for "
    "participating schools overall. "
    "The report cautions that longer follow-up would improve confidence."
)
OPPOSE_TEXT = (
    "Independent evaluator describes implementation costs. "
    "policy evidence shows a 20% decline in student satisfaction among surveyed families "
    "after the fixture rollout, and administrators reported that average workload increased "
    "across pilot schools, which the evaluator linked to training demands, schedule "
    "disruptions, and limited support during the first semester of implementation in "
    "participating districts across multiple reporting periods, institutional settings, "
    "implementation teams, demographic groups, and operational conditions documented in "
    "the evaluation during the full observation window for participating schools overall "
    "that year. "
    "The evaluator states that later adjustments reduced some burden."
)
SUPPORT_QUOTE = (
    '[District report introduces the fixture policy evaluation.] "policy evidence shows '
    "50% growth in student outcomes across a controlled fixture cohort because schools "
    "reported higher completion rates compared with baseline classes, and the authors state "
    "the improvement was consistent across participating campuses during the measured term "
    "while noting implementation quality remained important for interpreting the observed "
    "gains across multiple reporting periods, institutional settings, implementation teams, "
    "demographic groups, and operational conditions documented in the evaluation during the "
    'full observation window for participating schools overall." [The report cautions that '
    "longer follow-up would improve confidence.]"
)
OPPOSE_QUOTE = (
    '[Independent evaluator describes implementation costs.] "policy evidence shows a 20% '
    "decline in student satisfaction among surveyed families after the fixture rollout, and "
    "administrators reported that average workload increased across pilot schools, which the "
    "evaluator linked to training demands, schedule disruptions, and limited support during "
    "the first semester of implementation in participating districts across multiple "
    "reporting periods, institutional settings, implementation teams, demographic groups, "
    "and operational conditions documented in the evaluation during the full observation "
    'window for participating schools overall that year." '
    "[The evaluator states that later adjustments reduced some burden.]"
)


class MockProviderHTTP:
    def __init__(
        self,
        *,
        malformed_primary_planner: int = 0,
        malformed_fallback_planner: int = 0,
        invalidate_synthesis: bool = False,
        planner_status: int | None = None,
        on_planner_response: Callable[[], None] | None = None,
        on_search_response: Callable[[], None] | None = None,
        malformed_search: bool = False,
        source_status: int | None = None,
        unsupported_source: bool = False,
        mismatched_draft_identity: bool = False,
        invalid_synthesis_template: bool = False,
    ) -> None:
        self.malformed_primary_planner = malformed_primary_planner
        self.malformed_fallback_planner = malformed_fallback_planner
        self.invalidate_synthesis = invalidate_synthesis
        self.planner_status = planner_status
        self.on_planner_response = on_planner_response
        self.on_search_response = on_search_response
        self.malformed_search = malformed_search
        self.source_status = source_status
        self.unsupported_source = unsupported_source
        self.mismatched_draft_identity = mismatched_draft_identity
        self.invalid_synthesis_template = invalid_synthesis_template
        self.requests: list[httpx.Request] = []
        self.search_threads: set[str] = set()
        self.calls: Counter[tuple[str, str]] = Counter()
        self._lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.requests.append(request)
        if request.url.host == "research.test":
            if self.source_status is not None:
                return httpx.Response(self.source_status, request=request)
            side = "supporting" if "/supporting/" in request.url.path else "opposing"
            source_text = SUPPORT_TEXT if side == "supporting" else OPPOSE_TEXT
            return httpx.Response(
                200,
                headers={
                    "content-type": (
                        "image/png" if self.unsupported_source else "text/html; charset=utf-8"
                    )
                },
                text=f"<html><body>{source_text}</body></html>",
                request=request,
            )
        if request.url.path in {"/v1/search", "/search"}:
            with self._lock:
                self.search_threads.add(threading.current_thread().name)
            if self.malformed_search:
                return self._json(request, {"results": "malformed"})
            payload = json.loads(request.content)
            query = payload["query"]
            side = "supporting" if query.startswith("supporting") else "opposing"
            query_round = int(re.search(r"query (\d)", query).group(1))
            response = self._json(
                request,
                {
                    "results": [
                        {
                            "url": f"https://research.test/{side}/{query_round}/{rank}",
                            "title": f"{side} {query_round}-{rank}",
                        }
                        for rank in range(1, 6)
                    ],
                    "provider": "wigolo",
                    "version": "0.2.1",
                },
            )
            if self.on_search_response is not None:
                self.on_search_response()
            return response
        if request.url.path == "/v1/fetch":
            payload = json.loads(request.content)
            url = payload["url"]
            side = "supporting" if "/supporting/" in url else "opposing"
            text = SUPPORT_TEXT if side == "supporting" else OPPOSE_TEXT
            return self._json(
                request,
                {"status": "ok", "markdown": f"{text}\n\nUnique source {url}."},
            )
        if request.url.path.endswith("/chat/completions"):
            return self._llm(request)
        return self._json(request, {"name": "wigolo", "version": "0.2.1"})

    def _llm(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model = payload["model"]
        response_format = payload["response_format"]
        if response_format["type"] == "json_schema":
            name = response_format["json_schema"]["name"]
        else:
            prompt = payload["messages"][0]["content"]
            name = re.search(r"Requested Pydantic artifact: ([A-Za-z0-9_]+)", prompt).group(1)
        alias = (
            ModelAlias.MIMO_V25_PRO.value
            if model in {"xiaomi/mimo-v2.5-pro", "mimo-v2.5-pro"}
            else ModelAlias.MINIMAX_M3.value
        )
        with self._lock:
            call_number = self.calls[(name, model)]
            self.calls[(name, model)] += 1
        if name in {"PlannerOutput", "MimoPlannerResponse"} and self.planner_status is not None:
            return self._json(
                request, {"error": {"message": "planner failed"}}, self.planner_status
            )
        if (
            name in {"PlannerOutput", "MimoPlannerResponse"}
            and model == "xiaomi/mimo-v2.5-pro"
            and call_number < self.malformed_primary_planner
        ):
            return self._completion(request, model, '{"broken":', usage=True)
        if (
            name in {"PlannerOutput", "MimoPlannerResponse"}
            and model == "minimax/minimax-m3"
            and call_number < self.malformed_fallback_planner
        ):
            return self._completion(request, model, '{"broken":', usage=True)
        input_payload = _stage_input(payload["messages"][0]["content"])
        output = self._output(name, input_payload, alias)
        if name == "SynthesisOutput" and self.invalid_synthesis_template:
            output["sections"][0]["items"][0]["connective_template_id"] = (
                "standard_evidence_citation"
            )
        if name == "SynthesisOutput" and self.invalidate_synthesis:
            output["sections"][0]["items"][0]["approved_factual_statement"] += " Altered."
        if name == "MimoSynthesisResponse" and self.invalidate_synthesis:
            output["sections"][0]["section_type"] = "limitations"
        response = self._completion(request, model, json.dumps(output), usage=True)
        if (
            name in {"PlannerOutput", "MimoPlannerResponse"}
            and self.on_planner_response is not None
        ):
            self.on_planner_response()
        return response

    def _output(self, name: str, payload: dict[str, object], alias: str) -> dict[str, object]:
        if name == "MimoPlannerResponse":
            full = self._output("PlannerOutput", payload, alias)
            return {
                "claim_definition": {
                    key: value
                    for key, value in full["claim_definition"].items()
                    if key not in {"run_id", "created_at"}
                },
                "ambiguities": [
                    {
                        "description": item["description"],
                        "impact": item["impact"],
                    }
                    for item in full["ambiguities"]
                ],
                "search_queries": [
                    {
                        key: value
                        for key, value in item.items()
                        if key not in {"run_id", "query_id", "created_at"}
                    }
                    for item in full["search_queries"]
                ],
            }
        if name == "MimoExtractionResponse":
            item = ExtractionLLMInput.model_validate(payload)
            return {
                "extracted_quote_block": (
                    SUPPORT_QUOTE if item.stance is Stance.SUPPORTING else OPPOSE_QUOTE
                )
            }
        if name == "MimoScoreResponse":
            return {
                "evidence_quality": 4,
                "claim_fit": 4,
                "rationale": "Mocked Analyst approval.",
            }
        if name == "MimoStatementDraftResponse":
            item = StatementDraftLLMInput.model_validate(payload)
            candidate = item.analyst_input.candidate
            return {
                "draft_statement": (
                    "Schools reported higher completion rates compared with baseline classes."
                    if candidate.stance is Stance.SUPPORTING
                    else (
                        "Surveyed families reported a 20% decline in student satisfaction "
                        "after the fixture rollout."
                    )
                )
            }
        if name == "MimoSynthesisResponse":
            item = SynthesizerLLMInput.model_validate(payload)
            output = build_synthesis_output(
                run_id=item.run_id,
                ledger_records=item.ledger_records,
                created_at=NOW,
                synthesizer_prompt_version="phase8-synthesizer-v2",
                synthesizer_model_name=alias,
            )
            return {
                "sections": [
                    {
                        "section_type": section.section_type.value,
                        "ledger_claim_ids": [
                            str(synthesis_item.ledger_claim_id) for synthesis_item in section.items
                        ],
                    }
                    for section in output.sections
                ]
            }
        if name == "PlannerOutput":
            planner_input = PlannerLLMInput.model_validate(payload)
            queries = [
                SearchQuery(
                    run_id=planner_input.run_id,
                    query_id=uuid5(
                        NAMESPACE_URL,
                        f"mvp3a-query::{planner_input.run_id}::{stance.value}::{query_round}",
                    ),
                    stance=stance,
                    query_round=query_round,
                    strategy=f"{stance.value} strategy {query_round}",
                    query_text=f"{stance.value} query {query_round}",
                    exclusion_parameters=EXCLUSIONS,
                    created_at=NOW,
                )
                for stance in (Stance.SUPPORTING, Stance.OPPOSING)
                for query_round in range(1, 4)
            ]
            return PlannerOutput(
                run_id=planner_input.run_id,
                claim_definition=ClaimDefinition(
                    run_id=planner_input.run_id,
                    claim_text=planner_input.raw_claim,
                    population="students",
                    jurisdiction="test jurisdiction",
                    time_period="test term",
                    comparison_baseline="baseline classes",
                    intervention_or_exposure="fixture policy",
                    causal_or_comparative_meaning="comparative improvement",
                    created_at=NOW,
                ),
                ambiguities=[
                    AmbiguityRecord(
                        run_id=planner_input.run_id,
                        ambiguity_id=uuid5(NAMESPACE_URL, f"mvp3a::{planner_input.run_id}"),
                        description="Test scope.",
                        impact="Mocked public sources only.",
                        created_at=NOW,
                    )
                ],
                search_queries=queries,
                planner_prompt_version="phase8-planner-v1",
                planner_model_name=alias,
                planned_at=NOW,
            ).model_dump(mode="json")
        if name == "ProvisionalCandidate":
            item = ExtractionLLMInput.model_validate(payload)
            retrieval = item.retrieval
            assert retrieval is not None
            return ProvisionalCandidate(
                run_id=item.run_id,
                stance=item.stance,
                source_url=retrieval.resolved_url,
                retrieval_attempt_id=retrieval.retrieval_attempt_id,
                query_id=retrieval.query_id,
                query_round=retrieval.query_round,
                search_rank=retrieval.search_rank,
                snapshot_id=item.source.snapshot_id,
                snapshot_sha256=item.source.snapshot_sha256,
                extracted_quote_block=(
                    SUPPORT_QUOTE if item.stance is Stance.SUPPORTING else OPPOSE_QUOTE
                ),
                extraction_prompt_version="mvp6.4-extractor-50-75-v1",
                extraction_model_name=alias,
                extracted_at=NOW,
            ).model_dump(mode="json")
        if name in {"ScoreDecision", "StatementDraft"}:
            item = AnalystLLMInput.model_validate(payload)
            candidate = item.candidate
            if name == "ScoreDecision":
                return ScoreDecision(
                    run_id=item.run_id,
                    quote_block_id=candidate.quote_block_id,
                    evidence_quality=4,
                    claim_fit=4,
                    ledger_score=4,
                    placement="secondary",
                    approved=True,
                    rationale="Mocked Analyst approval.",
                    analyst_prompt_version="phase8-analyst-v2",
                    analyst_model_name=alias,
                    scored_at=NOW,
                ).model_dump(mode="json")
            return StatementDraft(
                run_id=uuid4() if self.mismatched_draft_identity else item.run_id,
                statement_draft_id=uuid5(NAMESPACE_URL, f"mvp3a-draft::{candidate.quote_block_id}"),
                quote_block_id=(
                    uuid4() if self.mismatched_draft_identity else candidate.quote_block_id
                ),
                stance=(
                    Stance.OPPOSING
                    if self.mismatched_draft_identity and candidate.stance is Stance.SUPPORTING
                    else candidate.stance
                ),
                draft_statement=(
                    "Schools reported higher completion rates compared with baseline classes."
                    if candidate.stance is Stance.SUPPORTING
                    else (
                        "Surveyed families reported a 20% decline in student satisfaction "
                        "after the fixture rollout."
                    )
                ),
                claim_fit=1 if self.mismatched_draft_identity else 4,
                analyst_prompt_version=(
                    "wrong-prompt" if self.mismatched_draft_identity else "phase8-analyst-v2"
                ),
                analyst_model_name="wrong-model" if self.mismatched_draft_identity else alias,
                drafted_at=NOW,
            ).model_dump(mode="json")
        if name == "ReviewerDecision":
            item = ReviewerInput.model_validate(payload)
            return ReviewerDecision(
                reviewed_statement=item.draft_statement,
                approved=True,
                rationale="Mocked independent approval.",
            ).model_dump(mode="json")
        item = SynthesizerLLMInput.model_validate(payload)
        return build_synthesis_output(
            run_id=item.run_id,
            ledger_records=item.ledger_records,
            created_at=NOW,
            synthesizer_prompt_version="phase8-synthesizer-v2",
            synthesizer_model_name=alias,
        ).model_dump(mode="json")

    @staticmethod
    def _completion(
        request: httpx.Request,
        model: str,
        content: str,
        *,
        usage: bool,
    ) -> httpx.Response:
        body: dict[str, object] = {
            "id": "mock-response",
            "model": model,
            "provider": "mock-upstream",
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        }
        if usage:
            body["usage"] = {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0001,
            }
        return MockProviderHTTP._json(request, body)

    @staticmethod
    def _json(
        request: httpx.Request,
        body: object,
        status: int = 200,
    ) -> httpx.Response:
        return httpx.Response(status, json=body, request=request)


def _stage_input(prompt: str) -> dict[str, object]:
    value = prompt.split("<APPLICATION_CONTROLLED_STAGE_INPUT>\n", maxsplit=1)[1]
    value = value.split("\n</APPLICATION_CONTROLLED_STAGE_INPUT>", maxsplit=1)[0]
    return json.loads(value)


def _config(
    *, ceilings: RunCeilings | None = None, revision: str = "test-revision"
) -> ProviderFactoryConfig:
    return ProviderFactoryConfig(
        openrouter=OpenRouterConfig(api_key="mock-secret"),
        ceilings=ceilings or RunCeilings(),
        repository_revision=revision,
    )


def _clients(mock: MockProviderHTTP) -> ProviderFactoryClients:
    transport = httpx.MockTransport(mock)
    return ProviderFactoryClients(
        search=httpx.Client(
            transport=transport,
            base_url="http://127.0.0.1:8000",
        ),
        source=httpx.Client(transport=transport, follow_redirects=True),
        acquisition=httpx.Client(
            transport=transport,
            base_url="http://127.0.0.1:8000",
        ),
        llm=httpx.Client(
            transport=transport,
            base_url="https://openrouter.ai/api/v1",
        ),
        health_verified=True,
        host_resolver=lambda hostname: ("93.184.216.34",),
    )


def _run(
    tmp_path: Path,
    mock: MockProviderHTTP,
    *,
    run_id: UUID = RUN_ID,
    config: ProviderFactoryConfig | None = None,
) -> ProviderPipelineResult:
    return run_mvp3a_pipeline(
        CLAIM,
        db_path=tmp_path / "mvp3a.sqlite3",
        factory_config=config or _config(),
        clients=_clients(mock),
        run_id=run_id,
        clock=lambda: NOW,
    )


def _mimo_config() -> MimoProviderFactoryConfig:
    return MimoProviderFactoryConfig(
        exa=ExaConfig(api_key="mock-exa-secret"),
        mimo=MimoConfig(api_key="mock-mimo-secret"),
        repository_revision="direct-mimo-test-revision",
    )


def _mimo_clients(mock: MockProviderHTTP) -> ProviderFactoryClients:
    clients = _clients(mock)
    return clients.model_copy(
        update={
            "llm": httpx.Client(
                transport=httpx.MockTransport(mock),
                base_url="https://api.xiaomimimo.com/v1",
            )
        }
    )


def test_mocked_full_direct_mimo_pipeline_releases_without_fallback(
    tmp_path: Path,
) -> None:
    mock = MockProviderHTTP(
        mismatched_draft_identity=True,
        invalid_synthesis_template=True,
    )
    result = run_mvp3b_pipeline(
        CLAIM,
        db_path=tmp_path / "mvp3b.sqlite3",
        factory_config=_mimo_config(),
        clients=_mimo_clients(mock),
        run_id=RUN_ID,
        clock=lambda: NOW,
    )

    assert result.status is ProviderRunStatus.RELEASED
    assert result.rendered_brief_hash
    assert result.retrieval_attempts_used == 18
    assert all(attempt.model_alias == ModelAlias.MIMO_V25_PRO for attempt in result.model_attempts)
    assert all(attempt.route_index == 0 for attempt in result.model_attempts)
    assert result.analysis_result is not None
    assert all(
        draft.statement_draft_id == uuid5(NAMESPACE_URL, f"phase9-draft::{draft.quote_block_id}::0")
        for draft in result.analysis_result.statement_drafts
    )
    contract = read_provider_run_contract(result.db_path, result.run_id)
    assert "xiaomi-mimo:https://api.xiaomimimo.com/v1" in contract.provider_identity
    assert contract.model_identity == "mimo-v2.5-pro"
    reopened = inspect_provider_run(result.db_path, result.run_id)
    assert reopened.final_brief == result.final_brief
    assert reopened.rendered_brief_hash == result.rendered_brief_hash


def test_provider_fingerprints_include_only_the_mvp6_4_live_evidence_policy() -> None:
    openrouter_bundle = build_provider_bundle(
        _config(),
        clients=_clients(MockProviderHTTP()),
    )
    mimo_bundle = build_mimo_provider_bundle(
        _mimo_config(),
        clients=_mimo_clients(MockProviderHTTP()),
    )
    openrouter_payload = json.loads(openrouter_bundle.fingerprint_payload_json)
    mimo_payload = json.loads(mimo_bundle.fingerprint_payload_json)

    assert EVIDENCE_POLICY_VERSION == "mvp6.4-evidence-density-50-75-v1"
    assert FINGERPRINT_VERSION == "mvp6.8-persistence-accounting-integrity-v1"
    assert MIMO_FINGERPRINT_VERSION == "mvp6.8-persistence-accounting-integrity-v1"
    assert EVIDENCE_POLICY_VERSION in openrouter_payload["policy_identity"]
    assert EVIDENCE_POLICY_VERSION in mimo_payload["policy_identity"]
    assert "post-mvp5-bounded-inference-v2" not in openrouter_payload["policy_identity"]
    assert "post-mvp5-bounded-inference-v2" not in mimo_payload["policy_identity"]


def test_mocked_full_approved_provider_pipeline_releases_and_persists_identity(
    tmp_path: Path,
) -> None:
    mock = MockProviderHTTP()
    result = _run(tmp_path, mock)

    assert result.status is ProviderRunStatus.RELEASED
    assert len(mock.search_threads) == 2
    assert result.retrieval_attempts_used == 18
    assert result.researcher_result is not None
    assert len(result.researcher_result.supporting.retrieval_batch.snapshots) == 9
    assert len(result.researcher_result.opposing.retrieval_batch.snapshots) == 9
    retrieved = [
        outcome
        for side in (
            result.researcher_result.supporting,
            result.researcher_result.opposing,
        )
        for outcome in side.retrieval_batch.outcomes
        if outcome.snapshot_id is not None
    ]
    assert all(outcome.provider_name == "wigolo" for outcome in retrieved)
    assert all(outcome.provider_version == "0.2.1" for outcome in retrieved)
    assert all(outcome.normalization_version == "ra-normalization-v1" for outcome in retrieved)
    assert all(
        outcome.acquisition_version == "mvp6.3-public-acquisition-v2" for outcome in retrieved
    )
    assert all(
        json.loads(request.content)["max_results"] == 5
        for request in mock.requests
        if request.url.path == "/v1/search"
    )
    assert result.model_attempts
    assert all(item.reserved_tokens and item.reserved_cost_usd for item in result.model_attempts)
    assert all(item.usage is not None for item in result.model_attempts)
    contract = read_provider_run_contract(result.db_path, result.run_id)
    assert contract.fingerprint_sha256
    assert "wigolo:0.2.1" in contract.provider_identity
    assert "ra-normalization-v1" in contract.normalization_identity
    assert result.final_brief == inspect_provider_run(result.db_path, result.run_id).final_brief
    assert len({item.snapshot_sha256 for item in result.analysis_result.ledger_records}) == 18


def test_mocked_primary_retry_then_only_approved_fallback_releases(tmp_path: Path) -> None:
    mock = MockProviderHTTP(malformed_primary_planner=2)
    result = _run(tmp_path, mock)
    planner = [item for item in result.model_attempts if item.stage == "planner"]

    assert result.status is ProviderRunStatus.RELEASED
    assert [item.model_alias for item in planner] == [
        ModelAlias.MIMO_V25_PRO.value,
        ModelAlias.MIMO_V25_PRO.value,
        ModelAlias.MINIMAX_M3.value,
    ]
    assert all(item.usage is not None for item in planner)


def test_mocked_deterministic_validation_block_is_terminal_and_idempotent(
    tmp_path: Path,
) -> None:
    mock = MockProviderHTTP(invalidate_synthesis=True)
    first = _run(tmp_path, mock)
    calls = len(mock.requests)
    second = _run(tmp_path, mock)

    assert first.status is ProviderRunStatus.BLOCKED
    assert second == first
    assert len(mock.requests) == calls
    assert first.rendered_brief_hash is None


@pytest.mark.parametrize(
    ("status", "failure_code"),
    [
        (401, "authentication_failure"),
        (422, "permanent_request_failure"),
    ],
)
def test_permanent_provider_failures_are_normalized_without_fallback(
    tmp_path: Path,
    status: int,
    failure_code: str,
) -> None:
    result = _run(tmp_path, MockProviderHTTP(planner_status=status))
    planner = [item for item in result.model_attempts if item.stage == "planner"]

    assert result.status is ProviderRunStatus.FAILED
    assert len(planner) == 1
    assert planner[0].failure_code == failure_code
    assert "mock-secret" not in result.failure_reason


def test_budget_exhaustion_prevents_physical_call_and_fallback(tmp_path: Path) -> None:
    mock = MockProviderHTTP()
    tiny = RunCeilings(max_cost_usd="0.000001", max_tokens=1_000_000, max_llm_calls=160)
    result = _run(tmp_path, mock, config=_config(ceilings=tiny))

    assert result.status is ProviderRunStatus.FAILED
    assert not any(request.url.path.endswith("/chat/completions") for request in mock.requests)
    assert "cannot reserve" in result.failure_reason


def test_token_exhaustion_prevents_physical_call(tmp_path: Path) -> None:
    mock = MockProviderHTTP()
    tiny = RunCeilings(max_cost_usd="1.00", max_tokens=100, max_llm_calls=160)
    result = _run(tmp_path, mock, config=_config(ceilings=tiny))

    assert result.status is ProviderRunStatus.FAILED
    assert not any(request.url.path.endswith("/chat/completions") for request in mock.requests)
    assert "token budget" in result.failure_reason


def test_unknown_usage_reservation_prevents_retry_from_bypassing_budget(tmp_path: Path) -> None:
    mock = MockProviderHTTP(planner_status=500)
    one_call_only = RunCeilings(max_cost_usd="0.20", max_tokens=10_000, max_llm_calls=160)
    result = _run(tmp_path, mock, config=_config(ceilings=one_call_only))
    planner = [item for item in result.model_attempts if item.stage == "planner"]

    assert result.status is ProviderRunStatus.FAILED
    assert len(planner) == 1
    assert planner[0].usage is None
    assert planner[0].reserved_tokens is not None
    assert planner[0].reserved_cost_usd is not None
    assert "cannot reserve the next call" in result.failure_reason


def test_fallback_exhaustion_retains_usage_for_all_four_physical_calls(
    tmp_path: Path,
) -> None:
    mock = MockProviderHTTP(
        malformed_primary_planner=2,
        malformed_fallback_planner=2,
    )
    result = _run(tmp_path, mock)
    planner = [item for item in result.model_attempts if item.stage == "planner"]

    assert result.status is ProviderRunStatus.FAILED
    assert len(planner) == 4
    assert all(item.failure_code == "malformed_output" for item in planner)
    assert all(item.usage is not None for item in planner)


@pytest.mark.parametrize(
    ("mock", "expected_code"),
    [
        (MockProviderHTTP(malformed_search=True), "malformed_success_response"),
        (MockProviderHTTP(source_status=403), "authentication_failure"),
        (MockProviderHTTP(unsupported_source=True), "no_passing_candidates"),
    ],
)
def test_search_and_acquisition_failures_are_explicit_and_network_free(
    tmp_path: Path,
    mock: MockProviderHTTP,
    expected_code: str,
) -> None:
    result = _run(tmp_path, mock)

    assert result.status is ProviderRunStatus.FAILED
    assert result.rendered_brief_hash is None
    assert expected_code in result.failure_reason


def test_exact_restart_reuses_checkpoints_and_changed_fingerprint_is_rejected(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mvp3a.sqlite3"
    first_mock = MockProviderHTTP()
    first = _run(tmp_path, first_mock)
    second_mock = MockProviderHTTP()
    second = _run(tmp_path, second_mock)

    assert second == first
    assert second_mock.requests == []
    with pytest.raises(ValueError, match="fingerprint"):
        run_mvp3a_pipeline(
            CLAIM,
            db_path=db_path,
            factory_config=_config(revision="changed-revision"),
            clients=_clients(MockProviderHTTP()),
            run_id=RUN_ID,
            clock=lambda: NOW,
        )
    with pytest.raises(ValueError, match="raw claim"):
        run_mvp3a_pipeline(
            "A changed claim.",
            db_path=db_path,
            factory_config=_config(),
            clients=_clients(MockProviderHTTP()),
            run_id=RUN_ID,
            clock=lambda: NOW,
        )
    assert read_run(str(db_path), RUN_ID).status.value == "completed"


def test_persisted_contract_tampering_blocks_resume_before_provider_work(tmp_path: Path) -> None:
    first = _run(tmp_path, MockProviderHTTP())
    assert first.status is ProviderRunStatus.RELEASED
    with sqlite3.connect(first.db_path) as connection:
        connection.execute(
            "UPDATE provider_run_contracts SET fingerprint_sha256 = ? WHERE run_id = ?",
            ("0" * 64, str(first.run_id)),
        )
    resumed_provider = MockProviderHTTP()

    with pytest.raises(ValidationError, match="fingerprint_sha256"):
        _run(tmp_path, resumed_provider)
    assert resumed_provider.requests == []


def test_75_75_policy_fingerprint_cannot_resume_as_mvp6_4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "providers.factory.EVIDENCE_POLICY_VERSION",
        "post-mvp5-bounded-inference-v2",
    )
    first = _run(tmp_path, MockProviderHTTP())
    assert first.status is ProviderRunStatus.RELEASED

    monkeypatch.setattr(
        "providers.factory.EVIDENCE_POLICY_VERSION",
        EVIDENCE_POLICY_VERSION,
    )
    with pytest.raises(ValueError, match="fingerprint"):
        _run(tmp_path, MockProviderHTTP())


def test_cancellation_after_active_call_persists_attempt_and_starts_no_new_call(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mvp3a.sqlite3"

    def cancel() -> None:
        request_run_cancellation(db_path, RUN_ID, reason="stop after active call", requested_at=NOW)

    mock = MockProviderHTTP(on_planner_response=cancel)
    result = _run(tmp_path, mock)

    assert result.status is ProviderRunStatus.CANCELLED
    assert result.failure_reason == "stop after active call"
    assert result.model_calls_used == 1
    assert result.model_attempts[0].status.value == "completed"
    assert not any(request.url.path == "/v1/search" for request in mock.requests)


def test_cancellation_after_search_starts_no_acquisition_or_extractor_call(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mvp3a.sqlite3"
    observed = False

    def cancel() -> None:
        nonlocal observed
        if observed:
            return
        observed = True
        request_run_cancellation(db_path, RUN_ID, reason="stop after search", requested_at=NOW)

    mock = MockProviderHTTP(on_search_response=cancel)
    result = _run(tmp_path, mock)

    assert result.status is ProviderRunStatus.CANCELLED
    assert result.model_calls_used == 1
    assert sum(request.url.host == "research.test" for request in mock.requests) <= 2
    assert mock.calls[("ProvisionalCandidate", "xiaomi/mimo-v2.5-pro")] == 0


def test_factory_rejects_missing_credentials_wrong_routes_and_unknown_pricing() -> None:
    with pytest.raises(ProviderConfigurationError):
        ProviderFactoryConfig.from_environment({}, repository_revision="test")
    with pytest.raises(ValidationError):
        ProviderFactoryConfig(
            openrouter=OpenRouterConfig(
                api_key="secret",
                fallback_model="unapproved/model",
            ),
            repository_revision="test",
        )
    config = _config()
    with pytest.raises(ProviderConfigurationError, match="pricing"):
        build_provider_bundle(config, price_caps={})
    assert "mock-secret" not in repr(config)
    assert "mock-secret" not in str(config)


def test_provider_contract_is_strict_and_secret_free() -> None:
    bundle = build_provider_bundle(_config(), clients=_clients(MockProviderHTTP()))
    contract = bundle.contract(RUN_ID, NOW)

    assert isinstance(contract, ProviderRunContract)
    assert "mock-secret" not in contract.payload_json
    with pytest.raises(ValidationError):
        ProviderRunContract.model_validate({**contract.model_dump(), "extra": True})
