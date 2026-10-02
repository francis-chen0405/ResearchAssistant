from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from agents.researcher import (
    assemble_quote_block_from_selected_segments,
    filter_provisional_candidate,
)
from agents.v2_evidence_analyst import (
    _RetryableAssessmentValidationError,
    _validate_contextual_exception_scope,
    revise_v2_canonical_statement,
    run_v2_evidence_analyst,
)
from agents.v2_extraction import (
    V2ExtractionState,
    _extract_source,
    run_v2_exact_extraction,
)
from agents.v2_source_selection import calculate_v2_deep_analysis_queue
from evidence_analysis import statement_has_required_qualification
from models import (
    V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY,
    V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
    V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY,
    CandidateQuoteBlock,
    DiscoveryProvenance,
    DiscoveryProvider,
    DiscoveryProviderReference,
    ModelAttemptStatus,
    ModelUsageMetadata,
    NormalizedDiscoveryItem,
    ProvisionalCandidate,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoreDecision,
    SourceCluster,
    SourceSnapshot,
    Stage,
    Stance,
    V2AcquiredSource,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
    V2CanonicalStatementModelOutput,
    V2DeepAnalysisBudget,
    V2DiscoveryScoutOutput,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystExtractionFailure,
    V2EvidenceAnalystModelOutput,
    V2EvidenceAnalystSourceResult,
    V2EvidenceAnalystState,
    V2EvidenceRelationship,
    V2PipelineIdentity,
    V2ProbeResult,
    V2SourceSelectionCandidate,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
    V2SourceSelectionRecommendation,
    V2VerbatimQuoteSelection,
    VerbatimQuoteSelection,
)
from providers.llm import (
    DEFAULT_LLM_ROUTING,
    LLMProviderCapabilities,
    LLMProviderExecutionError,
    LLMRequest,
    LLMStage,
    ModelAlias,
)
from providers.mimo import MimoFailureCode, MimoProviderError
from providers.model_choices import DEFAULT_STAGE_MODELS, ModelChoice, StageModelSelections
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
    policy_identity: str = V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
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
        policy_identity=policy_identity,
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
        canonical_factual_statement=(
            "Among surveyed regional-program adults, 62% reported course completion within "
            "six months, versus 48% among matched adults receiving standard materials."
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
    assert source.state is V2EvidenceAnalystState.READY_FOR_ADMISSION
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
        request.prompt.version
        == "post-phase13-luna-evidence-analyst-v9-independent-relationship-scope-context"
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
    assert len(attempts) == 1
    assert all(item.status is ModelAttemptStatus.COMPLETED for item in attempts)
    assert all(item.reserved_tokens is not None and item.reserved_tokens > 120 for item in attempts)
    assert all(item.usage is not None and item.usage.total_tokens == 120 for item in attempts)
    assert resumed == first and len(provider.requests) == 1


def test_extraction_failure_reason_survives_the_phase9_handoff(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    source_id = batch.queue_result.queued_source_ids[0]
    exact_failure = "ValueError: selected quote segment does not appear in snapshot text"
    failed_batch = batch.model_copy(
        update={
            "queued_candidates": (),
            "extraction_failures": (
                V2EvidenceAnalystExtractionFailure(
                    source_id=source_id,
                    failure=exact_failure,
                ),
            ),
        }
    )

    result = run_v2_evidence_analyst(
        db_path=_prepare_db(tmp_path, run_id),
        batch_input=failed_batch,
        llm_provider=FakeLunaAnalyst([]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    source = result.source_results[0]
    assert source.state is V2EvidenceAnalystState.FAILED
    assert source.failure == exact_failure


def test_claim_fit_three_is_accepted_without_a_scope_retry(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment(claim_fit=3)
    provider = FakeLunaAnalyst(
        [
            assessment,
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
    assert source.state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    assert source.score_decision is not None
    assert source.score_decision.placement.value == "secondary"
    assert source.statement_draft is not None
    assert len(provider.requests) == 1


def test_claim_fit_two_is_qualified_only_and_retries_for_scope(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment(claim_fit=2)
    provider = FakeLunaAnalyst(
        [
            assessment.model_copy(
                update={
                    "canonical_factual_statement": (
                        "Among surveyed adults in this regional sample, the program reported a "
                        "different completion rate."
                    )
                }
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
    assert source.state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    assert source.score_decision is not None
    assert source.score_decision.placement.value == "qualified_only"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "statement",
    (
        "In this study, the completion rate was higher in the program group.",
        "The paper reports that the completion rate was higher in the program group.",
        "The article reports that the completion rate was higher in the program group.",
    ),
)
def test_ordinary_scoped_report_forms_satisfy_qualification(statement: str) -> None:
    assert statement_has_required_qualification(statement)


def test_historical_unrelated_assessment_and_analyst_identity_still_parse() -> None:
    run_id = uuid4()
    batch = _batch_input(
        run_id,
        policy_identity=V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY,
    )
    historical_result = V2EvidenceAnalystBatchResult(
        run_id=run_id,
        input=batch,
        source_results=(
            V2EvidenceAnalystSourceResult(
                run_id=run_id,
                source_id=batch.queued_candidates[0].source_id,
                direction=batch.queued_candidates[0].direction,
                state=V2EvidenceAnalystState.FAILED,
                failure="historical fixture",
            ),
        ),
        completed_at=NOW,
        policy_identity=V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY,
    )
    historical_model = V2EvidenceAnalystBatchResult.model_validate_json(
        historical_result.model_dump_json()
    )

    assert historical_model.policy_identity == V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY
    assert (
        V2EvidenceAnalystModelOutput.model_validate_json(
            _assessment(
                relationship=V2EvidenceRelationship.UNRELATED,
                claim_fit=2,
            ).model_dump_json()
        ).relationship_to_claim
        is V2EvidenceRelationship.UNRELATED
    )


def test_analyst_batch_result_cannot_change_its_captured_policy_identity() -> None:
    run_id = uuid4()
    batch = _batch_input(
        run_id,
        policy_identity=V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY,
    )
    failed = V2EvidenceAnalystSourceResult(
        run_id=run_id,
        source_id=batch.queued_candidates[0].source_id,
        direction=batch.queued_candidates[0].direction,
        state=V2EvidenceAnalystState.FAILED,
        failure="offline policy-identity fixture",
    )

    with pytest.raises(ValidationError, match="policy identity must match its input"):
        V2EvidenceAnalystBatchResult.model_validate(
            {
                "run_id": run_id,
                "input": batch,
                "source_results": (failed,),
                "completed_at": NOW,
                "policy_identity": V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
            }
        )


def test_v2_policy_keeps_historical_direction_and_prompt_contract(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(
        run_id,
        policy_identity=V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY,
    )
    assessment = _assessment(relationship=V2EvidenceRelationship.CHALLENGES)
    provider = FakeLunaAnalyst([assessment])

    result = run_v2_evidence_analyst(
        db_path=_prepare_db(tmp_path, run_id),
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert result.source_results[0].state is V2EvidenceAnalystState.FAILED
    assert provider.requests[0].prompt.version == (
        "post-phase13-luna-evidence-analyst-v8-round-four-reconciliation"
    )


def test_candidate_direction_must_match_its_queued_survivor() -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    both_directions = ResearchDirections(support_enabled=True, challenge_enabled=True)
    selection_input = batch.queue_result.input.model_copy(update={"directions": both_directions})
    queue_result = V2SourceSelectionQueueResult.model_validate(
        {
            **batch.queue_result.model_dump(mode="python"),
            "input": selection_input,
        }
    )
    queued = batch.queued_candidates[0]
    opposite_candidate = queued.candidate.model_copy(update={"stance": Stance.OPPOSING})
    opposite_input = V2EvidenceAnalystCandidateInput.model_validate(
        {
            **queued.model_dump(mode="python"),
            "direction": ResearchDirection.CHALLENGE,
            "candidate": opposite_candidate,
        }
    )

    with pytest.raises(ValueError, match="candidate direction must match its queued survivor"):
        V2EvidenceAnalystBatchInput.model_validate(
            {
                **batch.model_dump(mode="python"),
                "directions": both_directions,
                "queue_result": queue_result,
                "queued_candidates": (opposite_input,),
            }
        )


def test_unqualified_combined_statement_retries_with_bounded_scope_guidance(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    first = _assessment(claim_fit=2).model_copy(
        update={
            "canonical_factual_statement": (
                "Program participants completed more courses than comparison participants."
            )
        }
    )
    repaired = _assessment(claim_fit=2).model_copy(
        update={
            "canonical_factual_statement": (
                "In this study, program participants completed more courses than the "
                "comparison participants."
            )
        }
    )
    provider = FakeLunaAnalyst([first, repaired])
    db_path = _prepare_db(tmp_path, run_id)

    result = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    source = result.source_results[0]
    assert source.state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    assert source.statement_draft is not None
    assert source.statement_draft.draft_statement == repaired.canonical_factual_statement
    assert len(provider.requests) == 2
    assert "explicitly scope" in provider.requests[1].rendered_prompt


def test_unrelated_assessment_is_rejected_without_retry_or_statement_drafting(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    unrelated = _assessment(
        relationship=V2EvidenceRelationship.UNRELATED,
        claim_fit=2,
    ).model_copy(update={"canonical_factual_statement": None})
    provider = FakeLunaAnalyst([unrelated])

    result = run_v2_evidence_analyst(
        db_path=_prepare_db(tmp_path, run_id),
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    source = result.source_results[0]
    assert source.state is V2EvidenceAnalystState.REJECTED
    assert source.assessment is not None
    assert source.assessment.relationship_to_claim is V2EvidenceRelationship.UNRELATED
    assert source.statement_draft is None
    assert len(provider.requests) == 1


def test_v3_preserves_exception_scope_and_rejects_universal_overstatement() -> None:
    too_broad = _assessment().model_copy(
        update={"canonical_factual_statement": "Private surveillance has no restrictions."}
    )
    scoped = _assessment().model_copy(
        update={
            "canonical_factual_statement": (
                "For personal use in a private home, the household exemption may apply, but it "
                "does not establish that private surveillance is free of other restrictions."
            )
        }
    )
    source_context = (
        "The personal-use household exemption may apply to processing in a private home."
    )

    with pytest.raises(_RetryableAssessmentValidationError, match="preserve the source's stated"):
        _validate_contextual_exception_scope(too_broad, source_context)
    _validate_contextual_exception_scope(scoped, source_context)


def test_v3_exception_scope_gate_avoids_household_survey_false_positive() -> None:
    assessment = _assessment().model_copy(
        update={
            "canonical_factual_statement": (
                "The survey found an association between camera use and neighborhood concern."
            )
        }
    )

    _validate_contextual_exception_scope(
        assessment,
        "The household survey asked respondents about camera use and neighborhood concern.",
    )


def test_v3_exception_scope_gate_does_not_reject_stated_statutory_requirements() -> None:
    assessment = _assessment().model_copy(
        update={
            "canonical_factual_statement": (
                "Swedish companies must meet statutory confidentiality requirements."
            )
        }
    )
    _validate_contextual_exception_scope(
        assessment,
        "The Camera Surveillance Act contains statutory confidentiality "
        "requirements for companies.",
    )


def test_v3_exception_scope_gate_accepts_a_locally_negated_conclusion() -> None:
    assessment = _assessment().model_copy(
        update={
            "canonical_factual_statement": (
                "A household GDPR exemption does not establish that surveillance is free of "
                "restrictions."
            )
        }
    )

    _validate_contextual_exception_scope(
        assessment,
        "The GDPR household exemption may apply to personal data processing in the home.",
    )


def test_v3_exception_scope_gate_accepts_under_exemption_scope_language() -> None:
    assessment = _assessment().model_copy(
        update={
            "canonical_factual_statement": (
                "Under the exemption, personal household surveillance may qualify, subject to "
                "applicable law."
            )
        }
    )

    _validate_contextual_exception_scope(
        assessment,
        "The GDPR household exemption may apply to personal data processing in the home.",
    )


def test_v3_exception_scope_gate_does_not_ignore_a_separate_affirmative_overclaim() -> None:
    assessment = _assessment().model_copy(
        update={
            "canonical_factual_statement": (
                "The law does not establish that the policy is sound, and the exemption means "
                "surveillance is free of restrictions."
            )
        }
    )

    with pytest.raises(_RetryableAssessmentValidationError, match="cannot imply"):
        _validate_contextual_exception_scope(
            assessment,
            "The GDPR household exemption may apply to personal data processing in the home.",
        )


def test_v3_exception_scope_gate_does_not_reuse_negation_across_conjunction() -> None:
    assessment = _assessment().model_copy(
        update={
            "canonical_factual_statement": (
                "Under the exemption, the law does not establish that surveillance is allowed "
                "and private surveillance is free of restrictions."
            )
        }
    )

    with pytest.raises(_RetryableAssessmentValidationError, match="cannot imply"):
        _validate_contextual_exception_scope(
            assessment,
            "The GDPR household exemption may apply to personal data processing in the home.",
        )


def test_combined_analyst_output_is_used_without_a_duplicate_drafting_call(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment()
    provider = FakeLunaAnalyst([assessment])

    result = run_v2_evidence_analyst(
        db_path=_prepare_db(tmp_path, run_id),
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert result.source_results[0].state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    assert result.source_results[0].statement_draft is not None
    assert (
        result.source_results[0].statement_draft.draft_statement
        == assessment.canonical_factual_statement
    )
    assert len(provider.requests) == 1


def test_short_exact_selection_retries_with_adjacent_source_range() -> None:
    run_id = uuid4()
    source_id = uuid4()
    text = (
        "Opening context. The study reported a modest improvement among participants during "
        "the six month observation period, with outcomes recorded by the research team "
        "directly. The comparison used standard materials as a reference group and did not "
        "establish a causal effect. Closing context."
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/short-selection",
        retrieved_at=NOW,
        normalized_text=text,
        snapshot_sha256=sha256(text.encode("utf-8")).hexdigest(),
        word_count=len(text.split()),
        truncated=False,
        normalization_version="fixture-v1",
        created_at=NOW,
    )
    provider = FakeLunaAnalyst(
        [
            V2VerbatimQuoteSelection(
                selected_sentence_ranges=({"start_sentence": 2, "end_sentence": 2},)
            ),
            V2VerbatimQuoteSelection(
                selected_sentence_ranges=({"start_sentence": 2, "end_sentence": 3},)
            ),
        ]
    )

    result = _extract_source(
        source_id=source_id,
        direction=ResearchDirection.SUPPORT,
        exact_claim="The study reports an improvement.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=provider,
        clock=lambda: NOW,
    )

    assert result.state is V2ExtractionState.EXTRACTED
    assert result.attempts == 2
    assert "short" in provider.requests[-1].rendered_prompt


def test_exact_extraction_retry_requires_a_non_empty_contiguous_range() -> None:
    run_id = uuid4()
    _, snapshot = _exact_candidate(run_id, ResearchDirection.SUPPORT)
    source_id = uuid4()
    provider = FakeLunaAnalyst(
        [
            RuntimeError("empty selection"),
            V2VerbatimQuoteSelection(
                selected_sentence_ranges=({"start_sentence": 2, "end_sentence": 2},)
            ),
        ]
    )

    result = _extract_source(
        source_id=source_id,
        direction=ResearchDirection.SUPPORT,
        exact_claim="The regional program increases course completion.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=provider,
        clock=lambda: NOW,
    )

    assert result.state is V2ExtractionState.EXTRACTED
    assert len(provider.requests) == 2
    assert "return at least one source sentence range" in provider.requests[-1].rendered_prompt


@pytest.mark.parametrize(
    ("choice", "expected_model_name"),
    (
        (ModelChoice.GPT_6_LUNA_HIGH, "gpt-6-luna-high"),
        (ModelChoice.GPT_6_LUNA_XHIGH, "gpt-6-luna-xhigh"),
        (None, "mimo-v2.5-pro"),
    ),
)
def test_extraction_persists_selected_effort_and_preserves_legacy_model_name(
    tmp_path: Path,
    choice: ModelChoice | None,
    expected_model_name: str,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    queue_result = batch.queue_result
    source = queue_result.input.survivors[0]
    snapshot = batch.queued_candidates[0].snapshot
    query_id = source.search_provenance[0].query_id
    provenance = DiscoveryProvenance(
        provider=DiscoveryProvider.OPENALEX,
        query_id=query_id,
        query_text="regional course completion study",
        direction=source.direction,
        round_number=1,
        provider_rank=1,
        original_url=source.source_url,
    )
    item = NormalizedDiscoveryItem(
        run_id=run_id,
        item_id=uuid4(),
        provider=DiscoveryProvider.OPENALEX,
        query_id=query_id,
        query_text=provenance.query_text,
        direction=source.direction,
        round_number=1,
        provider_rank=1,
        source_url=source.source_url,
        canonical_url=source.source_url,
        provenance_chain=(provenance,),
        discovered_at=NOW,
    )
    cluster = SourceCluster(
        cluster_id=source.source_id,
        preferred_url=source.source_url,
        canonical_url=source.source_url,
        item_ids=(item.item_id,),
        provider_references=(
            DiscoveryProviderReference(
                provider=DiscoveryProvider.OPENALEX,
                item_id=item.item_id,
                provider_rank=1,
            ),
        ),
        query_references=(query_id,),
        metadata_provenance=(provenance,),
    )
    discovery = V2DiscoveryScoutOutput(
        run_id=run_id,
        directions=queue_result.input.directions,
        items=(item,),
        clusters=(cluster,),
        scout_batches=(),
        scout_audits=(),
        completed_at=NOW,
    )
    acquisition = V2AcquisitionProbeOutput(
        run_id=run_id,
        directions=queue_result.input.directions,
        acquisitions=(
            V2AcquiredSource(
                cluster_id=source.source_id,
                direction=source.direction,
                snapshot=snapshot,
                provider=V2AcquisitionProvider.WIGOLO,
            ),
        ),
        attempts=(),
        probes=(
            V2ProbeResult(
                cluster_id=source.source_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot.snapshot_sha256,
                succeeded=True,
            ),
        ),
        survivors=(),
        completed_at=NOW,
    )
    if choice is None:
        routing = _routing()
    else:
        stage_models = StageModelSelections.model_validate(
            {
                **DEFAULT_STAGE_MODELS.model_dump(mode="json"),
                "extractor": choice.value,
            }
        )
        routing = V2RoutingConfig.from_environment(
            {"LUNA_API_KEY": "selected-openai", "MIMO_API_KEY": "selected-mimo"},
            repository_revision="extraction-effort-test",
            stage_models=stage_models,
        )
    db_path = _prepare_db(tmp_path, run_id)
    provider = FakeLunaAnalyst(
        [
            V2VerbatimQuoteSelection(
                selected_sentence_ranges=({"start_sentence": 2, "end_sentence": 2},)
            )
        ]
    )

    result = run_v2_exact_extraction(
        db_path=db_path,
        queue_result=queue_result,
        discovery_outputs=(discovery,),
        acquisition_outputs=(acquisition,),
        llm_provider=provider,
        routing_config=routing,
        clock=lambda: NOW,
    )
    resumed = run_v2_exact_extraction(
        db_path=db_path,
        queue_result=queue_result,
        discovery_outputs=(discovery,),
        acquisition_outputs=(acquisition,),
        llm_provider=provider,
        routing_config=routing,
        clock=lambda: NOW,
    )

    candidate = result.sources[0].candidate
    assert candidate is not None
    assert candidate.extraction_model_name == expected_model_name
    assert resumed == result
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    ("direction", "cross_direction_relationship"),
    (
        (ResearchDirection.SUPPORT, V2EvidenceRelationship.CHALLENGES),
        (ResearchDirection.CHALLENGE, V2EvidenceRelationship.SUPPORTS),
    ),
)
def test_relationship_is_independent_of_search_direction(
    tmp_path: Path,
    direction: ResearchDirection,
    cross_direction_relationship: V2EvidenceRelationship,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id, direction=direction)
    assessment = _assessment(relationship=cross_direction_relationship)
    provider = FakeLunaAnalyst([assessment])
    db_path = _prepare_db(tmp_path, run_id)
    result = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    source = result.source_results[0]
    assert source.state is V2EvidenceAnalystState.READY_FOR_ADMISSION
    assert source.candidate == batch.queued_candidates[0].candidate
    assert source.assessment is not None
    assert source.assessment.relationship_to_claim is cross_direction_relationship
    assert source.statement_draft is not None
    assert len(source.analyst_attempt_ids) == 1
    assert not hasattr(result, "ledger_records")
    assert all(
        item.status is ModelAttemptStatus.COMPLETED
        for item in read_model_route_attempts(db_path, run_id)
    )


def test_semantic_analyst_failure_retains_returned_provider_usage(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    invalid_assessment = _assessment().model_copy(update={"canonical_factual_statement": None})
    provider = FakeLunaAnalyst([invalid_assessment])
    db_path = _prepare_db(tmp_path, run_id)

    result = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )

    assert result.source_results[0].state is V2EvidenceAnalystState.FAILED
    attempts = read_model_route_attempts(db_path, run_id)
    assert len(attempts) == 1
    assert attempts[0].status is ModelAttemptStatus.FAILED
    assert attempts[0].usage == ModelUsageMetadata(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cost_usd=Decimal("0.0012"),
    )


def test_transient_analyst_failure_is_terminal_after_one_attempt(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    provider = FakeLunaAnalyst(
        [
            RuntimeError("temporary Luna outage"),
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
    assert result.source_results[0].state is V2EvidenceAnalystState.FAILED
    attempts = read_model_route_attempts(db_path, run_id)
    assert [item.status for item in attempts].count(ModelAttemptStatus.FAILED) == 1
    assert [item.status for item in attempts].count(ModelAttemptStatus.COMPLETED) == 0


def test_terminal_analyst_provider_failure_aborts_the_batch(tmp_path: Path) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    provider = FakeLunaAnalyst(
        [
            MimoProviderError(
                MimoFailureCode.AUTHENTICATION,
                "Luna authentication failed",
                retryable=False,
            )
        ]
    )
    db_path = _prepare_db(tmp_path, run_id)

    with pytest.raises(LLMProviderExecutionError, match="Luna authentication failed"):
        run_v2_evidence_analyst(
            db_path=db_path,
            batch_input=batch,
            llm_provider=provider,
            routing_config=_routing(),
            clock=lambda: NOW,
        )

    assert len(provider.requests) == 1
    attempts = read_model_route_attempts(db_path, run_id)
    assert len(attempts) == 1
    assert attempts[0].status is ModelAttemptStatus.FAILED


def test_fresh_analyzer_result_does_not_trigger_reviewer_revision(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment()
    provider = FakeLunaAnalyst([assessment])
    db_path = _prepare_db(tmp_path, run_id)
    analyzed = run_v2_evidence_analyst(
        db_path=db_path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match="Reviewer-ready"):
        revise_v2_canonical_statement(
            db_path=db_path,
            batch_input=batch,
            source_result=analyzed.source_results[0],
            reviewer_rationale="Retain the sample size and six-month observation window.",
            llm_provider=provider,
            routing_config=_routing(),
            clock=lambda: NOW,
        )
    assert len(provider.requests) == 1
    assert len(read_model_route_attempts(db_path, run_id)) == 1


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
