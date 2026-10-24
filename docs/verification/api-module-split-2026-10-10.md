# Python API responsibility split — Prompt 10

October 10, 2026. Structural refactor of the migrated owner under
`backend/src/researchassistant/api/`. This record owns implementation and checks;
[STATUS](../project/STATUS.md) owns current verified state.

## Starting state and scope

Read AGENTS/conventions/architecture/decisions/status/handoff, plan/test indexes,
API/security/read-consistency/lifecycle/race tests and staged/unstaged diffs.
The folder move and earlier repairs were already present and are preserved.
The old graph lacked migrated API nodes. Refreshed it, searched routes and handlers,
traced inbound API callers and verified live source. A Luna Medium helper supplied
a read-only test/import/launcher inventory; Sol performed design and implementation.

Captured pre-split OpenAPI, canonical method/path/name/status inventory and 24 offline
responses in [the contract fixture](../../tests/fixtures/api-contract-before.json).
Every operation is covered, plus validation/redaction and origin failures. Only isolated
fixture database paths are normalized. Compare against these original bytes; do not
regenerate this fixture to accept a changed contract.

## File and route ownership

Paths are relative to `backend/src/researchassistant/api/`.

| Owner | Methods and paths / responsibility |
| --- | --- |
| `routes/research.py` | POST `/api/research/start`; GET `/api/research/{run_id}`; POST `/api/research/{run_id}/cancel` |
| `routes/history.py` | GET `/api/history`; POST `/api/history/import` |
| `routes/inspection.py` | GET `/api/research/{run_id}/trail`, `/api/research/{run_id}/v2-result`, `/api/research/{run_id}/v2-evidence` |
| `routes/settings.py` | GET and POST `/api/preferences`; GET `/api/model-profiles`, `/api/model-options`, `/api/configuration`; POST `/api/configuration/check` |
| `routes/credentials.py` | POST `/api/credentials`, `/api/credentials/{name}/check`, `/api/credentials/{name}/remove` |
| `routes/services.py` | GET `/api/service`; POST `/api/service/start`, `/api/service/stop` |
| `routes/health.py` | GET `/api/health` |
| `application.py` | Single assembly, middleware, sanitized validation/lifecycle errors and lifespan |
| `runtime.py`, `dependencies.py` | Explicit controller/service/I/O dependencies and shared lifecycle coordinator |
| `http_security.py`, `http_errors.py` | Session/host/origin boundaries; redacted/retryable inspection errors |
| `http_contracts.py`, `inspection_contracts.py` | HTTP schemas and evidence display contracts |
| `application_services/result_reads.py` | Final artifact fallback and evidence materialization from one validated read snapshot |
| `application_services/evidence_projection.py` | Pure quote/provenance, coverage, lineage, source-budget and website diagnostics |
| `application_services/configuration.py` | Offline configuration/model catalog and presence-only settings diagnostics |
| `api.py` | Public imports/factory, compatibility I/O adapters and lazy ASGI entry point |

Existing `live_service`, `live_lifecycle`, `live_progress`, `live_history`,
`discovery_diagnostics` and `service_manager` keep their responsibilities. Router factories
create fresh app-local routes. The facade declares no HTTP routes.
The migrated owner was 1,464 lines after earlier repairs; it is now a 334-line import/factory
facade. Route owners range from 19 to 189 lines; assembly is 103 lines. Application services
are 119-line result reads, 213-line configuration and 367-line pure evidence projection.

## Compatibility and contract decisions

- No deliberate HTTP contract or security change. Paths, methods, schemas, status codes,
  messages, descriptions, operation IDs, authentication, origin/host rules and redaction
  match the original inventory.
- `researchassistant.api.api.create_app` retains its signature. Runtime, schema, display
  helper and earlier exposed dependency imports remain re-exports. Installed `frontend.api`
  still aliases the same module object. Historical preference, connection-check, import and
  credential-removal replacement seams resolve at request time, even after app creation.
- Importing either facade now constructs no runtime/app. Explicit access to legacy `app`
  or `runtime` lazily returns one shared pair; the module command creates it on entry.
  This deliberate import behavior satisfies the requested absence of global side effects,
  with separate-process and singleton regressions.
- Result/evidence services close their read snapshot before projection. All three final
  artifact keys, admission/reviewer fallback, optional diagnostics and errors are preserved.
  Inspected databases are never created, migrated or changed.
- Prompt 05 admission/idle-change reservations and start availability move intact;
  service-manager synchronization is unchanged. Prompt 04 rejected-resume behavior
  remains in unchanged controller/progress owners.
