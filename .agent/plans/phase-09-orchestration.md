# Phase 09 - Real Orchestration and Controlled Concurrency

## Purpose

Connect the completed retrieval, LLM, deterministic integrity, Reviewer, Ledger,
synthesis, rendering, and validation surfaces into a provider-backed synchronous
orchestrator. Phase 9 adds controlled two-worker Researcher concurrency, audited retry
and ordered model fallback, restart-safe checkpoints, cancellation between stages,
explicit terminal states, and model/retrieval budgets. Normal tests remain deterministic
and offline through injected fake providers.

## Files Changed

- `orchestrator.py`
- `cli.py`
- `agents/supportingresearcher.py` (typed Extractor provenance compatibility fix)
- `providers/llm.py`
- `models.py` as the smallest compatibility extension for strict Phase 9 persistence
  artifacts and explicit terminal run states
- `store.py` as the smallest compatibility extension required to keep all SQLite schema
  definitions in `init_db()` and persist restart-safe Phase 9 audit/checkpoint state
- `tests/test_phase9.py`
- `.agent/plans/phase-09-orchestration.md`
- `STATUS.md`
- `HANDOFF.md`

## Implementation Design

- Preserve `run_fixture_pipeline()` unchanged as the Phase 6 offline fixture surface and
  add a separate provider-backed orchestration entry point.
- Create the run before the Planner call and persist an explicit status and current
  stage after every boundary.
- Invoke Planner, Extractor, Analyst, Reviewer, and Synthesizer through the Phase 8
  typed provider boundary. Every provider response is revalidated into the exact
  application-selected Pydantic output type.
- Run the supporting and opposing Researchers with `ThreadPoolExecutor(max_workers=2)`.
  Workers never share a SQLite connection and return strict typed result artifacts.
- Persist coordinator-owned retrieval, snapshot, candidate, Analyst, Reviewer, Ledger,
  synthesis, validation, checkpoint, and terminal-state artifacts idempotently.
- Keep snapshots and Ledger records insert-only. Existing deterministic IDs are used to
  verify a restart artifact instead of creating a duplicate.
- Check cancellation only between visible synchronous stages; do not create background
  workers or hidden polling tasks.
- Expose partial-run inspection and an explicit cancellation request API backed by the
  run database.
- Enforce equal fixed retrieval limits for both sides and an overall model-call budget.
  Optional token and cost totals are recorded and enforced when the provider exposes
  typed usage metadata.

## Architectural Decisions

- The Phase 9 SQLite extension is necessary because Phase 8 intentionally kept its
  richer invocation record in memory, while Phase 9 requires attempt history and model
  routes to survive database reopen and restart. The extension stays in `store.py` so
  the convention that all schema definitions live in `init_db()` remains true.
- Phase 9 persistence artifacts are strict Pydantic models with `extra="forbid"`.
  JSON is used only in SQLite payload columns and inspection/export boundaries.
- Researcher workers may open short-lived worker-local connections to reserve and
  finalize model-attempt audit rows. They never receive or share a connection, cursor,
  or transaction.
- A failure on one Researcher side is a typed explicit side failure. The other side may
  continue; two failed sides or no usable candidates produce an explicit failed run.
- Truth-sensitive output from any fallback alias still passes the exact same local
  schema validation, snapshot verification, post-extraction filter, Reviewer gate,
  Ledger admission, and final release validator.

## Exact Retry and Fallback Policy

- Each configured alias may be called at most twice for the same deterministic stage
  operation: the initial call and one retry.
- The current alias is retried only after an objective transient provider failure,
  timeout, malformed/non-Pydantic output, schema failure, or deterministic validation
  failure.
- After the alias retry limit, the next alias is used only with a recorded objective
  escalation reason. Capability/configuration errors are not retried or escalated.
- Extractor order is exactly `mimo-v2.5`, then `mimo-v2.5-pro`, then
  `deepseek-v4-flash`.
- Extractor MiMo Pro escalation requires an objective recorded reason such as repeated
  schema failure, exact-quote/post-filter failure, explicit ambiguity, or a declared
  context/complexity limit. DeepSeek Flash is used only as a third-line availability
  fallback after MiMo Pro transient/timeout/provider-availability exhaustion.
