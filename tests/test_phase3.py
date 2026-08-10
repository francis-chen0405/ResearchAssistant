from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from agents.researcher import (
    CURRENT_QUOTE_LENGTH_POLICY,
    EVIDENCE_POLICY_VERSION,
    LEGACY_FIXTURE_QUOTE_LENGTH_POLICY,
    NON_STATISTICAL_MIN_WORDS,
    STATISTICAL_MIN_WORDS,
    PostExtractionFilterResult,
    build_source_snapshot,
    derive_quote_block_id,
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


def test_current_and_legacy_quote_policies_are_explicitly_separate() -> None:
    assert EVIDENCE_POLICY_VERSION == "mvp6.4-evidence-density-50-75-v1"
    assert STATISTICAL_MIN_WORDS == 50
    assert NON_STATISTICAL_MIN_WORDS == 75
    assert CURRENT_QUOTE_LENGTH_POLICY.statistical_min_words == 50
    assert CURRENT_QUOTE_LENGTH_POLICY.non_statistical_min_words == 75
    assert LEGACY_FIXTURE_QUOTE_LENGTH_POLICY.statistical_min_words == 50
    assert LEGACY_FIXTURE_QUOTE_LENGTH_POLICY.non_statistical_min_words == 100


@pytest.mark.parametrize(("word_count", "accepted"), [(49, False), (50, True), (51, True)])
def test_statistical_quote_boundary(word_count: int, accepted: bool) -> None:
    segment = _statistical_sentence(word_count)
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    result = _filter(snapshot, f'[{_BEFORE}] "{segment}" [{_AFTER}]')

    assert result.valid is accepted
    assert (result.candidate is not None) is accepted


@pytest.mark.parametrize(("word_count", "accepted"), [(74, False), (75, True), (76, True)])
def test_non_statistical_quote_boundary(word_count: int, accepted: bool) -> None:
    segment = _non_statistical_sentence(word_count)
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    result = _filter(snapshot, f'[{_BEFORE}] "{segment}" [{_AFTER}]')

    assert result.valid is accepted
    assert (result.candidate is not None) is accepted


def test_non_statistical_quote_requires_at_least_seventy_five_words() -> None:
    accepted_segment = _non_statistical_sentence(75)
    accepted_snapshot = _snapshot(f"{_BEFORE} {accepted_segment} {_AFTER}")
    accepted = _filter(
        accepted_snapshot,
        f'[{_BEFORE}] "{accepted_segment}" [{_AFTER}]',
    )
    rejected_segment = _non_statistical_sentence(74)
    rejected_snapshot = _snapshot(f"{_BEFORE} {rejected_segment} {_AFTER}")
    rejected = _filter(
        rejected_snapshot,
        f'[{_BEFORE}] "{rejected_segment}" [{_AFTER}]',
    )

    assert accepted.valid is True
    assert accepted.candidate is not None
    assert accepted.candidate.raw_segment_word_count == 75
    assert rejected.valid is False
    assert rejected.rejection_message == "quoted segments contain 74 words; need 75"


def test_legacy_fixture_policy_does_not_leak_into_current_default_filtering() -> None:
    segment = _non_statistical_sentence(75)
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    current = _filter(snapshot, quote_block)
    legacy = filter_provisional_candidate(
        _provisional(snapshot, quote_block),
        snapshot,
        claim_keywords=["policy"],
        post_filter_version="legacy-fixture-test",
        validation_clock=lambda: _NOW,
        quote_length_policy=LEGACY_FIXTURE_QUOTE_LENGTH_POLICY,
    )

    assert current.valid is True
    assert current.candidate is not None
    assert legacy.valid is False
    assert legacy.candidate is None
    assert legacy.rejection_message == "quoted segments contain 75 words; need 100"


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


def test_non_statistical_quote_below_75_words_rejected_without_id() -> None:
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
        f"{_words(['policy', 'evidence', 'shows', '2026'], 74)}.",
        f"{_words(['policy', 'evidence', 'shows', 'growth'], 74)}.",
    ],
)
def test_digit_or_marker_alone_does_not_unlock_statistical_threshold(segment: str) -> None:
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


