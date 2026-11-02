"""Reader-facing labels shared by summaries and exports; never invent metadata."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from researchassistant.contracts.discovery_v2 import normalize_doi

if TYPE_CHECKING:
    from researchassistant.api.inspection_contracts import V2EvidenceDisplayItem


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
    host = (urlsplit(item.source_url).hostname or "").lower()
    kind = (item.source_type or "").lower().replace("_", " ")
    design = "Study design not recorded"
    if re.search(r"observational|non[ -]?randomi[sz]ed|not randomi[sz]ed", kind):
        design = "Observational study"
    elif re.search(r"\brandomi[sz]ed\b", kind):
        design = "Randomized trial"
    conflict = None
    if host == "flocksafety.com" or host.endswith(".flocksafety.com"):
        kind = "Vendor blog"
        conflict = (
            "Flock Safety publishes this source and has a commercial interest in ALPR products."
        )
    elif any(
        host == domain or host.endswith("." + domain)
        for domain in ("linkedin.com", "x.com", "twitter.com")
    ):
        kind = "Social post"
    elif re.search(r"op[ -]?ed|editorial|opinion", kind):
        kind = "Op-ed"
    elif "working paper" in kind:
        kind = "Working paper"
    elif re.search(r"government|agency report", kind):
        kind = "Government summary"
    elif "advocacy" in kind:
        kind = "Advocacy group"
    elif re.search(r"vendor|company blog", kind):
        kind = "Vendor source"
    elif re.search(r"peer.?review|journal|scholarly|research paper", kind):
        kind = "Research publication"
    elif not kind or kind == "general web":
        kind = "Source type not recorded"
    else:
        kind = "Publication type not recorded"
    return kind, design, conflict


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
