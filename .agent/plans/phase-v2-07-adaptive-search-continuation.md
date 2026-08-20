# ResearchAssistant v2 — Phase 7: Adaptive Search Continuation

Status: Complete and verified on 2026-08-20.

## Scope

- Continue only from a completed v2 Gap Analysis decision. A stop decision creates no
  Round-2 plan or provider work.
- Use the configured MiMo-v2.5-Pro Search Agent to create strict, gap-linked Round-2 or
  narrow Round-3 queries from persisted Gap IDs, discovered terminology, previous query
  history, enabled directions, and eligible enabled providers.
- Reject normalized repeats and clearly trivial rewrites without embeddings. Application
  policy owns provider/round lanes, hard ceilings, enabled-direction isolation, IDs,
  timestamps, persistence, and the absolute three-round limit.
- Reuse the existing v2 discovery normalization/clustering, batched Scout, safe acquisition,
  deterministic Probe, and survivor artifacts with round-specific append-only keys.
- Run Luna Gap Analysis again after Round 2. Adapt the deterministic Research Governor for
  v2 Round-3 authorization; Luna recommends and application policy authorizes.
- Preserve a complete search-reservation boundary for protected downstream budget and stop
  when cancellation, provider eligibility, novelty, duplicate saturation, failure, or hard
  ceilings prevent useful continuation.
- Persist each round plan and execution summary, targeted Gap IDs, status, new/duplicate
  source counts, survivor additions, merged survivors, and the final stopping decision/reason.

## Hard limits

- At most three research rounds; no Round 4 or recursive continuation.
- Round 3 is narrow and never performs a broad provider sweep.
- No disabled direction or disabled/ineligible provider work.
- No automatic citation tree, live provider call in verification, dependency, or migration.

## Verification

Offline tests cover one-, two-, and three-round paths; gap-directed queries; Round-2 and
Round-3 stopping; provider eligibility and exhaustion; duplicate-heavy stopping; query
novelty; restart after every round boundary; cancellation; provider degradation; direction
isolation; and the hard three-round maximum. Complete pytest, Ruff lint/format, and
`git diff --check` must pass.
