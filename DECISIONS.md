# Decisions

## 2026-06-26 - Phase 0 Foundation

- Keep Phase 0 documentation-only plus scaffold-only. No working agents, database behavior, retrieval, scraping, or LLM calls are implemented.
- Use Pydantic v2 as the only model layer for internal handoffs.
- Treat `.agent/plans/` as the canonical phase-plan directory.
- Treat `.agents/PLANS/` as a requested compatibility mirror only; it must not become a second source of truth.
- Require release-relevant records to carry provenance: run IDs, prompt versions, model names, retrieval attempts, validator/filter versions, and timestamps.
- Run supporting and opposing research concurrently only through synchronous workers with no shared SQLite connection.
- Assign IDs only after the relevant deterministic validation gate passes.

## 2026-06-26 - Phase 1 Pydantic Models

- Represent internal handoff and release-relevant artifacts as strict Pydantic v2 model instances.
- Keep JSON serialization at persistence, API, logging, and export boundaries only; do not use raw dictionaries as agent handoffs.
- Carry release-critical provenance through the model layer, including UUIDs, run IDs, source or snapshot provenance, prompt/model versions, and timezone-aware timestamps.
- Require `SynthesisOutput` items to preserve Ledger IDs, reviewer approval IDs, stance, placement, entailment, and exact approved factual statements for later deterministic validation.

## 2026-06-26 - Phase 2 SQLite Store

- Use Python's standard `sqlite3` module for persistence; do not add an ORM or new database dependency.
- Keep schema definitions centralized in `store.py` inside `init_db()`.
- Open and close SQLite connections per store function and enable foreign keys on every connection.
- Treat snapshots and Ledger records as insert-only audit artifacts.
- Preserve typed boundaries: store functions accept and return Pydantic models, with JSON used only for persistence encoding of structured fields.

## 2026-06-26 - Phase 2 Scoring and Store Hardening

- Enforce two-axis Ledger eligibility with separate `evidence_quality` and `claim_fit` thresholds before deriving `ledger_score`.
- Clarify that Claim Fit 2 items may be retained as borderline Analyst context but cannot enter the final Ledger unless rescored to Claim Fit 3 or higher.
- Derive `ledger_score` deterministically from the two sub-scores only after eligibility passes.
- Enforce placement consistency from score decisions instead of allowing downstream stages to promote or rewrite placement.
- Add SQLite foreign keys for architecture-defined parent-child artifact relationships.

## 2026-06-27 - Post-Phase-2 Hardening

- Require internal Pydantic artifacts to reject unknown fields by default with `model_config = ConfigDict(extra="forbid")`, unless a specific exception is documented.
- Add representative regression coverage for extra-field rejection across Ledger, synthesis, validation, candidate, snapshot, and model-invocation artifacts.
- Track SQLite schema versioning through a `schema_migrations` table initialized by `init_db()`.
- Strengthen assistant rules against destructive Git commands, test weakening, undocumented protected-doc deletion, and beginning the next phase without explicit direction.

## 2026-06-27 - Phase 3 Snapshot and Quotation Integrity

- Keep trusted snapshot and quote-block checks deterministic and local; Phase 3 does not add retrieval, scraping, LLM calls, Analyst scoring, Reviewer logic, Ledger admission, rendering, or orchestration.
- Put shared post-extraction filtering in `agents/researcher.py` so supporting and opposing researchers can later use the same deterministic validation rules.
- Recompute snapshot SHA-256 and word count from `normalized_text` before accepting snapshot-dependent artifacts.
- Validate bracketed quote blocks by exact segment membership, sequential offsets, immediate surrounding context, boundary markers, quote length thresholds, statistical-marker rules, and claim-keyword relevance before assigning a quote-block ID.
- Return typed rejection results without candidate IDs for invalid provisional candidates.

## 2026-06-27 - Phase 0-10 Roadmap Alignment

- Treat `.agent/PLANS.md` as the compact source of truth for the full Phase 0-10 roadmap.
- Keep detailed implementation prompts out of the roadmap index; use individual `.agent/plans/phase-XX-*.md` files for phase-specific plans.
- Clarify that `ARCHITECTURE.md` defines system invariants while phase sequencing lives in `.agent/PLANS.md` and the canonical `.agent/plans/` directory.
- At the time of roadmap alignment, Phase 4 was the next unstarted phase: Analyst rules, Reviewer rules, and Ledger admission.

## 2026-07-03 - Phase 4 Analyst Rules, Reviewer Rules, and Ledger Admission

- Implement Phase 4 as deterministic typed helper surfaces in `agents/analyst.py` and `agents/reviewer.py`; do not add LLM calls or provider integrations.
- Keep score interpretation explicit with a 25-row Evidence Quality and Claim Fit table, preserving separate score axes before deriving any Ledger score.
- Reconstruct Ledger records from candidate, snapshot, Analyst decision, StatementDraft, and Reviewer approval artifacts instead of trusting caller-supplied Ledger fields.
- Reuse Phase 3 snapshot and quote verification before Ledger admission so a matching hash alone is not treated as proof that the quotation exists at the recorded offsets.
- Keep Reviewer input narrow: quote block, bracket context, draft statement, and Claim Fit score only.

## 2026-07-04 - Phase 5 Synthesizer Schema, Renderer, and Release Validator

- Build `SynthesisOutput` only from typed `LedgerRecord` instances; reject raw dictionary Ledger handoffs.
- Keep approved connective templates in `agents/renderer.py` as deterministic strict Pydantic configuration artifacts.
- Validate final releases by exact Ledger claim ID, Reviewer approval ID, statement text, placement, stance, entailment, section compatibility, template compatibility, and one-use-per-Ledger-claim rules.
- Compute the rendered brief SHA-256 hash only after final validation succeeds; invalid validation results carry no rendered hash.
- Keep Phase 5 deterministic and fixture-oriented. No fixture pipeline, orchestration, CLI, live retrieval, scraping, LLM/API calls, provider integrations, dependencies, or Phase 6 behavior was added.
