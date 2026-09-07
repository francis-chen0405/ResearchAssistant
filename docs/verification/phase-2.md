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

- All 160 JSON schemas, original model class/function ASTs, and all 31 model
  constants/type aliases are identical. No prompt or UI files changed.
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
- Desktop JavaScript syntax and current documentation link checks passed.
- [Regular branch CI](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/34062740061)
  passed on final source revision `52e8f75`: Python 3.11 and 3.12 tests, Ruff, and
  the offline adversarial evaluation.
- Final-source macOS DMG and ZIP built successfully. `hdiutil verify` and `unzip -tq`
  passed. Both runtime/native-vault/acquisition and actual-window smokes passed directly
  from the read-only mounted DMG; it was detached afterward. No installed app was replaced.
- The first mounted runtime launch exceeded its unchanged 45-second startup allowance
  while the independent window smoke ran concurrently. The window smoke passed, then the
  unchanged runtime smoke passed by itself. No timeout or assertion was relaxed.
- All 92 packaged source/prompt/manifest files match the final checkout byte-for-byte.
- [Earlier cleanup native matrix](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/34062630000)
  passed both macOS and Windows, including full regressions, static frontend build,
  frozen runtime/native vault/acquisition smoke, actual-window smoke and installer build.
- [Final source native matrix](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/34078632828)
  passed both targets on source revision `52e8f75`: full Python/Ruff/frontend checks,
  bundled-runtime/static builds, frozen native-vault/backend/acquisition smokes,
  actual-window smokes, unsigned macOS DMG/ZIP and Windows NSIS installer creation,
  and artifact upload. Later commits only close documentation; executable inputs match
  this verified revision.

Local macOS disk-image creation failed inside the OneDrive-backed checkout with the
OS error `Operation not supported by device`. The unchanged builder succeeded with
output under `/private/tmp`; see the desktop guide. No packaging acceptance check was
removed and no application runtime path changed.

An initial history extraction left a method receiver on a module-level helper. Existing
history and annotation tests caught it; the receiver was removed and those tests pass.
No assertions or acceptance criteria were weakened.

## Retained limitations

Phase 1 Windows path/line-ending fixes were committed before this branch, but its
handoff lacked a successful Windows build/install record. Phase 2 uses the existing
native CI matrix to resolve build/runtime evidence. Neither CI smoke nor local artifact
smoke proves a clean-machine install, minimum-OS support, signing or notarization.
Those remain public-release gates in the Phase 1 desktop plan.

## Local final artifacts

Verified output and `SHA256SUMS.txt` are copied to `desktop/dist/` (ignored build
artifacts). Delivered installer checksums match, and the copied application also passes
its window smoke. The original build output remains under
`/private/tmp/researchassistant-phase2-final/` for this session.

```text
96f80fe12b833715cd92daf6a86ca3446974b116b44975db9a707c3099babecc  ResearchAssistant-0.1.0-arm64.dmg
d53d4b283df3359d734869bd79d4718e6b0880bfaaa4537c4883828b918143d7  ResearchAssistant-0.1.0-arm64-mac.zip
```
