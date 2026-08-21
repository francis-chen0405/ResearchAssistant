# CONVENTIONS.md

## 1. Folder Structure

```
debate_agent/
  AGENTS.md             # standing AI-assistant instructions
  .env                  # real secrets — never commit
  .env.example          # blank template — always commit
  .gitignore
  README.md
  ARCHITECTURE.md       # the system design brief
  CONVENTIONS.md
  DECISIONS.md          # durable project decisions
  STATUS.md             # phase status log
  HANDOFF.md            # handoff notes for the next assistant
  pyproject.toml
  .agent/
    PLANS.md
    plans/
      phase-00-foundation.md
  .agents/
    PLANS/
      phase-00-foundation.md  # compatibility mirror; .agent/plans is canonical
  
  models.py             # all Pydantic models
  store.py              # all SQLite read/write functions
  utils.py              # sha256, uuid5, shared helpers
  providers/
  prompts/
  
  agents/
    planner.py
    supportingresearcher.py
    opposingresearcher.py
    analyst.py
    reviewer.py
    synthesizer.py
    renderer.py
  
  tests/
    fixtures/
    ...
```

## 2. Agent Handoffs

Agents communicate by passing Pydantic model instances in memory within a run.
SQLite is the persistence layer — not the message bus.
The flow is:
  Planner output → `PlannerOutput` passed directly to Researcher functions
  Researcher output → `list[CandidateQuoteBlock]` written to SQLite, then read by Analyst
  Analyst output → `StatementDraft` passed directly to Statement Reviewer
  Reviewer-approved result → `LedgerRecord` written to SQLite, then read by Synthesizer
  Synthesizer output → `SynthesisOutput` passed directly to Renderer

Never pass raw dicts between agents. Always use the typed Pydantic models from models.py. JSON serialization is allowed only at persistence, API, logging, or export boundaries. `SynthesisOutput` must carry Ledger IDs, `reviewer_approval_id`, stance, placement, entailment, exact approved statements, and required provenance so the final validator can compare it against the Ledger.

Deliberately narrow model-facing schemas may keep forbidden contextual provenance outside
the model payload only when a typed application-owned request/result envelope and the
persisted domain artifact carry it. This exception applies to the narrow Reviewer input
and decision contracts; it does not permit provenance-free application handoffs.

IDs are assigned only after the deterministic validation gate for that artifact passes. Failed candidates, rejected statements, and invalid rendered briefs receive no release-relevant IDs.

Evidence scoring remains two-axis: `evidence_quality` and `claim_fit` are recorded and validated separately. The derived `ledger_score` is allowed only after both axis thresholds pass and must never compensate for a failing axis.

## 3. Tech Stack

  Python 3.11 or 3.12
  Pydantic v2           # data models and validation
  sqlite3               # stdlib, no ORM
  pytest                # all tests
  ruff                  # linting and formatting

No additional dependencies without flagging it first.
Do not add an LLM SDK, web framework, ORM, scraper, or HTTP library until a later phase explicitly approves it.
API client to be added in a later phase — skip any LLM call stubs for now.

MVP-2A Architecture Gate selects future `httpx` and `markdown-it-py` use with pinned
Wigolo `0.2.1`, plus OpenRouter's direct HTTP API, but does not add or finally approve
those dependencies. MVP-2B must obtain explicit approval before changing dependency or
runtime declarations. Do not add a second general provider framework: implement the
existing Protocols for the approved concrete stack when that phase is authorized.

MVP-2B obtained that approval and added `httpx`, `markdown-it-py`, and `pypdf`. MVP-3A
adds no dependency and constructs only those approved Wigolo/OpenRouter boundaries.
MVP-3B uses the already-approved direct `httpx` boundary to call Xiaomi MiMo and adds no
SDK or dependency.

## 4. Coding Style

  - Type hints on every function signature, no exceptions: every repository-owned Python
    `def` and `async def` has an explicit return annotation and every named parameter is
    annotated except conventional method receivers named `self` or `cls`. This includes
    production and test code, nested functions, fixtures, callbacks, positional-only,
    keyword-only, `*args`, and `**kwargs`. `tests/test_type_contracts.py` enforces the rule.
  - Async: no — everything is sync for MVP
  - Error handling: raise exceptions, never silently return None on failure
  - No global state — pass dependencies explicitly
  - One responsibility per function — if a function does two things, split it
  - No TODO comments in committed code — either build it or leave it out

