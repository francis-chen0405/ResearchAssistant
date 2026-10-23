"""Bounded exact sentence views over an immutable source snapshot."""

from __future__ import annotations

from researchassistant.evidence.evidence_core import fresh_sentence_spans

EXTRACTION_EXCERPT_BYTES = 8_000


def extraction_source_view(
    text: str, focus_passages: tuple[str, ...] = (), *, max_bytes: int = EXTRACTION_EXCERPT_BYTES
) -> tuple[str, frozenset[int]]:
    """Keep original sentence IDs, nearby context, and an opening view within a byte bound."""
    if max_bytes < 1:
        raise ValueError("source excerpt byte limit must be positive")
    spans = fresh_sentence_spans(text)
    if not spans:
        raise ValueError("snapshot has no selectable sentences")
    lines = {i: f"[{i}] {span.text}" for i, span in enumerate(spans, 1)}
    priorities: list[int] = []
    # Favor exact Probe passages over unrelated navigation and reference lists.
    for passage in focus_passages:
        start = text.find(passage)
        if start < 0:
            continue
        end = start + len(passage)
        matching = [
            i for i, span in enumerate(spans, 1) if span.start_char < end and span.end_char > start
        ]
        priorities.extend(matching)
        for i in matching:
            priorities.extend(range(max(1, i - 2), min(len(spans), i + 2) + 1))
    priorities.extend(range(1, min(len(spans), 12) + 1))
    priorities.extend(range(1, len(spans) + 1))
    selected: set[int] = set()
    used = 0
    for i in priorities:
        if i in selected:
            continue
        size = len(lines[i].encode("utf-8")) + (1 if selected else 0)
        if used + size <= max_bytes:
            selected.add(i)
            used += size
    if not selected:
        raise ValueError("no complete source sentence fits the extraction excerpt limit")
    return "\n".join(lines[i] for i in sorted(selected)), frozenset(selected)
