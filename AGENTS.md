# Assistant instructions

## Current authority

The user subsequently requested committing the verified changes and redelivering the corrected app; see the [current plan’s delivery authorization](.agent/plans/private-surveillance-run-fixes-2026-10-02.md). Commit delivery and fresh local installer/reinstallation are complete; the new app is open for manual testing. This supersedes the preceding uncommitted boundary. Paid calls, saved-data edits, signing and public release remain outside scope.

The completed implementation authority is [Approved private-surveillance run fixes](.agent/plans/private-surveillance-run-fixes-2026-10-02.md), approved by the user with “Fix all issues.” Implementation, offline verification, installed Mac replacement and obsolete-copy cleanup are complete; see [verification](docs/verification/private-surveillance-run-fixes-2026-10-02.md). The new app is open for manual testing. Preserve immutable history and budgets; no new paid allowance, real-data mutation, automatic commit/push or public release is included. The preceding completed phases below remain historical.

The latest authority is the completed [Approved discrimination run fixes](.agent/plans/discrimination-run-fixes-2026-10-01.md). A–G implementation, offline verification, installed Mac replacement and obsolete-copy cleanup are complete; see [verification](docs/verification/discrimination-run-fixes-2026-10-02.md). The app is open for manual testing. Preserve immutable history and existing budgets. No new paid allowance, real-data mutation, automatic commit/push or public release is authorized. Stop at manual testing unless the user gives new direction. The sections below are historical.

The preceding request authorized [read-only discrimination run review](.agent/plans/discrimination-run-review-2026-10-01.md), completed in the [findings](docs/verification/discrimination-run-review-2026-10-01.md). Its proposed-fix selection boundary is superseded by the latest approval.

The user subsequently authorized a final obsolete-app rescan, opening the verified new app, and committing and pushing all pending changes on 2026-10-01. This supersedes only the preceding commit/push boundary; paid research, real-data mutation and public-release gates remain unchanged.

The preceding implementation authority is [Approved ALPR run fixes](.agent/plans/alpr-run-fixes-2026-10-01.md). The user approved all A–G findings from the preceding read-only review. All A–G fixes, offline verification, installed Mac replacement and obsolete-copy cleanup are complete; see [verification](docs/verification/alpr-run-fixes-2026-10-01.md). Preserve immutable saved runs, existing work, and paid-call/data/publication boundaries. Stop at manual testing unless the user gives new direction. Earlier plans below describe historical authority.

The user has now authorized [installation and obsolete-app cleanup — 2026-10-01](.agent/plans/install-audited-mac-app-2026-10-01.md).
It supersedes the audit's installation boundary and old generated-artifact retention,
while preserving source, saved research, credentials, and verification records.
Installation and cleanup are complete; see [verification](docs/verification/audited-app-install-2026-10-01.md).
Stop at the manual-testing boundary unless the user gives new direction.

The preceding completed audit is [Comprehensive code audit and confirmed-defect fixes —
2026-10-01](.agent/plans/comprehensive-code-audit-2026-10-01.md), explicitly requested
by the user with Luna subagents. Codewide review, confirmed defect fixes, and final
local checks are complete; see the [report](docs/audits/2026-10-01/README.md).
Existing real-data, paid-call, installation, and publication boundaries remain.
The single-bug task below is the verified starting state.

The preceding bug task is [Installed Mac testing: adaptive budget route failure —
2026-10-01](.agent/plans/reviewer-route-testing-fix-2026-10-01.md). It authorizes the
reported routing/UI fix, offline regressions, and a locally verified rebuilt app;
installation, publication, paid calls, and real-data changes remain outside scope.
The release work described below is the preceding authority.

The preceding release work is [Current Mac build and release-gate verification — 2026-09-28](.agent/plans/mac-current-build-release-verification-2026-09-28.md). Its unsigned test download is published; actual macOS 14/clean-machine and Developer ID signing/notarization remain open. The completed [Documentation audit — 2026-09-28](.agent/plans/documentation-audit-2026-09-28.md) and [Database integrity fixes](.agent/plans/database-integrity-fixes.md) precede it; the preceding [audit maintenance](.agent/plans/audit-maintenance.md) is also complete. The completed [per-step model choices plan](.agent/plans/per-step-model-choices.md) remains the latest product implementation. The [Mac-first release plan](.agent/plans/mac-release-cache-pricing.md) records the release boundary: Windows release work is deferred and the five-submission live-test allowance is exhausted.

Read [architecture](ARCHITECTURE.md), [conventions](CONVENTIONS.md), [decisions](DECISIONS.md), [status](STATUS.md), [handoff](HANDOFF.md), [.agent/PLANS.md](.agent/PLANS.md), the applicable plan, and [desktop operations](desktop/README.md) before editing. Follow more specific nested instructions where they apply. The exact preceding root documents are preserved in the [archive index](docs/archive/INDEX.md); this file replaces their stale current-scope narrative.

## Required rules

- Stop at the authorized scope. Do not start further work without explicit user direction.
- Use strict Pydantic models (`ConfigDict(extra="forbid")`) for internal agent handoffs. JSON belongs at persistence, API, logging, and export boundaries; never pass raw dictionaries between agents.
- Annotate every named parameter and return on repository-owned Python functions, including tests and nested functions. Only conventional `self` and `cls` receivers may be unannotated. `tests/test_type_contracts.py` enforces this rule.
- Preserve immutable evidence and final artifacts. Never weaken tests, remove assertions, skip checks, or lower acceptance criteria to make a change pass.
- Prefer a failing regression test before fixing a validator or integrity bug. Never silently return `None` on failure; raise a clear exception or return a typed failure.
- Do not add dependencies without first flagging them and receiving explicit approval when outside the authorized scope. Record any approved dependency change in the plan, status, and handoff.
- Do not implement out-of-scope provider calls, web retrieval, scraping, database changes, live agent behavior, or framework/SDK integrations.
- Do not run destructive Git commands such as hard reset, clean, or force-push unless explicitly instructed. Preserve in-progress work and avoid unrelated edits.
- Do not remove architecture, convention, decision, status, handoff, or plan content without stating its replacement and keeping the historical record.
- Update STATUS.md and HANDOFF.md with actual changes, verification, unresolved issues, and the next boundary. Never claim an upgrade or release gate passed without its evidence.
- Before phase completion, run `pytest`, `ruff check .`, and `ruff format --check .` as required by the applicable plan; preserve existing skips and report results accurately.

If architecture and conventions conflict, resolve the documentation mismatch with a minimal explicit change before implementation.
