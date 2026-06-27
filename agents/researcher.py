from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from models import (
    CandidateQuoteBlock,
    ProvisionalCandidate,
    SegmentOffset,
    SourceSnapshot,
    StrictModel,
)
from utils import compute_sha256, count_words, derive_quote_block_id

START_MARKER = "Start of Text"
END_MARKER = "End of Text"
TRUNCATED_END_MARKER = "Truncated End of Snapshot"

STATISTICAL_MARKERS = (
    "%",
    "percent",
    "rate",
    "ratio",
    "average",
    "median",
    "index",
    "p-value",
    "million",
    "billion",
    "growth",
    "decline",
)

STATISTICAL_MIN_WORDS = 50
NON_STATISTICAL_MIN_WORDS = 100

_BRACKETED_QUOTE_RE = re.compile(
    r'^\s*\[(?P<before>[^\[\]]+)\]\s+"(?P<quote>.+?)"\s+\[(?P<after>[^\[\]]+)\]\s*$',
    re.DOTALL,
)
_ELLIPSIS_RE = re.compile(r"\s*\.\.\.\s*")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$", re.DOTALL)


class ParsedQuoteBlock(StrictModel):
    preceding_context: str
    segments: list[str] = Field(min_length=1)
    following_context: str


class QuoteMetrics(StrictModel):
    raw_segment_word_count: int = Field(ge=1)
    has_statistical_markers: bool
    claim_keyword_match_count: int = Field(ge=0)


class PostExtractionFilterResult(StrictModel):
    valid: bool
    candidate: CandidateQuoteBlock | None = None
    rejection_code: str | None = None
    rejection_message: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> PostExtractionFilterResult:
        if self.valid:
            if self.candidate is None:
                raise ValueError("valid filter results require a candidate")
            if self.rejection_code is not None or self.rejection_message is not None:
                raise ValueError("valid filter results cannot include rejection details")
        else:
            if self.candidate is not None:
                raise ValueError("rejected filter results cannot include a candidate")
            if self.rejection_code is None or self.rejection_message is None:
                raise ValueError("rejected filter results require rejection details")
        return self


class _SentenceSpan(StrictModel):
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=1)
    text: str


def build_source_snapshot(
    *,
    run_id: UUID,
    retrieval_attempt_id: UUID,
    snapshot_id: UUID,
    source_url: str,
    retrieved_at: datetime,
    normalized_text: str,
    truncated: bool,
    created_at: datetime,
) -> SourceSnapshot:
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=retrieval_attempt_id,
        snapshot_id=snapshot_id,
        source_url=source_url,
        retrieved_at=retrieved_at,
        normalized_text=normalized_text,
        snapshot_sha256=compute_sha256(normalized_text),
        word_count=count_words(normalized_text),
        truncated=truncated,
        created_at=created_at,
    )
    validate_snapshot_integrity(snapshot)
    return snapshot


def validate_snapshot_integrity(snapshot: SourceSnapshot) -> bool:
    expected_hash = compute_sha256(snapshot.normalized_text)
    if snapshot.snapshot_sha256 != expected_hash:
        raise ValueError("snapshot hash does not match normalized_text")
    expected_word_count = count_words(snapshot.normalized_text)
    if snapshot.word_count != expected_word_count:
        raise ValueError("snapshot word_count does not match normalized_text")
    return True


def parse_extracted_quote_block(extracted_quote_block: str) -> ParsedQuoteBlock:
    match = _BRACKETED_QUOTE_RE.match(extracted_quote_block)
    if match is None:
        raise ValueError('quote block must match [context] "segments" [context]')

    segments = [segment.strip() for segment in _ELLIPSIS_RE.split(match.group("quote"))]
    if not segments or any(segment == "" for segment in segments):
        raise ValueError("quote block must contain non-empty quoted segments")

    return ParsedQuoteBlock(
        preceding_context=match.group("before").strip(),
        segments=segments,
        following_context=match.group("after").strip(),
    )


