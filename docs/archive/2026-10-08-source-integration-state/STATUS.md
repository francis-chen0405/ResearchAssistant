# Current status

## Source and delivery

- Phases 1–5 of [source discovery v2](.agent/plans/source-discovery-v2-2026-10-05.md) are reviewed and committed locally, including the Phase 5 seed-identity corrections. Phase 6 product controls and final cross-phase acceptance remain the next boundary.
- The database implementation remains complete in local commits. Schema **17**, read-only support **7–17**, recovery and intentional writable upgrades are unchanged. New discovery artifacts reuse `v2_artifacts` without migration or dependencies.
- The installed runtime remains `20bf6a2`, replaced locally on 2026-10-02, with installer `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. It does not include the database implementation or these discovery phases. Saved application files remain intact. OneDrive cleanup of obsolete ignored desktop distribution placeholders remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) remains based on `ac49404`. Installation, commit, push and publication are separate boundaries.

## Verified source

Fresh OpenAlex neighborhood capability v4 and seed policy v2 resolve exact work IDs/DOIs and fetch bounded references, incoming citations and reported related works. At most three relevant owned scholarly seeds produce one-hop neighbors: ten unique works per seed across relations, thirty per run. Graph actions compete with text queries in existing adaptive Round 2–4 lanes; Round-4 Governor authorization, Round-3 limits and no Round 5 remain enforced. Each HTTP request reserves from the existing **10-request/$0.01** OpenAlex envelope, subordinate to existing metadata/model/acquisition limits. No new model-quality stage or provider budget is introduced.

Typed response bytes commit atomically with physical completion. Parser/raw candidate/edge ownership and hashes are revalidated on replay; cancellation can retain a resolved seed, and unknown starts cannot repeat. Exact identities reject ambiguity/conflicts and known retractions. Known DOI/provider-ID aliases share one seed slot; resolved seed IDs remain visited at runtime and storage. Compatible partial author lists are accepted without waiving ID, DOI, title, year or conflicting-author checks. Candidate locations retain public transport checks. Expanded candidates carry actual graph action/parent work/relation/provider/round/lane/Gaps with null query text through ordinary normalization, rank, Scout, acquisition, exact preview, selection, extraction, Analyst and deterministic admission. A support-lane citing work can yield challenging evidence. Discovery metadata never waives evidence gates. Read-only trails expose neighborhood provenance and graph diagnostics separately from text-query attempts.

Fresh prompt/schema/source identities require a fresh run; historical optional-field serialization, prompts, releases, costs, snapshots, source families and Ledger records retain their meanings. Existing claim-aware preview bounds, 24,000-token actual selection input cap, 3,000-word snapshots, independent Evidence Quality/Claim Fit and quotation gates remain unchanged. Full-chain fake fixtures establish action/source/snapshot ownership and expected admission only, not live retrieval quality. Unrelated restored files and the proposal pack remain preserved. No paid transport, credential access, real-user database change, installed-app replacement, automation, push or publication was performed.

Final isolated verification after review corrections: **2,167 tests passed, 3 existing skips in 159.14 seconds** on macOS arm64/Python 3.12.14; the focused graph/store/contract/type group passed **82 tests**. All **280 tracked/new Python files** pass Ruff lint and formatting; raw workspace formatting passes **297 files**. Whole-workspace lint reports only three pre-existing import-order failures in untouched untracked `desktop_settings.py`, `history_import.py`, `model_contracts.py`. Frontend ESLint/TypeScript, desktop syntax and whitespace checks pass. The implementation-stage isolated Next.js 16.3.1 webpack desktop static export passed; renderer source is unchanged by these corrections. The advisory graph was refreshed without persistence and reports ready (**9,697 nodes / 66,935 edges**). Five prior current-state documents match efbe119 byte-for-byte in the [archive](docs/archive/2026-10-08-source-neighborhood-state/STATUS.md). Detailed acceptance and reviewed local commit scope are in the shared plan.

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
