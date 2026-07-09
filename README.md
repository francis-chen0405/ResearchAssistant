# Debate Research Agent System

This repository contains a phase-gated Debate Research Agent System. The MVP separates retrieval, semantic approval, Ledger admission, synthesis, and deterministic final validation so factual text can only be released after passing typed gates.

Current status: Phases 0 through 6 and Phase 7A are complete. The full Phase 0-10 roadmap is documented in `.agent/PLANS.md`. Phase 7B has not started.

Next exact task: Phase 7B search and scraping provider interfaces, only after explicit user direction.

The completed implementation currently covers strict Pydantic contracts, SQLite persistence, schema migration tracking, deterministic snapshot/quotation integrity checks, deterministic Analyst score policy, fixture-driven Reviewer checks, Ledger admission, typed synthesis, fixed connective templates, deterministic final rendering, exact Ledger release validation, a fixture-only offline pipeline, a CLI fixture runner, and a minimal local Streamlit frontend for fixture runs. Active deterministic modules are `models.py`, `store.py`, `utils.py`, `agents/researcher.py`, `agents/analyst.py`, `agents/reviewer.py`, `agents/synthesizer.py`, `agents/renderer.py`, `orchestrator.py`, `cli.py`, and `frontend/streamlit_app.py`. The `agents/planner.py`, `agents/supportingresearcher.py`, and `agents/opposingresearcher.py` files remain placeholders for later roadmap phases.

The repo does not yet implement live retrieval, scraping, LLM calls, provider integrations, SDK integrations, production web frameworks, ORMs, HTTP clients, authentication, uploads, user accounts, or dashboards.

Start here:

1. Read `AGENTS.md`.
2. Read `ARCHITECTURE.md`.
3. Read `CONVENTIONS.md`.
4. Check `STATUS.md`, `HANDOFF.md`, and `.agent/PLANS.md`.
5. Read the relevant current phase plan in `.agent/plans/`.

Verification through Phase 7A:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Launch the local fixture frontend:

```bash
streamlit run frontend/streamlit_app.py
```
