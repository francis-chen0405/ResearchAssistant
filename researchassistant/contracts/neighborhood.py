"""Typed deterministic offers and physical parser checkpoints for one-hop discovery."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from providers.openalex_neighborhood import ResolvedOpenAlexWork
from providers.search import SearchResult
from researchassistant.contracts.discovery_v2 import (
    Digest,
    V2DiscoveryArtifact,
    V2GraphNeighborAction,
    V2SeedEligibility,
)


class V2SeedSelection(V2DiscoveryArtifact):
    seed_identity: Literal["source-seed-expansion-v2"] = "source-seed-expansion-v2"
    round_number: int = Field(strict=True, ge=1, le=4)
    seeds: tuple[V2SeedEligibility, ...] = Field(default=(), max_length=3)
    status: Literal["offered", "skipped"]
    reason: str = Field(min_length=1, max_length=240)
    relationship_priority: tuple[Literal["references", "citing", "related"], ...] = (
        "references",
        "citing",
        "related",
    )
    tie_break: Literal["preview_relevance_then_work_id"] = "preview_relevance_then_work_id"

    @model_validator(mode="after")
    def owned(self) -> V2SeedSelection:
        if any(seed.run_id != self.run_id or not seed.eligible for seed in self.seeds):
            raise ValueError("seed offers must be eligible and owned")
        if bool(self.seeds) != (self.status == "offered"):
            raise ValueError("seed selection status differs from offers")
        return self


class V2NeighborhoodCheckpoint(V2DiscoveryArtifact):
    action: V2GraphNeighborAction
    phase: Literal["identity", "neighbors"]
    attempt_id: UUID
    response_hash: Digest
    parsed_hash: Digest
    work: ResolvedOpenAlexWork | None = None
    results: tuple[SearchResult, ...] = Field(default=(), max_length=10)
    status: Literal["resolved", "unsupported", "empty", "malformed"]

    @model_validator(mode="after")
    def owned(self) -> V2NeighborhoodCheckpoint:
        if self.action.run_id != self.run_id:
            raise ValueError("neighborhood checkpoint has cross-run action")
        from researchassistant.contracts.discovery_v2 import discovery_hash

        if self.parsed_hash != discovery_hash(
            (
                self.work.model_dump_json() if self.work else None,
                tuple(x.model_dump_json() for x in self.results),
                self.status,
            )
        ):
            raise ValueError("neighborhood parsed receipt differs")
        return self


class V2NeighborhoodResponse(V2DiscoveryArtifact):
    """Bounded exact provider bytes, stored atomically with the physical completion."""

    operation_id: UUID
    attempt_id: UUID
    response_hash: Digest
    content: str = Field(max_length=262144)

    @model_validator(mode="after")
    def exact_response(self) -> V2NeighborhoodResponse:
        import json
        from hashlib import sha256

        from researchassistant.contracts.discovery_v2 import safe_location

        if (
            len(self.content.encode()) > 262144
            or sha256(self.content.encode()).hexdigest() != self.response_hash
        ):
            raise ValueError("neighborhood response bytes/hash differ or exceed bound")

        def check(value: object) -> None:
            if isinstance(value, dict):
                if any(
                    str(key).casefold()
                    in {"api_key", "authorization", "access_token", "secret", "password"}
                    for key in value
                ):
                    raise ValueError("credential-bearing response cannot be persisted")
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
            elif isinstance(value, str) and value.startswith(("http://", "https://")):
                safe_location(value)

        check(json.loads(self.content))
        return self
