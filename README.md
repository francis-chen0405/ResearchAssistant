# Debate Research Agent System

This repository contains a phase-gated Debate Research Agent System. The MVP separates retrieval, semantic approval, Ledger admission, synthesis, and deterministic final validation so factual text can only be released after passing typed gates.

Current status: Phases 0, 1, 2, post-Phase-2 hardening, and Phase 3 are complete. The full Phase 0-10 roadmap is documented in `.agent/PLANS.md`. Phase 4 has not started.

Next exact task: Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.

The completed implementation currently covers strict Pydantic contracts, SQLite persistence, schema migration tracking, and deterministic snapshot/quotation integrity checks. It does not yet implement Analyst admission, Reviewer behavior, live retrieval, scraping, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients.

Start here:

1. Read `AGENTS.md`.
2. Read `ARCHITECTURE.md`.
3. Read `CONVENTIONS.md`.
4. Check `STATUS.md`, `HANDOFF.md`, and `.agent/PLANS.md`.
5. Read the relevant current phase plan in `.agent/plans/`.

Verification through Phase 3:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```
