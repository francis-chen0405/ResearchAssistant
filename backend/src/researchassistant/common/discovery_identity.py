"""Pure scholarly metadata/provenance projections shared with persistence."""

from __future__ import annotations

import json
import re

from researchassistant.contracts.discovery_v2 import (
    V2GraphNeighborAction,
    V2RawDiscoveryCandidate,
    V2SeedEligibility,
    V2SourceLocation,
    V2WorkIdentity,
    discovery_id,
    normalize_doi,
)
from researchassistant.contracts.model_research import NormalizedDiscoveryItem
from researchassistant.contracts.neighborhood import V2NeighborhoodCheckpoint
from researchassistant.contracts.neighborhood_results import ResolvedOpenAlexWork
from researchassistant.contracts.search import SearchResult


def _work_id(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"(?:https://openalex.org/)?W[0-9]{1,20}", value):
        return "https://openalex.org/" + value.rsplit("/", 1)[-1]
    return None


def _metadata(item: NormalizedDiscoveryItem, key: str) -> object:
    for entry in item.provider_metadata:
        if entry.key == key:
            return json.loads(entry.value_json)
    return None


def _identity_authors(authors: tuple[str, ...]) -> tuple[str, ...] | None:
    """Omit unrepresentable optional metadata; never truncate an author's identity."""
    if not authors or any(not author or len(author) > 240 for author in authors):
        return None
    return authors


def pipeline_work_identity(item: NormalizedDiscoveryItem) -> V2WorkIdentity:
    external_id = _work_id(_metadata(item, "external_id"))
    year = (
        int(item.publication_date[:4])
        if item.publication_date and item.publication_date[:4].isdigit()
        else None
    )
    if not item.doi and not external_id:
        raise ValueError("pipeline seed lacks exact DOI/OpenAlex identifier")
    return V2WorkIdentity(
        grouping_key=f"doi:{item.doi}" if item.doi else external_id,
        doi=item.doi,
        provider_work_id=external_id,
        title=item.title,
        authors=_identity_authors(item.authors),
        publication_year=year,
        resolution="verified_identifiers" if item.doi else "provider_identity",
    )


def _resolved_identity(work: ResolvedOpenAlexWork) -> V2WorkIdentity:
    doi = normalize_doi(work.doi) if work.doi else None
    return V2WorkIdentity(
        grouping_key=f"doi:{doi}" if doi else work.openalex_id,
        doi=doi,
        provider_work_id=work.openalex_id,
        title=work.title,
        authors=_identity_authors(work.authors),
        publication_year=work.year,
        resolution="verified_identifiers" if doi else "provider_identity",
    )


def _matches_seed(seed: V2SeedEligibility, work: ResolvedOpenAlexWork) -> bool:
    identity = _resolved_identity(work)
    expected = seed.work
    if (
        work.is_retracted is True
        or work.is_withdrawn is True
        or work.work_type in {"retraction", "withdrawn"}
    ):
        return False
    if expected.doi and identity.doi != expected.doi:
        return False
    if expected.provider_work_id and identity.provider_work_id != expected.provider_work_id:
        return False
    if expected.publication_year and identity.publication_year != expected.publication_year:
        return False

    def title_key(value: str) -> str:
        return " ".join(re.findall(r"\w+", value.casefold()))

    if expected.title and title_key(identity.title or "") != title_key(expected.title):
        return False
    if expected.authors and identity.authors:
        observed_authors = {x.casefold() for x in expected.authors}
        resolved_authors = {x.casefold() for x in identity.authors}
        # arXiv/PubMed discovery expose a comma-joined author display string.
        # Compare exact rendered prefixes of the resolved names, rather than
        # splitting commas inside names or accepting arbitrary substring matches.
        joined_prefix = len(expected.authors) == 1 and any(
            expected.authors[0].casefold() == separator.join(identity.authors[:count]).casefold()
            for count in range(1, len(identity.authors) + 1)
            for separator in (", ", "; ")
        )
        # Providers can expose only a prefix/subset of the author list. Additional
        # compatible coauthors are missing metadata, not an identity contradiction.
        if not (
            joined_prefix
            or observed_authors <= resolved_authors
            or resolved_authors <= observed_authors
        ):
            return False
    return True


def neighbor_work_identity(item: SearchResult) -> V2WorkIdentity:
    wid = _work_id(item.metadata.external_id)
    if wid is None:
        raise ValueError("neighbor requires canonical provider identity")
    doi = normalize_doi(item.metadata.doi) if item.metadata.doi else None
    return V2WorkIdentity(
        grouping_key=f"doi:{doi}" if doi else wid,
        doi=doi,
        provider_work_id=wid,
        title=item.title or None,
        authors=_identity_authors(tuple(item.metadata.author.split("; ")))
        if item.metadata.author
        else None,
        publication_year=int(item.metadata.published_at[:4])
        if item.metadata.published_at
        else None,
        resolution="verified_identifiers" if doi else "provider_identity",
    )


def raw_neighbor_candidate(
    action: V2GraphNeighborAction, cp: V2NeighborhoodCheckpoint, item: SearchResult
) -> V2RawDiscoveryCandidate:
    """Derive raw metadata only from an exactly reparsed provider record."""
    work = neighbor_work_identity(item)
    wid = work.provider_work_id
    if wid is None:
        raise ValueError("neighbor requires canonical provider identity")
    ckey = f"neighbor/{action.artifact_id}/{wid.rsplit('/', 1)[-1]}"
    raw = V2RawDiscoveryCandidate(
        run_id=action.run_id,
        artifact_id=discovery_id(action.run_id, "V2RawDiscoveryCandidate", ckey),
        identity_key=ckey,
        operation_id=action.artifact_id,
        attempt_id=cp.attempt_id,
        response_hash=cp.response_hash,
        provider=action.provider,
        direction=action.direction,
        round_number=action.round_number,
        provider_rank=item.rank,
        work=work,
        abstract=item.metadata.abstract,
        study_design=item.metadata.work_type,
        locations=tuple(
            V2SourceLocation(
                url=url,
                same_work_basis="provider_identity",
                kind="pdf" if url == item.metadata.pdf_url else "landing",
            )
            for url in dict.fromkeys(
                x
                for x in (
                    item.original_url,
                    item.metadata.pdf_url,
                    item.metadata.full_text_url,
                )
                if x
            )
        ),
    )
    return raw
