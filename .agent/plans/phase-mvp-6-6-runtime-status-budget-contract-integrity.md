# MVP-6.6 — Runtime Status, Budget, and Contract Integrity

## Authority and Boundary

MVP-6.5 is the complete prerequisite. The user explicitly authorized MVP-6.6 to correct
RUNNING process exit semantics, make model-usage accounting complete and conservative,
and make `ProviderRunContract` immutable and self-consistent. This phase does not include
the remaining repository-wide type-hint work. MVP-6.7 has not started.

No dependency, SQLite migration, live provider call, or commit is authorized or needed.
Valid historical canonical provider contracts must remain readable; inconsistent stored
contracts must fail rather than be repaired.

## RUNNING Exit Semantics

- Add stable `CLIExitCode.RUNNING = 13`.
- Map every `ProviderRunStatus` explicitly: RELEASED 0, BLOCKED 10, FAILED 11,
  CANCELLED 12, and RUNNING 13.
- Exit 0 represents a released research result or a separately documented successful
  administrative acceptance such as a persisted cancellation request. It never
  represents a nonterminal research result.
- RUNNING output identifies the current stage and never prints or implies a released
  brief. Direct calls, inspection, subprocess behavior, and the live-web status surface
  use the same semantics. Unsupported statuses fail clearly instead of falling through.

## Complete Usage Accounting

- Add one strict immutable Pydantic accounting summary containing exact totals (or
  unknown), known subtotals, token/cost completeness, missing-usage attempt IDs, and
  conservative reserved exposure.
- Zero physical attempts have exact token and cost totals of zero and are complete.
- Every persisted physical attempt is conservatively charge-capable. Token usage is
  known from `total_tokens` or from both input and output tokens; partial token fields
  remain unknown. Cost is known only when explicitly recorded.
- Any missing component makes its exact total unknown. Known values remain separately
  labeled subtotals and are never displayed as totals.
- Running, failed, timed-out, interrupted, or otherwise incomplete attempts are not
  assumed free. No error-message parsing is used to infer pre-dispatch failure.
- `ProviderPipelineResult.total_tokens` and `total_cost_usd` remain compatibility fields,
  but contain exact totals only: zero for zero attempts and `None` when incomplete.
- Atomic pre-call enforcement uses exact actual usage when available and the full
  persisted reservation for unknown usage. Missing actual usage plus missing usable
  reservation fails closed because remaining budget cannot be proven. Retry and fallback
  share this rule and physical-call ceilings remain unchanged.
- Exa and Firecrawl billing remains external to MiMo model-call accounting.

## Immutable Self-Consistent Provider Contract

- Freeze `ProviderRunContract` while preserving `extra="forbid"`; all contained values
  are immutable scalars.
- Put strict JSON loading, duplicate-key rejection, exact payload-shape validation,
  canonical sorted compact serialization, and SHA-256 derivation in one dependency-light
  helper used by both factories and the model validator.
- The exact payload contains the existing fingerprint version plus provider, adapter,
  model, prompt, schema, normalization, policy, and repository identities. `run_id` and
  `created_at` remain excluded from the payload and fingerprint.
- Construction and persisted reconstruction reject invalid JSON, duplicate/missing/extra
  keys, non-string values, noncanonical bytes, duplicated-field mismatches, repository
  mismatch, and incorrect hashes. Stored bytes are never normalized or rewritten.
- Keep the current fingerprint version unless the canonical payload inputs change; this
  phase validates the already-required representation rather than invalidating valid
  historical canonical records.

## Regression and Verification

Add regression tests before fixes for all status mappings and subprocess behavior;
zero/complete/mixed/partial/running/failed usage, reservation enforcement, retry and
fallback; inspection/reopening and CLI/web labels; valid and tampered provider contracts,
immutability, persistence, resumption, historical compatibility, and shared builder
algorithm.

Run focused CLI, provider inspection, accounting/budget, retry/fallback/cancellation,
contract persistence/compatibility, MVP-4, MVP-5, and Phase 9 tests; the full pytest
suite; all offline evaluations; Ruff lint and format checks; Python compilation;
launcher shell syntax; and `git diff --check`. Inspect all status mappings, usage
calculations/displays, and provider-contract construction/read paths. Record exact final
results in `STATUS.md` and `HANDOFF.md` only after every required check passes.

## Completion Record

MVP-6.6 is complete. The required focused selection passed 143 tests with one expected
opt-in skip; the full suite passed 578 tests with two expected opt-in skips; all 38
offline evaluation cases passed. Ruff lint/format, 61-file in-memory compilation,
launcher syntax, CLI help, `git diff --check`, and final scope/artifact audits passed.
No dependency, SQLite migration, provider call, spending, generated tracked artifact,
commit, MVP-6.7 work, or repository-wide type-hint work was added.
