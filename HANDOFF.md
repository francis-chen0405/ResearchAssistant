# Handoff

## 2026-07-19 - Daily Expanded CI Maintenance

Current branch:

- `master`

Maintenance changes:

- `.github/workflows/ci.yml` runs on every pushed branch, pull requests targeting
  `master`, manual dispatch, and daily at 1:17 AM `America/Los_Angeles`.
- Pytest runs with branch coverage on Python 3.11 and 3.12. Ruff and the deterministic
  38-case offline evaluation each run once per workflow invocation.
- `pytest-cov>=6.0,<7.0` is an explicitly approved development dependency. Coverage is
  reported with missing lines but has no failure threshold.
- This is CI/tooling maintenance only. No new product phase, live provider, API key,
  network-dependent test, or runtime behavior was started.

Verification:

- Full pytest with branch coverage: 310 passed, 1 skipped; total coverage was 85%.
- Offline evaluation: all 38 deterministic cases passed; optional live comparison was
  skipped.
- Ruff lint and format checks, workflow YAML parsing, and `git diff --check` passed.

## 2026-07-19 - Phase MVP-1 Release-Contract Correctness

Current branch:

- `master`
- Changes are intentionally uncommitted.

Latest completed phase:

- Phase MVP-1 Release-Contract Correctness.
- No later post-MVP phase has started.

Implementation handoff:

- `SynthesisOutput` and `SynthesizerLLMInput` no longer contain title, displayed claim,
  or arbitrary heading fields. `SynthesisSection` contains only `section_type` and typed
  Ledger-backed items.
- `agents/renderer.py` owns the fixed title, claim label, exact authoritative claim
  insertion, structural headings, and present-section order. Release allows supporting,
  opposing, and limitations sections once each in canonical order.
- `ReviewerDecision` is the only model-facing Reviewer result. It forbids unknown fields
  and cannot carry an approval ID. Application code validates its exact reviewed text,
  derives an ID, and constructs the existing `StatementReviewResult`.
- Approval IDs use canonical sorted compact JSON over `rappr_v1`,
  `reviewer-decision-v1`, statement draft ID, quote block ID, exact reviewed text, and
  normalized `approved`. The SHA-256 result is prefixed `rappr_v1_`.
- Legacy UUID approval IDs remain accepted on persisted/domain review, Ledger, synthesis,
  and fixture records. New provider-backed approvals use `rappr_v1` strings.
- Existing SQLite synthesis title/claim/heading columns were not migrated or dropped;
  fixed constants are written and legacy contents are ignored when reading the new
  synthesis domain schema.
- Completed synthesis checkpoints backed by SQLite synthesis rows remain readable. An
  interrupted pre-MVP-1 run with only a cached serialized synthesis result is rejected
  on restart and must be restarted as a fresh run; it is not treated as a completed
  current-schema checkpoint.
- Fixture runs are inserted as running and finalized only after validation. Released
  fixtures persist as `RunStatus.COMPLETED`; validation blocks persist as
  `RunStatus.BLOCKED`.

Exact files changed:

- `.agent/PLANS.md`
- `.agent/plans/phase-mvp-1-release-contract-correctness.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`
- `STATUS.md`
- `HANDOFF.md`
- `models.py`
- `agents/reviewer.py`
- `agents/synthesizer.py`
- `agents/renderer.py`
- `providers/llm.py`
- `orchestrator.py`
- `store.py`
- `prompts/reviewer.md`
- `prompts/synthesizer.md`
- `evaluations/evaluator.py`
- `tests/test_mvp1.py`
- `tests/test_phase1.py`
- `tests/test_phase2.py`
- `tests/test_phase4.py`
- `tests/test_phase5.py`
- `tests/test_phase8.py`
- `tests/test_phase9.py`
- `tests/fixtures/basic_valid_run/synthesis.json`
- `tests/fixtures/invalid_release_run/synthesis.json`
- `tests/fixtures/phase5_expected_valid_brief.txt`

Independent verification corrections:

- Malformed nested synthesis structures now return a blocked schema validation result
  instead of raising `AttributeError`.
- Provider final validation now receives the persisted authoritative submitted claim
  directly, and the released hash is regression-checked against the reopened rendering.
- Architecture and restart/checkpoint compatibility documentation now match the MVP-1
  contract.

Verification results:

- Focused MVP-1: 10 passed.
- Relevant Phase 5/6/8/9/10: 126 passed, 1 skipped.
- Full pytest: 310 passed, 1 skipped.
- Offline evaluation: 38 cases passed; output was written under `/tmp`, not the repo.
- Fixture CLI smoke: valid released with hash
  `7fecea19e1b9f01ff3fe68ef9a2b3a79cf88f0a6fe82897332548c258cb9e89f`;
  invalid blocked with no hash.
- Reopened SQLite: valid status `completed`; invalid status `blocked`.
- Ruff check passed; Ruff format check reported 34 files already formatted and changed
  no files; `git diff --check` passed.

Remaining risks:

- Old serialized synthesis JSON carrying framing fields is intentionally incompatible
  and must be regenerated. Old SQLite synthesis rows remain readable.
- Ignored legacy synthesis framing columns remain in SQLite pending separately approved
  cleanup.
- A caller outside the repository orchestrators must pass the true authoritative claim
  to render/validate; the two repository orchestrators do so.

Do not start:

- Do not add live providers, network calls, dependencies, frontend changes, `.env`
  loading, live CLI behavior, multi-candidate extraction, cross-stance deduplication,
  database triggers, or another post-MVP phase without explicit direction.


## 2026-07-17 - Phase 10 Evaluation and Adversarial Testing

Current branch:

- `master`

Latest completed phase:

- Phase 10 Evaluation and Adversarial Testing.
- Post-MVP hardening has not started.

Files changed:

- `evaluations/__init__.py`
- `evaluations/schema.py`
- `evaluations/evaluator.py`
- `evaluations/run_evaluations.py`
- `evaluations/README.md`
- `evaluations/cases/offline-corpus.json`
- `evaluations/cases/regression-fixtures/`
- `evaluations/output/.gitignore`
- `tests/test_phase10.py`
- `tests/fixtures/phase10/`
- `.agent/plans/phase-10-evaluation.md`
- `STATUS.md`
- `HANDOFF.md`

Decisions made:

- Keep normal evaluation fully offline, deterministic, corpus-driven, and strict
  Pydantic throughout internal evaluation flow.
- Exercise the existing deterministic integrity and final-release gates directly; do
  not copy, weaken, configure around, or replace them.
- Score citation membership and macro-bracket correctness independently. A shifted
  offset can fail citation membership while still identifying the same surrounding
  sentences, and the corpus records those outcomes separately.
- Use frozen fake-provider attempt histories for route reliability, retry/fallback,
  failure-rate, token, and cost metrics. Keep offline semantic quality labels separate
  from optional live observations.
- Count fallback output safe only when Pydantic schema, snapshot integrity,
  post-extraction filter, Reviewer, Ledger admission, and final validator gates are all
  recorded. An unsafe fallback fixture forces the report to fail.
- Compare MiMo V2.5 and MiMo V2.5 Pro only on identical frozen input IDs and report
  stage-level deltas alongside reliability, latency, and cost. Do not change a route
  based on benchmark preference alone.
