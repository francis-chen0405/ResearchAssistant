"""New quotations retain exact selected occurrences and complete sentence context."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from researchassistant.agents.v2_extraction import V2ExtractionState, _extract_source
from researchassistant.contracts.models import (
    ProvisionalCandidate,
    ResearchDirection,
    V2VerbatimQuoteSelection,
)
from researchassistant.evidence.evidence_core import (
    FRESH_QUOTE_CONTEXT_FILTER_VERSION,
    assemble_fresh_selected_quote,
    assemble_quote_block_from_selected_segments,
    build_source_snapshot,
    filter_provisional_candidate,
    fresh_sentence_spans,
    parse_extracted_quote_block,
    verify_candidate_against_snapshot,
)
from researchassistant.providers.llm import LLMProviderCapabilities, LLMRequest

NOW = datetime(2026, 10, 17, tzinfo=UTC)
PASSAGE = (
    "The course improved completion for the sampled participants in this generated study "
    "while the comparison group used the ordinary materials over the same observation "
    "period and experienced lower completion under the measured conditions."
)


class Selector:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True, supports_structured_output_control=True
    )

    def __init__(self, ranges: tuple[tuple[int, int], ...]) -> None:
        self.ranges = ranges

    def generate(self, request: LLMRequest) -> V2VerbatimQuoteSelection:
        return V2VerbatimQuoteSelection(
            selected_sentence_ranges=tuple(
                {"start_sentence": start, "end_sentence": end} for start, end in self.ranges
            )
        )


@pytest.mark.core
@pytest.mark.parametrize("multiple", [False, True])
def test_extraction_retains_later_selected_occurrences(multiple: bool) -> None:
    sentences = [
        "The first cohort excluded older adults.",
        PASSAGE,
        "The second cohort included all ages.",
        PASSAGE,
        "The second estimate is subject to sampling uncertainty.",
        PASSAGE,
        "These findings apply only to the second cohort.",
    ]
    text = " ".join(sentences)
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/generated",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=False,
        created_at=NOW,
    )
    ranges = ((4, 4), (6, 6)) if multiple else ((4, 4),)
    result = _extract_source(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        exact_claim="The course improves completion.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=Selector(ranges),
        clock=lambda: NOW,
    )
    assert result.state is V2ExtractionState.EXTRACTED, result.failure
    candidate = result.candidate
    assert candidate is not None
    spans = fresh_sentence_spans(text)
    assert [offset.start_char for offset in candidate.segment_offsets] == [
        spans[start - 1].start_char for start, _ in ranges
    ]
    parsed = parse_extracted_quote_block(candidate.extracted_quote_block)
    assert parsed.preceding_context == sentences[2]
    assert parsed.following_context == sentences[6 if multiple else 4]
    assert candidate.post_filter_version == FRESH_QUOTE_CONTEXT_FILTER_VERSION
    assert verify_candidate_against_snapshot(snapshot, candidate)
    changed = candidate.model_copy(
        update={
            "segment_offsets": [
                candidate.segment_offsets[0].model_copy(
                    update={
                        "start_char": spans[1].start_char,
                        "end_char": spans[1].end_char,
                    }
                ),
                *candidate.segment_offsets[1:],
            ]
        }
    )
    with pytest.raises(ValueError):
        verify_candidate_against_snapshot(snapshot, changed)


@pytest.mark.core
def test_decimal_context_is_complete_and_historical_assembly_remains_exact() -> None:
    before = "This observational sample excludes residents older than 65.5 years."
    after = "No improvement was measured above the 0.5 mg dose threshold."
    text = f"{before} {PASSAGE} {after}"
    selection = V2VerbatimQuoteSelection(
        selected_sentence_ranges=({"start_sentence": 2, "end_sentence": 2},)
    )
    current, offsets = assemble_fresh_selected_quote(text, selection, truncated=False)
    parsed = parse_extracted_quote_block(current)
    assert parsed.preceding_context == before and parsed.following_context == after
    assert text[offsets[0].start_char : offsets[0].end_char] == PASSAGE
    # The recorded historical assembler stays available with its original bytes.
    historical = assemble_quote_block_from_selected_segments(text, selection, truncated=False)
    assert historical == f'[5 years.] "{PASSAGE}" [No improvement was measured above the 0.]'
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/generated",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=False,
        created_at=NOW,
    )
    provisional = ProvisionalCandidate(
        run_id=snapshot.run_id,
        stance="supporting",
        source_url=snapshot.source_url,
        retrieval_attempt_id=snapshot.retrieval_attempt_id,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        extracted_quote_block=current,
        extraction_prompt_version="unchanged-prompt",
        extraction_model_name="offline",
        extracted_at=NOW,
    )
    filtered = filter_provisional_candidate(
        provisional,
        snapshot,
        claim_keywords=("course",),
        post_filter_version=FRESH_QUOTE_CONTEXT_FILTER_VERSION,
        selected_offsets=offsets,
        validation_clock=lambda: NOW,
    )
    assert filtered.valid and filtered.candidate is not None
    assert verify_candidate_against_snapshot(snapshot, filtered.candidate)
    historical_filtered = filter_provisional_candidate(
        provisional.model_copy(update={"extracted_quote_block": historical}),
        snapshot,
        claim_keywords=("course",),
        post_filter_version="researchassistant-v2-phase-12-post-filter-v1",
        validation_clock=lambda: NOW,
    )
    assert historical_filtered.valid and historical_filtered.candidate is not None
    assert verify_candidate_against_snapshot(snapshot, historical_filtered.candidate)


@pytest.mark.core
def test_fresh_filter_refuses_missing_or_substituted_selected_offsets() -> None:
    text = f"Opening context. {PASSAGE} Closing context."
    selection = V2VerbatimQuoteSelection(
        selected_sentence_ranges=({"start_sentence": 2, "end_sentence": 2},)
    )
    with pytest.raises(ValueError, match="exceeds the snapshot"):
        assemble_fresh_selected_quote(
            text,
            V2VerbatimQuoteSelection(
                selected_sentence_ranges=({"start_sentence": 4, "end_sentence": 4},)
            ),
            truncated=False,
        )
    quote, offsets = assemble_fresh_selected_quote(text, selection, truncated=True)
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/generated",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=True,
        created_at=NOW,
    )
    provisional = ProvisionalCandidate(
        run_id=snapshot.run_id,
        stance="supporting",
        source_url=snapshot.source_url,
        retrieval_attempt_id=snapshot.retrieval_attempt_id,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        extracted_quote_block=quote,
        extraction_prompt_version="unchanged-prompt",
        extraction_model_name="offline",
        extracted_at=NOW,
    )
    for selected in (None, (offsets[0].model_copy(update={"start_char": 0}),)):
        filtered = filter_provisional_candidate(
            provisional,
            snapshot,
            claim_keywords=("course",),
            post_filter_version=FRESH_QUOTE_CONTEXT_FILTER_VERSION,
            selected_offsets=selected,
            validation_clock=lambda: NOW,
        )
        assert not filtered.valid and filtered.candidate is None
