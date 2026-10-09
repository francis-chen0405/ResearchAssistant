# Current status

## Source and delivery

- All six phases of [source discovery v2](.agent/plans/source-discovery-v2-2026-10-05.md) are reviewed and committed locally, including the Phase 6 repairs and the comprehensive cross-phase review fixes.
- The database implementation remains complete in local commits. Schema **17**, read-only support **7–17**, recovery and intentional writable upgrades are unchanged. New discovery artifacts reuse `v2_artifacts` without migration or dependencies.
- The installed runtime remains `20bf6a2`, replaced locally on 2026-10-02, with installer `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. It does not include the database implementation or these discovery phases. Saved application files remain intact. OneDrive cleanup of obsolete ignored desktop distribution placeholders remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) remains based on `ac49404`. Installation, commit, push and publication are separate boundaries.

## Verified source

Ordinary desktop/API/CLI requests now use fresh product policy v3: metadata depth **20** (choices 10/20/50), paper expansion **enabled**, scholarly mode **lexical**. Automatic chooses lexical once; semantic requires selected OpenAlex. The existing per-direction source target separately bounds acquisition, under all previous provider, raw, Scout, source and model caps. Expansion remains one hop, three relevant owned seeds, ten unique neighbors per seed and thirty per run, inside OpenAlex's shared 10-request/$0.01 ceiling and authorized Round 2–4 slots. Round-4 Governor permission and no Round 5 remain enforced.

Frozen controls reach initial/adaptive orchestration and read-only history. Logical operations, physical requests/pages, retained metadata, work candidates, shortlists, acquisition attempts, usable captures and admissions have distinct presentation. Seed-derived counts include accepted completed expansion edges; rejected cycles, aliases and retractions remain in raw metadata totals. Synthetic graph attribution and acquisition URLs use exact provider/work IDs, preserving same-title papers and rejecting missing or unknown graph identities. Trails expose compiled query/depth, selection rationale, exact previews and seed provenance. Direct-v2 omission and explicit legacy injection retain prior behavior; absent historical fields remain absent, and changed fresh settings require a new run. Discovery metadata, previews and citation edges do not waive acquisition, immutable snapshots, quotation, Analyst or deterministic admission. Historical release bytes/hashes, costs, Ledger and source families remain unchanged. No migration, dependency or model stage was added.

The complete six-phase review repaired joined-author seed matching, lost graph PDF locations,
PDF acquisition ordering, conflicting same-title work clustering, exact DOI normalization,
compiled PubMed relevance sorting and DOI-alias evaluation accounting. Thirteen additional
regression cases cover those paths, including actual durable seed execution and fresh ranked
acquisition of a known PDF before an unusable publisher shell. Historical/default clustering
and normalization remain unchanged; no schema, dependency, prompt, quota or admission change.

Latest repository-review verification on macOS arm64/Python **3.12.14**:
**2,232 passed, 3 existing skips in 200.51 seconds**. Whole-workspace Ruff lint and
format pass across **312 Python files**, including the corrected imports in three
pre-existing untracked root copies. Offline evaluation passes **38 cases** and
strict source-discovery evaluation completes **six synthetic scenarios**; these
measure frozen fixtures rather than live research quality.

ESLint, TypeScript, Next.js **16.3.1** webpack desktop static export and whitespace
checks pass. The review repairs export overwrite races, terminal model retries,
acquisition/extraction input binding and checkpoint reuse, historical claim checks,
relocated database result paths, model-route display, generated-resource cleanup,
evaluation validation and test isolation. Bundles and executable fingerprints now
include only the four documented root Python entry points alongside package code.
The [repository-review record](.agent/plans/repository-review-2026-10-08.md) owns the
findings, regressions and scope. These changes are committed locally.

No fresh PyInstaller backend or native installer was built for these changes;
previous packaged-artifact evidence remains in the discovery plan. The advisory
graph retained old paths, and automatic approval review rejected its refresh;
local source, diffs and tests verified the reviewed owners. Exact preceding
current-state documents are retained in the
[repository-review archive](docs/archive/2026-10-08-repository-review-state/STATUS.md).
The installed application remains the older build. Installation, live provider
work, push and publication remain separate boundaries.

## Open acceptance gates

- **External cache:** Repository build Wigolo integrity, migrations, references, vectors and FTS passed with its bundled extension on a consistent disposable backup. Installed Wigolo access remains unavailable and unverified; the [cache review](docs/verification/database-phase4-review.md) gives the exact completion path.
- **Windows:** Native ACL/NTFS durability remains unverified. [Job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744) at `4a1d1cc` previously failed in Python quality checks; logs require repository-admin access. Windows release remains deferred.
- **Research quality:** Offline evidence/provenance checks do not establish interpretation quality. Manual live testing remains open; the five-submission paid allowance is exhausted.
- **Mac distribution:** Credential-backed launch, actual macOS 14/clean-machine installation, Developer ID signing and notarization remain open. The installed app is a local test build.

## Navigation

- [Discovery implementation and source acceptance](.agent/plans/source-discovery-v2-2026-10-05.md)
- [Next handoff](HANDOFF.md)
- [Grouped history](docs/history.md)
- [Exact prior-state archives](docs/archive/INDEX.md)
