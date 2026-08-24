from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from agents.researcher import (
    assemble_quote_block_from_selected_segments,
    filter_provisional_candidate,
)
from agents.v2_evidence_analyst import (
    revise_v2_canonical_statement,
    run_v2_evidence_analyst,
)
from agents.v2_source_selection import calculate_v2_deep_analysis_queue
from models import (
    CandidateQuoteBlock,
    DiscoveryProvider,
    ModelAttemptStatus,
    ModelUsageMetadata,
    ProvisionalCandidate,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoreDecision,
    SourceSnapshot,
    Stage,
    Stance,
    V2CanonicalStatementModelOutput,
    V2DeepAnalysisBudget,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystModelOutput,
    V2EvidenceAnalystState,
    V2EvidenceRelationship,
    V2PipelineIdentity,
    V2SourceSelectionCandidate,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
    V2SourceSelectionRecommendation,
    VerbatimQuoteSelection,
)
from providers.llm import (
    DEFAULT_LLM_ROUTING,
    LLMProviderCapabilities,
    LLMRequest,
    LLMStage,
    ModelAlias,
)
from providers.v2_routing import V2RoutingConfig
from store import (
    init_db,
    insert_run,
    insert_v2_pipeline_identity,
    read_model_route_attempts,
)

NOW = datetime(2026, 8, 21, tzinfo=UTC)
QUOTE = (
    "Among 240 surveyed adults in the regional program, 62 percent reported completing "
    "the assigned course within six months, compared with 48 percent of matched adults "
    "receiving the standard materials during the same observation period."
)
SNAPSHOT_TEXT = (
    "The evaluation describes a voluntary regional education program. "
    f"{QUOTE} "
    "The authors note that assignment was not randomized and self-reported completion may "
    "not generalize beyond the participating region."
)


class FakeLunaAnalyst:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self, responses: list[BaseModel | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> BaseModel:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def usage_for(
        self,
        request: LLMRequest,
        output: BaseModel,
        invocation_record: object,
    ) -> ModelUsageMetadata:
        del request, output, invocation_record
        return ModelUsageMetadata(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            cost_usd=Decimal("0.0012"),
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
            "LUNA_MODEL": "deployment-owned-luna-model",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="v2-phase9-tests",
    )


def _exact_candidate(
    run_id: UUID, direction: ResearchDirection
) -> tuple[CandidateQuoteBlock, SourceSnapshot]:
    digest = sha256(SNAPSHOT_TEXT.encode("utf-8")).hexdigest()
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/regional-evaluation",
        retrieved_at=NOW,
        normalized_text=SNAPSHOT_TEXT,
        snapshot_sha256=digest,
        word_count=len(SNAPSHOT_TEXT.split()),
        truncated=False,
        normalization_version="fixture-v1",
        created_at=NOW,
    )
    provisional = ProvisionalCandidate(
        run_id=run_id,
        stance=(Stance.SUPPORTING if direction is ResearchDirection.SUPPORT else Stance.OPPOSING),
        source_url=snapshot.source_url,
        retrieval_attempt_id=snapshot.retrieval_attempt_id,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        extracted_quote_block=assemble_quote_block_from_selected_segments(
            SNAPSHOT_TEXT,
            VerbatimQuoteSelection(selected_segments=(QUOTE,)),
            truncated=False,
        ),
        extraction_prompt_version="phase9-extractor-fixture",
        extraction_model_name=ModelAlias.MIMO_V25_PRO.value,
        extracted_at=NOW,
    )
    filtered = filter_provisional_candidate(
        provisional,
        snapshot,
        claim_keywords=("course", "completion"),
        post_filter_version="fixture-v1",
        validation_clock=lambda: NOW,
    )
    assert filtered.valid and filtered.candidate is not None
    return filtered.candidate, snapshot


