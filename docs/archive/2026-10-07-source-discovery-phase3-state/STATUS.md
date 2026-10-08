# Current status

## Source and delivery

- Phase 2 of [source discovery v2](.agent/plans/source-discovery-v2-2026-10-05.md) is delivered in a reviewed local source commit: concept-only fresh Planner/Search Agent handoffs, deterministic provider-native compilation, explicit OpenAlex semantic mode, frozen query identity and shared durable physical execution across Round 1–4. Phase 1 foundations remain locally committed. Retrieval/ranking, previews, expansion and product settings are later boundaries.
- The four-phase [database implementation](.agent/plans/database-review-2026-10-03.md) remains complete in local source commits. Installation, push and release are separate boundaries.
- The installed runtime remains `20bf6a2`, replaced locally on 2026-10-02. Its installer is `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. It does not include the database implementation. Saved application files remain intact. OneDrive still restores placeholders for the obsolete ignored `desktop/dist/private-surveillance-fixes-20261002/` directory; that cleanup remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) remains based on `ac49404` and does not include the October fixes.

## Verified source

Schema **17** and read-only support **7–17** are unchanged; intentional writable upgrades preserve supported **1–16** histories. Discovery artifacts reuse `v2_artifacts` without migration. Fresh query compiler/capability/prompt/schema/mode/configuration identities are frozen separately; incompatible resume requires a fresh run. Historical prompts, optional compiled fields, production fingerprint meanings, costs and release hashes retain their meanings and explicit legacy dispatch remains covered.

Fresh initial and adaptive lanes keep enabled directions/providers, exact claims and original Gap IDs. Provider-native parameters reach all five configured engines; unsupported Serper/modes are rejected before transport. OpenAlex semantic uses `search.semantic`, distinct frozen pricing identity and documented $0.001 reservation; no hidden fallback or paid rerank. Semantic starts/retries are spaced one second apart per adapter instance, with cancellable waiting before durable reservation. Ordinary client mode controls remain Phase 6. Every physical query/retry/PubMed summary reserves durably before transport; parent response/ID ownership, sanitized parameters, bounds, typed cancellation and conservative reported/unknown costs are enforced. Compiled requests require the accounting owner, and a legacy selector cannot bypass a fresh binding. Tighter configured OpenAlex budgets and complete-query physical headroom constrain later planning. Discovery remains metadata: acquisition, immutable snapshots, exact extraction, Analyst and admission remain mandatory.

Final macOS/Python **3.12.14** verification with disposable application data passed **1,969 tests, three existing skips in 109.05 seconds**. Python lint/format (**245 files**) and staged/working-tree whitespace checks passed. The skips are the explicit-approval CLI test, optional LLM integration and native Windows ACL verification. Fresh fixture production reaches release through Rounds 1–4 and retains Governor authorization, no Round 5, challenge-only admission and immutable history/resume boundaries. Review regressions cover fresh/legacy binding, legacy Planner order, semantic context, accounting guards, pacing/cancellation and complete PubMed query headroom. The [shared record](.agent/plans/source-discovery-v2-2026-10-05.md) contains detailed evidence and compiled examples; [provider reference](docs/source-query-provider-reference.md) records official URLs checked 2026-10-06/07. No frontend, desktop, dependency, schema or migration changes were made. Delivery is a local commit only; no paid/provider calls, credential access, real-data mutation, installed-app replacement, automation, push or publication occurred. Offline fixtures do not establish live research quality.

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
