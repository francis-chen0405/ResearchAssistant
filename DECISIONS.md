# Decisions

## 2026-07-22 - MVP-2B Production Provider Boundaries

- Implement only pinned loopback Wigolo `0.2.1` and direct OpenRouter HTTP adapters; add
  `httpx`, `markdown-it-py`, and `pypdf` with no LLM SDK or second provider stack.
- Make `ra-normalization-v1` normalized plain text the quote surface. Support deterministic
  HTML/Markdown/plain text and unencrypted digital PDFs; reject unusable PDFs without OCR.
- Migrate every default LLM route to MiMo Pro with MiniMax M3 as the sole fallback while
  retaining legacy aliases only for persisted-artifact compatibility.
- Use conservative frozen price caps above observed July 22, 2026 provider prices, reconcile
  provider-reported cost when present, and mark cap-calculated cost as estimated.
- Read `OPENROUTER_API_KEY` only from an explicitly supplied process environment mapping.
  Do not silently load `.env` or another credential source.
- Keep the boundary smoke outside the product CLI and require every enable, approval,
  call-count, token, cost, deadline, and dedicated-output gate. Credentials alone never run it.
- Make no SQLite migration and do not connect the complete orchestration in MVP-2B.

## 2026-07-22 - Narrow Model-Facing Provenance Envelopes

- Keep required release provenance in typed application-owned request/result envelopes
  and persisted domain artifacts when a deliberately narrow model-facing schema forbids
  contextual metadata.
- Apply this rule to `ReviewerInput` and `ReviewerDecision`: do not expose run IDs,
  timestamps, model metadata, or application-owned identifiers merely to duplicate the
  provenance already carried by `LLMRequest`, invocation records, and
  `StatementReviewResult`.
- This is a narrow exception for model context isolation, not permission for
  provenance-free application handoffs.

## 2026-07-21 - MVP-2A Architecture Gate

- Name this documentation phase **MVP-2A Architecture Gate**. It selects a live-provider
  design but does not authorize implementation, dependencies, secrets, migrations, live
  calls, or MVP-2B.
- Select pinned local Wigolo `0.2.1` for discovery and controlled source acquisition.
  Search results are discovery metadata only; every source is independently fetched and
  provider snippets, scores, evidence fields, or summaries never substitute for a
  ResearchAssistant snapshot.
- Request five ranked results for each of six queries and attempt them in rank order
  until three usable unique snapshots exist per query. Keep eighteen snapshots as the
  normal Extractor ceiling and thirty acquisition candidates as the structural maximum.
- Preserve original, final redirected, and advisory canonical URLs separately. Determine
  origin content type independently because Wigolo's REST extraction does not expose the
  original HTTP `Content-Type`.
- Allow one direct fetch and one controlled Chromium-render fallback only after a
  challenge or JavaScript-required result. Do not add authentication, clicks, typing,
  profiles, or general browser automation.
- Support digital PDFs through a narrow deterministic path. Reject scanned/image-only,
  encrypted, malformed, empty, oversized, timed-out, or unusably extracted PDFs without
  OCR. Headers, footnotes, and page markers may remain.
- Make the immutable, 3,000-word, ResearchAssistant-normalized plain-text snapshot the
  only quote authority. Normalize deterministically and version the contract. Character
  offsets always refer to stored normalized text and Python must verify
  `text[start:end] == exact_quote`. Refetches never replace snapshots.
- Use OpenRouter as the single LLM gateway. Route all five roles to
  `xiaomi/mimo-v2.5-pro`; use `minimax/minimax-m3` as the only objective-failure fallback.
  Require strict JSON Schema and exact local Pydantic revalidation.
- Permit at most primary, primary retry, fallback, and fallback retry per logical call.
  Semantic disagreement or low scores do not trigger routing. All attempts share one
  run-wide call, token, and monetary budget.
- Reserve conservative usage and capped price before calls and reconcile exact usage
  afterward. Retain usage from failed, malformed, and locally rejected outputs; fail
  closed when pricing or returned route identity cannot be established.
- Restrict live MVP research to public, non-sensitive claims. Configure OpenRouter data
  collection denied and prompt logging off, protect the API key from logs/persistence,
  and bind the unauthenticated Wigolo service to loopback only.
- Require an exact checkpoint fingerprint over repository, provider/adapter, exact
  model/upstream, prompt/schema, acquisition, normalization/PDF, retry/budget/pricing,
  and Wigolo configuration versions. Changed fingerprints require a new run; silent
  cross-version resume is unsupported.
- Keep Brave Search plus local `httpx`/`trafilatura`/`pypdf` extraction and the same
  OpenRouter route as the concrete alternative, not an additional implementation target.
- Defer approval of `httpx`, `markdown-it-py`, Node/Wigolo runtime requirements,
  response limits, deadlines, hard USD/token/call limits, environment-template changes,
  CLI/UI behavior, and schema migrations to MVP-2B.

## 2026-07-19 - Phase MVP-1 Release-Contract Correctness

- Treat brief title, displayed-claim label and text, section headings, and section order
  as application-owned release framing. The fixed title is `Research Brief`; the fixed
  label is `Claim under review`; the displayed value is the exact authoritative claim
  passed by the orchestrator.
- Remove `title`, `claim_definition`, and section `heading` from `SynthesisOutput` and
  `SynthesizerLLMInput`. The Synthesizer selects only typed sections, approved templates,
  and exact Ledger-backed items.
- Allow only supporting, opposing, and limitations sections, at most once each, in that
  application-defined order. Reject hidden or extra framing fields before release hash
  creation.
- Use a narrow `ReviewerDecision` as the LLM output. It contains exact reviewed text,
  normalized approval/rejection, an optional rejection code, and rationale; unknown
  fields, including `reviewer_approval_id`, are forbidden.
- Derive approved IDs in application code as `rappr_v1_<sha256>`, after decision-shape
  and exact-text validation. Canonical sorted compact JSON contains derivation version,
  Reviewer schema version, statement draft ID, quote block ID, exact reviewed text, and
  normalized `approved` decision only.
- Exclude timestamps, provider request/response metadata, formatting, routes, token
  usage, cost, and other unstable metadata from approval-ID derivation.
- Preserve the persisted/domain `StatementReviewResult`. Continue reading legacy UUID
  approval IDs while writing new application-owned `rappr_v1` IDs.
- Retain legacy SQLite synthesis framing columns for schema compatibility, write only
  fixed application constants into them, and ignore their contents when reconstructing
  framing-free `SynthesisOutput` artifacts.
- Preserve completed synthesis checkpoints backed by SQLite rows. Reject pre-MVP-1
  serialized synthesis payloads during an interrupted pre-checkpoint restart; those runs
  require a fresh run rather than silently accepting model-owned framing.
- Persist fixture runs as `RunStatus.RUNNING` until final validation, then update them to
  `RunStatus.COMPLETED` for release or `RunStatus.BLOCKED` for validation block.


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
