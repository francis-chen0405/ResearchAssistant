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

Final isolated macOS arm64/Python **3.12.14** verification: **2,214 passed, 3 existing skips in
172.85 seconds**. All **291 tracked/task Python files** pass Ruff lint/format; whole-workspace
format passes **308 files**. Whole-workspace lint retains only three pre-existing import-order
failures in untouched untracked `desktop_settings.py`, `history_import.py`, `model_contracts.py`.
Existing offline evaluation passes **38 cases**; strict discovery evaluation passes **six
synthetic scenarios**, retaining the biomedical capture failure and neutral precision loss.
These do not establish live source discovery or interpretation quality. General retry after
an unusable HTML capture remains outside the six-phase implementation scope.

ESLint, TypeScript, isolated Next.js **16.3.1** webpack desktop export, desktop shell syntax and
whitespace checks pass. A fresh isolated PyInstaller **6.22.2** backend includes seven inspected
modules and nine byte-exact sources/prompts; packaged/workspace source identities match
`source-sha256:008fdb5f52c74f3663b3ff4ba4f5f21c2a804c16a3d939e385dfa8c6d0176e62`.
The advisory graph remains incomplete after refresh; live source, complete phase diffs and
tests verify the reviewed owners. Exact prior current-state files are retained in the
[comprehensive-review archive](docs/archive/2026-10-08-source-complete-review-state/STATUS.md).
No paid transport, credentials, real application database mutation, app replacement,
automation, push or publication occurred. The installed application remains the older build.

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
