"""Deterministic, exact-substring previews for immutable source snapshots.

Preview selection is a convenience signal for source ranking. It never interprets
source text as instructions and never replaces the authoritative snapshot used by
the extraction pipeline.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256

from pydantic import ValidationError

from researchassistant.contracts.discovery_v2 import (
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    discovery_id,
)
from researchassistant.contracts.model_contracts import SourceSnapshot

MAX_SPANS = 5
MAX_SPAN_CHARS = 1200
MAX_TOTAL_CHARS = 4800
MAX_CONTEXT_CHARS = 160
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ebef]")

_STOP_WORDS = frozenset(
    "a an and are as at be been being by can could did do does for from had has have he her"
    " hers him his how i if in into is it its may might more most must no nor not of on or"
    " our ours she should so than that the their theirs them then there these they this those"
    " through to too under until up us was we were what when where which while who whom why"
    " will with would you your yours study studies research paper article result results"
    " effect effects impact association associated relationship related evidence claim".split()
)

_SECTION_HEADINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("title", ("title",)),
    ("abstract", ("abstract", "summary", "摘要", "résumé")),
    (
        "methods",
        (
            "method",
            "methods",
            "methodology",
            "materials and methods",
            "methods and materials",
            "experimental",
            "方法",
            "研究方法",
            "材料与方法",
            "材料與方法",
        ),
    ),
    ("results", ("result", "results", "findings", "outcomes", "résultats", "结果", "結果")),
    ("discussion", ("discussion", "interpretation", "讨论", "討論")),
    ("conclusion", ("conclusion", "conclusions", "concluding remarks", "结论", "結論")),
    (
        "bibliography",
        ("references", "bibliography", "works cited", "literature cited", "参考文献", "參考文獻"),
    ),
)
_SUBSTANTIVE_TERMS = frozenset(
    "method methods methodology participants sample cohort randomized randomised trial survey"
    " experiment intervention control analysis analyzed analysed estimate estimated model"
    " regression measured measurement outcome outcomes data dataset results finding found"
    " observed compared difference effect effects association confidence interval p-value"
    " p value odds ratio hazard ratio null no significant significant nonsignificant"
    " non-significant did not change did not differ no effect no difference unchanged"
    " table figure participants n= mean median standard deviation standard error".split()
)
_HAN_SUBSTANTIVE_TERMS = (
    "研究",
    "试验",
    "試驗",
    "实验",
    "實驗",
    "実験",
    "随机",
    "隨機",
    "患者",
    "参与者",
    "參與者",
    "干预",
    "干預",
    "症状",
    "症狀",
    "对照",
    "對照",
    "比較",
    "测量",
    "測量",
    "分析",
    "置信区间",
    "信賴區間",
)
_SHELL_PHRASES = (
    "enable javascript",
    "javascript is required",
    "access denied",
    "page not found",
    "this site can’t be reached",
    "this site can't be reached",
    "temporarily unavailable",
    "checking your browser",
    "verify you are human",
    "captcha",
    "cookie preferences",
    "accept all cookies",
    "privacy settings",
    "skip to content",
    "home | about | contact",
    "recommended articles",
    "related articles",
    "you may also like",
    "browse the latest articles",
    "browse issues",
    "submit a manuscript",
    "browse the archive",
    "启用javascript",
    "啟用javascript",
    "访问被拒绝",
    "存取遭拒",
    "页面未找到",
    "找不到頁面",
    "接受所有cookie",
    "接受所有 cookie",
)
_INJECTION_RE = re.compile(
    r"\b(ignore (?:all )?(?:previous|prior) instructions|system prompt|developer message|"
    r"reveal (?:the )?(?:hidden )?prompt|follow these instructions|assistant,? do this)\b",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"\bdoi\s*[:.]?\s*10\.\d{4,9}/\S+|https?://doi\.org/10\.\d{4,9}/\S+", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)
_CITATION_LINE_RE = re.compile(
    r"^\s*(?:\[\d{1,3}\]|\d{1,3}[.)])\s+.{0,180}\b(?:18|19|20)\d{2}\b|"
    r"^\s*[A-ZÀ-ÖØ-Þ][\w’'-]{1,50}(?:\s+et\s+al\.?)?\s*"
    r"\(\s*(?:18|19|20)\d{2}\s*\)[.,]?\s+.{8,}$",
    re.I,
)
_PAGE_MARKER_RE = re.compile(
    r"^\s*(?:(?:[-–—]|\[|\()?\s*)?(?:(?:pdf\s*)?page|p\.?)\s*\d{1,4}"
    r"(?:\s*(?:/|of)\s*\d{1,4})?\s*(?:[-–—]|\]|\))?\s*$|"
    r"^\s*\d{1,4}\s*/\s*\d{1,4}\s*$",
    re.I,
)
_PDF_MARKER_RE = re.compile(r"\[(?:page|p\.?)[ :#-]*\d{1,4}\]", re.I)
_HEADING_PREFIX_RE = re.compile(r"^\s*(?:(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+)?")


@dataclass(frozen=True)
class _Segment:
    start: int
    end: int
    section: str
    text: str
    heading: str | None = None


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    section: str
    text: str
    score: int
    relevance: int
    signals: tuple[str, ...]


def build_claim_preview(request: V2PreviewRequest, snapshot: SourceSnapshot) -> V2PreviewResult:
    """Select exact, bounded source windows using the frozen request and snapshot."""
    try:
        request = V2PreviewRequest.model_validate(request.model_dump(mode="python"))
    except ValidationError as exc:
        raise ValueError("preview request identity/ownership validation failed") from exc
    try:
        snapshot = SourceSnapshot.model_validate(snapshot.model_dump(mode="python"))
    except ValidationError as exc:
        raise ValueError("preview snapshot validation failed") from exc
    _verify_request_snapshot(request, snapshot)
    text = snapshot.normalized_text
    segments, observed = _segments(text)
    substantive_capture = any(
        not _is_excluded(segment.text) and _substantive(segment.text, segment.section)
        for segment in segments
    )
    content_classification = _classify_capture(segments, snapshot.truncated)
    query_terms, phrases = _query_terms(request)
    candidates = _rank_candidates(segments, text, query_terms, phrases)
    selected = _select_non_overlapping(candidates)
    relevance_score = _relevance_score(candidates)
    spans = tuple(_to_span(text, item) for item in selected)
    missing = tuple(
        section
        for section in ("abstract", "methods", "results", "discussion", "conclusion")
        if section not in observed
    )
    outcome = "completed" if spans else "unavailable"
    if spans:
        reason = "preview_windows_selected"
    elif content_classification in {"shell", "error"}:
        reason = "shell_or_error_snapshot"
    elif not segments:
        reason = "empty_snapshot"
    elif not substantive_capture:
        reason = "no_substantive_source_text"
    else:
        reason = "no_relevant_windows"

    identity = request.preview_identity
    values: dict[str, object] = {
        "run_id": request.run_id,
        "artifact_id": discovery_id(request.run_id, "V2PreviewResult", request.identity_key),
        "identity_key": request.identity_key,
        "request": request,
        "spans": spans,
        "content_classification": content_classification,
        "outcome": outcome,
        "reason": reason,
    }
    # V1 artifacts retain their historical shape. V2 records observable capture
    # diagnostics without claiming document completeness from section co-occurrence.
    if identity == "source-claim-preview-v2":
        values.update(
            observed_sections=tuple(sorted(observed)),
            missing_sections=missing,
            snapshot_truncated=snapshot.truncated,
            capture_usable=(
                substantive_capture if content_classification not in {"shell", "error"} else False
            ),
            relevance_score=relevance_score,
        )
    result = V2PreviewResult.model_validate(values)
    result.require_snapshot(snapshot)
    return result


def build_capture_windows(snapshot: SourceSnapshot) -> tuple[V2PreviewSpan, ...]:
    """Return bounded substantive passages for Probe without claim ranking."""
    try:
        snapshot = SourceSnapshot.model_validate(snapshot.model_dump(mode="python"))
    except ValidationError as exc:
        raise ValueError("preview snapshot validation failed") from exc
    text = snapshot.normalized_text
    if sha256(text.encode("utf-8")).hexdigest() != snapshot.snapshot_sha256:
        raise ValueError("preview snapshot text hash is stale")
    segments, _observed = _segments(text)
    candidates = _rank_candidates(segments, text, set(), (), allow_structural=True)
    spans = tuple(_to_span(text, item) for item in _select_non_overlapping(candidates))
    for span in spans:
        if (
            text[span.start : span.end] != span.text
            or span.omitted_before != (span.start > 0)
            or span.omitted_after != (span.end < len(text))
            or text[max(0, span.start - len(span.context_before)) : span.start]
            != span.context_before
            or text[span.end : span.end + len(span.context_after)] != span.context_after
        ):
            raise ValueError("preview text/context differs from immutable snapshot")
    return spans


def _verify_request_snapshot(request: V2PreviewRequest, snapshot: SourceSnapshot) -> None:
    if (
        request.run_id != snapshot.run_id
        or request.snapshot_id != snapshot.snapshot_id
        or request.snapshot_hash != snapshot.snapshot_sha256
    ):
        raise ValueError("preview snapshot ownership/hash mismatch")
    if sha256(snapshot.normalized_text.encode("utf-8")).hexdigest() != request.snapshot_hash:
        raise ValueError("preview snapshot text hash is stale")


def _segments(text: str) -> tuple[list[_Segment], set[str]]:
    """Segment by exact source boundaries while tracking visible section headings."""
    segments: list[_Segment] = []
    observed: set[str] = set()
    section = "unknown"
    bibliography = False
    title_seen = False
    for match in re.finditer(r"[^\n]+(?:\n+|$)", text):
        raw = match.group(0)
        body = raw.rstrip("\r\n")
        if not body.strip() or _PAGE_MARKER_RE.fullmatch(body) or not body.strip("\ufeff\x0c \t"):
            continue
        clean = _PDF_MARKER_RE.sub(" ", body).strip()
        if not clean:
            continue
        heading, heading_section = _heading(clean)
        if heading_section == "bibliography":
            bibliography = True
            observed.add("bibliography")
            continue
        if bibliography:
            continue
        if heading_section:
            section = heading_section
            observed.add(section)
            # Headings are retained as exact source text, but do not become preview
            # candidates by themselves.
            continue
        if _is_citation_line(clean):
            observed.add("bibliography")
            continue
        is_title = _is_titleish(clean, section) and not title_seen
        if is_title:
            observed.add("title")
            title_seen = True
        if section != "unknown":
            observed.add(section)
        start = match.start() + (len(body) - len(body.lstrip()))
        end = match.start() + len(body.rstrip())
        if start < end:
            segments.append(
                _Segment(
                    start,
                    end,
                    "title" if is_title else section,
                    text[start:end],
                    heading,
                )
            )
    # A flattened text capture often uses long lines with inline section labels.
    # Split recognized headings into exact offsets without normalizing the source.
    flattened, inline_observed = _split_inline_headings(segments, text)
    observed.update(inline_observed)
    return flattened, observed


def _heading(line: str) -> tuple[str | None, str | None]:
    candidate = _HEADING_PREFIX_RE.sub("", line).strip(" :.—-\t")
    candidate = re.sub(r"\s+", " ", candidate).casefold()
    candidate = re.sub(r"\s*\([^)]{1,30}\)\s*$", "", candidate)
    candidate = candidate.rstrip(" .:")
    if len(candidate) > 80 or len(candidate.split()) > 8:
        return None, None
    for section, forms in _SECTION_HEADINGS:
        if candidate in forms:
            return candidate, section
    return None, None


def _is_titleish(line: str, section: str) -> bool:
    return (
        section == "unknown"
        and len(line) <= 180
        and len(line.split()) <= 24
        and not line.endswith((".", ";"))
    )


def _split_inline_headings(segments: list[_Segment], text: str) -> tuple[list[_Segment], set[str]]:
    output: list[_Segment] = []
    observed: set[str] = set()
    inline = re.compile(
        r"(?i)(?<!\w)(?:\d+(?:\.\d+)*[.)]?\s+)?"
        r"(title|abstract|summary|materials\s+and\s+methods|methods\s+and\s+materials|"
        r"methods?|methodology|results?|findings|discussion|conclusions?|references|"
        r"bibliography|works\s+cited|literature\s+cited)(?:\s*[:.])\s+"
    )
    for segment in segments:
        matches = list(inline.finditer(segment.text))
        if not matches:
            output.append(segment)
            continue
        boundaries: list[tuple[int, int, str]] = []
        for found in matches:
            section = _section_for_heading(found.group(1))
            if found.start() > 0 and len(segment.text[found.start() :].split()) < 4:
                continue
            boundaries.append((found.start(), found.end(), section))
            observed.add(section)
            if section == "bibliography":
                # Once a flattened reference heading appears, treat the rest as
                # bibliography and never include it in a window.
                break
        if not boundaries:
            output.append(segment)
            continue
        intervals: list[tuple[int, int, str]] = []
        if boundaries[0][0] > 0:
            intervals.append((0, boundaries[0][0], segment.section))
        for index, (_heading_start, content_start, section) in enumerate(boundaries):
            if section == "bibliography":
                continue
            next_start = (
                boundaries[index + 1][0] if index + 1 < len(boundaries) else len(segment.text)
            )
            intervals.append((content_start, next_start, section))
        for left, right, section in intervals:
            raw_value = segment.text[left:right]
            value = raw_value.strip()
            if value:
                exact_start = segment.start + left + len(raw_value) - len(raw_value.lstrip())
                exact_end = exact_start + len(value)
                output.append(
                    _Segment(exact_start, exact_end, section, text[exact_start:exact_end])
                )
    return output, observed


def _section_for_heading(value: str) -> str:
    key = re.sub(r"\s+", " ", value.casefold()).rstrip("s")
    return {
        "abstract": "abstract",
        "title": "title",
        "method": "methods",
        "methodology": "methods",
        "methods and material": "methods",
        "material and method": "methods",
        "result": "results",
        "finding": "results",
        "discussion": "discussion",
        "conclusion": "conclusion",
        "summary": "abstract",
        "reference": "bibliography",
        "bibliography": "bibliography",
        "works cited": "bibliography",
        "literature cited": "bibliography",
    }.get(key, "unknown")


def _query_terms(request: V2PreviewRequest) -> tuple[set[str], tuple[str, ...]]:
    sources = (request.exact_claim, *request.asserted_components, *request.target_gaps)
    tokens = [_tokens(value) for value in sources]
    terms = {
        token
        for group in tokens
        for token in group
        if (len(token) > 2 or (len(token) >= 2 and _HAN_RE.search(token)))
        and token not in _STOP_WORDS
    }
    phrases: list[str] = []
    for value in sources:
        words = _tokens(value)
        for size in (2, 3, 4):
            phrases.extend(
                " ".join(words[index : index + size])
                for index in range(max(0, len(words) - size + 1))
            )
    aliases = set(terms)
    for term in tuple(terms):
        if term.endswith("ies") and len(term) > 5:
            aliases.add(term[:-3] + "y")
        if term.endswith("s") and len(term) > 4:
            aliases.add(term[:-1])
        if term.endswith("ed") and len(term) > 5:
            aliases.add(term[:-2])
        if term.endswith("ing") and len(term) > 6:
            aliases.add(term[:-3])
    aliases.update(_common_aliases(terms))
    for value in sources:
        for acronym in re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", value):
            aliases.add(acronym.casefold())
    # Expand acronyms against explicit, local parenthetical definitions only.
    for value in sources:
        for found in re.finditer(r"\b([A-Z][A-Za-z -]{5,80})\s*\(([A-Z]{2,8})\)", value):
            aliases.add(found.group(2).casefold())
    for phrase in tuple(phrases):
        words = _tokens(phrase)
        if len(words) >= 2:
            initials = "".join(word[0] for word in words if word not in _STOP_WORDS)
            if len(initials) >= 2:
                aliases.add(initials)
    return aliases, tuple(dict.fromkeys(phrases))


def _tokens(value: str) -> list[str]:
    tokens = [token.casefold() for token in _TOKEN_RE.findall(value)]
    return [_fold_accents(token) for token in tokens]


def _fold_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _common_aliases(terms: set[str]) -> set[str]:
    aliases: dict[str, set[str]] = {
        "adolescent": {"teen", "teenager", "youth"},
        "teenager": {"adolescent", "youth"},
        "child": {"children", "pediatric", "paediatric"},
        "children": {"child", "pediatric", "paediatric"},
        "mortality": {"death", "deaths"},
        "death": {"mortality", "deaths"},
        "increase": {"increased", "higher", "elevated", "rise"},
        "decrease": {"decreased", "lower", "reduced", "decline"},
        "association": {"associated", "correlation", "relationship"},
        "trial": {"randomized", "randomised", "rct"},
        "randomized": {"randomised", "rct"},
        "randomised": {"randomized", "rct"},
        "significant": {"meaningful", "statistically"},
        "intervention": {"treatment", "treated"},
        "treatment": {"intervention", "treated"},
        "symptom": {"symptome", "symptomes"},
        "symptome": {"symptom", "symptomes"},
        "reduce": {"reduit", "reduite", "reduction", "reduced"},
        "reduced": {"reduce", "reduit", "reduite", "reduction"},
    }
    result: set[str] = set()
    for term in terms:
        result.update(aliases.get(term, ()))
    return result


def _rank_candidates(
    segments: list[_Segment],
    text: str,
    query_terms: set[str],
    phrases: tuple[str, ...],
    *,
    allow_structural: bool = False,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for index, segment in enumerate(segments):
        if _is_excluded(segment.text):
            continue
        # Build useful contiguous windows from nearby paragraphs. Sentence-only
        # candidates are a fallback for a single long paragraph, never stitched.
        for start_index in range(index, min(len(segments), index + 8)):
            current = segments[start_index]
            if any(_is_excluded(item.text) for item in segments[index : start_index + 1]):
                break
            start, end = segment.start, current.end
            if current.section != segment.section:
                break
            if not _safe_gap(text, segment.end, current.start):
                break
            if end - start > MAX_SPAN_CHARS:
                if start_index == index:
                    candidates.extend(
                        _split_long_segment(
                            segment,
                            query_terms,
                            phrases,
                            allow_structural=allow_structural,
                        )
                    )
                break
            value = text[start:end]
            if len(value) < 35 and not _substantive(value, segment.section):
                continue
            candidate = _score_candidate(
                start,
                end,
                segment.section,
                value,
                query_terms,
                phrases,
                allow_structural=allow_structural,
            )
            if candidate.score > 0:
                candidates.append(candidate)
        if segment.section == "bibliography":
            continue
    # A short but substantive source may fit only one paragraph; keep it eligible.
    return sorted(candidates, key=lambda item: (-item.score, -item.relevance, item.start, item.end))


def _split_long_segment(
    segment: _Segment,
    terms: set[str],
    phrases: tuple[str, ...],
    *,
    allow_structural: bool = False,
) -> list[_Candidate]:
    text = segment.text
    sentence_starts = [0]
    for match in re.finditer(r"(?<=[.!?。！？])\s+(?=[A-ZÀ-ÖØ-Þ0-9(\[])", text):
        sentence_starts.append(match.end())
    sentence_starts.append(len(text))
    result: list[_Candidate] = []
    sentence_spans = list(zip(sentence_starts, sentence_starts[1:], strict=False))
    for first in range(len(sentence_spans)):
        left = sentence_spans[first][0]
        right = left
        for _sent_start, sent_end in sentence_spans[first:]:
            if sent_end - left > MAX_SPAN_CHARS:
                break
            right = sent_end
        if right > left:
            _append_candidate_window(
                result, segment, text, left, right, terms, phrases, allow_structural
            )
        if right == left and sentence_spans[first][1] - left > MAX_SPAN_CHARS:
            # Long unpunctuated statements are split at whitespace boundaries;
            # each resulting passage is still one exact contiguous source slice.
            sentence_end = sentence_spans[first][1]
            chunk_start = left
            while chunk_start < sentence_end:
                tentative = min(sentence_end, chunk_start + MAX_SPAN_CHARS)
                if tentative < sentence_end:
                    boundary = text.rfind(" ", chunk_start + MAX_SPAN_CHARS // 2, tentative)
                    if boundary > chunk_start:
                        tentative = boundary
                _append_candidate_window(
                    result,
                    segment,
                    text,
                    chunk_start,
                    tentative,
                    terms,
                    phrases,
                    allow_structural,
                )
                chunk_start = tentative
    return result


def _append_candidate_window(
    result: list[_Candidate],
    segment: _Segment,
    full_text: str,
    left: int,
    right: int,
    terms: set[str],
    phrases: tuple[str, ...],
    allow_structural: bool,
) -> None:
    raw = segment.text[left:right]
    value = raw.strip()
    if not value or len(value) > MAX_SPAN_CHARS or _is_excluded(value):
        return
    leading = len(raw) - len(raw.lstrip())
    start = segment.start + left + leading
    end = start + len(value)
    candidate = _score_candidate(
        start,
        end,
        segment.section,
        value,
        terms,
        phrases,
        allow_structural=allow_structural,
    )
    if candidate.score > 0:
        result.append(candidate)


def _score_candidate(
    start: int,
    end: int,
    section: str,
    value: str,
    query_terms: set[str],
    phrases: tuple[str, ...],
    *,
    allow_structural: bool = False,
) -> _Candidate:
    terms = set(_tokens(value))
    # Unspaced scripts do not expose word boundaries. Match explicit claim
    # components as literal substrings, never isolated characters or translations.
    folded = _fold_accents(value.casefold())
    terms.update(
        term for term in query_terms if len(term) >= 2 and _HAN_RE.search(term) and term in folded
    )
    words = _tokens(value)
    for size in (2, 3, 4, 5, 6):
        for index in range(max(0, len(words) - size + 1)):
            acronym = "".join(
                word[0] for word in words[index : index + size] if word not in _STOP_WORDS
            )
            if len(acronym) >= 2 and acronym in query_terms:
                terms.add(acronym)
    overlap = query_terms & terms
    coverage = len(overlap) / max(1, min(len(query_terms), 8))
    phrase_hits = sum(1 for phrase in phrases if phrase and phrase.casefold() in value.casefold())
    relevance = min(100, round(100 * min(1.0, coverage * 2.4 + phrase_hits * 0.12)))
    structure = {
        "title": 5,
        "abstract": 7,
        "methods": 18,
        "results": 24,
        "discussion": 14,
        "conclusion": 16,
        "unknown": 0,
    }.get(section, 0)
    substantive_terms = len(terms & _SUBSTANTIVE_TERMS) + sum(
        term in value for term in _HAN_SUBSTANTIVE_TERMS
    )
    substantial = 12 if substantive_terms >= 2 else 6 if substantive_terms == 1 else 0
    stat_score = _statistical_signal(value)
    qualification = (
        6
        if re.search(
            r"\b(no effect|no difference|did not|not significant|non-significant|null|"
            r"unchanged|failed to)\b",
            value,
            re.I,
        )
        else 0
    )
    injection_penalty = 12 if _INJECTION_RE.search(value) else 0
    # Claim relevance, section structure, and methods/results content dominate.
    score = round(
        coverage * 40
        + min(16, phrase_hits * 8)
        + structure
        + substantial
        + stat_score
        + qualification
        - injection_penalty
    )
    if not overlap and not phrase_hits and not allow_structural:
        score = 0
    if len(terms) < 5 and not _substantive(value, section):
        score = 0
    signals: list[str] = []
    if overlap:
        signals.append("claim_terms")
    if phrase_hits:
        signals.append("claim_phrase")
    if section in {"methods", "results", "discussion", "conclusion"}:
        signals.append(f"section:{section}")
    if substantive_terms:
        signals.append("substantive_content")
    if stat_score:
        signals.append("statistical_context")
    if qualification:
        signals.append("negative_or_qualified_finding")
    if injection_penalty:
        signals.append("untrusted_instruction_text")
    # Deliberately avoid digit-count bonuses: numbers only contribute alongside
    # surrounding statistical language, comparisons, or substantive structure.
    return _Candidate(start, end, section, value, score, relevance, tuple(signals))


def _statistical_signal(value: str) -> int:
    if not re.search(
        r"\b(p\s*[<=>]|confidence interval|odds ratio|hazard ratio|standard error|"
        r"standard deviation|mean|median|regression|table\s+\d+|n\s*=)\b",
        value,
        re.I,
    ):
        return 0
    return (
        8
        if re.search(
            r"\b(no effect|no difference|did not|not significant|null|unchanged)\b",
            value,
            re.I,
        )
        else 5
    )


def _substantive(value: str, section: str = "unknown") -> bool:
    lowered = value.casefold()
    if _INJECTION_RE.search(value) or any(phrase in lowered for phrase in _SHELL_PHRASES):
        return False
    tokens = set(_tokens(value))
    han = _HAN_RE.findall(value)
    if len(han) >= 12 and len(set(han)) >= 8:
        scientific_terms = sum(term in value for term in _HAN_SUBSTANTIVE_TERMS)
        if section in {"abstract", "methods", "results", "discussion", "conclusion"}:
            if scientific_terms:
                return True
        elif len(han) >= 24 and scientific_terms >= 2:
            return True
    if len(tokens) >= 7 and bool(tokens & _SUBSTANTIVE_TERMS):
        return True
    if section in {"methods", "results", "discussion", "conclusion"} and len(tokens) >= 5:
        return True
    # Accent folding supports a small, explicit multilingual vocabulary while
    # keeping arbitrary lexical translation out of this deterministic selector.
    return len(tokens) >= 5 and bool(
        tokens & {"symptome", "reduit", "reduite", "essai", "participants"}
    )


def _is_excluded(value: str) -> bool:
    lowered = value.casefold().strip()
    if _INJECTION_RE.search(value):
        return True
    if any(phrase in lowered for phrase in _SHELL_PHRASES):
        return True
    if _is_citation_line(value) or (len(_URL_RE.findall(value)) and len(_tokens(value)) < 24):
        return True
    if re.match(
        r"^(?:references|bibliography|recommended|related articles|menu|navigation)\b",
        lowered,
    ):
        return True
    if re.search(
        r"\b(?:accept cookies|manage cookies|sign in|log in|subscribe now|all rights reserved)\b",
        lowered,
    ):
        return True
    if (
        len(re.findall(r"\b(?:19|20)\d{2}\b", value)) >= 2
        and len(_tokens(value)) < 30
        and re.search(r"[;.]\s+[A-Z]", value)
    ):
        return True
    return False


def _is_citation_line(value: str) -> bool:
    if _CITATION_LINE_RE.search(value):
        return True
    doi = _DOI_RE.search(value)
    if doi:
        prefix = value[: doi.start()].strip(" .:;,-")
        # A DOI after a real abstract/result sentence is an inline reference
        # marker; let the later References heading split remove its suffix.
        if len(_tokens(prefix)) >= 6:
            return False
        return True
    return False


def _safe_gap(text: str, start: int, end: int) -> bool:
    """Only whitespace or explicit page markers may separate merged paragraphs."""
    if end <= start:
        return True
    for line in text[start:end].splitlines():
        if not line.strip() or _PAGE_MARKER_RE.fullmatch(line):
            continue
        if _PDF_MARKER_RE.fullmatch(line.strip()):
            continue
        return False
    return True


def _select_non_overlapping(candidates: list[_Candidate]) -> list[_Candidate]:
    selected: list[_Candidate] = []
    total = 0
    for item in candidates:
        if len(selected) >= MAX_SPANS or total + len(item.text) > MAX_TOTAL_CHARS:
            continue
        if any(item.start < prior.end and prior.start < item.end for prior in selected):
            continue
        selected.append(item)
        total += len(item.text)
    return sorted(selected, key=lambda item: item.start)


def _to_span(text: str, candidate: _Candidate) -> V2PreviewSpan:
    values: dict[str, object] = {
        "start": candidate.start,
        "end": candidate.end,
        "text": text[candidate.start : candidate.end],
        "section": candidate.section,
        "context_before": _context_before(text, candidate.start),
        "context_after": _context_after(text, candidate.end),
        "relevance_signals": candidate.signals,
    }
    values["omitted_before"] = candidate.start > 0
    values["omitted_after"] = candidate.end < len(text)
    return V2PreviewSpan.model_validate(values)


def _context_before(text: str, start: int) -> str:
    left = max(0, start - MAX_CONTEXT_CHARS)
    context = text[left:start]
    for marker in re.finditer(
        r"(?i)\b(?:references|bibliography|works cited|literature cited)\s*[:.]",
        context,
    ):
        context = context[marker.end() :]
    lines = context.splitlines(keepends=True)
    excluded_offset = 0
    for line in lines:
        if _is_excluded(line.strip()):
            excluded_offset += len(line)
        else:
            break
    return context[excluded_offset:]


def _context_after(text: str, end: int) -> str:
    right = min(len(text), end + MAX_CONTEXT_CHARS)
    context = text[end:right]
    marker = re.search(
        r"(?i)\b(?:references|bibliography|works cited|literature cited)\s*[:.]",
        context,
    )
    if marker:
        context = context[: marker.start()]
    for line in context.splitlines(keepends=True):
        if _is_excluded(line.strip()):
            context = context[: context.find(line)]
            break
    return context


def _relevance_score(candidates: list[_Candidate]) -> int:
    return max((item.relevance for item in candidates), default=0)


def _classify_capture(segments: list[_Segment], truncated: bool) -> str:
    text = " ".join(segment.text for segment in segments)
    lowered = text.casefold()
    if not text.strip():
        return "unknown"
    if re.search(
        r"\b(?:page not found|404\s+not found|access denied|temporarily unavailable|"
        r"error 40[134]|error 50[23]|(?:http\s*)?4\d\d error)\b",
        lowered,
    ):
        return "error"
    if any(phrase in lowered for phrase in _SHELL_PHRASES) and not any(
        _substantive(segment.text) for segment in segments
    ):
        return "shell"
    sections = {segment.section for segment in segments}
    if sections & {"methods", "results", "discussion", "conclusion"}:
        # Observing study sections does not prove complete full-text capture.
        return "partial"
    if "abstract" in sections:
        return "abstract_only"
    if len(_tokens(text)) < 500 and not any(_substantive(segment.text) for segment in segments):
        return "landing"
    return "unknown"
