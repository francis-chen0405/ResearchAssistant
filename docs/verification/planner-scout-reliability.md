# Planner/Scout reliability follow-up

The user selected research reliability before wider Mac distribution after the bounded
Mac/cache acceptance exposed failures. This continues the
[authorized plan](../../.agent/plans/mac-release-cache-pricing.md). The same five-submission
limit applies; no additional paid test is authorized by this follow-up.

## Evidence and implemented corrections

The original live planner failure reported only `claim_coverage_focus:value_error`.
Its exact rejected response is unavailable. Offline reproduction found a concrete
schema/validator contradiction: the generic coverage model advertised omitted/null
`kind`, but the planner required `claim_component`. The fresh model-facing subtype now
advertises only the three permitted claim dimensions, a concrete claim-component default,
searchable true and no unavailable reason. Explicit invalid/null values remain rejected.
Duplicate dimensions have a stable sanitized error code. The prompt states uniqueness
and fixed values. Generic historical coverage and persisted artifacts are unchanged.
This fixes a reproduced defect; it does not prove the original failure's exact cause.

In original run 4, 30-candidate Scout batches produced three truncated responses across
four attempts; one batch fell back after its two failures. Later 20- and 15-candidate
batches succeeded without retries. New batches are capped at 20. Round 4's reservation
uses the same batch-size constant and includes both possible attempts for every batch.
Historical typed artifacts still allow their old 30-item batches. Candidate mapping,
validation and deterministic fallback remain intact. Smaller batches can increase call
count; the total run budget and physical-call accounting still enforce the same ceilings.

Regression tests reproduced four planner failures and two Scout/reservation failures
before fixes. They verify valid defaults, forbidden cases, private-data-free diagnostics,
51-candidate batching (20/20/11), bounded retries, restart persistence and the rejection
of an underfunded Round-4 reservation.

## Response allowance correction

The user separately chose larger responses within the same total budget. The Standard
profile now gives Pro 8,192 and Luna High 16,384 completion tokens; Scout stays at 4,096.
Six failing regressions demonstrated the prior allowance before the change. Tests
verify actual HTTP payloads, full cost/token reservations, preflight rejection and
fingerprint differences. Legacy unprofiled defaults stay at 4,096. No retries, timeouts,
total run ceilings or protected source budgets increase. This is a bounded mitigation
for observed truncation, not proof of live improvement; larger calls may take longer.

## Verification and Mac delivery

992 Python tests passed, with two existing opt-in skips and the existing Starlette
warning. Ruff lint/format, diff whitespace and the 38-case frozen evaluation passed.
Native rebuilt-backend smoke passed: authenticated local UI/API, isolated vault cleanup,
durable settings and owned service lifecycle. Packaged actual-window smoke and isolated
old-to-new upgrade checks passed, preserving credentials/preferences and byte-identical
historical fixture data. No validation assertion or timeout was weakened.

The packaged frontend matches the previously verified static export; 96 loose Python,
prompt and project-manifest files match current source byte-for-byte. The bundle declares
macOS 14.0. DMG verification and ZIP integrity passed. The app was installed while closed,
with the previous bundle at
`/private/tmp/ResearchAssistant-before-reliability-x59milnf/ResearchAssistant.app`.
Real history, preferences and credentials were not replaced. Installed-window smoke
also passed; the app closed normally after the isolated check.

Downloads are in `desktop/dist/mac-reliability/`:

- `ResearchAssistant-0.1.0-arm64.dmg` — SHA-256
  `c3f6db2217797a8ff7db9056391fb51c7bd88b8b2a3b1a868b32dd0e3352edfb`
- `ResearchAssistant-0.1.0-arm64-mac.zip` — SHA-256
  `a1c295ab00a2a8ce731ea83f1e89ff50bddf40eb0e3a4523f55e1d98f4b112d0`
- `SHA256SUMS.txt` and `READ-ME-FIRST.txt`.

These supersede the earlier Mac/cache candidate. They remain unsigned test downloads;
clean-machine and actual macOS 14 checks, Developer ID signing/notarization and public
distribution remain open. No remote publication occurred. The original live acceptance
uses the prior frozen Mac/cache build, not these fixes. No end-to-end live quality or
latency acceptance is claimed by passing offline/native regressions.

The original five submissions have now finished: a harness cancellation, rejected
overlap, planner failure and two cancellations after the 20-minute acceptance cutoff.
Recorded model exposure totals $0.178617536, excluding source-service charges. No final
report was released. The backend stopped; no additional paid run was submitted.

Next steps: obtain a separately authorized small acceptance allowance for this exact
installed build; verify completed reports, source relevance/quotation quality and stage
timings rather than treating launch success as research acceptance. Investigate remaining
timeouts or truncation from that evidence before altering deadlines or retry policy.
Then perform clean-machine/macOS 14 installation checks and decide when to obtain Apple
signing/notarization for wider distribution. Windows remains deferred.
