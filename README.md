# Debate Research Agent System

This repository contains the design and scaffold for a multi-stage debate research system.

Current phase: Phase 2 store hardening.

Phase 2 defines the typed Pydantic contracts and SQLite persistence layer. It does not implement working agents, web retrieval, scraping, orchestration, rendering, SDK integrations, web frameworks, ORMs, HTTP clients, or LLM calls.

Start here:

1. Read `ARCHITECTURE.md`.
2. Read `CONVENTIONS.md`.
3. Read `AGENTS.md`.
4. Check `STATUS.md` and `HANDOFF.md`.

Verification commands:

```powershell
pytest
ruff check .
ruff format --check .
```
