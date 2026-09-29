# Current Mac build and release-gate verification — 2026-09-28

Status: unsigned Mac test download published; broader signed-release gates remain open.

The user selected steps 1 and 4 from the 2026-09-28 MVP assessment: rebuild and
verify a Mac candidate from current source, then work through installation and
signing gates. The user then clarified that the deliverable is a directly downloadable
test build, not a Mac App Store submission. This does not renew the exhausted paid
research allowance or authorize Windows release work or provider changes. A subsequent
"go" and "finish up" authorized publishing the finished downloadable test build.

## Completed local work

- Built Apple Silicon desktop resources and an unsigned DMG/ZIP from `ac49404` after
  the database-integrity and GPT-6 model-choice changes.
- Rechecked Python, Ruff, frontend lint/types, offline evaluation, browser smokes,
  frozen backend and native credentials, actual Electron window, artifact integrity,
  packaged source bytes, and a locally copied app from the DMG.
- Ran old-to-new history, preference, and native-credential verification against a
  schema-13 fixture readable by the preceding executable. The upgrade harness has an
  explicit `--previous-schema13` option for this case; all existing assertions remain.
- Saved checksums and detailed results in
  [current Mac build verification](../../docs/verification/mac-current-build-2026-09-28.md).

## Remaining boundary

The copied-app check ran on macOS 26.6.2 arm64 with isolated test data. It is not a
clean-machine or actual macOS 14 test. This host has no Developer ID signing identity,
so the candidate remains unsigned and unnotarized. These are further gates for a
broadly distributed signed release, not prerequisites for the finished test files.
The four verified files were published as the
[unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928).
GitHub's asset SHA-256 digests and sizes match the local files.
Live effectiveness remains outside this selected work and has no renewed paid allowance.
Windows remains deferred. No real user app was replaced. The release tag points to
`ac49404`; this verification harness and documentation follow-up is separate.
