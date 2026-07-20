# Phase Plans

Canonical phase plans live in `.agent/plans/`.

The requested `.agents/PLANS/` path is a compatibility mirror only when writable. It must not become a second source of truth.

## Current Project State After Phase 10

Phases 0 through 10 are complete. Phase MVP-1 Release-Contract Correctness is the active
user-authorized post-MVP hardening phase. Its canonical focused plan is
`.agent/plans/phase-mvp-1-release-contract-correctness.md`.

MVP-1 is limited to application-owned brief framing, application-owned Reviewer
approval IDs, validation-blocked fixture terminal persistence, their compatibility
effects, and regression verification. It must not add live providers, network calls,
dependencies, frontend changes, `.env` loading, a live CLI command, multi-candidate
extraction, cross-stance deduplication, database triggers, or unrelated redesign work.

## Phase 0: Repository Foundation

Purpose: Establish project documentation, repository rules, scaffold, pyproject configuration, assistant instructions, status tracking, handoff tracking, and phase planning.

Main files expected:

- `AGENTS.md`
- `DECISIONS.md`
- `STATUS.md`
- `HANDOFF.md`
- `README.md`
- `pyproject.toml`
- `.gitignore`
- `.env.example`
- `.agent/PLANS.md`
- `.agent/plans/phase-00-foundation.md`
- `agents/`
- `providers/`
- `prompts/`
- `tests/`
- `tests/fixtures/`

Explicitly out of scope:

- Working agents
- Database behavior
- Retrieval
- Scraping
- LLM calls
- Orchestration
- Rendering

Completion signal: Repository scaffold exists, architecture and conventions are internally consistent, project configuration is valid, and the repo can be used as the source of truth for future Codex sessions.

## Phase 1: Pydantic Data Models

Purpose: Define strict typed Pydantic v2 contracts for all internal handoffs and artifacts.

Main files expected:

- `models.py`
- `tests/test_phase1.py`
- `.agent/plans/phase-01-models.md`

Explicitly out of scope:

- SQLite operations
- Web retrieval
- Scraping
- LLM calls
- Orchestration
- Rendering

Completion signal: Model tests pass. Invalid score ranges, invalid offsets, naive datetimes, missing reviewer approval, invalid enum values, malformed validation errors, and unknown fields are rejected. All internal artifacts use typed models rather than arbitrary dictionaries.

## Phase 2: SQLite Artifact Store

Purpose: Implement SQLite persistence for typed artifacts with append-only audit behavior.

Main files expected:

- `store.py`
- `tests/test_phase2.py`
- `.agent/plans/phase-02-store.md`

Explicitly out of scope:

- Retrieval
- Scraping
- LLM calls
- Orchestration
- Rendering
- Snapshot validation algorithms
- Analyst scoring
- Reviewer logic

Completion signal: Database initialization, foreign-key enforcement, typed insert/read round trips, close/reopen behavior, immutability, transaction rollback, invalid foreign keys, duplicate identifier rejection, and schema migration tracking tests pass.

## Phase 3: Snapshot and Quotation Integrity

Purpose: Implement deterministic trusted-snapshot and quote/candidate validation.

Main files expected:

- `utils.py`
- `agents/researcher.py`
- `tests/test_phase3.py`
- `tests/fixtures/`
- `.agent/plans/phase-03-snapshot-integrity.md`

Explicitly out of scope:

- Retrieval execution
- Scraping
- LLM extraction
- Analyst scoring
- Reviewer logic
- Ledger admission
- Rendering
- Orchestration
- Provider integrations

Completion signal: Adversarial quote and snapshot tests pass. Hash mismatches, word-count mismatches, bad offsets, wrong brackets, bad truncation markers, insufficient quote length, missing claim keywords, duplicate candidates, and statistical marker edge cases are rejected. No invalid candidate receives a candidate ID or quote_block_id.

## Phase 4: Analyst Rules, Reviewer Rules, and Ledger Admission

Purpose: Implement deterministic policy around Analyst score interpretation, Statement Reviewer approval/rejection, one-revision maximum, and Ledger admission.

Main files expected:

- `agents/analyst.py`
- `agents/reviewer.py`
- `tests/test_phase4.py`
- `.agent/plans/phase-04-ledger-admission.md`

Explicitly out of scope:

- Real LLM calls
- Retrieval
- Scraping
- Rendering
- Final release validation
- Full orchestration
- Provider integration

Completion signal: All evidence_quality and claim_fit score-pair tests pass. Reviewer approval rules are enforced. Missing reviewer approval, altered statements, unauthorized placement changes, invalid revision counts, rejected evidence, and draft statements are blocked. Only exact Reviewer-approved statements enter the Ledger.

## Phase 5: Synthesizer Schema, Renderer, and Release Validator

Purpose: Implement typed SynthesisOutput validation, approved connective templates, deterministic rendering, and the final release gate.

Main files expected:

- `agents/synthesizer.py`
- `agents/renderer.py`
- `tests/test_phase5.py`
- `.agent/plans/phase-05-release-gate.md`

Explicitly out of scope:

- Real LLM calls
- Retrieval
- Scraping
- Fixture pipeline
- Full orchestration
- Provider integration

Completion signal: Mutation tests block changed words, punctuation, capitalization, wrong IDs, wrong statements, placement drift, stance mismatch, hidden prose, unapproved templates, missing qualification warnings, and excessive Ledger claim reuse. Invalid releases produce no final rendered hash.

