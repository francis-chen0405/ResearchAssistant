from __future__ import annotations

import hashlib
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from pydantic import BaseModel

from agents.analyst import AnalystLLMInput
from agents.planner import PlannerLLMInput
from agents.reviewer import ReviewerDecision, ReviewerInput
from agents.supportingresearcher import ExtractionLLMInput
from agents.synthesizer import SynthesizerLLMInput, build_synthesis_output
from models import (
    REQUIRED_QUERY_EXCLUSIONS,
    AmbiguityRecord,
    ClaimDefinition,
    ModelRouteAttempt,
    ModelUsageMetadata,
    PlannerOutput,
    ProvisionalCandidate,
    ReviewerFailureCode,
    RunStatus,
    ScoreDecision,
    SearchQuery,
    Stance,
    StatementDraft,
)
from orchestrator import (
    OrchestrationBudget,
    PinnedModelSnapshot,
    ProviderOrchestrationConfig,
    ProviderPipelineResult,
    ProviderRunStatus,
    ResearcherSideStatus,
    inspect_provider_run,
    request_run_cancellation,
    run_provider_pipeline,
)
from providers.llm import (
    LLMProviderCapabilities,
    LLMRequest,
    LLMStage,
    ModelAlias,
)
from providers.scraper import (
    ScrapeRequest,
    ScrapeResponse,
    ScraperProviderError,
)
from providers.search import SearchRequest, SearchResponse, SearchResult
from store import read_run

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
RUN_ID = UUID("90000000-0000-0000-0000-000000000001")
EXCLUSIONS = " ".join(REQUIRED_QUERY_EXCLUSIONS)

SUPPORT_TEXT = (
    "District report introduces the fixture policy evaluation. "
    "policy evidence shows 50% growth in student outcomes across a controlled fixture "
    "cohort because schools reported higher completion rates compared with baseline "
    "classes, and the authors state the improvement was consistent across participating "
    "campuses during the measured term while noting implementation quality remained "
    "important for interpreting the observed gains overall. "
    "The report cautions that longer follow-up would improve confidence."
)
OPPOSE_TEXT = (
    "Independent evaluator describes implementation costs. "
    "policy evidence shows a 20% decline in student satisfaction among surveyed families "
    "after the fixture rollout, and administrators reported that average workload increased "
    "across pilot schools, which the evaluator linked to training demands, schedule "
    "disruptions, and limited support during the first semester of implementation in "
    "participating districts overall that year. "
    "The evaluator states that later adjustments reduced some burden."
)
SUPPORT_QUOTE = (
    '[District report introduces the fixture policy evaluation.] "policy evidence shows '
    "50% growth in student outcomes across a controlled fixture cohort because schools "
    "reported higher completion rates compared with baseline classes, and the authors state "
    "the improvement was consistent across participating campuses during the measured term "
    "while noting implementation quality remained important for interpreting the observed "
    'gains overall." [The report cautions that longer follow-up would improve confidence.]'
)
OPPOSE_QUOTE = (
    '[Independent evaluator describes implementation costs.] "policy evidence shows a 20% '
    "decline in student satisfaction among surveyed families after the fixture rollout, and "
    "administrators reported that average workload increased across pilot schools, which the "
    "evaluator linked to training demands, schedule disruptions, and limited support during "
    'the first semester of implementation in participating districts overall that year." '
    "[The evaluator states that later adjustments reduced some burden.]"
)


class FakeSearchProvider:
    def __init__(self, *, fail_side: str | None = None) -> None:
        self.fail_side = fail_side
        self.requests: list[SearchRequest] = []
        self.thread_names: set[str] = set()
        self._lock = threading.Lock()

    def search(self, request: SearchRequest) -> SearchResponse:
        side = "supporting" if request.query_text.startswith("supporting") else "opposing"
        if self.fail_side in {side, "both"}:
            raise RuntimeError(f"{side} search unavailable")
        query_round = int(request.query_text.split()[2])
        with self._lock:
            self.requests.append(request)
            self.thread_names.add(threading.current_thread().name)
        return SearchResponse(
            results=[
                SearchResult(
                    original_url=f"https://research.test/{side}/{query_round}/{rank}",
                    title=f"{side} result {rank}",
                )
                for rank in range(1, 4)
            ]
        )


