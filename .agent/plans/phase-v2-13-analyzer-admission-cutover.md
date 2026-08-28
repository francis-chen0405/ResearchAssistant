# ResearchAssistant v2 — Phase 13: Analyzer Admission Cutover

Status: Complete and verified.

## Authorized scope

- Remove all fresh-v2 Reviewer calls and make the Luna Evidence Analyst the sole semantic
  judge for new v2 runs.
- Return the Analyst assessment and final factual statement in one concise call, with one
  attempt per successfully extracted source.
- Add deterministic Analyzer Admission for exact quote, provenance, direction, scores,
  placement, qualification, and statement checks.
- Process the full deep-analysis priority pool until the existing run-wide budget is reached,
  preserving actual analyzed, rejected, failed, and budget-prevented states.
- Update synthesis, final validation, API, UI, persistence, and export to accept analyzer-
  admitted records with an explicit reduced-safety disclosure.
- Keep historical Reviewer, Ledger, extraction, budget, and final-output artifacts readable
  without relabeling or migration.

## Versioned contracts

- Add `V2EvidenceAdmissionBatchResult`, `V2EvidenceAdmissionSourceResult`, and
  `V2AdmissionMethod`.
- Make Reviewer metadata optional for analyzer-admitted records and retain old canonical-
  drafting and Reviewer models for historical compatibility.
- Version fresh Phase-13 artifact keys, policy identities, fingerprints, and budget constants.
- Reserve three physical calls per source: up to two extraction attempts and one Analyst call.

## Safety boundary

Python validates structure, provenance, scores, direction, placement, qualification, and exact
statement identity. It does not independently prove semantic entailment. Fresh analyzer-
admitted evidence is labeled accordingly; historical Reviewer-approved evidence keeps its
original label and interpretation.

## Completion gates

- No fresh-v2 request uses `ReviewerDecision` or `LLMStage.REVIEWER`.
- One Analyst call is made per successfully extracted source; rejected and failed sources never
  enter evidence.
- Analyzer-only records reach synthesis without fabricated Reviewer IDs.
- Restart, immutable persistence, cancellation, budget accounting, rendering, API output,
  frontend output, and historical compatibility are covered by tests.
- Full Python tests, Ruff checks, frontend ESLint, TypeScript, and production build pass.
