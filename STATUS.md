# Current status

## Repository delivery authorization — 2026-10-01

The user explicitly requested a final obsolete-app cleanup, opening the new app,
and committing and pushing all current changes. The installed app's source/export
parity and normal launch were rechecked successfully; no research was started.
Luna precommit review found no credentials, user data, databases, build outputs or
installers among pending repository files. Ruff/format and whitespace checks passed;
the existing full 1,283-pass / 2-skip suite applies to the unchanged tested source.
The final name-only scan found only the installed Applications app and no named
installers or mac-arm64 folders in accessible locations. An obsolete backend build
cache in Codex worktree 3020 was removed; seven text records were archived. One
Google Drive CloudStorage location was unreadable and remains unchecked.
The remote branch was checked before delivery. Git history records the authorized
commit; the delivery result is verified against the remote after pushing. Earlier
uncommitted/no-push statements below record the preceding verification phases.
Paid research and signed/live/platform release gates remain outside this delivery.


## Approved ALPR fixes installed — 2026-10-01

All user-approved findings A–G are implemented and verified with three Luna helpers.
See the [verification record](docs/verification/alpr-run-fixes-2026-10-01.md) for admitted-only evidence, actual relationship
labels, Ledger-bound citations, current stopping/coverage disclosures, source
outcomes, optional future usage splits and conservative study-lineage notices.
Full pytest passed **1,283 tests / 2 unchanged skips**, warnings as errors; Ruff,
frontend/export, offline/API/browser and rebuilt/installed native/window gates passed.

Use `/Applications/ResearchAssistant.app`. Exact parity covers **101 source inputs,
22 frontend files and 30,929 installed payload entries**. Backend SHA-256:
`d561b04e95a2745792e8d76143e30cb4fefe0a9f314e2d74286b85fed302480c`.
The old app, redundant mac-arm64 candidate and temporary backend build/cache copies
were removed. Saved research, credentials, source and verification records remain;
all 233 saved-run artifact hashes and the released brief hash are unchanged.
Historical exports remain frozen; reopen saved research for the corrected display.
Normal launch passed with the installed app and its owned backend running from
Applications; unauthenticated health returned 401.

Changes remain uncommitted. No provider calls, new dependencies, schema migration,
publication or push occurred. Historical input/output/cache splits remain unknown;
the supplied-rate estimate is $0.06 and the saved total remains $0.057952460.
Stop at manual testing; fresh research must obey the existing identity gate. No new
paid allowance or live-quality, clean-machine/macOS 14, signing or notarization gate
is established. Earlier sections below are historical and superseded where this
completed approval applies.


## ALPR saved-run review; fixes await decision — 2026-10-01

Read-only review of the user's newly released ALPR run is complete; see
[findings A–G](docs/verification/alpr-run-review-2026-10-01.md). At the supplied
$0.10/$0.50 per-million rates, the user's corrected 250,000 input plus 70,000 output
tokens cost **$0.06**. Their 320,000-token total differs from the stored total and
cannot be exactly reconciled without the full provider breakdown/account scope.
The actual run records **268,135 tokens and $0.057952460**, correctly displayed as
$0.0580. All 48 physical calls retain completions and costs, including three failed
calls. Full input/output/cache splits are not retained for this run.

The release revalidated with the same hash and all 233 payload hashes matched.
Twelve records were admitted, two rejected, and seven failed; the Evidence UI
incorrectly includes three unadmitted cards. Search direction is labeled as
supporting relationship, and the displayed fixed-three-round stopping explanation
does not reflect the later Round-4 decline for expected search overlap. The report
also records partial coverage, absent visible finding citations, source-outcome
visibility, usage-telemetry limits, and duplicate-study family identity.
No app/runtime/test/data/settings changes or provider calls occurred. The user
explicitly reserves approval of fixes; do not implement until they decide.

## Audited Mac app installed; obsolete copies removed — 2026-10-01

At the user's direction, the latest verified comprehensive-audit build replaced
`/Applications/ResearchAssistant.app` and was opened normally. The staged copy
matched all **30,928 payload files/symlinks**; installed native/backend and actual
window checks passed using isolated test data. The normally launched app/backend
are running from Applications and authentication remains enforced. Backend SHA-256:
`2fbffbb0e524a1cd769ac11e37769325044290193707735b771363bf557cd9bd`.
See [installation verification](docs/verification/audited-app-install-2026-10-01.md).

Removed **24 old/redundant app bundles, 22 installers, 6 blockmaps, 4 obsolete resource
backups, and 22 residual packaging/cache/intermediate directories**, including all
old mac-arm64 packaging folders and the redundant latest candidate. Only the new
Applications app remains; home/temp rescans found no other app/installer copies.
Preserved source, current development resources, saved research, credentials, and
verification logs; 19 package text/hash records were archived. Real-data metadata
matched across installation and isolated checks. The audit and older build records
below describe the earlier state; their local binaries were removed by this new
authorization. No runtime code, paid call, or public release changed. The app is
ready for manual testing; signed/live/platform release gates remain open.

