# Local application service

The current UI is the existing Next.js application in root `frontend/`. Electron loads its static
export from the authenticated loopback Python API. For browser development, run
`python -m researchassistant.api.api` after installing `./backend` and `pnpm --dir frontend dev` separately.
Use the [desktop guide](../../../../desktop/README.md) for packaged builds and smokes.

`live_service.py` owns configuration preflight, worker registration, cross-process lock
ownership, cancellation and immutable snapshots. `live_contracts.py` owns strict API/view
contracts; `live_progress.py` projects persisted progress and conservative usage;
`live_history.py` reads history and research trails through validated read-only sessions.
Controller entry points and contract imports remain compatible. Shared executable identity
comes from `researchassistant.runtime.application_runtime`; no service needs to import the
CLI to compute it.

`api.py` is the compatibility import/factory facade. `application.py` centralizes assembly,
sanitized errors and lifespan; `http_security.py` owns desktop/session/host/origin guards.
`routes/` contains small app-local HTTP owners; `application_services/` materializes
one validated read snapshot and projects result, evidence and configuration diagnostics.
`http_contracts.py` and `inspection_contracts.py` retain the original HTTP schemas.
Importing the facade creates no runtime or app; explicit legacy `app`/`runtime` access
returns one lazily initialized pair. Installed `frontend.api` remains the same-module alias.
See [the route map and contract evidence](../../../../docs/verification/api-module-split-2026-10-10.md).
`service_manager.py`
owns acquisition-service lifecycle. The existing evidence viewer, fixture tooling and
historical export adapters remain available; they do not select a new research policy.
Fresh research uses `researchassistant.research.v2_orchestrator` and current configured
discovery/model routes. Use canonical `researchassistant.*` paths for backend imports;
installed `models.py`, `store.py`, and `orchestrator.py` facades under `backend/src/`
remain compatibility aliases.

See [architecture](../../../../docs/project/ARCHITECTURE.md) for exact evidence, persistence, accounting and
credential invariants. The workspace, settings and history workflows are implemented. Current source includes
all six discovery phases: provider-specific queries, bounded retrieval/ranking, exact
previews, seed expansion and frozen product controls. [STATUS](../../../../docs/project/STATUS.md) distinguishes
this source behavior from installed-build provenance and pending live acceptance.
The [original frontend README](../../../../docs/archive/pre-phase-2/frontend/README.md) is preserved
verbatim. This document replaces its historical MLP-only provider/launcher description.

Use [the test map](../../../../tests/README.md) for focused API/lifecycle tests and full collection.
