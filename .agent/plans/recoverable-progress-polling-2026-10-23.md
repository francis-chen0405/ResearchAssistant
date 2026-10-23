# Recoverable research progress polling

## Scope and behavior

The October 23 implementation request authorized a local renderer change with tests and records.
The subsequent user request authorizes code review, corrections, commit and push to master.
Installation and paid research remain outside this task.

Each snapshot request has a ten-second deadline covering headers and body, composed
with lifecycle cancellation. The API helper creates a fresh controller and clears its
timer/listener on completion or cancellation. Normal polling waits 1.5 seconds after
a read settles. Three consecutive failures pause automatic reads; a manual reconnect
resets that bounded allowance and reads the same run/database. Concurrent reconnect
clicks cannot overlap requests. Success clears the error and resumes polling; terminal
snapshots stop it. Navigation pauses reads without clearing the run or exhausted
retry budget. Layout cleanup suppresses late responses and clears pending timers.

Starting and progress views share scoped polite connection announcements and controls
for reconnect, History and cancellation. Last-confirmed timestamps record browser
receipt of a validated response, not backend checkpoint time. Stored snapshots remain
visible through failures with explicit uncertainty. Cancellation sends once per user
action, has its own ten-second deadline, and shows requested only after a positive
backend response. Pending and confirmed cancellation are guarded against duplicate
clicks. Timeout/failure stays unconfirmed and is never retried automatically. Old-run
cancellation responses cannot change a replacement selection. Backend state, saved
research, research start behavior and provider accounting are unchanged.

## Verification

- Full Python suite: **3,239 passed / nine existing skips** in 808.21 seconds on macOS.
- All **31 actual-component/hook tests** pass. New fake-request/fake-timer cases cover
  hanging headers/body reads, three-failure pause, same-run reconnect with no overlapping
  requests or research starts, retained snapshots/timestamps, navigation/replacement/
  unmount races, terminal cleanup including stale reconnect actions, cancellation
  confirmation/decline/unknown outcome, and reopening the same explicit selection.
- Frontend ESLint, TypeScript and the final desktop static webpack export pass.
- Ruff lint and formatting (531 files), repository boundaries and staged/unstaged
  whitespace checks pass. The advisory graph was refreshed after implementation;
  live source and tests remain the authority.
- The initial browser attempt was blocked by sandbox loopback permissions. During
  the authorized review, four browser scenarios passed against the final static export,
  including 14 deterministic polling snapshots with max concurrency one, bounded
  recovery before/after a snapshot, retry-budget preservation across navigation,
  same-run reconnect and backend-confirmed cancellation. The fifth check exposed
  a missing `AbortController` in the isolated API-client VM harness. The harness now
  supplies the actual abort controller and browser timer globals; its existing service
  readiness and ordered preference-commit assertions pass. The sixth history browser
  check then passed. All six offline checks have successful execution results.

## Review and publication

Manual review found no blocking production defects. It checked whole-response timeout
cleanup, bounded sequential retries, same-run identity, stale selection/navigation
responses, terminal cleanup, and cancellation confirmation/unknown outcomes. Review
fixed the API-client smoke harness compatibility issue without changing production
behavior or weakening assertions. No backend or Python test source changed; the full
3,239-pass/nine-skip receipt above remains applicable. Review also reran all 31 renderer
tests, frontend lint/types/static build, 22 focused API-contract/boundary tests, Ruff,
repository boundaries and whitespace checks. Logs are under `/private/tmp/ra-polling-review-*`.

The user authorized commit/push to master after review. The installed app and real
research data remain unchanged. The existing packaged acquisition health blocker is
outside this renderer task; these results do not establish native installation acceptance.

## Limitations

During a connection loss the renderer cannot establish whether the worker is active
or a cancellation persisted. History and reconnect are read-only recovery paths.
Automatic retries pause after three consecutive failures even if the service later
recovers; the user explicitly reconnects. Backend recovery policies remain unchanged.