## 5. SQLite Rules

  - snapshots and ledger tables are INSERT-ONLY
  - No UPDATE or DELETE operations on those two tables, ever
  - candidates table can be cleared between runs
  - `evidence_quality` and `claim_fit` are always stored separately; any `ledger_score` is derived from those fields after eligibility passes
  - All schema definitions live in store.py in a single init_db() function
  - Concurrent supporting/opposing researchers must not share SQLite connections, cursors, or transactions
  - Prefer coordinator-owned serialized writes after both sync researchers finish; if a worker must touch SQLite, it opens and closes its own connection
  - Persistence records that affect release must include run IDs, prompt/model versions when applicable, retrieval attempts, and timestamps
  - `runs.raw_claim` is immutable after insertion at both the application and SQLite trigger boundaries
  - Schema migration 4 contains same-run provenance triggers; migration 5 contains the raw-claim immutability trigger
  - History and inspection open existing databases with the validated read-only store session and never call `init_db()` or migrate
  - Operators migrate an older database only through an intentional writable run or resume operation
  - Provider-run contracts are frozen strict models; canonical payload bytes, duplicated identity fields, and fingerprint must agree on construction and read
  - Model-usage totals are exact only when complete; incomplete values retain labeled known subtotals and conservative reservation exposure
  - SQLite migration 6 rejects every UPDATE and DELETE of existing `snapshots` and
    `ledger_records` rows through unconditional table-specific triggers
  - Authoritative USD values use finite non-negative `Decimal` end to end and canonical
    non-exponent decimal text in SQLite; legacy REAL cost columns are compatibility-only
  - SQLite migration 7 adds nullable snapshot acquisition/media-provenance columns;
    historical immutable rows reconstruct as explicitly unknown and are never rewritten
  - MVP-9 adds no migration: semantic quote selections use the existing generic model-
    attempt JSON boundary, while assembled quote blocks and exact offsets retain the
    schema-7 provisional/candidate columns
  - MVP-10 migration 8 adds append-only Evidence Portfolio and Evidence Trail tables;
    historical MVP-9 runs remain readable with no required new artifacts
  - MVP-11 migration 9 adds append-only research-round, Governor-decision, and terminal
    research-result records; SQLite accepts only research rounds 1–3 and historical
    MVP-9/MVP-10 runs remain readable without migration during inspection
  - V2 Phase 7 adds no migration: adaptive plans, conservative model reservations, search
    outcomes, round execution summaries, merged survivors, Governor decisions, and stopping
    decisions use strict models in the existing append-only `v2_artifacts` boundary
  - Local brief export opens the database through the validated read-only inspection path;
    it may export only a re-hashed released brief and never creates or mutates artifacts

## 6. Environment Variables

  Read live secrets only from the explicitly supplied process-environment mapping.
  Never load `.env` files or shell profiles automatically.
  Never hardcode keys or paths.
  Required variables are documented with blank values in `.env.example` only.

MVP-2A and MVP-2B historically used OpenRouter. MVP-7 retires that executable boundary;
the current environment contains only direct-MiMo credentials. Historical records retain
their original provider history. Live MVP claims are public/non-sensitive only.

The authorized current stack uses required `MIMO_API_KEY`, `EXA_API_KEY`, and
`OPENALEX_API_KEY`, optional `FIRECRAWL_API_KEY`, their configurable HTTPS base URLs,
`MIMO_MODEL`, and optional
loopback `WIGOLO_BASE_URL`. Keys are read only from an explicitly supplied mapping and
remain blank in `.env.example`. Direct MiMo replaces OpenRouter for the live CLI; Exa is
metadata-only discovery, Wigolo is primary acquisition, and Firecrawl is only the narrow
optional acquisition fallback.

The legacy MVP-2B boundary smoke remains disabled unless its exact command argument,
enable flag, execution-time approval phrase, one-call caps, token/cost caps, and dedicated
absolute output path all validate. Its example token ceiling must not exceed the
`LiveSmokeConfig` maximum of 25,000.

