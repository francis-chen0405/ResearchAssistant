# Current plan state

## Latest Mac verification

[Current Mac build and release-gate verification — 2026-09-28](plans/mac-current-build-release-verification-2026-09-28.md)
records the user's selection of the current-build and Mac distribution checks. A fresh
unsigned DMG/ZIP passed the available source, package, native, window, upgrade, and
copied-app checks on macOS 26.6.2 and was published as an
[unsigned Mac test download](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928).
Actual macOS 14/clean-machine and Developer ID signing/notarization remain open;
see [verification](../docs/verification/mac-current-build-2026-09-28.md).

## Latest documentation audit

[Documentation audit — 2026-09-28](plans/documentation-audit-2026-09-28.md) corrected
schema compatibility and credential transport wording, verified current navigation,
rechecked published model prices, and dated older package-verification claims. No
product behavior or executable inputs changed.

## Latest completed database maintenance

[Database integrity fixes](plans/database-integrity-fixes.md), authorized 2026-09-27, addresses all ten confirmed review findings, including the bounded schema 14 accounting migration. Implemented and verified 2026-09-28: 1,204 tests passed, 2 unchanged skips; see [verification](../docs/verification/database-integrity-fixes.md).

## Prior audit maintenance

[Audit maintenance and follow-up checks](plans/audit-maintenance.md) was implemented, reviewed, and verified on 2026-09-26 for the authorized local commit. Its bounded scope includes upgrade-smoke diagnosis, approved extraction and route-guard work, packaging/test metadata and deprecation cleanup, current documentation, generated-cache tracking, and cleanup of already-merged branch state. The plan records scope; [STATUS.md](../STATUS.md) and [HANDOFF.md](../HANDOFF.md) record actual outcomes. Do not infer that an unresolved check passed.

## Completed implementation

The latest completed product plan is [Per-step model choices](plans/per-step-model-choices.md), authorized 2026-09-23 and updated for GPT-6 Luna on 2026-09-25. Its confirmed audit fixes preserve selected models through setup checks, credential readiness, and offline desktop smokes.

Its completed predecessors are [Neutral evidence ownership](plans/neutral-evidence-ownership.md), [Explicit pipeline selection](plans/explicit-pipeline-selection.md), [SQLite status polling](plans/sqlite-status-polling.md), and [Deterministic deep-analysis concurrency](plans/deep-analysis-deterministic-concurrency.md). Earlier product/platform records remain at their stable paths.

## Release boundary

[Mac-first release and cache pricing](plans/mac-release-cache-pricing.md) records the delivery decision and historical evidence. macOS remains first; Windows release work is deferred. The five-submission paid acceptance allowance is exhausted, with no completed final report. Do not make further paid research calls without new explicit authorization. The unsigned Mac build has not passed public-release gates for live acceptance, clean-machine installation, minimum OS, signing, or notarization. The earlier Phase 2 Windows matrix is historical evidence and does not verify the current-version Windows build or installation.

## History

Completed plan files remain at their original paths for stable references. Historical phase instructions do not authorize current work. The [archive index](../docs/archive/INDEX.md) links the verbatim pre-Phase-2 record and the exact documents replaced on 2026-09-26. The compatibility pointer under `.agents/PLANS/` is not a second plan authority.
