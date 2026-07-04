# Phase 04 - Analyst Rules, Reviewer Rules, and Ledger Admission

## Purpose

Implement deterministic Phase 4 policy for Analyst score interpretation, Statement
Reviewer approval and rejection handling, one-revision maximum, and Ledger admission
guards. This phase accepts typed Analyst and Reviewer artifacts or deterministic
fixtures only; it does not call an LLM.

## Files Changed

- `agents/analyst.py`
- `agents/reviewer.py`
- `tests/test_phase4.py`
- `.agent/plans/phase-04-ledger-admission.md`
- `STATUS.md`
- `HANDOFF.md`

## Implementation Design

- `agents/analyst.py` now defines an explicit 25-row `SCORE_PAIR_TABLE` for every
  Evidence Quality and Claim Fit pair from 1 through 5.
- `interpret_score_pair()` validates Evidence Quality and Claim Fit independently
  and returns the deterministic acceptance, Ledger score, placement, and reason.
- `score_candidate()` creates a typed `ScoreDecision` from the table, preserving the
  existing two-axis model contract and never creating a composite evidence score.
- `create_statement_draft()` only creates Ledger-bound drafts for Analyst-approved
  decisions that match the candidate.
- `admit_ledger_record()` reconstructs the final `LedgerRecord` from the candidate,
  snapshot, Analyst decision, statement draft, and Reviewer approval. It re-verifies
  snapshot integrity, quote offsets, exact Reviewer-approved text, placement, review
  attempt count, reviewer approval ID, and qualification requirements before creating
  the typed Ledger record.
- `agents/reviewer.py` now defines a strict `ReviewerInput` that contains only the
  extracted quote block, bracket context, draft statement, and Claim Fit score.
- `ReviewChecks` and `review_statement()` provide deterministic fixture-driven
  approval or rejection handling without replacement wording or LLM calls.

## Architectural Decisions

- No schema migration was needed. Existing strict Pydantic models and SQLite tables
  already carried the required Phase 4 fields.
- No dependencies were added to `pyproject.toml`. A local `.venv` was created only to
  install the dependencies already declared by the project so verification could run.
- Ledger admission always derives Ledger score and placement from the Analyst
  `ScoreDecision`; caller-provided placement changes are rejected.
- A quote block may create multiple Ledger records only through separate drafts and
  separate Reviewer approvals.
- Claim Fit 3, `qualified_only`, Partial entailment, and Weak entailment require an
  explicit qualification marker before Ledger admission.
- `verify_candidate_against_snapshot()` from Phase 3 is reused at Ledger admission so
  a matching hash alone is never treated as proof that the quotation exists at the
  recorded offsets.

## Acceptance Criteria

- All 25 Evidence Quality and Claim Fit score pairs are tested for acceptance,
  rejection, Ledger score, and placement.
- Evidence Quality and Claim Fit are validated separately.
- Analyst-rejected evidence cannot enter the Ledger.
- Reviewer-rejected drafts cannot enter the Ledger.
- A second Reviewer failure rejects the quote block.
- More than two Reviewer attempts are rejected as an invalid revision count.
- Missing `reviewer_approval_id` is rejected before Ledger admission.
- Altered statements after Reviewer approval are rejected.
- Unauthorized placement changes are rejected.
- Snapshot hash mismatch is rejected.
- Correct snapshot hash with incorrect quote offsets is rejected.
- Multiple separately reviewed Ledger claims from one quote block are allowed.
- Claim Fit 3 overclaims are rejected unless explicitly qualified.
- Partial and Weak entailment statements require explicit qualification.
- Reviewer input rejects forbidden fields.
- Ledger insert behavior remains append-only.
- No composite evidence score is produced or stored.

## Commands Run

```powershell
python -m pytest tests/test_phase4.py -q
```

Result: failed because `python` is not available on PATH in this shell.

```powershell
python3 -m pytest tests/test_phase4.py -q
```

Result: failed because the system Python did not have `pytest` installed.

```powershell
.venv/bin/python -m pip install -e '.[dev]'
```

Result: first failed under the sandbox because package index DNS was blocked. After
approval, it reached the package index but failed because setuptools package discovery
does not support this repository's current flat layout without explicit package
configuration. No package metadata was changed in Phase 4.

```powershell
.venv/bin/python -m pip install 'pydantic>=2.0,<3.0' 'python-dotenv>=1.0,<2.0' 'pytest>=8.0,<9.0' 'ruff>=0.8,<1.0'
```

Result: passed. These are the dependencies already declared in `pyproject.toml`.

```powershell
.venv/bin/python -m pytest tests/test_phase4.py -q
```

Result: final run passed, 43 passed in 0.20s.

```powershell
.venv/bin/python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q
```

Result: passed, 147 passed in 0.87s.

```powershell
.venv/bin/python -m ruff check .
```

Result: passed, all checks passed.

```powershell
.venv/bin/python -m ruff format --check .
```

Result: passed, 16 files already formatted.

## Exact Required Command Results

After the session-local `python` launcher was restored:

```powershell
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q
```

Result: passed, 147 passed in 0.82s on the first restored-launcher run and 147 passed
in 0.74s on the rerun after documentation updates.

```powershell
python -m ruff check .
```

Result: passed, all checks passed.

```powershell
python -m ruff format --check .
```

Result: passed, 16 files already formatted.

Earlier local equivalent verification before the launcher was restored:

```powershell
.venv/bin/python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q
```

Result: passed, 147 passed in 0.91s.

```powershell
.venv/bin/python -m ruff check .
```

Result: passed, all checks passed.

```powershell
.venv/bin/python -m ruff format --check .
```

Result: passed, 16 files already formatted.

## Unresolved Risks

- Qualification detection is deterministic and intentionally conservative. It checks
  for explicit qualification markers rather than performing semantic review.
- Reviewer approval is fixture-driven in Phase 4. Real LLM reviewer integration remains
  out of scope until a later phase.
- The `python` command currently resolves through a session-local temporary launcher.
  If Codex creates a new temporary PATH directory later, that launcher may need to be
  restored before rerunning the exact `python -m ...` commands.
- Editable package installation still fails because `pyproject.toml` does not declare
  package discovery for the flat `agents`, `prompts`, and `providers` layout. This was
  not changed because it is not required for Phase 4 tests.

## Next Phase Confirmation

At Phase 4 completion, Phase 5 Synthesizer schema, renderer, and release validator had
not started. Phase 5 has since completed; see `.agent/plans/phase-05-release-gate.md`,
`STATUS.md`, and `HANDOFF.md` for the current project state.
