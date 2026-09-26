# Handoff

## 2026-09-25 CLI routing and selection-aware setup correction

This bounded correction was made in a detached ResearchAssistant worktree at commit
`833a39c`; it has not been installed or published. `cli.py` no longer replaces
`LUNA_BASE_URL`, `MIMO_BASE_URL`, or `LUNA_MODEL` before fresh-v2 configuration.
The selected-route validator rejects a custom route before bundle construction,
returns the existing configuration-error exit code, and does not disclose API keys.
An override for a provider unused by all seven stage selections remains allowed.
The explicitly injected historical runner keeps its separate configuration path.

`POST /api/credentials/{name}/check` accepts a strict body with `model_profile` and
`stage_models`. The web sends its current choices. For model providers, a connected
state means the key was accepted and every distinct selected physical model ID was
listed by that provider. Luna High and XHigh deduplicate to one ID; Sol requires its
own ID; Standard checks its historical Luna and both MiMo IDs. A model provider with
no selected stage does not make an HTTP request or report connected. Direct requests
without a body use saved preferences; unreadable preferences give a sanitized
non-ready result. Source-provider key status remains presence-only. The provider
setup UI clears feedback for old choices and ignores late check results.

GET `/api/configuration` uses saved stage choices for a configurable profile, whether
or not the query names that profile. Unreadable preferences give a sanitized
non-ready result. The two string-matched `TypeError` compatibility catches in
`frontend/api.py` were removed; controller calls use the typed boundary and an
internal `TypeError` now propagates. The web configuration check uses an abort signal
and request identity so late success and error responses cannot replace a newer
selection's status, including on unmount.

Verification: 1,145 Python tests with two existing skips and one existing
Starlette/httpx deprecation warning; Ruff lint/format; `git diff --check`; frontend
ESLint, TypeScript, webpack desktop static export, `desktop/frontend-smoke.cjs`,
`desktop/frontend-poll-smoke.cjs`, and new
`desktop/configuration-race-smoke.cjs` all passed. Browser smokes used mocked local
API responses.
The default Turbopack build could not follow a dependency symlink outside the
worktree; the webpack export passed. No paid provider calls, credential installation,
dependency install, app packaging, installation, or publication occurred. The
intermittent upgrade smoke was not part of this correction and remains an unreliable
release gate. Real provider access and the existing Mac-first public-release gates
remain unverified.

## 2026-09-25 GPT-6 Luna model choices and replacement app

The active selectable GPT-5.6 Luna choices are now GPT-6 Luna High and XHigh, both routed
to `gpt-6-luna` with the selected reasoning effort. Scout and exact Extractor default to
High; the remaining five model stages default to XHigh. The other four choices remain
selectable. Saved desktop stage IDs migrate on read. Historical Standard profile records,
the low-level v2 compatibility route used without explicit stage selections, and stored run
identities remain compatible.
An explicit Standard-profile API request still selects its historical GPT-5.6 Luna route;
new configurable requests use GPT-6 Luna defaults.

All 42 stage/choice routes pass through the mocked provider API tests, alongside model
options, selected-provider readiness, pricing, preference migration and fingerprint checks.
Full verification passed: 1,124 Python tests (two existing skips), Ruff lint/format,
diff whitespace, frontend ESLint/TypeScript/static export, and the offline interaction and
polling browser checks. A final GPT-5.6 Luna High helper audit confirmed no active-route
findings. No provider API calls or credits were used.

The verified arm64 bundle replaced `/Applications/ResearchAssistant.app`; the packaged
`app.asar` and frontend entrypoint were compared after installation. The prior app bundle
is preserved at `/private/tmp/ResearchAssistant-before-gpt6-luna-20260925.app`.

Artifacts are in `desktop/dist/model-choices/`:

- `ResearchAssistant-0.1.0-arm64.dmg`: SHA-256
  `28148c5b9f344cca80680fccb4d957a23b32506dac260dae1f32648b351f447e`
- `ResearchAssistant-0.1.0-arm64-mac.zip`: SHA-256
  `ac12dd54ba22ddb94cdf057449480490859041310b1403617c34b468c4c12570`

