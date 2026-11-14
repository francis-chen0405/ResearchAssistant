"""Reader-facing labels shared by summaries, exports and the result page.

This module is the single owner of source labelling. It never invents
metadata: a missing value stays missing (``None``) for the result page, and the
export wording keeps its explicit "not recorded" phrases.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from researchassistant.contracts.discovery_v2 import normalize_doi

if TYPE_CHECKING:
    from researchassistant.api.inspection_contracts import V2EvidenceDisplayItem


@dataclass(frozen=True)
class _Publisher:
    """Host facts the generic rule cannot infer from the address alone."""

    name: str | None  # None: a file or site host that does not identify the publisher
    kind: str | None = None  # set only when the host itself establishes the type
    interest: str | None = None  # a documented commercial interest; unknown is not none


# The one data table. Unknown hosts never imply a source type or an interest.
PUBLISHERS: dict[str, _Publisher] = {
    "flocksafety.com": _Publisher(
        "Flock Safety",
        "Vendor blog",
        "Flock Safety publishes this source and has a commercial interest in ALPR products.",
    ),
    "linkedin.com": _Publisher("LinkedIn", "Social post"),
    "x.com": _Publisher("X", "Social post"),
    "twitter.com": _Publisher("X", "Social post"),
    "aclu.org": _Publisher("ACLU"),
    "voiceofsandiego.org": _Publisher("Voice of San Diego"),
    "studydaddy.com": _Publisher("StudyDaddy"),
    "ojp.gov": _Publisher("Office of Justice Programs"),
    "nij.ojp.gov": _Publisher("National Institute of Justice"),
    "everycrsreport.com": _Publisher("EveryCRSReport"),
    "policeforum.org": _Publisher("Police Executive Research Forum"),
    "ncbi.nlm.nih.gov": _Publisher("NCBI (National Library of Medicine)"),
    "squarespace.com": _Publisher(None),
    "amazonaws.com": _Publisher(None),
    "googleusercontent.com": _Publisher(None),
    "cloudfront.net": _Publisher(None),
}

_TWO_PART_SUFFIXES = frozenset(
    {"co.uk", "ac.uk", "gov.uk", "org.uk", "com.au", "edu.au", "gov.au", "co.nz", "co.jp"}
)
_TITLE_PUBLISHER_SUFFIX = re.compile(r"^(?P<title>.{8,}?)\s+\|\s+(?P<publisher>[^|]{2,60})$")
_AUTHOR_PREFIX = re.compile(r"^\s*(?:author\(s\)|authors?|by)\s*[:\-]?\s*", re.IGNORECASE)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _publisher(host: str) -> _Publisher | None:
    for domain in sorted(PUBLISHERS, key=len, reverse=True):
        if host == domain or host.endswith("." + domain):
            return PUBLISHERS[domain]
    return None


def _host_name(host: str) -> str | None:
    """Generic rule: a short label is an acronym; otherwise show the readable domain."""
    if not host:
        return None
    labels = host.split(".")
    suffix_length = 2 if ".".join(labels[-2:]) in _TWO_PART_SUFFIXES else 1
    if len(labels) <= suffix_length:
        return host
    label = labels[-suffix_length - 1]
    domain = ".".join(labels[-suffix_length - 1 :])
    if "-" in label:
        return " ".join(part.capitalize() for part in label.split("-") if part)
    if len(label) <= 4:
        return label.upper()
    return domain


def _classify(host: str, source_type: str | None) -> tuple[str | None, str | None, str | None]:
    kind = (source_type or "").lower().replace("_", " ")
    design: str | None = None
    if re.search(r"observational|non[ -]?randomi[sz]ed|not randomi[sz]ed", kind):
        design = "Observational study"
    elif re.search(r"\brandomi[sz]ed\b", kind):
        design = "Randomized trial"
    publisher = _publisher(host)
    if publisher is not None and publisher.kind is not None:
        return publisher.kind, design, publisher.interest
    interest = publisher.interest if publisher else None
    if re.search(r"op[ -]?ed|editorial|opinion", kind):
        return "Op-ed", design, interest
    if "working paper" in kind:
        return "Working paper", design, interest
    if re.search(r"government|agency report", kind):
        return "Government summary", design, interest
    if "advocacy" in kind:
        return "Advocacy group", design, interest
    if re.search(r"vendor|company blog", kind):
        return "Vendor source", design, interest
    if re.search(r"peer.?review|journal|scholarly|research paper", kind):
        return "Research publication", design, interest
    return None, design, interest


def citation(item: V2EvidenceDisplayItem) -> str:
    publication = item.verified_publication
    authors = publication.authors if publication else item.authors
    date = publication.publication_date if publication else item.publication_date
    venue = publication.venue if publication else item.publication_venue
    author = (
        (authors[0] + (" et al." if len(authors) > 1 else "")) if authors else "Author not recorded"
    )
    year = re.search(r"(?:18|19|20)\d{2}", date or "")
    return (
        f"{author} · {year[0] if year else 'Year not recorded'} · {venue or 'Venue not recorded'}"
    )


def source_labels(item: V2EvidenceDisplayItem) -> tuple[str, str, str | None]:
    """Export wording: explicit "not recorded" phrases for missing labels."""
    host = _host(item.source_url)
    kind, design, conflict = _classify(host, item.source_type)
    recorded = (item.source_type or "").lower().replace("_", " ")
    if kind is None:
        kind = (
            "Source type not recorded"
            if not recorded or recorded == "general web"
            else "Publication type not recorded"
        )
    return kind, design or "Study design not recorded", conflict


@dataclass(frozen=True)
class SourceDisplay:
    """Result-page labels for one source; ``None`` means not recorded."""

    heading: str
    source_name: str | None
    source_kind: str | None
    study_design: str | None
    publisher_interest: str | None
    year: str | None
    lead_author: str | None


def _people(authors: Iterable[str]) -> list[str]:
    people: list[str] = []
    for entry in authors:
        cleaned = _AUTHOR_PREFIX.sub("", entry or "").strip()
        parts = [cleaned] if not cleaned else re.split(r"\s*(?:;|,(?!\s*(?:jr|sr)\b))\s*", cleaned)
        for part in parts:
            name = part.strip()
            # A single token (an uploader handle, an address) is not a person's name.
            if not name or "@" in name or " " not in name:
                continue
            people.append(name)
    return people


def source_display(
    *,
    title: str | None,
    display_title: str,
    source_url: str,
    source_type: str | None = None,
    publication_date: str | None = None,
    item: V2EvidenceDisplayItem | None = None,
) -> SourceDisplay:
    """Readable heading, publisher name and labels without inventing metadata."""
    host = _host(source_url)
    publisher = _publisher(host)
    verified = item.verified_publication if item else None
    recorded_type = item.source_type if item and item.source_type else source_type
    kind, design, interest = _classify(host, recorded_type)
    heading = display_title
    title_publisher: str | None = None
    match = _TITLE_PUBLISHER_SUFFIX.match(display_title.strip())
    if match:
        heading, title_publisher = match["title"].strip(), match["publisher"].strip()
    if kind == "Social post":
        # A post's first line is not a title.
        heading = f"Post on {publisher.name if publisher and publisher.name else _host_name(host)}"
    if verified and verified.title:
        heading = verified.title
    if publisher is not None:
        name = publisher.name or title_publisher
    else:
        name = title_publisher or _host_name(host)
    if verified and verified.venue:
        name = verified.venue
    elif item and item.publication_venue and not publisher:
        name = item.publication_venue
    date = (
        verified.publication_date
        if verified
        else (item.publication_date if item and item.publication_date else publication_date)
    )
    year_match = re.search(r"(?:18|19|20)\d{2}", date or "")
    people = _people(verified.authors if verified else (item.authors if item else ()))
    lead = (people[0] + (" et al." if len(people) > 1 else "")) if people else None
    if heading.startswith("PDF file:"):
        filename = unquote(urlsplit(source_url).path).rsplit("/", 1)[-1]
        heading = filename or heading
    return SourceDisplay(
        heading=heading or source_url,
        source_name=name,
        source_kind=kind,
        study_design=design,
        publisher_interest=interest,
        year=year_match[0] if year_match else None,
        lead_author=lead,
    )


def claim_status(items: Iterable[V2EvidenceDisplayItem]) -> str:
    if any(item.relationship_to_claim.value == "challenges" for item in items):
        return "Challenging evidence admitted; claim not established"
    return "Claim not established by the admitted evidence"


def recorded_doi_url(item: V2EvidenceDisplayItem) -> str | None:
    if not item.doi:
        return None
    try:
        return "https://doi.org/" + normalize_doi(item.doi)
    except ValueError:
        return None