## Comprehensive code audit — 2026-10-01

The repository-wide Luna-assisted review and confirmed-defect repairs are complete.
The [plan](.agent/plans/comprehensive-code-audit-2026-10-01.md) and
[final report](docs/audits/2026-10-01/README.md) record nine area reviews, a 206-input
coverage ledger, all confirmed repairs, rejected hypotheses, and remaining limits.
Repairs cover evidence provenance, research-round status, exact money addition,
physical-prompt budget reservation, actual usage and terminal progress, early worker
failures, API errors, bounded service readiness, ordered preference writes,
saved-history races, owned process/stream cleanup, concurrent legacy retrieval,
fresh-v2 CLI inspection, and same-origin desktop export. The prior Reviewer-route
and failed-brief UI fixes are retained. All confirmed in-scope defects are resolved;
the audit does not prove absence of every possible defect.

Full pytest passed **1,256 tests with 2 unchanged skips**, warnings as errors, with
**81% combined line/branch coverage**. Ruff/format (170 files), whitespace, frontend
lint/types, offline evaluation, API/config smoke, four browser smokes, and rebuilt
frozen/packaged backend and actual Electron-window checks passed. All **100 source
identity inputs and 22 exported frontend files** match the tested source. The first
window candidate exposed an incorrect fixed API origin; it was preserved, the
configuration guard and regressions added, and the final rebuilt window passed.

Verified unsigned local app:
`desktop/dist/comprehensive-audit-20261001/mac-arm64/ResearchAssistant.app`.
Backend SHA-256: `2fbffbb0e524a1cd769ac11e37769325044290193707735b771363bf557cd9bd`.
Source-only identity: `source-sha256:7f9e05142129e7124cae130c4bc8feba32c49b193b8ca15237130e463c87f551`.
Exact evidence is in the final report and local parity JSON.

Changes remain uncommitted. The installed app, prior verified local app, and
published installers remain unchanged. No real user data, paid/live provider call,
dependency/schema change, installation, publication, or push occurred. Installation
and a fresh manual run are the next separate boundary; live quality, native Windows,
clean-machine/macOS 14, signing, and notarization are not verified by this audit.

## Installed Mac testing fix — 2026-10-01

Fixed the reported `no v2 route is configured for reviewer` failure: adaptive-search
budget protection now reserves the configured model routes, retaining the existing
eight-call token/cost protection and historical routing. Failed runs no longer claim
a validated brief is available; detailed evidence loads only after a valid released
result. Seven new regressions cover selected/default/mixed routes, protected-budget
thresholds, and actual round-four completion with fixture providers.

Full pytest passed **1,211 tests with 2 unchanged skips**, warnings as errors. Ruff,
frontend lint/types, offline evaluation, all three browser smokes, frozen/packaged
native smokes, and the packaged Electron window passed. All 100 packaged source
identity inputs and exported frontend files match tested source. The verified local
unsigned app is `desktop/dist/reviewer-route-20261001/mac-arm64/ResearchAssistant.app`;
see [verification](docs/verification/reviewer-route-testing-fix-2026-10-01.md).

The installed app still has the old code. No paid call, real-data change, installation,
publication, dependency change, or commit/push occurred. Prior build/release evidence
is preserved. Installing the replacement and starting a fresh run is the next boundary;
the existing live-quality and signed-release gates remain open.

## Installed Mac app and testing handoff — 2026-10-01

The verified unsigned release was installed at `/Applications/ResearchAssistant.app`
on 2026-09-29 after a downloaded, quarantined copy triggered a macOS launch warning.
The downloaded DMG matched its published SHA-256 and passed disk-image verification;
a fresh copy from it launched after quarantine was cleared on that verified app.
The installed app and backend stayed running after old mounted images were ejected.
Its isolated offline smoke passed, and the user confirmed saved history was visible.
No paid provider call or real-data migration was performed. The user is continuing
manual testing; no new bug had been reported at the handoff. See the
[testing handoff](docs/testing-handoff-2026-10-01.md).

## Current Mac build and release-gate verification — 2026-09-28

At the user's direction, the current `ac49404` source was rebuilt as an unsigned
Apple Silicon Mac DMG/ZIP. Full pytest passed with **1,204 tests and 2 existing skips**;
Ruff, frontend lint/types, offline evaluation, all three browser smokes, frozen and
packaged backend/window smokes, package integrity, and all 100 packaged source-byte
comparisons passed. An isolated old-to-new upgrade check passed against a schema-13
fixture after the test harness gained an explicit historical-fixture option. A copy
installed from the DMG passed the window smoke on this macOS 26.6.2 host. Exact hashes
and limitations are in [verification](docs/verification/mac-current-build-2026-09-28.md).