def find_segment_offsets(normalized_text: str, segments: list[str]) -> list[SegmentOffset]:
    offsets: list[SegmentOffset] = []
    search_start = 0
    for segment in segments:
        start = normalized_text.find(segment, search_start)
        if start == -1:
            raise ValueError("quoted segment does not appear in snapshot text")
        end = start + len(segment)
        offsets.append(SegmentOffset(start_char=start, end_char=end))
        search_start = end
    return offsets


def validate_bracket_context(
    snapshot: SourceSnapshot,
    parsed_quote: ParsedQuoteBlock,
    segment_offsets: list[SegmentOffset],
) -> bool:
    text = snapshot.normalized_text
    first_start = segment_offsets[0].start_char
    last_end = segment_offsets[-1].end_char

    previous_sentence = _previous_sentence(text, first_start)
    following_sentence = _following_sentence(text, last_end)

    if parsed_quote.preceding_context == START_MARKER:
        if text[:first_start].strip():
            raise ValueError("start marker is only valid at the true start of snapshot text")
    elif previous_sentence is None or parsed_quote.preceding_context != previous_sentence.text:
        raise ValueError("preceding bracket is not the immediate preceding sentence")

    if parsed_quote.following_context == END_MARKER:
        if snapshot.truncated:
            raise ValueError("truncated snapshots cannot use End of Text")
        if text[last_end:].strip():
            raise ValueError("end marker is only valid at the true end of snapshot text")
    elif parsed_quote.following_context == TRUNCATED_END_MARKER:
        if not snapshot.truncated:
            raise ValueError("truncated end marker requires a truncated snapshot")
        if text[last_end:].strip():
            raise ValueError("truncated end marker is only valid at the snapshot boundary")
    elif following_sentence is None or parsed_quote.following_context != following_sentence.text:
        raise ValueError("following bracket is not the immediate following sentence")

    return True


def has_statistical_markers(text: str) -> bool:
    return any(char.isdigit() for char in text) and any(
        _statistical_marker_matches(text, marker) for marker in STATISTICAL_MARKERS
    )


def count_claim_keyword_matches(text: str, claim_keywords: Iterable[str]) -> int:
    return sum(1 for keyword in set(claim_keywords) if _keyword_matches(text, keyword))


def validate_quote_substance(
    parsed_quote: ParsedQuoteBlock,
    claim_keywords: Iterable[str],
) -> QuoteMetrics:
    quoted_text = " ".join(parsed_quote.segments)
    raw_word_count = count_words(quoted_text)
    statistical = has_statistical_markers(quoted_text)
    keyword_matches = count_claim_keyword_matches(
        f"{parsed_quote.preceding_context} {quoted_text} {parsed_quote.following_context}",
        claim_keywords,
    )

    if keyword_matches < 1:
        raise ValueError("quote block does not contain a configured claim keyword")

    minimum_words = STATISTICAL_MIN_WORDS if statistical else NON_STATISTICAL_MIN_WORDS
    if raw_word_count < minimum_words:
        raise ValueError(f"quoted segments contain {raw_word_count} words; need {minimum_words}")

    return QuoteMetrics(
        raw_segment_word_count=raw_word_count,
        has_statistical_markers=statistical,
        claim_keyword_match_count=keyword_matches,
    )


