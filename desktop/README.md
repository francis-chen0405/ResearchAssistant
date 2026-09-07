# Desktop application

Phase 1 implementation and its release checks remain in `.agent/plans/phase-1-desktop.md`.
Current cleanup and verification are tracked in `.agent/plans/phase-2-cleanup.md`.
This is a local application: provider calls run in its bundled Python backend. There
is no hosted application backend and no automatic paid credential test.

## Installation and data

The macOS test build is a DMG/ZIP containing ResearchAssistant.app. Copy the app to
Applications. Windows builds use a per-user NSIS installer. End users do not install
Python, Node, pnpm or Docker. Updates replace the application bundle, not its data.
Unsigned test artifacts are not a signed/notarized public release.

Targets for this phase: Apple Silicon macOS 14+ and x64 Windows 11. Local verification
is on macOS 26.6.2 arm64. Native Windows build/runtime evidence is tracked in the Phase 2 verification record.
Clean-machine installation and minimum-OS verification remain release gates until the
corresponding artifact has actually been installed and tested.
Intel macOS and Windows ARM64 are not claimed as verified targets.

Persistent data:

- macOS: `~/Library/Application Support/ResearchAssistant/`.
- Windows: `%LOCALAPPDATA%/ResearchAssistant/`.
- `live-runs.sqlite3`: default research history.
- `preferences.json`: ordinary UI settings, model route overrides and prices only.
- `acquisition/`: application-owned Wigolo data; bundled browser resources are read-only.
- `imports/`: explicitly imported historical databases.

Keys use macOS Keychain or Windows Credential Manager directly. Existing macOS service
names/account are retained. There is no configurable keyring or plaintext fallback.
Provider setup saves or replaces nonempty key inputs, clears password fields, reports
saved presence, and removes individual keys. Presence does not establish live validity.
Legacy non-secret route/price settings are read from Keychain and copied into preferences
on first load. Existing browser-only provider preferences must be selected once in the
new desktop interface; browser storage cannot be read from this isolated desktop origin.

To preserve old checkout history, open Advanced, enter the old SQLite file path in
SQLite database, and choose **Import this database into app storage**. Finish active
research using that file first. Import uses a read-only source connection, the shared
process lock and SQLite backup, then validates every run manifest and database integrity.
It creates a new file and never overwrites or migrates the source. Source-adjacent lock
creation must be permitted. Historical inspection/export stays separate from explicit
resume: a source/executable/prompt fingerprint change still rejects incompatible resume.

## Ownership and recovery

The shell admits one desktop instance per user. Backend and acquisition use separate
loopback ports. A random per-launch bearer token is supplied over an inherited pipe;
the shell injects it only into requests from its own window to that backend origin.
Renderer JavaScript never receives the token. Unexpected origins/hosts are rejected;
provider calls and native credential operations remain in Python.

The renderer uses a sandbox, context isolation, no Node integration, denied permissions,
a restrictive content security policy and HTTPS-only external link opening. The API
returns generic validation errors rather than raw password inputs.

Only application-owned acquisition processes are stopped. Windows uses a kill-on-close
job for descendants; macOS uses an owned process group and shell cleanup after backend
exit. Shell pipe closure requests backend shutdown even if the shell exits unexpectedly.
Shutdown cancels at existing pipeline boundaries and waits up to 90 seconds. A provider
request already in progress can run to its deadline. If it cannot finish, persisted
unknown-outcome reservations remain charged and the backend exits. Reopen History to
inspect interrupted work; resume remains explicit and subject to the existing fingerprint
and budget checks. There is no automatic retry or budget refund on restart.

## Build and verification (developers/CI only)

Use Python 3.12 and Node 24.18.0 on the target OS/architecture. Install the project and
build requirements using `desktop/constraints.txt`; install web dependencies with the
committed pnpm lock and desktop dependencies with the committed npm locks.

```sh
python -m pip install -c desktop/constraints.txt -r requirements.txt -r desktop/requirements-build.txt pytest ruff
pnpm --dir web install --frozen-lockfile
npm ci --prefix desktop
node desktop/node_modules/electron/install.js
python desktop/build.py
python desktop/smoke.py desktop/build/resources
node desktop/ui-smoke.cjs
npm run package --prefix desktop
```

Artifacts are written under `desktop/dist/`; intermediate runtimes under `desktop/build/`
are ignored by Git. The build downloads a checksum-verified standalone Node distribution,
installs Wigolo 0.2.1 from its npm lock, and includes its exact Playwright Chromium build.
It exports the existing Next.js page and freezes Python with source files and prompts.
Python source hashing includes the complete root/agents/providers/frontend surface and
prompts, plus the frozen executable bytes. Runtime data/credentials are never build inputs.

Wigolo uses native better-sqlite3/sqlite-vec/embedding dependencies and Playwright. It
runs under bundled standalone Node to preserve the native ABI, not Electron's Node ABI.
The research adapter retains its approved acquisition behavior; Chromium is available
for the existing bounded JS fallback. SearXNG/Docker is not required for acquisition.
Bundled upstream licenses, including Wigolo's AGPL license, remain with their packages.

The frozen smoke uses an empty developer-tool PATH, an unrelated temporary working
folder, isolated native-vault service names and temporary application data. It verifies
health/auth, static UI, native credential round-trip and restart persistence, preference
persistence, exact packaged identity, and owned Wigolo startup/health/shutdown. It makes
no paid provider calls. The window smoke additionally checks renderer isolation, actual
page loading and empty password controls. CI runs these before installer creation.

`.github/workflows/desktop.yml` builds on macOS and Windows, retaining unsigned test
artifacts without publishing releases. Signing/notarization and clean-machine installer
verification must be performed separately before distribution. Windows execution is not
inferred from the presence of a workflow or from a successful macOS build.

Packaging references: [Tauri sidecars](https://v2.tauri.app/develop/sidecar/),
[Electron security](https://www.electronjs.org/docs/latest/tutorial/security),
[GitHub runner targets](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

## Phase 2 source compatibility

Root contract, schema, fixture and application-runtime modules and the extracted
`frontend/live_*` helpers remain covered by the existing recursive packaging and identity
rules. No new dependency or resource root was introduced. Rebuild the bundle after source
changes and start a new research run: the exact source/executable fingerprint changes.
Historical inspection/export is preserved; incompatible resume still fails explicitly.
See [current verification](../STATUS.md) for actual target results. Phase 3 UI work is not
part of this cleanup.

On this OneDrive-backed checkout, macOS disk-image creation returned `Operation not
supported by device` when output was inside the synced directory. The same unchanged
builder succeeded with a local temporary output directory:

```sh
CSC_IDENTITY_AUTO_DISCOVERY=false npm run package --prefix desktop -- --config.directories.output=/private/tmp/researchassistant-phase2-final
```

This is a developer build-location workaround, not an application runtime-path change.
Do not embed this temporary path or the checkout path in application code.
