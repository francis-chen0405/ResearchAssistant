from __future__ import annotations

import hashlib
import json
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from models import SegmentOffset

URL_NAMESPACE = NAMESPACE_URL

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*(?:%)?")


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def derive_quote_block_id(
    source_url: str,
    snapshot_sha256: str,
    segment_offsets: list[SegmentOffset],
) -> UUID:
    offset_payload = json.dumps(
        [
            {"start_char": offset.start_char, "end_char": offset.end_char}
            for offset in segment_offsets
        ],
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(URL_NAMESPACE, f"{source_url}::{snapshot_sha256}::{offset_payload}")
