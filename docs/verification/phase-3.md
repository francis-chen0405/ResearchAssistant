# Phase 3 verification

Development branch: `codex/phase-3-frontend-settings`, clean completed Phase 2 base.
Delivery branch: local `master`, fast-forwarded at the user’s request; no remote push.
Local target: Apple Silicon macOS. No paid provider calls or public publishing.

## Implementation

- Shared ivory/grid design system, floating navigation, welcome and research composer.
- Reusable workspace frame, progress path, status badges, evidence tiles and native
  accessible dialog; explicit local-only deterministic interactive example data.
- Visible direction/profile/model budget, source preferences, source/evidence inspection,
  limitations, cancellation, saved history and validated brief copy/download.
- Native credential save/replace/remove, explicit model-list connection checks and
  honest source-key presence checks. No new dependency or integration.
- Strict versioned Standard profile keeps the established MiMo/Luna roles, validated
  completion contracts, maintained conservative price caps and offline initial-call
  reservation check. Run-local resolution never mutates saved credentials or prior runs.
- Existing source fingerprint, frozen configuration, database schema and historical
  validation/export/immutability boundaries remain intact.

## Checks

- Full Python suite: **942 passed, 2 existing opt-in skips**, one pre-existing warning.
  Final Ruff lint/format, TypeScript and ESLint also pass after the Keychain guidance fix.
- Ruff lint/format, TypeScript, ESLint, static production export and diff check passed.
- `desktop/frontend-smoke.cjs` passed against the built export with every application
  API intercepted. Covers preview ready/active/review/complete/error/retry; seven
  rendered transient password fields; save/check/remove; model/direction/budget input;
  startup/progress/cancellation; history; actual downloaded/copied brief contents;
  detailed quotation and support/challenge inspection; keyboard dialog containment,
  Escape dismissal, reduced motion, and 1280/1024/800/480-pixel widths.
- Visual inspection uses screenshots from `desktop/build/phase3-screenshots/`.
  Dialog focus containment, narrow navigation, decorative accessible labels and
  prominent result limitations were corrected during QA.
- Full native macOS resource build passed using the existing pinned Node, Wigolo,
  Chromium, static Next.js and PyInstaller process.
- Frozen resource smoke passed: native vault, durable preferences, authenticated
  local API, owned acquisition start/health/stop, restart and cleanup.
- Actual Electron window smoke passed: page load, renderer isolation, authenticated
  API, seven empty password fields, duplicate-instance handling and clean shutdown.
- Phase 2 to Phase 3 preferences and historical data passed a separate isolated data-only
  check: migrated profile default, retained budget, identical validated historical brief
  and byte-identical history database, with distinct executable identities.
- Cross-version native credential check **not verified**: the user denied the macOS
  Keychain prompt. OS status -128 indicates cancellation. Both backends were ad hoc signed
  with different identifiers and no TeamIdentifier. The prompt expects a Mac login/keychain
  password, not a provider API key. The app now explains this and returns sanitized access
  guidance on denial; the regression confirms secrets and native error details are not echoed.
  Native security was not weakened and the denied cross-version prompt was not repeated.

Two existing source-text UI tests were updated to follow the extracted provider
component and renamed controls. The seven-field/security assertions are retained and
supplemented by rendered browser interaction tests; no acceptance threshold was lowered.
The pre-existing Starlette/httpx deprecation warning remains.

## Platform/release limits

No native Windows runtime is available here. The inspected GitHub browser session was
signed out and no remote build was dispatched. Publishing this branch to
its public repository would also exceed the user's no-public-publishing boundary.
A new Windows installer and Windows upgrade test remain pending an authorized native
runner. Existing Phase 2 Windows artifacts are not represented as Phase 3 artifacts.
Signing/notarization, clean-machine installation and minimum-OS checks remain release gates.

## Keychain investigation reference

