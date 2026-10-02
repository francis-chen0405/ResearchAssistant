"""Conservative, read-only study lineage disclosure from discovery metadata.

These notices neither merge source families nor count independent studies. A title
match is a warning, not verified identity; discovery metadata is not evidence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from model_contracts import NonEmptyStr, StrictModel
from models import V2SourceSelectionCandidate


class StudyLineageNotice(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ids: tuple[UUID, ...] = Field(min_length=2)
    basis: Literal["matching_doi", "matching_title"]
    explanation: NonEmptyStr

    @model_validator(mode="after")
    def validate_sources(self) -> StudyLineageNotice:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("study lineage sources must be unique")
        return self


def build_study_lineage_notices(
    candidates: tuple[V2SourceSelectionCandidate, ...],
) -> tuple[StudyLineageNotice, ...]:
    """Disclose shared identifiers or possible mirrors without rewriting evidence."""
    if len({item.source_id for item in candidates}) != len(candidates):
        raise ValueError("study lineage requires unique source IDs")
    doi_groups: dict[str, list[V2SourceSelectionCandidate]] = defaultdict(list)
    title_groups: dict[str, list[V2SourceSelectionCandidate]] = defaultdict(list)
    for candidate in candidates:
        doi = _normalized_doi(candidate.doi)
        if doi:
            doi_groups[doi].append(candidate)
        title = _normalized_study_title(candidate.title)
        if title:
            title_groups[title].append(candidate)
    notices: list[StudyLineageNotice] = []
    for group in doi_groups.values():
        if len(group) > 1:
            notices.append(
                StudyLineageNotice(
                    source_ids=tuple(item.source_id for item in group),
                    basis="matching_doi",
                    explanation=(
                        "These sources carry the same DOI in discovery metadata. "
                        "Separate links do not establish independent studies or replication."
                    ),
                )
            )
    for group in title_groups.values():
        if len(group) < 2:
            continue
        identifiers = {_normalized_doi(item.doi) for item in group} - {None}
        if len(identifiers) > 1:
            continue  # Conflicting identifiers defeat a weaker title-only hint.
        source_ids = tuple(item.source_id for item in group)
        if any(set(source_ids) <= set(item.source_ids) for item in notices):
            continue
        notices.append(
            StudyLineageNotice(
                source_ids=source_ids,
                basis="matching_title",
                explanation=(
                    "These sources have matching study titles and may report the same study. "
                    "Identity is unverified; separate links do not establish "
                    "independent replication."
                ),
            )
        )
    return tuple(notices)


def _normalized_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized)
    normalized = re.sub(r"^doi:\s*", "", normalized)
    return normalized if re.fullmatch(r"10\.\d{4,9}/\S+", normalized) else None


def _normalized_study_title(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"^\s*working\s+paper\s*:\s*", "", value.casefold())
    normalized = " ".join(re.sub(r"[^\w\s]", " ", normalized).split())
    # Avoid broad labels such as "Results" or "Impact assessment".
    return normalized if len(normalized) >= 35 and len(normalized.split()) >= 6 else None
