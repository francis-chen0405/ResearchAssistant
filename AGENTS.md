# AI Assistant Instructions

This repository has completed Phase 2 for the Debate Research Agent System. Before editing any file, read `ARCHITECTURE.md` and `CONVENTIONS.md` completely.

Required rules for every future assistant:

- Stop at the current phase boundary. Do not begin the next phase without explicit user direction.
- Do not begin the next phase.
- Use Pydantic models for all internal agent handoffs.
- Use `model_config = ConfigDict(extra="forbid")` for internal Pydantic artifacts unless a specific exception is documented.
- Never pass raw dictionaries between agents; JSON belongs only at persistence, API, logging, or export boundaries.
- Never weaken tests, delete assertions, skip checks, or lower acceptance criteria to make work pass.
- Do not weaken tests to make implementation pass.
- Prefer adding failing regression tests before fixing validator or integrity bugs.
- Never add dependencies without flagging them first and getting explicit approval when they are outside the current phase.
- Never silently return `None` on failure; raise a clear exception or return a typed failure model.
- Never run destructive Git commands such as `git reset --hard`, `git clean -fd`, or force-push unless explicitly instructed by the user.
- Never delete architecture, convention, status, handoff, or phase-plan content without explaining the exact replacement.
- Avoid unrelated edits, refactors, formatting churn, and metadata changes.
- Do not implement working agents, database behavior, web retrieval, scraping, LLM calls, SDK integrations, web frameworks, ORMs, or HTTP clients unless the active phase explicitly requires them.
- Treat artifacts that reach the Ledger, `SynthesisOutput`, or final validator as immutable.
- Update `STATUS.md` and `HANDOFF.md` after each phase with what changed, what was verified, what remains unresolved, and what the next phase should know.
- Run `pytest`, `ruff check .`, and `ruff format --check .` before considering a phase complete.

If the architecture and conventions conflict, pause implementation work and resolve the documentation mismatch first with minimal explicit edits.
