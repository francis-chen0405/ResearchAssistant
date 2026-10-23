# Desktop application

[STATUS](../docs/project/STATUS.md) owns current-source,
installed-app and public-download provenance. The
[October 21 repair/install record](../docs/verification/selection-coverage-repairs-2026-10-21.md)
retains the current local unsigned build's checks and saved-data preservation evidence.
The source layout described here is the backend/frontend consolidation; rebuilding
resources alone does not replace the installed application.

Current delivery target is a directly downloadable Apple Silicon Mac test build; no
Mac App Store submission is planned. Windows release work is deferred.
The [Mac/cache-pricing plan](../.agent/plans/mac-release-cache-pricing.md) tracks this
delivery. Without a Developer ID certificate, its DMG/ZIP is an unsigned test release.
Downloading outside the App Store still uses macOS Gatekeeper checks: Apple describes
[Developer ID and notarization](https://developer.apple.com/developer-id/) for that route.
No membership is required to build or share the unsigned test files; they are not a
signed, notarized public release. The installer declares macOS 14+, but minimum-OS
and clean-machine acceptance still require tests on those systems.

Phase 1 implementation and its release checks remain in
[the retained desktop plan](../.agent/plans/phase-1-desktop.md).
Historical September unsigned Mac build verification is tracked in
[the 2026-09-28 record](../docs/verification/mac-current-build-2026-09-28.md).
That build includes the then-current database-integrity changes and GPT-6 model choices.
The user app was subsequently replaced with the verified unsigned build on 2026-09-29;
see the [testing handoff](../docs/testing-handoff-2026-10-01.md). Earlier adaptive-search,
Phase 2, and Phase 3 records remain historical evidence for their specific builds and checks.
This is a local application: provider calls run in its bundled Python backend. There
is no hosted application backend and no automatic paid credential test.

## Installation and data

### Desktop shutdown deadline (current source)

The first quit closes the owned backend's stdin exactly once. Python keeps its
cooperative cancellation and **90-second controller drain** before service teardown.
Electron has one **150,000 ms (150 seconds)** outer shutdown deadline from that first
quit, including quits during startup/failure. Repeated quits never extend it. The
additional **60 seconds** allow loopback-server shutdown, SQLite/worker cleanup and
acquisition teardown (normally up to 25 seconds including output-reader joins).
An engine that exits sooner releases pipes/timers and exits the shell immediately;
renderer unload cannot veto that accepted quit. Failures emit fixed shell diagnostics;
native error dialogs are excluded because even Promise-returning parentless dialogs
can defer quit on macOS.

Startup, from backend spawn through health and window loading, is bounded separately
at **30,000 ms**. A startup stall then enters the same EOF-first shutdown path, giving
an exact maximum configured spawn-to-shell-exit window of **180,000 ms (180 seconds)**.
No pending health request, late startup response or window load can reopen the shell.
These are application watchdog limits under a running event loop/OS, not hard
real-time guarantees during OS suspension or kernel failure.

At 150 seconds, POSIX sends `SIGKILL` only to the newly created backend process group
and still-owned acquisition groups reported over its private stdout pipe. Acquisition
launchers initially inherit the backend group. Electron records ownership before
acknowledging a fresh PID/request pair on stdin; the backend then releases the launcher's
gate to detach and execute. Confirmation has a 10-second limit; EOF, timeout or a failed
pipe terminates the launcher. Quit never acknowledges new detachment. A delayed report
or crashed backend therefore leaves the launcher covered by the backend group.
Start also waits up to 10 seconds for the exact acquisition group to exist before
returning, so immediate stop always targets its established group.
Revoked owners are removed. Root exit also retires orphan members of its owned group.
Windows terminates the owned `ChildProcess` handle. Before bootstrap, Python attaches
itself to a non-inheritable kill-on-close Job Object; all descendants inherit that
ownership, including multiple acquisition generations and nested acquisition Jobs.
Denied Job assignment fails startup before data/vault access or child creation.
Windows never uses PID/name scans, `taskkill`, ports or unrelated services as targets.
The fallback exits Electron with status 1 without waiting for child/pipe events.

Forced shutdown never updates saved run status, releases unknown-call reservations,
deletes SQLite/WAL files or claims research completion. Saved work uses the existing
SQLite recovery and exact resume-compatibility rules; an unknown provider outcome
still needs explicit recovery. [Prompt 17](../docs/verification/windows-ci-durability-2026-10-13.md)
records native Windows Server 2025/NTFS nested-Job checks and the exact current
packaging/forced-Electron results. Windows client acceptance, physical power-loss
durability and actual minimum-macOS testing remain separate gates.

Offline checks: `npm --prefix desktop test`,
`npm --prefix desktop run smoke:shutdown`, and
`python -m pytest tests/test_desktop_shutdown.py tests/test_desktop_ownership.py`.
`node desktop/shutdown-electron-smoke.cjs`
also checks real Electron forced quit against disposable POSIX stubs. Native POSIX smoke uses
disposable stubs and the actual service manager (including delayed ownership reporting),
uses an accelerated test clock, checks unrelated-process
survival and stream cleanup, and never opens a user database. Deterministic tests use
the exact production 150-second constant. Frozen backend/UI smoke commands below
use temporary data; [the shutdown verification record](../docs/verification/desktop-shutdown-2026-10-10.md)
owns the preceding results. On Windows, `python desktop/windows-shutdown-electron-smoke.py`
uses real Electron, production main, a test clock and disposable native Job-owned
stubs; [Prompt 17](../docs/verification/windows-ci-durability-2026-10-13.md) owns its
actual runner result and platform limits.

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
Phase 2 Windows build/runtime evidence is historical. The
[Prompt 17 record](../docs/verification/windows-ci-durability-2026-10-13.md) binds
new Windows Server 2025/NTFS CI/native results to exact source/artifact hashes;
it does not authorize a Windows release or establish consumer Windows acceptance.
Intel macOS and Windows ARM64 are not claimed as verified targets.

Persistent data:

- macOS: `~/Library/Application Support/ResearchAssistant/`.
- Windows: `%LOCALAPPDATA%/ResearchAssistant/`.
- `live-runs.sqlite3`: default research history.
- `preferences.json`: ordinary UI settings, model route overrides and prices only.
- `acquisition/`: application-owned Wigolo data; bundled browser resources are read-only.
- `imports/`: explicitly imported historical databases.

In current source, writable runs and resumes migrate compatible databases to schema 18.
Installed-build schema provenance is recorded in [STATUS](../docs/project/STATUS.md).
Schema 14 added nullable
cached/uncached input-token fields; schema 15 adds nullable cache-write tokens/cost basis,
schema 16 protects same-run ownership and referenced keys, and schema 17 adds measured
history/evidence indexes. Schema 18 extends only v2 admission rounds through four,
preserving historical constraints and records. Existing records retain unknown cache
usage. History, status inspection, and export are read-only and support schemas 7–18
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
a restrictive content security policy and credential-free HTTP(S) external link opening. The API
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
build requirements using `desktop/constraints.txt`; install renderer dependencies with the
committed pnpm lock and desktop dependencies with the committed npm locks.
Run the following from the repository root in the development environment described
in [README](../README.md#install-and-develop).

```sh
python -m pip install -c desktop/constraints.txt -e "./backend[dev]" -r desktop/requirements-build.txt
python scripts/verify_distribution.py --constraints desktop/constraints.txt
pnpm --dir frontend install --frozen-lockfile
npm ci --prefix desktop
node desktop/node_modules/electron/install.js
python desktop/build.py
python desktop/smoke.py desktop/build/resources
node desktop/ui-smoke.cjs
CSC_IDENTITY_AUTO_DISCOVERY=false npm run package --prefix desktop
```

Artifacts are written under `desktop/dist/`; intermediate runtimes under `desktop/build/`
are ignored by Git. The build downloads a checksum-verified standalone Node distribution,
installs Wigolo 0.2.1 from its npm lock, and includes its exact Playwright Chromium build.
Staging applies the reviewed `acquisition/cache-policy.mjs` connection policy to
the exact hash-pinned upstream database module. Replacement writes fire FTS delete
triggers; an inconsistent derived URL index is rebuilt only after core integrity
passes. Content, vectors and migration records are preserved. Unreviewed upstream
bytes stop the build. The installed October 9 cache findings and disposable-copy
repair evidence are in [Mac delivery verification](../docs/verification/mac-delivery-gates-2026-10-13.md).
It exports the existing Next.js page and freezes Python with source files and the canonical
`backend/src/researchassistant/prompts/` resources. All 18 prompts and the PDF font must be present;
the frozen identity rejects incomplete resources.
Python source hashing includes the backend-owned installed facades and complete
researchassistant/agents/providers/frontend surface and prompts, bundled PDF font bytes, plus the frozen executable
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
artifacts without publishing releases. Windows packaging/frozen/installer verification
runs only through **Actions → Desktop Phase 1 → Run workflow**, at the user’s request.
Automatic pushes/PRs retain Windows regressions/native storage and the macOS desktop
checks and packaging. The Windows desktop matrix entry has been removed at the user's
request. Workflow configuration alone is not evidence that
the current version built or ran on either target. Its independent Windows job records
OS/NTFS and JUnit evidence for actual ACL/access-denial, file/link, generated-data crash,
native vault and process checks. The installer smoke is restricted to disposable
GitHub Windows runners: it retrieves a SHA-bound previous CI installer, interrupts an
owned upgrade, repairs by reinstalling, then exercises installed frozen/window and
generated-data/vault upgrade checks. CI status and exact results are in
[Prompt 17 verification](../docs/verification/windows-ci-durability-2026-10-13.md).
Process crashes do not establish physical power-loss durability; Windows directory
flush ordering remains unverified. Signing/notarization and clean-machine
installer verification must be performed separately before claiming a signed, broadly
distributed public release.

Packaging references: [Tauri sidecars](https://v2.tauri.app/develop/sidecar/),
[Electron security](https://www.electronjs.org/docs/latest/tutorial/security),
[GitHub runner targets](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

## Local installation and public distribution

The commands above produce local unsigned test artifacts. For a local Mac installation,
first smoke-test the candidate bundle with isolated data, quit the running app, then
replace `/Applications/ResearchAssistant.app` with the candidate. Saved data remains
in the application-data directory above. Verify the installed backend and window;
the [October 9 record](../docs/verification/current-app-install-2026-10-09.md) is evidence
for that delivery, not for a newly rebuilt candidate. Keychain access may require the
user's normal OS response. Never copy test data into saved research storage.

Signed public distribution is a separate delivery task: configure Developer ID signing
and notarization, validate the actual installer on clean/minimum-OS systems, then publish
the verified artifacts and checksums. `npm run package` uses `--publish never`;
neither this command nor the CI artifact upload publishes a GitHub release.
Use [STATUS](../docs/project/STATUS.md) for the actual delivery gates and
[the test map](../tests/README.md#desktop-and-renderer-checks) for source checks.

Developer ID inputs are prepared in `release-signing.cjs` and
`release-entitlements.plist`, validated against the pinned builder schema. This
opt-in config refuses missing certificate-name/notary-profile inputs, requires
signing, enables hardened runtime/JIT and requests notarization. Use an existing
Developer ID identity in the local Keychain (`CSC_NAME`) and a locally stored
`APPLE_KEYCHAIN_PROFILE`; never put private keys or account passwords in this
repository or chat. No valid identity was available for the October 13 candidate.
See the verification record for the exact secure-local commands and remaining
clean-machine/minimum-OS tests. Signed runtime acceptance remains unverified until
those inputs exist; configuration alone does not establish it.

## Historical Phase 2 source compatibility

At the Phase 2 verification point, contract, schema, fixture and application-runtime modules
were root-level files, with extracted `frontend/live_*` helpers covered by the then-current
recursive packaging and identity rules. The current organization is under `researchassistant/`;
see [architecture](../docs/project/ARCHITECTURE.md) for canonical imports and ownership. Rebuild the bundle
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

After exporting `frontend/out`, run `node desktop/frontend-smoke.cjs`,
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
null cache-usage columns, schema-16 provenance guards, schema-17 query indexes and migration records above 13
are removed atomically so the preceding executable can read it. Schema 18
first restores the historical three-round admission constraint on the generated fixture
and refuses populated Round-4 admissions. The converter supports
generated schemas 14–18 and refuses to discard populated cache usage or cost-basis metadata. The
normal invocation continues to test a current-schema fixture.

Both output pipes are drained continuously. Startup and shutdown failures report the
launch index, elapsed time, exit status, last known phase and stderr character count.
New self-test builds emit fixed phase labels, including credential access and identity
calculation; older builds report that phase information is unavailable. Raw child
output and bootstrap values are not logged. The startup deadline remains 45 seconds
and shutdown remains 100 seconds. A vault permission prompt still requires an OS
response; the harness neither grants access nor silently skips credential checks.

The legacy Streamlit interface is optional: install `backend/requirements-legacy.txt` from the
repository root only if you use it. The desktop runtime does not require Streamlit.

The checkout transition launcher `desktop/Launch ResearchAssistant.command` has a separate
45-second monotonic readiness deadline. Each API/web request receives at most two
seconds and the remaining deadline. Failed readiness reports the existing startup
error and stops only children started by that launcher. This does not change the
bundled Electron startup/shutdown watchdogs above.
