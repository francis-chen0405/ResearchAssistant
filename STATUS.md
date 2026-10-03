# Current status

## Source and delivery

- The user requested committing the verified ALPR equity, validator, repository-organization and documentation changes, installing a fresh Mac app and deleting outdated local builds. Commit and local redelivery are in progress; no push or public release was requested.
- `/Applications/ResearchAssistant.app` is the locally verified app from the private-surveillance delivery on 2026-10-02. It does not include the current ALPR equity, validator or repository-organization changes.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) was built from `ac49404`; it does not contain the October fixes. Do not describe it as the current-source build.

## Active work

The [current task](.agent/plans/validator-and-current-docs-2026-10-02.md) completed the metadata-validator repair, documentation cleanup and organization of 31 runtime modules into seven `researchassistant/` groups. Final verification: **1,400 tests passed, two unchanged skips**, lint/formatting, offline evaluations and API checks. The rebuilt development bundle passed isolated native and desktop-window checks; its 116 source inputs and 22 frontend files match the verified source/export. This verifies the development bundle, not installation or public distribution. The task record retains exact results and investigation limits.

## Open acceptance gates

- **Windows:** [Job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744) at `4a1d1cc` failed in Python regressions/quality; later desktop checks skipped. Logs require repository-admin access, so the cause remains unknown. CI now separates the four quality commands for diagnosis. Windows release remains deferred.
- **Research quality:** Offline evidence and provenance checks do not establish that interpretations or conclusions are correct. Fresh manual research testing remains open; the five-submission paid allowance remains exhausted.
- **Mac distribution:** Actual macOS 14 and clean-machine installation, Developer ID signing, and notarization remain open. The installed app is a local test build, not a signed public release.

## Navigation

- [Active plan and verification results](.agent/plans/validator-and-current-docs-2026-10-02.md)
- [Next handoff](HANDOFF.md)
- [Grouped plan and verification history](docs/history.md)
- [Archive index and exact snapshots](docs/archive/INDEX.md)
