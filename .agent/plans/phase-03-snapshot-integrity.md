# Phase 03 - Snapshot and Quotation Integrity

## Purpose

Implement deterministic snapshot and quote-block integrity checks without adding retrieval,
scraping, LLM calls, Analyst scoring, Reviewer logic, Ledger admission, rendering, or
orchestration.

## Files Changed

- `utils.py`
- `agents/researcher.py`
- `tests/test_phase3.py`
- `.agent/plans/phase-03-snapshot-integrity.md`
- `.agent/PLANS.md`
- `STATUS.md`
- `HANDOFF.md`

## Architectural Decisions

- Put shared deterministic researcher filtering in `agents/researcher.py` because both
  supporting and opposing researchers must apply the same post-extraction rules, while
  the stance-specific agent files remain placeholders.
- Keep hash, word-count, and deterministic UUID helpers in `utils.py`.
- Return a strict typed `PostExtractionFilterResult` for post-extraction filtering.
  Rejected provisional candidates carry rejection details and no `CandidateQuoteBlock`,
  so invalid candidates receive no `quote_block_id`.
- Use deterministic helper models for parsed quote blocks and quote metrics; these are
  strict Pydantic artifacts and are not raw dictionaries.
- Keep Phase 1 Pydantic contracts and Phase 2 SQLite schema unchanged.
- Use canonical JSON serialization of segment offsets inside the UUID5 name input so
  quote-block ID derivation is stable.

## Deterministic Thresholds

The architecture explicitly defines these Phase 3 thresholds:

- Statistical quote threshold: quoted segments with at least one digit and at least one
  statistical marker require at least 50 words.
- Non-statistical quote threshold: all other quoted segments require at least 100 words.
- Statistical markers are `%`, `percent`, `rate`, `ratio`, `average`, `median`,
  `index`, `p-value`, `million`, `billion`, `growth`, and `decline`.

Ellipsis tokens used to splice quoted segments are not counted as words.

## Acceptance Criteria

- Snapshot SHA-256 and word count are recomputed from `normalized_text`.
- Bracketed quote blocks are parsed deterministically.
- Quoted segments must appear exactly in the snapshot, in sequential order.
- Segment offsets must slice back to the exact quoted text.
- Bracket context must match the immediate surrounding snapshot sentences.
- `[Start of Text]`, `[End of Text]`, and `[Truncated End of Snapshot]` are accepted
  only at valid boundaries.
- Truncated snapshots never accept `[End of Text]`.
- Quote length, statistical-marker, and claim-keyword rules are enforced before ID
  assignment.
- Future Analyst code can call a deterministic re-check function, but no Analyst scoring
  or review behavior is implemented.

## Commands To Verify The Phase

```powershell
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q
python -m ruff check .
python -m ruff format --check .
```

## Out of Scope

- Web retrieval or scraping.
- LLM extraction or model-provider integration.
- Analyst semantic scoring, Statement Reviewer logic, Ledger admission, synthesis,
  rendering, final validation, or orchestration.
- Database schema changes or persistence changes.

## Unresolved Risks

- Sentence-boundary detection is intentionally simple and deterministic for MVP quote
  integrity. Later retrieval/extraction phases may need stronger normalization rules, but
  adding NLP dependencies is outside Phase 3.
- The local `.pytest_cache` directory may still emit a permission warning during pytest.
