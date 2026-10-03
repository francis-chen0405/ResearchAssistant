# Current status

## Source and delivery

- Runtime source is committed as `20bf6a2`; subsequent delivery-documentation changes do not change the tested runtime. No push or public release was requested.
- `/Applications/ResearchAssistant.app` was replaced on 2026-10-02 with the verified build from `20bf6a2`, including ALPR equity, validator and repository-organization changes. The new installer is `~/Downloads/ResearchAssistant-mac-arm64-20261002-20bf6a2.zip`. The superseded app and installer were deleted; saved application files were preserved. OneDrive repeatedly restores placeholders for the obsolete ignored `desktop/dist/private-surveillance-fixes-20261002/` folder, so that folder's cleanup remains incomplete.
- The public [September 28 unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928) was built from `ac49404`; it does not contain the October fixes. Do not describe it as the current-source build.

## Active work

The [current task](.agent/plans/validator-and-current-docs-2026-10-02.md) completed the metadata-validator repair, documentation cleanup, organization of 31 runtime modules into seven `researchassistant/` groups, commit and local app redelivery. Verification: **1,400 tests passed, two unchanged skips**, lint/formatting, offline evaluations and API checks. Packaged and installed native/window checks and old-to-new history/settings/test-credential compatibility passed. All 116 source inputs, 22 frontend files and 30,982 installed payload entries match the verified candidate; installer CRC/checksum checks passed. The task record retains exact results and investigation limits.

## Open acceptance gates

- **Windows:** [Job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744) at `4a1d1cc` failed in Python regressions/quality; later desktop checks skipped. Logs require repository-admin access, so the cause remains unknown. CI now separates the four quality commands for diagnosis. Windows release remains deferred.
- **Research quality:** Offline evidence and provenance checks do not establish that interpretations or conclusions are correct. Fresh manual research testing remains open; the five-submission paid allowance remains exhausted.
- **Mac distribution:** Actual macOS 14 and clean-machine installation, Developer ID signing, and notarization remain open. The installed app is a local test build, not a signed public release.

## Navigation

- [Active plan and verification results](.agent/plans/validator-and-current-docs-2026-10-02.md)
- [Next handoff](HANDOFF.md)
- [Grouped plan and verification history](docs/history.md)
- [Archive index and exact snapshots](docs/archive/INDEX.md)