def _batch_input(
    run_id: UUID,
    *,
    direction: ResearchDirection = ResearchDirection.SUPPORT,
) -> V2EvidenceAnalystBatchInput:
    candidate, snapshot = _exact_candidate(run_id, direction)
    source_id = uuid4()
    directions = ResearchDirections(
        support_enabled=direction is ResearchDirection.SUPPORT,
        challenge_enabled=direction is ResearchDirection.CHALLENGE,
    )
    survivor = V2SourceSelectionCandidate(
        source_id=source_id,
        direction=direction,
        source_family_id="family-regional-evaluation",
        research_round=1,
        source_url=snapshot.source_url,
        title="Regional program evaluation",
        source_type="observational evaluation",
        discovery_providers=(DiscoveryProvider.OPENALEX,),
        probe_passages=(
            {
                "passage_id": "probe-regional",
                "text": QUOTE,
                "score": 12,
            },
        ),
        search_provenance=(
            {
                "query_id": uuid4(),
                "provider": DiscoveryProvider.OPENALEX,
                "round_number": 1,
                "query_text": "regional program course completion evaluation",
                "targeted_gap_ids": (),
            },
        ),
        snapshot_word_count=snapshot.word_count,
        deep_analysis_input_tokens=1800,
    )
    selection_input = V2SourceSelectionInput(
        run_id=run_id,
        exact_claim="The regional program increases course completion.",
        directions=directions,
        survivors=(survivor,),
        gap_history=(),
    )
    budget = V2DeepAnalysisBudget(
        physical_calls_used=0,
        tokens_remaining=2_000_000,
        cost_remaining_usd=Decimal("100"),
    )
    rationale = V2SourceSelectionRecommendation(
        source_id=source_id,
        rationale="Direct empirical coverage of the requested completion outcome.",
    )
    plan = calculate_v2_deep_analysis_queue(
        selection_input=selection_input,
        ordered_source_ids=(source_id,),
        recommended_source_ids=(source_id,),
        recommendation_rationales=(rationale,),
        routing_config=_routing(),
        budget=budget,
    )
    queue_result = V2SourceSelectionQueueResult(
        run_id=run_id,
        input=selection_input,
        initial_budget=budget,
        recommended_source_ids=(source_id,),
        recommendation_rationales=(rationale,),
        used_fallback=True,
        selection_attempts=0,
        selection_attempt_records=(),
        queued_source_ids=plan.queued_source_ids,
        source_statuses=plan.source_statuses,
        queue_capacity=plan.queue_capacity,
        mandatory_synthesis_reservable=plan.mandatory_synthesis_reservable,
        physical_calls_after_reserve=plan.physical_calls_after_reserve,
        total_reserved_tokens=plan.total_reserved_tokens,
        total_reserved_cost_usd=plan.total_reserved_cost_usd,
        token_reservations=plan.token_reservations,
        limiting_reason=plan.limiting_reason,
        completed_at=NOW,
    )
    return V2EvidenceAnalystBatchInput(
        run_id=run_id,
        exact_claim=selection_input.exact_claim,
        directions=directions,
        queue_result=queue_result,
        queued_candidates=(
            V2EvidenceAnalystCandidateInput(
                source_id=source_id,
                direction=direction,
                candidate=candidate,
                snapshot=snapshot,
            ),
        ),
    )


def _assessment(
    *,
    relationship: V2EvidenceRelationship = V2EvidenceRelationship.SUPPORTS,
    claim_fit: int = 4,
) -> V2EvidenceAnalystModelOutput:
    return V2EvidenceAnalystModelOutput(
        narrowest_supported_proposition=(
            "Surveyed regional-program adults reported 62% course completion within six "
            "months, versus 48% among matched adults receiving standard materials."
        ),
        relationship_to_claim=relationship,
        material_limitations=(
            "Program assignment was not randomized.",
            "Completion was self-reported in one region.",
        ),
        inferential_boundaries=(
            "The comparison supports association, not an uncontrolled causal conclusion.",
        ),
        evidence_quality=4,
        claim_fit=claim_fit,
        reasoning="The quoted comparison is directly relevant but observational and local.",
    )


def _draft(
    assessment: V2EvidenceAnalystModelOutput, statement: str
) -> V2CanonicalStatementModelOutput:
    return V2CanonicalStatementModelOutput(
        narrowest_supported_proposition=assessment.narrowest_supported_proposition,
        canonical_factual_statement=statement,
        reasoning="The statement restates only the bounded reported comparison.",
    )


def _prepare_db(tmp_path: Path, run_id: UUID) -> str:
    path = str(tmp_path / "phase9.sqlite3")
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="The regional program increases course completion.",
            current_stage=Stage.EVIDENCE_ANALYST,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), NOW)
    return path


