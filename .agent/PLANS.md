# Phase plans

Current implementation scope is the completed [Per-step model choices](plans/per-step-model-choices.md),
explicitly authorized on 2026-09-23, including the confirmed post-audit fixes recorded in the current
status and handoff. It follows the completed neutral evidence ownership, explicit pipeline-selection
and SQLite status-polling phases and preserves the Mac-first release boundary. Earlier dated scope
statements below remain historical.

Completed latest phase: [Per-step model choices](plans/per-step-model-choices.md), authorized by the user
on 2026-09-23. Each active fresh-v2 stage now has an explicit selectable model choice; the confirmed
audit fixes preserve those choices through setup checks, credentials readiness and offline desktop smokes.

Completed predecessor: [Neutral evidence ownership](plans/neutral-evidence-ownership.md), authorized by the
user after the explicit pipeline-selection review. Fresh v2 stages now import neutral evidence helpers directly;
historical agent paths remain compatibility facades.

Completed predecessor: [Explicit pipeline selection](plans/explicit-pipeline-selection.md),
authorized 2026-09-20 and verified 2026-09-21. Its predecessor is [SQLite status polling](plans/sqlite-status-polling.md),
authorized 2026-09-19 and verified 2026-09-20.

Earlier completed work: [Deterministic deep-analysis concurrency](plans/deep-analysis-deterministic-concurrency.md),
explicitly authorized on 2026-09-18 to address the serial fresh-v2 bottleneck without
changing acquisition, routing, budgets, deadlines or evidence policy. The Mac-first plan
remains the release/distribution authority; its exhausted paid-test limit still applies.

The 2026-09-17 [MLP readiness audit and proposed next steps](plans/mlp-readiness.md)
records the user-requested repository review and safe documentation corrections.
Its product/accounting decisions were subsequently resolved by the active plan below.

Release authority: [Mac-first release and cache pricing](plans/mac-release-cache-pricing.md),
authorized by the user's follow-up to the readiness audit, then extended explicitly to
planner/Scout reliability before distribution. Windows release work is deferred.
Earlier completed work is [Adaptive search reliability](plans/adaptive-search-reliability.md),
explicitly authorized by the user's implementation request on 2026-09-12. It narrowly
extended the Phase 3 research-behavior boundary; the new plan adds the bounded Mac/pricing work above.

[Phase 3 — Frontend and provider/model settings](plans/phase-3-frontend-settings.md) and
[Phase 2 — Codebase and Documentation Cleanup](plans/phase-2-cleanup.md) are preceding
completed records. Their remaining platform and release checks are still tracked where
they apply; the Mac/pricing plan retains the release boundary while the selection plan above
authorizes the current implementation follow-up.

The [Phase 1 desktop plan](plans/phase-1-desktop.md) retains the original implementation
and verification record, including its originally open Windows and public-release gates.
The linked Phase 2 record supplies later native build/runtime verification; installation
and signing gates remain. It is a prerequisite record, not a second active implementation
plan.

The latest completed research-policy phase is [v2 Phase 14 — Conditional Round Four](plans/phase-v2-14-conditional-round-four.md).
Phase 2 preserved that policy; the later adaptive correction adds bounded fresh-run
reliability behavior while retaining historical contracts.

Completed plan files remain at their original paths for stable references. The
[archive index](../docs/archive/README.md) lists them and links the verbatim
[previous plan index](../docs/archive/pre-phase-2/.agent/PLANS.md), replacing its
chronological current-state narrative. Historical next-phase instructions do not
authorize new work. `STATUS.md` and `HANDOFF.md` at the repository root are current.
