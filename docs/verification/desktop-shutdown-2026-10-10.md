# Bounded desktop shutdown — 2026-10-10

## Scope and reproduction

Repair Prompt 06 in the existing dirty `master` checkout at `94a241b` without staging,
committing, installing, publishing, provider calls or user database access. Earlier
staged/unstaged repairs and proposal files are preserved. Read AGENTS, conventions,
current plan/architecture/decisions/status/handoff, Python shutdown and native smokes.
A Luna helper performed read-only smoke/test discovery; Sol implemented and verified.

The saved `/private/tmp/researchassistant-runtime-audit-94a241b-quit.cjs` ran before
editing and reproduced two prevented quits, stdin closed once, zero timers/kills,
and an indefinite child-exit listener. The initial advisory graph contained deleted
root paths despite matching HEAD; a fast refresh produced the canonical graph project
`Users-francischen-Library-CloudStorage-OneDrive2-EastsidePreparatorySchool-GitHub-ResearchAssistant`.
Graph discovery/trace and live source confirmed controller shutdown is owned by
`desktop/backend.py`. Important conclusions were checked against source and Git diff.
After implementation a second refresh reported ready under graph project
`Users-francischen-Library-CloudStorage-OneDrive2-EastsidePreparatorySchool-GitHub-ResearchAssistant-researchassistant`.
The final source refresh returned the original canonical graph project above to ready
with 9,768 nodes and 67,605 edges at the unchanged `94a241b` HEAD.

## Implementation and limits

- EOF remains first. Python's 90-second controller drain and conservative accounting
  are unchanged. The first quit arms a **150,000 ms** deadline; repeats never reset it.
  The 60-second margin includes server/worker/SQLite cleanup and normal acquisition
  teardown, whose waits/readers can consume approximately 25 seconds.
- Startup timeout is **30,000 ms**, now covering bootstrap, health and window load.
  Its failure enters that same shutdown deadline. A completely stuck startup therefore
  has a maximum configured **180,000 ms** spawn-to-shell-exit window. These watchdog
  guarantees assume an executing event loop and OS, not a suspended/hung kernel.
- POSIX backend spawn owns a new session. Deadline/exit cleanup signals only that
  group and the still-owned acquisition groups from the backend pipe. Ownership
  requires a safe positive integer and explicit boolean, excludes backend/shell PIDs,
  supports several owners, and forgets revoked owners. Native smoke reproduced an
  orphan descendant on ordinary root exit; group cleanup now covers it too.
- POSIX acquisition launchers initially inherit the backend group. A private stdin
  gate permits `setsid`/exec only after Electron has recorded ownership and acknowledged
  the exact PID and fresh request nonce. EOF, missing acknowledgement (10 seconds), or
  pipe failure terminates the launcher; quit never acknowledges a new detachment.
  The frozen onedir backend re-executes its internal supervisor mode; source runs use
  the same supervisor module. Both retain the acquisition PID/group through exec.
  Start additionally waits up to 10 seconds for that exact process group to exist,
  preventing immediate stop from racing `setsid`. Failure kills both launcher and
  any already-created group before revoking ownership.
- Windows uses the owned child handle, without `taskkill` or stale acquisition PIDs.
  Python enters an enclosing kill-on-close Job before bootstrap, retains its handle
  through exit and fails closed if assignment is denied. This covers child creation
  before individual acquisition Job assignment and multiple/nested generations.
- Exit/force paths close readline/streams, cancel startup/retry/watchdog timers and
  abort health fetches. Late startup/child events cannot reopen or re-signal anything.
  After engine exit, direct shell exit prevents renderer unload from extending quit.
  Native error dialogs are excluded from teardown; only fixed, secret-free shell
  diagnostics are emitted. Real Electron reproduced a Promise-returning parentless
  dialog deferring `before-quit`: its trace contained the startup timeout but no
  quit or shutdown timer. Removing that dialog restored both timers and exit 1.
- Electron never writes database/research/accounting state, refunds reservations or
  synthesizes completion. SQLite recovery and compatibility gates retain ownership.

## Initial implementation verification

Local platform: macOS **26.6.2 arm64**, Python **3.12.14**, Node **24.18.0**,
Electron **44.2.0**. The installed application is unchanged.

- `npm --prefix desktop test`: **19 deterministic handler tests passed** against
  actual `main.cjs`. Fake timers/child events verify exact 150,000 ms escalation,
  full graceful allowance, repeats, bootstrap/health/window stalls, setup races,
  late events, failures, fetch/retry cancellation, multiple owners, revocation,
  invalid ownership, simulated Windows handle targeting and resource cleanup.
- Focused desktop/lifecycle/ownership/cancellation/accounting Python checks:
  **102 passed, 2 native-Windows skips**. The new forced-writer regression kills a
  disposable process mid-SQLite transaction: integrity is `ok`, uncommitted completion
  rolls back, the exact RUNNING manifest/audit remains, and unknown exposure stays
  **12,500 tokens / $0.25**, with no physical completion.