def test_marker_substrings_do_not_unlock_statistical_threshold() -> None:
    segment = f"{_words(['policy', 'corporate', 'reporting', '2026'], 74)}."
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    quote_block = f'[{_BEFORE}] "{segment}" [{_AFTER}]'

    result = _filter(snapshot, quote_block)

    _assert_rejected(result)


@pytest.mark.parametrize("marker", ["50%", "2026 PERCENT,", "2026 p-value;"])
def test_statistical_markers_are_case_insensitive_and_punctuation_safe(marker: str) -> None:
    segment = f"{_words(['policy', 'evidence', marker], 50)}."
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")

    result = _filter(snapshot, f'[{_BEFORE}] "{segment}" [{_AFTER}]')

    assert result.valid is True
    assert result.candidate is not None
    assert result.candidate.has_statistical_markers is True


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
    first = _words(["policy"], 37) + "."
    second = _words(["evidence", "50%", "growth"], 38) + "."
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


def test_verify_rejects_underlength_candidate_without_keyword_recheck() -> None:
    segment = _non_statistical_sentence(74)
    snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    rejected = _filter(snapshot, f'[{_BEFORE}] "{segment}" [{_AFTER}]')
    assert rejected.valid is False

    accepted_segment = _non_statistical_sentence(75)
    accepted_snapshot = _snapshot(f"{_BEFORE} {accepted_segment} {_AFTER}")
    accepted = _filter(
        accepted_snapshot,
        f'[{_BEFORE}] "{accepted_segment}" [{_AFTER}]',
    )
    assert accepted.candidate is not None
    short_snapshot = _snapshot(f"{_BEFORE} {segment} {_AFTER}")
    start_char = short_snapshot.normalized_text.index(segment)
    offsets = [SegmentOffset(start_char=start_char, end_char=start_char + len(segment))]
    underlength = accepted.candidate.model_copy(
        update={
            "extracted_quote_block": f'[{_BEFORE}] "{segment}" [{_AFTER}]',
            "segment_offsets": offsets,
            "raw_segment_word_count": 74,
        }
    )
    underlength = underlength.model_copy(
        update={
            "snapshot_sha256": short_snapshot.snapshot_sha256,
            "quote_block_id": derive_quote_block_id(
                underlength.source_url,
                short_snapshot.snapshot_sha256,
                offsets,
            ),
        }
    )

    with pytest.raises(ValueError, match="need 75"):
        verify_candidate_against_snapshot(short_snapshot, underlength)


def test_downstream_recheck_rejects_tampered_statistical_candidate() -> None:
    accepted_segment = _statistical_sentence(50)
    accepted_snapshot = _snapshot(f"{_BEFORE} {accepted_segment} {_AFTER}")
    accepted = _filter(
        accepted_snapshot,
        f'[{_BEFORE}] "{accepted_segment}" [{_AFTER}]',
    )
    assert accepted.candidate is not None

    short_segment = _statistical_sentence(49)
    short_snapshot = _snapshot(f"{_BEFORE} {short_segment} {_AFTER}")
    start_char = short_snapshot.normalized_text.index(short_segment)
    offsets = [SegmentOffset(start_char=start_char, end_char=start_char + len(short_segment))]
    tampered = accepted.candidate.model_copy(
        update={
            "snapshot_sha256": short_snapshot.snapshot_sha256,
            "extracted_quote_block": f'[{_BEFORE}] "{short_segment}" [{_AFTER}]',
            "segment_offsets": offsets,
            "raw_segment_word_count": 49,
            "quote_block_id": derive_quote_block_id(
                accepted.candidate.source_url,
                short_snapshot.snapshot_sha256,
                offsets,
            ),
        }
    )

    with pytest.raises(ValueError, match="need 50"):
        verify_candidate_against_snapshot(short_snapshot, tampered)
