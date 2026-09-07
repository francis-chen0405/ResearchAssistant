# Handoff

Phase 2 is complete on `codex/phase-2-cleanup`, from clean Phase 1 commit `6499f1d`.
No pre-existing user edits were present. Do not begin Phase 3 frontend redesign without
explicit authorization. No merge or public release was performed.

Read [architecture](ARCHITECTURE.md), [conventions](CONVENTIONS.md),
[completed plan](.agent/plans/phase-2-cleanup.md) and
[verification record](docs/verification/phase-2.md). Stable `models`, `store`,
`orchestrator`, CLI and controller entry points remain. Fixture and historical provider
execution/read/export are intentionally retained. Native vault, data-path, lock and
process-tree ownership remain unchanged.

All required checks pass, including both native desktop builds, runtime/window smokes
and installers. Final executable source is `52e8f75`; later commits record documentation
only. The local final DMG passed both mounted-artifact smokes and archive checks.
Signing/notarization, minimum-OS and clean-machine installation remain release gates.

Rebuild, restart and start a new run after updating: source-layout changes alter the
unchanged executable fingerprint. Never loosen resume checks or reinterpret historical
rows. Phase 3 can use the strict request/view contracts and read-only history/progress
projections; worker, cancellation and cross-process lock ownership remain in the controller.
UI components and prompts were untouched.

Use `.venv/bin/python -m pytest` / `-m ruff` in this checkout: installed launcher
shebangs reference its older location. For local DMG creation, use the documented
temporary output directory; the synced checkout rejected disk-image creation.
The [original handoff](docs/archive/pre-phase-2/HANDOFF.md) preserves the full prior
narrative; this file replaces it with the current boundary and verification outcome.