- Final full `.venv/bin/python -m pytest -q`: **2,343 passed, 5 skipped in 201.05s**.
  Skips are three pre-existing platform cases and two new native Windows Job cases.
  The earlier full run before adding the writer regression also passed (2,342/5).
- Ruff lint/format over **303 Python files**, repository boundaries,
  staged/unstaged/new-file whitespace, JavaScript syntax and desktop workflow YAML
  checks passed. Desktop CI runs the new handlers/native smokes; its Python suite
  executes Job tests on Windows. No CI run was dispatched.
- Native `desktop/shutdown-smoke.cjs`: **normal, stuck, startup** passed. Actual
  backend/descendant and multiple acquisition groups terminate, an unrelated sentinel
  survives, and timers/streams retire. Production source is loaded unchanged with
  accelerated test clocks (30s→0.5s, 150s→2.5s).
- Native `desktop/shutdown-electron-smoke.cjs`: real Electron **startup stall / forced
  exit 1 / descendants gone** passed with those accelerated clocks. It copies current
  main source behind a test-only spawn/clock prelude and asserts both production timer
  values and quit/exit events. It touches no DB/vault.
- Fresh backend-only PyInstaller build and `desktop/smoke.py desktop/build/resources`
  passed: private bootstrap/authentication, randomly isolated native vault cleanup,
  durable settings, owned Wigolo lifecycle and graceful EOF exit. A first sandbox
  build could not access the standard PyInstaller cache; a disposable cache completed
  it. Native process/vault/UI checks ran outside sandbox restrictions with temporary
  data. Backend SHA-256:
  `f16572da740c40fca106721a5b23bd77f1c61e5c887ce2143cede9ff0fdae5f9`.
- Final `desktop/ui-smoke.cjs` with real local Electron + rebuilt frozen backend
  passed: authenticated renderer, isolated browser state/password fields, duplicate
  instance exclusion and normal quit. An initial renderer health-fetch attempt failed;
  fresh subsequent/final runs passed. This repair changes no renderer/network policy.

## Review repair

The independent review reproduced a P2: the actual service manager detached acquisition
before its ownership report reached Electron. Stopping the backend with `SIGSTOP`
immediately before that report, then triggering the shell deadline, killed the backend
and exited Electron while acquisition remained alive. The acknowledgement gate above
closes this creation-to-registration gap; a PID journal written after spawn would not.

Fresh local verification covers the actual manager stalled **before reporting, after
reporting, after acknowledgement**, running acquisition and unexpected backend exit.
The launcher cannot detach or execute before the gate opens. All created descendants
terminate; the unrelated sentinel remains alive. Native smoke clocks use 30s→3s for
Python import/startup and 150s→2.5s; deterministic handler clocks retain production values.
Python regressions cover exact/fresh acknowledgement, stale acknowledgement after PID
reuse, EOF/timeouts, failed handoff cleanup, secret-free execution and supervisor EOF.
The standalone frozen smoke monitor now acknowledges the same private protocol.

- **20 deterministic Electron handler tests** and **34 focused Python checks / 2
  native-Windows skips** passed. The native broken-release-pipe probe confirmed typed
  launch failure, launcher termination, stream cleanup and ownership revocation.
- Final full `.venv/bin/python -m pytest -q`: **2,350 passed, 5 skipped in 295.20s**
  against the completed ownership/readiness repair. Skips remain the three earlier
  platform cases and two native Windows Job cases. No acceptance criteria changed.
- All **9 native process scenarios**, including immediate stop after deliberately
  delayed supervisor initialization, and real Electron startup-stall/forced-exit
  checks passed. A fresh backend-only PyInstaller build and frozen lifecycle smoke
  passed with an empty PATH, temporary data and randomly isolated native credentials.
  Final backend SHA-256:
  `d1c17e8355d97f3d0c67b54067cb3fb3a832a04289e37922c89d55d5d5cd676f`.
- Real Electron + that final frozen backend passed authenticated renderer startup,
  browser isolation, duplicate-instance exclusion and normal quit.
- The bounded process-group readiness failure probe terminates the launcher and
  revokes ownership when detachment never happens. Scoped stop cannot miss a
  newly detached group between successful start and immediate stop.
- Ruff lint/format across **306 Python files**, repository boundaries, staged/unstaged/
  new-file whitespace and affected JavaScript syntax passed. The advisory graph was
  refreshed to ready at the same HEAD (9,404 nodes / 64,005 edges); live source and
  regressions remain authoritative. No installation, staging, commit or push occurred.

The Windows native Job tests are added source coverage with a native-platform
skip on macOS; passing simulated Windows tests are not native Windows evidence.
Native Windows nested Job inheritance, denied assignment and forced descendant exit
require Windows execution, including a fresh frozen/Electron build. Current
packaged Windows/macOS distributions, actual macOS 14, clean-machine and
signed/notarized delivery are separate pending boundaries. Installed app unchanged.
