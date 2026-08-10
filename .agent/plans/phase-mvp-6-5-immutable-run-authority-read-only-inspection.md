# MVP-6.5 — Immutable Run Authority and Read-Only Inspection

## Authority and Boundary

MVP-6.2 Batch A, MVP-6.3, and MVP-6.4 are complete prerequisites. The user separately
authorized MVP-6.5 to enforce authoritative run-claim immutability in SQLite and to make
history and inspection genuinely read-only. This phase does not implement CLI-status,
usage-accounting, provider-contract, or type-hint batches. MVP-6.6 has not started.

## Migration 5: Immutable Run Authority

- Migration 4 is accurately described as `same-run provenance protection triggers`.
- Migration 5 is `database-enforced immutable runs.raw_claim`.
- Trigger `runs_raw_claim_immutable` executes before updates of `runs.raw_claim` for
  every run status. `WHEN NEW.raw_claim IS NOT OLD.raw_claim` rejects only an actual
  byte-exact value change and permits an assignment that leaves the claim identical.
- Rejection uses the stable, secret-free SQLite integrity message
  `runs.raw_claim is immutable`.
- Trigger creation, verification, and the migration-5 record share one explicit
  transaction. A failed or conflicting installation rolls back and does not record
  migration 5. Reopening an installed database verifies the existing trigger and is
  idempotent.
- Existing claim text and the public `runs` column shape are unchanged. The existing
  `update_run()` comparison remains as defense in depth.

## Read-Only Store and Compatibility Boundary

- `ReadOnlyStore` resolves the existing path, safely URI-encodes spaces and reserved
  characters, and opens SQLite with `mode=ro`. It enables foreign keys, uses
  `sqlite3.Row`, and sets connection-local `PRAGMA query_only = ON`.
- It never uses `immutable=1`, never creates a missing file, and never falls back to a
  writable connection.
- One session performs compatibility validation and every transitive store read for a
  run inspection. Live history and provider-contract display reads use the same
  read-only mechanism.
- The strict `DatabaseCompatibilityResult` and `DatabaseCompatibilityError` distinguish
  missing files, invalid SQLite, older schemas, newer schemas, corrupt schemas, and
  permission/open failures. Required migration records, tables, indexes, triggers, and
  the exact migration-5 trigger contract are checked without changing persistent state.
- Older databases are not migrated by inspection. Operators intentionally migrate one
  by starting or resuming a run with write access; that existing writable path calls
  `init_db()` before normal run work.
- Missing web-history databases retain the established empty-history behavior without
  creating a file. Incompatible web databases surface a safe read error and remain
  unchanged.

## Preserved Integrity and Runtime Contracts

Typed Pydantic reconstruction, released-brief hash verification, partial and running
inspection, deterministic bounded history ordering, insert-only evidence, same-run
provenance triggers, short-lived writable run connections, cancellation, concurrency,
and writable initialization/resumption remain unchanged. No ORM or dependency was
added, and no provider call is part of this phase.

## Regression Coverage

Coverage includes every terminal and running claim status, identical-claim updates,
other mutable fields, the application guard, migration-4 upgrade, migration idempotency
and atomic failure, historical claim bytes, trigger persistence and secret-free errors,
read-only compatibility categories, missing files, special-character paths, read-only
permissions, schema/migration/object/byte/hash/mtime preservation, CLI and web failure
behavior, partial inspection, WAL concurrency, terminal reconstruction in the existing
orchestration/CLI suites, and released-brief hash corruption.

## Completion Record

MVP-6.5 is complete after all required focused and full verification passes. Exact
results are recorded in `STATUS.md` and `HANDOFF.md`. No dependency, provider call,
spending, generated database, coverage/cache artifact, or commit was added. MVP-6.6 has
not started.
