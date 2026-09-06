# Phase 2 — Codebase and Documentation Cleanup

Status: active; authorized 2026-09-06. Work is on `codex/phase-2-cleanup`,
from clean Phase 1 HEAD `6499f1d`. Phase 3 frontend redesign is not authorized.

## Prerequisites and baseline

Read AGENTS, nested web instructions, architecture, conventions, decisions, full
status/handoff and plan index, desktop plan/README and current v2 Phase 14 plan.
Phase 1 implementation exists; macOS artifacts passed native-vault, acquisition,
frozen-backend and window smokes. Windows CI previously failed on path fixtures and
line endings; both corrections are committed, but Windows packaging/install proof
remains open. Signing, minimum-OS and clean-machine release gates remain open.
These are retained verification limitations, not proof of functional completion.
The user's explicit Phase 2 authorization supersedes older phase/branch restrictions.

Baseline: `6499f1d`, 909 pytest passed, 2 existing opt-in skips, one existing
Starlette/httpx warning; Ruff lint and all 128 formatting checks passed; diff check
passed. Use `.venv/bin/python -m pytest` and `-m ruff`: installed script shebangs
still point at the previous checkout location. No dependency change is needed.
Frontend lint/types and the existing macOS frozen-runtime/native-vault/window baseline
checks passed. See `docs/verification/phase-2.md` for the durable verification record.

## Bounded implementation plan

1. Record baseline model JSON schemas and SQLite schema/migration rows to compare
   after moves. Preserve every validator, field, SQL statement and migration order.
2. Separate common/evidence/run contracts from v2 research-strategy contracts and
   v2 admission/result contracts. Keep `models.py` as explicit compatibility exports.
3. Move fixture execution out of `orchestrator.py`; retain historical provider
   execution and imports. Shared deterministic persistence helpers get one owner.
   Fresh execution remains `v2_orchestrator.py`, not the historical coordinator.
4. Extract schema initialization/migrations from `store.py`; preserve validated
   readers and every existing public entry point. No database semantic change.
5. Separate live request/view contracts and persisted progress projections from the
   controller's configuration, worker registry, locking and cancellation ownership.
   Inspect shared CLI/application identity and desktop boundaries; avoid UI refactoring.
6. Replace current docs with concise architecture, invariants, operating guide,
   phase index and handoff. Preserve exact pre-cleanup documents in a linked archive;
   keep completed plans at their existing stable paths, indexed as history. Prompts
   remain executable inputs and are not edited or archived.
7. Run complete Python/Ruff/diff checks, frontend lint/type/build, and desktop build,
   frozen-runtime/window/installer checks. Exercise both native target platforms when
   available; never infer Windows success from a macOS build or workflow definition.

## Documentation replacement authority

The existing convention requiring all schemas in `store.py:init_db()` and all
models in `models.py` is replaced for this phase by coherent implementation modules
behind those preserved public imports. This changes source organization only.
Historical architecture/convention/decision/status/handoff/index text is retained
verbatim in `docs/archive/pre-phase-2/`; current replacements state active contracts
and link the originals. No research-policy replacement is authorized.

## Compatibility and completion

New Python modules must stay in the root or existing recursively packaged/hashed
source directories. Verify fingerprint coverage and frozen resource loading. Changed
source/executable identity intentionally requires a new run; history/export stays
read-only and historical rows remain immutable. Do not weaken exact resume checks.
No new dependency, infrastructure, policy, prompt, scoring, model route, research
round, UI workflow or schema migration is authorized. No unused-code deletion
without call/import evidence. Stop at Phase 2; document unresolved target checks.

## Implementation record

Steps 1–6 are implemented. Contract implementations now live in `model_contracts`,
`model_research`, and `model_evidence`, with stable `models` exports. `fixture_pipeline`
owns frozen fixtures and `pipeline_artifacts` owns shared persistence comparisons.
`store_schema` owns the unchanged SQL and migrations. `frontend/live_contracts`,
`live_progress`, and `live_history` separate typed views/read projections from the
controller. `application_runtime` owns shared identity/exit codes. Existing platform
modules already provide coherent native boundaries and were retained.

Only unused imports were removed; no historical execution, reader, export, or fixture
contract was deleted. No dependencies or UI components changed. Original docs were
archived byte-for-byte; `docs/archive/README.md` explains each exact replacement.
All model schemas/class/function ASTs and initialized SQL/migration rows match baseline.
Step 7 is in progress; final results belong in `docs/verification/phase-2.md`.
