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

IDs are assigned only after the deterministic validation gate for that artifact passes. Failed candidates, rejected statements, and invalid rendered briefs receive no release-relevant IDs.

Evidence scoring remains two-axis: `evidence_quality` and `claim_fit` are recorded and validated separately. The derived `ledger_score` is allowed only after both axis thresholds pass and must never compensate for a failing axis.

## 3. Tech Stack

  Python 3.11+
  Pydantic v2           # data models and validation
  sqlite3               # stdlib, no ORM
  python-dotenv         # loading .env
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

## 4. Coding Style

  - Type hints on every function signature, no exceptions
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

## 6. Environment Variables

  Load with python-dotenv at the top of any file that needs them.
  Never hardcode keys or paths.
  Required variables are documented in .env.example only.

MVP-2A proposes `OPENROUTER_API_KEY` as the only required vendor secret for the primary
stack. Do not add it to `.env.example`, load it, or use it until MVP-2B is explicitly
authorized. Never expose the key to Wigolo, logs, SQLite, checkpoints, or exported
artifacts. Live MVP claims are public/non-sensitive only.

## 7. Phase-Gated Development

  Development is phase-gated.
  Before editing, Codex must check `STATUS.md`, `HANDOFF.md`, `.agent/PLANS.md`, and the current phase plan.
  Codex must not begin the next phase until the current phase is tested, documented, and committed.
  Codex must run pytest and Ruff before marking a phase complete.

MVP-2A is a documentation-only Architecture Gate. Completion approves the documented
design, not provider implementation. MVP-2B remains a distinct phase and must reconcile
the current top-three/PDF-unsupported/legacy-model test contracts with the approved
rank-five/keep-three, narrow-PDF, MiMo-Pro/MiniMax route before changing runtime code.

## 8. Done Criteria Per Phase

  A phase is complete when all tests for that phase pass with no errors.
  Do not move to the next phase until the current phase tests are green.
  Run `pytest`, `ruff check .`, and `ruff format --check .` before considering a phase complete.

  Phase 1: test_phase1.py passes
  Phase 2: test_phase2.py passes
  etc.
```

The canonical phase-plan path is `.agent/plans/`. The `.agents/PLANS/` path may exist only as a compatibility mirror for requested scaffolding and must not become a second source of truth.
