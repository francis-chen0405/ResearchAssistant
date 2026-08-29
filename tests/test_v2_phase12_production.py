from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

import agents.v2_final_output as v2_final_output
import v2_orchestrator
from agents.v2_adaptive_search import (
    V2AdaptiveBudgetState,
    V2AdaptiveRoundStatus,
    V2AdaptiveStopCode,
)
from agents.v2_evidence_admission import V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
from agents.v2_round_four import (
    V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
    V2RoundFourRunResult,
    reconcile_post_round_three_gaps,
)
from frontend.live_service import LiveResearchController, ResearchProgress, _v2_progress_percent
from models import (
    DiscoveryProvider,
    ModelUsageMetadata,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    ScoutItem,
    SelectedSentenceRange,
    Stage,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchProposal,
    V2AdmissionMethod,
    V2ClaimCoverageAssessment,
    V2ClaimCoverageState,
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAnalystModelOutput,
    V2EvidenceRelationship,
    V2FinalResearchOutput,
    V2GapAnalysisModelOutput,
    V2GapAnalysisOutput,
    V2GapSearchDirection,
    V2InitialPlannerModelOutput,
    V2InitialPlannerSearchResponse,
    V2MaterialGap,
    V2PipelineIdentity,
    V2ProviderRunDiagnostics,
    V2RoundFourGovernorDecision,
    V2RoundFourTerminalOutcome,
    V2RunDiagnostics,
    V2SourceSelectionModelOutput,
    V2SourceSelectionRecommendation,
    V2VerbatimQuoteSelection,
)
from orchestrator import request_run_cancellation
from providers.llm import LLMProviderCapabilities, LLMRequest, LLMStage
from providers.scraper import ScrapeRequest, ScrapeResponse
from providers.search import SearchRequest, SearchResponse, SearchResult
from providers.v2_budget import V2BudgetSnapshot, V2PhysicalCallStart, V2RunCeilings
from providers.v2_routing import V2RoutingConfig
from store import (
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_v2_artifact,
)
from v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2_PRODUCTION_FINGERPRINT_KEY,
    V2_PRODUCTION_LEGACY_ARTIFACT_KEY,
    V2ProductionFingerprint,
    V2ProductionPipelineResult,
    V2ProductionState,
    _prepare_identity,
    _production_fingerprint,
    run_v2_production_pipeline,
    v2_cancellation_requested,
)

NOW = datetime(2026, 8, 21, tzinfo=UTC)
QUOTE = (
    "Among 240 surveyed adults in the regional program, 62 percent reported completing "
    "the assigned course within six months, compared with 48 percent of matched adults "
    "receiving the standard materials during the same observation period."
)
SOURCE_TEXT = (
    "The evaluation describes a voluntary regional education program. "
    f"{QUOTE} "
    "The authors note that assignment was not randomized and self-reported completion may "
    "not generalize beyond the participating region."
)


class _Search:
    def __init__(self, *, unique_results: bool = False) -> None:
        self.requests: list[SearchRequest] = []
        self.unique_results = unique_results

    def search(self, request: SearchRequest) -> SearchResponse:
        self.requests.append(request)
        return SearchResponse(
            results=[
                SearchResult(
                    original_url=(
                        f"https://example.test/regional-evaluation-{len(self.requests)}"
                        if self.unique_results
                        else "https://example.test/regional-evaluation"
                    ),
                    title="Regional program evaluation",
                    snippet="A bounded observational comparison.",
                    rank=1,
                )
            ],
            provider_name="phase12-fixture",
            provider_version="v1",
            adapter_version="v1",
        )


class _FailsRoundFourSearch(_Search):
    def search(self, request: SearchRequest) -> SearchResponse:
        if len(self.requests) >= 5:
            raise RuntimeError("fixture Round-4 provider failure")
        return super().search(request)


class _FailsAllRoundFourSearch(_Search):
    def search(self, request: SearchRequest) -> SearchResponse:
        if "round 4" in request.query_text:
            raise RuntimeError("fixture all Round-4 provider failure")
        return super().search(request)


class _FailsSecondRoundFourSearch(_Search):
    def search(self, request: SearchRequest) -> SearchResponse:
        if "round 4" in request.query_text and any(
            "round 4" in prior.query_text for prior in self.requests
        ):
            raise RuntimeError("fixture partial Round-4 provider failure")
        return super().search(request)


class _FailsRoundThreeSearch(_Search):
    def search(self, request: SearchRequest) -> SearchResponse:
        if len(self.requests) >= 4:
            raise RuntimeError("fixture Round-3 provider failure")
        return super().search(request)


class _Scraper:
    def __init__(self) -> None:
        self.requests: list[ScrapeRequest] = []

    def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        self.requests.append(request)
        return ScrapeResponse(
            resolved_url=request.url,
            original_url=request.url,
            content_type="text/plain",
            text=SOURCE_TEXT,
            provider_name="phase12-fixture",
            provider_version="v1",
        )


