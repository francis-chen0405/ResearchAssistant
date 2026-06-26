# Handoff

## 2026-06-26 - Phase 0 Foundation

Work completed:

- Documented the Phase 0 architecture corrections requested by the user.
- Added the repository scaffold needed for reliable AI-assisted development.
- Configured `pyproject.toml` for Python 3.11+, Pydantic v2, python-dotenv, pytest, and Ruff.

Important constraints:

- Do not begin Phase 1 without explicit user instruction.
- Do not implement working agents, SQLite behavior, web retrieval, scraping, LLM calls, SDK integrations, ORMs, web frameworks, or HTTP libraries yet.
- Future assistants must read `ARCHITECTURE.md` and `CONVENTIONS.md` completely before editing.
- Internal handoffs must use Pydantic model instances, not raw dictionaries.

Open issue:

- The requested compatibility path `.agents/PLANS/phase-00-foundation.md` is blocked by a Windows deny ACL on `.agents`. The canonical plan exists at `.agent/plans/phase-00-foundation.md`.

Next expected phase:

- Phase 1 should start only after the user explicitly requests it. It should begin with schemas and artifact-store design as described in `ARCHITECTURE.md`, without weakening the Phase 0 constraints.
