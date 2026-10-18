# Current status

The [Prompt 07 installability work](docs/verification/backend-installability-2026-10-10.md)
is locally verified in the current checkout layout: wheel/editable installs run outside
the checkout, all 18 prompt bytes and the PDF font are bundled, public imports remain
intact, and `researchassistant --help` is supported. **2,371 Python tests passed,
5 existing skips**; Ruff/format/boundaries/whitespace, isolated install/resource/fixture
checks, offline evaluations and a rebuilt native frozen smoke passed. Prompt 08 starts
from this installable flat tree with canonical prompts already under
`researchassistant/prompts/`. Earlier staged/unstaged repairs are preserved; no app
replacement, staging, commit or push occurred. Python 3.11 and Windows execution remain
CI/platform verification boundaries.

The [bounded desktop shutdown repair](docs/verification/desktop-shutdown-2026-10-10.md)
is locally verified: **150 seconds** from first quit, **180 seconds** maximum from a
stalled spawn (30-second startup + shutdown), EOF-first cancellation and acknowledged
POSIX ownership before detachment. Start waits for the group before allowing scoped stop.
**2,350 Python tests passed, 5 skips**, **34 focused Python checks**, **20 handler tests**,
Ruff/format/boundaries/whitespace, nine native Mac process scenarios and real Electron
forced/normal quit checks and a rebuilt frozen backend smoke passed. Native Windows Jobs and fresh
packaged/minimum-OS checks remain pending. Changes are unstaged/uncommitted;
the installed app is unchanged.

The [atomic service-lifecycle repair](docs/verification/service-lifecycle-2026-10-10.md)
orders research admission against service stop and confirmed equivalent credential/import
guards. Short operation reservations preserve concurrent workers and cancellation ownership;
no lifecycle mutex spans provider, vault, SQLite or teardown/drain I/O. Fresh verification:
**2,340 tests passed, 3 existing skips**, **184 focused checks**, Ruff/format across **302
Python files**, boundary/whitespace checks, web lint/types/export and affected offline API/browser
smokes. The record owns 26 new barrier cases and contention measurements. This repair is
unstaged/uncommitted; the installed app is unchanged.

The [resume-status correction](docs/verification/resume-status-2026-10-10.md) exposes
rejected attempts within one poll without changing saved status/settings or audit
reservations. Restart shows unfinished saved progress with no worker in this app.
This is locally verified and unstaged/uncommitted; the installed app is unchanged.

The [unusable-capture correction](docs/verification/acquisition-usable-fallback-2026-10-09.md)
adds fresh acquisition Probe v4: usability is checked between allowed locations/methods,
with an immutable attempt/capture trail. The shell→alternate probe now yields one usable
source in two requests. All required offline checks pass; changes are unstaged/uncommitted.

The October 9 [citation-expansion investigation](docs/verification/citation-expansion-limits-2026-10-09.md)
reproduced and corrected shared-retention and changed-limit response-replay failures.
Fresh seed policy v3 is locally verified and uncommitted; the installed app is unchanged.

Reviewed 2026-10-08 against local source at `15b8281`, Git history, the installed
backend, and fresh offline checks. [The documentation review](docs/verification/project-stage-2026-10-08.md)
records the scope and evidence. Current-source Mac delivery was completed on
2026-10-09 from `27aeb95`; see [the installation record](docs/verification/current-app-install-2026-10-09.md).

## Project stage

**Implementation and local verification are complete for the database work, all six
source-discovery phases, and the subsequent repository review. The current-source Mac
app is installed and running locally; live research acceptance remains pending.**
There is no unfinished implementation phase in the historical shared plans.
The October 9 [root cleanup](docs/verification/root-cleanup-2026-10-09.md) removes
17 inactive copies and adds CI guardrails for the four supported root entries and
six reviewed dependency exceptions. The cleanup is staged locally, without a new
commit or push; it does not change runtime implementations or executable identity.

| Surface | Verified state |
| --- | --- |
| Repository source | Local `master` HEAD is `94a241b`; local `origin/master` is `27aeb95` (one commit behind). Installed-build provenance remains `27aeb95`. No remote fetch or push was performed during cleanup. |
| Working tree | Root cleanup remains staged. The resume-status, citation-expansion and acquisition runtime corrections, tests and current guidance are unstaged/uncommitted. The pre-existing untracked foundation proposal and implementation prompt pack are preserved. |
| Installed Mac backend | October 9 build from `27aeb95`, installed at `/Applications/ResearchAssistant.app`. Database schema 17 and source-discovery updates are included; packaged identity, upgrade, installed runtime and window checks passed. |
| Latest recorded public release | [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928), based on `ac49404`. Public release state was not reverified during this review. |
| Current-source distributable | A fresh unsigned Apple Silicon app bundle was built and installed on October 9. No new DMG/ZIP or public release was created. |

The installed backend hash is
`12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5`.
The old installed app was removed after verification. All 38 saved-data payload entries
were unchanged through replacement and isolated installed checks. The October 2 ZIP
is historical and does not contain the current changes.
The remaining OneDrive cleanup of obsolete ignored distribution placeholders has no
recorded completion. Source verification, installation, push and publication are
separate boundaries.

## Completed source behavior

- Database schema **17**, read-only schemas **7–17**, verified upgrade backups,
  explicit restore/import, historical decoding, accounting/provenance protections,
  coherent reads, query indexes and paginated Unicode PDF exports are implemented.
