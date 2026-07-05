# Phase 06 - Fixture-Only Complete Pipeline

## Purpose

Build a complete deterministic offline pipeline from raw fixture input through final
release or validation block. Phase 6 proves the local typed flow without real LLMs,
search, scraping, provider abstractions, API keys, network access, async code, or
external services.

## Files Changed

- `orchestrator.py`
- `cli.py`
- `tests/test_phase6.py`
- `tests/fixtures/basic_valid_run/`
- `tests/fixtures/invalid_release_run/`
- `.agent/plans/phase-06-fixture-pipeline.md`
- `.agent/PLANS.md`
- `STATUS.md`
- `HANDOFF.md`

## Implementation Design

- Added `run_fixture_pipeline()` in `orchestrator.py` as the Phase 6 fixture-only
  coordinator.
- Fixture files are JSON or text persistence-boundary artifacts. The orchestrator
  deserializes JSON into the existing strict Pydantic models before passing data between
  stages.
- The raw claim is read from `raw_claim.txt` and must match the typed
  `PlannerOutput.claim_definition.claim_text`.
- Fixture retrievals, snapshots, provisional candidates, Analyst decisions, Reviewer
  decisions, and `SynthesisOutput` are loaded from local files only.
- Snapshot integrity is rechecked with the Phase 3 deterministic hash and word-count
  guard.
- Provisional candidates pass through the Phase 3 deterministic candidate filter before
  any `CandidateQuoteBlock` is created.
- Ledger records are admitted through the Phase 4 `admit_ledger_record()` helper from
  typed candidate, snapshot, Analyst decision, statement draft, and Reviewer decision
  artifacts.
- Phase 6 derives deterministic Ledger claim IDs from the run ID, Reviewer approval ID,
  approved factual statement, and a Phase 6 derivation-version string.
- Fixture `SynthesisOutput` is validated by the Phase 5 final validator. Valid results
  are rendered with `render_brief()`; invalid results are returned as typed blocked
  results with useful validation errors and no rendered hash.
- The CLI command `run-fixture` returns exit code `0` for both released results and
  expected validation blocks. Malformed fixtures, missing files, import failures, and
  internal pipeline errors return nonzero.
- The fixture output directory stores a SQLite database plus deterministic `audit.json`
  and `result.json`. Existing rows and output files are verified against the fixture
  result instead of being overwritten or duplicated.

## Architectural Decisions

- No model or store schema change was required.
- No dependencies were added.
- No provider abstraction, search provider, scraper, LLM provider, network call, API-key
  read, SDK integration, async code, web framework, ORM, or HTTP client was added.
- Phase 6 uses the existing store functions for typed inserts and reads, with
  orchestrator-level idempotency checks around already-existing rows.
- The existing `provisional_extractions` table has no primary key, so the orchestrator
  compares the full existing typed provisional list for the run before inserting to
  prevent rerun duplication.
- Snapshots and Ledger records remain insert-only; reruns verify existing rows rather
  than updating or deleting them.
- The audit trail is persisted as deterministic JSON with `run_id`, stage, status,
  artifact reference, count, hash, and outcome.
- Fixture directories ignore their generated `.phase6_output/` directories so required
  CLI runs do not pollute the tracked working tree.

## Acceptance Criteria

- Valid fixture releases a final brief.
- Valid fixture produces a stable rendered hash.
- Invalid fixture returns a normal blocked result with useful validation errors.
- Every stage passes typed Pydantic model instances internally.
- Every persisted database artifact carries `run_id`.
- The audit trail is inspectable after the run.
- Rerunning the same fixture does not duplicate Ledger records or provisional records.
- Rerunning the same fixture does not silently overwrite changed audit or result output.
- The database can be reopened after a run.
- CLI valid and invalid fixture commands exit `0`.
- Malformed fixtures fail explicitly and nonzero.
- No network, API-key, search, scraper, LLM, provider, or subprocess network behavior is
  used.
- Phase 7 search and scraping provider interfaces were not started.

## Commands Run

```powershell
python cli.py run-fixture tests/fixtures/basic_valid_run
```

Result: failed before project execution with `zsh:1: command not found: python`.

```powershell
python cli.py run-fixture tests/fixtures/invalid_release_run
```

Result: failed before project execution with `zsh:1: command not found: python`.

```powershell
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q
```

Result: failed before project execution with `zsh:1: command not found: python`.

```powershell
python -m ruff check .
python -m ruff format --check .
```

Result: both failed before project execution with `zsh:1: command not found: python`.

The same commands run with the repository virtual environment first on `PATH`:

```powershell
PATH="$PWD/.venv/bin:$PATH" python cli.py run-fixture tests/fixtures/basic_valid_run
```

Result: passed. Released run
`60000000-0000-0000-0000-000000000001` with rendered hash
`cfb4182d7469c05f269150605aa24907fbc850ea7f70e4e86633a9c96f60f1ed`.

```powershell
PATH="$PWD/.venv/bin:$PATH" python cli.py run-fixture tests/fixtures/invalid_release_run
```

Result: passed. Blocked run
`60000000-0000-0000-0000-000000000002` with an `altered_statement` validation error.

```powershell
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase6.py -q
```

Result: passed with 11 passed in 1.63s.

```powershell
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q
```

Result: passed with 182 passed in 3.38s.

```powershell
PATH="$PWD/.venv/bin:$PATH" python -m ruff check .
```

Result: passed, all checks passed.

```powershell
PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .
```

Result: passed, 20 files already formatted.

## Exact Test Results

- Phase 6 focused tests: 11 passed in 1.63s.
- Phase 1 through Phase 6 tests: 182 passed in 3.38s.
- Ruff check: all checks passed.
- Ruff format check: 20 files already formatted.

## Unresolved Risks

- The shell still does not provide a bare `python` executable unless the repository
  `.venv/bin` directory is placed on `PATH`.
- Phase 6 is intentionally fixture-only. It does not execute real retrieval, scraping,
  LLM calls, provider abstraction, or provider-backed orchestration.
- The fixture pipeline proves local deterministic wiring, not semantic quality beyond
  the fixture Analyst and Reviewer artifacts.

## Next Phase Confirmation

Phase 7 search and scraping provider interfaces were not started.
