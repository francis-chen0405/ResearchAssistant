# Development conventions

Current implementation scope is [Per-step model choices](.agent/plans/per-step-model-choices.md),
explicitly authorized on 2026-09-23, including the confirmed post-audit fixes recorded in the
current status and handoff. It follows the completed neutral evidence ownership, explicit
pipeline-selection and SQLite status-polling phases and preserves the Mac-first release boundary.
Earlier dated scope statements below remain historical.

Preceding implementation scope is
[deterministic deep-analysis concurrency](.agent/plans/deep-analysis-deterministic-concurrency.md),
authorized on 2026-09-18. Its specific concurrency rules are recorded below.

The user authorized the adaptive-search reliability corrective plan on 2026-09-12.
Its bounded research changes supersede the Phase 3-only scope below for this work.

Release scope is [Mac-first release and cache pricing](.agent/plans/mac-release-cache-pricing.md),
following the completed adaptive correction. Read
[architecture](ARCHITECTURE.md), [status](STATUS.md), [handoff](HANDOFF.md),
[decisions](DECISIONS.md), [plan index](.agent/PLANS.md) and applicable `AGENTS.md`
before editing. The user subsequently authorized the plan's evidence-led planner/Scout
reliability follow-up. Stop at that boundary; do not begin another phase.

## Contracts and code

- Internal handoffs use Pydantic v2 with `ConfigDict(extra="forbid")`, except a
  specifically documented exception. Preserve existing frozen models and immutable
  snapshots, Ledger and final artifacts. JSON is a boundary format, not an agent bus.
- Use explicit annotations on every named Python parameter and return, including
  tests, nested functions, callbacks and variadics. Only `self`/`cls` may be unannotated.
  `tests/test_type_contracts.py` enforces this syntactically.
- Raise clear errors or return typed failure artifacts; never silently return `None`
  on failure. Optional missing artifacts keep their existing documented contracts.
- Pass dependencies explicitly. Research stages remain synchronous; independent workers
  never share a SQLite connection, cursor, transaction or mutable handoff. Existing
  asynchronous HTTP lifecycle handling is not a research-pipeline rewrite.
- Keep coherent domain boundaries. `models.py` is the stable export facade;
  `model_contracts`, `model_research` and `model_evidence` own definitions. Preserve
  field names, schemas, validators, enum values and historical meanings during moves.
- `store.py` owns typed persistence/read-only inspection; `store_schema.py` owns
  initialization/migration SQL and schema checks. All initialization still enters
  through `store.init_db()`. This intentionally replaces the original single-file rule.
- Preserve public imports with explicit exports or small compatibility wrappers.
  Prove code unused across production, fixtures, history/export and tests before removal.
- Avoid unrelated edits, formatting churn, speculative infrastructure and dependencies.
  Flag necessary dependencies first; out-of-phase additions require explicit approval.
  Keep approved versions/locks in the existing project and desktop build manifests.

## Persistence, security and identity

- Snapshot and Ledger rows are insert-only; preserve database immutability and same-run
  provenance triggers. Do not weaken validators or tests to make refactors pass.
- History, inspection and export use validated read-only sessions. They never create or
  migrate a database. Writable run/resume is the intentional migration boundary.
- Costs use finite non-negative `Decimal` and canonical decimal SQLite text. Unknown
  physical-call usage retains reservations; never guess missing precision or refunds.
- Default desktop runtime writes go to `desktop_paths.application_data_dir()`, never the checkout/bundle.
  Use `FileLock` for cross-process exclusion and preserve database lock naming/ownership.
- Use native macOS Keychain or Windows Credential Manager; no plaintext fallback.
  Ordinary preferences use strict `desktop_settings`. Never load `.env` or shell profiles.
  Secrets remain transient in the backend and absent from logs, browser storage and data.
- Keep `prompts/*.md` in place as executable inputs. Documentation cleanup cannot archive
  or semantically edit them. Source moves must remain packaged and fingerprinted.
- Source/executable changes require a fresh run under the unchanged exact compatibility
  gate. They never authorize mutation or reinterpretation of historical records.

## Documentation and verification

`STATUS.md` is the concise current state; `HANDOFF.md` gives the next work boundary.
`.agent/PLANS.md` identifies the current plan state. Completed narratives belong in the linked
archive; existing plan paths remain stable historical references. Explain the exact
replacement before moving architecture, conventions, decisions or phase records.
The `.agents/PLANS` compatibility pointer is not a second authority.

Run `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`,
`git diff --check`, relevant frontend checks, and the established desktop checks before
claiming phase completion. Preserve existing assertions/skips and acceptance criteria.
Report actual platform/artifact results; a workflow definition is not a successful
Windows build or installation. See [build instructions](desktop/README.md).

The full former conventions are preserved in
[the pre-Phase-2 archive](docs/archive/pre-phase-2/CONVENTIONS.md). Current rules here
replace stale no-HTTP/framework, single-file and earlier-phase instructions; approved
runtime behavior and all evidence/release invariants remain unchanged.

## Deep-analysis concurrency conventions (2026-09-18)

- Fresh deep analysis uses fixed, priority-ordered waves of at most four sources. Never
  submit the full survivor queue or let completion timing choose a later source.
- A wave is eligible only when its complete conservative source envelopes and protected
  downstream capacity fit the current global call, token and cost snapshot. The provider
  lock remains the final reservation authority.
- Source workers return strict typed results and never mutate shared aggregate collections.
  Each worker opens persistence operations through existing store functions; connections
  and cursors are never shared.
- Cancellation must remain a distinct exception through generic invocation wrappers.
  Cancel work that has not started, drain running work, persist its audit exposure and do
  not write a terminal aggregate for the cancelled stage.
- Read physical-call audit rows in one bounded query, validate the run-wide dense sequence,
  then filter/group by source. Missing completion usage remains conservatively reserved.
