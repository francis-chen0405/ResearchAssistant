# Phase 10 - Evaluation and Adversarial Testing

## Purpose

Build a deterministic offline evaluation framework for the completed MVP. Measure
citation and snapshot integrity, bracket correctness, deterministic release resistance,
Analyst and Reviewer behavior, retrieval parity, model routing, fallback safety, model
quality comparisons, correlated errors, completion time, and cost when token metadata is
available. Optional live model comparison remains opt-in and uses the same frozen inputs
as the offline corpus.

## Files Changed

- `evaluations/`
- `evaluations/cases/`
- `evaluations/run_evaluations.py`
- `evaluations/README.md`
- `tests/test_phase10.py`
- `tests/fixtures/phase10/`
- `.agent/plans/phase-10-evaluation.md`
- `STATUS.md`
- `HANDOFF.md`

No earlier implementation file is expected to change. If evaluation exposes an earlier
compatibility defect, only the smallest documented fix with a regression test is
permitted.

## Implementation Design

- Load JSON only at the corpus boundary and immediately validate it into strict,
  immutable Pydantic evaluation artifacts with `extra="forbid"`.
- Execute snapshot, citation, and bracket cases against the existing deterministic
  integrity helpers.
- Execute mutation and unsupported-claim attacks against the existing Phase 5 final
  validator using typed `LedgerRecord` and `SynthesisOutput` artifacts.
- Evaluate prompt-injection cases through the existing untrusted-source envelope and
  through final-validator mutation attacks.
- Calculate route, retry, fallback, failure, token, cost, and fallback-gate metrics from
  frozen deterministic fake-provider attempt cases that cover primary success, retry,
  backup, and third-line paths.
- Emit one strict machine-readable report and derive the human-readable summary from
  that same report. Any unexpected case outcome is named in the failure list and causes
  a nonzero script exit.
- Keep strict frozen regression expectations separate from corpus expectations and
  compare both to observed gate behavior so fixtures cannot become self-fulfilling.
- Validate full configured route aliases, one-retry sequencing, required route coverage,
  MiMo normal/Pro quality pairs, same-model correlated-error coverage, and pricing for
  every token-bearing alias.
- Keep output ordering, timestamps, corpus data, and metric rounding deterministic so
  identical corpus inputs produce identical results.

## Architectural Decisions

- Evaluation does not alter routing defaults, validators, Reviewer policy, Ledger
  admission, or final release rules.
- Offline route cases model fake-provider outcomes and persisted token metadata; they do
  not pretend to measure live semantic quality.
- Optional live comparison requires an explicitly supplied provider and opt-in flag. It
  receives the exact frozen corpus input for every alias and records the exact alias and
  pinned snapshot used. Normal evaluation never opens a network connection.
- A fallback is safe only when every required deterministic, Reviewer, Ledger, and final
  gate is recorded. Fallback success never implies release authorization by itself.
- Same-model Analyst/Reviewer correlated errors are reported as risks; they are never
  removed from denominators or silently skipped.
- No dependency is added.

## Evaluation Design for MiMo Normal vs. Pro Stage Ownership

- Compare MiMo V2.5 and MiMo V2.5 Pro on the same frozen input IDs for each represented
  stage and report Pro-minus-normal quality delta overall and by stage.
- Report malformed-output and exact-quote-failure rates separately by exact alias.
- Combine quality separation with primary success, retry, fallback, latency, and cost
  measurements. Benchmark preference alone is insufficient to change a route.
- Retain current defaults unless repeated frozen-corpus and optional live evidence shows
  a material quality or reliability improvement for the candidate alias without worse
  gate escapes, unacceptable cost/latency, or loss of Reviewer independence.
- Any later default change belongs to post-MVP hardening and requires its own explicit
  decision and regression verification.

## Offline and Optional Live Separation

- Offline evaluation is the normal path, uses frozen cases/fakes, and is deterministic.
- Live comparison is skipped unless explicitly enabled and a provider is supplied.
- Live calls use the same frozen input text and IDs for MiMo normal, MiMo Pro, and the
  Extractor-specific DeepSeek Flash comparison, and record exact aliases and snapshots.
- Live results are observations only; they do not bypass or modify deterministic gates.

## Acceptance Criteria

- The offline runner writes deterministic JSON and Markdown outputs.
- Every required metric is present and internally consistent.
- Invalid, unexpected, or unevaluated cases appear explicitly in the failure report.
- Snapshot, quote, bracket, placement, unsupported-claim, prompt-injection, and mutation
  attacks are blocked or reported as configured.
- Primary, retry, backup, and third-line fake-provider routes are covered.
- Fallback output cannot be counted safe without all required gates.
- Live comparison is skipped by default and uses frozen identical inputs when enabled.
- Cost calculations reproduce configured pricing and recorded token usage.
- Existing validators and acceptance thresholds are unchanged.

## Commands Run

The exact required commands were run first:

```bash
python evaluations/run_evaluations.py
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py tests/test_phase8.py tests/test_phase9.py tests/test_phase10.py -q
python -m ruff check .
python -m ruff format --check .
```

All four failed before project execution with `zsh: command not found: python` because
this shell does not expose a bare `python` executable.

The identical commands were then run without setting `PYTHONPATH`, with the existing
repository virtual environment first on `PATH`:

```bash
PATH="$PWD/.venv/bin:$PATH" python evaluations/run_evaluations.py
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py tests/test_phase8.py tests/test_phase9.py tests/test_phase10.py -q
PATH="$PWD/.venv/bin:$PATH" python -m ruff check .
PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .
```

Additional focused verification:

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase10.py -q
PATH="$PWD/.venv/bin:$PATH" python -m pytest -q
git diff --check
```

## Exact Test Results

- Offline evaluation: passed, 38 cases evaluated, optional live comparison explicitly
  skipped, no evaluation failures.
- Focused Phase 10 suite: 30 passed.
- Required Phase 1-through-10 selection: 294 passed, 1 skipped.
- Full repository suite: 300 passed, 1 skipped.
- The one skip is the optional Phase 8 integration test because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.
- Ruff check: all checks passed.
- Ruff format check: 33 files already formatted.
- `git diff --check`: passed.

## Unresolved Risks

- Offline quality scores are frozen evaluation labels, not evidence of live provider
  behavior.
- The repository still has no live vendor adapter; optional live comparison therefore
  requires an injected implementation outside normal evaluation.
- Frozen pricing is evaluation configuration, not a claim about current vendor pricing.
- Bare `python` remains unavailable unless `.venv/bin` is placed first on `PATH`.

## Next Phase Confirmation

Post-MVP hardening based on evaluation results was not started.
