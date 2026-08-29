# ResearchAssistant v2 — Phase 14: Conditional Round Four and Gap Reconciliation

Status: Complete and verified. Authorized and completed on 2026-08-28; a focused Round-Four
correction was completed the same day.

## Scope

- Add a fresh-v2-only post-Round-3 Luna Gap Analysis using cumulative Round 1–3 strategy
  context and the established bounded retry contract. Its typed input/output carries an exact
  claim-coverage map (relevant dimensions, component, status, and evidence summary), true
  source-family identities, and deterministic per-round/direction representative quotas.
- Add one tightly bounded, Governor-authorized Round 4. It may use no more than two
  provider lanes and two queries per lane per enabled direction, with no more than four
  queries per enabled direction.
- Preserve direction isolation, provider ceilings, duplicate/productivity stopping rules,
  cancellation, terminal-failure handling, and conservative physical-call/token/cost
  accounting.
- Require each Round-4 search direction to resolve a named unsupported claim component with a
  specified evidence kind. A maximum of two provider lanes and four queries per enabled
  direction is enforced deterministically even if the Search Agent proposes more.
- Protect the existing Phase-13 downstream workload. Round 4 may use only a separately
  persisted surplus reservation and cannot displace source selection, extraction, Analyst,
  or deterministic admission capacity.
- Record the pre-Gap conservative envelope and a fresh post-Gap budget snapshot separately;
  only future Search-Agent/Scout work is tested against the latter. Restarted final output is
  validated against the same immutable gap reconciliation supplied to a fresh run.
- Add deterministic post-admission reconciliation from the original post-Round-3 gap set to
  qualifying Round-4 analyzer-admitted evidence. No Gap Analysis model call may occur after
  Round 4.
- Version fresh policy identities, artifact keys, fingerprints, API/UI/trail progress, final
  output disclosure, and tests. Historical Phase-13 and earlier three-round results remain
  immutable and readable under their original contracts.

## Explicitly out of scope

- Round 5, recursive continuation, broad exploratory Round-4 search, a new Reviewer call,
  changed Phase-13 per-source workload, dependency changes, live paid calls, and historical
  artifact reinterpretation or migration.

## Verification

- Offline tests cover claim coverage, representative quotas, three-provider/five-query lane
  pressure, every typed Governor decision, reservations, end-to-end Round-4 execution,
  reconciliation linkage, admission failures, history compatibility, and fingerprint mismatches.
- Verification completed: `pytest` (834 passed, 2 skipped), `ruff check .`,
  `ruff format --check .`, and `git diff --check` all passed.
