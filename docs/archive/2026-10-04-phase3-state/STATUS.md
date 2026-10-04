# Current status

## Source and delivery

- The installed runtime's source baseline is `20bf6a2`. Prompt 1 database lifecycle and Prompt 2 schema/accounting changes are reviewed, committed source work under the user's conditional approval. Neither is in the installed or public build. No push or public release was requested.
- `/Applications/ResearchAssistant.app` was replaced on 2026-10-02 with the verified build from `20bf6a2`, including ALPR equity, validator and repository-organization changes. The new installer is `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. The superseded app and installer were deleted; saved application files were preserved. OneDrive repeatedly restores placeholders for the obsolete ignored `desktop/dist/private-surveillance-fixes-20261002/` folder, so that folder's cleanup remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) was built from `ac49404`; it does not contain the October fixes. Do not describe it as the current-source build.

## Active work

The [database-review shared plan](.agent/plans/database-review-2026-10-03.md) owns four sequential implementation phases. Phases 1–2 are complete in source: verified recovery/lock lifecycle, shared strict schema preflight, full usage-field persistence, identity-bound atomic attempt completion and update-safe same-run provenance. Schema 15 adds nullable cache-write tokens/cost basis; schema 16 adds ownership/key guards. Writable boundaries 1–16 and public read-only boundaries 7–16 are covered. Conditional-commit review also fixed erased-schema bootstrap, table-option validation and the disposable old-build fixture. Final local macOS full-suite verification: **1,693 passed, three skips**, **85.20 s**, with warnings as errors and isolated application storage. Lint/format (**204 files**) and diff checks passed. Only disposable databases were used. Prompts 3–4, cross-phase acceptance and measured performance verification remain pending. Windows native ACL/durability and a new built artifact remain unverified.

The preceding [validator and organization record](.agent/plans/validator-and-current-docs-2026-10-02.md) retains the 1,400-test baseline and exact packaged/installed checks for `20bf6a2`; those results do not verify the new lifecycle source.

## Open acceptance gates

- **Windows:** [Job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744) at `4a1d1cc` failed in Python regressions/quality; later desktop checks skipped. Logs require repository-admin access, so the cause remains unknown. CI now separates the four quality commands for diagnosis. Windows release remains deferred.
- **Research quality:** Offline evidence and provenance checks do not establish that interpretations or conclusions are correct. Fresh manual research testing remains open; the five-submission paid allowance remains exhausted.
- **Mac distribution:** Actual macOS 14 and clean-machine installation, Developer ID signing, and notarization remain open. The installed app is a local test build, not a signed public release.

## Navigation

- [Active plan and verification results](.agent/plans/database-review-2026-10-03.md)
- [Next handoff](HANDOFF.md)
- [Grouped plan and verification history](docs/history.md)
- [Archive index and exact snapshots](docs/archive/INDEX.md)