The ZIP integrity test and DMG checksum verification passed. Independent review confirmed
GPT-6 Luna selectors/defaults and that the only GPT-5.6 Luna frontend references are
compatibility migration/restore paths. The low-level no-selection v2 route also retains its
older model for explicitly requested Standard runs and existing direct-v2 configuration
fingerprints. The isolated frozen credential smoke could not complete because macOS
Keychain returned `-60008`; a separate frozen loopback API smoke timed out. Neither check
called a provider. The app remains unsigned. Signing/notarization,
clean-machine installation, minimum-OS and current-version Windows checks remain open.

## Earlier 2026-09-25 per-step model-choice Mac app delivery

The current app is installed at `/Applications/ResearchAssistant.app` from the verified
arm64 package. There was no app at that path immediately before installation. The ZIP
integrity and DMG checksum checks passed. Packaged and installed window smokes and the
installed frozen-backend smoke passed with isolated data; the installed `app.asar` matched
the package. The existing `live-runs.sqlite3` and `preferences.json` checksums did not
change during installation or smoke testing. No paid provider calls were made.

Artifacts are in `desktop/dist/model-choices/`:

- `ResearchAssistant-0.1.0-arm64.dmg`: SHA-256
  `7a89263185c1bb1d69d99a78cffaad2d50337d1cab3449d005a903081c668397`
- `ResearchAssistant-0.1.0-arm64-mac.zip`: SHA-256
  `5e1f9e3d37fa39d2fe7c8a471bd1be07e2975a4d52ef2693ae6850ee237b451e`

The build is unsigned. Signing/notarization, clean-machine installation, minimum-OS and
current-version Windows checks remain release gates. The intermittent upgrade-smoke
startup timeout described below remains unresolved. The next phase should preserve those
gates and avoid paid provider verification without explicit direction.

## 2026-09-23 Per-step model choices and confirmed audit fixes

The current implementation authority is the [per-step model choices plan](.agent/plans/per-step-model-choices.md).
The confirmed audit fixes keep the selected model profile and stage choices in the POST
configuration check and credential-save paths, use the supported selectable catalog for
provider model checks, and update the offline frontend and upgrade smokes to exercise the
configurable profile and conditional provider credentials. Historical records and the
Mac-first release boundary remain unchanged.

Verification passed: 1,122 Python tests with two existing skips, Ruff lint and format,
diff whitespace checks, frontend lint, TypeScript and static export, JavaScript syntax, the
frontend interaction smoke, the status-polling smoke and one isolated upgrade smoke run. Two
upgrade reruns after the final backend rebuild timed out waiting for startup; both prior
and final backends passed separate native self-tests, so investigate the intermittent
upgrade startup before relying on that gate. No paid
provider calls or dependency changes were made. Keep the existing Windows deferral,
clean-machine, minimum-OS, signing and notarization gates.

## 2026-09-23 Neutral evidence ownership

The completed [neutral evidence ownership plan](.agent/plans/neutral-evidence-ownership.md)
is the latest implementation record. Fresh v2 stages import source-snapshot, quotation,
untrusted-source, Analyst scoring, drafting and Ledger admission helpers from the neutral
`evidence_core.py` and `evidence_analysis.py` modules. They no longer reach those helpers
through historical agent modules.

`agents.researcher` and `agents.analyst` are compatibility facades; `agents.supportingresearcher`
retains historical retrieval behavior and re-exports the neutral trust envelope. Public names,
model fields, validation behavior, persisted contracts and historical execution remain intact.
The historical `orchestrator.py` remains an explicit compatibility boundary and is not selected
by ordinary CLI/controller construction. Renderer and synthesizer remain shared final-output owners.

Verification passed: 1,027 Python tests with two existing skips; Ruff lint/format; and diff
whitespace checks. No dependency, schema, prompt, provider, budget, packaging, installation,
live call, push or publication changed. The source identity surface changed, so exact resume
requires new runs; historical inspection and export remain readable.

## 2026-09-21 Explicit pipeline selection

