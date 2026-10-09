# Current status

Reviewed 2026-10-08 against local source at `15b8281`, Git history, the installed
backend, and fresh offline checks. [The documentation review](docs/verification/project-stage-2026-10-08.md)
records the scope and evidence.

## Project stage

**Implementation and local verification are complete for the database work, all six
source-discovery phases, and the subsequent repository review. Delivery of that source
and live research acceptance remain pending.** There is no unfinished implementation
phase in the current shared plans.

| Surface | Verified state |
| --- | --- |
| Repository source | `master` at `15b8281`; nine commits ahead of the local `origin/master` reference after the documentation commit (eight at the source-review baseline). The remote was not fetched during this review. |
| Working tree | The documentation refresh and reviewed proposal pack are committed locally. Seventeen pre-existing untracked root Python copies remain local. |
| Installed Mac backend | October 2 build `20bf6a2`; its executable SHA-256 still matches the delivery record. It lacks the later database and source-discovery work. |
| Latest recorded public release | [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928), based on `ac49404`. Public release state was not reverified during this review. |
| Current-source distributable | No fresh PyInstaller backend or native installer for `15b8281` is recorded or was produced by this review. |

The installed backend hash is
`41c930ebde8f65e0f53f999b1a4d652f744bd9028974954e73230797847f8c4f`.
The recorded local installer is
`~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`.
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
- **Mac delivery:** Build and verify a distributable containing current source, then
  perform separately authorized installation/distribution. Credential-backed launch,
  actual macOS 14 and clean-machine installation, Developer ID signing and notarization
  remain open. The installed app is an older local test build.
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
