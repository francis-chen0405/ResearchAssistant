# Handoff

Phase 2 cleanup implementation is ready for final verification. Do not start Phase 3
frontend redesign without explicit authorization. Work is on `codex/phase-2-cleanup`,
from clean Phase 1 commit `6499f1d`; no pre-existing user edits were present.

Read [architecture](ARCHITECTURE.md), [conventions](CONVENTIONS.md),
[active plan](.agent/plans/phase-2-cleanup.md) and
[verification record](docs/verification/phase-2.md). Stable `models`, `store`,
`orchestrator`, CLI and controller imports remain. Fixture and historical provider
execution/read/export are intentionally retained. Existing native vault, data-path,
lock and process-tree boundaries remain unchanged.

Source-layout changes are covered by existing packaging/fingerprint rules. Rebuild,
restart and start a new run; do not loosen exact resume checks. Prompts and UI components
were not changed. Phase 3 can use the separated strict request/view contracts and
read-only history/progress projections without taking ownership of workers or locks.

Remaining work: finish the final full suite, packaged macOS smoke and existing native
macOS/Windows CI workflow, then record actual results. Signing/notarization, minimum-OS
and clean-machine installation are separate retained Phase 1 release gates.
Use `.venv/bin/python -m pytest` / `-m ruff` in this checkout: installed launcher
shebangs still reference its older location.

The complete previous handoff is retained in
[the archive](docs/archive/pre-phase-2/HANDOFF.md). This file replaces its chronological
phase narratives with the current boundary and actionable verification work.
