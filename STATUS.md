# Status

## 2026-07-04 - Post-Phase-5 Documentation State Audit

Status: Complete.

Completed:

- Audited source-of-truth documentation, phase plans, `agents/`, and `tests/` against the
  current Phase 5 implementation.
- Updated `README.md` and `AGENTS.md` so they no longer describe Phase 3 as the latest
  completed phase or Phase 4 as unstarted.
- Added missing durable Phase 4 and Phase 5 decisions to `DECISIONS.md`.
- Added a current Phase 5 project-state summary to `.agent/PLANS.md`, including active
  deterministic modules, remaining placeholder agent files, current tests, and the Phase 6
  boundary.
- Clarified that `.agent/plans/` is canonical and `.agents/PLANS/` is only a compatibility
  mirror; the mirror was kept and its stale absolute Windows path was replaced with the
  canonical relative path.
- Updated older phase-plan wording where it could mislead future readers about the
  current mirror state or Phase 5 completion.
- Left dated historical status and handoff entries as point-in-time records instead of
  rewriting them wholesale.
- No implementation behavior, tests, dependencies, or Phase 6 behavior was changed.

Verification:

- Exact `python -m pytest`: failed because this shell does not have `python` on `PATH`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 173 passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 17 files
  already formatted.

Known limitations:

- Plain `python` remains unavailable unless the repository `.venv/bin` directory is placed
  on `PATH`.
- Phase 6 fixture-only complete pipeline has not started.
- The repo still has no orchestration, CLI, live retrieval, scraping, LLM/API calls,
  provider integrations, SDK integrations, web frameworks, ORMs, or HTTP clients.

Next exact task:

- Phase 6 fixture-only complete pipeline, only after explicit user direction.

## 2026-07-04 - Phase 5 Verification Pass

Status: Complete.

Completed:

- Inspected the Phase 5 implementation and confirmed the Phase 5 commit changed only
  `agents/synthesizer.py`, `agents/renderer.py`, `tests/test_phase5.py`,
  `tests/fixtures/phase5_expected_valid_brief.txt`,
  `.agent/plans/phase-05-release-gate.md`, `STATUS.md`, and `HANDOFF.md`.
- Confirmed final rendering uses fixed approved connective templates, exact Ledger
  factual statements, and Ledger source URLs only after final validation succeeds.
- Confirmed placement, stance, entailment, Reviewer approval ID, Ledger claim ID, and
  exact approved statement matching are enforced by the release validator.
- Added narrow Phase 5 regression coverage for raw dictionary Ledger handoffs and empty
  approved Ledger statements.
- Tightened Phase 5 typed boundaries so the synthesizer rejects raw dictionary Ledger
  records explicitly and the release validator revalidates LedgerRecord shape before
  trusting approved statement fields.
- No provider abstraction, real LLM/API call, retrieval, scraping, orchestration,
  fixture pipeline, dependency, or Phase 6 behavior was added.

Verification:

- Initial exact `python -m pytest` failed because this shell did not have `python` on
  `PATH`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase5.py -q`: passed with
  24 passed in 0.10s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 173 passed in 0.74s.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 17 files
  already formatted.

Known risks:

- The plain `python` command is still unavailable unless the local `.venv/bin` directory
  is placed on `PATH`.
- Template compatibility remains deterministic configuration, not semantic review.
- Phase 6 fixture-only complete pipeline was not started.

Next exact task:

- Phase 6 fixture-only complete pipeline, only after explicit user direction.

## 2026-07-03 - Phase 5 Synthesizer Schema, Renderer, and Release Validator

Status: Complete.

Completed:

- Added deterministic `SynthesisOutput` construction in `agents/synthesizer.py` from
  typed `LedgerRecord` instances.
- Added a fixed approved non-factual connective template registry in
  `agents/renderer.py`.
- Added deterministic final validation that revalidates typed synthesis shape, rejects
  hidden renderable fields, compares every item against the Ledger, enforces section
  compatibility, enforces template compatibility, enforces one final use per Ledger
  claim, and returns no hash for invalid releases.
- Added deterministic rendering that uses only title/framing fields, approved template
  text, exact Ledger factual statements, and Ledger source URLs.
- Added SHA-256 hashing of the final rendered brief only when validation succeeds.
- Added adversarial Phase 5 tests for changed words, punctuation, capitalization, wrong
  IDs, wrong statements, Reviewer approval drift, placement drift, stance drift,
  qualified evidence promotion, side-crossing sections, unknown templates, hidden prose,
  free-form factual transitions, missing Partial/Weak warnings, Ledger overuse,
  non-Ledger statements, valid stable hashing, and invalid no-hash results.
- Added the canonical Phase 5 plan at
  `.agent/plans/phase-05-release-gate.md`.

Verification:

- `python -m pytest tests/test_phase5.py -q`: first run failed only on the intentional
  hash placeholder; final run passed with 21 passed in 0.12s.
- `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py -q`:
  passed with 168 passed in 0.73s.
- `python -m ruff check .`: passed, all checks passed.
- `python -m ruff format --check .`: passed, 17 files already formatted.

Known risks:

- Template compatibility is deterministic configuration, not semantic review.
- The renderer includes Ledger `source_url` citations mechanically; no citation
  formatting beyond deterministic URL inclusion was added.
- The synthesizer helper remains deterministic and fixture-oriented. No LLM calls,
  provider integrations, retrieval, scraping, orchestration, CLI, async code, or
  external dependencies were added.

Next exact task:

- Phase 6 fixture-only complete pipeline.
- Phase 6 was not started.

## 2026-07-03 - Phase 4 Analyst Rules, Reviewer Rules, and Ledger Admission

Status: Complete.

Completed:

- Added deterministic Analyst score interpretation in `agents/analyst.py` with an
  explicit 25-row Evidence Quality and Claim Fit score-pair table.
- Added typed Analyst helpers for score decisions, Ledger-bound statement drafts, and
  Ledger admission.
- Added deterministic Reviewer input and review-result helpers in `agents/reviewer.py`.
- Enforced one-revision maximum, Reviewer approval/rejection handling, required
  `reviewer_approval_id`, exact Reviewer-approved statement matching, and rejection of
  altered statements after approval.
- Reused Phase 3 snapshot and quote verification before Ledger admission, including
  hash recomputation and exact quote-offset rechecks.
- Enforced placement immutability, Claim Fit 3 qualification requirements,
  `qualified_only` requirements, and Partial/Weak entailment qualification requirements.
- Allowed multiple Ledger records from one quote block only when each statement is
  separately drafted and separately reviewed.
- Added adversarial Phase 4 tests covering all required score pairs and Ledger
  admission guard failures.
- Added the canonical Phase 4 plan at
  `.agent/plans/phase-04-ledger-admission.md`.

Verification:

- `python -m pytest tests/test_phase4.py -q`: failed because `python` is not available
  on PATH in this shell.
- `python3 -m pytest tests/test_phase4.py -q`: failed because the system Python did not
  have `pytest` installed.
- `.venv/bin/python -m pip install -e '.[dev]'`: first failed under the sandbox due to
  blocked package-index DNS; after approval it reached the package index but failed
  because editable package discovery is not configured for the current flat layout.
- `.venv/bin/python -m pip install 'pydantic>=2.0,<3.0' 'python-dotenv>=1.0,<2.0' 'pytest>=8.0,<9.0' 'ruff>=0.8,<1.0'`:
  passed, installing only dependencies already declared in `pyproject.toml`.
- `.venv/bin/python -m pytest tests/test_phase4.py -q`: 43 passed in 0.20s.
- `.venv/bin/python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q`:
  147 passed in 0.87s before documentation updates and 147 passed in 0.91s after
  documentation updates.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m ruff format --check .`: passed.