The completed [explicit pipeline selection plan](.agent/plans/explicit-pipeline-selection.md)
is the latest implementation record. Ordinary CLI and API construction selects v2;
historical execution is selected only through an explicit typed `legacy_runner` dependency.
The CLI no longer infers a pipeline from whether a historical function was monkeypatched.
Deterministic subprocess tests inject both their compatibility runner and repository identity
provider. `LiveResearchController` accepts the named `legacy_runner`, preserves the older
`runner` alias, and rejects conflicting injection before worker allocation.

The historical orchestrator, evidence modules, public imports and persisted contracts remain
available. V2's shared imports from legacy-named evidence modules remain intentional
compatibility debt and are a separate future extraction phase. Source identity changed, so
new exact runs are required; historical inspection/export remains readable.

Verification passed: 1,026 Python tests with two existing skips; Ruff lint/format;
frontend lint, TypeScript, production export, offline frontend acceptance and offline
status-polling acceptance; and diff whitespace checks. No paid/live calls, dependency,
schema, prompt, provider, budget, packaging, installation, push or publication occurred.
The work is committed directly on local `master`; remote `master` was not changed.

## 2026-09-20 SQLite status polling

Current implementation authority is the completed
[SQLite polling plan](.agent/plans/sqlite-status-polling.md). Each v2 snapshot owns one
validated `mode=ro`, `query_only` session and passes that connection through every v2
projection reader. Connections close on success and error; later requests see later
commits and revalidate a database replaced at the same path. Imported terminal snapshots
use the requested database path for subsequent UI requests.

Frontend polling is completion-driven, so a slow response cannot overlap another poll.
The dedicated browser test covers error recovery, a response longer than the old interval,
terminal stop, active-run replacement and unmount cleanup. Exact operation counts and limitations
are in [verification](docs/verification/sqlite-status-polling.md). The 1,019-test suite
passed with two existing skips, along with Ruff and all relevant frontend checks.

WAL and explicit busy-timeout policy remain a separate storage decision requiring
checkpoint/sidecar, import/backup and interruption analysis. The previous paid allowance
is still exhausted. The SQLite and deep-analysis reliability changes are merged locally into
`master`; no live acceptance, packaging, installation, remote push or publication occurred.

## 2026-09-18 Deep-analysis concurrency

Current implementation authority is
[deterministic deep-analysis concurrency](.agent/plans/deep-analysis-deterministic-concurrency.md).
Fresh-v2 deep analysis dispatches only budget-safe priority prefixes and uses at most four
source workers. Workers share the locked budgeted provider but no SQLite connection,
cursor or mutable aggregate. Each source still executes extraction, Analyst and admission
in order. The coordinator drains in-flight work before propagating cancellation and never
writes the aggregate completion artifact for a cancelled run.

The physical-call audit has one typed bulk reader shared by provider recovery and
deep-analysis reconciliation. It accepts current and legacy keys, requires dense global
start sequences, preserves unknown usage at reservation exposure and groups source
sequences only after validating the run-wide audit. The execution policy identity is
versioned `v2-waves4`; changed frozen identity requires a new run.

Synthetic eight-source delay measurements were 0.4286s serial, 0.2221s with two workers
and 0.1057s with four workers. Treat these only as deterministic scheduler measurements.
The 1,007-test suite passed with two existing skips, along with Ruff lint/format, diff
whitespace, the 38-case frozen evaluation, rebuilt arm64 backend and isolated native
smoke. No paid provider test, installer build, install or public release was performed. The
concurrency change is now merged locally into `master`. Live speed and research effectiveness remain unverified; any paid acceptance
needs new authorization because the previous five-submission allowance is exhausted.

## 2026-09-17 Reliability follow-up

The user authorized reliability before distribution and larger model responses within
the same total budget. The active Mac/cache plan includes this extension. Fresh planner
schema/default mismatch, Scout batching and Round-4 call estimates are corrected. The
Standard profile supplies 4,096/8,192/16,384 completion allowances for Scout/Pro/Luna;
legacy unprofiled defaults remain 4,096. No retry, timeout or global budget increase.
992 tests (2 existing skips), Ruff, offline evaluation, rebuilt native smoke, archive
integrity, upgrade and packaged/installed window checks pass. The app is installed;
latest downloads are in `desktop/dist/mac-reliability/`; see
[reliability record](docs/verification/planner-scout-reliability.md).

