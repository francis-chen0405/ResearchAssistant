# ResearchAssistant v2 — Phase 9: Luna Evidence Analyst

Status: Complete and verified.

Authorized 2026-08-24 correction: fresh Phase-9 execution performs only the assessment and
canonical-draft Analyst operations (each bounded to two attempts). The Analyst request carries
the exact candidate quote block, immediate context, and typed source metadata, not the complete
normalized snapshot. Reviewer-directed revision remains available only as a historical/direct
compatibility API and is not part of normal Phase-10 recovery.

## Scope

- Consume only the deterministic Phase-8 deep-analysis queue and exact, application-
  assembled `CandidateQuoteBlock` artifacts.
- Preserve MiMo-v2.5-Pro as the v2 Extractor route. The Extractor selects exact snapshot
  passages only; application code continues to own assembly, context brackets, offsets,
  exact membership, provenance, and candidate verification.
- Route fresh v2 Analyst assessment and canonical statement drafting to GPT-5.6 Luna High.
- Keep source text, the narrowest supported proposition, and its relationship to the exact
  requested claim as separate typed fields. Retain material limitations, inferential
  boundaries, and reasoning.
- Reuse the existing Evidence Quality / Claim Fit score-pair table, placement derivation,
  Claim Fit 3 qualification check, `ScoreDecision`, and `StatementDraft` construction.
- Enforce support/challenge isolation in application validation while permitting an attached
  qualification in either enabled direction.
- Reserve every physical Luna attempt through `model_route_attempts` using the configured
  route's exact token and cost reservation. Retry each Analyst operation once.
- Persist a result for every Phase-8 survivor. On exhausted Analyst failure, retain the exact
  candidate, record failure, create no Reviewer-ready draft, and never admit a Ledger record.
- Reuse append-only v2 artifacts for restart; add no database migration or dependency.

## Hard limits

- Phase 9 never changes quote text, offsets, hashes, IDs, or provenance.
- Phase 9 never calls the Reviewer or creates a `LedgerRecord`; existing downstream Reviewer
  approval and deterministic Ledger validation remain mandatory.
- A disabled or opposite direction relationship is rejected even if the model returns it.
- Claim Fit 3 output cannot become Reviewer-ready without explicit scope qualification.
- No more than two physical attempts occur for one Analyst logical operation.
- No live model call is permitted during implementation or verification.

## Verification

Offline tests cover Luna routing, unchanged quote provenance, narrow propositions, Claim Fit
3 qualification, direction isolation, limitations, bounded retry/failure, survivor retention
without Ledger admission, physical token/call/cost accounting, restart, and historical MiMo
Analyst readability. Run the focused tests, full pytest suite, Ruff lint and format checks,
and `git diff --check`.

Final verification: 7 focused Phase-9 tests passed. The complete offline Python suite passed
with 742 tests, 2 expected opt-in skips, and the pre-existing Starlette deprecation warning.
Ruff lint, Ruff format check, and `git diff --check` passed. No live call occurred.