- A valid semantic output is never switched merely because it disagrees with another
  semantic output or because confidence prose is low. Reviewer rejection triggers the
  architecture-approved single Analyst revision, not a silent provider switch.

## Restart Idempotency

- Each LLM operation has a deterministic operation ID. Each route attempt has a
  deterministic attempt ID derived from run, operation, alias, route position, and
  per-alias attempt number.
- Attempt rows store stage, alias, pinned snapshot, attempt number, failure/retry/
  escalation reasons, timestamps, latency, optional token/cost metadata, and the typed
  output serialized only at the SQLite boundary.
- Usage metadata already returned by the provider is retained when typed output later
  fails an exact-quote or other deterministic validation gate, so retries remain fully
  counted against configured token and cost budgets.
- Completed attempts are revalidated and reused after restart. Failed attempts remain
  immutable audit history and routing resumes at the next allowed retry or fallback.
- Stage checkpoints are written only after their canonical artifacts are persisted.
  Restart skips completed checkpoints and resumes the first incomplete/failed stage.
- Insert-only snapshots and Ledger rows are read and compared on duplicate IDs; they are
  never updated, deleted, or blindly reinserted.

## Acceptance Criteria

- Full provider-backed orchestration can release a deterministic final brief using only
  fake providers in normal tests.
- One-side failure, both-side failure, partial retrieval, extraction failure, Analyst
  failure, Reviewer revision/second failure, validator block, restart, duplicate retry,
  cancellation, database reopen, worker connection isolation, equal retrieval budgets,
  model/retrieval budget exhaustion, retry-before-fallback, objective Extractor
  escalation, no semantic-disagreement escalation, DeepSeek gate preservation,
  restart-safe attempt metadata, and duplicate prevention are covered.
- Every run ends in an explicit released, blocked, failed, or cancelled state.
- Blocked, failed, and cancelled runs have no final rendered hash.
- No dependency, async rewrite, live-network normal test, evaluation corpus, Phase 10
  metric, production UI, or Phase 10 work is added.
- The exact Phase 1-through-9 pytest command and both Ruff commands pass, or any bare
  launcher failure is documented together with the identical successful repository
  virtual-environment run.

## Commands Run

```bash
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py tests/test_phase8.py tests/test_phase9.py -q
python -m ruff check .
python -m ruff format --check .
```

The exact bare commands failed before project execution because `python` is not on this
shell's `PATH`. They were repeated identically with `PATH="$PWD/.venv/bin:$PATH"` and
without setting `PYTHONPATH`; all passed with the results below. A focused Phase 9 run
and a full repository pytest run were also completed.

## Exact Test Results

- Focused Phase 9 suite:
  `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase9.py -q` passed with
  27 tests.
- Required Phase 1-through-9 selection:
  `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py tests/test_phase8.py tests/test_phase9.py -q`
  passed with 264 passed and 1 skipped in 4.54s.
- Full repository suite: `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q` passed with
  270 passed and 1 skipped in 4.51s.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: 28 files already
  formatted.
- The one skip is the Phase 8 optional integration gate because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.
- Each exact bare `python -m ...` command was also run first and failed before project
  execution with `zsh: command not found: python`; `PYTHONPATH` was never set.

## Unresolved Risks

- No real search, scraper, or LLM vendor adapter exists; Phase 9 proves orchestration
  through strict injected provider contracts and offline fakes.
- Provider-side token/cost reporting is optional. Calls without typed usage metadata
  retain explicit `None` usage fields rather than guessed values.
- The provider-backed API requires injected Search, Scraper, and LLM implementations;
  this repository still intentionally contains no live vendor adapter.
- Bare `python` remains unavailable unless `.venv/bin` is placed on `PATH`.

## Next Phase Confirmation

Phase 10 evaluation and adversarial testing was not started and was not implemented as
part of Phase 9. The next exact task is Phase 10 evaluation and adversarial testing,
only after explicit user direction.
