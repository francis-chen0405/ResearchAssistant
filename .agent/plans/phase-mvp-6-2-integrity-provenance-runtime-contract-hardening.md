# MVP-6.2 — Integrity, Provenance, and Runtime Contract Hardening

## Authority and Phase Boundary

MVP-6 and MVP-6.1 are completed committed prerequisites. MVP-6.2 is the current
authorized phase, but its implementation is divided into separately approved batches.
Authorization of one batch does not authorize another batch or complete MVP-6.2 as a
whole. No phase after MVP-6.2 has started.

Only Batch A is authorized and implemented by the current task. Batch A may correct
phase records, current-stack documentation, CLI launch reporting and its tests, package
description metadata, expected test-skip documentation, and accidental `.coverage`
tracking. It must not change provider behavior, security policy, database schema,
accounting, evidence policy, or model contracts.

## Batch A — Records and Runtime Reporting

Authorized scope:

- record MVP-6 (`37c52a7`, `6e0f434`) and MVP-6.1 (`c10c844`) as completed committed
  work while preserving genuinely historical chronology;
- establish MVP-6.2 as current and state that later phases have not started;
- document the current Exa Search `auto`, pinned loopback Wigolo `0.2.1`, optional
  narrowly gated Firecrawl, and direct Xiaomi `mimo-v2.5-pro` stack;
- retain clearly labeled SearXNG compatibility history for old persisted runs;
- make the CLI disclose secret-free provider roles, configured endpoints, and whether
  Firecrawl fallback is enabled;
- align CLI assertions, normal-suite skip documentation, and package description;
- stop tracking the accidental `.coverage` binary and ignore future `.coverage` files;
- record Batch A in `STATUS.md` and `HANDOFF.md` without marking MVP-6.2 complete.

Batch A does not add dependencies or a database migration and must make no provider
call. The tracked `.coverage` deletion remains recoverable from Git history.

## Pending Separately Approved Batches

The later MVP-6.2 security, database, accounting, evidence-policy, and model-contract
batches remain pending approval and implementation. Their authorization, detailed
acceptance criteria, and completion status must be recorded separately before work
begins. Completion of Batch A is not completion of MVP-6.2.

## Verification Requirements

Before Batch A is considered implemented, run focused CLI tests, the complete `pytest`
suite, all offline evaluations, `ruff check .`, `ruff format --check .`, launcher shell
syntax validation, and `git diff --check`. Inspect the final Git diff for unrelated
changes and contradictions. Confirm no provider call or spending occurred and that no
dependency or database migration was added.
