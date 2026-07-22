from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from agents.researcher import (
    NON_STATISTICAL_MIN_WORDS,
    STATISTICAL_MIN_WORDS,
    PostExtractionFilterResult,
    build_source_snapshot,
    filter_provisional_candidate,
    verify_candidate_against_snapshot,
)
from models import ProvisionalCandidate, SegmentOffset, SourceSnapshot, Stance
from utils import compute_sha256, count_words

_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
_RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
_RETRIEVAL_ID = UUID("10000000-0000-0000-0000-000000000002")
_QUERY_ID = UUID("10000000-0000-0000-0000-000000000003")
_SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000004")
_SOURCE_URL = "https://example.test/source"
_BEFORE = "Opening context establishes scope."
_AFTER = "Closing context names limitations."


def _words(prefix: list[str], total: int) -> str:
    filler_needed = total - len(prefix)
    return " ".join([*prefix, *["filler" for _ in range(filler_needed)]])


def _statistical_sentence(word_count: int = STATISTICAL_MIN_WORDS) -> str:
    return f"{_words(['policy', 'evidence', 'shows', '50%', 'growth'], word_count)}."


def _non_statistical_sentence(word_count: int = NON_STATISTICAL_MIN_WORDS) -> str:
    return f"{_words(['policy', 'evidence'], word_count)}."


def _snapshot(text: str, *, truncated: bool = False) -> SourceSnapshot:
    return build_source_snapshot(
        run_id=_RUN_ID,
        retrieval_attempt_id=_RETRIEVAL_ID,
        snapshot_id=_SNAPSHOT_ID,
        source_url=_SOURCE_URL,
        retrieved_at=_NOW,
        normalized_text=text,
        truncated=truncated,
        created_at=_NOW,
    )


def _provisional(snapshot: SourceSnapshot, quote_block: str) -> ProvisionalCandidate:
    return ProvisionalCandidate(
        run_id=snapshot.run_id,
        stance=Stance.SUPPORTING,
        source_url=snapshot.source_url,
        retrieval_attempt_id=snapshot.retrieval_attempt_id,
        query_id=_QUERY_ID,
        query_round=1,
        search_rank=1,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        extracted_quote_block=quote_block,
        extraction_prompt_version="extract-v1",
        extraction_model_name="test-model",
        extracted_at=_NOW,
    )


def _filter(
    snapshot: SourceSnapshot,
    quote_block: str,
    keywords: list[str] | None = None,
) -> PostExtractionFilterResult:
    return filter_provisional_candidate(
        _provisional(snapshot, quote_block),
        snapshot,
        claim_keywords=keywords or ["policy"],
        post_filter_version="phase3-filter-v1",
        validation_clock=lambda: _NOW,
    )


def _valid_statistical_case() -> tuple[SourceSnapshot, str, str]:
    segment = _statistical_sentence()
    text = f"{_BEFORE} {segment} {_AFTER}"
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'
    return _snapshot(text), segment, quote_block


def _assert_rejected(result: PostExtractionFilterResult) -> None:
    assert result.valid is False
    assert result.candidate is None
    assert result.rejection_code is not None
    assert result.rejection_message is not None


def test_valid_statistical_quote_gets_deterministic_candidate_id() -> None:
    snapshot, _, quote_block = _valid_statistical_case()

    first = _filter(snapshot, quote_block)
    second = _filter(snapshot, quote_block)

    assert first.valid is True
    assert second.valid is True
    assert first.candidate is not None
    assert second.candidate is not None
    assert first.candidate.quote_block_id == second.candidate.quote_block_id
    assert first.candidate.raw_segment_word_count == STATISTICAL_MIN_WORDS
    assert first.candidate.has_statistical_markers is True
    assert verify_candidate_against_snapshot(
        snapshot,
        first.candidate,
        claim_keywords=["policy"],
    )


def test_post_filter_uses_validation_clock_instead_of_extraction_time() -> None:
    snapshot, _, quote_block = _valid_statistical_case()
    validation_time = _NOW + timedelta(seconds=1)

    result = filter_provisional_candidate(
        _provisional(snapshot, quote_block),
        snapshot,
        claim_keywords=["policy"],
        post_filter_version="phase3-filter-v1",
        validation_clock=lambda: validation_time,
    )

    assert result.valid is True
    assert result.candidate is not None
    assert result.candidate.extracted_at == _NOW
    assert result.candidate.post_filter_validated_at == validation_time


def test_valid_repeated_segment_uses_occurrence_with_matching_brackets() -> None:
    segment = _statistical_sentence()
    text = f"Wrong context. {segment} Buffer sentence. {_BEFORE} {segment} {_AFTER}"
    snapshot = _snapshot(text)
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    assert result.valid is True
    assert result.candidate is not None
    assert result.candidate.segment_offsets[0].start_char > snapshot.normalized_text.find(segment)


@pytest.mark.parametrize(
    ("quote_block", "keywords"),
    [
        ("not bracketed", ["policy"]),
        (f'[{_BEFORE}] "missing segment text" [{_AFTER}]', ["policy"]),
        (f'[Wrong preceding sentence.] "{_statistical_sentence()}" [{_AFTER}]', ["policy"]),
        (f'[{_BEFORE}] "{_statistical_sentence()}" [Wrong following sentence.]', ["policy"]),
        (f'[{_BEFORE}] "{_statistical_sentence()}" [{_AFTER}]', ["unmatched"]),
    ],
)
def test_invalid_quote_blocks_are_rejected_without_candidate_id(
    quote_block: str,
    keywords: list[str],
) -> None:
    snapshot, _, _ = _valid_statistical_case()

    result = _filter(snapshot, quote_block, keywords)

    _assert_rejected(result)