- Keep DeepSeek V4 Flash comparison Extractor-specific and use the same frozen Extractor
  input. No new provider vendor or route was added.
- Make optional live comparison an injected Protocol, skipped by default. Enabled calls
  must preserve exact frozen input, alias, and pinned snapshot identity.
- Report same-model Analyst/Reviewer correlated errors by case ID instead of removing
  them from results.
- Derive the human summary from the machine report and verify agreement before writing.
- Freeze regression expectations in strict fixture manifests so corpus labels cannot be
  changed to match a weakened or altered observed outcome.
- Validate the complete configured route alias path and the documented one-retry limit;
  reject missing MiMo normal/Pro quality pairs and token-bearing aliases without frozen
  pricing.
- Label frozen quality and pricing inputs in both report formats and use distinct runner
  exit codes `0`, `1`, `2`, and `3` for pass, evaluated failure, expected
  configuration/execution error, and unexpected internal error.
- Add no dependencies and make no earlier implementation-file compatibility change.

Commands run:

- Before edits, `git status --short --branch` reported
  `## master...origin/master` with no uncommitted changes.
- Before edits, `git log --oneline -10` showed
  `526a897 Complete Phase 9 orchestration` as the latest commit.
- All four exact bare verification commands were attempted and failed before project
  execution with `zsh: command not found: python`.
- The identical commands with `PATH="$PWD/.venv/bin:$PATH"`, without setting
  `PYTHONPATH`, all passed.
- Focused Phase 10 pytest passed.
- `git diff --check` passed.

Exact results:

- Offline evaluation: passed with 38 evaluated cases, explicit optional-live skip, and
  no failures.
- Focused Phase 10 suite: 30 passed.
- Required Phase 1-through-10 selection: 294 passed, 1 skipped.
- Full repository suite: 300 passed, 1 skipped.
- The one skip is the optional Phase 8 integration gate because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.
- Ruff check: all checks passed.
- Ruff format check: 33 files already formatted.

Known limitations:

- Frozen quality scores and pricing are evaluation inputs, not current provider claims.
- No live Search, Scraper, LLM, or live-evaluation adapter exists in the repository.
- Bare `python` remains unavailable unless `.venv/bin` is placed first on `PATH`.

Next exact task:

- Post-MVP hardening based on evaluation results, only after explicit user direction.

Do not start:

- Do not start post-MVP hardening without explicit user direction.
- Do not change routing defaults solely from frozen benchmark preference.
- Do not add live vendors, network-dependent normal evaluation, validator weakening,
  hidden skips, score inflation, production UI, or later work as a Phase 10 follow-up.

## 2026-07-17 - Phase 9 Real Orchestration and Controlled Concurrency

Current branch:

- `master`

Latest completed phase:

- Phase 9 Real Orchestration and Controlled Concurrency.
- Phase 10 has not started.

Files changed:

- `orchestrator.py`
- `cli.py`
- `agents/supportingresearcher.py`
- `providers/llm.py`
- `models.py` (strict Phase 9 persistence and terminal-state compatibility models)
- `store.py` (Phase 9 migration and typed checkpoint/attempt/cancellation operations)
- `tests/test_phase9.py`
- `.agent/plans/phase-09-orchestration.md`
- `STATUS.md`
- `HANDOFF.md`

Decisions made:

- Preserve `run_fixture_pipeline()` and add `run_provider_pipeline()` as a separate
  synchronous provider-backed surface.
- Use `ThreadPoolExecutor(max_workers=2)` only for the supporting and opposing
  Researchers. Workers return strict Pydantic results and use only short-lived
  worker-local SQLite connections for attempt audit reservations/finalization.
- Keep every SQLite schema definition in `store.py:init_db()`. The new schema migration
  is the minimal compatibility change required because Phase 8 intentionally kept rich
  route attempts in memory while Phase 9 requires restart-safe audit history.
- Assign deterministic operation and attempt IDs. Persist a running reservation before
  each provider call, finalize it with objective failure or typed output, and reuse
  completed typed output after restart.
- Retry an alias once only for objective transient, timeout, malformed-output, schema,
  exact-quote, interrupted, or deterministic validation failures. Record retry and
  escalation reasons explicitly.
- Enforce Extractor order `mimo-v2.5`, `mimo-v2.5-pro`, then
  `deepseek-v4-flash`. MiMo Pro requires an objective escalation reason. DeepSeek Flash
  remains a third-line availability fallback only.
- Never route on semantic disagreement or confidence prose. Reviewer rejection triggers
  one Analyst revision and one second review with the configured Reviewer primary unless
  an objective invocation failure independently authorizes retry/fallback.
- Subject all fallback output, including DeepSeek output, to the same local Pydantic,
  snapshot, exact-quote, post-filter, Analyst, Reviewer, Ledger, and final-validator
  requirements.
- Treat one Researcher-side failure as explicit partial evidence and allow the other
  side to continue. Treat both-side failure or no passing candidates as an explicit
  failed run.
- Persist explicit released, blocked, failed, and cancelled terminal states. Blocked,
  failed, and cancelled runs never carry a final hash.
- Retain provider-reported usage when typed output later fails an exact-quote or other
  deterministic validation gate, so failed retries remain represented in persisted
  token and cost totals.
- Keep snapshots and Ledger records insert-only. Reruns compare deterministic existing
  artifacts and never update, delete, or duplicate them.
- Carry typed `RetrievalRecord` provenance in Phase 9 Extractor input so the model never
  invents query ID, round, rank, URL, or retrieval-attempt metadata.
- Add no dependency, live adapter, async rewrite, evaluation corpus, Phase 10 metric,
  production UI, or Phase 10 behavior.

Commands run:

- `git status --short --branch`: before edits, `## master...origin/master`, with no
  uncommitted changes.
- `git log --oneline -10`: latest commit before Phase 9 edits was `dee6176 phase-08`.
- Exact bare Phase 1-through-9 pytest command: failed before project execution with
  `zsh: command not found: python`.
- Exact bare Ruff check and Ruff format commands: both failed before project execution
  with the same missing `python` error.
- Identical required commands with `PATH="$PWD/.venv/bin:$PATH"`, without setting
  `PYTHONPATH`: all passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase9.py -q`: passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q`: full repository suite passed.
- `git diff --check`: passed.

Exact results:

- Focused Phase 9 suite: 27 passed in 2.89s.
- Required Phase 1-through-9 selection: 264 passed, 1 skipped in 4.54s.
- Full repository suite: 270 passed, 1 skipped in 4.51s.
- Ruff check: all checks passed.
- Ruff format check: 28 files already formatted.
- The one skipped test is the optional Phase 8 integration gate because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.

Known limitations:

- No live Search, Scraper, or LLM vendor adapter exists. Phase 9 normal tests use only
  injected deterministic fake providers and make no live-service call.
- Optional token/cost totals require a provider to return strict
  `ModelUsageMetadata` through `usage_for()`; unavailable metadata remains explicit
  `None` rather than an estimate.
- Bare `python` remains unavailable unless `.venv/bin` is placed on `PATH`.

Next exact task:

- Phase 10 evaluation and adversarial testing, only after explicit user direction.

Do not start:

