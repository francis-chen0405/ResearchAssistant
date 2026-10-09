# ResearchAssistant testing handoff — 2026-10-01

> Historical testing handoff. Its setup describes the September build and is superseded by [current STATUS](../STATUS.md) and [current HANDOFF](../HANDOFF.md). Retain the dated observations below; the installed backend was subsequently replaced on October 2.

Use this file as context for a new chat while I test the installed Mac app. I will
describe each bug I encounter. Investigate the reported behavior, reproduce it when
possible, fix it within the scope I authorize, and verify the fix. Do not assume a bug
exists merely because this handoff was created.

## Current setup

- Repository: `/Users/francischen/Library/CloudStorage/OneDrive2-EastsidePreparatorySchool/GitHub/ResearchAssistant`.
- Branch at handoff: `master`, commit `4d88266` (`Document and publish unsigned Mac test download`); the working tree was clean before this handoff was added. Check the live Git state again before editing.
- Installed app: `/Applications/ResearchAssistant.app` on Apple Silicon macOS 26.6.2.
- Release: [unsigned Mac test download](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928), tagged at source commit `ac49404`. The subsequent `4d88266` commit records verification and the upgrade-test harness adjustment; it did not change the release binary.
- DMG SHA-256: `c73d1f93013eeaa91d2c4f79670fcf4a088bbddc03bbe5288eaeeb47cc5042ba`. ZIP SHA-256: `ceb13ecef96c2bb0dd7436077b8b183e0b23740c65315cbcf7e17f41d27481e4`.
- App data: `~/Library/Application Support/ResearchAssistant/`. Credentials are in macOS Keychain. Preserve both; do not put secrets or user data into diagnostics or test artifacts.

## What has actually been checked

- On 2026-09-28, the release build passed 1,204 Python tests with 2 existing skips; Ruff, frontend checks, offline evaluation, browser smokes, frozen and packaged backend/window smokes, source-byte comparison, installer integrity, and an isolated old-to-new upgrade check. Details are in [build verification](verification/mac-current-build-2026-09-28.md).
- The GitHub DMG was downloaded on this Mac and matched the published SHA-256; `hdiutil verify` passed. I reported a macOS damaged/corrupted-style launch warning; its exact dialog text was not captured. Inspection found quarantine on the unsigned app, while its executable matched the verified DMG. A fresh copy from that DMG launched after quarantine was cleared on that verified copy.
- On 2026-09-29, the fresh copy replaced `/Applications/ResearchAssistant.app`. The old Applications backup, redundant Downloads installers, and temporary install copy were removed; six ResearchAssistant disk images were ejected. The project build artifacts were preserved. The installed app and bundled backend remained running after the disk images were ejected, and `open -a ResearchAssistant` succeeded.
- The installed app's offline smoke passed: local UI/backend, authentication, native credential cleanup, durable settings, and owned acquisition-service lifecycle. This used isolated temporary data and made no paid provider calls.
- I opened the installed app and confirmed my saved history is visible. That is a user observation; it is not a claim that every historical run or export was reviewed.

## Boundaries and known limitations

- This is a directly downloadable Apple Silicon Mac **test** build, not a Mac App Store app. It is unsigned and unnotarized. The local quarantine workaround does not make the published download signed or guarantee that it opens without intervention on another Mac.
- A clean Mac and actual macOS 14 installation have not been tested. Windows release work remains deferred.
- The prior five-submission paid live-test allowance is exhausted. I have performed live runs before, but this handoff does not authorize the assistant to make more paid provider calls. Use fixtures, isolated data, and offline checks unless I explicitly provide a new allowance.
- Do not replace or migrate my real data, clear Keychain items, change provider credentials, or delete immutable run evidence while debugging. Read-only inspection is fine.

## How to handle the next bug report

1. Start with my observed behavior and check the current working tree, [AGENTS.md](../AGENTS.md), [STATUS.md](../STATUS.md), [HANDOFF.md](../HANDOFF.md), the applicable plan, and relevant source. Use the repository knowledge graph as an advisory map when available, then verify against live files.
2. Capture exact reproduction steps, expected and actual behavior, the app screen or error text, and whether the issue occurs in the installed release, current source, or both. Ask only for missing details needed to proceed; do safe independent diagnosis meanwhile.
3. Reproduce with isolated data when possible. For validator or integrity defects, add a failing regression test before fixing the code. Preserve assertions and existing history/evidence.
4. Fix the cause, run focused checks, then the required full `pytest`, `ruff check .`, and `ruff format --check .` gates before declaring the phase complete. For desktop changes, rebuild and check the affected packaged app; source-only test success does not prove the installed binary is fixed.
5. Record the fix, verification, remaining risk, and next boundary in `STATUS.md` and `HANDOFF.md`. If a new downloadable build is needed, distinguish its source commit and checksums from the existing release and ask for any genuinely required publication approval only after the result is ready for review.

My preference is to use GPT-6 Luna helpers for routine searching and inspection where
available, keeping Sol for harder reasoning and final review. Do not start a paid live
run merely to reproduce a bug.
