# MVP-10 — Evidence Portfolio & Trail

## Authority and boundary

The user explicitly authorized MVP-10 on 2026-08-11. This phase makes source coverage auditable and adds one bounded portfolio-expansion round after normal MVP-9 research and review. It does not alter deterministic quotation assembly, Reviewer/Ledger admission, final validation, provider ceilings, or immutable historical artifacts.

## Design

- Add strict typed models for research rounds, deterministic source-family identity, trail entries, portfolio items, coverage, expansion context, and stopping reasons.
- Add SQLite migration 8. It is transactional/idempotent and adds append-only trail, family, portfolio, and coverage records. Existing rows are never modified; read-only inspection requires but never applies the migration.
- Determine source families from canonical source identity when available, otherwise normalized resolved URL, then immutable snapshot hash. Duplicates remain trail rows but are excluded from model extraction and independent-family counts.
- Run normal research and review as round one. If fewer than three independent Reviewer-approved families exist, call the Planner once with typed expansion context and execute only a targeted round. Completed work is preserved and accounting stays cumulative.
- Merge new, non-duplicate approved evidence. Coverage is deterministic: strong (three+ families including opposing/limitation), adequate (three+), limited (one–two), insufficient (zero).
- Extend the local read-only Evidence Browser into the Evidence Trail view with outcomes, optional technical details, role/round/family/cost filters, and a portfolio summary.

## Required protections

- All handoffs are strict Pydantic models with forbidden extras.
- Quotes remain `VerbatimQuoteSelection` plus deterministic application assembly.
- Migration, resume, historical-read, and duplicate behavior are covered by mocked or recorded tests. No live provider call is permitted.

## Completion checks

- Add the MVP-10 regression scenarios from the authorization, including bounded expansion, cumulative budgets, historical schema readability, and trail completeness.
- Run complete `pytest`, `ruff check .`, and `ruff format --check .`.