- Do not begin Phase 10 without explicit user direction.
- Do not add an evaluation corpus, Phase 10 metrics, new live vendor adapters,
  network-dependent normal tests, validator weakening, production UI, async rewrite, or
  later-phase behavior as a Phase 9 follow-up.

## 2026-07-16 - Phase 8 LLM Provider and Structured Prompts

Current branch:

- `master`

Latest completed phase:

- Phase 8 LLM Provider and Structured Prompts.
- Phase 9 has not started.

Files changed:

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

Decisions made:

- Keep the LLM boundary synchronous, vendor-neutral, Pydantic-only, and one-call-at-a-
  time. Phase 8 does not perform orchestration.
- Make model routing strict application configuration: exactly one primary and up to two
  ordered distinct fallbacks for every stage.
- Reserve MiMo Pro for Planner, Analyst, and Synthesizer high-leverage reasoning; use
  MiMo normal for repeated grounded Extractor and Reviewer work.
- Treat DeepSeek aliases as third-line availability fallbacks that never bypass
  deterministic checks, independent Reviewer approval, Ledger admission, or final
  validation.
- Record configured fallbacks while enforcing `fallback_executed: false`; runtime retry,
  failover, restart, cancellation, budgets, and controlled concurrency remain Phase 9.
- Reject unsupported temperature or provider-native structured-output controls
  explicitly. Callers may disable unsupported controls explicitly, but local exact
  Pydantic schema validation always remains active.
- Carry Pydantic instances and requested Pydantic model classes in strict frozen request
  and result artifacts; never convert internal handoffs to raw dictionaries.
- Label source text `UNTRUSTED_SOURCE_TEXT`, ignore all embedded instructions, and
  recheck deterministic integrity before Extractor/Analyst prompt construction.
- Add no SDK, HTTP client, live vendor adapter, API key, dependency, database migration,
  async code, evaluation corpus, or Phase 9 behavior.
- Document only the blank `RUN_LLM_INTEGRATION_TESTS` opt-in gate in `.env.example`.

Commands run:

- Exact bare Phase 1-8 pytest command: failed before execution with
  `zsh: command not found: python`.
- Exact bare Ruff check and format commands: failed before execution with the same
  missing `python` error.
- Identical required commands with `PATH="$PWD/.venv/bin:$PATH"`: all passed without
  setting `PYTHONPATH`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase8.py -q`: passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q`: full suite passed.

Exact results:

- Focused Phase 8 suite: 34 passed, 1 skipped in 0.18s.
- Required Phase 1 through Phase 8 selection: 237 passed, 1 skipped in 2.14s.
- Full pytest suite: 243 passed, 1 skipped in 2.28s.
- Ruff check: all checks passed.
- Ruff format check: 27 files already formatted.
- The one skipped test is the optional integration gate because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.

Known limitations:

- No real LLM vendor adapter, API call, or live integration test exists.
- The richer invocation record is currently an in-memory typed audit artifact;
  persistence and provider-backed stage coordination remain Phase 9 work.
- Phase 8 validates fallback order but does not execute automatic retry or failover.
- Bare `python` remains unavailable unless `.venv/bin` is placed on `PATH`.

Next exact task:

- Phase 9 real orchestration and controlled concurrency, only after explicit user
  direction.

Do not start:

- Do not begin Phase 9 without explicit user direction.
- Do not add real orchestration, sync-worker concurrency, runtime retry/restart/fallback,
  cancellation, budgets, provider-backed persistence, evaluation corpus, or Phase 10
  work as a Phase 8 follow-up.

## 2026-07-10 - Phase 7B Search and Scraping Provider Interfaces

Current branch:

- `master`

Latest completed phase:

- Phase 7B Search and Scraping Provider Interfaces.
- Phase 8 has not started.

Files changed:

- `providers/search.py`
- `providers/scraper.py`
- `agents/supportingresearcher.py`
- `agents/opposingresearcher.py`
- `tests/test_phase7.py`
- `models.py` (freeze `SourceSnapshot` compatibility fix)
- `frontend/streamlit_app.py` (import-only compatibility fix for required Ruff checks)
- `.agent/plans/phase-07-retrieval.md`
- `STATUS.md`
- `HANDOFF.md`

Decisions made:

- Keep search and scraper vendors behind runtime-checkable synchronous Protocols and
  strict Pydantic request/response artifacts.
- Preserve the existing persisted `RetrievalRecord`; place scrape-specific status,
  content type, retry, failure, snapshot, and duplicate metadata in a new strict typed
  `RetrievalOutcome` handoff.
- Make balanced retrieval the cross-stance deduplication boundary and enforce nine
  intended attempts per side and 18 total.
- Retry timeouts according to `RetryPolicy`; fail non-timeout provider errors explicitly
  without retrying them.
- Reject malformed non-Pydantic provider responses explicitly at the provider boundary,
  and validate consistency among retrieval status, scrape status, retry metadata,
  content type, and snapshot provenance.
- Treat PDF and binary content as explicitly unsupported; accept normalized text and
  XML-family types only.
- Freeze `SourceSnapshot` as the smallest earlier-file compatibility fix required for
  immutable snapshot creation.
- Apply only an import consolidation to the Phase 7A frontend because its committed
  duplicate/misplaced imports blocked the required full-repository Ruff verification.
- Use `.agent/plans/phase-07-retrieval.md`, the canonical path in the repository
  roadmap, rather than creating the conflicting alternate plan filename from the prompt.
- Add no dependencies, real adapters, network-dependent tests, LLM behavior, prompts,
  semantic scoring, renderer behavior, async code, or Phase 8 work.

Commands run:

- Exact bare required pytest command for Phase 1 through Phase 7: failed before project
  execution with `zsh: command not found: python`.
- Exact bare required Ruff check and format commands: failed before project execution
  with `zsh: command not found: python`.
- The identical three commands with `PATH="$PWD/.venv/bin:$PATH"`: all passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: full suite passed.

Exact results:

- Required Phase 1 through Phase 7 tests: 203 passed in 2.19s.
- Full pytest suite: 209 passed in 1.98s.
- Ruff check: all checks passed.
- Ruff format check: 25 files already formatted.
- Bare exact commands: unavailable because this shell has no `python` on `PATH`.

Audit note:

- The claim that Ruff formatted 25 files was inaccurate: `ruff format --check .`
  reported that 25 files were already formatted. No repository-wide formatting-only
  changes were present or reverted.
- The frontend import-only compatibility patch was retained because the committed file
  produces seven Ruff errors; the application body is unchanged.

Known limitations:

- Bare `python` remains unavailable unless `.venv/bin` is placed on `PATH`.
- Phase 7B provides interfaces and deterministic behavior only; it does not include a
  live search or scraper vendor implementation.
- Standalone stance calls deduplicate within their own call. Use `retrieve_balanced()`
  for shared support/opposition deduplication.
- Search errors or short search result sets fail explicitly before URL-bearing records
  can be constructed for missing ranks.
- Scraper adapters must return textual content; Phase 7B does not parse raw HTML.
- Persistence wiring and full provider-backed orchestration are deferred to their
  roadmap phase.

Next exact task:

- Phase 8 LLM provider and structured prompts, only after explicit user direction.

Do not start:

- Do not begin Phase 8 without explicit user direction.
- Do not add LLM providers, prompts, live network adapters, API keys, semantic scoring,
  renderer changes, async orchestration, or later-phase behavior as Phase 7B follow-up.

