"""Typed Phase 8 input for the Claim Planner LLM boundary."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from models import StrictModel


class PlannerLLMInput(StrictModel):
    """Application-controlled Planner input; the model receives no routing controls."""

    run_id: UUID
    raw_claim: str = Field(min_length=1)