def test_luna_analysis_preserves_exact_quote_limitations_accounting_and_restart(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    original_candidate = batch.queued_candidates[0].candidate
    assessment = _assessment()
    provider = FakeLunaAnalyst(
        [
            assessment,
            _draft(
                assessment,
                "Among surveyed adults in the regional program, 62% reported course "
                "completion within six months, compared with 48% receiving standard materials.",
            ),
        ]
    )
    db_path = _prepare_db(tmp_path, run_id)

    first = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    resumed = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    source = first.source_results[0]
    assert source.state is V2EvidenceAnalystState.READY_FOR_REVIEWER
    assert source.candidate == original_candidate
    assert source.assessment == assessment
    assert source.assessment.material_limitations == assessment.material_limitations
    assert (
        source.assessment.narrowest_supported_proposition
        != original_candidate.extracted_quote_block
    )
    assert source.statement_draft is not None
    assert all(request.model_alias is ModelAlias.GPT_5_6_LUNA_HIGH for request in provider.requests)
    assert all(
        request.prompt.version == "phase9-luna-evidence-analyst-v2-source-context"
        for request in provider.requests
    )
    assert all(
        not hasattr(request.input_artifact, "untrusted_snapshot_text")
        for request in provider.requests
    )
    assert all(
        request.pinned_model_snapshot == "deployment-owned-luna-model"
        for request in provider.requests
    )
    attempts = read_model_route_attempts(db_path, run_id)
    assert len(attempts) == 2
    assert all(item.status is ModelAttemptStatus.COMPLETED for item in attempts)
    assert all(item.reserved_tokens is not None and item.reserved_tokens > 120 for item in attempts)
    assert all(item.usage is not None and item.usage.total_tokens == 120 for item in attempts)
    assert resumed == first and len(provider.requests) == 2


def test_claim_fit_three_requires_qualification_and_retries_draft(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment(claim_fit=3)
    provider = FakeLunaAnalyst(
        [
            assessment,
            _draft(assessment, "The program produced a higher completion rate."),
            _draft(
                assessment,
                "Among surveyed adults in this specific regional sample, completion was "
                "reported by 62% in the program and 48% receiving standard materials.",
            ),
        ]
    )
    result = run_v2_evidence_analyst(
        db_path=_prepare_db(tmp_path, run_id),
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    source = result.source_results[0]
    assert source.state is V2EvidenceAnalystState.READY_FOR_REVIEWER
    assert source.score_decision is not None
    assert source.score_decision.placement.value == "qualified_only"
    assert source.statement_draft is not None and "sample" in source.statement_draft.draft_statement
    assert len(provider.requests) == 3


@pytest.mark.parametrize(
    ("direction", "forbidden_relationship"),
    (
        (ResearchDirection.SUPPORT, V2EvidenceRelationship.CHALLENGES),
        (ResearchDirection.CHALLENGE, V2EvidenceRelationship.SUPPORTS),
    ),
)
def test_disabled_direction_relationship_is_retried_then_fails_without_ledger(
    tmp_path: Path,
    direction: ResearchDirection,
    forbidden_relationship: V2EvidenceRelationship,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id, direction=direction)
    wrong = _assessment(relationship=forbidden_relationship)
    provider = FakeLunaAnalyst([wrong, wrong])
    db_path = _prepare_db(tmp_path, run_id)
    result = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    source = result.source_results[0]
    assert source.state is V2EvidenceAnalystState.FAILED
    assert source.candidate == batch.queued_candidates[0].candidate
    assert source.statement_draft is None
    assert len(source.analyst_attempt_ids) == 2
    assert not hasattr(result, "ledger_records")
    assert all(
        item.status is ModelAttemptStatus.FAILED
        for item in read_model_route_attempts(db_path, run_id)
    )


def test_transient_analyst_failure_retries_once_and_succeeds(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment()
    provider = FakeLunaAnalyst(
        [
            RuntimeError("temporary Luna outage"),
            assessment,
            _draft(
                assessment,
                "Among surveyed adults in the regional program, 62% reported completion, "
                "compared with 48% receiving standard materials.",
            ),
        ]
    )
    db_path = _prepare_db(tmp_path, run_id)
    result = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    assert result.source_results[0].state is V2EvidenceAnalystState.READY_FOR_REVIEWER
    attempts = read_model_route_attempts(db_path, run_id)
    assert [item.status for item in attempts].count(ModelAttemptStatus.FAILED) == 1
    assert [item.status for item in attempts].count(ModelAttemptStatus.COMPLETED) == 2


def test_reviewer_directed_revision_is_the_third_luna_analyst_operation(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment()
    initial = _draft(
        assessment,
        "Among surveyed adults in the regional program, 62% reported completion, compared "
        "with 48% receiving standard materials.",
    )
    revised = _draft(
        assessment,
        "Among 240 surveyed regional-program adults, 62% reported course completion within "
        "six months, compared with 48% of matched adults receiving standard materials.",
    )
    provider = FakeLunaAnalyst([assessment, initial, revised])
    db_path = _prepare_db(tmp_path, run_id)
    analyzed = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    revision = revise_v2_canonical_statement(
        db_path=db_path,
        batch_input=batch,
        source_result=analyzed.source_results[0],
        reviewer_rationale="Retain the sample size and six-month observation window.",
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    resumed = revise_v2_canonical_statement(
        db_path=db_path,
        batch_input=batch,
        source_result=analyzed.source_results[0],
        reviewer_rationale="Retain the sample size and six-month observation window.",
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    assert revision.revised_statement.draft_statement == revised.canonical_factual_statement
    assert resumed == revision
    assert len(provider.requests) == 3
    assert provider.requests[-1].model_alias is ModelAlias.GPT_5_6_LUNA_HIGH
    assert len(read_model_route_attempts(db_path, run_id)) == 3


def test_historical_mimo_analyst_decision_and_route_remain_readable() -> None:
    historical = ScoreDecision(
        run_id=uuid4(),
        quote_block_id=uuid4(),
        evidence_quality=4,
        claim_fit=4,
        ledger_score=4,
        placement="secondary",
        approved=True,
        rationale="Historical direct-MiMo Analyst record.",
        analyst_prompt_version="phase8-analyst-v2",
        analyst_model_name="mimo-v2.5-pro",
        scored_at=NOW,
    )
    restored = ScoreDecision.model_validate_json(historical.model_dump_json())
    assert restored == historical
    assert DEFAULT_LLM_ROUTING.for_stage(LLMStage.ANALYST).primary is ModelAlias.MIMO_V25_PRO
    assert (
        _routing().preflight().for_stage(LLMStage.EXTRACTOR).logical_alias
        is ModelAlias.MIMO_V25_PRO
    )