class FakeScraperProvider:
    def __init__(self, *, fail_url: str | None = None) -> None:
        self.fail_url = fail_url
        self.requests: list[ScrapeRequest] = []
        self._lock = threading.Lock()

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        with self._lock:
            self.requests.append(request)
        if self.fail_url is not None and self.fail_url in request.url:
            raise ScraperProviderError(f"scrape failed for {request.url}")
        side = "supporting" if "/supporting/" in request.url else "opposing"
        return ScrapeResponse(
            resolved_url=request.url.replace("research.test", "resolved.test"),
            content_type="text/html; charset=utf-8",
            text=SUPPORT_TEXT if side == "supporting" else OPPOSE_TEXT,
        )


class FakeLLMProvider:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(
        self,
        *,
        transient_failures: dict[tuple[LLMStage, ModelAlias], int] | None = None,
        malformed_failures: dict[tuple[LLMStage, ModelAlias], int] | None = None,
        invalid_extractor_aliases: set[ModelAlias] | None = None,
        reject_reviewer_attempts: int = 0,
        invalidate_synthesis: bool = False,
        usage: ModelUsageMetadata | None = None,
    ) -> None:
        self.transient_failures = transient_failures or {}
        self.malformed_failures = malformed_failures or {}
        self.invalid_extractor_aliases = invalid_extractor_aliases or set()
        self.reject_reviewer_attempts = reject_reviewer_attempts
        self.invalidate_synthesis = invalidate_synthesis
        self.usage = usage
        self.requests: list[LLMRequest] = []
        self.calls: defaultdict[tuple[LLMStage, ModelAlias], int] = defaultdict(int)
        self.draft_counts: defaultdict[UUID, int] = defaultdict(int)
        self.review_counts: defaultdict[UUID, int] = defaultdict(int)
        self._lock = threading.Lock()

    def generate(self, request: LLMRequest) -> BaseModel:
        key = (request.stage, request.model_alias)
        with self._lock:
            call_number = self.calls[key]
            self.calls[key] += 1
            self.requests.append(request)
        if call_number < self.transient_failures.get(key, 0):
            raise RuntimeError(f"transient {request.stage.value} failure")
        if call_number < self.malformed_failures.get(key, 0):
            return {"malformed": True}  # type: ignore[return-value]
        if request.stage is LLMStage.PLANNER:
            return self._planner(request)
        if request.stage is LLMStage.EXTRACTOR:
            return self._extractor(request)
        if request.stage is LLMStage.ANALYST:
            return self._analyst(request)
        if request.stage is LLMStage.REVIEWER:
            return self._reviewer(request)
        return self._synthesizer(request)

    def usage_for(
        self,
        request: LLMRequest,
        output: BaseModel,
        invocation_record: object,
    ) -> ModelUsageMetadata | None:
        del request, output, invocation_record
        return self.usage

    def _planner(self, request: LLMRequest) -> PlannerOutput:
        planner_input = request.input_artifact
        assert isinstance(planner_input, PlannerLLMInput)
        queries = []
        for stance in (Stance.SUPPORTING, Stance.OPPOSING):
            for query_round in range(1, 4):
                queries.append(
                    SearchQuery(
                        run_id=request.run_id,
                        query_id=uuid5(
                            NAMESPACE_URL,
                            f"phase9-query::{request.run_id}::{stance.value}::{query_round}",
                        ),
                        stance=stance,
                        query_round=query_round,
                        strategy=f"{stance.value} strategy {query_round}",
                        query_text=f"{stance.value} query {query_round}",
                        exclusion_parameters=EXCLUSIONS,
                        created_at=NOW,
                    )
                )
        return PlannerOutput(
            run_id=request.run_id,
            claim_definition=ClaimDefinition(
                run_id=request.run_id,
                claim_text=planner_input.raw_claim,
                population="student outcomes",
                jurisdiction="test jurisdiction",
                time_period="test term",
                comparison_baseline="baseline classes",
                intervention_or_exposure="fixture policy",
                causal_or_comparative_meaning="comparative improvement",
                created_at=NOW,
            ),
            ambiguities=[
                AmbiguityRecord(
                    run_id=request.run_id,
                    ambiguity_id=uuid5(NAMESPACE_URL, f"phase9-ambiguity::{request.run_id}"),
                    description="Test scope.",
                    impact="The test uses offline sources.",
                    created_at=NOW,
                )
            ],
            search_queries=queries,
            planner_prompt_version=request.prompt.version,
            planner_model_name=request.model_alias.value,
            planned_at=NOW,
        )

    def _extractor(self, request: LLMRequest) -> ProvisionalCandidate:
        extraction_input = request.input_artifact
        assert isinstance(extraction_input, ExtractionLLMInput)
        assert extraction_input.retrieval is not None
        retrieval = extraction_input.retrieval
        quote = SUPPORT_QUOTE if extraction_input.stance is Stance.SUPPORTING else OPPOSE_QUOTE
        if request.model_alias in self.invalid_extractor_aliases:
            quote = '[Start of Text] "This quote is not in the snapshot." [End of Text]'
        return ProvisionalCandidate(
            run_id=request.run_id,
            stance=extraction_input.stance,
            source_url=retrieval.resolved_url,
            retrieval_attempt_id=retrieval.retrieval_attempt_id,
            query_id=retrieval.query_id,
            query_round=retrieval.query_round,
            search_rank=retrieval.search_rank,
            snapshot_id=extraction_input.source.snapshot_id,
            snapshot_sha256=extraction_input.source.snapshot_sha256,
            extracted_quote_block=quote,
            extraction_prompt_version=request.prompt.version,
            extraction_model_name=request.model_alias.value,
            extracted_at=NOW,
        )

    def _analyst(self, request: LLMRequest) -> BaseModel:
        analyst_input = request.input_artifact
        assert isinstance(analyst_input, AnalystLLMInput)
        candidate = analyst_input.candidate
        if request.requested_output_type is ScoreDecision:
            evidence_quality = 5 if candidate.stance is Stance.SUPPORTING else 4
            claim_fit = 5 if candidate.stance is Stance.SUPPORTING else 4
            return ScoreDecision(
                run_id=request.run_id,
                quote_block_id=candidate.quote_block_id,
                evidence_quality=evidence_quality,
                claim_fit=claim_fit,
                ledger_score=5 if candidate.stance is Stance.SUPPORTING else 4,
                placement="primary" if candidate.stance is Stance.SUPPORTING else "secondary",
                approved=True,
                rationale="Offline fake Analyst decision.",
                analyst_prompt_version=request.prompt.version,
                analyst_model_name=request.model_alias.value,
                scored_at=NOW,
            )
        with self._lock:
            draft_index = self.draft_counts[candidate.quote_block_id]
            self.draft_counts[candidate.quote_block_id] += 1
        statement = (
            "Schools reported higher completion rates compared with baseline classes."
            if candidate.stance is Stance.SUPPORTING
            else (
                "Surveyed families reported a 20% decline in student satisfaction after "
                "the fixture rollout."
            )
        )
        return StatementDraft(
            run_id=request.run_id,
            statement_draft_id=uuid5(
                NAMESPACE_URL,
                f"phase9-draft::{candidate.quote_block_id}::{draft_index}",
            ),
            quote_block_id=candidate.quote_block_id,
            stance=candidate.stance,
            draft_statement=statement,
            claim_fit=5 if candidate.stance is Stance.SUPPORTING else 4,
            analyst_prompt_version=request.prompt.version,
            analyst_model_name=request.model_alias.value,
            drafted_at=NOW,
        )

    def _reviewer(self, request: LLMRequest) -> ReviewerDecision:
        reviewer_input = request.input_artifact
        assert isinstance(reviewer_input, ReviewerInput)
        _, quote_block_id = request.input_artifact_ids
        with self._lock:
            review_index = self.review_counts[quote_block_id]
            self.review_counts[quote_block_id] += 1
        rejected = review_index < self.reject_reviewer_attempts
        if rejected:
            return ReviewerDecision(
                reviewed_statement=reviewer_input.draft_statement,
                approved=False,
                failure_code=ReviewerFailureCode.MISSING_QUALIFICATION,
                rationale="Fake Reviewer rejection.",
            )
        return ReviewerDecision(
            reviewed_statement=reviewer_input.draft_statement,
            approved=True,
            rationale="Fake Reviewer approval.",
        )

    def _synthesizer(self, request: LLMRequest) -> BaseModel:
        synthesis_input = request.input_artifact
        assert isinstance(synthesis_input, SynthesizerLLMInput)
        synthesis = build_synthesis_output(
            run_id=request.run_id,
            ledger_records=synthesis_input.ledger_records,
            created_at=NOW,
            synthesizer_prompt_version=request.prompt.version,
            synthesizer_model_name=request.model_alias.value,
        )
        if not self.invalidate_synthesis:
            return synthesis
        payload = synthesis.model_dump(mode="python")
        payload["sections"][0]["items"][0]["approved_factual_statement"] += " Altered."
        return type(synthesis).model_validate(payload)


