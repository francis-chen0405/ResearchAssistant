# Desktop application

The app was replaced with a verified local build from `20bf6a2` on 2026-10-02, including
the ALPR equity, validator and repository-organization changes; see the
[current task's delivery results](../.agent/plans/validator-and-current-docs-2026-10-02.md#user-authorized-commit-and-local-redelivery).
The current local installer is `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`.
The latest public download is still the September 28 test release built from `ac49404`;
it does not contain the October fixes. The older `desktop/dist` paths below describe
historical artifacts. Saved research and credentials were preserved.

Current delivery target is a directly downloadable Apple Silicon Mac test build; no
Mac App Store submission is planned. Windows release work is deferred.
The [Mac/cache-pricing plan](../.agent/plans/mac-release-cache-pricing.md) tracks this
delivery. Without a Developer ID certificate, its DMG/ZIP is an unsigned test release.
Downloading outside the App Store still uses macOS Gatekeeper checks: Apple describes
[Developer ID and notarization](https://developer.apple.com/developer-id/) for that route.
No membership is required to build or share the unsigned test files; they are not a
signed, notarized public release. The installer declares macOS 14+, but minimum-OS
and clean-machine acceptance still require tests on those systems.

Phase 1 implementation and its release checks remain in `.agent/plans/phase-1-desktop.md`.
Historical September unsigned Mac build verification is tracked in
[the 2026-09-28 record](../docs/verification/mac-current-build-2026-09-28.md).
That build includes the then-current database-integrity changes and GPT-6 model choices.
The user app was subsequently replaced with the verified unsigned build on 2026-09-29;
see the [testing handoff](../docs/testing-handoff-2026-10-01.md). Earlier adaptive-search,
Phase 2, and Phase 3 records remain historical evidence for their specific builds and checks.
This is a local application: provider calls run in its bundled Python backend. There
is no hosted application backend and no automatic paid credential test.

## Installation and data

The macOS test build is a DMG/ZIP containing ResearchAssistant.app. Copy the app to
Applications. Windows builds use a per-user NSIS installer. End users do not install
Python, Node, pnpm or Docker. Updates replace the application bundle, not its data.
Unsigned test artifacts are not a signed/notarized public release.
The September 28 DMG and ZIP were saved under `desktop/dist/mac-current-20260928/`
with checksums and a short readme. All four files are available from the
[unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928).
That public release was built from `ac49404` and lacks the October source fixes; it is
not the current local app. A recipient of an unsigned download may encounter Gatekeeper
restrictions.

The current delivery target is Apple Silicon macOS 14+. The local candidate checks were
run on macOS 26.6.2 arm64; clean-machine installation and actual macOS 14 verification
remain open. Windows packaging support exists, but Windows release work is deferred.
Phase 2 Windows build/runtime evidence is historical and does not verify the current
version. Intel macOS and Windows ARM64 are not claimed as verified targets.

Persistent data:

- macOS: `~/Library/Application Support/ResearchAssistant/`.
- Windows: `%LOCALAPPDATA%/ResearchAssistant/`.
- `live-runs.sqlite3`: default research history.
- `preferences.json`: ordinary UI settings, model route overrides and prices only.
- `acquisition/`: application-owned Wigolo data; bundled browser resources are read-only.
- `imports/`: explicitly imported historical databases.

Writable runs and resumes migrate compatible databases to schema 16. Schema 14 added nullable
cached/uncached input-token fields; schema 15 adds nullable cache-write tokens/cost basis,
and schema 16 protects same-run ownership and referenced keys. Existing records retain unknown cache
usage. History, status inspection, and export are read-only and support schemas 7–16
without migrating them; incompatible source or executable identity still blocks resume.
See the [database-review record](../.agent/plans/database-review-2026-10-03.md)
for the migration and compatibility evidence.

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
python -m pip install -c desktop/constraints.txt -r requirements.txt -r desktop/requirements-build.txt httpx2 pytest ruff
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
Python source hashing includes the root compatibility entries and complete
researchassistant/agents/providers/frontend surface and prompts, plus the frozen executable
bytes. Runtime data/credentials are never build inputs.

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

`.github/workflows/desktop.yml` defines macOS and Windows builds, retaining unsigned test
artifacts without publishing releases. Workflow configuration alone is not evidence that
the current version built or ran on either target. Signing/notarization and clean-machine
installer verification must be performed separately before claiming a signed, broadly
distributed public release.

Packaging references: [Tauri sidecars](https://v2.tauri.app/develop/sidecar/),
[Electron security](https://www.electronjs.org/docs/latest/tutorial/security),
[GitHub runner targets](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

## Historical Phase 2 source compatibility

At the Phase 2 verification point, contract, schema, fixture and application-runtime modules
were root-level files, with extracted `frontend/live_*` helpers covered by the then-current
recursive packaging and identity rules. The current organization is under `researchassistant/`;
see [architecture](../ARCHITECTURE.md) for canonical imports and ownership. Rebuild the bundle
after source changes. A changed source/executable fingerprint requires a new research run under
the exact compatibility gate; historical records remain available for inspection and export.
Historical inspection/export was preserved; incompatible resume failed explicitly.
This records the Phase 2 result only. Phase 3, adaptive-search, audit-maintenance, and
database-integrity work followed it; use the dated verification records for each result.

On this OneDrive-backed checkout, macOS disk-image creation returned `Operation not
supported by device` when output was inside the synced directory. The same unchanged
builder succeeded with a local temporary output directory:

```sh
CSC_IDENTITY_AUTO_DISCOVERY=false npm run package --prefix desktop -- --config.directories.output=/private/tmp/researchassistant-phase2-final
```

This is a developer build-location workaround, not an application runtime-path change.
Do not embed this temporary path or the checkout path in application code.

## Phase 3 frontend verification and upgrade behavior

After exporting `web/out`, run `node desktop/frontend-smoke.cjs`,
`node desktop/frontend-poll-smoke.cjs`, and
`node desktop/configuration-race-smoke.cjs`. They use the existing acquisition
Playwright installation and mocked application APIs; no provider calls are made.
The interaction smoke writes screenshots to `desktop/build/phase3-screenshots/`.
Desktop CI runs all three on both target platforms.

`desktop/upgrade-smoke.py PREVIOUS_RESOURCES CURRENT_RESOURCES` tests isolated historical
read/export, preferences and cross-executable native credentials. On macOS unsigned
updates may cause a Keychain permission prompt. That OS prompt expects the Mac login/keychain
password, never a provider API key. Do not weaken ACLs to bypass it. An earlier cross-version
credential prompt was denied, then the user explicitly authorized the unchanged isolated
upgrade smoke on 2026-09-08; it passed native credential persistence, preferences and history
checks. Same-build vault persistence and old-to-new non-secret data remain separate checks.
See [Phase 3 verification](../docs/verification/phase-3.md) and
[adaptive-search verification](../docs/verification/adaptive-search-reliability.md) for
actual results and limitations.

## Upgrade diagnostics

Run the upgrade check against a previous resource directory and a freshly rebuilt
current directory. Both must contain distinct backend executables. The test retains
all native-credential, preference-migration, exact historical-report and byte-identical
database assertions. It waits for authenticated health after each startup announcement;
announcing an address alone does not mean the API is accepting requests.

For a previous executable that supports schema 13 but predates schema 14, append
`--previous-schema13`. The isolated fixture is generated by current code, then its
null cache-usage columns, schema-16 provenance guards and migration records above 13
are removed atomically so the preceding executable can read it. The converter supports
generated schemas 14–16 and refuses to discard populated cache usage or cost-basis metadata. The
normal invocation continues to test a current-schema fixture.

Both output pipes are drained continuously. Startup and shutdown failures report the
launch index, elapsed time, exit status, last known phase and stderr character count.
New self-test builds emit fixed phase labels, including credential access and identity
calculation; older builds report that phase information is unavailable. Raw child
output and bootstrap values are not logged. The startup deadline remains 45 seconds
and shutdown remains 100 seconds. A vault permission prompt still requires an OS
response; the harness neither grants access nor silently skips credential checks.

The legacy Streamlit interface is optional: install `requirements-legacy.txt` from the
repository root only if you use it. The desktop runtime does not require Streamlit.
