# MVP-6.4 — Evidence Density Threshold Calibration

## Authority and Boundary

MVP-6.2 Batch A and MVP-6.3 are complete prerequisites. The user separately authorized
MVP-6.4 to calibrate current provider-backed quotation density from 75/75 to deterministic
50-statistical/75-non-statistical thresholds. This phase does not implement database,
read-only inspection, CLI-status, usage-accounting, provider-contract, or type-hint work.
MVP-6.5 has not started.

## Current Evidence Policy

- A quotation is statistical only when its exact quoted segments contain at least one digit
  and at least one recognized statistical marker.
- Recognized markers are `%`, `percent`, `rate`, `ratio`, `average`, `median`, `index`,
  `p-value`, `million`, `billion`, `growth`, and `decline`.
- Marker matching is case-insensitive and respects word/token boundaries. Incidental
  substrings, including `rate` inside `corporate`, do not count.
- Statistical quotations require at least 50 quoted words. All other quotations require at
  least 75 quoted words. A digit alone and a marker alone therefore use 75.
- Ellipses are not quoted words. Exact snapshot membership, segment order, offsets,
  immediate brackets, hashes, boundary markers, claim-keyword relevance, truncation, and
  provenance remain mandatory.
- Invalid model output is rejected before candidate/quote-block ID assignment. It is never
  healed, padded, expanded, or rewritten.

The strict `QuoteLengthPolicy` in `agents/researcher.py` is the shared source of truth for
initial provider extraction, Analyst input verification, and Ledger admission verification.
Reviewer approval, literal entailment, qualification preservation, Ledger admission, and
final release validation are unchanged.

## Historical Fixture Compatibility

`run_fixture_pipeline()` explicitly injects the separately named
`legacy-frozen-fixture-50-100-v1` policy for already-frozen fixture replay. The provider
pipeline never selects that object and defaults to the current 50/75 policy. Historical
artifacts remain inspectable under their recorded identities and are not reinterpreted.

## Identity and Restart Compatibility

- Evidence policy: `mvp6.4-evidence-density-50-75-v1`.
- Extractor prompt: `mvp6.4-extractor-50-75-v1`.
- Extractor prompt SHA-256:
  `a4f95d7468e22f6e95961d409ed7f99910ffe911b1a1788fb409b64bfc9725eb`.
- Aggregate five-prompt identity:
  `49cc02aee6025c4d2bf4a50b8ccfd97a23cb896f15ff8ecb650704ad45db33a2`.
- Provider post-filter validator: `mvp6.4-provider-post-filter-50-75-v1`.
- Canonical provider fingerprint: `mvp6.4-evidence-density-fingerprint-v1`.

Both the historical OpenRouter factory surface and the current direct-MiMo factory include
the current evidence-policy identity in their canonical policy fingerprints. Exact persisted
fingerprint matching rejects a 75/75 run under 50/75 code. After restarting the launcher or
application, the operator must use a new run ID. No database migration is required.

## Regression and Verification Requirements

Regression coverage includes 49/50/51 statistical and 74/75/76 non-statistical boundaries,
digit-plus-marker classification, marker boundaries/case/punctuation, incidental substrings,
no-ID rejection, downstream tampering, prompt alignment, fingerprint identity, incompatible
resume behavior, frozen fixture replay, and unchanged Analyst/Reviewer/Ledger/final-validator
gates.

Before completion, run focused quote, Researcher, Analyst, Reviewer, Ledger, renderer,
final-validator, fingerprint/resume, and fixture tests; full pytest; all offline evaluations;
Ruff lint/format; Python compilation; launcher syntax; `git diff --check`; stale-policy and
artifact audits. Record exact results in `STATUS.md` and `HANDOFF.md`. No provider call,
provider spend, dependency, SQLite migration, or commit is authorized.

## Completion Record

MVP-6.4 is complete. The focused Researcher/Analyst/Reviewer/Ledger/renderer/final-
validator/fingerprint/resume/frozen-fixture selection passed 240 tests with 1 expected
opt-in skip. The complete suite passed 517 tests with 2 expected opt-in skips. All 38
offline evaluation cases passed. Ruff lint passed; Ruff format reported 58 files already
formatted. Python compilation, launcher `zsh -n`, `git diff --check`, stale-policy review,
dependency/migration review, generated-artifact review, and final diff review passed.

No Exa, Wigolo, Firecrawl, MiMo, OpenRouter, or other live provider call or spending
occurred. No dependency or SQLite migration was added, no commit was created, and MVP-6.5
has not started.