- Ordinary desktop/API/CLI requests use source-discovery product policy v3:
  metadata depth **20** (choices 10/20/50), paper expansion **enabled**, scholarly
  mode **lexical**. Automatic chooses lexical once; semantic requires selected OpenAlex.
- Provider-specific queries, bounded pagination/ranking, exact claim-aware previews,
  one-hop scholarly expansion, product controls and read-only diagnostics/trails are
  integrated. Expansion remains bounded to 3 seeds, 10 neighbors per seed and 30 per
  run inside OpenAlex's shared 10-request/$0.01 ceiling and authorized Round 2–4 slots.
  Round 4 requires Governor permission; there is no Round 5.
- Cross-phase and repository review fixes cover scholarly identity, known-PDF
  prioritization, exclusive exports, terminal retries, input-bound checkpoint reuse,
  historical resume, relocated paths, actual model-route display, packaging and
  evaluation/test isolation. Details and regressions remain in the shared plans.
- Discovery metadata and previews cannot bypass acquisition, immutable snapshots,
  exact quotations, Analyst or deterministic admission. Historical artifacts,
  released text/hashes, costs and source families retain their original meanings.
  Incompatible changed source/settings require a new run.

## Verification

Fresh resume-status checks pass: **2,314 tests, 3 existing skips in 241.42 seconds**,
**116 focused checks**, Ruff lint/format across **300 Python files**, repository
boundaries, staged/unstaged/new-file whitespace, web ESLint/TypeScript, desktop
webpack export, browser polling/UI/history race smokes and the rebuilt production
probe. [The record](docs/verification/resume-status-2026-10-10.md) owns ephemeral
attempt retention, controller ownership, API compatibility and unchanged database
hash/accounting evidence. No paid call, installation, staging, commit or push occurred.

Fresh acquisition checks pass: **2,304 tests, 3 existing skips in 207.49 seconds**,
**23 new regressions / 89 focused integration checks**, Ruff lint/format across **299 Python
files**, repository boundaries, staged/unstaged/new-file whitespace checks, **38 offline
cases** and **six synthetic discovery scenarios**. The [capture record](docs/verification/acquisition-usable-fallback-2026-10-09.md)
owns the before/after counts, immutable snapshots, replay and Probe-v4 identity evidence.
No live call, real research database write, installation, staging, commit or push occurred.

Fresh citation-expansion checks pass: **2,281 tests, 3 existing skips in 198.14 seconds**,
**188 focused tests**, Ruff lint/format across **298 Python files**, the root/import guard,
web ESLint/TypeScript, desktop shell syntax, whitespace checks, 38 offline evaluation cases
and six synthetic discovery scenarios. The [investigation record](docs/verification/citation-expansion-limits-2026-10-09.md)
owns the reproducers, boundary matrix and version/compatibility evidence. No paid call,
real research database mutation, native build, app replacement, staging, commit or push occurred.

Fresh root-cleanup checks passed: **2,243 tests, 3 existing skips in 204.63 seconds**,
**46 focused tests**, Ruff lint/format across **297 Python files**, the fast CI guard,
and staged/unstaged whitespace checks. Packaging/identity regressions passed and
restoring all 17 old copies in isolation left executable identity unchanged.
The root-cleanup record owns the detailed results and Git boundary.
The counts below describe the earlier project-stage review, not this cleanup.

Fresh checks on macOS arm64/Python **3.12.14** passed: **2,232 tests, 3 existing
skips in 176.65 seconds**, Ruff lint/format across **312 Python files**, ESLint,
TypeScript, **38 offline cases** and **six synthetic discovery scenarios**.
[The documentation review](docs/verification/project-stage-2026-10-08.md) records the
scope and limits. The committed repository review additionally recorded a passing
Next.js **16.3.1** webpack static export; no new export or native build was performed
for this documentation refresh. Offline checks establish fixture and integrity
behavior; live ranking and interpretation quality remain unverified.

The old advisory graph retained obsolete module paths. The root cleanup refreshed
the graph and verified canonical package owners against live source and the staged diff.
The earlier rejected refresh remains historical evidence in the repository-review plan.

## Open acceptance gates

- **Live research quality:** Manual current-source testing remains open, including
  ranking, usable full-text gains, model-selection value and interpretation quality.
  The five-submission paid allowance is exhausted. The later eight-run/$6.48 protocol
  is a proposal, not authorization. Bounded fallback after unusable captures is implemented
  locally under Probe v4. OCR and new catalog providers remain outside the completed scope.
- **Mac distribution:** Current-source local installation and normal credential-backed
  launch passed on October 9; the user allowed macOS Keychain access. Actual macOS 14,
  clean-machine installation, Developer ID signing/notarization and updated public
  distribution remain open. The installed app is an unsigned local test build.
- **External cache:** Repository-build Wigolo integrity, migrations, references, vectors
  and FTS passed on a disposable backup; installed-cache access remains unverified.
  [The cache review](docs/verification/database-phase4-review.md) gives the completion path.
- **Windows:** Native ACL/NTFS durability remains unverified and release remains deferred.
  [Job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744)
  at `4a1d1cc` previously failed Python quality checks; restricted logs remain unresolved.

## Navigation

- [Next handoff](HANDOFF.md) and [current plan index](.agent/PLANS.md)
- [Discovery implementation and acceptance](.agent/plans/source-discovery-v2-2026-10-05.md)
- [Repository review](.agent/plans/repository-review-2026-10-08.md)
- [Grouped history](docs/history.md) and [exact prior-state archives](docs/archive/INDEX.md)
