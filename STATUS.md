# Status

## 2026-06-27 - Documentation Roadmap Alignment

Status: Complete.

Completed:

- Updated `.agent/PLANS.md` with the full Phase 0-10 roadmap.
- Added a short phase-sequencing cross-reference note to `ARCHITECTURE.md`.
- Added a short phase-gated development note to `CONVENTIONS.md`.
- Confirmed Phase 3 is complete and Phase 4 has not started.

Verification:

- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: failed because it would reformat existing code files outside this documentation-only pass: `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`.

Notes:

- This was a documentation-only roadmap alignment pass.
- No code files were changed.
- No Phase 4 implementation was started.
- The next exact task remains Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.

## 2026-06-27 - Phase 3 Snapshot and Quotation Integrity

Status: Complete.

Completed:

- Added deterministic helpers for SHA-256 hashing, word counting, and UUID5 quote-block ID derivation.
- Added shared researcher post-extraction filtering in `agents/researcher.py`.
- Added strict typed Phase 3 helper artifacts for parsed quote blocks, quote metrics, and filter results.
- Implemented snapshot integrity checks that recompute `snapshot_sha256` and `word_count` from `normalized_text`.
- Implemented deterministic parsing and validation for bracketed quote blocks, segment membership, segment offsets, immediate bracket context, start/end/truncated boundary markers, quote length thresholds, statistical markers, and claim-keyword relevance.
- Ensured rejected provisional candidates return typed rejection results with no `CandidateQuoteBlock` and no `quote_block_id`.
- Added a deterministic candidate-vs-snapshot re-check function for future Analyst code without implementing Analyst scoring or Ledger behavior.
- Added adversarial Phase 3 tests for malformed quote blocks, missing or out-of-order segments, wrong bracket context, hash and word-count mismatches, boundary marker misuse, quote length thresholds, statistical marker rules, missing claim keywords, repeated segment text, ellipsis word counting, deterministic IDs, and tampered offsets.
- During final self-review, tightened statistical marker detection so incidental substrings such as `rate` inside `corporate` cannot unlock the 50-word statistical threshold, and added a metadata rejection guard before candidate ID assignment.
- Added the canonical Phase 3 plan at `.agent/plans/phase-03-snapshot-integrity.md` and linked it from `.agent/PLANS.md`.

Verification:

- `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q` from the activated virtual environment: 104 passed, one local `.pytest_cache` permission warning remains.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: passed.

Notes:

- PowerShell blocked activation of `.venv\Scripts\Activate.ps1`, and `python` was not available on PATH, so verification used the virtual environment's Python executable directly without setting `PYTHONPATH`.
- Phase 1 models, Phase 2 store code, and the SQLite schema were not changed.

Scope review:

- No retrieval, scraping, LLM calls, SDK integrations, Analyst scoring, Reviewer logic, Ledger admission, synthesis, rendering, final validation, orchestration, web frameworks, ORMs, HTTP clients, or Phase 4 work was implemented.

Safe to continue:

- Yes, after explicit user direction for Phase 4.

## 2026-06-27 - Post-Phase-2 Hardening

Status: Complete.

Completed:

- Strengthened `AGENTS.md` with explicit safety rules for destructive Git commands, phase boundaries, protected documentation content, regression tests, strict internal Pydantic artifacts, immutable release-relevant artifacts, and unchanged test expectations.
- Confirmed internal Pydantic artifacts inherit the shared `StrictModel` base with `model_config = ConfigDict(extra="forbid")`.
- Added representative extra-field rejection tests for Ledger, synthesis, validation, candidate quote, source snapshot, and model invocation artifacts.
- Added a SQLite `schema_migrations` table initialized by `init_db()` with the Phase 2 initial schema record.
- Added Phase 2 coverage proving the schema migration table and initial migration record exist after initialization.
- Reviewed the Phase 1 and Phase 2 implementation for later-phase scope creep.
- Updated the Phase 2 plan with a post-phase hardening note.

Verification:

- `pytest tests/test_phase1.py tests/test_phase2.py -q`: 81 passed, one local `.pytest_cache` permission warning remains.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Tracked issues:

- Snapshot `snapshot_sha256` and `word_count` are not recomputed from `normalized_text` at model construction. This remains deferred until Phase 3 defines snapshot and quotation integrity behavior precisely.
- The local `.pytest_cache` directory may still produce a permission warning during pytest.

Scope review:

- No retrieval, scraper, LLM provider, orchestration, renderer, or Phase 3 snapshot-integrity implementation was found.
- Phase 3 has not started.

Safe to continue:

- Yes. The next exact task is Phase 3 snapshot and quotation integrity, only after explicit user direction.

## 2026-06-26 - Phase 2 Hardening

Status: Complete.

Completed:

- Resolved the architecture inconsistency around Claim Fit 2: Claim Fit 2 items may be retained as borderline analyst context, but they cannot enter the final Ledger unless rescored to Claim Fit 3 or higher.
- Documented and implemented two-axis Ledger eligibility: `evidence_quality >= 2`, `claim_fit >= 3`, and `total_score >= 5`, with no compensation for a failing axis.
- Added derived `ledger_score` values: 3 for total scores 5-6, 4 for total scores 7-8, and 5 for total scores 9-10.
- Enforced deterministic score-to-placement validation in `ScoreDecision` and `LedgerRecord`.
- Strengthened `PlannerOutput` validation to require exactly six queries, matching child `run_id` values, no duplicate or extra stance/round pairs, and all standard exclusion parameters.
- Strengthened `StatementReviewResult` so rejected reviews cannot carry approval fields.
- Strengthened `ValidationResult` so invalid validation results cannot carry `rendered_brief_hash`.
- Added SQLite foreign keys for clear parent-child artifact relationships from planner queries through synthesis items.
- Added `read_statement_draft()` for typed statement draft round trips.
- Updated README and Phase 2 plan notes; fixed the `HANDbOFF.md` typo in the Phase 0 plan.
- Added type annotations to Phase 2 test helpers.

