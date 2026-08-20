# ResearchAssistant v2 — Phase 2: Multi-Model Routing

Status: Complete and verified on 2026-08-20.

## Scope

- Add v2-only logical stage aliases for Scout, Gap Analysis, Search Agent, and Source
  Selection while preserving historical stage and model aliases.
- Freeze the v2 target routing table: MiMo Pro for Planner, Search Agent, Source
  Selection, Extractor, Reviewer, and Synthesizer; MiMo normal for Scout; Luna High
  for Gap Analysis and Evidence Analyst.
- Add fail-closed configuration, deterministic price caps/reservation coverage,
  secret-safe route identity, and immutable provider-contract fingerprint construction.
- Reuse the Xiaomi-compatible adapter for independently configured MiMo normal and
  Pro routes.  Luna remains a configuration-only boundary until a later authorized
  phase selects and implements a verified transport.

## Explicitly out of scope

- Scout, Gap Analysis, Search Agent, Source Selection, or Analyst execution flow.
- Any live provider invocation, Luna adapter/transport, database migration, UI route,
  retrieval, evidence, Ledger, or release-gate behavior.
- Changes to historical direct-MiMo factory contracts or persisted route records.

## Configuration requirements

- `MIMO_API_KEY` is required for both MiMo routes. `MIMO_V25_MODEL` defaults to
  `mimo-v2.5`, while `MIMO_V25_PRO_MODEL` defaults to `mimo-v2.5-pro`.
- Normal MiMo requires explicit positive `MIMO_V25_INPUT_USD_PER_TOKEN` and
  `MIMO_V25_OUTPUT_USD_PER_TOKEN`. A changed Pro physical model also requires the
  equivalent `MIMO_V25_PRO_*` pricing values.
- Luna requires explicit `LUNA_API_KEY`, HTTPS `LUNA_BASE_URL`, `LUNA_MODEL`, and
  positive `LUNA_INPUT_USD_PER_TOKEN` / `LUNA_OUTPUT_USD_PER_TOKEN`. No physical Luna
  model ID is assumed by the repository.

## Completion signal

Offline tests prove exact stage routing, distinct MiMo normal/Pro routes, Luna
configuration failures, returned-model validation, credential redaction, fingerprint
drift, complete positive pricing coverage, and historical direct-MiMo compatibility.
Verification completed with 682 passed and 2 expected skips across the complete Python
suite, plus Ruff lint/format checks and `git diff --check`. No live provider calls were
made.