## 2026-07-09 - Phase 7A Extremely Basic Local Frontend

Current branch:

- `master`

Latest completed phase:

- Phase 7A Extremely Basic Local Frontend.
- Phase 7B has not started.

Files changed:

- `frontend/streamlit_app.py`
- `frontend/README.md`
- `tests/test_phase7_frontend.py`
- `tests/test_phase0_foundation.py`
- `pyproject.toml`
- `.agent/plans/phase-07a-local-frontend.md`
- `.agent/PLANS.md`
- `README.md`
- `AGENTS.md`
- `STATUS.md`
- `HANDOFF.md`

Decisions made:

- Implement Phase 7A as a thin local Streamlit wrapper around the existing Phase 6
  `run_fixture_pipeline()` API.
- Keep helper logic pure and testable through strict Pydantic UI summary models rather
  than browser UI tests.
- Add `streamlit>=1.37,<2.0` as the only new dependency because the phase explicitly
  requires Streamlit.
- Keep output behavior delegated to the Phase 6 fixture pipeline; default UI runs use the
  fixture-local `.phase6_output/` behavior already implemented by the orchestrator.
- Do not change `orchestrator.py`, `cli.py`, Ledger validation, renderer, synthesizer,
  analyst, researcher, or planner behavior.
- Do not add live LLM calls, live retrieval, scraping, providers, React, FastAPI,
  authentication, uploads, dashboards, user accounts, database changes, Phase 7B work, or
  Phase 8 work.

Commands run:

- `git status --short --branch`: before edits, `## master...origin/master`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase7_frontend.py -q`:
  passed with 4 passed in 0.23s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase0_foundation.py tests/test_phase7_frontend.py -q`:
  passed with 6 passed in 0.19s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 188 passed in 1.73s.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 22 files
  already formatted.
- `PATH="$PWD/.venv/bin:$PATH" python -m pip install "streamlit>=1.37,<2.0"`: passed;
  Streamlit 1.59.1 was already installed in the virtual environment.
- Sandboxed `streamlit run frontend/streamlit_app.py --server.headless true --server.address 127.0.0.1 --server.port 8501`:
  failed with `PermissionError: [Errno 1] Operation not permitted` while binding to
  localhost.
- Approved local server launch with `.venv/bin/streamlit`: passed and started
  `http://127.0.0.1:8501`.
- Approved `curl -I --max-time 5 http://127.0.0.1:8501`: passed with
  `HTTP/1.1 200 OK`.

Exact results:

- Phase 7A focused tests: 4 passed.
- Phase 0 plus Phase 7A targeted tests: 6 passed.
- Full pytest suite: 188 passed.
- Ruff check: all checks passed.
- Ruff format check: 22 files already formatted.
- Local Streamlit launch: passed at `http://127.0.0.1:8501` after localhost bind
  approval.
- Localhost response check: passed with `HTTP/1.1 200 OK`.

Known limitations:

- The frontend is intentionally basic and local-only.
- The helper tests verify display data and wrapper behavior, not browser rendering.
- Phase 7A still depends entirely on fixture artifacts; it does not add live retrieval,
  scraping, LLM calls, provider-backed orchestration, uploads, dashboards, or accounts.
- Streamlit introduces local web-serving transitive packages in the environment, but no
  project web framework or HTTP-provider behavior was implemented.

Next exact task:

- Phase 7B search and scraping provider interfaces, only after explicit user direction.

Do not start:

- Do not begin Phase 7B without explicit user direction.
- Do not add live LLM calls, live retrieval, scraping, provider integrations, API-key
  reads, SDK integrations, React, FastAPI, uploads, authentication, dashboards, user
  accounts, database changes, or Phase 8 behavior as part of Phase 7A follow-up.

## 2026-07-04 - Phase 6 Fixture-Only Complete Pipeline

Current branch:

- `master`

Latest completed phase:

- Phase 6 Fixture-Only Complete Pipeline.
- Phase 7 has not started.

Files changed:

- `orchestrator.py`
- `cli.py`
- `tests/test_phase6.py`
- `tests/fixtures/basic_valid_run/`
- `tests/fixtures/invalid_release_run/`
- `.agent/plans/phase-06-fixture-pipeline.md`
- `.agent/PLANS.md`
- `STATUS.md`
- `HANDOFF.md`

Decisions made:

- Implement Phase 6 as a fixture-only coordinator around the existing typed Phase 1
  models, Phase 2 store functions, Phase 3 deterministic candidate filter, Phase 4
  Ledger admission helper, and Phase 5 renderer/validator.
- Keep fixture JSON at persistence boundaries only. Internal handoffs are Pydantic
  model instances.
- Derive Phase 6 Ledger claim IDs deterministically from run ID, Reviewer approval ID,
  approved factual statement, and a Phase 6 derivation-version string.
- Treat expected final-validator blocks as successful CLI execution with a typed
  blocked result and useful validation errors.
- Persist fixture output locally and deterministically in `.phase6_output/`, with
  idempotent output verification on rerun.
- Keep snapshots and Ledger records insert-only; reruns verify existing rows instead of
  updating or deleting them.
- Add no dependencies and do not start provider abstractions, search, scraping, LLM/API
  calls, API-key reads, async code, web frameworks, ORMs, HTTP clients, or Phase 7 work.

Commands run:

- `git status --short --branch`: before edits, `## master...origin/master` with no
  uncommitted changes.
- `git log --oneline -10`: latest commit before Phase 6 edits was
  `1cbf5c9 update files to phase-05`.
- Exact `python cli.py run-fixture tests/fixtures/basic_valid_run`: failed before
  project execution with `zsh:1: command not found: python`.
- Exact `python cli.py run-fixture tests/fixtures/invalid_release_run`: failed before
  project execution with `zsh:1: command not found: python`.
- Exact `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q`:
  failed before project execution with `zsh:1: command not found: python`.
- Exact `python -m ruff check .`: failed before project execution with
  `zsh:1: command not found: python`.
- Exact `python -m ruff format --check .`: failed before project execution with
  `zsh:1: command not found: python`.
- `PATH="$PWD/.venv/bin:$PATH" python cli.py run-fixture tests/fixtures/basic_valid_run`:
  passed and printed a released result with rendered hash
  `cfb4182d7469c05f269150605aa24907fbc850ea7f70e4e86633a9c96f60f1ed`.
- `PATH="$PWD/.venv/bin:$PATH" python cli.py run-fixture tests/fixtures/invalid_release_run`:
  passed and printed a blocked result with an `altered_statement` validation error.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase6.py -q`: passed with
  11 passed in 1.63s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q`:
  passed with 182 passed in 3.38s.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 20 files
  already formatted.

Exact results:

- Valid fixture CLI: released.
- Invalid fixture CLI: blocked, not crashed.
- Phase 6 focused tests: 11 passed.
- Phase 1 through Phase 6 tests: 182 passed.
- Ruff check: all checks passed.
- Ruff format check: 20 files already formatted.

Known limitations:

- Bare `python` is still unavailable unless `.venv/bin` is placed on `PATH`.
- Phase 6 is fully offline and fixture-only; it does not execute live retrieval,
  scraping, LLM calls, or provider-backed orchestration.
