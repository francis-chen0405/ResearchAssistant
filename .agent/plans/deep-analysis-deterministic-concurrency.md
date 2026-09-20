# Deep-analysis deterministic concurrency

Status: complete

## Objective

Reduce fresh-v2 deep-analysis wall time by running independent source envelopes in bounded,
priority-ordered waves while preserving the existing budget, routing, evidence, persistence,
restart, and cancellation contracts.

## Scope

- Add source-level concurrency only to `run_v2_deep_analysis_with_backfill()`.
- Use a fixed policy maximum of four workers and dispatch only the largest safe priority prefix
  for each wave.
- Reserve complete source envelopes before dispatch and retain downstream capacity.
- Keep extraction, Analyst, and deterministic admission sequential within a source.
- Drain in-flight work on cancellation and never persist the aggregate completion artifact for a
  cancelled run.
- Replace repeated point reads of physical-call audit artifacts with one typed, bounded bulk read
  that supports current and legacy keys.
- Add deterministic concurrency, restart, cancellation, accounting, ordering, SQLite contention,
  and immutability regressions plus synthetic worker-count timing evidence.
- Version the backfill execution policy so incompatible frozen runs fail explicitly.

## Exclusions

- Acquisition concurrency.
- Provider routing, model, budget, or deadline changes.
- Evidence validation changes.
- Dependencies, paid provider tests, database polling work, legacy-pipeline cleanup, distribution,
  installation, merge, push, or publication.

## Acceptance

1. No more than four source workers overlap, later waves wait, and persisted semantic results use
   priority order regardless of completion order.
2. Every dispatched wave fits conservative call, token, cost, downstream, and per-source limits.
3. Budget exhaustion and cancellation launch no later wave; cancellation drains in-flight work and
   preserves conservative audit exposure without an aggregate completion artifact.
4. Restart reuses source-scoped artifacts without duplicate provider calls.
5. Physical-call sequences stay unique and dense, and bulk reconciliation preserves current and
   legacy semantics including unknown usage.
6. Focused regressions, full `pytest`, Ruff checks, `git diff --check`, frozen offline evaluation,
   and relevant desktop/native smoke checks pass.
7. Authority documents record implementation, evidence, synthetic timing, and the remaining need
   for separately authorized paid live validation.

## Work log

- 2026-09-18: plan opened from commit `485d652`; authority documents read; direct source review
  confirmed the serial source loop and repeated physical-audit point reads.
- 2026-09-18: implemented four-worker maximum priority waves, restart-aware residual source
  envelopes, distinct cancellation propagation, one-query typed physical-audit loading and the
  `v2-waves4` frozen policy identity. No acquisition, routing, budget, deadline, schema,
  dependency or evidence-policy change was made.
- 2026-09-18: deterministic eight-source delay measurement recorded 0.4286s serial, 0.2221s
  with two workers and 0.1057s with four workers. These synthetic results do not predict a
  three-minute or other live runtime.
- 2026-09-18: verification passed: 1,007 tests plus two existing skips, repository Ruff lint and
  format, `git diff --check`, the 38-case frozen offline evaluation, rebuilt arm64 frozen backend
  and isolated native smoke. The first sandboxed build/smoke attempts could not access the
  existing PyInstaller cache/macOS Keychain; the required isolated reruns passed with native
  access. No paid provider call, installer build, installation, push, merge or publication was
  performed. Live effectiveness remains unverified and requires separate authorization.
