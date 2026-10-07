# Current status

## Source and delivery

- Phase 1 of [source discovery v2](.agent/plans/source-discovery-v2-2026-10-05.md) passed conditional-commit review and is delivered in a local source commit: versioned contracts, conservative capabilities, deterministic fair allocation, downstream budget protection, durable physical-request accounting and validated read-only inspection. Five review findings were corrected with regressions. These foundations are dormant; production discovery still uses its prior policy. Later phases have not been activated.
- The four-phase [database implementation](.agent/plans/database-review-2026-10-03.md) remains complete in local source commits. Installation, push and release are separate boundaries.
- The installed runtime remains `20bf6a2`, replaced locally on 2026-10-02. Its installer is `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. It does not include the database implementation. Saved application files remain intact. OneDrive still restores placeholders for the obsolete ignored `desktop/dist/private-surveillance-fixes-20261002/` directory; that cleanup remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) remains based on `ac49404` and does not include the October fixes.

## Verified source

Schema **17** and read-only support **7–17** are unchanged; intentional writable upgrades preserve supported **1–16** histories. Discovery artifacts reuse `v2_artifacts` without a migration. Historical formats, exact costs, original release hashes and strict fresh-admission/resume gates retain their meanings. Missing new client settings retain the historical runtime policy; explicit new settings require their own immutable binding and cannot resume a legacy run.

Discovery reservations commit before transport and retain unknown exposure. Physical requests include retries, pages and metadata subrequests; PubMed requires two requests per complete metadata page. Native capabilities are distinct from what current adapters can execute. Exact previews and seed provenance remain selection metadata; acquisition, immutable snapshots, extraction, Analyst assessment and admission remain mandatory.

Final Phase 1 review verification on macOS with Python 3.12 and disposable application data passed **1,893 tests, three existing skips**, including **96 discovery-focused regressions**. Python lint/format and staged/working-tree whitespace checks passed. No frontend, desktop, dependency or executable prompt changes were made. The [shared record](.agent/plans/source-discovery-v2-2026-10-05.md) contains the contract inventory, acceptance matrix and limitations. Earlier database benchmarks/package evidence remain in the [database acceptance record](docs/verification/database-phase4.md). No paid/provider calls, credential access, real-data mutation, installed-app replacement, push or publication occurred. Offline fixtures do not establish live research quality.

## Open acceptance gates

- **External cache:** Repository build Wigolo integrity, migrations, references, vectors and FTS passed with its bundled extension on a consistent disposable backup. Installed Wigolo access remains unavailable and unverified; the [cache review](docs/verification/database-phase4-review.md) gives the exact completion path.
- **Windows:** Native ACL/NTFS durability remains unverified. [Job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744) at `4a1d1cc` previously failed in Python quality checks; logs require repository-admin access. Windows release remains deferred.
- **Research quality:** Offline evidence/provenance checks do not establish interpretation quality. Manual live testing remains open; the five-submission paid allowance is exhausted.
- **Mac distribution:** Credential-backed launch, actual macOS 14/clean-machine installation, Developer ID signing and notarization remain open. The installed app is a local test build.

## Navigation

- [Discovery foundations and source acceptance](.agent/plans/source-discovery-v2-2026-10-05.md)
- [Next handoff](HANDOFF.md)
- [Grouped history](docs/history.md)
- [Exact prior-state archives](docs/archive/INDEX.md)