- The fixture pipeline proves deterministic wiring and validation behavior, not live
  semantic research quality.

Next exact task:

- Phase 7 search and scraping provider interfaces, only after explicit user direction.

Do not start:

- Do not begin Phase 7 without explicit user direction.
- Do not add live network calls, search providers, scrapers, LLM providers, API-key
  reads, SDK integrations, async orchestration, web frameworks, ORMs, or HTTP clients as
  part of Phase 6 follow-up.

## 2026-07-04 - Post-Phase-5 Documentation State Audit

Current branch:

- `master`

Latest completed phase:

- Phase 5 Synthesizer Schema, Renderer, and Release Validator.
- Phase 6 has not started.

Files changed in this audit:

- `README.md`
- `AGENTS.md`
- `DECISIONS.md`
- `STATUS.md`
- `HANDOFF.md`
- `.agent/PLANS.md`
- `.agent/plans/phase-00-foundation.md`
- `.agent/plans/phase-04-ledger-admission.md`
- `.agents/PLANS/phase-00-foundation.md`

Work completed:

- Audited the current docs, phase plans, `agents/`, and `tests/` after the Phase 5 commits.
- Fixed stale current-state wording that still said Phase 3 was latest and Phase 4 had not
  started.
- Added current Phase 5 project-state guidance to the canonical plan index.
- Added durable Phase 4 and Phase 5 decision entries.
- Confirmed `.agent/plans/` is the intended source of truth. `.agents/PLANS/` was left in
  place as a compatibility mirror and not consolidated or deleted.
- Replaced the mirror file's stale absolute Windows path with the canonical relative plan
  path.
- Confirmed active deterministic modules are `models.py`, `store.py`, `utils.py`,
  `agents/researcher.py`, `agents/analyst.py`, `agents/reviewer.py`,
  `agents/synthesizer.py`, and `agents/renderer.py`.
- Confirmed `agents/planner.py`, `agents/supportingresearcher.py`, and
  `agents/opposingresearcher.py` remain placeholders for later roadmap phases.
- Made no implementation, test, dependency, or Phase 6 behavior changes.

Commands run:

- `git status --short`: clean before audit edits.
- `git log --oneline --decorate -n 8`: latest commits were `64d0408 phase-05 fix` and
  `378d58a phase-05`.
- `git diff dfa57af..HEAD --name-only`: confirmed Phase 5 changed seven tracked files.
- `python -m pytest`: failed because this shell does not have `python` on `PATH`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 173 passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 17 files already
  formatted.

Known limitations:

- Plain `python` is unavailable unless `.venv/bin` is placed on `PATH`.
- No Phase 6 fixture pipeline, orchestration, CLI, live retrieval, scraping, LLM/API calls,
  provider integrations, SDK integrations, web frameworks, ORMs, or HTTP clients exist.

Next exact task:

- Phase 6 fixture-only complete pipeline, only after explicit user direction.

Do not start:

- Do not begin Phase 6 without explicit user direction.
- Do not add real search providers, scrapers, LLM providers, network calls, live API keys,
  or external provider integrations.

## 2026-07-04 - Phase 5 Verification Pass

Current branch:

- `master`

Latest completed phase:

- Phase 5 Synthesizer Schema, Renderer, and Release Validator.
- Phase 6 has not started.

Files changed in this verification pass:

- `agents/synthesizer.py`
- `agents/renderer.py`
- `tests/test_phase5.py`
- `STATUS.md`
- `HANDOFF.md`
- `.agent/plans/phase-05-release-gate.md`

Work completed:

- Verified the original Phase 5 commit touched exactly the files documented in the Phase
  5 plan and handoff.
- Confirmed the renderer only produces final text through the validation gate and uses
  fixed approved templates plus exact Ledger factual statements and source URLs.
- Confirmed the validator enforces Ledger claim ID, Reviewer approval ID, exact
  statement, placement, stance, entailment, section compatibility, template
  compatibility, and one-use-per-Ledger-claim checks.
- Added narrow regression tests for raw dictionary Ledger handoffs and empty approved
  Ledger statements.
- Tightened the synthesizer to reject non-`LedgerRecord` inputs with a clear exception.
- Tightened the final validator to reject non-`LedgerRecord` inputs and malformed
  `LedgerRecord` instances with typed invalid validation results and no rendered hash.

Commands run:

- `git status --short --branch`: clean before verification edits.
- `git log --oneline --decorate -10`: latest commit before this pass was
  `378d58a phase-05`.
- `git show --stat --oneline --name-only HEAD`: confirmed Phase 5 changed seven files.
- `git diff dfa57af..HEAD --name-only`: confirmed Phase 5 changed seven files.
- Exact `python -m pytest`: failed because this shell did not have `python` on `PATH`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 170 passed in 1.08s
  before the verification patch.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed before the verification
  patch.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed before the
  verification patch.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase5.py -q`: passed with
  24 passed in 0.10s after the verification patch.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 173 passed in 0.74s after
  the verification patch.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed after the verification
  patch.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed after the
  verification patch.

Known limitations:

- Plain `python` is unavailable unless `.venv/bin` is placed on `PATH`.
- Template compatibility is deterministic configuration, not semantic review.
- Source citations are still deterministic URL inclusions only.
- No provider abstractions, real LLM/API calls, retrieval, scraping, fixture pipeline,
  orchestration, CLI, dependencies, or Phase 6 behavior were added.

Next exact task:

- Phase 6 fixture-only complete pipeline, only after explicit user direction.

Do not start:

- Do not begin Phase 6 without explicit user direction.
- Do not add provider abstractions, real search, scraping, real LLM calls, SDK
  integrations, live network calls, API keys, or external provider integrations.

## 2026-07-03 - Phase 5 Synthesizer Schema, Renderer, and Release Validator

Current branch:

- `master`

Latest completed phase:

- Phase 5 Synthesizer Schema, Renderer, and Release Validator.
- Phase 6 has not started.

Files changed:

- `agents/synthesizer.py`
- `agents/renderer.py`
- `tests/test_phase5.py`
- `tests/fixtures/phase5_expected_valid_brief.txt`
- `.agent/plans/phase-05-release-gate.md`
- `STATUS.md`
- `HANDOFF.md`

Decisions made:

- Implement Phase 5 as deterministic typed helpers and a release validator around the
  existing Phase 1 `SynthesisOutput`, `LedgerRecord`, and `ValidationResult` models.
- Keep the fixed approved non-factual connective template registry in
  `agents/renderer.py` as strict Pydantic configuration artifacts.
- Build synthesis output only from typed `LedgerRecord` instances and copy Ledger IDs,
  Reviewer approval IDs, stance, placement, entailment, and approved factual statements
  exactly.
- Render only after validation succeeds. Invalid releases return typed
  `ValidationResult(valid=False, rendered_brief_hash=None)`.
- Enforce one final rendered use per Ledger claim in Phase 5.
- Treat `qualified_only`, Partial entailment, and Weak entailment as requiring approved
  qualification or warning templates.
- No model or SQLite schema change was needed. No dependencies were added.
- No LLM calls, retrieval, scraping, provider integrations, fixture pipeline,
  orchestration, CLI, external dependencies, async code, or Phase 6 work was added.

Commands run:

- `git status --short --branch`: before edits, `## master...origin/master`.
- `git log --oneline -10`: latest commit before Phase 5 edits was `dfa57af phase-04`.
- `python -m pytest tests/test_phase5.py -q`: first run failed only on the intentional
  hash placeholder; final run passed with 21 passed in 0.12s.
