# Current status

Reviewed 2026-10-08 against local source at `15b8281`, Git history, the installed
backend, and fresh offline checks. [The documentation review](docs/verification/project-stage-2026-10-08.md)
records the scope and evidence. Current-source Mac delivery was completed on
2026-10-09 from `27aeb95`; see [the installation record](docs/verification/current-app-install-2026-10-09.md).

## Project stage

**Implementation and local verification are complete for the database work, all six
source-discovery phases, and the subsequent repository review. The current-source Mac
app is installed and running locally; live research acceptance remains pending.**
There is no unfinished implementation phase in the current shared plans.

| Surface | Verified state |
| --- | --- |
| Repository source | Built from `master` at `27aeb95`, including implementation through `15b8281`. At build time, HEAD matched the local `origin/master` reference; no remote fetch or push was performed during delivery. |
| Working tree | Clean before delivery. The installation record and current delivery guidance are updated locally; runtime source is unchanged. |
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

Fresh checks on macOS arm64/Python **3.12.14** passed: **2,232 tests, 3 existing
skips in 176.65 seconds**, Ruff lint/format across **312 Python files**, ESLint,
TypeScript, **38 offline cases** and **six synthetic discovery scenarios**.
[The documentation review](docs/verification/project-stage-2026-10-08.md) records the
scope and limits. The committed repository review additionally recorded a passing
Next.js **16.3.1** webpack static export; no new export or native build was performed
for this documentation refresh. Offline checks establish fixture and integrity
behavior; live ranking and interpretation quality remain unverified.

The old advisory graph retained obsolete module paths. This review successfully
refreshed the graph and verified canonical package owners against live source.
The earlier rejected refresh remains historical evidence in the repository-review plan.

## Open acceptance gates

- **Live research quality:** Manual current-source testing remains open, including
  ranking, usable full-text gains, model-selection value and interpretation quality.
  The five-submission paid allowance is exhausted. The later eight-run/$6.48 protocol
  is a proposal, not authorization. General retry after unusable HTML, OCR and new
  catalog providers remain outside the completed implementation scope.
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