def filter_provisional_candidate(
    provisional: ProvisionalCandidate,
    snapshot: SourceSnapshot,
    *,
    claim_keywords: Iterable[str],
    post_filter_version: str,
    post_filter_validated_at: datetime,
) -> PostExtractionFilterResult:
    try:
        _validate_filter_metadata(post_filter_version, post_filter_validated_at)
        validate_snapshot_integrity(snapshot)
        _validate_provisional_snapshot_match(provisional, snapshot)
        parsed_quote = parse_extracted_quote_block(provisional.extracted_quote_block)
        offsets = _find_offsets_with_valid_context(snapshot, parsed_quote)
        metrics = validate_quote_substance(parsed_quote, claim_keywords)
    except ValueError as exc:
        return _reject("deterministic_filter_failed", str(exc))

    quote_block_id = derive_quote_block_id(
        provisional.source_url,
        provisional.snapshot_sha256,
        offsets,
    )
    candidate = CandidateQuoteBlock(
        run_id=provisional.run_id,
        stance=provisional.stance,
        quote_block_id=quote_block_id,
        source_url=provisional.source_url,
        retrieval_attempt_id=provisional.retrieval_attempt_id,
        query_id=provisional.query_id,
        query_round=provisional.query_round,
        search_rank=provisional.search_rank,
        retrieved_at=snapshot.retrieved_at,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        snapshot_created_at=snapshot.created_at,
        extracted_quote_block=provisional.extracted_quote_block,
        segment_offsets=offsets,
        raw_segment_word_count=metrics.raw_segment_word_count,
        has_statistical_markers=metrics.has_statistical_markers,
        claim_keyword_match_count=metrics.claim_keyword_match_count,
        truncated=snapshot.truncated,
        extraction_prompt_version=provisional.extraction_prompt_version,
        extraction_model_name=provisional.extraction_model_name,
        extracted_at=provisional.extracted_at,
        post_filter_version=post_filter_version,
        post_filter_validated_at=post_filter_validated_at,
    )
    return PostExtractionFilterResult(valid=True, candidate=candidate)


def verify_candidate_against_snapshot(
    snapshot: SourceSnapshot,
    candidate: CandidateQuoteBlock,
    *,
    claim_keywords: Iterable[str] | None = None,
) -> bool:
    validate_snapshot_integrity(snapshot)
    if candidate.snapshot_id != snapshot.snapshot_id:
        raise ValueError("candidate snapshot_id does not match snapshot")
    if candidate.snapshot_sha256 != snapshot.snapshot_sha256:
        raise ValueError("candidate snapshot hash does not match snapshot")
    if candidate.truncated != snapshot.truncated:
        raise ValueError("candidate truncated flag does not match snapshot")

    parsed_quote = parse_extracted_quote_block(candidate.extracted_quote_block)
    if len(parsed_quote.segments) != len(candidate.segment_offsets):
        raise ValueError("candidate segment count does not match parsed quote block")
    for segment, offset in zip(parsed_quote.segments, candidate.segment_offsets, strict=True):
        if snapshot.normalized_text[offset.start_char : offset.end_char] != segment:
            raise ValueError("candidate segment offsets do not match snapshot text")

    validate_bracket_context(snapshot, parsed_quote, candidate.segment_offsets)
    quoted_text = " ".join(parsed_quote.segments)
    if candidate.raw_segment_word_count != count_words(quoted_text):
        raise ValueError("candidate raw word count does not match quoted segments")
    if candidate.has_statistical_markers != has_statistical_markers(quoted_text):
        raise ValueError("candidate statistical marker flag does not match quoted segments")
    if claim_keywords is not None:
        metrics = validate_quote_substance(parsed_quote, claim_keywords)
        if candidate.claim_keyword_match_count != metrics.claim_keyword_match_count:
            raise ValueError("candidate keyword match count does not match quote block")

    expected_id = derive_quote_block_id(
        candidate.source_url,
        candidate.snapshot_sha256,
        candidate.segment_offsets,
    )
    if candidate.quote_block_id != expected_id:
        raise ValueError("candidate quote_block_id is not the deterministic ID")
    return True


def _reject(code: str, message: str) -> PostExtractionFilterResult:
    return PostExtractionFilterResult(
        valid=False,
        rejection_code=code,
        rejection_message=message,
    )


