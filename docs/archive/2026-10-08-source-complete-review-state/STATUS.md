# Current status

## Source and delivery

- All six phases of [source discovery v2](.agent/plans/source-discovery-v2-2026-10-05.md) are reviewed and committed locally, including the Phase 6 diagnostic-count and evaluation-identity repairs.
- The database implementation remains complete in local commits. Schema **17**, read-only support **7–17**, recovery and intentional writable upgrades are unchanged. New discovery artifacts reuse `v2_artifacts` without migration or dependencies.
- The installed runtime remains `20bf6a2`, replaced locally on 2026-10-02, with installer `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. It does not include the database implementation or these discovery phases. Saved application files remain intact. OneDrive cleanup of obsolete ignored desktop distribution placeholders remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) remains based on `ac49404`. Installation, commit, push and publication are separate boundaries.

## Verified source

Ordinary desktop/API/CLI requests now use fresh product policy v3: metadata depth **20** (choices 10/20/50), paper expansion **enabled**, scholarly mode **lexical**. Automatic chooses lexical once; semantic requires selected OpenAlex. The existing per-direction source target separately bounds acquisition, under all previous provider, raw, Scout, source and model caps. Expansion remains one hop, three relevant owned seeds, ten unique neighbors per seed and thirty per run, inside OpenAlex's shared 10-request/$0.01 ceiling and authorized Round 2–4 slots. Round-4 Governor permission and no Round 5 remain enforced.

Frozen controls reach initial/adaptive orchestration and read-only history. Logical operations, physical requests/pages, retained metadata, work candidates, shortlists, acquisition attempts, usable captures and admissions have distinct presentation. Seed-derived counts include accepted completed expansion edges; rejected cycles, aliases and retractions remain in raw metadata totals. Synthetic graph attribution and acquisition URLs use exact provider/work IDs, preserving same-title papers and rejecting missing or unknown graph identities. Trails expose compiled query/depth, selection rationale, exact previews and seed provenance. Direct-v2 omission and explicit legacy injection retain prior behavior; absent historical fields remain absent, and changed fresh settings require a new run. Discovery metadata, previews and citation edges do not waive acquisition, immutable snapshots, quotation, Analyst or deterministic admission. Historical release bytes/hashes, costs, Ledger and source families remain unchanged. No migration, dependency or model stage was added.

Final isolated macOS arm64/Python **3.12.14** acceptance: **2,201 passed, 3 existing skips in 165.65 seconds**; focused diagnostics/evaluation/type verification: **16 passed**. All **290 tracked/task Python files** pass Ruff lint/format; raw format passes **307 files**. Whole-workspace lint retains only the three pre-existing import-order failures in untouched untracked `desktop_settings.py`, `history_import.py`, `model_contracts.py`. Existing offline evaluation passes **38 cases**; the separate strict discovery evaluation passes **six synthetic scenarios**, with recall gains on four opportunity cases, a neutral precision loss and biomedical capture failure explicitly reported. These do not establish live research quality.

ESLint, TypeScript, isolated Next.js **16.3.1** webpack desktop export, desktop shell syntax and whitespace checks pass. An isolated PyInstaller **6.22.2** macOS backend was rebuilt after the repairs and includes new modules and exact prompts; packaged/workspace source identity both equal `source-sha256:60e008aa2870f00b0e64cce55e7f6fcc83dfde317cebd822764dfc92d08609d2`. Credential-backed native launch and installation were not run. The advisory graph refresh is incomplete; live source, diffs and tests verify the corrected paths and ordinary CLI/controller wiring. Five prior state files match f665f204 byte-for-byte in the [archive](docs/archive/2026-10-08-source-integration-state/STATUS.md). The plan contains the requirement/failure matrix, exact checks, evaluation scope and a later bounded live-test protocol. No paid transport, credential access, real database mutation, app replacement, automation, push or publication occurred.

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
