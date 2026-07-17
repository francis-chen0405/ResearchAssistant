# Phase 08 - LLM Provider and Structured Prompts

## Purpose

Implement a vendor-isolated synchronous LLM boundary, strict per-stage model routing,
versioned structured prompts, typed stage inputs, local schema enforcement, and complete
invocation provenance. Phase 8 uses deterministic fake providers in normal tests and
does not begin Phase 9 orchestration, concurrency, runtime retry, or runtime failover.

## Files Changed

- `providers/llm.py`
- `prompts/planner.md`
- `prompts/extractor.md`
- `prompts/analyst.md`
- `prompts/reviewer.md`
- `prompts/synthesizer.md`
- `agents/planner.py`
- `agents/supportingresearcher.py`
- `agents/analyst.py`
- `agents/synthesizer.py`
- `tests/test_phase8.py`
- `.env.example`
- `.agent/plans/phase-08-llm-integration.md`
- `STATUS.md`
- `HANDOFF.md`

`.env.example` documents only the blank `RUN_LLM_INTEGRATION_TESTS` opt-in gate. Phase
8 adds no live vendor adapter, API-key variable, or dependency.

## Implementation Design

- `LLMProvider` is a runtime-checkable synchronous Protocol. It receives one immutable
  `LLMRequest` and must return a Pydantic model instance, never a raw dictionary.
- `build_stage_request()` accepts a Pydantic input artifact, one or more input artifact
  IDs, an application-selected Pydantic output type, the validated routing
  configuration, and an optional pinned model snapshot. It loads the stage prompt,
  records its declared version and SHA-256 hash, selects only the configured primary
  alias, and renders the application-owned output schema and typed input.
- Stage-to-output-type policy is application-controlled: Planner requests
  `PlannerOutput`; Extractor requests `ProvisionalCandidate`; Analyst requests
  `ScoreDecision` or `StatementDraft`; Reviewer requests `StatementReviewResult`; and
  Synthesizer requests `SynthesisOutput`.
- `invoke_llm()` executes exactly one provider call. It rejects non-Pydantic responses,
  revalidates Pydantic responses through the exact requested model so missing, invalid,
  or extra fields fail, and returns only a typed output paired with a strict invocation
  record.
- Failed calls raise a clear typed exception carrying the failed invocation record.
  Invalid or failed responses never become output artifacts and cannot become approved
  artifacts.
- Invocation provenance records run and invocation IDs, stage, prompt version and hash,
  requested output type, model alias, optional pinned snapshot, configured fallbacks,
  input artifact IDs, timezone-aware start and end timestamps, status, retry metadata,
  failure code/message/retryability, and explicit `fallback_executed: false`.
- Retry metadata is audit-only in Phase 8. `invoke_llm()` contains no retry loop and no
  fallback loop.
- Provider capability metadata explicitly declares temperature and structured-output
  control support. Requested unsupported controls raise an invocation capability error;
  they are never silently dropped. A caller may explicitly configure `temperature=None`
  or disable the provider-native structured-output control, while local Pydantic output
  validation remains mandatory.
- `PlannerLLMInput`, `ExtractionLLMInput`, `AnalystLLMInput`, the existing narrow
  `ReviewerInput`, and `SynthesizerLLMInput` preserve typed stage boundaries.
- Snapshot text is wrapped in `UntrustedSourceText`, labeled
  `UNTRUSTED_SOURCE_TEXT`, and paired with a fixed instruction policy requiring every
  instruction inside the source to be ignored. Snapshot integrity is rechecked before
  extraction input construction, and candidate/snapshot integrity is rechecked before
  Analyst input construction.
- Each prompt has a `Prompt-Version` and `Stage` header. The exact UTF-8 file contents
  are SHA-256 hashed, so prompt edits are auditable even when the declared version is
  accidentally left unchanged.

## Architectural Decisions

- Routing, prompt choice, requested schema, validators, IDs, and downstream behavior
  remain application-owned. None are fields the model may choose in a stage input or
  model output.
- MiMo Pro is reserved for high-leverage reasoning in Planner, Analyst, and Synthesizer
  stages. MiMo normal handles repeated grounded extraction and independent Reviewer
  audit work. This keeps the stronger alias focused on tasks where broader reasoning has
  the highest leverage while using the normal alias for high-volume, tightly bounded
  work.
- DeepSeek aliases are third-line availability fallbacks only. They do not bypass
  deterministic snapshot/post-extraction checks, Reviewer approval, Ledger admission,
  or the deterministic final release validator.
