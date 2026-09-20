# SQLite status polling

Status: complete, explicitly authorized 2026-09-19 and verified 2026-09-20.

## Scope

Use one validated request-scoped read-only connection for each v2 status snapshot,
including artifact probes, progress, budget, diagnostics and terminal reconstruction.
Preserve path-based helper APIs, integrity/schema validation and fresh committed reads.
Prevent overlapping frontend polls and stop scheduled work on terminal state or cleanup.

The SQLite changes were isolated from the implementation worktree and are now combined
with the separately reviewed deep-analysis concurrency commit on local `master`.

No WAL activation, schema change, persistent validation cache, shared worker connection,
dependency, research-policy change, paid call, packaging, merge, push or publication.

## Acceptance and verification

- Instrument one connection and one full validation/quick_check per v2 snapshot.
- Compare complete snapshot behavior and observe writes committed between requests.
- Preserve read-only flags, database bytes/mtime/schema/triggers and typed failures.
- Cover terminal, startup, historical, missing and incompatible/corrupt databases.
- Prove delayed polls cannot overlap; errors retry and cleanup/terminal states stop polling.
- Run focused and full Python tests, Ruff lint/format, frontend lint/types/build,
  established offline frontend/API smokes and diff whitespace checks.
- Record deterministic before/after counts, verification and limitations here and in
  STATUS/HANDOFF; commit locally on `codex/sqlite-status-polling` with a clean worktree.

## Follow-up boundary

WAL, busy-timeout policy, checkpoint/sidecar lifecycle and import/backup behavior require
a separate storage decision. Full validation still occurs on each snapshot request;
this phase removes repeated validation within that request. Live research effectiveness
and release acceptance remain open under the Mac-first plan; no paid allowance is renewed.

## Delivery record

The v2 status path now opens one validated `ReadOnlyStore` per request and passes its
connection through terminal discovery, providers, manifest, directions, diagnostics,
budget, stage, round, directional progress, contract and status-message reads. Imported
terminal results retain their immutable payload but report the database path actually
opened by the user. The frontend waits for each request to finish, delays 1.5 seconds,
and cancels pending work when the effect ends.

Deterministic fixtures measured 51 connections / 17 validations at adaptive search and
65 / 33 at claim planning before the change; both use 1 connection / 1 validation now,
with zero writable-capable opens. Complete snapshots remained equal, apart from the
intentional imported-path correction, and database bytes/mtime stayed unchanged. See
`docs/verification/sqlite-status-polling.md`.

Verification passed: 1,019 Python tests with two existing skips; Ruff lint/format;
frontend ESLint, TypeScript and desktop production export; the dedicated delayed/error/
terminal/replacement/unmount polling smoke; established offline frontend acceptance; JavaScript
syntax; and diff whitespace. No provider call, packaging or install occurred. The change is
merged locally into `master`; no remote push or publication occurred.