- `python -m ruff check .`: passed after import cleanup, all checks passed.
- `python -m ruff format --check .`: passed, 17 files already formatted.
- `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py -q`:
  passed with 168 passed in 0.73s.
- `python -m ruff check .`: final required run passed, all checks passed.
- `python -m ruff format --check .`: final required run passed, 17 files already
  formatted.

Exact results:

- Phase 5 focused tests: 21 passed in 0.12s.
- Required Phase 1-5 tests: 168 passed in 0.73s.
- Ruff check: all checks passed.
- Ruff format check: 17 files already formatted.

Known limitations:

- Template compatibility is deterministic configuration, not semantic review.
- Source citations are rendered mechanically from Ledger `source_url` values.
- The synthesizer helper is deterministic and fixture-oriented; it is not an LLM-backed
  synthesizer and does not orchestrate a complete run.

Next exact task:

- Phase 6 fixture-only complete pipeline.

Do not start:

- Do not begin Phase 7 or later work.
- Do not add real search providers, scrapers, LLM providers, live network calls, API
  keys, or external provider integrations as part of Phase 6.

## 2026-07-03 - Phase 4 Analyst Rules, Reviewer Rules, and Ledger Admission

Current branch:

- `master`

Latest completed phase:

- Phase 4 Analyst Rules, Reviewer Rules, and Ledger Admission.
- At that handoff time, Phase 5 had not started.

Files changed:

- `agents/analyst.py`
- `agents/reviewer.py`
- `tests/test_phase4.py`
- `.agent/plans/phase-04-ledger-admission.md`
- `STATUS.md`
- `HANDOFF.md`

Decisions made:

- Implement Phase 4 as deterministic typed helper surfaces around existing Pydantic
  models rather than changing the model or SQLite schema.
- Keep the explicit 25-row Evidence Quality and Claim Fit score-pair policy in
  `agents/analyst.py`.
- Reconstruct `LedgerRecord` values from the candidate, snapshot, Analyst decision,
  reviewed draft, and Reviewer approval instead of accepting caller-supplied Ledger
  fields.
- Reuse Phase 3 `verify_candidate_against_snapshot()` before Ledger admission so hash
  and offset re-verification are both required.
- Treat Claim Fit 3, `qualified_only`, Partial entailment, and Weak entailment as
  requiring explicit qualification markers before Ledger admission.
- Keep Reviewer behavior fixture-driven and deterministic. No LLM calls, provider
  integrations, retrieval, rendering, final validator, orchestration, async code, or
  new dependencies were added.

Commands run:

- `git status --short --branch`: `## master...origin/master` before Phase 4 edits.
- `git log --oneline -10`: latest commit before Phase 4 edits was `272c7bf phase-03 fix`.
- `python -m pytest tests/test_phase4.py -q`: failed because `python` is not available
  on PATH.
- `python3 -m pytest tests/test_phase4.py -q`: failed because the system Python did not
  have `pytest` installed.
- `/Users/francischen/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pytest tests/test_phase4.py -q`:
  failed because the bundled interpreter did not have `pytest` installed.
- `/Users/francischen/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv .venv`:
  passed.
- `.venv/bin/python -m pip install -e '.[dev]'`: first failed because sandboxed DNS
  blocked package-index access; after approval, failed because editable package
  discovery is not configured for the current flat layout.
- `.venv/bin/python -m pip install 'pydantic>=2.0,<3.0' 'python-dotenv>=1.0,<2.0' 'pytest>=8.0,<9.0' 'ruff>=0.8,<1.0'`:
  passed, installing only dependencies already declared in `pyproject.toml`.
- `.venv/bin/python -m pytest tests/test_phase4.py -q`: first run found one adversarial
  test construction issue; final run passed with 43 passed in 0.20s.
- `.venv/bin/python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q`:
  passed with 147 passed in 0.87s before documentation updates and 147 passed in
  0.91s after documentation updates.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m ruff format --check .`: passed.
- Exact required command
  `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q`:
  initially failed with `zsh:1: command not found: python`; after the session-local
  `python` launcher was restored, passed with 147 passed in 0.82s, then 147 passed in
  0.74s after documentation updates.
- Exact required command `python -m ruff check .`: initially failed with
  `zsh:1: command not found: python`; after the launcher was restored, passed.
- Exact required command `python -m ruff format --check .`: initially failed with
  `zsh:1: command not found: python`; after the launcher was restored, passed.

Known limitations:

- Qualification checks are deterministic marker checks, not semantic judgment.
- Reviewer approval is represented by typed fixtures/checks only; real Reviewer LLM
  calls are still out of scope.
- Plain `python` now resolves through a session-local temporary launcher and the exact
  `python -m ...` checks pass. If Codex creates a new temporary PATH directory later,
  that launcher may need to be restored.
- Editable installation is blocked by current flat-layout package discovery. This was
  not changed because Phase 4 does not require packaging work.

Next exact task:

- Phase 5 Synthesizer schema, renderer, and release validator.

Do not start:

- Do not begin Phase 5 or later work without explicit user direction.
- Do not add LLM calls, retrieval, scraping, provider integrations, orchestration,
  rendering, final validation, async code, or external dependencies as part of Phase 4.

## 2026-06-27 - Documentation Consistency Pass After Phase 3

Current branch:

- `master`

Latest completed phase:

- Phase 3 Snapshot and Quotation Integrity.
- At that handoff time, Phase 4 had not started.

Latest important commits:

- `2661eeb plan`
- `298b711 phase-03`
- `23caf22 phase-02 fix`
- `cff9c0e phase 02 fix`
- `2e80edb phase-01`
- `d854df3 phase-00complete`

Files changed by recent phases:

- Phase 3: `utils.py`, `agents/researcher.py`, `tests/test_phase3.py`, `.agent/plans/phase-03-snapshot-integrity.md`, `.agent/PLANS.md`, `STATUS.md`, and `HANDOFF.md`.
- Roadmap/documentation alignment: `.agent/PLANS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `STATUS.md`, and `HANDOFF.md`.
- This consistency pass: documentation files only.

Commands run:

- `git branch --show-current`: `master`.
- `git status --short`: only documentation files modified, plus the local `.pytest_cache/` permission warning.
- `git status --porcelain=v1 -uno`: clean before this pass.
- `git log --oneline -10`: latest commit was `2661eeb plan`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: failed because it would reformat existing code/test files outside this documentation-only pass: `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`.
- `.\.venv\Scripts\python.exe -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q`: 104 passed, one local `.pytest_cache` permission warning.
- `git diff --stat`: documentation files only.
- `git diff --name-only`: documentation files only.

Current known limitations:

- Sentence-boundary detection is deterministic and intentionally simple for MVP quote integrity.
- The local `.pytest_cache` directory may emit a permission warning during pytest or Git scans.
- Ruff format currently reports pre-existing formatting drift in `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`; those files were not modified during this documentation-only pass.

Next exact task:

- Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.

Do not start:

- Do not begin Phase 5 or later work.
- Do not implement Phase 4 during documentation-only passes.
- Do not create `agents/analyst.py` or `agents/reviewer.py` until Phase 4 is explicitly requested.

