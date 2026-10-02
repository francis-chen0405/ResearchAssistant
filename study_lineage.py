"""Conservative, read-only study lineage disclosure from discovery metadata.

These notices neither merge source families nor count independent studies. A title
match is a warning, not verified identity; discovery metadata is not evidence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Literal
from urllib.parse import unquote, urlsplit
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
    mirror_groups: dict[tuple[str, str], list[V2SourceSelectionCandidate]] = defaultdict(list)
    for candidate in candidates:
        doi = _normalized_doi(candidate.doi)
        if doi:
            doi_groups[doi].append(candidate)
        title = _normalized_study_title(candidate.title)
        if title:
            title_groups[title].append(candidate)
        mirror_key = _dated_slug_and_title(candidate)
        if mirror_key is not None:
            mirror_groups[mirror_key].append(candidate)
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
    for group in mirror_groups.values():
        if len(group) < 2:
            continue
        identifiers = {_normalized_doi(item.doi) for item in group} - {None}
        if len(identifiers) > 1:
            continue
        for index, first in enumerate(group):
            first_host = _http_host(first.source_url)
            for second in group[index + 1 :]:
                second_host = _http_host(second.source_url)
                if first_host is None or second_host is None or first_host == second_host:
                    continue
                source_ids = (first.source_id, second.source_id)
                if any(set(source_ids) <= set(item.source_ids) for item in notices):
                    continue
                notices.append(
                    StudyLineageNotice(
                        source_ids=source_ids,
                        basis="matching_title",
                        explanation=(
                            "These sources have the same dated article URL slug and "
                            "headline; one title includes a publisher suffix. They may "
                            "be mirrors of the same report. Identity is unverified; "
                            "the records remain separate and do not establish "
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


def _dated_slug_and_title(
    candidate: V2SourceSelectionCandidate,
) -> tuple[str, str] | None:
    title = _normalized_study_title(candidate.title)
    if title is None:
        return None
    parsed = urlsplit(candidate.source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    segments = [unquote(part).casefold() for part in parsed.path.split("/") if part]
    dated_slug = _dated_slug(segments)
    if dated_slug is None:
        return None
    base_title = _title_without_verified_publisher_suffix(candidate.title, parsed.hostname)
    normalized_title = _normalized_study_title(base_title)
    if normalized_title is None:
        return None
    return (dated_slug, normalized_title)


def _dated_slug(segments: list[str]) -> str | None:
    for index, segment in enumerate(segments):
        if re.fullmatch(r"20\d{2}", segment) and index + 2 < len(segments):
            month, day = segments[index + 1 : index + 3]
            if re.fullmatch(r"0?[1-9]|1[0-2]", month) and re.fullmatch(
                r"0?[1-9]|[12]\d|3[01]", day
            ):
                date = f"{segment}-{int(month):02d}-{int(day):02d}"
                slug_parts = segments[index + 3 :]
                if slug_parts:
                    return f"{date}/{_normalized_url_slug(slug_parts)}"
        dashed_date = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})", segment)
        if dashed_date is not None:
            year, month, day = dashed_date.groups()
            if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                slug_parts = segments[index + 1 :]
                if slug_parts:
                    date = f"{year}-{month}-{day}"
                    return f"{date}/{_normalized_url_slug(slug_parts)}"
    return None


def _normalized_url_slug(segments: list[str]) -> str:
    return "/".join("-".join(re.findall(r"[a-z0-9]+", segment.casefold())) for segment in segments)


def _title_without_verified_publisher_suffix(title: str | None, hostname: str) -> str | None:
    if title is None:
        return None
    suffix_match = re.search(r"\s+[—–-]\s+(.+)$", title)
    if suffix_match is None:
        return title
    publisher = suffix_match.group(1)
    host_label = hostname.casefold().removeprefix("www.").split(".", 1)[0]
    compact_publisher = re.sub(r"[^a-z0-9]", "", publisher.casefold())
    compact_host = re.sub(r"[^a-z0-9]", "", host_label)
    return title[: suffix_match.start()].strip() if compact_publisher == compact_host else title


def _http_host(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname.casefold().removeprefix("www.")