Never rerun or reset `desktop/build/mac-cache-live-acceptance/attempts.json`: five
submissions are consumed and the backend stopped. Outcomes: harness cancellation,
rejected overlap, initial-planner failure, and two 20-minute deep-analysis cancellations.
Total recorded model cost is $0.178617536; no final report was released. These original
candidate tests do not validate later fixes. Read the final acceptance record before
any further provider action; new paid tests need permission.

## 2026-09-17 Mac-first delivery

Current authority is [Mac-first release/cache pricing](.agent/plans/mac-release-cache-pricing.md).
The user resolved the earlier audit decisions: Mac first, Windows deferred, and official
model-specific cache accounting. The implementation, 984-test suite, offline checks,
packaging, native/upgrade/window tests and installed identity pass. The new unsigned Mac
app is installed; the prior app is backed up. Read the exact artifact/verification record
in [Mac verification](docs/verification/mac-cache-pricing.md).

Live acceptance is authorized for at most five submissions total with at most $5 model
budget and existing source-service quotas. The ledger under
`desktop/build/mac-cache-live-acceptance/attempts.json` is authoritative; do not reset it
or silently add paid tests. Initial harness interruption/rejected overlap count toward
that limit. A completed live attempt failed the initial planner's claim-coverage contract;
do not weaken validation or declare general research quality accepted. Final live results
are recorded in verification. No remote publication or paid Apple enrollment occurred.

The user has no Developer ID certificate; downloadable unsigned test delivery is possible,
but signing/notarization and clean-machine/minimum-OS checks remain open. Earlier audit
and phase notes below are historical, not unresolved choices or current execution authority.

## 2026-09-17 audit follow-up

Read the [MLP readiness audit](.agent/plans/mlp-readiness.md) before planning further
implementation. Documentation now distinguishes historical Windows verification from
current-version acceptance and scopes the no-network claim to the evaluation harness.
The current code still has a reproduced shared-adapter cache-pricing mismatch; decide
the accounting policy with the user before implementation. Recommended next work is
route-cap accounting with regression tests, followed by evidence-led acquisition/latency
investigation and explicitly budgeted live acceptance on the selected delivery target.

This audit changed documentation only. It did not start a new product phase, alter
historical artifacts, rebuild/install the app or run paid providers. Fresh Python/Ruff,
offline evaluation and frontend lint/type checks pass; details and pending decisions are
in the readiness plan. Later implementation will require a fresh build and new research
runs under the existing fingerprint rules. Earlier delivery instructions below describe
their dated work and do not constitute new commit/push or paid-call authorization.

## 2026-09-14 corrective delivery

The user explicitly authorized implementing the adaptive-search reliability plan after
Phase 3. Implementation and offline checks pass: 959 tests, 2 existing skips; Ruff,
frontend lint/types/build, browser acceptance and isolated frozen native smoke. See
[plan](.agent/plans/adaptive-search-reliability.md) and
[delivery verification](docs/verification/adaptive-search-reliability.md).
The new Mac app is installed and verified with isolated test data; it is closed. Installers
are in `desktop/dist/adaptive-reliability/`. The prior app bundle is retained as a temporary
backup at the location in the verification record. No user data or real credentials changed.

Use a new run with the updated app; old fingerprints remain incompatible with resume.
Round 2/3 now get one persisted, budgeted repair. Unresolved gaps survive relevant evidence;
old reports keep their historical reporting semantics. No paid test was run. Stop at this
corrective boundary. Acquisition/error-page filtering, model pricing and long timeouts are
separate investigations, not implemented here. Commit locally to master; do not push.

The Phase 3 handoff below is retained as historical implementation/platform context.

## Historical Phase 3 handoff

Phase 3 was developed on `codex/phase-3-frontend-settings`, from clean completed
Phase 2, and delivered to local `master` by fast-forward at the user’s request.
The user explicitly authorized this phase. No push, public release, paid call or
dependency addition was performed. Stop at the Phase 3 boundary.

