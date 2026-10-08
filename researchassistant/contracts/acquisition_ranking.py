"""Discovery-to-acquisition audit, distinct from final evidence recommendation."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from researchassistant.contracts.model_contracts import StrictModel


class V2ClusterAcquisitionDisposition(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: UUID
    disposition: Literal[
        "not_scouted",
        "scout_skipped",
        "cap_prevented",
        "excluded_prior",
        "duplicate",
        "unavailable",
        "fetched_unusable",
        "usable",
    ]
    shortlisted: bool


class V2AcquisitionRankingAudit(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: int = Field(strict=True, ge=1, le=4)
    ranking_identity: Literal["source-candidate-ranking-v2"] = "source-candidate-ranking-v2"
    raw_hits: int = Field(strict=True, ge=0)
    deduplicated_works: int = Field(strict=True, ge=0)
    scouted_candidates: int = Field(strict=True, ge=0)
    acquisition_shortlisted_clusters: int = Field(strict=True, ge=0, le=25)
    fetched_documents: int = Field(strict=True, ge=0, le=25)
    usable_survivors: int = Field(strict=True, ge=0, le=25)
    dispositions: tuple[V2ClusterAcquisitionDisposition, ...] = Field(max_length=300)

    @model_validator(mode="after")
    def coherent_counts(self) -> V2AcquisitionRankingAudit:
        if len({item.cluster_id for item in self.dispositions}) != len(self.dispositions):
            raise ValueError(
                "every discovered cluster requires exactly one acquisition disposition"
            )
        if self.deduplicated_works != len(
            self.dispositions
        ) or self.acquisition_shortlisted_clusters != sum(
            item.shortlisted for item in self.dispositions
        ):
            raise ValueError("acquisition audit count conflicts with cluster membership")
        if (
            not self.usable_survivors
            <= self.fetched_documents
            <= self.acquisition_shortlisted_clusters
        ):
            raise ValueError("acquisition audit stages have contradictory counts")
        return self


class V2DiscoveryPipelineCounters(StrictModel):
    """Fresh derived run counts; historical count fields keep their original meaning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    raw_hits: int = Field(strict=True, ge=0)
    deduplicated_works: int = Field(strict=True, ge=0)
    scouted_candidates: int = Field(strict=True, ge=0)
    acquisition_shortlisted_clusters: int = Field(strict=True, ge=0)
    fetched_documents: int = Field(strict=True, ge=0)
    usable_survivors: int = Field(strict=True, ge=0)
    evidence_admissions: int = Field(strict=True, ge=0)