The DMG and ZIP were published as an
[unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928),
with SHA-256 checksums and a short readme. GitHub's published asset digests and sizes
match the verified local files. There is no Developer ID signing identity on this host,
and no clean macOS 14 machine was available. Signing/notarization and
actual clean-machine/minimum-OS acceptance remain open for a broadly distributed
signed release, not for this test download. The installed user app was not
replaced. The user reports prior live testing and selected build/distribution work
here; no new paid live run was made. The recorded five-submission allowance remains
exhausted, and Windows remains deferred.

## Documentation audit — 2026-09-28

The documentation-only [audit](.agent/plans/documentation-audit-2026-09-28.md) corrected stale schema-support and credential-transport statements, refreshed the model-guide pricing links, and identified older package-verification and installed-app claims as historical. Read-only inspection supports schemas 7–14; OpenAlex and optional PubMed API keys are sent to their upstream services in HTTPS query strings. Current-document links resolve locally. Full pytest passed with 1,204 tests and 2 existing skips; Ruff lint/format and whitespace checks passed. No source, product behavior, or release evidence changed.

## Database integrity fixes — 2026-09-28

The [database integrity plan](.agent/plans/database-integrity-fixes.md) implements all ten review findings. Writable initialization rejects newer schemas before mutation; schema validation checks complete known table/trigger/index definitions and foreign keys. Schema 14 adds nullable cached/uncached input-token fields without inventing historical usage; read-only inspection supports schemas 7–14 without migration.

Fresh-v2 terminal artifacts and run manifests commit together, and explicit compatible resume repairs previously interrupted current-policy completion metadata from the saved result. Read-only history also projects older terminal results correctly without requiring resume or changing database bytes. Legacy portfolio writes use correct snapshot provenance, atomic batches, conflict-checked replay, and a narrow recovery path for earlier missing-provenance projections; historical rows remain unchanged. Imports return typed input errors, preserve pre-existing destination files, and close backup connections.

Final verification passed **1,204 tests with 2 existing skips**, with warnings treated as errors; Ruff, formatting, and whitespace checks passed. The 41 new regression cases and exact boundaries are recorded in [verification](docs/verification/database-integrity-fixes.md). This record accompanies the local database-fix commit; no push is included. The earlier packaged/native evidence below applies to the preceding maintenance commit, not these source changes. The installed app has not been replaced, and these changes require a fresh build before distribution.

## Prior audit maintenance — 2026-09-26

The 2026-09-26 [audit maintenance](.agent/plans/audit-maintenance.md) is implemented and reviewed. Extraction records preserve selected effort; legacy routing policy is centralized; the upgrade harness handles startup readiness and output pipes with safe diagnostics. Package/CLI branding, optional Streamlit installation, pytest imports, the Starlette test dependency, generated-cache tracking, and current documentation are corrected. The already-merged remote cleanup branch was deleted.

The preceding commit `5c66287` fixes selected-provider endpoint validation, model-aware connection checks, saved-selection API checks, TypeError fallbacks, and stale frontend responses. Fresh v2 retains seven model choices by stage: Luna High defaults for Scout/extraction and XHigh for the other five. Historical Standard routes and stored runs remain compatible. The historical Luna pricing branch is required and retained.

## Prior maintenance verification — 2026-09-26

**1,163 Python tests passed, 2 existing skips, with warnings treated as errors.** Ruff, TypeScript, ESLint, offline evaluation, and all three browser smokes passed. The final frozen backend matches all 100 source identity inputs and passed its native smoke. Three consecutive old-to-new upgrade checks passed every credential, preference, historical-report, executable-identity, and database-integrity assertion.

The original intermittent timeout did not recur; its exact historical cause remains unknown. Confirmed readiness and pipe-handling defects are fixed and regression-tested. This establishes successful local upgrade checks, not universal unsigned-vault or platform acceptance. See [the verification record](docs/verification/audit-maintenance.md) for artifacts, timings, commands, and limitations.

Test-only `httpx2` and its constrained dependencies were installed. Streamlit is available through `requirements-legacy.txt`; runtime adapters still use httpx. The changes are recorded in the local maintenance commit containing this document; source commits have not been pushed and the installed app has not been replaced.

## Release gates

Live provider effectiveness and dependable live research completion remain unverified. The five-submission allowance is exhausted ($0.178617536 recorded exposure, no released final report); further paid research needs a new allowance. The Mac candidate remains unsigned, with clean-machine, minimum-OS, signing, and notarization checks open. Windows release work remains deferred.

Dated implementation and prior failed checks are preserved in [the archive](docs/archive/INDEX.md). They are historical evidence, not current download instructions.
