# Phase 00 - Foundation

## Purpose

Prepare the repository for reliable AI-assisted development without implementing working agents, database behavior, web retrieval, scraping, or LLM calls.

## Files Being Changed

- `ARCHITECTURE.md`
- `CONVENTIONS.md`
- `AGENTS.md`
- `DECISIONS.md`
- `STATUS.md`
- `HANDOFF.md`
- `README.md`
- `pyproject.toml`
- `.agent/PLANS.md`
- `.agent/plans/phase-00-foundation.md`
- `providers/.gitkeep`
- `prompts/.gitkeep`
- `tests/fixtures/.gitkeep`

## Architectural Decisions

- Use Pydantic v2 models for all internal handoffs.
- Pass `SynthesisOutput` as a typed model, not a raw dictionary.
- Carry `reviewer_approval_id` from Ledger records through synthesizer output and final validation.
- Carry explicit `stance` so supporting and opposing records can be validated against their rendered sections.
- Allow supporting and opposing researchers to run concurrently only as synchronous workers with no shared SQLite connection.
- Record provenance fields for run IDs, prompt versions, model names, retrieval attempts, filter or validator versions, and timestamps.
- Use an explicit truncated snapshot boundary marker instead of a normal end-of-text marker when the source was truncated.
- Assign IDs only after the relevant deterministic validation gate passes.

## Acceptance Criteria

- `ARCHITECTURE.md` and `CONVENTIONS.md` resolve the known Phase 0 consistency issues.
- Required scaffold files and directories exist, except paths blocked by workspace permissions are documented.
- `pyproject.toml` declares Python 3.11+, Pydantic v2, python-dotenv, pytest, and Ruff.
- No LLM SDK, web framework, ORM, scraper, or HTTP library is added.
- No working agents, database behavior, web retrieval, scraping, or LLM calls are implemented.
- `STATUS.md` and `HANDOFF.md` describe Phase 0 work and remaining risks.

## Commands To Verify The Phase

```powershell
pytest
ruff check .
ruff format --check .
```

## Unresolved Risks

- The `.agents/PLANS/phase-00-foundation.md` compatibility mirror may require a workspace permission or ACL change outside normal Phase 0 edits.
- Future schema work must translate the documented fields into concrete Pydantic models without weakening the exact-match validator requirements.
- Empty existing agent and test files remain placeholders until a later phase defines their contents.
