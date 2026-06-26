# CONVENTIONS.md

## 1. Folder Structure

```
debate_agent/
  .env                  # real secrets — never commit
  .env.example          # blank template — always commit
  .gitignore
  ARCHITECTURE.md       # the system design brief
  CONVENTIONS.md
  
  models.py             # all Pydantic models
  store.py              # all SQLite read/write functions
  utils.py              # sha256, uuid5, shared helpers
  
  agents/
    planner.py
    supportingresearcher.py
    opposingresearcher.py
    analyst.py
    reviewer.py
    synthesizer.py
    renderer.py
  
  tests/
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

Never pass raw dicts between agents. Always use the typed Pydantic models from models.py. JSON serialization is allowed only at persistence, API, logging, or export boundaries.

## 3. Tech Stack

  Python 3.11+
  Pydantic v2           # data models and validation
  sqlite3               # stdlib, no ORM
  python-dotenv         # loading .env
  pytest                # all tests
  ruff                  # linting and formatting

No additional dependencies without flagging it first.
API client to be added in a later phase — skip any LLM call stubs for now.

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
  - No composite score column anywhere — evidence_quality and claim_fit are always separate
  - All schema definitions live in store.py in a single init_db() function

## 6. Environment Variables

  Load with python-dotenv at the top of any file that needs them.
  Never hardcode keys or paths.
  Required variables are documented in .env.example only.

## 7. Done Criteria Per Phase

  A phase is complete when all tests for that phase pass with no errors.
  Do not move to the next phase until the current phase tests are green.

  Phase 1: test_phase1.py passes
  Phase 2: test_phase2.py passes
  etc.
```