- Source identity changes under the existing exact resume gate. Fresh research requires
  a new run. Historical inspection/export and persisted release hashes remain intact.

## Verification

Verified on macOS 26.6.2 arm64 / Python 3.12.14:

- All **21 operations** register exactly once. Saved OpenAPI (including descriptions,
  operation IDs, request/response schemas and statuses), canonical route metadata and
  **24 offline responses** match exactly. Every operation shares session, host and origin
  guards. Successful persisted result/evidence responses retain all three artifact fallbacks.
- **208 focused tests pass**: API split, existing API/security, credentials, atomic lifecycle,
  rejected resume, request/read consistency, read-only inspection, polling and evidence display.
  The new ten regressions additionally verify side-effect-free imports, one lazy default pair,
  one validated transaction/connection per request and closure before evidence projection.
- Final full Python suite: **2,387 passed, 5 existing skips in 253.43 seconds**;
  default discovery collects **2,392 tests**. An initial full run loaded a new test's original closure
  assertion before its correction and reported six failures (all that assertion), 2,381 passes
  and five existing skips. SQLite closure is now asserted on the owning request thread;
  no implementation or existing assertion was weakened. All ten new tests then passed.
- Ruff lint and format (**403 Python files**), repository root/dependency guard,
  staged/unstaged and new-file whitespace pass. Current navigation has zero broken links;
  nine preserved historical archive references remain as in Prompt 09. The original staged
  binary diff remains byte-identical. Prior archives and completed records are preserved.
- Renderer lint/types with pinned pnpm 11.19.0 pass. All five offline browser smokes pass:
  workspace/provider/evidence UI, polling/rejected-resume/restart, configuration races,
  service readiness/preference ordering and history races. Desktop handler tests (**20**)
  and native shutdown smoke also pass.
- Rebuilt current frozen backend using an isolated PyInstaller cache. All **246** source/
  configuration payload files match the checkout byte-for-byte. Frozen startup from an
  unrelated directory with empty PATH passes authentication, UI, isolated native-vault
  roundtrip/cleanup, durable temporary settings and owned Wigolo start/stop.
- Exact **251-file wheel** and fresh wheel/editable installs from unrelated directories pass
  package/resource/alias parity, CLI/API health, offline fixtures, binding replay and Unicode
  PDF. The source, wheel/editable and frozen source payload identity agree:
  `source-sha256:a524568b2932d8ab6e5058adfd6196899e4f7d7a71cd586549d7b84d8ccafc6d`.
  The frozen executable additionally binds its bytes; its SHA-256 is
  `5c614691a6746487af907ef15e36aa820a782fd357f35381c190ea35da8ad917`.
- Structural comparison verifies **33** moved definitions retain identical ASTs and **16**
  non-projection route bodies retain identical ASTs after dependency qualification. The
  three configuration/catalog service bodies also match their original route projections.

Commands ran from the workspace using `.venv/bin/python`: `-m pytest -q`, the focused
14-file selection recorded in `focused-final.log`, `-m ruff check .`,
`-m ruff format --check .`, `scripts/check_repository_boundaries.py`,
`scripts/verify_distribution.py --constraints desktop/constraints.txt --work-dir
/private/tmp/researchassistant-prompt10/installs`, `desktop/build.py --backend-only`
with an isolated `PYINSTALLER_CONFIG_DIR`, and `desktop/smoke.py desktop/build/resources`.
Renderer lint/types used pinned pnpm with `--config.verify-deps-before-run=false`;
desktop and browser commands are the unchanged commands in [the test map](../../tests/README.md).

Initial browser loopback and default PyInstaller cache access were sandbox-restricted;
reruns used approved loopback access and an isolated writable cache. Fresh installation
verification needed approved access to pinned build/runtime dependencies. These were
environment restrictions, resolved without changing dependencies or runtime policy.

Logs, isolated installs and before/after inventory are under
`/private/tmp/researchassistant-prompt10/`.
The exact preceding documents are in
[the starting-state archive](https://github.com/francis-chen0405/ResearchAssistant/tree/archive-2026-10-23-docs-baseline/docs/archive/2026-10-10-api-split-state).
Implementation and local verification are complete. No branch switch, staging, commit,
push, app installation or publication is included.
Local HEAD remains `94a241b` on `master`. Real research databases and paid providers were
not used. Native smoke used its dedicated temporary data and dummy credential namespace.
Python 3.11/Linux, Windows/Jobs, installers, clean-machine/minimum-OS and signing/notarization
retain the preceding delivery gates; this task establishes current local source/frozen checks.
