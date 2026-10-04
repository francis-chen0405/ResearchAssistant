"""Inspection-only historical types; never contracts for new research or admission."""

from __future__ import annotations

from pydantic import ConfigDict, model_validator

from researchassistant.contracts.models import Entailment, LedgerRecord, Placement, StrictModel


class HistoricalRead:
    """Marks decoded historical values so persistence cannot re-admit them."""


class RecordCompatibilityResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_key: str
    artifact_type: str
    compatible: bool = False
    message: str


class RecordCompatibilityError(ValueError):
    def __init__(self, result: RecordCompatibilityResult) -> None:
        self.result = result
        super().__init__(f"{result.record_key}: {result.message}")


class AugustLedgerRecord(LedgerRecord, HistoricalRead):
    """Recorded phase8 two-axis contract, preserving its Strong/4 entailment."""

    @model_validator(mode="after")
    def validate_score_contract(self) -> AugustLedgerRecord:
        if (
            self.evidence_quality == self.claim_fit == self.ledger_score == 4
            and self.placement is Placement.SECONDARY
            and self.entailment is Entailment.STRONG
            and self.analyst_prompt_version == "phase8-analyst-v1"
            and self.reviewer_prompt_version == "phase8-reviewer-v2"
        ):
            return self
        super().validate_score_contract()
        return self
