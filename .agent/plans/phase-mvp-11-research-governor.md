# MVP-11 — Adaptive Research Expansion & Cost Control

## Authority and boundary

The user explicitly authorized MVP-11 on 2026-08-11 after requiring verification of
the completed MVP-10 Evidence Portfolio & Trail baseline. MVP-11 replaces MVP-10's
single optional targeted expansion with a deterministic Research Governor that may run
rounds one, two, and (only when authorized after completed Round 2) three. It does not
alter MVP-9 exact quote assembly, Reviewer/Ledger admission, final validation, secret
handling, or cumulative provider budgets. No live provider calls or dependencies change.

## Non-negotiable invariant

Every accepted research round number is an integer in `1..3`. No configuration,
planner output, retry, recovery, cancellation, or resume path may create a fourth
research round. Round 3 always transitions to a permitted terminal outcome.

## Design

- Add strict Pydantic Governor policy, productivity, budget-reservation, decision, and
  terminal-result artifacts. The post-Round-2 authorization is deterministic application
  logic with a versioned reason code, timestamp, and plain-language explanation.
- Define documented deterministic policies: duplicate-heavy is a Round-2 duplicate rate
  of at least 70%; recent unproductive research is three consecutive sources without
  Reviewer-approved independent evidence; meaningful angles are normalized new query
  text; a Round-3 reserve covers its complete planned retrieval and model workload.
- Process all planned Round-2/3 work unless cancellation, hard ceilings, or unavoidable
  terminal provider/infrastructure failure stops it. Completeness and saturation never
  short-circuit an already-started round.
- Deduplicate before acquisition/extraction against all prior and current-round source
  families. Persist every duplicate as append-only trail evidence linked to its original
  family while excluding it from paid/provider work and portfolio counts.
- Add the smallest transactional idempotent migration for append-only research-round and
  Governor-decision records, with database enforcement of round values `1..3`. Inspection
  remains read-only; historical MVP-9/MVP-10 databases remain reconstructable.
- Resume unfinished persisted rounds only. Terminal runs and runs completing Round 3
  cannot start new research. A new MVP-11 policy/contract identity requires a new Run ID.
- Extend the Evidence Browser with a compact Governor summary: rounds/max, portfolio,
  Round-2 duplicate rate, productivity, remaining angles and accounted budget,
  authorization, and reason.

## Required regression proof

Add offline unit, parameterized, persistence, resume, orchestration, and browser tests
for all eighteen authorization scenarios, including all terminal outcomes, cumulative
budgets, historical inspection, secret safety, unchanged quote/final safeguards, and
the `1..3` research-round property.

## Completion checks

Run complete `pytest`, `ruff check .`, `ruff format --check .`, the integrity evaluation
suite, `git diff --check`, and inspect the final diff. Update architecture, conventions,
decisions, status, and handoff with exact policies, migration compatibility, verification,
and the next phase boundary.
