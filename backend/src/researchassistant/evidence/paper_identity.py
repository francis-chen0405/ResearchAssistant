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


_CAMBRIDGE_REVIEW_TITLE = re.compile(
    r"^(?:Review|Decision):\s*(?P<title>.+?)\s+[—–-]\s*"
    r"R(?P<round>\d+)/(?P<kind>PR\d+|Decision)\s*$",
    re.IGNORECASE,
)
_DOI_HEADER_LINE = re.compile(
    r"(?im)^\s*(?:doi\s*:\s*|https?://doi\.org/)"
    r"(10\.\d{4,9}/[^\s\x00-\x1f\x7f]+)\s*$"
)
_CAMBRIDGE_AOP_PDF_PATH = re.compile(
    r"^/core/services/aop-cambridge-core/content/view/[0-9a-f]{32}/"
    r"[^?#]+\.pdf/[^?#]+\.pdf$",
    re.IGNORECASE,
)


def confirmed_parent_article_citation(
    snapshot: SourceSnapshot,
    title: str | None,
    metadata_doi: str | None,
    source_type: str | None,
) -> tuple[str, str] | None:
    """Confirm a Cambridge open-review PDF is actually its parent article.

    The correction is intentionally narrow: all metadata must identify a review
    attachment, while the captured PDF itself must identify the parent article
    in both its first-page title and its primary DOI header.
    """
    if source_type != "peer-review" or not title or not metadata_doi:
        return None
    title_match = _CAMBRIDGE_REVIEW_TITLE.fullmatch(title.strip())
    if title_match is None:
        return None

    try:
        doi = normalize_doi(metadata_doi)
    except ValueError:
        return None
    doi_match = re.fullmatch(r"(?P<parent>10\.\d{4,9}/.+)\.pr(?P<review>\d+)", doi)
    if doi_match is None:
        return None

    review_suffix = title_match.group("kind")
    if not review_suffix.casefold().startswith("pr"):
        return None
    if review_suffix[2:] != doi_match.group("review"):
        return None

    parsed = urlsplit(snapshot.source_url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or not (host == "cambridge.org" or host.endswith(".cambridge.org"))
        or _CAMBRIDGE_AOP_PDF_PATH.fullmatch(unquote(parsed.path)) is None
    ):
        return None

    if sha256(snapshot.normalized_text.encode()).hexdigest() != snapshot.snapshot_sha256:
        return None

    # Restrict the proof to the first-page header region. A DOI copied from a
    # reference later in the PDF must never establish the parent identity.
    header = snapshot.normalized_text[:6000]
    doi_lines = tuple(_DOI_HEADER_LINE.finditer(header))
    if not doi_lines:
        return None
    try:
        header_dois = {normalize_doi(match.group(1)) for match in doi_lines}
    except ValueError:
        return None
    parent_doi = doi_match.group("parent")
    if header_dois != {parent_doi}:
        return None

    parent_title = title_match.group("title").strip()
    title_key = paper_title_key(parent_title)
    title_header = re.sub(r"(?im)^\s*page\s+\d+\s*$", "", header[: doi_lines[0].start()])
    header_title_key = paper_title_key(title_header.lstrip())
    if len(title_key) < 24 or not header_title_key.startswith(title_key):
        return None
    return parent_title, parent_doi