- Exact required command
  `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q`:
  initially failed with `zsh:1: command not found: python`; after the session-local
  `python` launcher was restored, passed with 147 passed in 0.82s, then 147 passed in
  0.74s after documentation updates.
- Exact required command `python -m ruff check .`: initially failed with
  `zsh:1: command not found: python`; after the launcher was restored, passed.
- Exact required command `python -m ruff format --check .`: initially failed with
  `zsh:1: command not found: python`; after the launcher was restored, passed.

Known risks:

- Qualification detection is deterministic and marker-based; it is not semantic LLM
  review.
- Reviewer approval is fixture-driven in Phase 4 and does not call an LLM.
- The exact requested `python -m ...` verification commands now pass through a
  session-local temporary launcher. If Codex creates a new temporary PATH directory
  later, that launcher may need to be restored.
- Editable installation remains blocked by missing package discovery configuration, but
  no Phase 4 packaging change was required.

Next exact task:

- Phase 5 Synthesizer schema, renderer, and release validator.
- Phase 5 was not started.

## 2026-06-27 - Documentation Consistency Pass After Phase 3

Status: Complete.

Current state:

- Phase 0 is complete.
- Phase 1 is complete.
- Phase 2 is complete.
- Post-Phase-2 hardening is complete.
- Phase 3 is complete.
- Full Phase 0-10 roadmap alignment is complete.
- Tests through Phase 3 pass.
- At that time, Phase 4 had not started.

Documentation updates in this pass:

- Updating stale project-state references in `AGENTS.md`, `DECISIONS.md`, `STATUS.md`, `HANDOFF.md`, `README.md`, and `.agent/plans/phase-02-store.md`.
- Leaving code, tests, dependencies, provider files, orchestrator files, and future agent implementations unchanged.

Verification:

- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: failed because it would reformat existing code/test files outside this documentation-only pass: `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`.
- `.\.venv\Scripts\python.exe -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q`: 104 passed, one local `.pytest_cache` permission warning.

Verification note:

- No code files were changed to satisfy the format check because this pass is documentation-only.

Known risks:

- Sentence-boundary detection remains deterministic and intentionally simple for the MVP.
- The local `.pytest_cache` directory may emit a permission warning during pytest or Git scans.

Next exact task:

- Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.

## 2026-06-27 - Documentation Roadmap Alignment

Status: Complete.

Completed:

- Updated `.agent/PLANS.md` with the full Phase 0-10 roadmap.
- Added a short phase-sequencing cross-reference note to `ARCHITECTURE.md`.
- Added a short phase-gated development note to `CONVENTIONS.md`.
- Confirmed at that time that Phase 3 was complete and Phase 4 had not started.

Verification:

- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: failed because it would reformat existing code files outside this documentation-only pass: `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`.

Notes:

- This was a documentation-only roadmap alignment pass.
- No code files were changed.
- No Phase 4 implementation was started.
- The next exact task remains Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.
- Current roadmap and formatting status is superseded by the documentation consistency pass above and the later Phase 3 verification entry.

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
