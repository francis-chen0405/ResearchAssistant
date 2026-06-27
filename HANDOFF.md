# Handoff

## 2026-06-26 - Phase 2 Hardening

Work completed:

- Performed a narrow Phase 2 hardening and cleanup pass without beginning Phase 3.
- Updated `ARCHITECTURE.md` and `CONVENTIONS.md` for the two-axis eligibility rule, derived `ledger_score`, and Claim Fit 2 clarification.
- Implemented deterministic scoring helpers in `models.py`.
- Added `ledger_score` to `ScoreDecision` and `LedgerRecord`.
- Enforced score eligibility, derived Ledger score, and placement consistency in `ScoreDecision` and `LedgerRecord`.
- Strengthened `PlannerOutput`, `StatementReviewResult`, and `ValidationResult` validators.
- Added SQLite foreign keys for clear architecture-defined artifact relationships:
  planner queries to retrieval attempts, retrieval attempts to snapshots, snapshots/retrieval attempts to candidates, candidates to analyst decisions and statement drafts/reviews, approved reviews to Ledger records, and Ledger records to synthesis items.
- Added `read_statement_draft()` to the store API.
- Updated tests for all changed validators and store constraints.
- Updated README phase text, Phase 2 plan notes, and the `HANDbOFF.md` typo in the Phase 0 plan.

Verification:

- `pytest`: 73 passed; one local `.pytest_cache` permission warning remains.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Tracked issues:

- Snapshot `snapshot_sha256` and `word_count` validation against `normalized_text` is still deferred. Do this when snapshot normalization and hashing behavior are implemented precisely; do not guess the normalization rules in the model layer.
- The local `.pytest_cache` directory still causes a permission warning.

Important constraints:

- Stop at Phase 2 unless the user explicitly requests Phase 3.
- Do not implement web retrieval, scraping, LLM calls, orchestration, renderer logic, SDK integrations, web frameworks, ORMs, HTTP clients, or real agent behavior yet.
- Agent modules remain placeholders.
- Internal handoffs must continue to use Pydantic model instances, not raw dictionaries.
- Claim Fit 2 records must not enter the final Ledger.

Safe to continue:

- Yes, after explicit user direction for Phase 3.

## 2026-06-26 - Phase 2 Store

Work completed:

- Implemented the SQLite persistence layer in `store.py` with `init_db()` containing all schema definitions for 19 tables.
- Created append-only storage for runs, planner outputs, planner queries, retrieval attempts, snapshots, provisional extractions, candidates, analyst decisions, statement review attempts, ledger records, synthesis attempts, validation runs, and model invocations.
- All functions accept explicit `db_path` parameters; no global connections.
- Read functions return Pydantic models; write functions accept Pydantic models.
- Snapshots and Ledger records are INSERT-ONLY with no update or delete functions.
- Multi-write operations use explicit transactions with rollback on failure.
- Fixed `_validate_aware_datetime` in `models.py` to handle `None` for optional datetime fields.
- Added `tests/test_phase2.py` with 36 tests covering all required scenarios.
- Added `.agent/plans/phase-02-store.md` and updated `.agent/PLANS.md`.
- Updated `STATUS.md` for Phase 2.

Important constraints:

- Stop at Phase 2 unless the user explicitly requests Phase 3.
- Do not implement web retrieval, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients yet.
- Continue passing Pydantic model instances between internal stages; do not pass raw dictionaries except at persistence, API, logging, or export boundaries.
- Preserve the separate `evidence_quality` and `claim_fit` fields; do not add any composite evidence score.
- Concurrent researcher workers must each open their own connections; this is enforced by design but not yet tested under threading.

Verification:

- `pytest tests/test_phase2.py`: 36 passed.
- `pytest tests/`: 54 passed (Phase 0: 2, Phase 1: 16, Phase 2: 36).
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Open issue:

- Verification used the local `.venv` created in Phase 1.

Next expected phase:

- Phase 3 should begin only after explicit user direction and should implement retrieval logging and web search integration.

## 2026-06-26 - Phase 1 Models

Work completed:

- Implemented the Phase 1 Pydantic v2 model layer in `models.py`.
- Added strict construction-time validation for Phase 1 contract requirements, including score bounds, required reviewer approval for approved Ledger records, timezone-aware timestamps, source/snapshot provenance, ordered non-overlapping offsets, exact Ledger statement fields, and synthesis section stance compatibility.
- Added `tests/test_phase1.py` with valid and invalid model construction coverage.
- Added `.agent/plans/phase-01-models.md` and updated `.agent/PLANS.md`.
- Updated `STATUS.md` for Phase 1.

Important constraints:

- Stop at Phase 1 unless the user explicitly requests Phase 2.
- Do not implement database operations, web retrieval, scraping, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients yet.
- Continue passing Pydantic model instances between internal stages; do not pass raw dictionaries except at persistence, API, logging, or export boundaries.
- Preserve the separate `evidence_quality` and `claim_fit` fields; do not add any composite evidence score.

Verification:

- `pytest tests/test_phase1.py`: 16 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Open issue:

- The direct `pytest`, `python`, and `ruff` commands were not available on PATH. I created a local `.venv` with only the already-declared project/dev dependencies to run verification. The sandbox blocked recursive cleanup, so `.venv/` remains as an untracked local tooling directory.

Next expected phase:

- Phase 2 should begin only after explicit user direction and should build on the typed contracts without introducing raw-dictionary handoffs.

## 2026-06-26 - Phase 0 Foundation

Work completed:

- Documented the Phase 0 architecture corrections requested by the user.
- Added the repository scaffold needed for reliable AI-assisted development.
- Configured `pyproject.toml` for Python 3.11+, Pydantic v2, python-dotenv, pytest, and Ruff.
- Added a Phase 0 scaffold/configuration test.
- Verified the phase with `pytest`, `ruff check .`, and `ruff format --check .`.

Important constraints:

- Do not begin Phase 1 without explicit user instruction.
- Do not implement working agents, SQLite behavior, web retrieval, scraping, LLM calls, SDK integrations, ORMs, web frameworks, or HTTP libraries yet.
- Future assistants must read `ARCHITECTURE.md` and `CONVENTIONS.md` completely before editing.
- Internal handoffs must use Pydantic model instances, not raw dictionaries.

Open issue:

- No blocking Phase 0 issue remains. `.agent/plans/phase-00-foundation.md` is the canonical plan; `.agents/PLANS/phase-00-foundation.md` is only a compatibility pointer.

Next expected phase:

- Phase 1 should start only after the user explicitly requests it. It should begin with schemas and artifact-store design as described in `ARCHITECTURE.md`, without weakening the Phase 0 constraints.
