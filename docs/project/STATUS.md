# Project status

## What the app does

ResearchAssistant is a local desktop app for investigating a precise claim. It searches
for supporting and challenging sources, captures source text, checks exact quotations,
and produces evidence-backed reports within configured budgets. Saved research can be
inspected and released reports exported. Credentials stay in the operating system's
credential store; research data stays outside the application bundle.

## What currently works

Current source uses assessed findings to guide further searches, replaces unusable
sources within existing limits, captures later PDF pages with explicit omissions,
and performs a bounded follow-up when analysis leaves evidence gaps. Reports retain
source provenance, quotation checks and conservative cost accounting. The CLI defaults
remain 20 sources per direction and metadata search depth 50. The old native execution
engine is retired; historical inspection, evidence browsing and released exports
retain their original validation and hashes.

Progress screens preserve the last confirmed state when the connection fails and let
the user reconnect to the same run. Cancellation is confirmed by the backend before
the screen reports it as requested. Recorded source, renderer, browser and distribution
checks passed; see the [integration](../../.agent/plans/source-loss-recovery-2026-10-19.md#master-integration--october-23)
and [progress recovery](../../.agent/plans/recoverable-progress-polling-2026-10-23.md)
evidence. These are previously recorded results, not new installation or quality acceptance.

## Known problems and limits

The fresh unsigned Mac candidate passes isolated acquisition readiness checks after
packaging its Python runtime's previously omitted certificate-policy file unchanged.
Full desktop acceptance and installation remain pending. The installed Mac build,
`20261020.6`, predates the later PDF, post-analysis, final CLI and progress recovery
changes; [its delivery record](../verification/selection-coverage-repairs-2026-10-21.md)
describes what was actually installed.

Offline checks do not establish better live research. Actual IPBES PDF recapture and
human evaluation remain outstanding. Provider/page scheduling, partial-unknown stop
reporting and an earlier Planner rejection remain open investigations; [the retry review](../verification/extinction-risk-retry-review-2026-10-21.md)
and [subsequent reporting repairs](../verification/selection-coverage-repairs-2026-10-21.md)
explain the evidence and partial progress. [Manual asset review](../audits/2026-10-15/remaining-file-review.json)
also remains incomplete.

Windows packaging is manual-only. Its acquisition startup failure, interrupted-upgrade
repair and remaining native acceptance checks are open. Public release, Mac signing
and notarization, clean-machine/minimum-OS testing, and physical power-loss durability
remain unverified. [Windows evidence](../verification/windows-ci-durability-2026-10-13.md)
and [desktop operations](../../desktop/README.md) retain the specific gates.

## What comes next

Complete broader desktop acceptance on the fresh Mac candidate in a separate chat
before any installed-app replacement. Packaging and isolated acquisition readiness
are verified, with the existing deadline unchanged. The next research-quality step
is controlled live recapture and human evaluation; the previous paid-test allowance is exhausted,
so further paid work needs new explicit authorization. Windows acceptance remains a
separate delivery effort.

Preserve saved research, credentials, historical policies and exact resume compatibility
throughout. Unknown request outcomes must retain their reservations and must not
trigger duplicate calls. [Work navigation](../../.agent/PLANS.md) links follow-up owners;
[conventions](CONVENTIONS.md) govern changes and verification.
