# Current plan state

## Repository delivery authorization — 2026-10-01

The user explicitly requested a final obsolete-app cleanup, opening the new app,
and committing and pushing all current changes. The installed app's source/export
parity and normal launch were rechecked successfully; no research was started.
Luna precommit review found no credentials, user data, databases, build outputs or
installers among pending repository files. Ruff/format and whitespace checks passed;
the existing full 1,283-pass / 2-skip suite applies to the unchanged tested source.
The final name-only scan found only the installed Applications app and no named
installers or mac-arm64 folders in accessible locations. An obsolete backend build
cache in Codex worktree 3020 was removed; seven text records were archived. One
Google Drive CloudStorage location was unreadable and remains unchecked.
The remote branch was checked before delivery. Git history records the authorized
commit; the delivery result is verified against the remote after pushing. Earlier
uncommitted/no-push statements below record the preceding verification phases.
Paid research and signed/live/platform release gates remain outside this delivery.


## Approved ALPR fixes installed — 2026-10-01

All user-approved findings A–G are implemented and verified with three Luna helpers.
See the [verification record](../docs/verification/alpr-run-fixes-2026-10-01.md) for admitted-only evidence, actual relationship
labels, Ledger-bound citations, current stopping/coverage disclosures, source
outcomes, optional future usage splits and conservative study-lineage notices.
Full pytest passed **1,283 tests / 2 unchanged skips**, warnings as errors; Ruff,
frontend/export, offline/API/browser and rebuilt/installed native/window gates passed.

Use `/Applications/ResearchAssistant.app`. Exact parity covers **101 source inputs,
22 frontend files and 30,929 installed payload entries**. Backend SHA-256:
`d561b04e95a2745792e8d76143e30cb4fefe0a9f314e2d74286b85fed302480c`.
The old app, redundant mac-arm64 candidate and temporary backend build/cache copies
were removed. Saved research, credentials, source and verification records remain;
all 233 saved-run artifact hashes and the released brief hash are unchanged.
Historical exports remain frozen; reopen saved research for the corrected display.
Normal launch passed with the installed app and its owned backend running from
Applications; unauthenticated health returned 401.

Changes remain uncommitted. No provider calls, new dependencies, schema migration,
publication or push occurred. Historical input/output/cache splits remain unknown;
the supplied-rate estimate is $0.06 and the saved total remains $0.057952460.
Stop at manual testing; fresh research must obey the existing identity gate. No new
paid allowance or live-quality, clean-machine/macOS 14, signing or notarization gate
is established. Earlier sections below are historical and superseded where this
completed approval applies.


## ALPR run review; fixes pending decision — 2026-10-01

[Read-only ALPR assessment](plans/alpr-run-review-2026-10-01.md) is complete; see
[findings A–G](../docs/verification/alpr-run-review-2026-10-01.md). Source/app/data
remain unchanged. The user explicitly reserves approval of fixes; no implementation
or new paid call is authorized by the review.

## Audited Mac installation and cleanup — 2026-10-01

[Install audited app and remove obsolete copies](plans/install-audited-mac-app-2026-10-01.md)
is complete. The verified new app is installed/open in Applications, artifact-specific
checks passed, and obsolete local app/installer/mac-arm64 copies were removed. See
[verification](../docs/verification/audited-app-install-2026-10-01.md). Saved research,
credentials, source, and verification records remain. No new paid allowance or
release publication is included.

## Comprehensive code audit — 2026-10-01

[Comprehensive audit and confirmed-defect fixes](plans/comprehensive-code-audit-2026-10-01.md)
was authorized by the user's request to scour the codebase with Luna subagents and
fix all confirmed issues. It is complete: all confirmed in-scope repairs and final
source/rebuilt-app checks passed. See the [report](../docs/audits/2026-10-01/README.md)
for nine area reviews, the 206-input ledger, 1,256 passing tests / 2 unchanged skips,
frontend/native evidence, artifact hashes, and limits. Existing paid-call, real-data,
installation, and release boundaries remain; changes are uncommitted.

## Installed Mac testing fix — 2026-10-01

[Adaptive budget route failure](plans/reviewer-route-testing-fix-2026-10-01.md)
records the reported missing Reviewer route and contradictory failed-run evidence
message. Offline reproduction, the bounded fix, and local rebuilt-app verification
are complete; see [verification](../docs/verification/reviewer-route-testing-fix-2026-10-01.md).
No new paid allowance or installation/publication is included.

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
