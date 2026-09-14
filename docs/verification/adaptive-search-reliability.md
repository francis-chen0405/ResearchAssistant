# Adaptive-search reliability verification — 2026-09-14

User-authorized correction after Phase 3, delivered locally on master. No paid model,
search, or acquisition calls were made; no remote publication or dependency change.

## Verified behavior

- Exact-claim default on fresh initial planning; complete typed plan persists atomically
  with its relational projection and survives readback/restart.
- Strict fresh early-round coverage policy; round-aware Gap instructions; semantic Gap
  identities remain stable. Supporting-only does not enable challenging research.
- At most two physical Search Agent attempts per Round 2/3, including the first.
  Rejected candidates and typed diagnostics persist before any search executes. Repair
  receives original constraints and rejection feedback; every replacement is fully validated.
- Adapter schema/JSON/truncation failures can use the one repair; authentication and
  transport failures cannot. Cancellation and fresh call/token/cost reserves are enforced.
- Persisted accepted outcomes recover without another call. Unknown outcomes and exhausted
  attempts never silently replay. Physical-call records link to planning attempt IDs.
- Fresh final output retains known gaps despite source relevance, carries strategy coverage,
  and rejects gap removal or coverage drift. Old stored outputs retain legacy semantics.
  Nonempty-gap persisted output revalidation is covered directly.
- Round 4 still requires its existing Governor authority, call limits and evidence-based
  reconciliation. Per-source analysis allowances and global ceilings remain unchanged.

## Checks

| Check | Result |
| --- | --- |
| Full Python suite | 959 passed, 2 existing skips; one existing Starlette deprecation warning |
| Ruff check and format check | Passed, 146 Python files formatted |
| Git whitespace check | Passed |
| Frontend ESLint / TypeScript / static production build | Passed |
| Offline browser acceptance | Passed, including failed repair disclosure and coverage display |
| Visual result review | Passed; `desktop/build/phase3-screenshots/adaptive-search-limitations.png` |
| Frozen backend build | Passed |
| Native smoke | Passed: authenticated local API/UI, isolated test vault cleanup, settings persistence, owned Wigolo lifecycle |
| Packaged window smoke | Passed: renderer isolation, authenticated requests, seven empty credential fields, duplicate exclusion, normal shutdown |
| Installed window smoke | Same checks passed against `/Applications/ResearchAssistant.app` with isolated data |
| DMG and ZIP integrity | DMG checksum valid; ZIP reported no compressed-data errors |

The new regressions cover duplicate rejection/recovery, budget reservation and refresh,
cancellation, restart at persistence boundaries, adapter error classification, exact-claim
defaults, legacy reporting, and complete supporting-only production paths. Existing invalid
proposal fixtures now provide both rejected attempts. The production Gap fixture reuses
semantic IDs now that fresh early rounds have coverage focus. A stale-budget test now asserts
the earlier protected stop and absence of a Round-3 call; no assertions or gates were removed.

## Local delivery

Installers are under `desktop/dist/adaptive-reliability/` (ignored build artifacts):

- `ResearchAssistant-0.1.0-arm64.dmg`: SHA-256
  `8c13ae1a1adb98f5a07151eeb734d769e743c522d04ee88cd43eca6671aa4f6c`
- `ResearchAssistant-0.1.0-arm64-mac.zip`: SHA-256
  `f1c636242546e700cb52ea1da9a4e7a32a61d79461bba59f39845e114e7e6551`

The closed installed app was replaced after staged copying, preserving the previous bundle at
`/private/tmp/ResearchAssistant-before-adaptive-02qaixby/ResearchAssistant.app`.
Installed backend executable, frontend entry page and Gap prompt hashes match the packaged
build. The installed app was smoke-tested with isolated data and then closed normally.
Research history, preferences and real saved credentials were not modified by installation.

Start a new research run after reopening the updated app. Old source/prompt fingerprints
remain incompatible with resume; historical inspection/export is preserved. Live query utility
has not been retested with paid providers. Native Windows, clean-machine/minimum-OS acceptance,
production signing and notarization remain separate gates.

## Build environment notes

Local loopback/browser and native smoke checks required expanded sandbox access. PyInstaller's
default external cache was unwritable; the unchanged builder succeeded using an isolated
`PYINSTALLER_CONFIG_DIR` under `/private/tmp`. The copied bundled npm launcher lost its relative
module layout; packaging used the intact extracted Node 24.18.0/npm 11.16.0 toolchain. No package
versions or locks changed. Disk images were built outside the synced checkout, following the
existing desktop workaround, then copied into the local delivery directory.
