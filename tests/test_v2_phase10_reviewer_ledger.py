from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from test_v2_phase9_luna_evidence_analyst import (
    NOW,
    _assessment,
    _batch_input,
    _draft,
    _prepare_db,
    _routing,
)

from agents.reviewer import ReviewerDecision
from agents.v2_evidence_analyst import run_v2_evidence_analyst
from agents.v2_reviewer_ledger import run_v2_reviewer_ledger
from models import (
    ModelUsageMetadata,
    Placement,
    ResearchDirections,
    ReviewerFailureCode,
    V2ReviewerLedgerBatchResult,
    V2ReviewerLedgerState,
)
from providers.llm import LLMProviderCapabilities, LLMRequest, LLMStage
from store import read_v2_ledger_admission


class Phase10Provider:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self, reviewer_decisions: list[ReviewerDecision]) -> None:
        self.reviewer_decisions = list(reviewer_decisions)
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> object:
        self.requests.append(request)
        if request.stage is LLMStage.ANALYST:
            if request.requested_output_type.__name__ == "V2EvidenceAnalystModelOutput":
                return _assessment()
            return _draft(
                _assessment(),
                (
                    "Among surveyed adults, 62 percent reported completing the assigned course "
                    "within six months."
                ),
            )
        decision = self.reviewer_decisions.pop(0)
        return decision.model_copy(
            update={"reviewed_statement": request.input_artifact.draft_statement}
        )

    def usage_for(
        self, request: LLMRequest, output: object, invocation_record: object
    ) -> ModelUsageMetadata:
        del request, output, invocation_record
        return ModelUsageMetadata(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost_usd=Decimal("0.001"),
        )


def _approved() -> ReviewerDecision:
    return ReviewerDecision(
        reviewed_statement="placeholder",
        approved=True,
        rationale="The statement is fully entailed and keeps its scope.",
    )


def _rejected() -> ReviewerDecision:
    return ReviewerDecision(
        reviewed_statement="placeholder",
        approved=False,
        failure_code=ReviewerFailureCode.MISSING_QUALIFICATION,
        rationale="The qualification must remain explicit.",
    )


def _run(
    tmp_path: Path,
    provider: Phase10Provider,
    *,
    claim_fit: int = 4,
    recommended: bool = True,
) -> tuple[str, V2ReviewerLedgerBatchResult]:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    batch = _batch_input(run_id)
    if claim_fit != 4:
        provider_assessment = _assessment(claim_fit=claim_fit)
        original_generate = provider.generate

        def generate(request: LLMRequest) -> object:
            if (
                request.stage is LLMStage.ANALYST
                and request.requested_output_type.__name__ == "V2EvidenceAnalystModelOutput"
            ):
                return provider_assessment
            return original_generate(request)

        provider.generate = generate  # type: ignore[method-assign]
    if not recommended:
        status = batch.queue_result.source_statuses[0].model_copy(
            update={
                "recommended": False,
                "recommendation_rank": None,
                "selection_rationale": None,
            }
        )
        queue = batch.queue_result.model_copy(
            update={
                "recommended_source_ids": (),
                "recommendation_rationales": (),
                "source_statuses": (status,),
            }
        )
        batch = batch.model_copy(update={"queue_result": queue})
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    return path, run_v2_reviewer_ledger(
        db_path=path,
        analyst_result=analyst,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )


def test_v2_reviewer_approval_admits_immutable_ledger_metadata(tmp_path: Path) -> None:
    path, result = _run(tmp_path, Phase10Provider([_approved()]))
    source = result.source_results[0]
    assert source.state is V2ReviewerLedgerState.ADMITTED
    assert source.ledger_record is not None
    assert source.review_results[0].reviewer_approval_id.startswith("rappr_v1_")
    restored, provenance = read_v2_ledger_admission(path, source.ledger_record.ledger_claim_id)
    assert restored == source.ledger_record
    assert provenance.recommended is True
    assert provenance.research_direction.value == "support"
    with sqlite3.connect(path) as conn, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE v2_ledger_admissions SET recommended = 0")


def test_v2_reviewer_rejection_revises_once_then_approves(tmp_path: Path) -> None:
    _, result = _run(tmp_path, Phase10Provider([_rejected(), _approved()]))
    source = result.source_results[0]
    assert source.state is V2ReviewerLedgerState.ADMITTED
    assert len(source.review_results) == 2
    assert source.review_results[0].approved is False
    assert source.review_results[1].approved is True


def test_v2_second_reviewer_rejection_never_enters_the_ledger(tmp_path: Path) -> None:
    _, result = _run(tmp_path, Phase10Provider([_rejected(), _rejected()]))
    source = result.source_results[0]
    assert source.state is V2ReviewerLedgerState.REVIEWER_REJECTED
    assert source.ledger_record is None
    assert len(source.review_results) == 2


def test_v2_qualified_only_and_nonrecommended_source_are_admitted(tmp_path: Path) -> None:
    _, result = _run(tmp_path, Phase10Provider([_approved()]), claim_fit=3, recommended=False)
    source = result.source_results[0]
    assert source.state is V2ReviewerLedgerState.ADMITTED
    assert source.ledger_record is not None
    assert source.ledger_record.placement is Placement.QUALIFIED_ONLY
    assert source.provenance.recommended is False


def test_v2_disabled_direction_is_rejected_before_reviewer_call(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    provider = Phase10Provider([_approved()])
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=_batch_input(run_id),
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    disabled_input = analyst.input.model_copy(
        update={"directions": ResearchDirections(support_enabled=False, challenge_enabled=True)}
    )
    disabled = analyst.model_copy(update={"input": disabled_input})
    with pytest.raises(ValueError, match="disabled research direction"):
        run_v2_reviewer_ledger(
            db_path=path,
            analyst_result=disabled,
            llm_provider=provider,
            routing_config=_routing(),
            clock=lambda: NOW,
        )


def test_v2_reviewer_ledger_restart_reuses_immutable_artifact(tmp_path: Path) -> None:
    path, first = _run(tmp_path, Phase10Provider([_approved()]))
    resumed = run_v2_reviewer_ledger(
        db_path=path,
        analyst_result=first.analyst_result,
        llm_provider=Phase10Provider([]),
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    assert resumed == first
