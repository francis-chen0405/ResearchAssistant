from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from agents.reviewer import ReviewerDecision
from agents.synthesizer import _item_from_ledger
from models import (
    DiscoveryProvider,
    ModelUsageMetadata,
    ResearchDirection,
    ResearchDirections,
    ScoutBatch,
    ScoutItem,
    SynthesisOutput,
    SynthesisSection,
    V2AdaptiveSearchModelOutput,
    V2AdaptiveSearchProposal,
    V2CanonicalStatementModelOutput,
    V2EvidenceAnalystModelOutput,
    V2EvidenceRelationship,
    V2GapAnalysisModelOutput,
    V2GapSearchDirection,
    V2InitialPlannerModelOutput,
    V2InitialPlannerSearchResponse,
    V2MaterialGap,
    V2SourceSelectionModelOutput,
    V2SourceSelectionRecommendation,
    VerbatimQuoteSelection,
)
from providers.llm import LLMProviderCapabilities, LLMRequest
from providers.scraper import ScrapeRequest, ScrapeResponse
from providers.search import SearchRequest, SearchResponse, SearchResult
from providers.v2_budget import V2RunCeilings
from providers.v2_routing import V2RoutingConfig
from store import read_v2_artifact
from v2_orchestrator import (
    V2_PRODUCTION_ARTIFACT_KEY,
    V2ProductionPipelineResult,
    V2ProductionState,
    run_v2_production_pipeline,
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
        invalid_synthesis: bool = False,
    ) -> None:
        self.requests: list[LLMRequest] = []
        self.completed_rounds = completed_rounds
        self.fail_first_scout = fail_first_scout
        self.fail_first_gap = fail_first_gap
        self.invalid_synthesis = invalid_synthesis
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
            if self.successful_gaps < self.completed_rounds:
                direction = request.input_artifact.directions.enabled_directions[0]
                gap = V2MaterialGap(
                    gap_id=f"gap-round-{self.successful_gaps}",
                    direction=direction,
                    missing_evidence="Independent replication evidence remains missing.",
                    rationale="The current pool contains a material replication gap.",
                )
                return V2GapAnalysisModelOutput(
                    coverage_summary="A material replication gap remains.",
                    material_gaps=(gap,),
                    continue_research=True,
                    new_search_directions=(
                        V2GapSearchDirection(
                            gap_id=gap.gap_id,
                            direction=direction,
                            missing_evidence=gap.missing_evidence,
                            search_focus="Independent replication with a distinct instrument",
                        ),
                    ),
                    discovered_terms=("replication",),
                )
            return V2GapAnalysisModelOutput(
                coverage_summary="The surviving source is adequate for this bounded run.",
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
                searches=(
                    V2AdaptiveSearchProposal(
                        direction=gap.direction,
                        provider=DiscoveryProvider.EXA,
                        targeted_gap_ids=(gap.gap_id,),
                        strategy=f"replication_round_{request.input_artifact.round_number}",
                        query_text=(
                            f"distinct replication instrument round "
                            f"{request.input_artifact.round_number} outcome"
                        ),
                    ),
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
        if output_name == "VerbatimQuoteSelection":
            return VerbatimQuoteSelection(selected_segments=(QUOTE,))
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
                relationship_to_claim=relationship,
                material_limitations=("Assignment was not randomized.",),
                inferential_boundaries=("The result is an association in one region.",),
                evidence_quality=4,
                claim_fit=4,
                reasoning="The quoted comparison is directly relevant but observational.",
            )
        if output_name == "V2CanonicalStatementModelOutput":
            proposition = request.input_artifact.assessment.narrowest_supported_proposition
            return V2CanonicalStatementModelOutput(
                narrowest_supported_proposition=proposition,
                canonical_factual_statement=proposition,
                reasoning="This restates only the bounded reported comparison.",
            )
        if output_name == "ReviewerDecision":
            return ReviewerDecision(
                reviewed_statement=request.input_artifact.draft_statement,
                approved=True,
                rationale="The statement is entailed and preserves its qualifications.",
            )
        if output_name == "SynthesisOutput":
            items = request.input_artifact.approved_ledger_items
            synthesis_items = tuple(_item_from_ledger(item) for item in items)
            if self.invalid_synthesis:
                synthesis_items = (
                    synthesis_items[0].model_copy(
                        update={"approved_factual_statement": "Unsupported altered statement."}
                    ),
                    *synthesis_items[1:],
                )
            return SynthesisOutput(
                run_id=request.run_id,
                synthesizer_prompt_version=request.prompt.version,
                synthesizer_model_name=request.model_alias.value,
                created_at=NOW,
                sections=(
                    SynthesisSection(
                        section_type="supporting",
                        items=tuple(
                            item for item in synthesis_items if item.stance.value == "supporting"
                        ),
                    ),
                )
                if all(item.stance.value == "supporting" for item in synthesis_items)
                else tuple(
                    SynthesisSection(
                        section_type=stance,
                        items=tuple(
                            item for item in synthesis_items if item.stance.value == stance
                        ),
                    )
                    for stance in ("supporting", "opposing")
                    if any(item.stance.value == stance for item in synthesis_items)
                ),
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
    assert first.budget.physical_calls_used == len(model.requests)
    assert first.budget.physical_calls_used < 40
    assert first.budget.token_exposure == len(model.requests) * 15
    assert read_v2_artifact(str(db_path), run_id, V2_PRODUCTION_ARTIFACT_KEY)

    resumed = _run(db_path, _V2Model(), _Search(), _Scraper(), run_id=run_id)
    assert resumed == first


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
    assert result.final_output.stopping.completed_rounds == 2
    assert "budget" in result.final_output.stopping.reason.casefold()


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


def test_run_h_release_integrity_violation_blocks_final_output(tmp_path: Path) -> None:
    result = _run(
        tmp_path / "run-h.sqlite3",
        _V2Model(invalid_synthesis=True),
        _Search(),
        _Scraper(),
    )

    assert result.state is V2ProductionState.BLOCKED
    assert result.final_output is not None
    assert not result.final_output.release_validation.valid
    assert result.final_output.release_validation.rendered_output_hash is None
