# MVP-8.1 — Research Controls

## Authority and Boundary

The user explicitly authorized MVP-8.1 on 2026-08-10 after MVP-8 completed in commit
`1e1a0e7`. This is the canonical active phase plan. MVP-8.1 adds deliberate operator
controls for research depth, report length, presentation tone, and optional focus without
changing evidence admission, reviewer approval, Ledger facts, quotation rules, provider
boundaries, or final release policy.

## Scope

- Define frozen strict Pydantic control models and a strict aggregate run-controls model.
- Support a small bounded depth preset set that changes only approved retrieval/work
  limits, with equivalent support and oppose limits.
- Support bounded brief-length presets that change only synthesis structure and
  application-owned connective presentation.
- Support neutral, executive, academic, and plain-language presentation tones, applied
  only to application-owned framing/connective text.
- Support an optional typed focus constraint containing geographic area, timeframe,
  population, and analytical lens fields; never infer focus from the claim.
- Carry controls into Planner input, the provider-run contract/fingerprint, persisted run
  data, read-only reconstruction, CLI/live displays, and released-brief/export metadata.
- Reject unknown values and contradictory combinations clearly. Controls changed for an
  existing run require a new run ID; compatible resumes require exact control equality.
- Add regression coverage for defaults, accepted and rejected combinations, fingerprint
  mismatch/resume rejection, tone isolation, and all operator metadata displays.

## Non-Negotiable Invariants

- Every internal handoff is a frozen strict Pydantic model with
  `ConfigDict(extra="forbid")`; raw dictionaries are limited to persistence, API, logging,
  and export boundaries.
- Controls never change the public/non-sensitive restriction, budget ceilings, provider
  boundary, exact quotation validation, analyst/reviewer decisions, Ledger admission,
  approved factual statements, warnings, source metadata, or final validator.
- Tone never modifies Ledger statements, quotations, reviewer decisions, warnings, or
  source metadata. Length never changes factual content.
- Existing historical records remain readable. No control change may overwrite or repair
  a persisted run contract.
- No dependency, vendor, account, cloud service, live-network requirement, multi-claim
  comparison, source-authority scoring, or semantic-release rule is introduced.

## Likely Implementation Surfaces

- `models.py`, `provider_contract.py`, `providers/factory.py`, and
  `providers/mimo_factory.py` for contracts and exact fingerprints.
- `orchestrator.py`, `store.py`, and `cli.py` for run creation/resume/persistence and
  operator display.
- `agents/planner.py`, `agents/synthesizer.py`, `agents/renderer.py`, prompts, and
  `brief_export.py` for constrained planning, presentation, and released metadata.
- `frontend/live_service.py` and `frontend/live_app.py` for live display.
- A focused MVP-8.1 regression test module plus narrow updates to affected tests.

## Verification

- Run focused regression coverage first, then the complete offline `pytest` suite.
- Run `ruff check .`, `ruff format --check .`, deterministic evaluation, and
  `git diff --check`.
- Confirm no generated reports, databases, credentials, caches, dependencies, or live
  calls are added; inspect the final worktree and migration/compatibility behavior.

## Out of Scope

- Multi-claim comparison, source-authority scoring, semantic-release policy changes,
  new provider behavior, live-network requirements, accounts, cloud storage, and
  dependency changes.
