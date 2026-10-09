# API, settings, and native boundary review — 2026-10-01

> Historical October 1 audit evidence. Subsequent repairs and local app replacement are recorded in [October 2 delivery](../../verification/committed-app-redelivery-2026-10-02.md); [current STATUS](../../../STATUS.md) owns today’s source and delivery state. Findings, test counts and artifact hashes below describe the original audit point.

The primary agent reviewed `frontend/api.py`, `frontend/security.py`,
`frontend/live_contracts.py`, `frontend/live_service.py`, `frontend/live_progress.py`,
`frontend/live_history.py`, `frontend/service_manager.py`, `credential_store.py`,
`desktop_settings.py`, `desktop_paths.py`, `file_lock.py`, `windows_credentials.py`,
`windows_job.py`, `application_runtime.py`, `desktop/backend.py`, `desktop/main.cjs`,
`desktop/build.py`, and `desktop/smoke_support.py`. Provider, lifecycle, and packaging
helpers independently cross-check the corresponding integration points. Windows
source review is not native Windows execution.

## Confirmed repairs

- Non-ASCII authorization headers caused `secrets.compare_digest` to raise instead
  of rejecting the session. Two isolated requests failed with HTTP 500 before the
  comparison changed to UTF-8 bytes; they now return the existing generic HTTP 401.
- Validating the stricter internal `LiveRunRequest` inside the start endpoint raised
  uncaught validation errors. Whitespace claims, directory paths, absent parent
  directories, and non-SQLite files each returned HTTP 500 in four regressions.
  The endpoint now handles this specific construction failure as the existing
  generic HTTP 422 before dispatching any worker or exposing input contents.
- The client treated the service's valid `starting` response as startup failure.
  The API-client regression failed before implementation. Startup now polls exact
  health with a 30-second deadline and abort deadlines on individual requests;
  exited, wrong-service, and launch-failed responses stop polling immediately.
- Preference POSTs could commit in completion order, allowing an older request to
  overwrite a newer choice. A deliberately held first write demonstrated the second
  write committing first. The client now serializes commits and resumes the queue
  after a failed save. Serialization captures each request's settings at submission.
- Snapshot requests for corrupt or non-SQLite databases exposed an uncaught
  `DatabaseCompatibilityError` as HTTP 500. The API now maps that specific exception
  to generic HTTP 400 without exposing the path or contents. The read-only regression
  verifies that the database bytes and modification time remain unchanged; the
  controller's compatibility exception contract remains intact.
- A desktop static export could bake in port 8765 when the separate API environment
  variable was omitted or incorrect. The first packaged-window test caught native
  CSP rejecting those requests, even though mocked browser checks and backend health
  had passed. `web/next.config.ts` now forces same-origin API requests in desktop
  mode. Config regressions cover absent, incorrect, and blank values, and the final
  export was deliberately built with the incorrect value to verify the guard.
  `desktop/frontend-smoke.cjs` also checks request origins before mocking responses.

The initial API boundary/desktop/API suite passed **40 tests**. The new offline
`desktop/audit-api-smoke.cjs` passes readiness, timeout, startup failure, commit
ordering, and save-failure recovery checks. The existing full frontend browser
smoke now includes two initial health probes and asserts that research dispatch
waits for readiness. The final API/compatibility focused suite passed **14 tests**
with warnings as errors. Final combined verification passed **1,256 tests with 2
unchanged skips**, Ruff, frontend lint/types, offline evaluation, four browser
smokes, API/config smoke, and rebuilt packaged-backend and actual Electron-window
checks. Exact artifacts, logs, hashes, and limits are in the [audit report](README.md).

## Assessed boundaries

Credential inputs remain transient `SecretStr` values and OS-vault-only secrets;
preferences allow only named non-secret provider settings and atomic, locked file
replacement. Desktop isolation, loopback session binding, navigation restrictions,
resource provenance, and ownership notifications were checked against current
source. No real vault/data, external account, paid call, installed-app replacement,
dependency, or release operation was performed. Process cleanup and saved-history
races have separate helper reviews and passed the final integration checks.

Also reviewed root environment-example comments, Git attributes/ignore rules, web
TypeScript configuration, and Next.js export configuration. `.env.example` now
distinguishes historical Phase-2 pricing from fresh selected-model presets and
limits discovery-key requirements to enabled lanes; settings remain blank and live
gates remain disabled. No environment credentials were read or written.
