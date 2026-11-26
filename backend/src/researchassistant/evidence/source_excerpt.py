"""Bounded exact sentence views over an immutable source snapshot."""

from __future__ import annotations

import re

from researchassistant.evidence.evidence_core import fresh_sentence_spans

EXTRACTION_EXCERPT_BYTES = 8_000
_FOCUS_CONTEXT_SENTENCES = 12
_RESULT = re.compile(
    r"\b(?:overall (?:injury |adjusted )?(?:incidence|risk|rate|result)|"
    r"our (?:results|findings|analysis)|we (?:found|observed|estimated)|"
    r"annual maintenance costs?|present.value maintenance)\b",
    re.I,
)
_CAVEAT = re.compile(
    r"\b(?:lack of exposure data|(?:no|without|lack(?:ing)?) exposure (?:data|time)|"
    r"(?:cannot|unable to|limits? the ability to) (?:calculate|estimate|control)|"
    r"confound(?:ers|ing)|underreporting|evidence quality (?:low|very low)|"
    r"considerable heterogeneity|(?:observational|retrospective) (?:design|study))\b",
    re.I,
)


def source_context_excerpts(text: str) -> tuple[str, ...]:
    """Expose bounded exact results/caveats, never invented quote context."""
    spans = fresh_sentence_spans(text)
    excerpts: list[str] = []
    for cue in (_CAVEAT, _RESULT):
        count = 0
        for index, span in enumerate(spans):
            if not cue.search(span.text):
                continue
            # PDF line breaks can split one caveat into several sentence spans.
            end = span.end_char
            for neighbor in spans[index + 1 : index + 4]:
                if neighbor.end_char - span.start_char > 1800:
                    break
                end = neighbor.end_char
            excerpt = text[span.start_char : end]
            if len(excerpt) <= 1800 and excerpt not in excerpts:
                excerpts.append(excerpt)
                count += 1
            if count == 3:
                break
    return tuple(excerpts)


def extraction_source_view(
    text: str, focus_passages: tuple[str, ...] = (), *, max_bytes: int = EXTRACTION_EXCERPT_BYTES
) -> tuple[str, frozenset[int]]:
    """Keep original sentence IDs, a local focus window, and an opening view within a byte bound."""
    if max_bytes < 1:
        raise ValueError("source excerpt byte limit must be positive")
    spans = fresh_sentence_spans(text)
    if not spans:
        raise ValueError("snapshot has no selectable sentences")
    lines = {i: f"[{i}] {span.text}" for i, span in enumerate(spans, 1)}
    priorities: list[int] = []
    # Probe keyword hits can be introductory citations. Reserve room for the
    # document's own results and methodological caveats before local padding.
    important = [
        i
        for i, span in enumerate(spans, 1)
        if (_RESULT.search(span.text) or _CAVEAT.search(span.text))
        and len(lines[i].encode("utf-8")) <= max_bytes // 3
    ]
    priorities.extend(important[:8])
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
            # Table column headings often sit several extracted lines above the value row.
            # Keep a bounded local window so the extractor can see those exact source labels.
            priorities.extend(
                range(
                    max(1, i - _FOCUS_CONTEXT_SENTENCES),
                    min(len(spans), i + _FOCUS_CONTEXT_SENTENCES) + 1,
                )
            )
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
