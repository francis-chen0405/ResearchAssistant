# Service-manager ownership review — 2026-10-01

## Scope and method

Reviewed `frontend/service_manager.py` and its desktop ownership callback
contract, including the isolated desktop backend/Electron shutdown path. Added
offline subprocess regressions that launch children in a session created by the
manager; no network service, provider, app data, or credentials were used.

## Confirmed finding

The manager only signaled a POSIX process group when its recorded leader was
still running. When Wigolo's leader exited while a child remained alive,
`stop()` skipped `killpg`, cleared the owned record, and emitted the ownership
callback as false while the descendant kept running. The same state let
`start()` overwrite the dead leader's ownership record without terminating its
descendants or emitting the old owner's false callback. On Windows, replacing a
dead leader also left its old `WindowsJob` handle open instead of closing the
kill-on-close job.

The failure was reproduced with actual local subprocesses: the leader spawned a
child and exited; `stop()` did not deliver SIGTERM to the child's handler, and a
SIGTERM-ignoring child remained alive. A restart emitted `True` for the new PID
without first emitting `False` for the retired PID. These tests failed against
the original implementation.

## Fix and regression coverage

`WigoloServiceManager` now serializes `start()` and `stop()` with a lifecycle
lock. It retires stale ownership before launching a replacement, closes the old
Windows job, and reports the old owner false before reporting a new owner true.
On POSIX it signals the recorded owned process group even when the leader has
exited, reaps/polls the leader during a bounded graceful-shutdown window, and
sends SIGKILL if descendants remain after that window. Cleanup targets only the
process group created with `start_new_session=True`; the no-owned-process path
still returns without signaling any group.

The first warning-as-error integration run also surfaced unclosed Popen output
pipes and a test-created replacement process that the restart regression had not
reaped. Output-reader threads now close their stream in `finally` and are joined
after shutdown. The regression cleanup stops and waits for the manager's current
owner and targets only the exact group recorded for the prior owner.

`tests/test_audit_service_manager.py` covers a graceful descendant after leader
exit, escalation against a SIGTERM-ignoring descendant, callback order during
restart, and closure of the retired Windows job. Each POSIX test's `finally`
block kills only its own test-created process group.

## Verification and boundaries

- Pre-fix subprocess reproductions failed in all three cases.
- Service-manager and frozen backend tests with warnings treated as errors:
  **14 passed**; Ruff checks for changed runtime and test files passed.
- The process-group tests were run with the narrowly scoped elevated runner
  because the default sandbox rejects signals to subprocess groups. An initial
  cleanup attempt was also rejected by the sandbox; the short-lived child
  processes expired, and the subsequent elevated test run used `finally`
  cleanup for every test-created process group.
- No edits were made to `desktop/backend.py` or `desktop/main.cjs`; their
  ownership callback and exit-cleanup handoff was cross-checked against the
  manager. No native application, credential store, or external service was
  accessed.
