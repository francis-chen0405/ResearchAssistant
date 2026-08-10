# MVP-6.8 — Persistence and Accounting Integrity

## Authority and Boundary

MVP-6.7 is the complete prerequisite. The user explicitly authorized MVP-6.8 to make
source snapshots and Ledger records immutable at the SQLite boundary and to remove
binary floating-point from authoritative USD accounting. MVP-6.9 and later work are not
authorized.

No dependency, live provider call, provider spending, commit, push, or pull request is
part of this phase. Immutability is limited to `snapshots` and `ledger_records`; other
artifact tables retain their existing lifecycle.

## SQLite Migration 6

Migration 6 is `immutable snapshots and Ledger with exact decimal model costs`. In one
explicit transaction it:

- adds canonical-text `reserved_cost_usd_exact` and `cost_usd_exact` columns to
  `model_route_attempts` when absent;
- converts recoverable historical `REAL` values through their SQLite/Python float text
  representation without inventing digits that were already lost;
- installs unconditional `BEFORE UPDATE` and `BEFORE DELETE` triggers for `snapshots`
  and `ledger_records` with stable table-specific errors;
- verifies the columns and exact trigger contracts; and
- records schema version 6 only after successful verification.

Repeated initialization verifies and preserves the installed schema. A conflict,
malformed existing exact value, or other failure rolls back migration-6 changes and
leaves version 6 unrecorded. Migration 5 remains solely responsible for
`runs.raw_claim` immutability.

## Exact USD Contract

Authoritative USD values use `Decimal` in strict Pydantic models, reservations,
provider usage, aggregation, resume reconstruction, budget comparisons, inspection,
and live summaries. Storage uses canonical non-exponent decimal text. Canonical zero is
`0`; redundant leading/trailing zeros, signs, exponent notation, negative zero,
negative values, and non-finite values are rejected at the exact-storage boundary.

New writes leave legacy `REAL` cost columns null and write only exact text. Existing
rows remain readable through the migration-populated exact columns. Historical binary
floats can be represented deterministically after migration, but their original source
decimal digits cannot be recovered and are not fabricated.

Exact-limit exposure is allowed. Any positive amount above the ceiling is rejected,
including differences below IEEE-754 precision. Incomplete usage retains its exact
reservation exposure under the MVP-6.6 fail-closed policy.

## Compatibility Identity

Schema version 6 is required for read-only inspection. Writable run/resume paths
intentionally migrate version-5 databases. Provider accounting identity is
`mvp6.8-exact-decimal-reserve-reconcile-v1`, and both provider fingerprint versions are
`mvp6.8-persistence-accounting-integrity-v1`. Pre-MVP-6.8 runs therefore cannot resume
under the new accounting semantics with the same run ID.

## Regression and Verification

Regression tests were added before implementation and demonstrated direct SQL mutation,
precision round-trip, above-ceiling, and exact-sum failures. Coverage includes fresh
creation, version-5 migration, repeated migration, rollback on trigger conflict, normal
fixture insertion/reconstruction, direct SQL update/delete rejection, long provider
decimal strings, exact boundary comparisons, reservations plus completed/incomplete
usage, zero values, canonical validation, persistence round trips, and historical
`REAL` conversion.

Completion requires the full offline pytest suite, repository-wide type-contract test,
focused migration/immutability/accounting suites, all deterministic offline evaluations,
Ruff lint and format checks, `git diff --check`, final diff review, and generated-
artifact review. Exact results belong in `STATUS.md` and `HANDOFF.md` after all gates pass.

## Completion Record

MVP-6.8 is complete. The focused required selection passed 164 tests with one expected
live-smoke skip; the full offline suite passed 605 tests with two expected opt-in skips;
all 38 deterministic evaluation cases passed. The repository-wide type-contract test,
Ruff lint/format, `git diff --check`, migration/trigger inspection, and final tracked-
artifact review passed. No dependency, live provider call, spending, commit, push, pull
request, or MVP-6.9 work was added.
