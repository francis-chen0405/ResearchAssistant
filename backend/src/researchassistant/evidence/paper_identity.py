"""Conservative DOI anchors from metadata, publisher locations and PMC headers."""

from __future__ import annotations

import re
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from researchassistant.contracts.discovery_v2 import normalize_doi
from researchassistant.contracts.models import SourceSnapshot


def paper_title_key(title: str | None) -> str:
    text = (title or "").split("|")[0]
    text = re.sub(r"\s+-\s+PMC\s*$", "", text, flags=re.I)
    return " ".join(re.findall(r"\w+", text.casefold()))


def confirmed_paper_anchor(
    snapshot: SourceSnapshot, title: str | None, metadata_dois: tuple[str, ...]
) -> tuple[str, str] | None:
    """Require a single consistent DOI; ignore arbitrary DOI mentions in body text."""
    anchors: list[tuple[str, str]] = []
    for value in metadata_dois:
        try:
            anchors.append((normalize_doi(value), "metadata"))
        except ValueError:
            return None
    url = urlsplit(snapshot.source_url)
    host = (url.hostname or "").casefold()
    path = unquote(url.path)
    located = None
    if host in {"doi.org", "dx.doi.org"}:
        located = path.lstrip("/")
    elif host in {"nature.com", "www.nature.com"} and path.startswith("/articles/"):
        article = path.removeprefix("/articles/").removesuffix(".pdf").rstrip("/")
        if re.fullmatch(r"(?:s\d[\w.-]+|ncomms\d+)", article, flags=re.I):
            located = "10.1038/" + article
    if located:
        try:
            anchors.append((normalize_doi(located), "publisher_url"))
        except ValueError:
            return None
    title_key = paper_title_key(title)
    if (
        host == "pmc.ncbi.nlm.nih.gov"
        and re.fullmatch(r"/articles/PMC\d+/?", path)
        and len(title_key) >= 24
    ):
        header = snapshot.normalized_text[:6000]
        matches = tuple(re.finditer(r"(?im)^.{0,80}\bdoi\s*:\s*(10\.\d{4,9}/\S+)", header))
        if len(matches) == 1:
            match = matches[0]
            following = paper_title_key(header[match.end() : match.end() + 1000])
            if following.startswith(title_key):
                try:
                    anchors.append((normalize_doi(match[1]), "pmc_header"))
                except ValueError:
                    return None
    if not anchors or len({doi for doi, _ in anchors}) != 1:
        return None
    if sha256(snapshot.normalized_text.encode()).hexdigest() != snapshot.snapshot_sha256:
        raise ValueError("paper identity snapshot hash differs from its content")
    return anchors[0]