def test_segments_must_appear_in_extracted_order() -> None:
    first = _statistical_sentence()
    second = _non_statistical_sentence()
    snapshot = _snapshot(f"{_BEFORE} {second} Buffer sentence. {first} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{first}... {second}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_snapshot_hash_mismatch_rejects_before_candidate_id() -> None:
    good, _, quote_block = _valid_statistical_case()
    bad_snapshot = SourceSnapshot(
        run_id=good.run_id,
        retrieval_attempt_id=good.retrieval_attempt_id,
        snapshot_id=good.snapshot_id,
        source_url=good.source_url,
        retrieved_at=good.retrieved_at,
        normalized_text=good.normalized_text,
        snapshot_sha256="b" * 64,
        word_count=good.word_count,
        truncated=good.truncated,
        created_at=good.created_at,
    )

    result = _filter(bad_snapshot, quote_block)

    _assert_rejected(result)


def test_snapshot_word_count_mismatch_rejects_before_candidate_id() -> None:
    good, _, quote_block = _valid_statistical_case()
    bad_snapshot = SourceSnapshot(
        run_id=good.run_id,
        retrieval_attempt_id=good.retrieval_attempt_id,
        snapshot_id=good.snapshot_id,
        source_url=good.source_url,
        retrieved_at=good.retrieved_at,
        normalized_text=good.normalized_text,
        snapshot_sha256=compute_sha256(good.normalized_text),
        word_count=good.word_count + 1,
        truncated=good.truncated,
        created_at=good.created_at,
    )

    result = _filter(bad_snapshot, quote_block)

    _assert_rejected(result)


def test_truncated_snapshot_cannot_use_end_of_text_marker() -> None:
    segment = _statistical_sentence()
    snapshot = _snapshot(f"{_BEFORE} {segment}", truncated=True)
    quote_block = f'[{_BEFORE}] "{segment}" [End of Text]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_truncated_end_marker_requires_truncated_boundary() -> None:
    segment = _statistical_sentence()
    snapshot = _snapshot(f"{_BEFORE} {segment}")
    quote_block = f'[{_BEFORE}] "{segment}" [Truncated End of Snapshot]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_start_marker_only_valid_at_true_start() -> None:
    segment = _statistical_sentence()
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[Start of Text] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_valid_boundary_markers_pass_at_true_boundaries() -> None:
    segment = _statistical_sentence()
    snapshot = _snapshot(segment)
    quote_block = f'[Start of Text] "{segment}" [End of Text]'

    result = _filter(snapshot, quote_block)

    assert result.valid is True
    assert result.candidate is not None


def test_valid_truncated_boundary_marker_passes_at_snapshot_boundary() -> None:
    segment = _statistical_sentence()
    snapshot = _snapshot(f"{_BEFORE} {segment}", truncated=True)
    quote_block = f'[{_BEFORE}] "{segment}" [Truncated End of Snapshot]'

    result = _filter(snapshot, quote_block)

    assert result.valid is True
    assert result.candidate is not None


def test_non_statistical_quote_below_100_words_rejected_without_id() -> None:
    segment = _non_statistical_sentence(NON_STATISTICAL_MIN_WORDS - 1)
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_statistical_quote_below_50_words_rejected_without_id() -> None:
    segment = _statistical_sentence(STATISTICAL_MIN_WORDS - 1)
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


@pytest.mark.parametrize(
    "segment",
    [
        f"{_words(['policy', 'evidence', 'shows', '2026'], STATISTICAL_MIN_WORDS)}.",
        f"{_words(['policy', 'evidence', 'shows', 'growth'], STATISTICAL_MIN_WORDS)}.",
    ],
)
def test_digit_or_marker_alone_does_not_unlock_statistical_threshold(segment: str) -> None:
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_marker_substrings_do_not_unlock_statistical_threshold() -> None:
    segment = f"{_words(['policy', 'corporate', 'reporting', '2026'], STATISTICAL_MIN_WORDS)}."
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_invalid_filter_metadata_rejects_without_candidate_id() -> None:
    snapshot, _, quote_block = _valid_statistical_case()

    result = filter_provisional_candidate(
        _provisional(snapshot, quote_block),
        snapshot,
        claim_keywords=["policy"],
        post_filter_version="",
        validation_clock=lambda: _NOW,
    )

    _assert_rejected(result)


def test_ellipsis_is_not_counted_as_a_quoted_word() -> None:
    first = _words(["policy"], 25) + "."
    second = _words(["evidence", "50%", "growth"], 25) + "."
    snapshot = _snapshot(f"{_BEFORE} {first} Bridge sentence. {second} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{first}... {second}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    assert result.valid is True
    assert result.candidate is not None
    assert result.candidate.raw_segment_word_count == count_words(f"{first} {second}")


def test_verify_rejects_tampered_candidate_offsets_even_when_hash_matches() -> None:
    snapshot, segment, quote_block = _valid_statistical_case()
    result = _filter(snapshot, quote_block)
    assert result.candidate is not None
    tampered = result.candidate.model_copy(
        update={
            "segment_offsets": [
                SegmentOffset(start_char=0, end_char=len(segment)),
            ]
        }
    )

    with pytest.raises(ValueError, match="offsets"):
        verify_candidate_against_snapshot(snapshot, tampered, claim_keywords=["policy"])
