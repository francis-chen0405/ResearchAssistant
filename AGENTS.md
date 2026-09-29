# Assistant instructions

## Current authority

The latest authorized work is [Current Mac build and release-gate verification — 2026-09-28](.agent/plans/mac-current-build-release-verification-2026-09-28.md). Its unsigned test download is published; actual macOS 14/clean-machine and Developer ID signing/notarization remain open. The completed [Documentation audit — 2026-09-28](.agent/plans/documentation-audit-2026-09-28.md) and [Database integrity fixes](.agent/plans/database-integrity-fixes.md) precede it; the preceding [audit maintenance](.agent/plans/audit-maintenance.md) is also complete. The completed [per-step model choices plan](.agent/plans/per-step-model-choices.md) remains the latest product implementation. The [Mac-first release plan](.agent/plans/mac-release-cache-pricing.md) records the release boundary: Windows release work is deferred and the five-submission live-test allowance is exhausted.

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
