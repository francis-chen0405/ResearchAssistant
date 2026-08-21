# ResearchAssistant v2 — Phase 11: Synthesis and Final Research Output

Status: Complete and verified.

## Scope

- Use MiMo-v2.5-Pro only to arrange a strict typed projection of the exact claim, enabled
  directions, Reviewer-approved Ledger statements, placement/entailment, qualifications,
  unresolved material gaps, deterministic stopping disclosure, and non-evidentiary
  recommendation metadata. Raw source/snapshot text and unreviewed claims are excluded.
- Preserve the existing `SynthesisOutput` factual-item contract and extend release validation
  with v2 direction, surviving-source, recommendation-ID, Ledger-admission, gap, stopping,
  and complete-rendered-output integrity checks.
- Expose recommended sources and the complete survivor pool with explicit analyzed,
  no-Ledger-evidence, not-deeply-analyzed, and budget-prevented states.
- Add a read-only local API endpoint, conditional Next.js v2 result rendering, and v2-aware
  local export. Historical output paths remain unchanged.

## Hard limits

- No raw-source reinterpretation in synthesis, no model-authored factual prose, no live
  provider call, no dependency, and no schema migration.
- Support-only and challenge-only releases do not create, display, or imply examination of
  the disabled side. Both-direction releases are not required to be artificially symmetric.
- An invalid v2 release receives no rendered-output hash and cannot be rendered or exported.

## Verification

- Focused Phase-11, Phase-10, export, and API tests pass.
- All 762 Python tests passed in three non-overlapping complete batches with 2 expected
  opt-in skips. Ruff lint/format and `git diff --check` passed. Frontend lint/build was
  blocked before execution because pnpm required an unavailable registry install.
