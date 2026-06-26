# Phase 01 - Models

## Purpose

Define the typed Pydantic v2 contracts used for internal handoffs in the Debate Research Agent System without implementing database operations, retrieval, LLM calls, orchestration, or rendering.

## Files Being Changed

- `models.py`
- `tests/test_phase1.py`
- `.agent/PLANS.md`
- `.agent/plans/phase-01-models.md`
- `STATUS.md`
- `HANDOFF.md`

## Architectural Decisions

- All internal handoffs are represented as Pydantic model instances.
- Release-relevant models carry UUID identifiers, stage provenance, source or snapshot provenance, prompt/model versions, and timezone-aware timestamps.
- `evidence_quality` and `claim_fit` remain separate 1-through-5 dimensions; no composite score is modeled.
- Approved Ledger records require `reviewer_approval_id` and non-empty approved factual statements.
- Segment offsets must be ordered and non-overlapping.
- Synthesis items carry stance, placement, entailment, Ledger IDs, reviewer approval IDs, and exact approved factual statements so later validation can compare them against Ledger records.

## Acceptance Criteria

- Phase 1 models cover the architecture-required handoff artifacts.
- Invalid score ranges, missing reviewer approvals, invalid enum values, reversed or overlapping offsets, naive datetimes, empty approved factual statements, invalid section types, and malformed validation errors are rejected at model construction.
- No database behavior, web retrieval, scraping, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, HTTP clients, or additional dependencies are introduced.
- `STATUS.md` and `HANDOFF.md` are updated for Phase 1.

## Commands To Verify The Phase

```powershell
pytest tests/test_phase1.py
ruff check .
ruff format --check .
```

## Unresolved Risks

- Later phases must map these contracts to persistence carefully without adding raw-dictionary handoffs.
- Exact quote membership, bracket validation, and final rendered-text matching are intentionally not implemented in Phase 1.