Apple explains [designated requirements and app identity](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements)
and [Keychain access prompts](https://support.apple.com/en-ca/guide/keychain-access/kyca1243/mac).
The observed identity change explains why an unsigned replacement can request renewed
access; it is not evidence that a provider rejected the supplied API key.

## Local macOS artifacts

Unsigned Apple Silicon test build, application version 0.1.0; not a public release:

- `desktop/dist/phase3/ResearchAssistant-0.1.0-arm64.dmg`
- `desktop/dist/phase3/ResearchAssistant-0.1.0-arm64-mac.zip`
- `desktop/dist/phase3/SHA256SUMS.txt`
- `desktop/dist/phase3/screenshots/` (17 screenshots of preview, research, settings,
  evidence, error and responsive states).

Final DMG checksum verification and ZIP integrity validation passed. The mounted DMG
passed native vault/persistence/acquisition and actual Electron window/security/shutdown
smokes. Its first native launch exceeded the unchanged 45-second startup timeout; a
retry passed with the same timeout and assertions. Cold-launch timing remains a
clean-machine verification concern.
SHA-256:

```text
d231c247201766ab3893202ba5acec3a9c790c78fd341d3cff20779b358d6906  ResearchAssistant-0.1.0-arm64.dmg
c2af252700e2f29eee098e55db938a24db05c22f2df3fafb5a0251eca75cfd4a  ResearchAssistant-0.1.0-arm64-mac.zip
```

The existing Phase 2 artifacts are preserved in their prior locations. No new Windows
artifact is claimed. Installer signing/icon/version distribution preparation remains
outside this unsigned test delivery; the existing Electron default icon is retained.

## 2026-09-08 authorized upgrade verification

The user explicitly authorized another isolated test. The unchanged
`desktop/upgrade-smoke.py` passed against the preceding Phase 2 frozen app and the new
Phase 3 resources: native credential persistence, migrated preferences, identical
validated historical brief and byte-identical history database, with distinct executable
identities. This supersedes the earlier unverified credential result after cancellation;
no assertions, timeouts or vault access controls were weakened. Signed distribution and
Windows verification remain separate outstanding gates.

Inspection also confirmed `/Applications/ResearchAssistant.app` still contained the old
frontend. The new Phase 3 DMG was opened for the user to replace the installed application.
Installation/replacement by the user has not yet been verified.

## 2026-09-08 warm palette and automatic preview

User-requested visual refinement: coral/apricot/green/plum replaces blue workspace
surfaces; compact side-by-side desktop home; repetitive caption/footer copy removed.
Only Nomu's initial viewport was visually inspected, without scrolling.

- 942 Python tests passed, 2 existing skips and one existing warning.
- Ruff lint/format, ESLint, TypeScript, static production build and diff check passed.
- Offline browser acceptance now verifies automatic ready/active/review/complete/error/
  recovery transitions without playback buttons, hover/focus pause, and static completed
  reduced-motion presentation. All original credential, startup, cancellation, history,
  quotation, clipboard/export, keyboard and resize checks remain.
- Home fits vertically at 1440/1280/1024 desktop widths and 768px height; all automatic
  states fit at 1280×860. Narrow 800/480 layouts remain readable with no horizontal overflow.
- Screenshots were inspected for home, completed preview and the actual active workspace.
- The existing frozen backend is reused byte-for-byte; only the static frontend changes.
  No credential migration or research runtime change requires another Keychain test.

Revised unsigned macOS artifacts are delivered separately under `desktop/dist/phase3-colors/`;
the previous Phase 3 installer remains intact. Windows and public-release gates remain.

Final macOS verification: DMG checksum and ZIP integrity passed. The packaged Electron
window test passed (frontend load, authentication, empty password fields, renderer
isolation, duplicate exclusion and normal shutdown). The first launch concurrent with
packaging timed out; the unchanged test passed after packaging completed. Backend
executable bytes match the previous Phase 3 artifact exactly.

SHA-256 for `desktop/dist/phase3-colors/`:

```text
10d942def84af5abf8798406903f68eb677292cef840e28da04b06bf06c18501  ResearchAssistant-0.1.0-arm64.dmg
93ef31dc14733110663a0ee6aaf88e129619cbb1981237b50969ff83002a2a63  ResearchAssistant-0.1.0-arm64-mac.zip
```