## Phase 6: Fixture-Only Complete Pipeline

Purpose: Build a complete end-to-end deterministic pipeline using fixtures only.

Main files expected:

- `orchestrator.py`
- `cli.py`
- `tests/test_phase6.py`
- `tests/fixtures/basic_valid_run/`
- `tests/fixtures/invalid_release_run/`
- `.agent/plans/phase-06-fixture-pipeline.md`

Explicitly out of scope:

- Real search providers
- Real scrapers
- Real LLM providers
- Network calls
- Live API keys
- External provider integration

Completion signal: A valid fixture run releases a final brief with a stable hash. An invalid fixture run is blocked with useful errors. The audit trail is inspectable, all stages pass typed artifacts, reruns do not corrupt state, and no real network/API/LLM calls occur.

## Phase 7A: Extremely Basic Local Frontend

Purpose: Add a minimal local Streamlit frontend around the existing Phase 6 fixture-only
pipeline.

Main files expected:

- `frontend/streamlit_app.py`
- `frontend/README.md`
- `tests/test_phase7_frontend.py`
- `.agent/plans/phase-07a-local-frontend.md`

Explicitly out of scope:

- Core Phase 6 pipeline behavior changes
- Live LLM calls
- Web retrieval or scraping
- React
- FastAPI
- Authentication
- User accounts
- Uploads
- Project dashboards
- Database changes
- Phase 7B or Phase 8 work

Completion signal: Local helper tests prove fixture discovery, valid fixture execution,
invalid fixture execution, and structured display information without browser UI tests.
The frontend launches with `streamlit run frontend/streamlit_app.py`.

## Phase 7B: Search and Scraping Provider Interfaces

Purpose: Implement vendor-isolated search and scraping provider abstractions plus deterministic retrieval behavior using fake providers in tests.

Main files expected:

- `providers/search.py`
- `providers/scraper.py`
- `agents/supportingresearcher.py`
- `agents/opposingresearcher.py`
- `tests/test_phase7.py`
- `.agent/plans/phase-07-retrieval.md`

Explicitly out of scope:

- LLM integration
- Live-network tests by default
- Semantic scoring
- Rendering
- Final orchestration

Completion signal: Fake-provider tests prove exactly 18 intended retrieval attempts, supporting/opposing parity, exclusion parameters on every query, stable ranking records, URL/content deduplication, timeout behavior, failed scrape handling, unsupported content handling, truncation behavior, and snapshot creation before extraction.

## Phase 8: LLM Provider and Structured Prompts

Purpose: Implement a vendor-isolated LLM provider interface and versioned structured prompts.

Main files expected:

- `providers/llm.py`
- `prompts/planner.md`
- `prompts/extractor.md`
- `prompts/analyst.md`
- `prompts/reviewer.md`
- `prompts/synthesizer.md`
- `agents/planner.py`
- `tests/test_phase8.py`
- `.agent/plans/phase-08-llm-integration.md`
- `.env.example` if needed

Explicitly out of scope:

- Full real orchestration
- Live tests by default
- Evaluation corpus
- Provider-backed end-to-end run as the main implementation

Completion signal: Fake LLM tests pass. Invalid model responses are rejected by Pydantic validation. Prompt hashes and model invocation provenance are recorded. Reviewer input excludes forbidden fields. Prompt injection inside source text is labeled untrusted. Optional integration tests are skipped unless explicitly enabled.

## Phase 9: Real Orchestration and Controlled Concurrency

Purpose: Connect provider-backed stages into a complete orchestrator with controlled concurrency, retries, restarts, cancellation, and budgets.

Main files expected:

- `orchestrator.py`
- `cli.py`
- `agents/supportingresearcher.py`
- `agents/opposingresearcher.py`
- Relevant provider/agent modules
- `tests/test_phase9.py`
- `.agent/plans/phase-09-orchestration.md`

Explicitly out of scope:

- Evaluation corpus
- Phase 10 metrics
- Production UI
- Live network tests by default
- Hidden background tasks

Completion signal: Fake-provider orchestration tests pass for successful runs, one-side failure, both-side failure, partial retrieval, extraction failure, Reviewer first failure then approval, Reviewer second failure, validator rejection, restart after failure, duplicate retry, cancellation, database reopening, no shared SQLite connection across workers, no duplicate snapshots, no duplicate Ledger records, and explicit final run status.

## Phase 10: Evaluation and Adversarial Testing

Purpose: Build an evaluation corpus, adversarial cases, metrics, machine-readable output, and human-readable summary.

Main files expected:

- `evaluations/`
- `evaluations/cases/`
- `evaluations/run_evaluations.py`
- `evaluations/README.md`
- `tests/test_phase10.py`
- `.agent/plans/phase-10-evaluation.md`

Explicitly out of scope:

- Validator weakening
- New production UI
- New provider vendors
- Live network dependency for normal evaluations

Completion signal: Evaluations run offline. Required metrics are reported, including citation accuracy, snapshot integrity, bracket accuracy, unsupported-claim rate, validator escape rate, placement consistency, score separation, Reviewer rejection rate, Analyst rejection rate, retrieval parity, mutation attack block rate, and completion time. Remaining MVP risks are documented.
