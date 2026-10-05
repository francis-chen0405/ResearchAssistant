# Current status

## Source and delivery

- The four-phase [database implementation](.agent/plans/database-review-2026-10-03.md) is complete at the source boundary. Prompts 1–4 passed conditional-commit review and are delivered in local source commits. Push, release and installed-app replacement were not authorized for Prompt 4.
- The installed runtime remains `20bf6a2`, replaced locally on 2026-10-02. Its installer is `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. It does not include the database implementation. Saved application files remain intact. OneDrive still restores placeholders for the obsolete ignored `desktop/dist/private-surveillance-fixes-20261002/` directory; that cleanup remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) remains based on `ac49404` and does not include the October fixes.

## Verified source

Schema **17** adds measured history/evidence indexes, with strict canonical validation, verified pre-upgrade recovery and atomic migration records. Read-only support is **7–17**; intentional writable upgrades preserve supported **1–16** histories. Historical formats, exact costs, original release hashes and strict fresh-admission/resume gates remain intact.

Requests now use explicit coherent read snapshots, including deterministic cleanup for Python 3.12 autocommit connections, bounded evidence batches and one-second retryable contention handling. Rollback journaling remains the default; existing WAL databases remain readable. Every new request retains full physical/schema/FK/ownership validation, with no unsafe validation cache. Unicode exports use pinned ReportLab **4.4.9** and bundled GNU Unifont **15.0.01**; font bytes now participate in source identity.

Final offline verification, benchmarks, the complete finding-to-test matrix and exact limitations are in the [source acceptance record](docs/verification/database-phase4.md). The complete suite passed **1,797 tests, three explicit skips** after the final Python 3.12 snapshot-ownership regressions. Lint, format, diff, offline evaluations, renderer lint/types/build and isolated frontend/recovery/import/export checks passed. An isolated macOS arm64 frozen backend verified the font, PDF dependencies, schema 17 and identity inputs. This is source/package verification, not installed-app launch. No paid/provider calls, credential access, real-data mutation or installed-app replacement occurred.

## Open acceptance gates

- **External cache:** Repository build Wigolo integrity, migrations, references, vectors and FTS passed with its bundled extension on a consistent disposable backup. Installed Wigolo access remains unavailable and unverified; the [cache review](docs/verification/database-phase4-review.md) gives the exact completion path.
- **Windows:** Native ACL/NTFS durability remains unverified. [Job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744) at `4a1d1cc` previously failed in Python quality checks; logs require repository-admin access. Windows release remains deferred.
- **Research quality:** Offline evidence/provenance checks do not establish interpretation quality. Manual live testing remains open; the five-submission paid allowance is exhausted.
- **Mac distribution:** Credential-backed launch, actual macOS 14/clean-machine installation, Developer ID signing and notarization remain open. The installed app is a local test build.

## Navigation

- [Shared plan and source acceptance](.agent/plans/database-review-2026-10-03.md)
- [Next handoff](HANDOFF.md)
- [Grouped history](docs/history.md)
- [Exact prior-state archives](docs/archive/INDEX.md)
