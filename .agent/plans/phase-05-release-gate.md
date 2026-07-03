# Phase 05 - Synthesizer Schema, Renderer, and Release Validator

## Purpose

Implement the deterministic Phase 5 release gate: typed `SynthesisOutput` creation,
approved non-factual connective templates, final rendering, exact Ledger validation, and
SHA-256 hashing only for valid rendered briefs.

## Files Changed

- `agents/synthesizer.py`
- `agents/renderer.py`
- `tests/test_phase5.py`
- `tests/fixtures/phase5_expected_valid_brief.txt`
- `.agent/plans/phase-05-release-gate.md`
- `STATUS.md`
- `HANDOFF.md`

## Implementation Design

- `agents/synthesizer.py` now builds a typed `SynthesisOutput` from typed
  `LedgerRecord` instances only.
- The synthesizer copies Ledger IDs, Reviewer approval IDs, stance, placement,
  entailment, and approved factual statements exactly from the Ledger.
- Ledger records are grouped deterministically into supporting, opposing, and
  limitations sections, ordered by Ledger placement and ID.
- `agents/renderer.py` defines the fixed approved connective template registry as
  strict Pydantic configuration artifacts.
- The final validator revalidates the `SynthesisOutput` model shape, checks for hidden
  extra instance fields, compares every item against the Ledger, enforces section and
  template compatibility, enforces one final use per Ledger claim, and computes a
  rendered brief hash only after all checks pass.
- The renderer assembles text mechanically from the title, Planner claim framing,
  approved template text, exact Ledger factual statements, and Ledger source URLs.

## Architectural Decisions

- No model or SQLite schema change was required. Existing Phase 1 models already carry
  the fields needed for Phase 5 validation.
- No dependencies were added.
- The maximum final rendered use count is one per Ledger claim for Phase 5.
- `qualified_only` Ledger items require an approved qualification-capable template.
- Partial and Weak entailment items require their corresponding warning templates.
- Invalid releases return the existing typed `ValidationResult` with
  `valid=False` and `rendered_brief_hash=None`.
- `render_brief()` refuses to render invalid synthesis artifacts instead of returning
  partial output.

## Acceptance Criteria

- The renderer never invents facts.
- The renderer never paraphrases Ledger factual statements.
- Rendered factual statements come only from exact approved Ledger statements.
- Approved non-factual connective text comes only from the fixed registry.
- Correct Ledger IDs paired with altered statements fail.
- Correct statements paired with wrong Ledger IDs fail.
- Reviewer approval ID drift fails.
- Placement and stance drift fail.
- `qualified_only` evidence cannot be promoted.
- Qualified evidence without a qualification-capable template fails.
- Partial and Weak entailment items without warning templates fail.
- Supporting and opposing evidence cannot be rendered in the opposite side's section.
- Unknown templates and free-form factual transition strings fail.
- Hidden prose in extra instance fields fails.
- Reusing one Ledger claim too many times fails.
- Statements not present in the Ledger fail.
- Valid output produces a stable rendered brief and stable hash.
- Invalid output produces no final hash.

## Commands Run

```powershell
python -m pytest tests/test_phase5.py -q
```

Result: first run failed only on the intentional hash placeholder; final run passed with
21 passed in 0.12s.

```powershell
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py -q
```

Result: passed, 168 passed in 0.73s.

```powershell
python -m ruff check .
```

Result: passed, all checks passed.

```powershell
python -m ruff format --check .
```

Result: passed, 17 files already formatted.

## Exact Test Results

- `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py -q`:
  168 passed in 0.73s.
- `python -m ruff check .`: all checks passed.
- `python -m ruff format --check .`: 17 files already formatted.

## Unresolved Risks

- Template compatibility is deterministic configuration, not semantic review.
- The renderer includes Ledger `source_url` citations mechanically; no citation
  formatting beyond deterministic URL inclusion was added.
- The synthesizer helper is fixture/deterministic only. It does not call an LLM and does
  not perform orchestration.

## Next Phase Confirmation

Phase 6 fixture-only complete pipeline was not started.
