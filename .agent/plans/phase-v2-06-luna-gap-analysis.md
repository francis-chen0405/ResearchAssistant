# ResearchAssistant v2 — Phase 6: Luna Gap Analysis

Status: Complete and verified on 2026-08-20.

## Scope

- After immutable Phase-5 survivors exist, build one bounded typed Round-1 strategy input from
  the exact claim, enabled directions, attempted queries, survivor metadata, Probe excerpts,
  conservative source-family/duplicate data, discovered terminology, acquisition failures,
  optional previous gaps, and remaining budget state.
- Use no source document content beyond at most 40 Probe excerpts, each capped at 1,200
  characters. Gap Analysis is routed only through the configured GPT-5.6 Luna High route.
- Persist a strict completed result with coverage summary, priority-ordered material gaps,
  continue/stop decision, specific typed later-search directions, and discovered terms.
- Enforce no more than three material gaps for either enabled direction, require every gap and
  later-search direction to stay in an enabled direction, and prohibit a stopping decision from
  inventing gaps or search directions.
- Retry the same Luna route at most once. If all permitted attempts fail, persist a degraded
  output with no result, no invented gaps, and `stop_adaptive_continuation=True`.
- Reuse the persisted output exactly on restart without another Luna call.

## Explicitly out of scope

- Round-2 or Round-3 planning/execution, discovery, Scout, acquisition, source selection,
  deep analysis, Ledger evidence, factual claims, UI work, migrations, dependencies, or live
  provider calls.

## Completion signal

Offline tests cover support-only, challenge-only, and both directions; disabled-direction
rejection; bounded Probe input; typed gap-linked search directions; stop after Round 1; Luna
route/reservation auditing; bounded retry/degraded handling; and restart reuse. The full suite,
Ruff lint/format, and diff check pass with no live calls.