def _validate_provisional_snapshot_match(
    provisional: ProvisionalCandidate,
    snapshot: SourceSnapshot,
) -> None:
    if provisional.run_id != snapshot.run_id:
        raise ValueError("provisional run_id does not match snapshot")
    if provisional.retrieval_attempt_id != snapshot.retrieval_attempt_id:
        raise ValueError("provisional retrieval_attempt_id does not match snapshot")
    if provisional.snapshot_id != snapshot.snapshot_id:
        raise ValueError("provisional snapshot_id does not match snapshot")
    if provisional.snapshot_sha256 != snapshot.snapshot_sha256:
        raise ValueError("provisional snapshot hash does not match snapshot")
    if provisional.source_url != snapshot.source_url:
        raise ValueError("provisional source_url does not match snapshot")


def _validate_filter_metadata(post_filter_version: str, post_filter_validated_at: datetime) -> None:
    if post_filter_version == "":
        raise ValueError("post_filter_version must be non-empty")
    if post_filter_validated_at.tzinfo is None or post_filter_validated_at.utcoffset() is None:
        raise ValueError("post_filter_validated_at must be timezone-aware")


def _find_offsets_with_valid_context(
    snapshot: SourceSnapshot,
    parsed_quote: ParsedQuoteBlock,
) -> list[SegmentOffset]:
    saw_segment_match = False
    context_error: ValueError | None = None
    for offsets in _candidate_offset_sequences(snapshot.normalized_text, parsed_quote.segments):
        saw_segment_match = True
        try:
            validate_bracket_context(snapshot, parsed_quote, offsets)
        except ValueError as exc:
            context_error = exc
            continue
        return offsets
    if saw_segment_match and context_error is not None:
        raise context_error
    raise ValueError("quoted segment does not appear in snapshot text")


def _candidate_offset_sequences(
    text: str,
    segments: list[str],
    segment_index: int = 0,
    search_start: int = 0,
) -> Iterable[list[SegmentOffset]]:
    if segment_index == len(segments):
        yield []
        return

    segment = segments[segment_index]
    start = text.find(segment, search_start)
    while start != -1:
        end = start + len(segment)
        current = SegmentOffset(start_char=start, end_char=end)
        for remainder in _candidate_offset_sequences(text, segments, segment_index + 1, end):
            yield [current, *remainder]
        start = text.find(segment, start + 1)


def _sentence_spans(text: str) -> list[_SentenceSpan]:
    spans: list[_SentenceSpan] = []
    for match in _SENTENCE_RE.finditer(text):
        raw = match.group(0)
        if not raw.strip():
            continue
        leading_whitespace = len(raw) - len(raw.lstrip())
        trailing_index = len(raw.rstrip())
        start = match.start() + leading_whitespace
        end = match.start() + trailing_index
        if start < end:
            spans.append(_SentenceSpan(start_char=start, end_char=end, text=text[start:end]))
    return spans


def _previous_sentence(text: str, offset: int) -> _SentenceSpan | None:
    previous: _SentenceSpan | None = None
    for span in _sentence_spans(text):
        if span.end_char <= offset:
            previous = span
        else:
            break
    return previous


def _following_sentence(text: str, offset: int) -> _SentenceSpan | None:
    for span in _sentence_spans(text):
        if span.start_char >= offset:
            return span
    return None


def _keyword_matches(text: str, keyword: str) -> bool:
    clean_keyword = keyword.strip()
    if clean_keyword == "":
        return False
    escaped_parts = [re.escape(part) for part in clean_keyword.casefold().split()]
    phrase_pattern = r"\s+".join(escaped_parts)
    pattern = rf"(?<!\w){phrase_pattern}(?!\w)"
    return re.search(pattern, text.casefold()) is not None


def _statistical_marker_matches(text: str, marker: str) -> bool:
    if marker == "%":
        return marker in text
    pattern = rf"(?<!\w){re.escape(marker.casefold())}(?!\w)"
    return re.search(pattern, text.casefold()) is not None
