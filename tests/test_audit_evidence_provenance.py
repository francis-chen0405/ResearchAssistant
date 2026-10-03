"""Regressions for binding exact candidates to their immutable source snapshot."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from researchassistant.common.utils import derive_quote_block_id
from researchassistant.contracts.model_contracts import SourceSnapshot
from researchassistant.contracts.model_evidence import V2EvidenceAnalystCandidateInput
from researchassistant.contracts.model_research import ResearchDirection
from researchassistant.evidence.evidence_core import verify_candidate_against_snapshot
from tests.test_phase4 import (
    _admission_request,
    _admit,
    _approved_review,
    _decision,
    _draft,
    _snapshot_and_candidate,
)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("run_id", lambda snapshot: uuid4(), "run_id"),
        ("retrieval_attempt_id", lambda snapshot: uuid4(), "retrieval_attempt_id"),
        ("source_url", lambda snapshot: "https://forged.example/source", "source_url"),
        (
            "retrieved_at",
            lambda snapshot: snapshot.retrieved_at + timedelta(seconds=1),
            "retrieved_at",
        ),
        (
            "snapshot_created_at",
            lambda snapshot: snapshot.created_at + timedelta(seconds=1),
            "snapshot_created_at",
        ),
    ),
)
def test_snapshot_verifier_rejects_forged_candidate_provenance(
    field: str,
    value: Callable[[SourceSnapshot], object],
    message: str,
) -> None:
    snapshot, candidate = _snapshot_and_candidate()
    fields = candidate.model_dump(mode="python")
    fields[field] = value(snapshot)
    if field == "source_url":
        fields["quote_block_id"] = derive_quote_block_id(
            fields["source_url"],
            fields["snapshot_sha256"],
            candidate.segment_offsets,
        )
    forged = type(candidate).model_validate(fields)

    with pytest.raises(ValueError, match=message):
        verify_candidate_against_snapshot(snapshot, forged)


def test_v2_analyst_candidate_contract_rejects_mismatched_retrieval_and_url() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    fields = candidate.model_dump(mode="python")
    fields["retrieval_attempt_id"] = uuid4()
    forged = type(candidate).model_validate(fields)

    with pytest.raises(ValidationError, match="retrieval attempt"):
        V2EvidenceAnalystCandidateInput(
            source_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            candidate=forged,
            snapshot=snapshot,
        )

    fields = candidate.model_dump(mode="python")
    fields["source_url"] = "https://forged.example/source"
    fields["quote_block_id"] = derive_quote_block_id(
        fields["source_url"], fields["snapshot_sha256"], candidate.segment_offsets
    )
    forged = type(candidate).model_validate(fields)
    with pytest.raises(ValidationError, match="source URL"):
        V2EvidenceAnalystCandidateInput(
            source_id=uuid4(),
            direction=ResearchDirection.SUPPORT,
            candidate=forged,
            snapshot=snapshot,
        )


def test_ledger_admission_inherits_snapshot_provenance_guard() -> None:
    snapshot, candidate = _snapshot_and_candidate()
    fields = candidate.model_dump(mode="python")
    fields["source_url"] = "https://forged.example/source"
    fields["quote_block_id"] = derive_quote_block_id(
        fields["source_url"], fields["snapshot_sha256"], candidate.segment_offsets
    )
    forged = type(candidate).model_validate(fields)
    decision = _decision(forged)
    statement = "The study reported 50% growth among surveyed adults."
    draft = _draft(forged, decision, statement)
    review = _approved_review(forged, draft)
    request = _admission_request(
        snapshot,
        forged,
        decision,
        draft,
        review,
        statement=statement,
    )

    with pytest.raises(ValueError, match="source_url"):
        _admit(request)
