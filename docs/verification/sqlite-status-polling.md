# SQLite status polling verification

Started 2026-09-19; completed 2026-09-20. Scope: request-scoped read reuse and
non-overlapping browser polling.
No paid provider calls, schema migration, journal-mode change or dependency additions.

## Deterministic before/after measurement

The baseline is `frontend/live_service.py` from `76dfc00` (the clean cherry-pick of
`5cc95292ea4f0b44d70cafbe042e5d50dd09aa32`). A temporary module loaded that original
controller alongside the current controller in the same interpreter. Shared reader helpers
retain the baseline path behavior; their change is accepting an existing connection.

An isolated fixture from `test_running_v2_snapshot_reports_persisted_progress` contains
one running v2 run, its fingerprint and two legacy physical-call start artifacts with no
completions. The same file was inspected with the original and current controllers, first
at adaptive search and then at the planner stage (which exercises more fallback probes).
Instrumentation wrapped `sqlite3.connect`, `_validate_read_only_schema`, and SQL trace
callbacks for `PRAGMA quick_check`. Fixture creation and the stage change were outside
measurement. No providers were invoked.

| Fixture stage | Connections before → after | Full validations before → after | quick_check before → after | Writable-capable opens before → after |
| --- | --- | --- | --- | --- |
| Adaptive search | 51 → 1 | 17 → 1 | 17 → 1 | 34 → 0 |
| Claim planner | 65 → 1 | 33 → 1 | 33 → 1 | 32 → 0 |

For both cases, complete `LiveRunSnapshot.model_dump(mode="json")` outputs were equal
before and after. Database bytes and nanosecond modification time remained unchanged.
These are operation counts on two prepared fixtures, not timing measurements or a claim
about live research completion time. Counts vary with persisted artifacts and stage.

The full validation still occurs once every request and remains proportional to database
size. Point queries for budget/progress artifacts are retained; this phase removes repeated
connections and full validations without changing their interpretation.

## Verification results

- Existing read-only inspection, API and runtime-integrity checks: 74 passed.
- New compatibility/lifecycle checks: 7 passed (invalid/older/newer/corrupt database,
  missing file, replacement at the same path, close on projection failure).
- Focused snapshot, compatibility and v2 production checks: 63 passed.
- Full Python suite: 1,019 passed, 2 existing skips; one upstream deprecation warning.
- Ruff repository lint and format checks: passed.
- Frontend ESLint, TypeScript and production desktop export: passed.
- Dedicated polling browser acceptance: five deterministic status calls, maximum
  same-run concurrency one; error recovery, delayed response, terminal stop, active-run
  replacement and unmount cleanup passed.
- Established offline frontend acceptance: passed, including automatic preview/recovery,
  provider settings, run progress/cancellation, history, export and dialog behavior.
- JavaScript syntax and `git diff --check`: passed.

An independent Luna review found one adjacent correctness issue: an imported terminal
artifact was read through the requested connection but projected its persisted original
database path. The snapshot now receives the resolved requested path separately. A
parameterized regression moves completed terminal artifacts, removes the original file,
and verifies released/blocked/failed/cancelled reconstruction, diagnostics, one read-only
session and the returned imported path.

## Follow-up boundary

WAL adoption and explicit busy-timeout policy are not implemented. A separate storage
change must address checkpointing, reader/writer contention, `-wal`/`-shm` lifecycle,
backup/import, startup and interrupted shutdown. Existing WAL-reader coexistence coverage
is retained. This work does not establish live research effectiveness or release readiness.
