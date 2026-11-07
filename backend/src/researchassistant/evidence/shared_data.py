"""Source-family anchors from explicit primary-data statements in captured text."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from researchassistant.contracts.discovery_v2 import normalize_doi
from researchassistant.contracts.models import SourceSnapshot
from researchassistant.evidence.evidence_core import validate_snapshot_integrity
from researchassistant.evidence.evidence_portfolio import identify_source_family

DATA_FAMILY_PREFIX = "shared-data:"
UNVERIFIED_DATA_FAMILY_PREFIX = "unverified-data:"
_REFERENCES = re.compile(r"(?im)^\s*(?:references|bibliography|works cited)\s*$")
_DATA_USE = re.compile(
    r"\b(?:we (?:used|analy[sz]ed|re.analy[sz]ed)|"
    r"(?:this|our) (?:study|analysis) (?:uses?|used|analy[sz]es?|analy[sz]ed|"
    r"is a secondary analysis of))\s+(?:participant.level |individual.level |"
    r"de.identified |the )?data from\s+(?:the )?"
    r"(?:registered )?(?:trial|cohort|study|dataset)(?:\s+(?:registered (?:as|under)|doi)\s*:?|\s*)"
    r"\s*\(?\s*(?P<anchor>NCT\d{8}\b|(?:https://doi\.org/)?"
    r"10\.\d{4,9}/[-._a-z0-9/]{1,160}(?=$|[\s,;)]))",
    re.I,
)


def source_family_key(snapshot: SourceSnapshot, *, track_shared_data: bool) -> str:
    """Keep publications separate while linking verified use of one registered data source."""
    if track_shared_data:
        # Ignore reference lists, incidental identifiers and registrations in other works.
        text = _REFERENCES.split(snapshot.normalized_text[:100_000], maxsplit=1)[0]
        anchors = set()
        for match in _DATA_USE.finditer(text):
            value = match["anchor"].rstrip(".")
            if value.upper().startswith("NCT"):
                anchors.add(value.upper())
            else:
                try:
                    anchors.add(normalize_doi(value))
                except ValueError:
                    continue
        if len(anchors) == 1:
            validate_snapshot_integrity(snapshot)
            return DATA_FAMILY_PREFIX + next(iter(anchors))
    family = str(identify_source_family(snapshot).source_family_id)
    return UNVERIFIED_DATA_FAMILY_PREFIX + family if track_shared_data else family


def shared_data_limitations(family_keys: Iterable[str]) -> tuple[str, ...]:
    registered: Counter[str] = Counter()
    unresolved: set[str] = set()
    for family in family_keys:
        if family.startswith(DATA_FAMILY_PREFIX):
            registered[family.removeprefix(DATA_FAMILY_PREFIX)] += 1
        elif family.startswith(UNVERIFIED_DATA_FAMILY_PREFIX):
            unresolved.add(family)
    notes = [
        f"{count} admitted publications report analyses of the same registered data "
        f"source ({identifier}). They count as one data source for a shared finding."
        for identifier, count in sorted(registered.items())
        if count > 1
    ]
    if len(unresolved) + len(registered) > 1:
        notes.append("Data overlap between other admitted publications remains unresolved.")
    return tuple(notes)
