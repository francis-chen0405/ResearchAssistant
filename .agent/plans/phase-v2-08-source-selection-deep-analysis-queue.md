# ResearchAssistant v2 — Phase 8: Source Selection and Deep-Analysis Queue

Status: Complete and verified.

## Scope

- Preserve the complete useful survivor pool merged across every completed v2 research round.
- Use the configured MiMo-v2.5-Pro Source Selection route to recommend an ordered,
  complementary subset for each enabled direction from only persisted survivors.
- Provide the model with the exact claim, enabled direction, compact source metadata,
  conservative source-family identity, deterministic Probe passages, material Gap history,
  and search-round provenance. Reject invented, repeated, wrong-direction, or
  family-dominated recommendations.
- Treat recommendation as prioritization only. It creates no evidence, score, Claim Fit,
  Evidence Quality, Reviewer approval, Ledger eligibility, or factual proof claim.
- Retry Source Selection once for objective failure. After retry exhaustion or insufficient
  safe budget, use deterministic complementary source ordering and continue without deleting
  a survivor.
- Build a bounded deep-analysis queue with recommended survivors first and complementary
  non-recommended survivors second.
- Compute a safe queue prefix before deep analysis using the remaining 160-call ceiling,
  one retry per logical operation, one Extractor operation, three possible Analyst operations,
  two possible Reviewer operations, two mandatory Synthesis attempts, and conservative
  route-specific token/cost reservations.
- Persist one explicit status for every survivor: recommendation state, queue state, ranks,
  and a stable reason when physical-call, token, or cost reserve prevents deep analysis.
- Reuse the append-only generic v2 artifact boundary; add no migration or dependency.

## Hard limits

- No source outside the persisted survivor input may be recommended or queued.
- Recommendation normally targets at most ten sources per enabled direction and is not a quota.
- A source family cannot dominate the recommendation prefix while unused families remain.
- The queue is a deterministic priority prefix; lower-priority work cannot displace a higher-
  priority source that cannot be safely reserved.
- Physical model calls may never exceed 160, including retries and mandatory Synthesis reserve.
- No live provider call is permitted during implementation or verification.

## Verification

Offline tests cover complete survivor retention, complementary selection, family diversity,
fallback ordering, queue math, physical-call and token reserve protection, one- and two-
direction runs, deterministic shrink, explicit statuses, and completed-run restart reuse.
Complete pytest, Ruff lint/format, and `git diff --check` must pass.

Final verification: 8 focused Phase-8 tests passed. The complete offline Python suite
passed with 735 tests, 2 expected opt-in skips, and the pre-existing Starlette deprecation
warning. Ruff lint, Ruff format check, and `git diff --check` passed. No live call occurred.
