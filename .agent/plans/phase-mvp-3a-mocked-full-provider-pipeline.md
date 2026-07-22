# Phase MVP-3A - Mocked Full-Provider Pipeline Integration

## Prerequisite and Purpose

Begin only after the production-intended MVP-2B adapters and boundary tests pass.
Connect only the approved adapters to `run_provider_pipeline()` using realistic mocked
HTTP/provider responses. Normal tests remain network-free. Do not run a full live canary,
add the live CLI, modify Streamlit, or begin MVP-3B.

## Provider Construction Boundary

Create the narrowest strict Pydantic provider factory/configuration boundary that:

- validates configuration before a run;
- constructs only Wigolo acquisition/normalization and OpenRouter LLM adapters;
- maps every internal role to `xiaomi/mimo-v2.5-pro` primary and
  `minimax/minimax-m3` only fallback;
- validates structured-output, temperature, usage, and pricing capabilities;
- redacts secrets from representations and errors; and
- documents and tests thread safety.

Preferred thread strategy: immutable shared configuration plus a thread-safe HTTP client
or separate lightweight adapter/client instances per Researcher worker. Do not share
mutable request state or SQLite connections.

## Complete Mocked Pipeline

Exercise Planner, both concurrent Researchers, Search discovery, controlled acquisition,
normalization, Extractor, deterministic quote filtering, Analyst, Reviewer,
application-owned approval IDs, Ledger admission, Synthesizer, deterministic Renderer,
and final validation. Cover released, blocked, failed, and cancelled states without live
network access.

Keep rank-five/keep-three acquisition, at most eighteen snapshots, at most thirty ranked
source candidates, narrow digital-PDF behavior, immutable normalized snapshots, and
exact quote offsets.

## Normalized Failures

Test missing credentials/configuration, authentication failure, timeout, rate limit,
transient outage, permanent provider failure, malformed Search response, inaccessible
source, unsupported type, malformed/refused LLM output, schema failure, returned-model
mismatch, unknown pricing, fallback exhaustion, token exhaustion, cost exhaustion, and
cancellation observed at every documented boundary.

## Retry, Fallback, and Budgets

- Permit primary, primary retry, fallback, and fallback retry only for approved objective
  failures.
- Never route on semantic disagreement or low Analyst/Reviewer scores.
- Reserve calls/tokens/cost before every physical call and reconcile exact usage after.
- Preserve usage from failed, malformed, and deterministically rejected responses.
- Charge retries and fallback to the same persisted total-run budget.
- Never begin fallback when remaining budget cannot reserve it.
- Fail closed on unknown/unreliable pricing or route identity.

## Persistence, Restart, and Cancellation

Verify normalized attempts and complete provider/adapter/model/prompt/schema/
normalization/policy identities are persisted. Exact same run ID, claim, and fingerprint
may resume; changed claim or incompatible fingerprint is rejected. Valid checkpoints are
skipped, attempts/budgets are preserved, and snapshots, Ledger records, and released
output are never duplicated. Reconstruct released briefs from persistence and document
terminal-run reinvocation.

Cancellation is cooperative: persist requests; check before/after provider calls and at
orchestration boundaries; start no new call after observation; allow an active blocking
request to finish or reach its deadline; never claim immediate interruption.

## Minimum Tests

Include realistic mocked runs for release, deterministic block, normalized provider
failure, budget exhaustion, restart, cancellation, and fallback. Add focused tests for
every failure and persistence contract above.

## Scope and Verification

Do not run a full live canary, add a live CLI, modify Streamlit, add another provider,
add new browser automation, add hosting/FastAPI/Docker/accounts, or redesign
orchestration.

Run focused integration, restart/cancellation, full suite, offline evaluation, Ruff,
fixture CLI smokes, mocked full-pipeline smoke, `git diff --check`, and Git status.
Report exact files, factory design, aliases, thread strategy, pipeline states, retry/
fallback behavior, budget accounting, restart/cancellation guarantees, remaining risks,
and confirmation that no live canary/CLI/frontend work occurred. Leave changes
uncommitted.

