# Current status

## Source and delivery

- The installed runtime's source baseline is `20bf6a2`. Prompts 1–3 are reviewed, committed source work under the user's conditional approval. These changes are not in the installed or public build. No push or public release was requested.
- `/Applications/ResearchAssistant.app` was replaced on 2026-10-02 with the verified build from `20bf6a2`, including ALPR equity, validator and repository-organization changes. The new installer is `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. The superseded app and installer were deleted; saved application files were preserved. OneDrive repeatedly restores placeholders for the obsolete ignored `desktop/dist/private-surveillance-fixes-20261002/` folder, so that folder's cleanup remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) was built from `ac49404`; it does not contain the October fixes. Do not describe it as the current-source build.

## Active work

The [database-review shared plan](.agent/plans/database-review-2026-10-03.md) owns four sequential implementation phases. Phases 1–2 are reviewed and committed: recovery/locks, strict schema preflight, complete usage persistence, identity-bound completion and same-run provenance protection. Schema remains **16**, with writable boundaries 1–16 and public read-only boundaries 7–16.

Prompt 3 is **reviewed and committed**: explicit historical decoders and original release-hash reconstruction, noncreating path readers, actual v2 retrieval-attempt progress, explicit-decision browser filters and wrapped/paginated Unicode PDF exports. Current admission and incompatible-resume gates remain strict. ReportLab is a new runtime dependency, pinned to **4.4.9** for desktop builds; GNU Unifont **15.0.01** and its license are bundled. Unsupported PDF glyphs/complex shaping fail explicitly with Markdown/DOCX alternatives.

Conditional-commit local macOS focused verification: **661 passed**, **40.96 s**, with warnings as errors and isolated application storage; no skips in this selection. Review fixed unsupported v2 trail records and unsafe production/stage envelopes hiding unrelated history; compatibility is now reported per record or history item. Lint, formatting (**213 files**), diff, TypeScript and changed-file ESLint checks passed. Both rendered PDF pages were visually inspected again. The implementation's read-only repository-history verification reconstructed all **188** identified prior-policy v2 failures and both August release hashes, preserving database bytes/mtime and all **47** history entries. Known reviewed historical formats have no unresolved compatibility failure. Review tests wrote only disposable databases; real databases, providers, credentials and the installed app were untouched. Prompt 4 owns full-suite, cross-phase and measured performance/consistency verification. The preceding Prompt 2 full-suite result (**1,693 passed, three skips**, **85.20 s**) is a baseline, not verification of Prompt 3. Native Windows checks and a new built artifact remain unverified.

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