Tests added or updated:

- Added scoring example coverage for eligible and ineligible two-axis combinations.
- Added tests for inconsistent placement and derived Ledger score rejection.
- Added planner validation tests for extra queries, child `run_id` mismatches, and missing exclusion parameters.
- Added review and validation result shape tests.
- Added statement draft round-trip coverage.
- Added SQLite orphan-artifact rejection tests for retrieval attempts, snapshots, candidates, analyst decisions, Ledger records, and synthesis items.
- Updated Phase 2 fixtures to create realistic parent artifact chains before inserting child records.

Verification:

- `pytest`: 73 passed; one local `.pytest_cache` permission warning remains.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Tracked issues:

- Snapshot `snapshot_sha256` and `word_count` are not recomputed from `normalized_text` at model construction. This should be implemented in the snapshot creation or post-extraction validation phase once normalization and hashing behavior are precisely defined in code.
- The local `.pytest_cache` directory still produces a permission warning during pytest.

Safe to continue:

- Yes. The project is safe to continue to Phase 3 after explicit user direction. No Phase 3 implementation has begun.

## 2026-06-26 - Phase 2 Store

Status: Complete.

Completed:

- Implemented the SQLite persistence layer in `store.py` with `init_db()` containing all schema definitions.
- Created append-only storage for runs, planner outputs, planner queries, retrieval attempts, snapshots, provisional extractions, candidates, analyst decisions, statement review attempts, ledger records, synthesis attempts, validation runs, and model invocations.
- Enabled SQLite foreign keys on every connection via `PRAGMA foreign_keys = ON`.
- All functions accept explicit `db_path` parameters; no global connections are used.
- Read functions return Pydantic models; write functions accept Pydantic models.
- Snapshots and Ledger records are INSERT-ONLY with no update or delete functions.
- Multi-write operations use explicit transactions with rollback on failure.
- Timestamps are stored as UTC ISO-8601 strings and reconstructed as timezone-aware datetimes.
- `evidence_quality` and `claim_fit` remain separate columns; no composite score column.
- Fixed `_validate_aware_datetime` in `models.py` to handle `None` for optional datetime fields.
- Added Phase 2 tests covering database initialization, foreign-key enforcement, insert and read round trips, database close and reopen, immutable snapshot behavior, immutable Ledger behavior, transaction rollback, invalid foreign keys, typed reconstruction from stored rows, and duplicate identifier rejection.
- Added the canonical Phase 2 plan at `.agent/plans/phase-02-store.md` and linked it from `.agent/PLANS.md`.

Not completed:

- No Phase 3 implementation has begun.
- No web retrieval, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients were implemented.

Verification:

- `pytest tests/test_phase2.py`: 36 passed.
- `pytest tests/`: 54 passed (Phase 0: 2, Phase 1: 16, Phase 2: 36).
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Notes:

- Verification used the local `.venv` created in Phase 1.

## 2026-06-26 - Phase 1 Models

Status: Complete.

Completed:

- Read all required Phase 1 context files before editing: `AGENTS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `DECISIONS.md`, `STATUS.md`, `HANDOFF.md`, `.agent/PLANS.md`, and `.agent/plans/phase-00-foundation.md`.
- Implemented Pydantic v2 handoff contracts in `models.py` for planner, retrieval, snapshot, candidate, scoring, reviewer, Ledger, synthesis, validation, run manifest, and model invocation artifacts.
- Added enums for run status, stage, stance, placement, entailment, retrieval status, reviewer failure codes, synthesis section types, and validator error codes.
- Enforced timezone-aware datetimes, UUID identifiers, score ranges, reviewer approval requirements, non-empty approved factual statements, ordered non-overlapping segment offsets, source/snapshot provenance, and synthesis section stance compatibility.
- Added the canonical Phase 1 plan at `.agent/plans/phase-01-models.md` and linked it from `.agent/PLANS.md`.
- Added Phase 1 tests covering valid construction and invalid score ranges, reviewer approval, placement, entailment, offsets, naive datetimes, empty approved statements, section types, and validation errors.

Not completed:

- No Phase 2 implementation has begun.
- No database operations, web retrieval, scraping, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients were implemented.

Verification:

- `pytest tests/test_phase1.py`: 16 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Notes:

- The direct `pytest` and `python` commands were not available on PATH in this shell, so verification used a local `.venv` created with the dependencies already declared in `pyproject.toml`.

## 2026-06-26 - Phase 0 Foundation

Status: Complete.

Completed:

- Read `ARCHITECTURE.md` and `CONVENTIONS.md` completely before editing.
- Inspected the documents for Phase 0 consistency gaps.
- Updated architecture rules for typed `SynthesisOutput`, `reviewer_approval_id` propagation, stance propagation, provenance, truncated snapshot markers, sync researcher concurrency, and post-validation ID assignment.
- Updated conventions for the requested scaffold, typed handoffs, dependency boundaries, SQLite concurrency limits, provenance fields, and phase completion checks.
- Added assistant instructions, decision log, status log, handoff log, README, pyproject configuration, canonical plan index, canonical Phase 0 plan, and compatibility plan pointer.
- Added placeholder files so empty scaffold directories can be tracked.
- Added a Phase 0 scaffold/configuration test.

Not completed:

- No Phase 1 implementation has begun.

Verification:

- `pyproject.toml` parsed successfully with Python.
- `pytest`: 2 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
