# Historical ResearchAssistant v2 — Phase 10: Reviewer and Claim Ledger Integration

Status: Complete and verified.

Authorized 2026-08-24 correction: historical Phase-10 execution permitted one independent Reviewer
call per source. Rejection is terminal for that source and is handled by the Phase-12 typed
deterministic backfill; no Analyst revision or second Reviewer call occurs. Existing Reviewer
validation and immutable Ledger admission are unchanged.

## Scope

- Consume the complete, append-only Phase-9 Analyst result and reuse the existing narrow
  `ReviewerInput`, `ReviewerDecision`, application-derived `rappr_v1` approval ID,
  deterministic score-pair placement, and `admit_ledger_record` validation.
- Route historical v2 Reviewer audits only to MiMo-v2.5-Pro. The Reviewer receives no claim,
  stance, Evidence Quality, source-selection, or provenance context and never supplies
  replacement wording or approval IDs.
- Permit one independent Reviewer audit. A rejection admits no Ledger record and is terminal
  for the source; the next survivor is selected by Phase-12 deterministic backfill.
- Persist each admitted v2 `LedgerRecord` beside immutable v2 provenance: research
  direction, discovery round, source family, recommendation flag, survivor ID, and
  relevant Gap IDs. Recommendation remains provenance only, never an admission rule.
- Reject any historical v2 source whose direction is disabled before the Reviewer is invoked.
- Add the migration-13 append-only `v2_ledger_admissions` sidecar. It leaves historical
  `ledger_records` rows unchanged and retains their existing immutable triggers.

## Hard limits

- Do not introduce a Reviewer confidence field, `APPROVE_WITH_LIMITS`, a new quality
  judge, or Reviewer-authored replacement wording.
- Do not change score-pair eligibility, Claim Fit mapping, placement derivation,
  `QUALIFIED_ONLY`, Ledger admission validation, or historical Ledger data.
- Retain at most two Reviewer calls per source, as already reserved by the Phase-8 queue.
- No live model, search, or acquisition call is permitted during implementation or tests.

## Verification

Offline tests cover approval, rejection/revision, qualified-only admission, Claim Fit
mapping, recommended and non-recommended provenance, disabled-direction rejection,
approval IDs, immutable SQLite admission rows, migration compatibility, restart reuse,
and the existing release/type-contract suites. Run the full pytest suite, Ruff lint and
format checks, and `git diff --check`.
