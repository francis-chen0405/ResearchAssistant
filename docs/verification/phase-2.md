# Phase 2 verification record

Base: `6499f1d`; branch: `codex/phase-2-cleanup`; local target: macOS arm64.
No paid provider calls were used. Existing opt-in integration skips remain unchanged.

## Baseline

- Python: 909 passed, 2 skipped; existing Starlette/httpx deprecation warning.
- Ruff check and format: passed (128 Python files); Git diff check: passed.
- Frontend ESLint and TypeScript: passed.
- Existing frozen desktop smoke: passed with isolated native-vault/data locations,
  authenticated API, durable preferences and owned Wigolo startup/shutdown.
- Existing actual-window smoke: passed isolation, seven empty password inputs,
  duplicate-instance handling and normal shutdown.
- Captured all 160 domain JSON schemas and complete SQLite schema SQL/migration rows.

## Cleanup verification

- All 160 JSON schemas and all original model class/function ASTs are identical.
- Complete initialized SQLite SQL and migration rows are identical.
- Archived documentation is identical to the original commit except three pre-existing whitespace-only lines
  in archived CONVENTIONS.md, trimmed so the complete branch diff passes whitespace checks.
- Existing full suite after extraction: 909 passed, 2 skipped.
- New focused import-order, compatibility and source-fingerprint regressions plus
  repository annotation check: 15 passed.
- Ruff check/format passed after extraction (139 files); diff check passed.
- Full macOS resource build passed: locked Node/acquisition/Chromium, static Next.js
  export and PyInstaller backend. Native-vault/backend/acquisition smoke passed.
- Final full Python suite: 923 passed, 2 existing skips, same warning.
- Final frontend ESLint and TypeScript checks passed; full static export passed.
- Packaged macOS window smoke passed authentication/isolation, empty password inputs,
  duplicate-launch exclusion and shutdown. Final source refresh/installer and CI results
  are pending.

An initial history extraction left a method receiver on a module-level helper. Existing
history and annotation tests caught it; the receiver was removed and those tests pass.
No assertions or acceptance criteria were weakened.

## Retained limitations

Phase 1 Windows path/line-ending fixes were committed before this branch, but its
handoff lacked a successful Windows build/install record. Phase 2 uses the existing
native CI matrix to resolve build/runtime evidence. Neither CI smoke nor local artifact
smoke proves a clean-machine install, minimum-OS support, signing or notarization.
Those remain public-release gates in the Phase 1 desktop plan.