- Phase 8 defines and validates fallback order but never executes automatic failover.
  Phase 9 remains responsible for runtime retry, restart, fallback, budgets,
  cancellation, and controlled concurrency.
- The richer Phase 8 invocation record is an in-memory typed audit artifact. Persisting
  and coordinating provider-backed invocations belongs to Phase 9; the Phase 2 SQLite
  schema and store were not changed outside the allowed Phase 8 files.
- Pydantic `arbitrary_types_allowed` is used only on `LLMRequest` and
  `LLMInvocationResult` so those strict, frozen models can carry Pydantic instances and
  model classes without converting internal handoffs to dictionaries. Both retain
  `extra="forbid"` and explicit instance validators.
- No LLM SDK, HTTP client, provider adapter, API key, network dependency, database
  migration, async code, or new dependency was added.

## Default Model Routing

| Stage | Primary | Backup | Third line | Temperature |
|---|---|---|---|---:|
| Planner | `mimo-v2.5-pro` | `mimo-v2.5` | `deepseek-v4-pro` | 0.2 |
| Extractor | `mimo-v2.5` | `mimo-v2.5-pro` | `deepseek-v4-flash` | 0.0 |
| Analyst | `mimo-v2.5-pro` | `mimo-v2.5` | `deepseek-v4-pro` | 0.1 |
| Reviewer | `mimo-v2.5` | `mimo-v2.5-pro` | `deepseek-v4-pro` | 0.0 |
| Synthesizer | `mimo-v2.5-pro` | `mimo-v2.5` | `deepseek-v4-pro` | 0.15 |

Each route requires exactly one primary and accepts at most two ordered, distinct,
known fallback aliases.

## Acceptance Criteria

- Fake-provider calls return validated typed Planner, extraction, Analyst, Reviewer,
  and Synthesis artifacts.
- Raw dictionary responses, wrong Pydantic schemas, malformed values, and extra fields
  are rejected before an artifact is returned.
- Pydantic input artifacts and application-selected output types are enforced.
- Prompt versions and exact hashes are recorded; a material prompt edit changes the
  hash deterministically.
- Success and failure records contain complete timestamps, model/prompt provenance,
  input artifact IDs, and retry/failure metadata.
- Reviewer input rejects claim context, Evidence Quality, stance, Analyst rationale,
  and model-routing fields.
- Source prompt-injection text remains visible only inside an explicit untrusted-data
  envelope whose fixed policy says to ignore embedded instructions.
- Normal tests make no network call. The optional integration gate skips unless
  `RUN_LLM_INTEGRATION_TESTS=1` is set.
- Routing rejects missing stages, missing/empty/unknown aliases, duplicate aliases, and
  more than two fallbacks.
- Per-stage generation settings are typed and temperature-bounded.
- Unsupported provider controls fail explicitly or must be disabled explicitly; local
  schema validation is never disabled.
- One failed primary call produces one failed record and no fallback execution.
- No Phase 9 behavior is implemented.

## Commands Run

The three exact commands from the Phase 8 prompt were run first:

```bash
python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py tests/test_phase8.py -q
python -m ruff check .
python -m ruff format --check .
```

All three failed before project execution with `zsh: command not found: python` because
this shell does not expose a bare `python` executable.

The identical commands were then run without setting `PYTHONPATH`, with the repository
virtual environment placed first on `PATH`:

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py tests/test_phase8.py -q
PATH="$PWD/.venv/bin:$PATH" python -m ruff check .
PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .
```

Additional full-suite verification:

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest -q
```

## Exact Test Results

- Focused Phase 8 suite: 34 passed, 1 skipped in 0.18s.
- Required Phase 1 through Phase 8 selection: 237 passed, 1 skipped in 2.14s.
- Full pytest suite: 243 passed, 1 skipped in 2.28s.
- Ruff check: all checks passed.
- Ruff format check: 27 files already formatted.
- The one skip is the optional integration gate because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.

## Unresolved Risks

- Phase 8 has no real vendor adapter or live model call. Provider-specific snapshot
  names and capability declarations must be supplied by a future adapter.
- Local schema validation can prove artifact shape, provenance, and forbidden extra
  fields, but cannot prove semantic model quality; deterministic filters, independent
  Reviewer approval, Ledger admission, and final validation remain mandatory.
- Invocation persistence, automatic retry/fallback, restart behavior, cancellation,
  budgets, and provider-backed stage coordination remain unimplemented by design.
- Bare `python` remains unavailable unless `.venv/bin` is placed on `PATH`.

## Next Phase Confirmation

Phase 9 real orchestration and controlled concurrency was not started.
