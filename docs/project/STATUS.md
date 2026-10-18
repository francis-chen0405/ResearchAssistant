# Current status

All user-approved R01–R59 fixes in the [full review](../audits/2026-10-15/full-code-review.md)
are implemented and verified. The latest repairs preserve query directions, recover
interrupted stage/admission prefixes, retain exact fresh quote context and selected
occurrences, correct methods headings and approval wording, tolerate optional author
metadata, verify native source evidence, repair retained deduplication/accounting,
and protect evaluation inputs and benchmark fixtures.
[Verification](../verification/full-review-fixes-2026-10-15.md) retains exact evidence.

R53–R57 retain exact bounded-stage inputs and attempts, replay known results and
stop on unknown outcomes without repeating calls. Selection keeps its original
budget/shortlist; initial planning preserves its plan date and valid publication
prefixes. Fresh labels follow admitted evidence relationships. R58 bounds checkout
readiness; R59 aligns maintained schema/security/link/identity guidance. All 44 new
R56–R59 regressions and current source/distribution/frozen checks pass.

Current application/tooling/test code has full reads in the [manual ledger](../audits/2026-10-15/manual-coverage.json).
The user excluded historical files from further review. The previous 365-entry
pending count included 341 old records and four already-read guidance files.
The [active pending inventory](../audits/2026-10-15/remaining-file-review.json) now
contains 20 current items: three dependency lockfiles, current test/evaluation
fixtures, two reference documents and a bundled font. Historical compatibility code
and fixtures remain active consumers; archived documents and old reports are
preserved without further manual review. No absence-of-bugs claim follows.

## Current verification

The latest Mac CI failure at `ea4773c` was a test PID-publication race: an empty file
became PID zero. The [test-only repair](../../.agent/plans/mac-smoke-pid-race-2026-10-18.md)
uses atomic records and strict PID parsing. All 22 desktop units, two complete local
nine-scenario native runs, and 19 focused Python tests / two Windows-only skips pass.
The app source identity is unchanged; the new remote revision still requires CI confirmation.


The complete Python suite passes **3,196 tests / nine existing skips** in 415.65
seconds (rerun for the folders-only root), including all 44 R56–R59 regressions. Ruff lint/format (517 files), repository
boundaries, generated API types, frontend lint/types and staged/unstaged whitespace
checks pass. Focused historical compatibility and resume checks pass.

The exact 304-file wheel audit and fresh wheel/editable installs pass from unrelated
directories, including prompts/fonts, fixture release/blocking, fresh/replayed bindings
and DNS/PDF helpers. A separate frozen Mac candidate passes authentication,
smoke-only vault cleanup, settings restart, acquisition lifecycle and DNS/PDF dispatch
with an empty PATH. The preceding frozen candidate remains preserved; the installed Mac app is now updated as recorded below.

Renderer/Node bytes remain unchanged from R29. Its exact static export, 17 hook
checks, six offline browser smokes, 38 desktop/acquisition units and nine native
shutdown scenarios are retained; those unchanged checks were not rerun for R56–R59.

Current verified source identity: `source-sha256:fe0cc617eaba0753c9895d0a5f4a983f07946c594c7054d9696775250dcf937c`.

Schema 18 and existing research budgets/scoring remain authoritative. Fresh query
provenance v2 retains each lane's own direction; quotation context filter v2 preserves
exact selected offsets; fresh synthesis v2 / renderer validator v4 use relationship-aware admission wording. Explicit
old dispatch/serialization preserves historical records and released hashes. An older
ranking-only checkpoint has no saved Scout decisions: versioned recovery discloses
that loss and uses the existing ranking fallback without another Scout call. Original
charges and unknown reservations remain unchanged. Source/executable changes require
fresh research under the exact compatibility gate.

## Installed Mac app

The user-authorized [October 18 replacement](../verification/current-app-install-2026-10-18.md)
is installed and open at `/Applications/ResearchAssistant.app`, build `20261018.59`.
The October 9 app was deleted after candidate/DMG/installed backend/window and
isolated schema-17 history/credential upgrade checks passed. All 31,663 payload
entries/modes match. A verified 1.03 GB DMG remains in Downloads.
All 38 saved-data entries matched through installation/isolated checks. Normal
opening changed only ordinary Electron logs/instance links; research, acquisition
cache and preferences remain unchanged. Real credentials were preserved.
The app remains an unsigned local build; public-release acceptance is separate.

## Windows and release boundary

At `2586027`, the Windows packaging job failed earlier than installer acceptance:
`desktop/smoke.py` reported `Owned Wigolo exited with code 1`. The deeper service
startup cause remains undiagnosed. The user requested removing that verifier from
automatic checks; [Windows packaging is now manual-only](../../.agent/plans/windows-ci-trigger-2026-10-18.md).
Passing Windows native regressions and all other automatic jobs remain enabled.
This changes CI triggering only and does not establish Windows delivery acceptance.


[Prompt 17](../verification/windows-ci-durability-2026-10-13.md) retains historical CI
target `44f83d9bfb7e8e2896dc44390c366e4d498be044` on
`codex/windows-ci-durability-20261013`. Automatic CI and Mac packaging passed there;
Windows Python passed 2,810 / 15 skips. Packaging remains blocked by the 240-second
repair-install timeout after interrupted upgrade; installed acceptance was not reached.
The latest uninstall harness and these runtime changes have no native Windows rerun.

Physical power loss, Windows directory-entry flush ordering, clean/minimum-OS
acceptance, Windows ARM64, signing/SmartScreen and Mac signing/notarization remain
unverified. No new Electron installer acceptance is claimed. Public release is deferred.

## Repository root

The [folders-only layout](../../.agent/plans/root-layout-2026-10-18.md) follows the
user’s explicit choice: ten folder owners plus README. Instructions, workspace
configuration, launchers and Git rules are nested; CI and source archives use the
new paths. The full suite, explicit lint/format, coverage smoke, fresh-checkout Git
rules and real 2,151-file source archive pass. Runtime source identity and installed
Mac build remain unchanged. Historical snapshots and actual data are preserved.

## Git consolidation and preservation

The user authorized committing/pushing current project work to master and removing
the redundant Windows CI branch. The [task record](../../.agent/plans/publish-master-2026-10-18.md)
records exact branch comparison and validation. All useful Windows changes are
already retained in the current source; its historical CI results remain unchanged.
Original staged/unstaged patches and branch history were backed up locally before
index changes. The installed Mac app and real databases/cache/credentials remain
untouched. No paid research or public release is included.

[Preceding current-state records](../archive/2026-10-18-master-publish-preceding-state/hashes.json)
are archived. [HANDOFF](HANDOFF.md) owns the next boundary.
