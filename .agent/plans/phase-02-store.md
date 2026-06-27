# Phase 02 - Store

## Purpose

Implement the SQLite persistence layer for the Debate Research Agent System using Python's built-in `sqlite3` module, without adding an ORM or additional dependencies.

## Files Changed

- `store.py`
- `tests/test_phase2.py`
- `models.py` (minor fix: `_validate_aware_datetime` now handles `None` for optional fields)
- `.agent/PLANS.md`
- `.agent/plans/phase-02-store.md`
- `STATUS.md`
- `HANDOFF.md`

## Architectural Decisions

- All schema definitions live in `store.py` inside a single `init_db()` function.
- Every connection enables foreign keys via `PRAGMA foreign_keys = ON`.
- Connections are created and closed per function call; no global connections are used.
- Read functions return Pydantic models; write functions accept Pydantic models.
- Snapshots and Ledger records tables are INSERT-ONLY — no update or delete functions exist.
- Multi-write operations (planner output, synthesis, validation) use explicit transactions with rollback on failure.
- Timestamps are stored as UTC ISO-8601 strings and reconstructed as timezone-aware datetimes.
- `evidence_quality` and `claim_fit` remain separate columns; `ledger_score` is derived only after both axes pass eligibility.
- Segment offsets are stored as JSON strings and reconstructed as typed `SegmentOffset` lists.
- Boolean values are stored as integers (0/1) per SQLite convention.
- Clear parent-child artifact relationships are enforced with SQLite foreign keys where the architecture defines them.

## Acceptance Criteria

- `init_db()` creates all required tables: runs, planner outputs, claim definitions, ambiguities, search queries, retrieval attempts, snapshots, provisional extractions, candidates, analyst decisions, statement drafts, statement review attempts, ledger records, synthesis attempts, synthesis sections, synthesis items, validation runs, validation errors, and model invocations.
- Foreign keys are enforced on every connection.
- Insert and read round trips preserve all fields for every artifact type.
- Data survives database close and reopen.
- Snapshots and Ledger records reject duplicate inserts and expose no update/delete functions.
- Multi-write transactions roll back completely on failure.
- Invalid foreign key references are rejected.
- Stored rows reconstruct into correctly typed Pydantic models.
- Duplicate identifiers are rejected via PRIMARY KEY constraints.
- No ORM, web retrieval, LLM calls, or orchestration are introduced.
- `STATUS.md` and `HANDOFF.md` are updated for Phase 2.

## Commands To Verify The Phase

```powershell
pytest tests/test_phase2.py
ruff check .
ruff format --check .
```

## Unresolved Risks

- Phase 3 will need to implement retrieval logging and web search integration.
- Concurrent researcher workers must each open their own connections; this is enforced by design but not yet tested under threading.
