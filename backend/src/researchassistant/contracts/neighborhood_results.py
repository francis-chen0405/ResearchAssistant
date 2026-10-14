"""Recorded scholarly identity and neighborhood response shapes; no transport."""

from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict, Field

from researchassistant.contracts.model_contracts import StrictModel
from researchassistant.contracts.search import SearchResult

MAX_NEIGHBOR_RESULTS = 10


class NeighborhoodStatus(StrEnum):
    RESOLVED = "resolved"
    UNSUPPORTED = "unsupported"
    EMPTY = "empty"
    MALFORMED = "malformed"


class NeighborhoodRelation(StrEnum):
    REFERENCES = "references"
    RELATED = "related"
    CITING = "citing"


class ResolvedOpenAlexWork(StrictModel):
    """Small immutable, verified identity and bounded neighborhood for one work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    openalex_id: str
    doi: str | None = None
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = Field(default=None, ge=1000, le=9999)
    work_type: str | None = None
    is_retracted: bool | None = None
    # OpenAlex documents is_retracted but no is_withdrawn work attribute.
    is_withdrawn: bool | None = None
    referenced_work_ids: tuple[str, ...] | None = Field(
        default=None, max_length=MAX_NEIGHBOR_RESULTS
    )
    related_work_ids: tuple[str, ...] | None = Field(default=None, max_length=MAX_NEIGHBOR_RESULTS)
    results: tuple[SearchResult, ...] = Field(max_length=MAX_NEIGHBOR_RESULTS)


class NeighborhoodResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: NeighborhoodStatus
    relation: NeighborhoodRelation | None = None
    work: ResolvedOpenAlexWork | None = None
    results: tuple[SearchResult, ...] = Field(default=(), max_length=MAX_NEIGHBOR_RESULTS)
