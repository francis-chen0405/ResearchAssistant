# Phase 07B - Search and Scraping Provider Interfaces

## Purpose

Implement vendor-isolated synchronous search and scraper contracts plus deterministic,
offline retrieval behavior with fake providers. Phase 7B stops at trusted snapshot
creation and does not add LLM extraction, semantic scoring, rendering, or full live
orchestration.

## Files Changed

- `providers/search.py`
- `providers/scraper.py`
- `agents/supportingresearcher.py`
- `agents/opposingresearcher.py`
- `tests/test_phase7.py`
- `models.py` (compatibility fix: freeze `SourceSnapshot`)
- `frontend/streamlit_app.py` (compatibility fix: remove duplicate/misplaced imports)
- `.agent/plans/phase-07-retrieval.md`
- `STATUS.md`
- `HANDOFF.md`

The prompt named both `phase-07-retrieval.md` and
`phase-07-retrieval-providers.md`. The repository roadmap identifies
`.agent/plans/phase-07-retrieval.md` as canonical, so this phase uses that path and does
not create a second plan source.

## Implementation Design

- `SearchProvider` and `ScraperProvider` are runtime-checkable synchronous Protocols.
- Provider inputs and outputs are strict Pydantic artifacts: `SearchRequest`,
  `SearchResponse`, `SearchResult`, `ScrapeRequest`, and `ScrapeResponse`.
- `retrieve_supporting()` and `retrieve_opposing()` each execute exactly three
  stance-appropriate queries and preserve the top three provider-ranked results.
- `retrieve_balanced()` runs both sides with one shared deduplication boundary and
  validates exactly 18 intended attempts with equal nine-attempt depth.
- Required site exclusions are revalidated and appended to every provider search
  request.
- Each intended result produces a typed `RetrievalOutcome` containing the existing
  `RetrievalRecord`, scrape status, content type, retry count, optional explicit failure,
  optional snapshot ID, and optional duplicate reference.
- Runtime provider outputs must be the declared strict Pydantic response artifacts;
  malformed raw values fail explicitly at the provider boundary.
- Retrieval outcome and batch validators enforce consistent statuses, attempts, content
  types, snapshot IDs, and snapshot provenance rather than relying on tests alone.
- Original search URLs and scraper-resolved URLs remain distinct in every retrieval
  record.
- Scraper timeouts retry synchronously according to a strict `RetryPolicy`. Exhausted
  timeouts and provider failures remain explicit typed outcomes; non-timeout provider
  failures are not retried.
- PDF and binary content types are explicitly unsupported. Text and XML-family content
  types are normalized and recorded.
- Scraped text is whitespace-normalized and limited to its first 3,000 words. The
  `truncated` flag is true only when additional words existed.
- Trusted snapshots are fully constructed and integrity-checked before they are added
  to results or supplied to the optional downstream snapshot consumer.
- Original URL, resolved URL, and normalized-content SHA-256 deduplication prevent
  duplicate snapshots. Balanced retrieval shares deduplication across both stances.
- Retrieval and snapshot UUIDs are deterministic UUID5 values derived from stable run,
  query, rank, URL, and content inputs.
- All timestamps are timezone-aware; tests inject a fixed UTC clock.

## Architectural Decisions

- No dependencies, database schema changes, async behavior, real network adapter, API
  keys, or LLM integration were added.
- Existing `RetrievalRecord` remains the stable persisted retrieval artifact. Phase 7B
  adds scrape-specific metadata in a strict typed `RetrievalOutcome` rather than
  changing the Phase 2 SQLite schema outside this phase boundary.
- `SourceSnapshot` is now frozen in memory as well as insert-only in SQLite. This is the
  smallest compatibility fix required to enforce the architecture's immutable snapshot
  rule; all existing construction and persistence behavior remains unchanged.
- The committed Phase 7A frontend contained duplicate imports and module imports after
  executable path setup, which made required full-repository Ruff verification fail.
  The compatibility cleanup only consolidates imports, keeps the path setup, and adds
  narrow `E402` annotations to the two imports that necessarily follow it.
- Search-provider failure or fewer than three results raises an explicit
  `SearchProviderError`; it never silently reduces retrieval depth.
- Phase 7B returns snapshots only. Extraction remains unimplemented until Phase 8.

## Acceptance Criteria

- Exactly three supporting and three opposing queries execute.
- Every query requests exactly three results and contains all required exclusions.
- Exactly 18 intended retrieval outcomes are recorded for a successful balanced run.
- Supporting and opposing batches have equal fixed depth.
- Search order, rounds, ranks, original URLs, resolved URLs, statuses, content types,
  and timezone-aware timestamps are preserved.
- Original URL, resolved URL, and normalized-content duplicates create no duplicate
  snapshots.
- Timeouts retry up to the configured maximum and remain explicit after exhaustion.
- Failed scrapes and unsupported PDF/binary content create no snapshots and remain
  explicit.
- Snapshot text contains no more than 3,000 words and reports truncation accurately.
- Snapshots are immutable and exist before any downstream consumer is invoked.
- Tests use only injected fakes and fail if normal retrieval tries to open a real
  network connection.
- No LLM, semantic scoring, renderer, async, or Phase 8 behavior is introduced.

## Commands Run

```bash
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py -q
python -m ruff check .
python -m ruff format --check .
```

Result: all three exact commands failed before project execution with
`zsh: command not found: python` because this shell does not put a bare Python
executable on `PATH`.

The identical commands were rerun with the repository virtual environment first on
`PATH`:

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py -q
PATH="$PWD/.venv/bin:$PATH" python -m ruff check .
PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .
```

Result: all passed.

Additional verification:

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest
```

Result: 205 passed in 2.15s.

## Exact Test Results

- Required Phase 1 through Phase 7 test selection: 203 passed in 2.19s.
- Full pytest suite including Phase 0 and Phase 7A frontend tests: 209 passed in 1.98s.
- Ruff check: all checks passed.
- Ruff format check: 25 files already formatted.
- Bare exact commands: could not start because `python` is absent from shell `PATH`.
- Equivalent commands using the repository virtual environment: all passed.

## Pre-Commit Audit

- Confirmed Phase 7B, not all of Phase 7, is the intended scope. Phase 7A was already
  complete and Phase 8 remains unstarted.
- Confirmed `models.py` changes only freeze `SourceSnapshot`, as required by the
  architecture's immutable snapshot rule.
- Confirmed the frontend change only repairs imports required for repository-wide Ruff
  checks; the application body is unchanged.
- Confirmed Ruff did not modify 25 files. Its output means 25 files were already
  formatted, and no unrelated formatting-only working-tree changes existed.
- Added regressions for malformed provider outputs, contradictory typed outcome
  metadata, cross-stance content-hash deduplication, and deterministic retrieval IDs,
  snapshot IDs, and timestamps.

## Unresolved Risks

- Phase 7B defines provider interfaces but intentionally supplies no real vendor
  adapters or live-network tests.
- Cross-stance deduplication requires `retrieve_balanced()`; the standalone stance
  entry points intentionally own isolated per-call deduplication state.
- Search failure before result URLs exist is raised explicitly rather than synthesized
  into URL-bearing `RetrievalRecord` instances.
- The deterministic text normalization is deliberately simple and does not parse HTML;
  vendor adapters are responsible for returning extracted textual content.
- Persistence wiring and provider-backed full orchestration remain later-phase work.

## Next Phase Confirmation

Phase 8 LLM provider and structured prompts was not started.