## 2026-06-27 - Documentation Roadmap Alignment

Current branch:

- `master`
- Attempted to create `docs/phase-roadmap`, but Git could not create the branch ref in this session.

Files changed:

- `.agent/PLANS.md`
- `ARCHITECTURE.md`
- `CONVENTIONS.md`
- `STATUS.md`
- `HANDOFF.md`

Work completed:

- Added the full Phase 0-10 roadmap to `.agent/PLANS.md`.
- Added a short architecture note clarifying that architecture defines invariants while phase sequencing lives in `.agent/PLANS.md` and `.agent/plans/`.
- Added a short conventions note clarifying phase-gated development and required pre-edit checks.
- Confirmed at that time that Phase 3 was complete and Phase 4 had not started.

Commands run:

- `git branch --show-current`: `master`.
- `git status --short`: clean except a permission warning when Git inspected `.pytest_cache/`.
- `git status --porcelain=v1 -uno`: clean.
- `git log --oneline -10`: latest commit was `298b711 phase-03`.
- `git branch --list docs/phase-roadmap`: no local branch found.
- `git switch -c docs/phase-roadmap`: failed because Git could not create `.git/refs/heads/docs/phase-roadmap`.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: failed because it would reformat existing code files outside this documentation-only pass: `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`.

Scope review:

- Documentation-only pass.
- No code files changed.
- No dependencies added.
- No Analyst rules, Reviewer rules, Ledger admission, rendering, orchestration, retrieval, scraping, LLM provider work, or evaluation work was started.
- `.agent/PLANS.md` now contains the Phase 0-10 roadmap.

Next exact task:

- Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.

## 2026-06-27 - Phase 3 Snapshot and Quotation Integrity

Current branch:

- `master`

Files changed:

- `utils.py`
- `agents/researcher.py`
- `tests/test_phase3.py`
- `.agent/PLANS.md`
- `.agent/plans/phase-03-snapshot-integrity.md`
- `STATUS.md`
- `HANDOFF.md`

Work completed:

- Implemented deterministic SHA-256, word-count, and quote-block UUID5 helpers.
- Added `agents/researcher.py` as the shared deterministic post-extraction filter surface for future supporting and opposing researchers.
- Added strict typed helper artifacts: `ParsedQuoteBlock`, `QuoteMetrics`, and `PostExtractionFilterResult`.
- Implemented `build_source_snapshot()` and `validate_snapshot_integrity()` for recomputing snapshot hash and word count from `normalized_text`.
- Implemented bracketed quote parsing, sequential exact segment matching, offset recording, immediate bracket-context validation, boundary-marker validation, statistical marker detection, claim-keyword matching, and architecture-defined quote length thresholds.
- Implemented `filter_provisional_candidate()` so invalid provisional candidates return a typed rejection result and never receive a `CandidateQuoteBlock` or `quote_block_id`.
- Implemented `verify_candidate_against_snapshot()` as a deterministic re-check function future Analyst code can call. It does not score evidence, create Analyst decisions, call a Reviewer, or admit anything to the Ledger.
- Added adversarial Phase 3 coverage for invalid quote blocks, segment/order failures, context failures, snapshot integrity failures, boundary-marker misuse, threshold edges, statistical marker rules, missing keywords, repeated text disambiguation, ellipsis word counts, deterministic IDs, and tampered offsets.
- During final self-review, fixed statistical marker substring matching so incidental words such as `corporate` cannot satisfy the `rate` marker, and added a pre-ID metadata validation guard for filter version and validation timestamp.
- Documented Phase 3 in `.agent/plans/phase-03-snapshot-integrity.md` and updated the phase-plan index.

Commands run:

- `. .\.venv\Scripts\Activate.ps1; python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q`: failed because PowerShell script execution is disabled and `python` is not on PATH.
- `cmd /c ".venv\Scripts\activate.bat && python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q"`: 104 passed, one local `.pytest_cache` permission warning.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format agents\researcher.py`: reformatted one file after the initial format check requested changes.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: passed.

Known limitations:

- Sentence-boundary detection is deterministic and intentionally simple for Phase 3. It handles the MVP test cases but is not a full NLP sentence segmenter.
- The local `.pytest_cache` directory still causes a permission warning during pytest.
- Verification used the virtual environment's Python executable directly because activation was blocked and `python` is not on PATH. `PYTHONPATH` was not set.

Scope review:

- Phase 1 models, Phase 2 store code, and the SQLite schema were not changed.
- No retrieval, scraping, LLM calls, SDK integrations, Analyst scoring, Reviewer logic, Ledger admission, synthesis, rendering, final validation, orchestration, web frameworks, ORMs, HTTP clients, or Phase 4 work was implemented.
- Tests assert that rejected post-extraction filter results have `candidate is None`, so invalid cases do not receive a candidate ID.

Next exact task:

- Phase 4 only after explicit user direction.

## 2026-06-27 - Post-Phase-2 Hardening

Current branch:

- `master`

Files changed:

- `AGENTS.md`
- `STATUS.md`
- `HANDOFF.md`
- `.agent/plans/phase-02-store.md`
- `store.py`
- `tests/test_phase1.py`
- `tests/test_phase2.py`

Work completed:

- Performed a narrow post-Phase-2 hardening pass without beginning Phase 3.
- Strengthened `AGENTS.md` with explicit rules against destructive Git commands without user instruction, undocumented deletion of protected docs/plans, weakening tests, and beginning the next phase.
- Documented the strict internal Pydantic artifact default: `model_config = ConfigDict(extra="forbid")` unless a specific exception is documented.
- Confirmed all internal artifact models in `models.py` already inherit `StrictModel`; no model redesign was needed.
- Added representative regression tests proving unknown extra fields are rejected for `LedgerRecord`, `SynthesisItem`, `SynthesisSection`, `SynthesisOutput`, `ValidationError`, `ValidationResult`, `CandidateQuoteBlock`, `SourceSnapshot`, and `ModelInvocationRecord`.
- Added a SQLite `schema_migrations` table in `init_db()` and an idempotent version 1 record for the Phase 2 initial schema.
- Added Phase 2 tests proving the schema migration table and initial record exist after database initialization.
- Reviewed Phase 1 and Phase 2 implementation for later-phase scope creep.
- Updated `STATUS.md` and `.agent/plans/phase-02-store.md` with post-phase hardening notes.

Commands run:

- `git branch --show-current`: `master`
- `git status --short`: reported the existing `.pytest_cache` permission warning.
- `rg -n "requests|httpx|aiohttp|beautifulsoup|bs4|selenium|playwright|openai|anthropic|LLM|scrape|retriev|render|orchestrat|integrity|sha256|hash|Snapshot Integrity|Final Renderer|async def|sqlite3\\.connect\\(|UPDATE |DELETE |reset --hard|clean -fd|force-push|force push" .`: reviewed for scope creep and destructive-command references.
- `pytest tests/test_phase1.py tests/test_phase2.py -q`: first attempt failed collection because the sandbox import path did not include the workspace root.
- `PYTHONPATH=C:\Users\fchen\ResearchAssistant pytest tests/test_phase1.py tests/test_phase2.py -q`: 81 passed, one `.pytest_cache` permission warning.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Known limitations:

- Snapshot `snapshot_sha256` and `word_count` still are not recomputed from `normalized_text` at model construction. This remains deferred to Phase 3, where snapshot and quotation integrity should be defined precisely.
- The local `.pytest_cache` directory still causes a permission warning during pytest and git status scans.
- No threaded SQLite concurrency test exists yet; Phase 2 still enforces no global connections by design through per-call connections.

Scope review:

- No retrieval implementation, scraper, LLM provider, orchestration, renderer behavior, or Phase 3 snapshot-integrity implementation was found.
- No later-phase code was removed because no later-phase implementation was present.
- Phase 3 was not started.

Next exact task:

- Phase 3 snapshot and quotation integrity.

## 2026-06-26 - Phase 2 Hardening

Work completed:

- Performed a narrow Phase 2 hardening and cleanup pass without beginning Phase 3.
- Updated `ARCHITECTURE.md` and `CONVENTIONS.md` for the two-axis eligibility rule, derived `ledger_score`, and Claim Fit 2 clarification.
- Implemented deterministic scoring helpers in `models.py`.
- Added `ledger_score` to `ScoreDecision` and `LedgerRecord`.
- Enforced score eligibility, derived Ledger score, and placement consistency in `ScoreDecision` and `LedgerRecord`.
- Strengthened `PlannerOutput`, `StatementReviewResult`, and `ValidationResult` validators.
- Added SQLite foreign keys for clear architecture-defined artifact relationships:
  planner queries to retrieval attempts, retrieval attempts to snapshots, snapshots/retrieval attempts to candidates, candidates to analyst decisions and statement drafts/reviews, approved reviews to Ledger records, and Ledger records to synthesis items.
- Added `read_statement_draft()` to the store API.
- Updated tests for all changed validators and store constraints.
- Updated README phase text, Phase 2 plan notes, and the `HANDbOFF.md` typo in the Phase 0 plan.

Verification:

- `pytest`: 73 passed; one local `.pytest_cache` permission warning remains.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Tracked issues:

- Snapshot `snapshot_sha256` and `word_count` validation against `normalized_text` is still deferred. Do this when snapshot normalization and hashing behavior are implemented precisely; do not guess the normalization rules in the model layer.
- The local `.pytest_cache` directory still causes a permission warning.

Important constraints:

- Stop at Phase 2 unless the user explicitly requests Phase 3.
- Do not implement web retrieval, scraping, LLM calls, orchestration, renderer logic, SDK integrations, web frameworks, ORMs, HTTP clients, or real agent behavior yet.
- At Phase 2 close, agent modules remained placeholders.
- Internal handoffs must continue to use Pydantic model instances, not raw dictionaries.
- Claim Fit 2 records must not enter the final Ledger.

Safe to continue:

- Yes, after explicit user direction for Phase 3.

## 2026-06-26 - Phase 2 Store

Work completed:

- Implemented the SQLite persistence layer in `store.py` with `init_db()` containing all schema definitions for 19 tables.
- Created append-only storage for runs, planner outputs, planner queries, retrieval attempts, snapshots, provisional extractions, candidates, analyst decisions, statement review attempts, ledger records, synthesis attempts, validation runs, and model invocations.
- All functions accept explicit `db_path` parameters; no global connections.
- Read functions return Pydantic models; write functions accept Pydantic models.
- Snapshots and Ledger records are INSERT-ONLY with no update or delete functions.
- Multi-write operations use explicit transactions with rollback on failure.
- Fixed `_validate_aware_datetime` in `models.py` to handle `None` for optional datetime fields.
- Added `tests/test_phase2.py` with 36 tests covering all required scenarios.
- Added `.agent/plans/phase-02-store.md` and updated `.agent/PLANS.md`.
- Updated `STATUS.md` for Phase 2.

Important constraints:

- Stop at Phase 2 unless the user explicitly requests Phase 3.
- Do not implement web retrieval, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients yet.
- Continue passing Pydantic model instances between internal stages; do not pass raw dictionaries except at persistence, API, logging, or export boundaries.
- Preserve the separate `evidence_quality` and `claim_fit` fields; do not add any composite evidence score.
- Concurrent researcher workers must each open their own connections; this is enforced by design but not yet tested under threading.

Verification:

- `pytest tests/test_phase2.py`: 36 passed.
- `pytest tests/`: 54 passed (Phase 0: 2, Phase 1: 16, Phase 2: 36).
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Open issue:

- Verification used the local `.venv` created in Phase 1.

Next expected phase:

- Phase 3 should begin only after explicit user direction and should implement retrieval logging and web search integration.

## 2026-06-26 - Phase 1 Models

Work completed:

- Implemented the Phase 1 Pydantic v2 model layer in `models.py`.
- Added strict construction-time validation for Phase 1 contract requirements, including score bounds, required reviewer approval for approved Ledger records, timezone-aware timestamps, source/snapshot provenance, ordered non-overlapping offsets, exact Ledger statement fields, and synthesis section stance compatibility.
- Added `tests/test_phase1.py` with valid and invalid model construction coverage.
- Added `.agent/plans/phase-01-models.md` and updated `.agent/PLANS.md`.
- Updated `STATUS.md` for Phase 1.

Important constraints:

- Stop at Phase 1 unless the user explicitly requests Phase 2.
- Do not implement database operations, web retrieval, scraping, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients yet.
- Continue passing Pydantic model instances between internal stages; do not pass raw dictionaries except at persistence, API, logging, or export boundaries.
- Preserve the separate `evidence_quality` and `claim_fit` fields; do not add any composite evidence score.

Verification:

- `pytest tests/test_phase1.py`: 16 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Open issue:

- The direct `pytest`, `python`, and `ruff` commands were not available on PATH. I created a local `.venv` with only the already-declared project/dev dependencies to run verification. The sandbox blocked recursive cleanup, so `.venv/` remains as an untracked local tooling directory.

Next expected phase:

- Phase 2 should begin only after explicit user direction and should build on the typed contracts without introducing raw-dictionary handoffs.

## 2026-06-26 - Phase 0 Foundation

Work completed:

- Documented the Phase 0 architecture corrections requested by the user.
- Added the repository scaffold needed for reliable AI-assisted development.
- Configured `pyproject.toml` for Python 3.11+, Pydantic v2, python-dotenv, pytest, and Ruff.
- Added a Phase 0 scaffold/configuration test.
- Verified the phase with `pytest`, `ruff check .`, and `ruff format --check .`.

Important constraints:

- Do not begin Phase 1 without explicit user instruction.
- Do not implement working agents, SQLite behavior, web retrieval, scraping, LLM calls, SDK integrations, ORMs, web frameworks, or HTTP libraries yet.
- Future assistants must read `ARCHITECTURE.md` and `CONVENTIONS.md` completely before editing.
- Internal handoffs must use Pydantic model instances, not raw dictionaries.

Open issue:

- No blocking Phase 0 issue remains. `.agent/plans/phase-00-foundation.md` is the canonical plan; `.agents/PLANS/phase-00-foundation.md` is only a compatibility pointer.

Next expected phase:

- Phase 1 should start only after the user explicitly requests it. It should begin with schemas and artifact-store design as described in `ARCHITECTURE.md`, without weakening the Phase 0 constraints.