class _V2Model:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(
        self,
        *,
        completed_rounds: int = 1,
        fail_first_scout: bool = False,
        fail_first_gap: bool = False,
        round_four_query_count: int = 1,
    ) -> None:
        self.requests: list[LLMRequest] = []
        self.completed_rounds = completed_rounds
        self.fail_first_scout = fail_first_scout
        self.fail_first_gap = fail_first_gap
        self.round_four_query_count = round_four_query_count
        self.gap_attempts = 0
        self.scout_attempts = 0
        self.successful_gaps = 0
        self.search_agent_calls = 0

    def generate(self, request: LLMRequest) -> object:
        self.requests.append(request)
        output_name = request.requested_output_type.__name__
        if output_name == "V2InitialPlannerModelOutput":
            return V2InitialPlannerModelOutput(
                scope_interpretations=(),
                searches=tuple(
                    V2InitialPlannerSearchResponse(
                        direction=lane.direction,
                        provider=lane.provider,
                        strategy=lane.strategy,
                        query_text=f"{lane.direction.value} {lane.strategy} regional evidence",
                    )
                    for lane in request.input_artifact.search_lanes
                ),
            )
        if output_name == "ScoutBatch":
            self.scout_attempts += 1
            if self.fail_first_scout and self.scout_attempts == 1:
                raise RuntimeError("mocked transient Scout degradation")
            return ScoutBatch(
                run_id=request.run_id,
                items=tuple(
                    ScoutItem(
                        item_id=item.item_id,
                        decision="retrieve",
                        rationale="The result can provide direct bounded evidence.",
                    )
                    for item in request.input_artifact.candidates
                ),
            )
        if output_name == "V2GapAnalysisModelOutput":
            self.gap_attempts += 1
            if self.fail_first_gap and self.gap_attempts == 1:
                raise RuntimeError("mocked transient Gap degradation")
            self.successful_gaps += 1
            coverage_focus = request.input_artifact.claim_coverage_focus
            coverage_map = tuple(
                V2ClaimCoverageAssessment(
                    dimension=item.dimension,
                    claim_component=item.claim_component,
                    coverage_state=(
                        V2ClaimCoverageState.UNAVAILABLE
                        if not item.searchable
                        else V2ClaimCoverageState.MISSING
                        if self.successful_gaps < self.completed_rounds
                        else V2ClaimCoverageState.COVERED
                    ),
                    evidence_summary="Fixture coverage assessment.",
                    kind=item.kind,
                    searchable=item.searchable,
                    unavailable_reason=item.unavailable_reason,
                )
                for item in coverage_focus
            )
            if self.successful_gaps < self.completed_rounds:
                direction = request.input_artifact.directions.enabled_directions[0]
                focus = coverage_focus[0] if coverage_focus else None
                gap = V2MaterialGap(
                    gap_id=f"gap-round-{self.successful_gaps}",
                    direction=direction,
                    missing_evidence="Independent replication evidence remains missing.",
                    rationale="The current pool contains a material replication gap.",
                    claim_dimension=focus.dimension if focus is not None else None,
                    unsupported_claim_component=(
                        focus.claim_component if focus is not None else None
                    ),
                )
                return V2GapAnalysisModelOutput(
                    coverage_summary="A material replication gap remains.",
                    claim_coverage_map=coverage_map,
                    material_gaps=(gap,),
                    continue_research=True,
                    new_search_directions=(
                        V2GapSearchDirection(
                            gap_id=gap.gap_id,
                            direction=direction,
                            missing_evidence=gap.missing_evidence,
                            search_focus="Independent replication with a distinct instrument",
                            claim_dimension=focus.dimension if focus is not None else None,
                            resolving_evidence_kind=(
                                "independent replication" if focus is not None else None
                            ),
                        ),
                    ),
                    discovered_terms=("replication",),
                )
            return V2GapAnalysisModelOutput(
                coverage_summary="The surviving source is adequate for this bounded run.",
                claim_coverage_map=coverage_map,
                material_gaps=(),
                continue_research=False,
                stop_reason="More searches would duplicate the same source family.",
                new_search_directions=(),
                discovered_terms=("completion",),
            )
        if output_name == "V2AdaptiveSearchModelOutput":
            self.search_agent_calls += 1
            gap = request.input_artifact.material_gaps[0]
            return V2AdaptiveSearchModelOutput(
                searches=tuple(
                    V2AdaptiveSearchProposal(
                        direction=gap.direction,
                        provider=DiscoveryProvider.EXA,
                        targeted_gap_ids=(gap.gap_id,),
                        strategy=(
                            f"replication_round_{request.input_artifact.round_number}_{index}"
                        ),
                        query_text=(
                            f"distinct replication instrument round "
                            f"{request.input_artifact.round_number} outcome variant {index}"
                        ),
                    )
                    for index in range(
                        self.round_four_query_count
                        if request.input_artifact.round_number == 4
                        else 1
                    )
                )
            )
        if output_name == "V2SourceSelectionModelOutput":
            source = request.input_artifact.survivors[0]
            return V2SourceSelectionModelOutput(
                recommendations=(
                    V2SourceSelectionRecommendation(
                        source_id=source.source_id,
                        rationale="Direct, nonredundant empirical coverage.",
                    ),
                )
            )
        if output_name in {"V2VerbatimQuoteSelection", "VerbatimQuoteSelection"}:
            return V2VerbatimQuoteSelection(
                selected_sentence_ranges=(SelectedSentenceRange(start_sentence=2, end_sentence=2),)
            )
        if output_name == "V2EvidenceAnalystModelOutput":
            relationship = (
                V2EvidenceRelationship.SUPPORTS
                if request.input_artifact.direction is ResearchDirection.SUPPORT
                else V2EvidenceRelationship.CHALLENGES
            )
            return V2EvidenceAnalystModelOutput(
                narrowest_supported_proposition=(
                    "Surveyed regional-program adults reported 62% completion versus 48% "
                    "among matched adults receiving standard materials."
                ),
                canonical_factual_statement=(
                    "Among surveyed regional-program adults, 62% reported course completion "
                    "versus 48% among matched adults receiving standard materials."
                ),
                relationship_to_claim=relationship,
                material_limitations=("Assignment was not randomized.",),
                inferential_boundaries=("The result is an association in one region.",),
                evidence_quality=4,
                claim_fit=4,
                reasoning="The quoted comparison is directly relevant but observational.",
            )
        raise AssertionError(f"unhandled output type: {output_name}")

    def usage_for(
        self,
        request: LLMRequest,
        output: object,
        invocation_record: object,
    ) -> ModelUsageMetadata:
        del request, output, invocation_record
        return ModelUsageMetadata(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost_usd=Decimal("0.00001"),
        )


class _AuthorizationObservingV2Model(_V2Model):
    def __init__(self, *, db_path: Path) -> None:
        super().__init__(completed_rounds=4)
        self._db_path = db_path
        self.round_four_authorization_seen = False

    def generate(self, request: LLMRequest) -> object:
        if (
            request.requested_output_type.__name__ == "V2AdaptiveSearchModelOutput"
            and request.input_artifact.round_number == 4
        ):
            decision = V2RoundFourGovernorDecision.model_validate_json(
                read_v2_artifact(
                    self._db_path,
                    request.run_id,
                    V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
                ).payload_json
            )
            self.round_four_authorization_seen = (
                decision.authorized and decision.reservation is not None
            )
        return super().generate(request)


