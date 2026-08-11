# MVP-9 — Verified Quote Selection & Deterministic Assembly

## Authority and Boundary

The user explicitly authorized MVP-9 on 2026-08-11 after repeated live Extractor
failures consumed model tokens while MiMo attempted to author the application-owned
bracketed quote format. MVP-8.2 is complete. MVP-9 replaces that fragile model contract
without weakening any evidence, Reviewer, Ledger, or final-release gate.

## Scope

- Replace provider-facing `ProvisionalCandidate` Extractor output with the strict,
  minimal `VerbatimQuoteSelection` schema containing only ordered exact snapshot
  passages.
- Make ResearchAssistant locate the selected passages in the immutable normalized
  snapshot and deterministically construct immediate context, boundary markers,
  ellipses, provenance, and the legacy-compatible `ProvisionalCandidate`.
- Keep exact membership, source order, quote-density, claim relevance, truncation,
  Analyst, Reviewer, Ledger, and final-render validation fail closed.
- Treat exact-selection mismatch as non-retryable. Retrying cannot make invented or
  altered text become present in an immutable snapshot.
- Bump prompt, adapter, factory, retry, post-filter, schema, and fingerprint identities
  so an older in-flight contract cannot resume under MVP-9 with the same run ID.
- Preserve SQLite schema version 7 and historical artifact reconstruction. New runs
  continue persisting canonical bracketed candidates and exact offsets in the existing
  columns; no immutable historical row is rewritten.

## Non-Negotiable Invariants

- The model never authors brackets, context sentences, offsets, IDs, timestamps,
  provenance, or completed candidate artifacts.
- Every selected passage must match snapshot text byte-for-byte and in source order.
- Application assembly is deterministic and undergoes the existing post-extraction
  filter before any candidate ID exists.
- Malformed JSON/schema/provider failures retain the established bounded objective retry
  policy; exact-selection mismatch does not retry or switch models.
- Internal handoffs remain strict Pydantic models with unknown fields forbidden.
- Snapshot and Ledger immutability, read-only inspection, exact accounting, controls,
  export, Evidence Browser, and release validation remain unchanged.

## Database Compatibility

- Do not add migration 8. `VerbatimQuoteSelection` is persisted only in the existing
  generic model-attempt JSON audit boundary.
- The assembled `ProvisionalCandidate` retains the existing schema and column layout.
- Schema-7 databases remain readable and writable under their established migration,
  trigger, and read-only compatibility rules.
- MVP-9 code/prompt/schema/fingerprint identities require a new run ID for execution;
  historical terminal runs remain inspectable without reinterpretation.

## Verification

- Add regression coverage for strict selection shape, deterministic multi-segment
  assembly, start/end/truncated markers, nonexistent and out-of-order text, non-retryable
  mismatch, schema-7 preservation, and direct-MiMo semantic output.
- Run focused extraction/orchestration/persistence coverage, full `pytest`,
  `ruff check .`, `ruff format --check .`, deterministic evaluation, and
  `git diff --check`.
- Make no live provider call and incur no additional Exa, Firecrawl, or MiMo cost.

## Out of Scope

- Quote healing, fuzzy matching, model-authored offsets, database migration, historical
  artifact rewriting, threshold reduction, Reviewer/Ledger weakening, new providers,
  dependencies, accounts, hosting, or a phase after MVP-9.

## Completion Record

Complete on 2026-08-11. Focused coverage passed 107 tests with one expected opt-in skip;
the full offline suite passed 579 tests with two expected opt-in skips. All 38
deterministic evaluation cases, Ruff lint/format, and `git diff --check` passed. SQLite
remains schema version 7. No dependency, migration, live provider call, or spending was
added.