Read [architecture](ARCHITECTURE.md), [configuration](docs/model-settings.md),
[Phase 3 plan](.agent/plans/phase-3-frontend-settings.md) and
[verification](docs/verification/phase-3.md) for actual checks and artifact locations.
The UI now shares reusable workspace/progress/dialog components; demo data is isolated
from live APIs. Standard model selection resolves a copied environment before worker
startup and preserves existing immutable configuration, accounting and release checks.

Outstanding: rebuild and test Windows on an authorized native runner; verify credential
access across signed versions, clean-machine install, minimum OS and signing/notarization.
An earlier isolated old-to-new Keychain test was denied after a provider API key was entered
into the macOS password prompt. Different ad hoc executable identities explain the system
access request; cancellation returned -128. The user then explicitly authorized the
unchanged 2026-09-08 upgrade smoke, which passed cross-version credential persistence and
historical data checks. Do not weaken native ACLs. Settings and API errors still explain the
distinction. Same-build native vault round-trip/persistence remains separately tested.

Rebuild, restart and start a new run after updating. The source/executable fingerprint
changes; incompatible resume must still fail explicitly. Historical inspection/export
must remain read-only and preserve exact validated output.

Use `.venv/bin/python -m pytest` / `-m ruff`: launcher shebangs reference the older
checkout. Local DMG output must use a temporary directory because the synced checkout
rejects disk-image creation; this is not an application runtime path.

This replaces the prior handoff while preserving its exact text in the
[Phase 2 handoff](docs/archive/phase-2-handoff/HANDOFF.md) and the
[earlier archive](docs/archive/pre-phase-2/HANDOFF.md).

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

## 2026-09-08 visual refinement

The user requested warmer, more varied colors, automatic preview playback, a smaller
side-by-side desktop home layout and removal of repetitive explanatory/footer copy.
The initial viewport of https://nomu.store/ was inspected without scrolling or exploring
lower sections. Coral, apricot, green and plum now distinguish actions, workspace,
supporting and challenging evidence. The hero and preview share the desktop viewport;
narrow windows retain readable stacking and scrolling.

The isolated example automatically advances through preparation, evidence, completion,
interruption and recovery. Hover and keyboard inspection pause it; hidden documents do
not advance. Reduced-motion mode shows a static completed example. A compact Example
badge and fictional source labels preserve its distinction from actual research. No
provider calls, engine changes, new dependencies or storage changes were introduced.
This supersedes the earlier manual example controls and dark workspace styling.

Verification: 942 tests passed, 2 existing skips; Ruff, frontend lint/types/build,
offline browser acceptance, archive validation and packaged Mac window test passed.
Updated installer and screenshots: `desktop/dist/phase3-colors/`. Replace the installed
app to see this refinement. See the Phase 3 verification record for retry details
and unchanged Windows/public-release gates.

## 2026-09-09 orange/green and sourced evidence refinement

At the user's request, orange and green are the only accent families; neutral surfaces
replace saturated background panels. Four real-source cards replace the fictional pair
and takeaway box. Source-type labels were removed; source links, years and expandable
context remain. Automatic playback, reduced motion, side-by-side desktop layout and
all actual research functionality remain. See [preview source audit](docs/preview-sources.md)
for provenance and the distinction between curated example material and live-run output.

Verification passed: 942 Python tests (2 existing skips), Ruff, frontend lint/types/build,
offline browser interaction/desktop-fit checks, DMG/ZIP integrity and packaged Mac
window/security/shutdown checks. Updated installer: `desktop/dist/phase3-evidence/`.

## 2026-09-12 preview tempo and orange hue

The requested fivefold speedup conflicts with the above-10-second full-loop minimum:
28.8 / 5 = 5.76 seconds. The loop is now 10.4 seconds (8 × 1.3 seconds), with its first
completed result at 3.9 seconds. This replaces the prior 3.6-second stage timing.
Hover/focus pause and static reduced-motion behavior remain. Orange accents shift toward
amber-orange; green and neutral surfaces remain. Browser timing measured 10,496 ms.
942 tests passed (2 existing skips), plus Ruff, frontend lint/types/build and offline
browser acceptance. New Mac installer location: `desktop/dist/phase3-tempo/`.

Final Mac artifact checks passed: DMG checksum, ZIP integrity and packaged window
load/authentication/renderer isolation/duplicate exclusion/normal shutdown.