def _run(
    tmp_path: Path,
    *,
    llm: FakeLLMProvider | None = None,
    search: FakeSearchProvider | None = None,
    scraper: FakeScraperProvider | None = None,
    config: ProviderOrchestrationConfig | None = None,
    run_id: UUID = RUN_ID,
    stage_hook: Callable[[UUID, str], None] | None = None,
) -> ProviderPipelineResult:
    return run_provider_pipeline(
        "The fixture policy improves student outcomes.",
        db_path=tmp_path / "phase9.sqlite3",
        search_provider=search or FakeSearchProvider(),
        scraper_provider=scraper or FakeScraperProvider(),
        llm_provider=llm or FakeLLMProvider(),
        run_id=run_id,
        config=config,
        clock=lambda: NOW,
        stage_hook=stage_hook,
    )


def test_successful_full_orchestration_releases_with_explicit_status(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.status is ProviderRunStatus.RELEASED
    assert result.validation_result is not None and result.validation_result.valid
    assert result.final_brief is not None
    assert result.rendered_brief_hash is not None
    assert (
        result.rendered_brief_hash == hashlib.sha256(result.final_brief.encode("utf-8")).hexdigest()
    )
    assert result.researcher_result is not None
    assert result.researcher_result.supporting.status is ResearcherSideStatus.COMPLETED
    assert result.researcher_result.opposing.status is ResearcherSideStatus.COMPLETED
    assert result.retrieval_attempts_used == 18
    assert len(result.analysis_result.ledger_records) == 2
    assert all(
        isinstance(record.reviewer_approval_id, str)
        and record.reviewer_approval_id.startswith("rappr_v1_")
        for record in result.analysis_result.ledger_records
    )
    assert read_run(result.db_path, result.run_id).status is RunStatus.COMPLETED


def test_researchers_use_at_most_two_workers_and_equal_limits(tmp_path: Path) -> None:
    search = FakeSearchProvider()
    result = _run(tmp_path, search=search)

    assert result.status is ProviderRunStatus.RELEASED
    assert len(search.thread_names) == 2
    assert all(request.limit == 3 for request in search.requests)
    assert sum("supporting" in request.query_text for request in search.requests) == 3
    assert sum("opposing" in request.query_text for request in search.requests) == 3


def test_one_researcher_failure_is_explicit_and_other_side_continues(tmp_path: Path) -> None:
    result = _run(tmp_path, search=FakeSearchProvider(fail_side="opposing"))

    assert result.status is ProviderRunStatus.RELEASED
    assert result.researcher_result.opposing.status is ResearcherSideStatus.FAILED
    assert result.researcher_result.opposing.failures
    assert len(result.analysis_result.ledger_records) == 1


def test_both_researcher_failures_end_in_clean_failed_state(tmp_path: Path) -> None:
    result = _run(tmp_path, search=FakeSearchProvider(fail_side="both"))

    assert result.status is ProviderRunStatus.FAILED
    assert "both Researcher sides failed" in result.failure_reason
    assert result.rendered_brief_hash is None
    assert read_run(result.db_path, result.run_id).status is RunStatus.FAILED


def test_partial_retrieval_success_is_preserved(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        scraper=FakeScraperProvider(fail_url="/supporting/2/2"),
    )

    assert result.status is ProviderRunStatus.RELEASED
    assert result.researcher_result.supporting.status is ResearcherSideStatus.PARTIAL
    assert result.retrieval_attempts_used == 18


def test_validator_rejection_blocks_release_without_hash(tmp_path: Path) -> None:
    result = _run(tmp_path, llm=FakeLLMProvider(invalidate_synthesis=True))

    assert result.status is ProviderRunStatus.BLOCKED
    assert result.validation_result is not None and not result.validation_result.valid
    assert result.final_brief is None
    assert result.rendered_brief_hash is None
    assert read_run(result.db_path, result.run_id).status is RunStatus.BLOCKED


def test_extraction_failure_is_explicit_and_has_no_ledger(tmp_path: Path) -> None:
    failures = {
        (LLMStage.EXTRACTOR, ModelAlias.MIMO_V25): 99,
        (LLMStage.EXTRACTOR, ModelAlias.MIMO_V25_PRO): 99,
        (LLMStage.EXTRACTOR, ModelAlias.DEEPSEEK_V4_FLASH): 99,
    }
    result = _run(tmp_path, llm=FakeLLMProvider(transient_failures=failures))

    assert result.status is ProviderRunStatus.FAILED
    assert result.analysis_result is None
    assert result.rendered_brief_hash is None
    assert (
        all(
            side.status is ResearcherSideStatus.FAILED
            for side in (result.researcher_result.supporting, result.researcher_result.opposing)
        )
        if result.researcher_result
        else True
    )


def test_analyst_failure_ends_run_without_bypassing_ledger(tmp_path: Path) -> None:
    failures = {
        (LLMStage.ANALYST, ModelAlias.MIMO_V25_PRO): 99,
        (LLMStage.ANALYST, ModelAlias.MIMO_V25): 99,
        (LLMStage.ANALYST, ModelAlias.DEEPSEEK_V4_PRO): 99,
    }
    result = _run(tmp_path, llm=FakeLLMProvider(transient_failures=failures))

    assert result.status is ProviderRunStatus.FAILED
    assert result.analysis_result is None
    assert result.rendered_brief_hash is None
    with sqlite3.connect(result.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ledger_records").fetchone()[0] == 0


def test_reviewer_first_failure_allows_one_revision_then_approval(tmp_path: Path) -> None:
    result = _run(tmp_path, llm=FakeLLMProvider(reject_reviewer_attempts=1))

    assert result.status is ProviderRunStatus.RELEASED
    assert len(result.analysis_result.statement_drafts) == 4
    assert len(result.analysis_result.reviewer_decisions) == 4
    assert len(result.analysis_result.ledger_records) == 2
    assert all(
        len(
            [
                review
                for review in result.analysis_result.reviewer_decisions
                if review.quote_block_id == ledger.quote_block_id
            ]
        )
        == 2
        for ledger in result.analysis_result.ledger_records
    )


def test_reviewer_second_failure_rejects_quote_and_run_fails_cleanly(tmp_path: Path) -> None:
    result = _run(tmp_path, llm=FakeLLMProvider(reject_reviewer_attempts=2))

    assert result.status is ProviderRunStatus.FAILED
    assert result.rendered_brief_hash is None
    with sqlite3.connect(result.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ledger_records").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM statement_review_attempts").fetchone()[0] == 4
        )


def test_primary_transient_failure_retries_same_alias_before_fallback(tmp_path: Path) -> None:
    llm = FakeLLMProvider(transient_failures={(LLMStage.PLANNER, ModelAlias.MIMO_V25_PRO): 1})
    result = _run(tmp_path, llm=llm)
    planner_attempts = [item for item in result.model_attempts if item.stage == "planner"]

    assert result.status is ProviderRunStatus.RELEASED
    assert [item.model_alias for item in planner_attempts] == [
        ModelAlias.MIMO_V25_PRO.value,
        ModelAlias.MIMO_V25_PRO.value,
    ]
    assert planner_attempts[1].retry_reason is not None
    assert planner_attempts[1].escalation_reason is None


def test_malformed_primary_output_retries_then_records_fallback(tmp_path: Path) -> None:
    llm = FakeLLMProvider(malformed_failures={(LLMStage.PLANNER, ModelAlias.MIMO_V25_PRO): 2})
    result = _run(tmp_path, llm=llm)
    planner_attempts = [item for item in result.model_attempts if item.stage == "planner"]

    assert result.status is ProviderRunStatus.RELEASED
    assert [item.model_alias for item in planner_attempts] == [
        ModelAlias.MIMO_V25_PRO.value,
        ModelAlias.MIMO_V25_PRO.value,
        ModelAlias.MIMO_V25.value,
    ]
    assert planner_attempts[0].failure_code == "malformed_output"
    assert planner_attempts[2].escalation_reason is not None


def test_extractor_exact_quote_failure_objectively_escalates_to_mimo_pro(
    tmp_path: Path,
) -> None:
    llm = FakeLLMProvider(invalid_extractor_aliases={ModelAlias.MIMO_V25})
    result = _run(tmp_path, llm=llm)
    extractor_attempts = [item for item in result.model_attempts if item.stage == "extractor"]

    assert result.status is ProviderRunStatus.RELEASED
    assert any(
        item.model_alias == ModelAlias.MIMO_V25_PRO.value
        and item.escalation_reason is not None
        and "exact_quote_failure" in item.escalation_reason
        for item in extractor_attempts
    )
    assert all(
        attempts[0].model_alias == ModelAlias.MIMO_V25.value
        for attempts in _attempts_by_operation(extractor_attempts).values()
    )


def test_semantic_reviewer_disagreement_does_not_switch_models(tmp_path: Path) -> None:
    result = _run(tmp_path, llm=FakeLLMProvider(reject_reviewer_attempts=1))
    reviewer_attempts = [item for item in result.model_attempts if item.stage == "reviewer"]

    assert result.status is ProviderRunStatus.RELEASED
    assert reviewer_attempts
    assert {item.model_alias for item in reviewer_attempts} == {ModelAlias.MIMO_V25.value}
    assert all(item.route_index == 0 for item in reviewer_attempts)
    assert all(item.escalation_reason is None for item in reviewer_attempts)


def test_deepseek_third_line_output_still_passes_all_truth_gates(tmp_path: Path) -> None:
    failures = {
        (LLMStage.EXTRACTOR, ModelAlias.MIMO_V25): 99,
        (LLMStage.EXTRACTOR, ModelAlias.MIMO_V25_PRO): 99,
    }
    result = _run(tmp_path, llm=FakeLLMProvider(transient_failures=failures))

    assert result.status is ProviderRunStatus.RELEASED
    assert any(
        item.stage == "extractor"
        and item.model_alias == ModelAlias.DEEPSEEK_V4_FLASH.value
        and item.status.value == "completed"
        for item in result.model_attempts
    )
    assert result.researcher_result.supporting.candidates
    assert result.researcher_result.opposing.candidates
    assert result.analysis_result.reviewer_decisions
    assert result.analysis_result.ledger_records
    assert result.validation_result.valid


def test_invalid_deepseek_extraction_is_blocked_by_deterministic_filter(tmp_path: Path) -> None:
    failures = {
        (LLMStage.EXTRACTOR, ModelAlias.MIMO_V25): 99,
        (LLMStage.EXTRACTOR, ModelAlias.MIMO_V25_PRO): 99,
    }
    llm = FakeLLMProvider(
        transient_failures=failures,
        invalid_extractor_aliases={ModelAlias.DEEPSEEK_V4_FLASH},
    )
    result = _run(tmp_path, llm=llm)

    assert result.status is ProviderRunStatus.FAILED
    assert result.rendered_brief_hash is None
    with sqlite3.connect(result.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ledger_records").fetchone()[0] == 0


def test_restart_after_failure_reuses_completed_attempts_and_finishes(tmp_path: Path) -> None:
    def fail_after_planner(run_id: UUID, stage_key: str) -> None:
        del run_id
        if stage_key == "planner":
            raise RuntimeError("injected boundary failure")

    first_llm = FakeLLMProvider()
    first = _run(tmp_path, llm=first_llm, stage_hook=fail_after_planner)
    assert first.status is ProviderRunStatus.FAILED
    first_attempt_ids = [item.attempt_id for item in first.model_attempts]

    second_llm = FakeLLMProvider()
    second = _run(tmp_path, llm=second_llm)

    assert second.status is ProviderRunStatus.RELEASED
    assert set(first_attempt_ids).issubset({item.attempt_id for item in second.model_attempts})
    assert not any(request.stage is LLMStage.PLANNER for request in second_llm.requests)


def test_duplicate_retry_and_terminal_rerun_create_no_duplicate_artifacts(
    tmp_path: Path,
) -> None:
    llm = FakeLLMProvider(transient_failures={(LLMStage.PLANNER, ModelAlias.MIMO_V25_PRO): 1})
    first = _run(tmp_path, llm=llm)
    call_count = len(llm.requests)
    second = _run(tmp_path, llm=llm)

    assert second.status is ProviderRunStatus.RELEASED
    assert len(llm.requests) == call_count
    assert first.analysis_result is not None and second.analysis_result is not None
    assert [record.reviewer_approval_id for record in first.analysis_result.ledger_records] == [
        record.reviewer_approval_id for record in second.analysis_result.ledger_records
    ]
    with sqlite3.connect(first.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM ledger_records").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM model_route_attempts").fetchone()[0] == len(
            first.model_attempts
        )


def test_restart_after_researchers_does_not_duplicate_snapshots(tmp_path: Path) -> None:
    def fail_after_researchers(run_id: UUID, stage_key: str) -> None:
        del run_id
        if stage_key == "researchers":
            raise RuntimeError("injected post-research failure")

    first_search = FakeSearchProvider()
    first = _run(tmp_path, search=first_search, stage_hook=fail_after_researchers)
    assert first.status is ProviderRunStatus.FAILED
    assert first.researcher_result is not None

    second_search = FakeSearchProvider()
    second = _run(tmp_path, search=second_search)

    assert second.status is ProviderRunStatus.RELEASED
    assert second_search.requests == []
    with sqlite3.connect(second.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM ledger_records").fetchone()[0] == 2


def test_cancellation_is_honored_between_stages_and_has_no_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "phase9.sqlite3"

    def cancel_after_planner(run_id: UUID, stage_key: str) -> None:
        if stage_key == "planner":
            request_run_cancellation(
                db_path,
                run_id,
                reason="stop after planning",
                requested_at=NOW,
            )

    result = _run(tmp_path, stage_hook=cancel_after_planner)

    assert result.status is ProviderRunStatus.CANCELLED
    assert result.failure_reason == "stop after planning"
    assert result.researcher_result is None
    assert result.rendered_brief_hash is None
    assert read_run(result.db_path, result.run_id).status is RunStatus.CANCELLED


def test_database_reopening_preserves_partial_and_attempt_metadata(tmp_path: Path) -> None:
    result = _run(tmp_path)
    reopened = inspect_provider_run(result.db_path, result.run_id)

    assert reopened == result
    assert reopened.model_attempts
    assert all(
        item.ended_at is not None and item.latency_ms is not None
        for item in reopened.model_attempts
    )
    assert all(
        item.model_alias and item.stage and item.attempt_number >= 1
        for item in reopened.model_attempts
    )


def test_worker_threads_never_share_sqlite_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import store

    original_connect = store._connect
    connections_by_thread: defaultdict[str, list[sqlite3.Connection]] = defaultdict(list)
    lock = threading.Lock()

    def traced_connect(db_path: str) -> sqlite3.Connection:
        connection = original_connect(db_path)
        with lock:
            connections_by_thread[threading.current_thread().name].append(connection)
        return connection

    monkeypatch.setattr(store, "_connect", traced_connect)
    result = _run(tmp_path)

    assert result.status is ProviderRunStatus.RELEASED
    worker_connections = {
        thread: values
        for thread, values in connections_by_thread.items()
        if thread.startswith("phase9-researcher")
    }
    assert len(worker_connections) == 2
    worker_sets = [set(map(id, values)) for values in worker_connections.values()]
    assert worker_sets[0].isdisjoint(worker_sets[1])


def test_retrieval_budget_exceeded_fails_before_research(tmp_path: Path) -> None:
    config = ProviderOrchestrationConfig(budget=OrchestrationBudget(retrieval_attempts_per_side=8))
    result = _run(tmp_path, config=config)

    assert result.status is ProviderRunStatus.FAILED
    assert "retrieval budget exceeded" in result.failure_reason
    assert result.retrieval_attempts_used == 0


def test_model_call_budget_exceeded_is_explicit(tmp_path: Path) -> None:
    config = ProviderOrchestrationConfig(budget=OrchestrationBudget(max_model_calls=1))
    result = _run(tmp_path, config=config)

    assert result.status is ProviderRunStatus.FAILED
    assert (
        "model call budget" in result.failure_reason or "both Researcher" in result.failure_reason
    )
    assert result.model_calls_used == 1
    assert result.rendered_brief_hash is None


def test_optional_token_and_cost_metadata_is_recorded(tmp_path: Path) -> None:
    usage = ModelUsageMetadata(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=0.002,
    )
    config = ProviderOrchestrationConfig(
        budget=OrchestrationBudget(max_total_tokens=1_000, max_total_cost_usd=1.0),
        pinned_model_snapshots=(
            PinnedModelSnapshot(
                model_alias=ModelAlias.MIMO_V25_PRO,
                snapshot="mimo-pro-test-snapshot",
            ),
        ),
    )
    result = _run(tmp_path, llm=FakeLLMProvider(usage=usage), config=config)

    assert result.status is ProviderRunStatus.RELEASED
    assert result.total_tokens == result.model_calls_used * 15
    assert result.total_cost_usd == pytest.approx(result.model_calls_used * 0.002)
    planner_attempt = next(item for item in result.model_attempts if item.stage == "planner")
    assert planner_attempt.pinned_model_snapshot == "mimo-pro-test-snapshot"
    assert planner_attempt.usage == usage


def test_usage_metadata_survives_deterministic_route_failure(tmp_path: Path) -> None:
    usage = ModelUsageMetadata(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=0.002,
    )
    llm = FakeLLMProvider(
        invalid_extractor_aliases={ModelAlias.MIMO_V25},
        usage=usage,
    )
    result = _run(tmp_path, llm=llm)
    failed_extractor_attempts = [
        item
        for item in result.model_attempts
        if item.stage == "extractor" and item.status.value == "failed"
    ]

    assert result.status is ProviderRunStatus.RELEASED
    assert failed_extractor_attempts
    assert all(item.failure_code == "exact_quote_failure" for item in failed_extractor_attempts)
    assert all(item.usage == usage for item in failed_extractor_attempts)
    assert result.total_tokens == result.model_calls_used * usage.total_tokens
    assert result.total_cost_usd == pytest.approx(result.model_calls_used * usage.cost_usd)


def test_every_tested_run_has_an_explicit_terminal_status(tmp_path: Path) -> None:
    released = _run(tmp_path / "released", run_id=uuid5(NAMESPACE_URL, "released"))
    blocked = _run(
        tmp_path / "blocked",
        run_id=uuid5(NAMESPACE_URL, "blocked"),
        llm=FakeLLMProvider(invalidate_synthesis=True),
    )
    failed = _run(
        tmp_path / "failed",
        run_id=uuid5(NAMESPACE_URL, "failed"),
        search=FakeSearchProvider(fail_side="both"),
    )

    assert {released.status, blocked.status, failed.status} == {
        ProviderRunStatus.RELEASED,
        ProviderRunStatus.BLOCKED,
        ProviderRunStatus.FAILED,
    }
    assert all(item.status is not ProviderRunStatus.RUNNING for item in (released, blocked, failed))


def _attempts_by_operation(
    attempts: Sequence[ModelRouteAttempt],
) -> dict[UUID, list[ModelRouteAttempt]]:
    grouped: defaultdict[UUID, list[ModelRouteAttempt]] = defaultdict(list)
    for attempt in attempts:
        grouped[attempt.operation_id].append(attempt)
    return grouped