class _ExtractionFailureModel(_V2Model):
    def generate(self, request: LLMRequest) -> object:
        if request.requested_output_type.__name__ == "V2VerbatimQuoteSelection":
            self.requests.append(request)
            return V2VerbatimQuoteSelection(
                selected_sentence_ranges=(
                    SelectedSentenceRange(start_sentence=99, end_sentence=99),
                )
            )
        return super().generate(request)


class _CancellingV2Model(_V2Model):
    def __init__(
        self,
        *,
        db_path: Path,
        run_id: UUID,
        cancel_after_output_type: str,
        fail_on_cancellation: bool = False,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._run_id = run_id
        self._cancel_after_output_type = cancel_after_output_type
        self._fail_on_cancellation = fail_on_cancellation

    def generate(self, request: LLMRequest) -> object:
        output_name = request.requested_output_type.__name__
        if output_name == self._cancel_after_output_type and self._fail_on_cancellation:
            self.requests.append(request)
            request_run_cancellation(self._db_path, self._run_id, reason="test cancellation")
            raise RuntimeError("test provider failure before retry")
        output = super().generate(request)
        if output_name == self._cancel_after_output_type:
            request_run_cancellation(self._db_path, self._run_id, reason="test cancellation")
        return output


def _routing() -> V2RoutingConfig:
    return V2RoutingConfig.from_environment(
        {
            "MIMO_API_KEY": "mimo-secret",
            "MIMO_V25_MODEL": "mimo-v2.5",
            "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
            "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
            "LUNA_API_KEY": "luna-secret",
            "LUNA_BASE_URL": "https://luna.example.test/v1",
            "LUNA_MODEL": "luna",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="v2-phase12-tests",
    )


def _run(
    db_path: Path,
    model: _V2Model,
    search: _Search,
    scraper: _Scraper,
    *,
    run_id: UUID | None = None,
    directions: ResearchDirections | None = None,
    ceilings: V2RunCeilings | None = None,
) -> V2ProductionPipelineResult:
    return run_v2_production_pipeline(
        "The regional program increases course completion.",
        db_path=db_path,
        directions=directions or ResearchDirections(support_enabled=True, challenge_enabled=False),
        discovery_providers=(DiscoveryProvider.EXA,),
        search_providers={DiscoveryProvider.EXA: search},
        wigolo_provider=scraper,
        llm_provider=model,
        routing_config=_routing(),
        ceilings=ceilings
        or V2RunCeilings(
            max_physical_calls=40,
            max_total_tokens=100_000,
            max_total_cost_usd=Decimal("1"),
        ),
        run_id=run_id,
        clock=lambda: NOW,
    )


@pytest.fixture(scope="module")
def _reconciliation_inputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, V2GapAnalysisOutput, V2EvidenceAdmissionBatchResult]:
    db_path = tmp_path_factory.mktemp("phase14-reconciliation") / "reconciliation.sqlite3"
    run_id = uuid4()
    result = _run(
        db_path,
        _V2Model(completed_rounds=4),
        _Search(unique_results=True),
        _Scraper(),
        run_id=run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )
    assert result.final_output is not None
    post_gap = V2GapAnalysisOutput.model_validate_json(
        read_v2_artifact(db_path, run_id, V2_POST13_GAP_AFTER_ROUND_THREE_KEY).payload_json
    )
    admission = V2EvidenceAdmissionBatchResult.model_validate_json(
        read_v2_artifact(db_path, run_id, V2_EVIDENCE_ADMISSION_ARTIFACT_KEY).payload_json
    )
    return db_path, post_gap, admission


def test_reconciliation_accepts_the_typed_admission_chain(
    _reconciliation_inputs: tuple[Path, V2GapAnalysisOutput, V2EvidenceAdmissionBatchResult],
) -> None:
    db_path, post_gap, admission = _reconciliation_inputs

    reconciliation = reconcile_post_round_three_gaps(
        db_path=db_path,
        post_round_three_gap=post_gap,
        admission_result=admission,
        clock=lambda: NOW,
    )

    assert reconciliation.run_id == admission.run_id
    assert reconciliation.post_round_three_gap_artifact_key == V2_POST13_GAP_AFTER_ROUND_THREE_KEY


@pytest.mark.parametrize("invalid_input", [{}, object()])
def test_reconciliation_rejects_untyped_admission_input(
    _reconciliation_inputs: tuple[Path, V2GapAnalysisOutput, V2EvidenceAdmissionBatchResult],
    invalid_input: object,
) -> None:
    db_path, post_gap, _admission = _reconciliation_inputs

    with pytest.raises(TypeError, match="V2EvidenceAdmissionBatchResult"):
        reconcile_post_round_three_gaps(
            db_path=db_path,
            post_round_three_gap=post_gap,
            admission_result=invalid_input,
            clock=lambda: NOW,
        )


def test_reconciliation_rejects_foreign_admission_batch_run(
    _reconciliation_inputs: tuple[Path, V2GapAnalysisOutput, V2EvidenceAdmissionBatchResult],
) -> None:
    db_path, post_gap, admission = _reconciliation_inputs

    with pytest.raises(ValueError, match="batch run_id"):
        reconcile_post_round_three_gaps(
            db_path=db_path,
            post_round_three_gap=post_gap,
            admission_result=admission.model_copy(update={"run_id": uuid4()}),
            clock=lambda: NOW,
        )


def test_reconciliation_rejects_foreign_nested_evidence_record(
    _reconciliation_inputs: tuple[Path, V2GapAnalysisOutput, V2EvidenceAdmissionBatchResult],
) -> None:
    db_path, post_gap, admission = _reconciliation_inputs
    source_index = next(
        index
        for index, source in enumerate(admission.source_results)
        if source.evidence_record is not None
    )
    source = admission.source_results[source_index]
    assert source.evidence_record is not None
    tampered_source = source.model_copy(
        update={"evidence_record": source.evidence_record.model_copy(update={"run_id": uuid4()})}
    )
    tampered_sources = list(admission.source_results)
    tampered_sources[source_index] = tampered_source

    with pytest.raises(ValueError, match="evidence record run_id"):
        reconcile_post_round_three_gaps(
            db_path=db_path,
            post_round_three_gap=post_gap,
            admission_result=admission.model_copy(
                update={"source_results": tuple(tampered_sources)}
            ),
            clock=lambda: NOW,
        )


def test_reconciliation_rejects_mismatched_gap_and_round_four_provenance_ids(
    _reconciliation_inputs: tuple[Path, V2GapAnalysisOutput, V2EvidenceAdmissionBatchResult],
) -> None:
    db_path, post_gap, admission = _reconciliation_inputs
    assert post_gap.result is not None and post_gap.result.material_gaps
    foreign_gap = post_gap.result.material_gaps[0].model_copy(update={"gap_id": "foreign-gap"})
    tampered_post_gap = post_gap.model_copy(
        update={"result": post_gap.result.model_copy(update={"material_gaps": (foreign_gap,)})}
    )
    with pytest.raises(ValueError, match="absent from source-selection history"):
        reconcile_post_round_three_gaps(
            db_path=db_path,
            post_round_three_gap=tampered_post_gap,
            admission_result=admission,
            clock=lambda: NOW,
        )

    source_index = next(
        index
        for index, source in enumerate(admission.source_results)
        if source.evidence_record is not None
    )
    source = admission.source_results[source_index]
    tampered_source = source.model_copy(
        update={
            "provenance": source.provenance.model_copy(
                update={"relevant_gap_ids": ("foreign-gap",)}
            )
        }
    )
    tampered_sources = list(admission.source_results)
    tampered_sources[source_index] = tampered_source
    with pytest.raises(ValueError, match="provenance"):
        reconcile_post_round_three_gaps(
            db_path=db_path,
            post_round_three_gap=post_gap,
            admission_result=admission.model_copy(
                update={"source_results": tuple(tampered_sources)}
            ),
            clock=lambda: NOW,
        )


def test_run_a_full_v2_path_releases_and_restart_reuses_terminal_artifact(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase12.sqlite3"
    run_id = uuid4()
    model = _V2Model()
    search = _Search()
    scraper = _Scraper()

    first = _run(db_path, model, search, scraper, run_id=run_id)

    assert first.state is V2ProductionState.RELEASED, first.failure_reason
    assert first.final_output is not None and first.final_output.release_validation.valid
    assert first.current_stage is Stage.FINAL_RENDERER_VALIDATOR
    assert first.diagnostics is not None

    assert first.diagnostics.configured_providers == (DiscoveryProvider.EXA,)
    assert first.diagnostics.search_attempts >= 1
    assert first.diagnostics.sources_acquired >= 1
    assert first.diagnostics.sources_analyzed >= 1
    assert first.diagnostics.approved_evidence_records >= 1
    snapshot = LiveResearchController(environment={})._snapshot_from_v2_result(first)
    assert snapshot.supporting.candidates >= 1
    assert snapshot.supporting.model_attempts >= 1
    assert first.budget.physical_calls_used == len(model.requests)
    assert first.budget.physical_calls_used < 40
    assert first.budget.token_exposure == len(model.requests) * 15
    assert read_v2_artifact(str(db_path), run_id, V2_PRODUCTION_ARTIFACT_KEY)
    assert len(model.requests) == 6
    assert all(request.stage is not LLMStage.REVIEWER for request in model.requests)
    assert all(
        request.requested_output_type.__name__ != "ReviewerDecision" for request in model.requests
    )
    assert first.final_output is not None
    assert all(
        item.admission_method is V2AdmissionMethod.ANALYZER_ADMITTED
        for section in first.final_output.synthesis.sections
        for item in section.items
    )

    resumed = _run(db_path, _V2Model(), _Search(), _Scraper(), run_id=run_id)
    assert resumed == first


def test_post_phase13_round_four_is_bounded_and_uses_versioned_artifacts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase14-round-four.sqlite3"
    run_id = uuid4()
    model = _V2Model(completed_rounds=4)

    result = _run(
        db_path,
        model,
        _Search(unique_results=True),
        _Scraper(),
        run_id=run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 4
    assert model.search_agent_calls == 3
    assert read_v2_artifact(db_path, run_id, "post-phase-13-round-4-plan-v1")
    assert read_v2_artifact(db_path, run_id, "post-phase-13-gap-coverage-reconciliation-v1")
    assert result.final_output.gap_reconciliation is not None
    tampered = result.final_output.model_dump()
    tampered["claim_coverage_map"] = ()
    with pytest.raises(ValidationError, match="final claim coverage"):
        V2FinalResearchOutput.model_validate(tampered)


def test_round_four_authorization_is_persisted_before_search_agent_execution(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase14-authorization-order.sqlite3"
    model = _AuthorizationObservingV2Model(db_path=db_path)
    result = _run(
        db_path,
        model,
        _Search(unique_results=True),
        _Scraper(),
        run_id=uuid4(),
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert model.round_four_authorization_seen


def test_orchestrator_round_four_uses_fresh_budget_after_gap_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_round_four = v2_orchestrator.run_v2_round_four_continuation
    pre_gap_budgets: list[V2AdaptiveBudgetState] = []
    post_gap_budgets: list[V2AdaptiveBudgetState] = []

    def observe_round_four(**kwargs: object) -> V2RoundFourRunResult:
        pre_gap_budgets.append(cast(V2AdaptiveBudgetState, kwargs["budget"]))
        snapshot = cast(Callable[[], V2AdaptiveBudgetState], kwargs["budget_snapshot"])

        def observe_snapshot() -> V2AdaptiveBudgetState:
            current = snapshot()
            post_gap_budgets.append(current)
            return current

        forwarded = dict(kwargs)
        forwarded["budget_snapshot"] = observe_snapshot
        return original_round_four(**forwarded)

    monkeypatch.setattr(v2_orchestrator, "run_v2_round_four_continuation", observe_round_four)
    db_path = tmp_path / "phase14-fresh-budget-orchestrator.sqlite3"
    run_id = uuid4()
    result = _run(
        db_path,
        _V2Model(completed_rounds=4),
        _Search(unique_results=True),
        _Scraper(),
        run_id=run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert len(pre_gap_budgets) == 1
    assert len(post_gap_budgets) == 1
    assert post_gap_budgets[0].model_calls_remaining < pre_gap_budgets[0].model_calls_remaining
    assert post_gap_budgets[0].tokens_remaining < pre_gap_budgets[0].tokens_remaining
    assert post_gap_budgets[0].cost_remaining_usd < pre_gap_budgets[0].cost_remaining_usd
    decision = V2RoundFourGovernorDecision.model_validate_json(
        read_v2_artifact(db_path, run_id, "post-phase-13-round-4-governor-decision-v1").payload_json
    )
    assert decision.authorized
    assert decision.reservation is not None
    assert (
        decision.reservation.post_gap_available_calls == post_gap_budgets[0].model_calls_remaining
    )
    assert decision.reservation.post_gap_available_tokens == post_gap_budgets[0].tokens_remaining
    assert (
        decision.reservation.post_gap_available_cost_usd == post_gap_budgets[0].cost_remaining_usd
    )
    assert decision.reservation.provider_search_calls == 2
    assert decision.reservation.acquisition_cluster_capacity == 10
    assert decision.reservation.optional_calls == 5


def test_direct_round_four_requires_fresh_snapshot_and_rejects_stale_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_round_four = v2_orchestrator.run_v2_round_four_continuation
    captured: dict[str, object] = {}

    def capture_round_four(**kwargs: object) -> object:
        captured.update(kwargs)
        raise RuntimeError("stop before direct Round-4 invocation")

    monkeypatch.setattr(v2_orchestrator, "run_v2_round_four_continuation", capture_round_four)
    db_path = tmp_path / "phase14-fresh-budget-direct.sqlite3"
    model = _V2Model(completed_rounds=4)
    result = _run(
        db_path,
        model,
        _Search(unique_results=True),
        _Scraper(),
        run_id=uuid4(),
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.FAILED
    pre_gap_call_count = len(model.requests)
    missing_snapshot = dict(captured)
    missing_snapshot.pop("budget_snapshot")
    with pytest.raises(TypeError, match="budget_snapshot"):
        original_round_four(**missing_snapshot)

    pre_gap_budget = cast(V2AdaptiveBudgetState, captured["budget"])
    search_agent_calls_before_direct = model.search_agent_calls
    snapshot_calls: list[int] = []

    def reduced_post_gap_snapshot() -> V2AdaptiveBudgetState:
        assert len(model.requests) > pre_gap_call_count
        snapshot_calls.append(len(model.requests))
        return pre_gap_budget.model_copy(
            update={
                "model_calls_remaining": 0,
                "tokens_remaining": 0,
                "cost_remaining_usd": Decimal("0"),
            }
        )

    direct_arguments = dict(captured)
    direct_arguments["budget_snapshot"] = reduced_post_gap_snapshot
    direct = original_round_four(**direct_arguments)

    assert snapshot_calls
    assert not direct.governor_decision.authorized
    assert direct.governor_decision.reservation is None
    assert model.search_agent_calls == search_agent_calls_before_direct


def test_round_four_planning_is_not_invoked_without_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_round_four = v2_orchestrator.run_v2_round_four_continuation
    captured: dict[str, object] = {}

    def capture_round_four(**kwargs: object) -> object:
        captured.update(kwargs)
        raise RuntimeError("stop before direct Round-4 invocation")

    monkeypatch.setattr(v2_orchestrator, "run_v2_round_four_continuation", capture_round_four)
    db_path = tmp_path / "phase14-planning-requires-authorization.sqlite3"
    run_id = uuid4()
    model = _V2Model(completed_rounds=4)
    search = _Search(unique_results=True)
    result = _run(
        db_path,
        model,
        search,
        _Scraper(),
        run_id=run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )
    assert result.state is V2ProductionState.FAILED
    search_calls_before_direct = len(search.requests)
    search_agent_calls_before_direct = model.search_agent_calls
    pre_gap_budget = cast(V2AdaptiveBudgetState, captured["budget"])

    def planning_must_not_run(**kwargs: object) -> object:
        raise AssertionError("Round-4 planning must not run without authorization")

    monkeypatch.setattr("agents.v2_round_four._plan_round_four", planning_must_not_run)
    direct_arguments = dict(captured)
    direct_arguments["budget_snapshot"] = lambda: pre_gap_budget.model_copy(
        update={
            "model_calls_remaining": 0,
            "tokens_remaining": 0,
            "cost_remaining_usd": Decimal("0"),
        }
    )
    direct = original_round_four(**direct_arguments)

    assert not direct.governor_decision.authorized
    assert len(search.requests) == search_calls_before_direct
    assert model.search_agent_calls == search_agent_calls_before_direct


def test_degraded_round_three_does_not_call_round_four(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    round_four_calls: list[object] = []

    def record_round_four_call(**kwargs: object) -> object:
        round_four_calls.append(kwargs)
        raise AssertionError("degraded Round 3 must not call Round 4")

    monkeypatch.setattr(v2_orchestrator, "run_v2_round_four_continuation", record_round_four_call)
    model = _V2Model(completed_rounds=4)
    result = _run(
        tmp_path / "phase14-degraded-round-three.sqlite3",
        model,
        _FailsRoundThreeSearch(unique_results=True),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert round_four_calls == []
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 3
    assert result.final_output.stopping.reason.value == "provider_eligibility_exhausted"


def test_round_four_provider_failure_persists_terminal_outcome_without_rewriting_authorization(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase14-terminal.sqlite3"
    run_id = uuid4()
    result = _run(
        db_path,
        _V2Model(completed_rounds=4),
        _FailsRoundFourSearch(unique_results=True),
        _Scraper(),
        run_id=run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    authorization = read_v2_artifact(db_path, run_id, "post-phase-13-round-4-governor-decision-v1")
    terminal = V2RoundFourTerminalOutcome.model_validate_json(
        read_v2_artifact(db_path, run_id, "post-phase-13-round-4-terminal-outcome-v1").payload_json
    )
    assert '"reason_code":"authorized"' in authorization.payload_json
    assert terminal.reason_code.value == "terminal_failure"


def test_degraded_round_four_preserves_successful_partial_survivors(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase14-partial-round-four.sqlite3"
    run_id = uuid4()
    result = _run(
        db_path,
        _V2Model(completed_rounds=4, round_four_query_count=2),
        _FailsSecondRoundFourSearch(unique_results=True),
        _Scraper(),
        run_id=run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 4
    completion = V2RoundFourRunResult.model_validate_json(
        read_v2_artifact(db_path, run_id, "post-phase-13-round-4-completion-v1").payload_json
    )
    assert completion.continuation.rounds[-1].status is V2AdaptiveRoundStatus.DEGRADED
    assert (
        completion.continuation.stopping_decision.stop_code is V2AdaptiveStopCode.PROVIDER_FAILURE
    )
    round_four_sources = tuple(
        source
        for source in result.final_output.all_surviving_sources
        if source.discovery_round == 4
    )
    assert round_four_sources
    assert result.final_output.gap_reconciliation is not None
    assert result.final_output.gap_reconciliation.round_four_attempted


def test_degraded_round_four_with_all_failures_preserves_prior_work_only(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase14-all-failed-round-four.sqlite3"
    run_id = uuid4()
    result = _run(
        db_path,
        _V2Model(completed_rounds=4, round_four_query_count=2),
        _FailsAllRoundFourSearch(unique_results=True),
        _Scraper(),
        run_id=run_id,
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 4
    completion = V2RoundFourRunResult.model_validate_json(
        read_v2_artifact(db_path, run_id, "post-phase-13-round-4-completion-v1").payload_json
    )
    assert completion.continuation.rounds[-1].status is V2AdaptiveRoundStatus.DEGRADED
    assert (
        completion.continuation.stopping_decision.stop_code is V2AdaptiveStopCode.PROVIDER_FAILURE
    )
    assert result.final_output.all_surviving_sources
    assert all(source.discovery_round < 4 for source in result.final_output.all_surviving_sources)
    assert result.final_output.gap_reconciliation is not None
    assert result.final_output.gap_reconciliation.round_four_attempted


def test_degraded_round_four_does_not_authorize_a_fifth_round(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase14-no-fifth-round.sqlite3"
    model = _V2Model(completed_rounds=4, round_four_query_count=2)
    result = _run(
        db_path,
        model,
        _FailsSecondRoundFourSearch(unique_results=True),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=80,
            max_total_tokens=500_000,
            max_total_cost_usd=Decimal("5"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 4
    assert model.search_agent_calls == 3
    assert all(
        request.input_artifact.round_number <= 4
        for request in model.requests
        if request.requested_output_type.__name__ == "V2AdaptiveSearchModelOutput"
    )


def test_completed_legacy_v2_result_bypasses_phase13_identity_validation(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    db_path = tmp_path / "legacy-terminal.sqlite3"
    legacy_result = V2ProductionPipelineResult(
        run_id=run_id,
        db_path=str(db_path),
        raw_claim="The regional program increases course completion.",
        state=V2ProductionState.FAILED,
        current_stage=Stage.REVIEW,
        failure_reason="historical Phase-12 terminal result",
        budget=V2BudgetSnapshot(
            physical_calls_used=7,
            token_exposure=105,
            cost_exposure_usd=Decimal("0.00105"),
            physical_calls_remaining=153,
            tokens_remaining=499_895,
            cost_remaining_usd=Decimal("0.19895"),
        ),
        completed_at=NOW,
    )
    _prepare_identity(
        str(db_path),
        run_id,
        legacy_result.raw_claim,
        _routing().model_copy(update={"repository_revision": "historical-phase12"}),
        lambda: NOW,
    )
    insert_v2_artifact(str(db_path), V2_PRODUCTION_LEGACY_ARTIFACT_KEY, legacy_result, NOW)

    resumed = _run(db_path, _V2Model(), _Search(), _Scraper(), run_id=run_id)

    assert resumed == legacy_result


def test_running_v2_snapshot_reports_persisted_progress(tmp_path: Path) -> None:
    db_path = str(tmp_path / "running-v2.sqlite3")
    run_id = uuid4()
    ceilings = V2RunCeilings(
        max_physical_calls=40,
        max_total_tokens=100_000,
        max_total_cost_usd=Decimal("1"),
    )
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="The regional program increases course completion.",
            current_stage=Stage.ADAPTIVE_SEARCH,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)
    fingerprint = _production_fingerprint(
        run_id,
        directions,
        (DiscoveryProvider.EXA,),
        ceilings,
        _routing(),
        "test-provider-policy",
        NOW,
    )
    assert isinstance(fingerprint, V2ProductionFingerprint)
    insert_v2_artifact(db_path, V2_PRODUCTION_FINGERPRINT_KEY, fingerprint, NOW)

    controller = LiveResearchController(environment={})
    before_call = controller.snapshot(db_path, run_id)

    assert before_call.classification == "running"
    assert before_call.stage == Stage.ADAPTIVE_SEARCH.value
    assert before_call.progress_percent == 50
    assert before_call.model_calls_used == 0

    insert_v2_artifact(
        db_path,
        "phase-12-physical-call-001-start",
        V2PhysicalCallStart(
            run_id=run_id,
            sequence=1,
            stage=Stage.ADAPTIVE_SEARCH.value,
            model_alias="mimo-v2.5",
            reserved_tokens=100,
            reserved_cost_usd=Decimal("0.001"),
            started_at=NOW,
        ),
        NOW,
    )
    insert_v2_artifact(
        db_path,
        "phase-12-physical-call-002-start",
        V2PhysicalCallStart(
            run_id=run_id,
            sequence=2,
            stage=Stage.ADAPTIVE_SEARCH.value,
            model_alias="mimo-v2.5",
            reserved_tokens=100,
            reserved_cost_usd=Decimal("0.001"),
            started_at=NOW,
        ),
        NOW,
    )
    after_call = controller.snapshot(db_path, run_id)

    assert after_call.classification == "running"
    assert after_call.model_calls_used == 2
    assert after_call.progress_percent == before_call.progress_percent + 1


def test_extraction_failure_is_preserved_in_final_pipeline_reason(tmp_path: Path) -> None:
    result = _run(
        tmp_path / "extraction-failure.sqlite3",
        _ExtractionFailureModel(),
        _Search(),
        _Scraper(),
    )

    assert result.state is V2ProductionState.FAILED
    assert result.failure_reason is not None
    assert "no analyzer-admitted evidence records" in result.failure_reason
    assert "extraction_failed" in result.failure_reason
    assert "selected sentence range exceeds the snapshot" in result.failure_reason
    assert result.current_stage is Stage.EVIDENCE_ADMISSION
    assert result.diagnostics is not None
    assert result.diagnostics.sources_acquired >= 1
    assert result.diagnostics.sources_analyzed >= 1
    assert result.diagnostics.approved_evidence_records == 0

    legacy_result = V2ProductionPipelineResult.model_validate_json(
        result.model_dump_json(exclude={"current_stage", "diagnostics"})
    )
    snapshot = LiveResearchController(environment={})._snapshot_from_v2_result(legacy_result)
    assert snapshot.stage == Stage.SYNTHESIS.value
    assert snapshot.retrieval_attempts_used == result.diagnostics.sources_acquired
    assert snapshot.research_controls.discovery_providers == (DiscoveryProvider.EXA,)
    assert snapshot.v2_diagnostics == result.diagnostics


def test_fresh_synthesis_progress_uses_the_synthesis_stage_value() -> None:
    diagnostics = V2RunDiagnostics(
        configured_providers=(DiscoveryProvider.EXA,),
        provider_outcomes=(V2ProviderRunDiagnostics(provider=DiscoveryProvider.EXA),),
    )
    budget = V2BudgetSnapshot(
        physical_calls_used=0,
        token_exposure=0,
        cost_exposure_usd=Decimal("0"),
        physical_calls_remaining=160,
        tokens_remaining=500_000,
        cost_remaining_usd=Decimal("1"),
    )
    progress = ResearchProgress(
        stance="supporting",
        status="running",
        model_attempts=0,
        retrieval_attempts=0,
        usable_snapshots=0,
        candidates=0,
    )

    assert _v2_progress_percent(Stage.SYNTHESIS, 1, diagnostics, budget, progress, progress) == 92


def test_run_wide_lower_call_ceiling_fails_closed_before_an_overrun(tmp_path: Path) -> None:
    model = _V2Model()
    result = _run(
        tmp_path / "lower-limit.sqlite3",
        model,
        _Search(),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=1,
            max_total_tokens=100_000,
            max_total_cost_usd=Decimal("1"),
        ),
    )

    assert result.state is V2ProductionState.FAILED
    assert result.budget.physical_calls_used == 1
    assert len(model.requests) == 1
    assert "downstream reserve" in (result.failure_reason or "")
    persisted = V2ProductionPipelineResult.model_validate_json(
        read_v2_artifact(
            str(tmp_path / "lower-limit.sqlite3"),
            result.run_id,
            V2_PRODUCTION_ARTIFACT_KEY,
        ).payload_json
    )
    assert persisted == result


def test_empty_deep_analysis_queue_reports_budget_reason_and_persists_failure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "empty-queue.sqlite3"
    result = _run(
        db_path,
        _V2Model(),
        _Search(),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=40,
            max_total_tokens=100_000,
            max_total_cost_usd=Decimal("0.01"),
        ),
    )

    assert result.state is V2ProductionState.FAILED
    assert "deep-analysis queue is empty" in (result.failure_reason or "")
    assert "cost_reserve" in (result.failure_reason or "")
    persisted = V2ProductionPipelineResult.model_validate_json(
        read_v2_artifact(str(db_path), result.run_id, V2_PRODUCTION_ARTIFACT_KEY).payload_json
    )
    assert persisted == result


def test_default_v2_ceiling_matches_product_budget() -> None:
    defaults = V2RunCeilings()

    assert defaults.max_total_tokens == 500_000
    assert defaults.max_total_cost_usd == Decimal("0.20")


def test_policy_fingerprint_rejects_cross_configuration_resume(tmp_path: Path) -> None:
    path = tmp_path / "fingerprint.sqlite3"
    run_id = uuid4()
    first = _run(path, _V2Model(), _Search(), _Scraper(), run_id=run_id)
    assert first.state is V2ProductionState.RELEASED

    with pytest.raises(ValueError, match="fingerprint changed"):
        _run(
            path,
            _V2Model(),
            _Search(),
            _Scraper(),
            run_id=run_id,
            directions=ResearchDirections(
                support_enabled=False,
                challenge_enabled=True,
            ),
        )


def _assert_direction_run(tmp_path: Path, directions: ResearchDirections) -> None:
    result = _run(
        tmp_path
        / f"directions-{len(directions.enabled_directions)}-{directions.support_enabled}.db",
        _V2Model(),
        _Search(),
        _Scraper(),
        directions=directions,
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert {source.direction for source in result.final_output.all_surviving_sources} <= set(
        directions.enabled_directions
    )


def test_run_b_support_only_completes_targeted_round_two(tmp_path: Path) -> None:
    model = _V2Model(completed_rounds=2)
    result = _run(
        tmp_path / "run-b.sqlite3",
        model,
        _Search(unique_results=True),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=160,
            max_total_tokens=300_000,
            max_total_cost_usd=Decimal("1"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 2
    assert model.search_agent_calls == 1


def test_run_c_challenge_only_is_isolated(tmp_path: Path) -> None:
    _assert_direction_run(
        tmp_path,
        ResearchDirections(support_enabled=False, challenge_enabled=True),
    )


def test_run_d_both_directions_remain_isolated(tmp_path: Path) -> None:
    _assert_direction_run(tmp_path, ResearchDirections())


def test_run_e_round_three_is_governor_authorized(tmp_path: Path) -> None:
    model = _V2Model(completed_rounds=3)
    result = _run(
        tmp_path / "run-e.sqlite3",
        model,
        _Search(unique_results=True),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=160,
            max_total_tokens=300_000,
            max_total_cost_usd=Decimal("1"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 3
    assert model.search_agent_calls == 2


def test_run_f_round_three_is_denied_to_protect_downstream_budget(tmp_path: Path) -> None:
    model = _V2Model(completed_rounds=3)
    result = _run(
        tmp_path / "run-f.sqlite3",
        model,
        _Search(unique_results=True),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=22,
            max_total_tokens=300_000,
            max_total_cost_usd=Decimal("1"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert result.final_output is not None
    assert result.final_output.stopping.completed_rounds == 3
    assert result.final_output.stopping.reason.value == "hard_round_limit"


def test_run_g_transient_gap_degradation_preserves_valid_release(tmp_path: Path) -> None:
    model = _V2Model(fail_first_scout=True, fail_first_gap=True)
    result = _run(
        tmp_path / "run-g.sqlite3",
        model,
        _Search(),
        _Scraper(),
        ceilings=V2RunCeilings(
            max_physical_calls=40,
            max_total_tokens=300_000,
            max_total_cost_usd=Decimal("1"),
        ),
    )

    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    assert model.scout_attempts == 2
    assert model.gap_attempts == 2
    assert result.budget.physical_calls_used == len(model.requests)


def test_run_h_release_integrity_violation_blocks_final_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_builder = v2_final_output.build_v2_synthesis_output

    def invalid_builder(*, synthesis_input: object, created_at: datetime) -> object:
        valid = original_builder(synthesis_input=synthesis_input, created_at=created_at)
        first_section = valid.sections[0]
        invalid_item = first_section.items[0].model_copy(
            update={"approved_factual_statement": "Unsupported altered statement."}
        )
        invalid_section = first_section.model_copy(update={"items": (invalid_item,)})
        return valid.model_copy(update={"sections": (invalid_section, *valid.sections[1:])})

    monkeypatch.setattr(v2_final_output, "build_v2_synthesis_output", invalid_builder)
    result = _run(
        tmp_path / "run-h.sqlite3",
        _V2Model(),
        _Search(),
        _Scraper(),
    )

    assert result.state is V2ProductionState.BLOCKED
    assert result.final_output is not None
    assert not result.final_output.release_validation.valid
    assert result.final_output.release_validation.rendered_output_hash is None


def test_persisted_cancellation_before_first_model_call_stops_v2_run(tmp_path: Path) -> None:
    db_path = tmp_path / "phase12-cancel-before-planner.sqlite3"
    run_id = uuid4()
    routing = _routing()
    _prepare_identity(
        str(db_path),
        run_id,
        "The regional program increases course completion.",
        routing,
        lambda: NOW,
    )
    request_run_cancellation(db_path, run_id, reason="cancel before model work")

    result = _run(db_path, _V2Model(), _Search(), _Scraper(), run_id=run_id)

    assert v2_cancellation_requested(db_path, run_id)
    assert result.state is V2ProductionState.CANCELLED
    assert result.current_stage is Stage.CLAIM_PLANNER
    assert result.budget.physical_calls_used == 0


@pytest.mark.parametrize(
    ("cancel_after_output_type", "expected_stage"),
    (
        ("V2InitialPlannerModelOutput", Stage.CLAIM_PLANNER),
        ("V2SourceSelectionModelOutput", Stage.SOURCE_SELECTION),
        ("V2VerbatimQuoteSelection", Stage.DEEP_ANALYSIS),
        ("V2EvidenceAnalystModelOutput", Stage.DEEP_ANALYSIS),
    ),
)
def test_persisted_cancellation_stops_before_later_v2_model_work(
    tmp_path: Path,
    cancel_after_output_type: str,
    expected_stage: Stage,
) -> None:
    db_path = tmp_path / f"phase12-cancel-{cancel_after_output_type}.sqlite3"
    run_id = uuid4()
    model = _CancellingV2Model(
        db_path=db_path,
        run_id=run_id,
        cancel_after_output_type=cancel_after_output_type,
    )

    result = _run(db_path, model, _Search(), _Scraper(), run_id=run_id)

    assert result.state is V2ProductionState.CANCELLED
    assert result.current_stage is expected_stage
    assert model.requests[-1].requested_output_type.__name__ == cancel_after_output_type
    assert result.budget.physical_calls_used == len(model.requests)


def test_cancellation_after_scout_stops_before_acquisition_requests(tmp_path: Path) -> None:
    db_path = tmp_path / "phase12-cancel-before-acquisition.sqlite3"
    run_id = uuid4()
    model = _CancellingV2Model(
        db_path=db_path,
        run_id=run_id,
        cancel_after_output_type="ScoutBatch",
    )
    scraper = _Scraper()

    result = _run(db_path, model, _Search(), scraper, run_id=run_id)

    assert result.state is V2ProductionState.CANCELLED
    assert result.current_stage is Stage.DISCOVERY
    assert scraper.requests == []


def test_cancellation_between_scout_retries_prevents_additional_provider_call(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase12-cancel-before-scout-retry.sqlite3"
    run_id = uuid4()
    model = _CancellingV2Model(
        db_path=db_path,
        run_id=run_id,
        cancel_after_output_type="ScoutBatch",
        fail_on_cancellation=True,
    )
    scraper = _Scraper()

    result = _run(db_path, model, _Search(), scraper, run_id=run_id)

    scout_requests = [
        request
        for request in model.requests
        if request.requested_output_type.__name__ == "ScoutBatch"
    ]
    assert result.state is V2ProductionState.CANCELLED
    assert result.current_stage is Stage.DISCOVERY
    assert len(scout_requests) == 1
    assert len(model.requests) == 2
    assert result.budget.physical_calls_used == len(model.requests)
    assert scraper.requests == []


def test_cancellation_between_selection_retries_prevents_a_second_model_call(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "phase12-cancel-before-selection-retry.sqlite3"
    run_id = uuid4()
    model = _CancellingV2Model(
        db_path=db_path,
        run_id=run_id,
        cancel_after_output_type="V2SourceSelectionModelOutput",
        fail_on_cancellation=True,
    )

    result = _run(db_path, model, _Search(), _Scraper(), run_id=run_id)

    selection_requests = [
        request
        for request in model.requests
        if request.requested_output_type.__name__ == "V2SourceSelectionModelOutput"
    ]
    assert result.state is V2ProductionState.CANCELLED
    assert result.current_stage is Stage.SOURCE_SELECTION
    assert len(selection_requests) == 1
