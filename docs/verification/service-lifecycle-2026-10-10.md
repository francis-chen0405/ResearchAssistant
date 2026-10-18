# Atomic service stop and research admission

Completed locally on 2026-10-10 on macOS arm64/Python 3.12.14. Local HEAD remains
`94a241b` on `master`. Earlier staged root cleanup and unstaged runtime/discovery
repairs were preserved. This repair remains unstaged/uncommitted; the installed app
has not changed.

## Reproduction and bounded scope

The service-stop portion of the saved
`/private/tmp/researchassistant-runtime-audit-94a241b-probes.py` reproduced against
current source before the repair: HTTP **200** and
`service_stopped_during_active_research=True`. Its unrelated resume-status assertion
was superseded by the preceding repair, so only the service-stop probe was executed.

The rebuilt `/private/tmp/researchassistant-lifecycle-orders-probe.py` exercises actual
HTTP research admission, with fake acquisition/vault/import boundaries and temporary
paths. Before the repair, stop, credential save, credential removal and history import
each returned **200** after admission returned **200**, with research active at the
mutation. After the repair, all four mutations complete with **200**, the competing
admission returns **409**, and no research is active at the mutation. The retained
regression surface is `tests/test_service_lifecycle_atomicity.py`; the disposable
scripts supplement reproduction and measurement.

The three nearby idle guards had the same confirmed check-then-act gap. Credential
save covers native-vault save, environment application and the existing provider
route/price changes. Ordinary interface preference saves remain available: active
workers consume immutable request/configuration, not later interface preferences.
Read-only configuration checks and credential connection tests gain no lifecycle lock.
Startup credential loading precedes HTTP service and has no equivalent admission guard.

## Coordination and ownership

`frontend/live_lifecycle.py` owns one coordinator per live controller. `ApiRuntime`
reuses it; injected boundary doubles receive a runtime coordinator. Both HTTP admission
and direct `LiveResearchController.start()` reserve admission before configuration
capture through worker registration. HTTP/direct entry can nest their short reservations.
The controller's unfinished futures then remain the authority for ownership; completed
futures need not wait for callback eviction.

An idle operation checks pending admissions and unfinished futures while holding the
coordination mutex, marks a change in progress, then releases the mutex. It clears the
reservation in `finally`, including failure. Admissions during a change receive
HTTP **409** with `A service or configuration change is in progress. Retry shortly.`
An admitted/pending run makes ordinary stop return the existing **409** detail,
`The owned service cannot stop while research is active.` Credential/import active-run
conflicts retain their existing **409** detail. Success response models, configuration
failures, native-vault failures, import errors and duplicate-run reconnect responses
retain their established contracts.

The mutex covers only counters/flags and the in-memory ownership read. Its sole nested
lock order is coordinator → controller state. Registration/completion never acquires
the coordinator while holding controller state. There is **no coordination mutex held
across** identity/configuration preflight, file-lock acquisition, SQLite reads/waits,
paid requests, vault access, import backup, acquisition teardown or shutdown draining.
Long operations retain a logical reservation; competitors receive a conflict instead
of waiting for their I/O.

Service start uses a shared reservation: it remains available during research and stop
cannot overtake an in-flight launch. The manager retains its separate start/stop
serialization and exact recorded process-group/Windows-job ownership. API lifespan cleanup
uses the same idle reservation. Native ownership callbacks, child environment filtering,
vault rules and explicit desktop exit's bounded cancellation/drain and unknown-outcome
preservation remain unchanged. Different database workers retain executor concurrency
and per-database process locks.

The trace covered API start/cancel/service routes, credential save/remove, history import,
preference/configuration paths, worker registration/eviction, and `desktop/backend.py` →
controller shutdown → owned cleanup. Graph status/refresh was checked before and after.
A fresh `ResearchAssistant-service-lifecycle-review` index exposes the new coordinator;
the earlier advisory map omitted that untracked file even after refresh. Important
conclusions were verified against live source, the dirty Git diff and relevant tests.

## Barrier and accounting evidence

**26 new regressions** cover both operation orders for all four idle changes, direct and
HTTP preflight admission before registration, active ownership, duplicate admission at
preflight, duplicate stop, separate concurrent databases, repeated service start during
research, failed launch, configuration/submission/vault/import/stop failures, a finished
future with callback eviction pending, and a run finishing as stop checks ownership.

Real pipeline/controller regressions use fake providers and disposable databases:

- An interrupted physical-call start remains exactly equal in the audit after duplicate
  admission, rejected stop, cancellation and timed-out shutdown draining. No model/search/
  acquisition call is replayed; its unknown completion remains absent.
- A paused model call has one durable start and no completion while in flight. The
  coordination mutex remains available. Stop stays **409** through cancellation/draining,
  then succeeds after completion. The same start acquires its completion; the model
  executes once and no search/acquisition request starts after cancellation.

No fake stop observed an unfinished worker. Operations and callbacks completed without
deadlock. Rejected stop does not cancel a worker, clear its process lock, edit SQLite,
refund a reservation or cause provider retry.

## Measured contention

`/private/tmp/researchassistant-lifecycle-contention.py` instruments the coordination mutex
and exercises eight threads with **24,000 operations**, including deliberately overlapping
1 ms fake I/O outside the mutex. One recorded run completed **12,000 operations** and
returned **12,000 conflicts**, with **36,000 critical sections** in **211.621 ms**:

| Measurement | Observed |
| --- | --- |
| Mutex hold median / p99 / maximum | 0.208 / 0.375 / 20.167 µs |
| Mutex acquisition wait p99 / maximum | 0.208 / 24.000 µs |
| Admission conflict p99 during held fake stop (1,000 attempts) | 1.500 µs |
| HTTP admission during held fake stop (100 requests) | all 409; zero workers |
| HTTP response median / p99 | 1.460 / 2.461 ms |

These local synthetic timings include instrumentation and interpreter scheduling; they
are observations, not latency guarantees. The held stop was still pending after all HTTP
conflicts, then completed with 200 when released. Barrier tests separately prove both
legitimate orders and that slow I/O does not hold the mutex.

## Verification

- Focused controller/API/service/desktop/lifecycle/accounting checks: **184 passed in
  30.09 seconds**.
- Full Python suite: **2,340 passed, 3 existing skips in 226.90 seconds**.
- Ruff lint and format: pass across **302 Python files**; repository root/import guard:
  pass; staged, unstaged and new-file whitespace checks: pass.
- Web ESLint and TypeScript: pass; fresh Next.js **16.3.1** webpack desktop static export:
  pass, using installed dependencies directly after pnpm attempted an unavailable registry
  lookup. No dependency or lockfile change was made.
- API-client offline smoke and desktop shell syntax: pass. Fresh-export offline interface,
  polling and configuration-race browser smokes: pass. Their temporary loopback servers
  and browser required sandbox escalation; application APIs were mocked.

All new tests/probes use fake services/vault/providers and temporary data. Existing
ownership regressions use controlled temporary child processes. No paid request, real
research database mutation, native vault operation, native app build/replacement,
staging, commit, push or publication occurred. Frozen-bundle/installed-app smokes are
outside this fake-service scope and were not claimed.