## 7. Phase-Gated Development

  Development is phase-gated.
  Before editing, Codex must check `STATUS.md`, `HANDOFF.md`, `.agent/PLANS.md`, and the current phase plan.
  Codex must not begin the next phase until the current phase is tested, documented, and committed.
  Codex must run pytest and Ruff before marking a phase complete.

MVP-2A is a documentation-only Architecture Gate. Completion approves the documented
design, not provider implementation. MVP-2B remains a distinct phase and must reconcile
the current top-three/PDF-unsupported/legacy-model test contracts with the approved
rank-five/keep-three, narrow-PDF, MiMo-Pro/MiniMax route before changing runtime code.

MVP-2B, MVP-3A, MVP-3B, MVP-4, MVP-5, MVP-6, MVP-6.1, MVP-6.2 Batch A, MVP-6.3,
MVP-6.4, MVP-6.5, MVP-6.6, MVP-6.7, MVP-6.8, MVP-6.9, MVP-7.1, MVP-8, MVP-8.1,
MVP-8.2, MVP-9, MVP-10, and MVP-11 are complete. MVP-11 Adaptive Research Expansion &
Cost Control (Research Governor) is the latest completed authorized phase. Current
provider-backed candidates use the shared 20-statistical/30-non-statistical quote
policy; statistical classification requires both a digit and a whole-token recognized
marker. Discovery scores below 5 leave the bounded acquisition pool, while a zero
claim-keyword count remains audit metadata for semantic Analyst review rather than a
hard pre-Analyst rejection. Exact snapshot and downstream approval gates remain strict.
Frozen fixture replay alone injects the explicit legacy 50/100 policy. MVP-6.5 completed
the immutable-run-authority and
read-only-inspection database batch. MVP-6.6 completed CLI-status, model-usage
accounting/budget, and provider-contract integrity. MVP-6.7 completed repository-wide
function-signature annotation enforcement across production and test code, including
nested functions. MVP-6.8 completed SQLite snapshot/Ledger immutability and exact
decimal monetary accounting. MVP-6.9 completed truthful Firecrawl media-type provenance,
snapshot provenance persistence, legacy smoke-example repair, and phase-neutral package
metadata. MVP-10 adds immutable source-family and portfolio-trail inspection; MVP-11
adds cumulative-budget-governed Research Governor rounds with an absolute maximum of
three. The contradiction-audit remediation sequence is complete. The original Streamlit
app remains fixture-only; the Next.js live product reuses the established persistence,
fingerprint, cancellation, and terminal contracts. Do not begin a phase after MVP-11
without separate explicit direction. MLP-1 Simplified Live Experience and MLP-2 Local
Product Experience are complete. MLP-3 Next.js Product Rebuild and its dependency set
were explicitly authorized on 2026-08-14 and are complete. MLP-4 is the latest completed
product-experience phase and preserves the completed MVP-11 release contracts. Its local
credential source remains macOS Keychain; `.env` and shell-profile loading remain
forbidden. MLP-4 Research Quality & OpenAlex Integration is complete; MLP-5 is not
authorized.

## 8. Done Criteria Per Phase

  A phase is complete when all tests for that phase pass with no errors.
  Do not move to the next phase until the current phase tests are green.
  Run `pytest`, `ruff check .`, and `ruff format --check .` before considering a phase complete.

  Phase 1: test_phase1.py passes
  Phase 2: test_phase2.py passes
  etc.
```

The canonical phase-plan path is `.agent/plans/`. The `.agents/PLANS/` path may exist only as a compatibility mirror for requested scaffolding and must not become a second source of truth.

## ResearchAssistant v2 Phase 8 Selection and Queue Conventions

- Persist the full merged survivor input before recommendation; stopping research never
  deletes a legitimate survivor.
- Source Selection is a strict MiMo-v2.5-Pro prioritization handoff. Recommendations may
  reference only known source and Gap IDs and never imply proof, evidence approval, or
  Ledger eligibility.
- Prefer unused source families before repeated families in both model validation and
  deterministic fallback ordering. The usual five-to-ten recommendation range is guidance,
  not a quota.
- Queue only a deterministic priority prefix: recommended survivors first, then
  complementary non-recommended survivors. Never skip an unaffordable higher-priority
  source to admit a lower-priority source.
- Reserve twelve physical calls per queued source and two for mandatory Synthesis, plus
  conservative route-specific tokens and cost. Persist an explicit budget reason for every
  survivor outside the queue.
