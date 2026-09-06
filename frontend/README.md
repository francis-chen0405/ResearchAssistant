# Local application service

The current UI is the existing Next.js application in `web/`. Electron loads its static
export from the authenticated loopback Python API. For browser development, run
`python -m frontend.api` from the repository root and `pnpm --dir web dev` separately.
Use the [desktop guide](../desktop/README.md) for packaged builds and smokes.

`live_service.py` owns configuration preflight, worker registration, cross-process lock
ownership, cancellation and immutable snapshots. `live_contracts.py` owns strict API/view
contracts; `live_progress.py` projects persisted progress and conservative usage;
`live_history.py` reads history and research trails through validated read-only sessions.
Controller entry points and contract imports remain compatible. Shared executable identity
comes from `application_runtime.py`; no service needs to import the CLI to compute it.

`api.py` retains transport validation and desktop authentication. `service_manager.py`
owns acquisition-service lifecycle. The existing evidence viewer, fixture tooling and
historical export adapters remain available; they do not select a new research policy.
Fresh research uses `v2_orchestrator.py` and current configured discovery/model routes.

See [architecture](../ARCHITECTURE.md) for exact evidence, persistence, accounting and
credential invariants. UI components and workflows are unchanged; Phase 3 has not begun.
The [original frontend README](../docs/archive/pre-phase-2/frontend/README.md) is preserved
verbatim. This document replaces its historical MLP-only provider/launcher description.
