"""Immutable capture journal contracts, usable without acquisition execution."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.research_acquisition import (
    V2AcquiredSource,
    V2AcquisitionAttempt,
    V2AcquisitionProvider,
)
from researchassistant.contracts.research_directions import ResearchDirection
from researchassistant.contracts.scraping import ScrapeResponse, VerifiedAcquisitionPreflight


class V2AcquisitionCaptureStart(StrictModel):
    """Immutable dispatch record; absent completion means unknown exposure, never retry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    cluster_id: UUID
    direction: ResearchDirection
    url: str = Field(min_length=1)
    provider: V2AcquisitionProvider
    timeout_seconds: float = Field(gt=0, le=120)
    policy_identity: Literal["researchassistant-v2-phase-5-acquisition-probe-v4"]
    started_at: datetime
    verified_preflight: VerifiedAcquisitionPreflight | None = None


class V2AcquisitionCaptureResponse(StrictModel):
    """Persist returned data before snapshot construction or readability assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    start: V2AcquisitionCaptureStart
    attempt: V2AcquisitionAttempt
    response: ScrapeResponse | None = None
    verified_preflight: VerifiedAcquisitionPreflight | None = None


class V2AcquisitionCaptureCompletion(StrictModel):
    """One physical scraper outcome, including unusable and empty capture bytes.

    Empty text cannot inhabit SourceSnapshot's historical nonempty contract. Its
    exact response remains immutable here; failures without a response have no snapshot.
    Readability does not assert claim fit, evidence quality, or admission.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    start: V2AcquisitionCaptureStart
    attempt: V2AcquisitionAttempt
    response: ScrapeResponse | None = None
    source: V2AcquiredSource | None = None
    readable: bool = False
    verified_preflight: VerifiedAcquisitionPreflight | None = None

    @model_validator(mode="after")
    def validate_capture(self) -> V2AcquisitionCaptureCompletion:
        if self.run_id != self.start.run_id or (
            self.attempt.cluster_id != self.start.cluster_id
            or self.attempt.url != self.start.url
            or self.attempt.provider != self.start.provider
        ):
            raise ValueError("capture completion differs from its dispatch ownership")
        if self.attempt.succeeded != (
            self.response is not None and bool(self.response.text.strip())
        ):
            raise ValueError("capture attempt must preserve its actual response outcome")
        if self.source is not None:
            if self.response is None or (
                self.source.cluster_id != self.start.cluster_id
                or self.source.direction != self.start.direction
                or self.source.provider != self.start.provider
                or self.source.snapshot.run_id != self.run_id
                or self.source.snapshot.normalized_text != self.response.text
            ):
                raise ValueError("capture snapshot differs from its response or ownership")
        if self.attempt.succeeded != (self.source is not None):
            raise ValueError("nonempty successful captures require their immutable snapshot")
        if self.readable and self.source is None:
            raise ValueError("readable capture requires a snapshot")
        return self


# Preserve public class and pickle identity at the historical execution path.
V2AcquisitionCaptureStart.__module__ = "researchassistant.agents.v2_acquisition"
V2AcquisitionCaptureResponse.__module__ = "researchassistant.agents.v2_acquisition"
V2AcquisitionCaptureCompletion.__module__ = "researchassistant.agents.v2_acquisition"
