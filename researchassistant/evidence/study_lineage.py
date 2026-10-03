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

from researchassistant.contracts.model_contracts import NonEmptyStr, StrictModel
from researchassistant.contracts.models import V2SourceSelectionCandidate


class StudyLineageNotice(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ids: tuple[UUID, ...] = Field(min_length=2)
    basis: Literal["matching_doi", "matching_title", "matching_archive_id"]
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
    archive_groups: dict[
        str, list[tuple[V2SourceSelectionCandidate, str | None, Literal["osf", "repec"]]]
    ] = defaultdict(list)
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
        archive_reference = _recognized_socarxiv_reference(candidate.source_url)
        if archive_reference is not None:
            archive_id, version, host_kind = archive_reference
            archive_groups[archive_id].append((candidate, version, host_kind))
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
    for archive_id, group in archive_groups.items():
        host_kinds = {host_kind for _, _, host_kind in group}
        if host_kinds != {"osf", "repec"}:
            continue
        identifiers = {_normalized_doi(item.doi) for item, _, _ in group} - {None}
        if len(identifiers) > 1:
            continue  # Conflicting registered identifiers defeat a weaker archive hint.
        source_ids = tuple(item.source_id for item, _, _ in group)
        if any(set(source_ids) <= set(item.source_ids) for item in notices):
            continue
        versions = sorted({version for _, version, _ in group}, key=lambda version: version or "")
        version_description = _archive_version_description(versions)
        notices.append(
            StudyLineageNotice(
                source_ids=source_ids,
                basis="matching_archive_id",
                explanation=(
                    f"These OSF and RePEc links share the recognized SocArXiv archive ID "
                    f"`{archive_id}`{version_description}. They may refer to versions of "
                    "the same preprint, but the identifier does not establish that the "
                    "captured texts or results are identical. The records remain separate; "
                    "separate links do not establish independent studies or replication."
                ),
            )
        )
    return tuple(notices)


def _recognized_socarxiv_reference(
    source_url: str,
) -> tuple[str, str | None, Literal["osf", "repec"]] | None:
    parsed = urlsplit(source_url)
    if parsed.scheme.casefold() != "https":
        return None
    netloc = parsed.netloc.casefold()
    if netloc == "osf.io":
        match = re.fullmatch(
            r"/preprints/socarxiv/([a-z0-9]{5})(?:_v([1-9]\d*))?/?",
            parsed.path.casefold(),
        )
        host_kind: Literal["osf", "repec"] = "osf"
    elif netloc == "ideas.repec.org":
        match = re.fullmatch(
            r"/p/osf/socarx/([a-z0-9]{5})(?:_v([1-9]\d*))?\.html",
            parsed.path.casefold(),
        )
        host_kind = "repec"
    else:
        return None
    if match is None:
        return None
    archive_id, version_number = match.groups()
    version = f"v{version_number}" if version_number is not None else None
    return archive_id, version, host_kind


def _archive_version_description(versions: list[str | None]) -> str:
    explicit_versions = [version for version in versions if version is not None]
    if len(explicit_versions) == len(versions) and len(set(explicit_versions)) == 1:
        return f" at version `{explicit_versions[0]}`"
    if len(explicit_versions) == len(versions) and len(set(explicit_versions)) > 1:
        return " at different versions " + " and ".join(
            f"`{version}`" for version in explicit_versions
        )
    if explicit_versions:
        labels = " and ".join(f"`{version}`" for version in explicit_versions)
        return f", with {labels} listed and at least one URL omitting its version"
    return " with no version stated in the URLs"


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
