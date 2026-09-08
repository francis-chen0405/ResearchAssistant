# AI Assistant Instructions

## Active Codex checkout

The active local checkout for this project is currently located at
`/Users/francischen/Library/CloudStorage/OneDrive2-EastsidePreparatorySchool/GitHub/ResearchAssistant`.
Use the repository root supplied by the task when working; do not assume the older
`/Users/francischen/Documents/GitHub/ResearchAssistant` placement. This synced-folder
location is a workspace detail only and must not be embedded in application runtime paths.

Current authority: `.agent/plans/phase-3-frontend-settings.md`, `ARCHITECTURE.md`, and
`desktop/README.md`. Phase 2 maintainability refactoring and documentation consolidation
was completed on `codex/phase-2-cleanup`. Phase 3 frontend redesign and provider/model settings are explicitly authorized on 2026-09-07.
Phase 1 native macOS/Windows build and runtime checks now pass. Clean-machine
installation, minimum-OS, signing and notarization remain public-release gates. The current research pipeline is completed v2 Phase 14.
Before editing, completely read architecture, conventions, decisions, status, handoff,
`.agent/PLANS.md`, relevant current plans and applicable nested instructions.
The original chronological preamble is preserved in
`docs/archive/pre-phase-2/AGENTS.md`; this paragraph replaces its stale phase authority.

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
- Document any approved dependency change in the relevant status, handoff, and phase-plan files.
- Never silently return `None` on failure; raise a clear exception or return a typed failure model.
- Require explicit return annotations and annotations for every named parameter on every
  repository-owned Python `def` and `async def`; only conventional receivers named `self`
  or `cls` may be unannotated. The repository-wide AST regression lives in
  `tests/test_type_contracts.py` and covers production and test code, including nested functions.
- Never run destructive Git commands such as `git reset --hard`, `git clean -fd`, or force-push unless explicitly instructed by the user.
- Never delete architecture, convention, status, handoff, or phase-plan content without explaining the exact replacement.
- Avoid unrelated edits, refactors, formatting churn, and metadata changes.
- Do not implement live agent behavior, database changes, web retrieval, scraping, LLM calls, SDK integrations, production web frameworks, ORMs, HTTP clients, or other out-of-phase behavior unless the active phase explicitly requires them.
- Treat artifacts that reach the Ledger, `SynthesisOutput`, or final validator as immutable.
- Update `STATUS.md` and `HANDOFF.md` after each phase with what changed, what was verified, what remains unresolved, and what the next phase should know.
- Run `pytest`, `ruff check .`, and `ruff format --check .` before considering a phase complete.

If the architecture and conventions conflict, pause implementation work and resolve the documentation mismatch first with minimal explicit edits.
