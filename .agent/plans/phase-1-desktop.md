# Phase 1 — local desktop application

Status: implementation in progress. Current desktop scope supersedes historical
MVP/MLP/v2 summaries. Work stays on master at the user's explicit request.
Research stages, routing, budgets, evidence and resume policies are unchanged.

## Packaging decision

Electron with a PyInstaller one-folder Python backend and static Next.js export.
Tauri external binaries can package Python, but cannot eliminate Wigolo's separate
Node runtime, native libraries, or Playwright browser. Electron keeps installer
orchestration in JavaScript; its larger Chromium footprint is an accepted cost.
Wigolo uses standalone Node, not Electron's different native ABI.

Dependencies flagged to the user: pinned Electron/electron-builder, PyInstaller,
and an explicit Windows native credential-vault backend. No plaintext fallback.

## Acceptance sequence

- [ ] Packaged vertical slice on macOS and Windows: UI, Python health, durable data,
  isolated OS vault round-trip, owned Wigolo start/health/stop.
- [x] Portable paths, cross-process exclusion, settings and history migration.
- [x] Credential save/replace/remove, sanitized errors, local request authentication.
- [x] Shutdown, cancellation, crash recovery, source/prompt fingerprints.
- [ ] Reproducible installers and offline CI checks on both operating systems.
- [x] Full Python/frontend checks and actual artifact/platform evidence.

No installer or platform verification is claimed until exercised. Signing,
notarization and clean-machine installation remain explicit release gates.
No paid provider calls or publishing are authorized by this implementation.

## Implementation and evidence (2026-09-05)

- [x] macOS packaged vertical slice: native vault, durable data, frozen UI/backend,
  owned pinned acquisition; tested without a developer-tool PATH.
- [x] Portable paths/locks, native vault save/replace/remove, typed preferences and
  verified immutable history import.
- [x] Authenticated loopback shell, renderer isolation, cancellation-aware shutdown,
  process ownership and complete source/prompt/frozen executable fingerprints.
- [x] macOS .app, DMG and ZIP packaging; copied .app passes both smoke suites outside
  the checkout. Final archive verification follows below.
- [x] macOS/Windows CI and package workflows, dependency locks and build constraints.
- [x] pytest 909 passed / 2 existing skips; Ruff lint/format, Git diff check, frontend
  lint/type/static build and JavaScript syntax checks passed.
- [ ] Windows workflow execution, actual Windows installer and Windows installation test.
- [ ] Signing/notarization, minimum-OS and clean-machine release verification.

This is an implemented desktop foundation with verified local macOS test artifacts,
not a fully verified cross-platform release. Windows hardware and signing credentials
are unavailable in this session. No public release or remote-state changes were made.

Dependency decision finalized: native Windows ctypes APIs avoid adding a keyring package.
Electron/electron-builder and PyInstaller are the only new direct build dependencies;
Wigolo is now a locked bundled runtime rather than a runtime npx download. The full
validated Python build environment is constrained in `desktop/constraints.txt`.

Artifacts: `desktop/dist/ResearchAssistant-0.1.0-arm64.dmg`,
`desktop/dist/ResearchAssistant-0.1.0-arm64-mac.zip`,
`desktop/dist/mac-arm64/ResearchAssistant.app`.

## Final macOS artifact verification

Both window and frozen-backend/native-vault/acquisition smoke suites passed directly
from the final read-only mounted DMG, in addition to the copied application test.
`hdiutil verify` reported a valid DMG checksum and `unzip -tq` reported no ZIP errors.
The temporary DMG mount was detached after testing. No system installation was replaced.

Final SHA-256 checksums (also in `desktop/dist/SHA256SUMS.txt`):

```text
9729062b674b51f5770471ec33ec3f4e9e9159ac36e32e145c2b286b835b7748  ResearchAssistant-0.1.0-arm64.dmg
1440f75d71610ca7faeecac6ece6a4ff8c004990cf06b26dd6836a04a1cd9152  ResearchAssistant-0.1.0-arm64-mac.zip
```

macOS test artifacts are complete. The unchecked Windows and release-signing gates above
remain open; no actual Windows artifact or clean Windows install is claimed.

## Windows CI path-fixture correction — 2026-09-06

The first Desktop Phase 1 workflow passed macOS (job 101520646091) and failed
Windows during Python regressions (job 101520645876), before packaging. Windows
reported 907 passed / 2 failed / 2 existing skips. Both failures were invalid test
inputs: a filename containing Windows-forbidden `?`, and a Unix `/tmp` output path.

The database fixture retains spaces, `#` and `%` on every platform and additionally
retains `?` on POSIX. All read-only/foreign-key/query-only assertions remain intact.
The environment example now leaves the smoke output blank with OS-specific absolute
path examples; the offline test explicitly supplies its platform-native temporary
output path, just as it explicitly supplies the credential and approval gates.
The absolute-path validator and execution gates remain unchanged.

Validation: 43 targeted tests passed; full pytest passed 909 tests with 2 existing skips.
Ruff lint/format and Git whitespace checks passed. A fresh Windows workflow run after committing
and pushing this correction is still required; Windows packaging/install validation
and signing gates remain open. Existing macOS runtime artifacts are unaffected.
