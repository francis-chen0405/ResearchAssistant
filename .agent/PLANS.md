# Phase Plans

Canonical phase plans live in `.agent/plans/`.

The requested `.agents/PLANS/` path is a compatibility mirror only when writable. It must not become a second source of truth.

## CI Maintenance After MVP-1

The user-authorized CI maintenance plan is
`.agent/plans/ci-daily-expanded-checks.md`. It changes automation and development
tooling only; it does not start another product phase or alter runtime behavior.

## Current Project State: MVP-7

Phases 0 through 10, MVP-1 through MVP-6, and MVP-6.1 are complete committed work.
MVP-6 comprises the live research stabilization in `37c52a7` and the post-audit
integrity/web-interface hardening in `6e0f434`; MVP-6.1 is the committed live-worker test
fix in `c10c844`. MVP-6.2 Batch A completed the documentation/current-stack correction.
MVP-6.3 completes public-acquisition redirect safety and Firecrawl provenance validation.
MVP-6.4 calibrates new provider-backed evidence density to 50 words for quotations with
both a digit and a recognized statistical marker, and 75 words otherwise. Frozen fixture
replay alone retains its labeled historical 50/100 contract. MVP-6.5 adds SQLite
migration 5 for database-enforced `runs.raw_claim` immutability and makes history and
inspection use validated read-only SQLite sessions. MVP-6.6 assigns RUNNING exit code
13, distinguishes exact usage totals from incomplete known subtotals while retaining
conservative reservations for budget enforcement, and freezes/validates canonical
provider-run contracts. MVP-6.7 enforces explicit return annotations and explicit named-
parameter annotations on every repository-owned Python function except conventional
`self`/`cls` receivers. MVP-6.8 installs SQLite migration 6 to reject updates/deletes of
snapshots and Ledger records, and uses canonical decimal text plus strict `Decimal`
accounting for authoritative USD values. MVP-6.9 distinguishes independently verified
origin media type from provider-declared Firecrawl metadata, carries verified preflight
evidence through fallback, persists the provenance in migration 7, repairs the legacy
boundary-smoke example, and makes package wording phase-neutral. The contradiction-audit
remediation sequence and MVP-6.9 integrity work are complete.

New live runs use Exa Search `auto` for metadata-only discovery, pinned loopback Wigolo
`0.2.1` for primary acquisition, optional Firecrawl acquisition fallback under the
narrow fail-closed policy, and direct Xiaomi `mimo-v2.5-pro` for every LLM role. Exact
fingerprints, explicit budgets, restart-safe persistence, stable exit codes, detailed
inspection, cooperative cancellation, persisted history, duplicate-worker prevention,
and application-owned local service lifecycle remain in force. The original Streamlit
frontend remains fixture-only. Native SearXNG paths remain historical compatibility
surfaces for old persisted runs, not the current live-run operating stack.

Canonical current plan:

- `.agent/plans/phase-mvp-7-direct-mimo-consolidation.md`

## MVP-2A: Architecture Gate

Purpose: Select and freeze a concrete live-provider architecture before any live adapter
or dependency is added.

Canonical plan:

- `.agent/plans/phase-mvp-2a-architecture-gate.md`

Completed decisions:

- Primary acquisition stack: pinned local Wigolo `0.2.1` for discovery and controlled
  fetching, with ResearchAssistant-owned normalization and snapshots.
- Primary LLM stack: OpenRouter with `xiaomi/mimo-v2.5-pro` for every role and
  `minimax/minimax-m3` as the only objective-failure fallback.
- Narrow deterministic support for digitally generated PDFs; scanned, encrypted,
  malformed, empty, or unusably extracted PDFs return a typed unsupported result.
- Six searches return five discovery candidates each; each stance worker attempts them
  in rank order until three usable unique snapshots exist per query. Eighteen snapshots
  remain the normal Extractor ceiling; thirty acquisitions are the structural maximum.
- Source snapshots are immutable ResearchAssistant-owned normalized plain text with
  exact character offsets, versioned normalization, and separate original, final, and
  advisory canonical URL provenance.
- Live runs are public/non-sensitive only, use one total retry/fallback budget, and fail
  closed when price or resume compatibility cannot be established.

Explicitly out of scope:

- Provider or process-manager implementation
- Dependency or environment-template changes
- Live calls, secrets, network-dependent tests, or provider CLI commands
- Database/schema migrations
- Changes to existing protocol, routing, orchestration, or normalization code
- MVP-2B or any later phase

Completion signal: The primary and alternative stacks, acquisition contract, PDF policy,
normalization and quotation contract, data handling, retries, budgets, persistence,
restart compatibility, canary evidence, implementation boundary, and approval-required
open items are documented consistently. Existing offline verification remains green.

## MVP Sequence

These canonical plans record the earlier completed MVP sequence. MVP-6.9 is the latest
completed authorized phase; no later phase has started or been authorized.

1. MVP-2B Production Provider Adapters and Boundary Proof:
   `.agent/plans/phase-mvp-2b-production-provider-boundaries.md`
2. MVP-3A Mocked Full-Provider Pipeline Integration:
   `.agent/plans/phase-mvp-3a-mocked-full-provider-pipeline.md`
3. MVP-3B Full Live-Canary Stabilization:
   `.agent/plans/phase-mvp-3b-live-canary-stabilization.md`
4. MVP-4 Usable Live CLI and MVP Release:
   `.agent/plans/phase-mvp-4-live-cli-release.md`
5. MVP-5 Polished Local Live Web Interface:
   `.agent/plans/phase-mvp-5-scheduled-live-validation.md`
6. MVP-6 Live Research Stabilization and Post-Audit Hardening: committed work recorded
   in `STATUS.md`, `HANDOFF.md`, and `DECISIONS.md` under commit evidence `37c52a7` and
   `6e0f434`.
7. MVP-6.1 Live Worker Test Fix: committed work recorded under `c10c844`.
8. MVP-6.2 Integrity, Provenance, and Runtime Contract Hardening:
   `.agent/plans/phase-mvp-6-2-integrity-provenance-runtime-contract-hardening.md`
9. MVP-6.3 Public Acquisition and Provenance Security:
   `.agent/plans/phase-mvp-6-3-public-acquisition-provenance-security.md`
10. MVP-6.4 Evidence Density Threshold Calibration:
    `.agent/plans/phase-mvp-6-4-evidence-density-threshold-calibration.md`
11. MVP-6.5 Immutable Run Authority and Read-Only Inspection:
    `.agent/plans/phase-mvp-6-5-immutable-run-authority-read-only-inspection.md`
12. MVP-6.6 Runtime Status, Budget, and Contract Integrity:
    `.agent/plans/phase-mvp-6-6-runtime-status-budget-contract-integrity.md`
13. MVP-6.7 Repository-Wide Type Contract Enforcement:
    `.agent/plans/phase-mvp-6-7-repository-wide-type-contract-enforcement.md`
14. MVP-6.8 Persistence and Accounting Integrity:
    `.agent/plans/phase-mvp-6-8-persistence-accounting-integrity.md`
15. MVP-6.9 Acquisition and Configuration Integrity:
    `.agent/plans/phase-mvp-6-9-acquisition-configuration-integrity.md`

The canonical MVP-5 plan path is retained for history, but its earlier scheduled-live-
validation placeholder was superseded by the user's 2026-08-01 explicit MVP-5 web-
interface direction. Scheduled automation is not part of MVP-5.

The controlled Wigolo `render_js: "always"` retry is the only approved rendering
exception. “No browser automation” in later prompts means no ResearchAssistant-owned
browser driver, actions, authentication, typing, profiles, or additional automation.

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
