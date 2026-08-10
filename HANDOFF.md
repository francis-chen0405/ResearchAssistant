# Handoff

## 2026-08-09 - MVP-6.6 Runtime Status, Budget, and Contract Integrity

- MVP-6.6 is complete and verified; MVP-6.7 and repository-wide type-hint work have not
  started. RUNNING is exit 13 across direct CLI results, read-only inspection,
  subprocesses, and live-web snapshots. Exit 0 never means nonterminal research;
  `cancel-run` retains its separate persisted-administrative-success meaning.
- `ModelUsageAccounting` is the typed authority for exact totals, known subtotals,
  completeness, missing-attempt IDs, and conservative exposure. `ProviderPipelineResult`
  retains `total_tokens` and `total_cost_usd` only as exact compatibility fields: zero
  for zero attempts and `None` when incomplete.
- Every persisted model attempt is conservatively potentially charge-capable. Exact
  component usage replaces its reservation; missing component usage retains its full
  reservation. No failure string or terminal state implies a free call. Retry/fallback
  stops when incomplete unreserved usage makes remaining budget unprovable.
- `provider_contract.py` is the single standard-library canonical identity algorithm.
  Both factories use it, and the frozen `ProviderRunContract` validates exact keys,
  duplicate-free canonical JSON, duplicated identities, repository revision, and
  SHA-256 on creation/read. Stored inconsistency is never normalized or repaired and
  blocks resume before provider work.
- Valid historical canonical payloads retain compatibility because payload inputs and
  fingerprint-version strings did not change. Runtime source changes still alter the
  normal executable repository identity, and `provider_contract.py` is included in that
  source hash.

Files changed:

- Runtime/contracts: `cli.py`, `models.py`, `orchestrator.py`, `provider_contract.py`,
  `store.py`, `providers/factory.py`, `providers/mimo_factory.py`.
- Live display: `frontend/live_service.py`, `frontend/live_app.py`.
- Regression coverage: `tests/test_mvp6_6_runtime_integrity.py`,
  `tests/test_mvp3a_pipeline.py`, `tests/test_mvp5_live_web.py`.
- Phase/operator documentation: `.agent/PLANS.md`, the canonical MVP-6.6 plan,
  `AGENTS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `DECISIONS.md`, `README.md`,
  `frontend/README.md`, `STATUS.md`, and `HANDOFF.md`.

Verification handoff:

- Required focused selection: 143 passed, 1 expected opt-in skip.
- Full suite: 578 passed, 2 expected opt-in skips.
- Offline evaluation: 38/38 passed; optional live comparison skipped.
- Ruff lint/format, 61-file in-memory compilation, launcher syntax, CLI help,
  `git diff --check`, and final source/diff/artifact audits passed.
- No dependency, SQLite migration, provider call, spending, generated tracked artifact,
  commit, or MVP-6.7/type-hint work was added.

Known limitation:

- Historical incomplete usage without a defensible stored reservation remains readable
  but fails closed before another budgeted call; no historical usage is fabricated.
  Exa and Firecrawl charges remain external to MiMo model accounting.

Do not start:

- Do not begin MVP-6.7 or the remaining repository-wide type-hint phase without separate
  explicit direction.

## 2026-08-09 - MVP-6.5 Immutable Run Authority and Read-Only Inspection

- MVP-6.5 is complete and verified; MVP-6.6 has not started. SQLite migration 5 is
  `database-enforced immutable runs.raw_claim`. Migration 4 is accurately limited to
  same-run provenance protection.
- `store.py` installs `runs_raw_claim_immutable` atomically. It is a
  `BEFORE UPDATE OF raw_claim ON runs` trigger with
  `WHEN NEW.raw_claim IS NOT OLD.raw_claim`; every actual claim change aborts with
  `runs.raw_claim is immutable`, regardless of status or direct-SQL caller. Identical
  assignments remain valid. `update_run()` retains its earlier application guard.
- `ReadOnlyStore` is the inspection/history boundary. It opens a safely encoded existing
  path with URI `mode=ro`, foreign keys, `sqlite3.Row`, and connection-local
  `query_only`; it deliberately does not use `immutable=1`. The compatibility check
  validates integrity, migration rows 1-5, required objects, and exact trigger semantics.
- Compatibility failures distinguish missing, invalid, older, newer, corrupt, and open/
  permission cases. Inspection never creates or migrates. To migrate an older database,
  intentionally start or resume a writable run; the normal `init_db()` path upgrades it.
- `inspect_provider_run` reuses one read-only session for manifest, checkpoints, attempts,
  artifacts, synthesis, validation, cancellation reason, and released-hash reconstruction.
  CLI contract display, live history, and live contract display also use read-only
  sessions. Missing history retains the empty tuple contract without creating a file.

Files changed:

- Store/runtime: `store.py`, `orchestrator.py`, `cli.py`, `frontend/live_service.py`.
- Regression coverage: `tests/test_mvp6_5_read_only_inspection.py`, `tests/test_phase9.py`.
- Phase records and operator documentation: `.agent/PLANS.md`, the canonical MVP-6.5
  plan, `AGENTS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `DECISIONS.md`, `README.md`,
  `frontend/README.md`, `STATUS.md`, and `HANDOFF.md`.

Verification handoff:

- Focused required selection: 206 passed, 1 expected opt-in skip.
- Full suite: 543 passed, 2 expected opt-in skips.
- Offline evaluation: 38/38 passed; optional live comparison skipped.
- Ruff lint/format, Python compilation, launcher syntax, `git diff --check`, direct
  schema/trigger inspection, migration record review, and before/after database-hash
  comparison passed.
- No dependency, ORM, provider call, spending, committed fixture mutation, generated
  database/cache/coverage artifact, or commit was added.

Known limitation:

- Public-target validation and transport DNS remain separate as documented in MVP-6.3;
  MVP-6.5 does not change that acquisition limitation. Read-only inspection supports
  active WAL writers but does not promise a multi-query snapshot across a writer's
  separate commits beyond ordinary SQLite read-transaction semantics.

Do not start:

- Do not begin MVP-6.6 or the CLI-status, usage-accounting, provider-contract, or
  type-hint batches without separate explicit direction.

## 2026-08-09 - MVP-6.4 Evidence Density Threshold Calibration

- MVP-6.4 is complete and verified; MVP-6.5 has not started. Current provider-backed
  evidence requires 50 exact quoted words only when both a digit and a recognized
  statistical marker are present, and 75 otherwise. Digit-only, marker-only, and
  incidental-substring cases use 75.
- `agents/researcher.py` owns the strict current policy
  `mvp6.4-evidence-density-50-75-v1`. Its existing whole-token, case-insensitive marker
  classification feeds both initial filtering and downstream verification. Analyst and
  Ledger paths share that same default policy.
- Frozen fixture replay explicitly injects `legacy-frozen-fixture-50-100-v1`; this is
  isolated compatibility behavior, not a current provider option. Historical runs and
  fixtures are not rewritten or reinterpreted.
- `prompts/extractor.md` and the direct MiMo compatibility instruction require exact
  source text, 50 words only for digit-plus-marker evidence, 75 otherwise, no healing or
  expansion, and authoritative Python validation.
- Identity values: Extractor prompt `mvp6.4-extractor-50-75-v1`; prompt SHA-256
  `a4f95d7468e22f6e95961d409ed7f99910ffe911b1a1788fb409b64bfc9725eb`;
  aggregate prompt identity
  `49cc02aee6025c4d2bf4a50b8ccfd97a23cb896f15ff8ecb650704ad45db33a2`;
  provider post-filter validator `mvp6.4-provider-post-filter-50-75-v1`; provider
  fingerprint version `mvp6.4-evidence-density-fingerprint-v1`.
- Exact fingerprint matching prevents a 75/75 run from resuming under 50/75. Restart
  the launcher/application and use a new run ID. Historical inspection remains tied to
  the persisted identity.
- Reviewer approval, literal entailment, material qualification, Ledger admission,
  renderer policy, and deterministic final validation are unchanged.

Files changed:

- Policy and downstream identity: `agents/researcher.py`, `orchestrator.py`, `providers/factory.py`,
  `providers/mimo_factory.py`.
- Prompt behavior: `prompts/extractor.md`, `providers/mimo.py`.
- Regression coverage: `tests/test_phase3.py`, `tests/test_phase4.py`,
  `tests/test_phase8.py`, `tests/test_mvp3b_mimo.py`,
  `tests/test_mvp3a_pipeline.py`.
- Phase records: `.agent/PLANS.md`, the canonical MVP-6.4 plan, `AGENTS.md`,
  `ARCHITECTURE.md`, `CONVENTIONS.md`, `DECISIONS.md`, `README.md`, `STATUS.md`, and
  `HANDOFF.md`. Historical Phase 3/MVP-5 plans received explicit supersession labels.

Verification handoff:

- Focused role/integrity/release/fingerprint/fixture selection: 240 passed, 1 expected
  opt-in skip.
- Full suite: 517 passed, 2 expected opt-in skips.
- Offline evaluation: 38/38 passed.
- Ruff lint/format, Python compilation, launcher syntax, `git diff --check`, tracked
  stale-policy review, dependency/migration review, generated-artifact review, and final
  diff review passed.
- No provider call or spend occurred. No dependency or SQLite migration was added. No
  generated cache/coverage artifact is tracked. Changes are uncommitted.

Do not start:

- Do not begin MVP-6.5 or the database, read-only inspection, CLI-status,
  usage-accounting, provider-contract, or type-hint batches without separate explicit
  direction.

## 2026-08-09 - MVP-6.3 Public Acquisition and Provenance Security

- MVP-6.3 is complete and verified; no later phase has started. The scope was limited to
  redirect-time local acquisition safety, Firecrawl provenance validation, compatible
  identity changes, regression tests, and documentation.
- `providers/acquisition.py` now uses an explicit no-auto-follow redirect loop. It
  validates the initial URL and every proposed next hop through the injectable resolver
  before sending, permits exactly the configured number of 301/302/303/307/308 hops,
  closes every response, rejects malformed locations/loops, and passes only the final
  validated URL to Wigolo.
- `providers/firecrawl.py` validates the direct request URL before the provider call and
  validates returned `sourceURL` and recognized canonical metadata before constructing
  provenance. Absent `sourceURL` uses only the already validated request URL. Unsafe or
  malformed provenance fails with typed secret-free errors.
- The existing fallback allowlist remains narrow. Authentication, paywall, access,
  content/policy, size, and redirect-safety failures cannot activate Firecrawl.
- New identities are `mvp6.3-public-acquisition-v2`,
  `mvp6.3-firecrawl-provenance-v2`, and
  `mvp6.3-public-acquisition-fingerprint-v2`. Acquisition identity is included in exact
  run fingerprints, so pre-MVP-6.3 runs require a new run ID and historical artifacts
  remain unchanged.
- DNS validation is a pre-request policy check, not socket pinning. `httpx` resolves for
  transport separately, and Wigolo performs its own fetch; do not describe the result as
  complete DNS-rebinding protection.

Files changed:

- Provider behavior/identity: `providers/acquisition.py`, `providers/firecrawl.py`,
  `providers/config.py`, `providers/factory.py`, `providers/mimo_factory.py`.
- Regression compatibility: `tests/test_mvp6_3_security.py`,
  `tests/test_mvp2b_providers.py`, `tests/test_post_mvp5_retrieval.py`,
  `tests/test_mvp3a_pipeline.py`.
- Phase documentation: `.agent/PLANS.md`, the canonical MVP-6.3 plan, `AGENTS.md`,
  `ARCHITECTURE.md`, `CONVENTIONS.md`, `DECISIONS.md`, `README.md`,
  `frontend/README.md`, `STATUS.md`, and `HANDOFF.md`.

Verification handoff:

- Focused security/provider/persistence selection: 159 passed.
- Full suite: 501 passed, 2 expected opt-in skips.
- Offline evaluation: 38/38 passed.
- Ruff lint/format, Python compilation, launcher syntax, and `git diff --check` passed.
- All new security tests use injected transports and resolvers. No provider call or
  spend occurred. No dependency or SQLite migration was added. Generated cache and
  coverage artifacts are absent from the repository worktree. Changes are uncommitted.

Do not start:

- Do not begin MVP-6.4 or any database, accounting, evidence-policy, provider-contract,
  CLI-status, usage-accounting, or type-hint batch without separate explicit direction.

## 2026-08-09 - MVP-6.2 Batch A Records and Runtime Reporting

- MVP-6 (`37c52a7`, `6e0f434`) and MVP-6.1 (`c10c844`) are completed committed work.
  MVP-6.2 is current, but only Batch A was authorized and implemented. The later
  security, database, accounting, evidence-policy, and model-contract batches remain
  pending approval/implementation; MVP-6.2 is not complete, and no later phase started.
- Current new-run identity is Exa Search `auto` for metadata-only discovery, pinned
  loopback Wigolo `0.2.1` for primary acquisition, optional narrowly gated Firecrawl
  fallback, and direct Xiaomi `mimo-v2.5-pro` for every LLM role. Native SearXNG remains
  only in clearly historical compatibility records and adapters for old persisted runs.
- The CLI launch summary now prints the configured Exa, Wigolo, and MiMo endpoints and
  an explicit Firecrawl enabled/disabled state plus its configured endpoint when
  enabled. It never prints keys. Focused tests cover both fallback states and secret
  absence from output and SQLite.
- Package metadata now describes the MVP-6.2 system. README verification documentation
  names both normal opt-in skips. `.coverage` is deleted from tracking and ignored; its
  prior binary is recoverable from Git history.
- Verification passed: focused CLI 13 passed/1 expected skip; full suite 469 passed/2
  expected skips; offline evaluation 38/38; Ruff lint/format; launcher shell syntax;
  and `git diff --check`.
- No provider call or spending occurred. No dependency or database migration was added.
  Changes remain uncommitted.

## 2026-08-09 - MVP-6.1 Live Worker Test Fix (`c10c844`)

- Completed committed work: the live-worker redaction test waits within a bounded loop
  for the background result rather than racing the initial starting snapshot.
- The accidentally committed `.coverage` output is not part of the phase contract and
  is removed by MVP-6.2 Batch A.

## 2026-08-01 - MVP-6 Post-Audit Boundary Corrections (`6e0f434`)

- Verified Python-normalized digital PDFs now continue into immutable source snapshots without
  falsifying their content type. Unnormalized PDF payloads still fail closed.
- The obsolete 40-second aggregate acquisition deadline was removed. The approved per-operation
  preflight, HTML, PDF, and browser deadlines remain in force.
- Candidate verification itself enforced the then-current MVP-6 75-word minimum; the direct MiMo prompt
  also says 75 rather than 100.
- Live display redaction covers the raw values and assignment labels for MiMo, Exa, and Firecrawl
  keys.
- The direct orchestration boundary rejects leading/trailing claim whitespace rather than silently
  trimming the authoritative claim.
- Package metadata now matches the tested Python 3.11 and 3.12 support range.
- Acquisition rejects non-public initial URLs, DNS answers, and redirect targets.
- Claims are immutable after run creation; inspection recomputes the released brief hash; SQLite
  migration 4 rejects cross-run parent references.
- Direct MiMo returns semantic content only. Python constructs all application-owned identity,
  timestamps, provenance, score routing, and templates. No quote or metadata healing remains.
- One live worker may use a given SQLite database at a time; separate database files can still
  run concurrently.
- `python-dotenv` was removed. Configuration is read from the explicit process environment and
  `.env` files are never loaded automatically.
- Verification: 468 passed and 2 skipped; 38/38 offline evaluations; Ruff lint/format,
  launcher syntax, and diff checks passed.
- No live provider call occurred. The unused dotenv dependency was removed and migration 4
  added same-run integrity triggers as committed MVP-6 work.

## 2026-08-01 - MVP-6 Bounded-Inference Evidence Policy (`37c52a7`)

- New runs use a 75-word minimum for all exact quote candidates.
- Claim Fit 5 is Strong/direct, Claim Fit 4 is Partial/indirect, and Claim Fit 3 is
  Weak/contextual. Reviewer approval still requires the factual statement itself to be
  literally entailed and qualified; it no longer requires that fact to independently
  prove the entire debated claim.
- One-sided released briefs carry a deterministic not-balanced warning naming the
  missing stance. No-Ledger runs still fail rather than releasing an empty brief.
- Prompt, validator, renderer, and evidence-policy identities changed, so the launcher
  must be restarted and the next run must leave Run ID blank.
- Frozen fixture replay explicitly retains its historical 50-statistical/100-
  non-statistical threshold; this compatibility route is not used by new live runs.
- Follow-up live-run correction: Claim Fit 4 Partial evidence relies on the deterministic
  indirect renderer connective and does not require a magic qualification keyword. Claim
  Fit 3, qualified-only, and Weak statements remain explicitly qualification-gated.
  Failure stage is set before stage execution, and per-stance model-attempt counts are
  joined through persisted snapshot/candidate IDs instead of generic stage-name text.
- Evidence policy identity is now `post-mvp5-bounded-inference-v2`; restart and use a new
  run ID. The failed v1 run must not be resumed under v2.
- This policy correction was committed as part of MVP-6. No dependency or SQLite
  migration was added.
- Verification: 461 passed and 2 skipped in the full suite; 38/38 offline evaluations;
  Ruff lint/format, launcher syntax, and diff checks passed. No live call or spend
  occurred.

## 2026-08-01 - MVP-6 Exa/Wigolo/Firecrawl Provider Correction (`37c52a7`)

- New direct-MiMo runs now use Exa Search `auto` for metadata-only discovery, pinned
  Wigolo `0.2.1` for primary acquisition, and optional Firecrawl v2 scrape fallback.
- Required process secrets are `MIMO_API_KEY` and `EXA_API_KEY`.
  `FIRECRAWL_API_KEY` is optional. The click launcher prompts for all three without
  persistence; leaving Firecrawl blank disables fallback without disabling research.
- Firecrawl is attempted only after Wigolo-local connection, timeout, malformed,
  extraction, or challenge failures. It is never attempted for authentication, paywall,
  access-denied, unsupported-content, size, redirect, or source-side failures.
- The Wigolo child no longer receives native-SearXNG launch settings and never inherits
  provider secrets. Existing historical Wigolo/SearXNG adapters/tests remain for prior
  artifact compatibility, but the direct-MiMo factory constructs Exa discovery.
- The provider/adapter/policy fingerprint includes Exa, Wigolo, and Firecrawl-enabled
  identity. Old SearXNG runs require their historical executable identity; ordinary use
  should start a new run ID.
- Verification: 14 new provider tests; 451 passed and 2 skipped full suite; 38/38 offline
  evaluations; Ruff lint/format, launcher syntax, and diff checks passed. No live call or
  spend occurred.
- This correction was committed as part of MVP-6 and added no dependency or SQLite
  migration.

## 2026-08-01 - MVP-5 Polished Local Live Web Interface

Current branch and state:

- `master`; all MVP-5 changes are intentionally uncommitted.
- MVP-5 is complete. The obsolete scheduled-validation placeholder is superseded. MVP-6
  is not authorized.

Operator surface:

- macOS: double-click `Launch ResearchAssistant.command`. With no inherited key, a native
  hidden-input dialog requests `MIMO_API_KEY` for that server process only. Streamlit
  opens on loopback and its Terminal/server process must remain running.
- `frontend/live_app.py` is the live website. It controls exact claim, explicit budgets,
  optional run ID, SQLite location, local service health/start/owned stop, live persisted
  progress, cancellation, history, inspection, and released brief/hash/download.
- `frontend/streamlit_app.py` remains fixture-only and is explicitly labeled as using no
  MiMo, Wigolo, live search, or credentials.
- Live identity remains pinned Wigolo `0.2.1` plus native SearXNG and direct Xiaomi
  `mimo-v2.5-pro`. No `.env` or shell profile is loaded.

Lifecycle, restart, and cancellation:

- The live controller directly calls the stable MVP-4 application service in a background
  worker. SQLite is authoritative. A process-local registry and per-database `flock`
  prevent duplicate workers across reruns, sessions, and local processes.
- Start stack runs exactly `npx -y wigolo@0.2.1 serve` with loopback/native-SearXNG
  environment. Health verifies exact identity; output is bounded/redacted. Stop sends
  termination only to the application-owned process group, including at server exit.
- Same run ID still requires byte-exact claim and exact provider/model/prompt/schema/
  adapter/normalization/policy/budget/repository fingerprint. Budget or identity changes
  require a new run. Consumed usage is never reset.
- Released, blocked, and cancelled runs reconstruct without calls. Failed runs may resume
  only under the exact same contract. Cancellation is persisted and cooperative; an
  active request may finish or reach its deadline, then no new call starts.
- Status/exit mapping is released `0`, blocked `10`, failed `11`, cancelled `12`,
  configuration error `20`, invalid input `21`.

Security:

- The browser and Streamlit session state never receive the MiMo key. The key is absent
  from URLs, SQLite, subprocess arguments, launcher arguments, logs, downloaded briefs,
  and rendered errors. Provider and child-process errors pass through bounded redaction.
- The Wigolo child receives only a small allowlisted environment and never inherits
  `MIMO_API_KEY`. User-selected existing database files must have a valid SQLite header.
- Claims remain public/non-sensitive and all released output requires human review.
- The confirmation is checked after form submission so Streamlit form batching cannot
  leave a correctly configured user trapped behind a permanently disabled button; an
  unchecked confirmation stops before run creation or provider spend.

Files changed:

- `.agent/PLANS.md`, `.agent/plans/phase-mvp-5-scheduled-live-validation.md`
- `.gitignore`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `DECISIONS.md`, `README.md`,
  `STATUS.md`, `HANDOFF.md`
- `frontend/README.md`, `frontend/streamlit_app.py`, `frontend/live_app.py`,
  `frontend/live_service.py`, `frontend/security.py`, `frontend/service_manager.py`
- `store.py`, `tests/test_mvp5_live_web.py`, `Launch ResearchAssistant.command`

Verification handoff:

- Focused MVP-5: 17 passed. Full suite: 437 passed, 2 skipped.
- Offline evaluation: 38 passed. Fixture release/block, mocked released live-web reopen,
  restart/cancellation subprocess, secret scans, child ownership/cleanup, browser visual
  smoke, Ruff lint/format, launcher syntax, and `git diff --check` passed.
- Clean Python 3.12.13 installed requirements and imported the live surface with
  Streamlit 1.60.0. Python 3.11 was unavailable locally but remains in CI. Node.js
  24.18.0 and npm/npx 11.16.0 were present.
- Optional real live web test was not approved/run; additional live cost is zero.

Known limitations:

- Initial dependency/Wigolo resource installation remains a setup step. Native SearXNG
  cold/degraded searches may still exceed the unchanged 15-second deadline.
- The local Streamlit server must remain alive. Cancellation is cooperative and arbitrary
  cross-version crash recovery is unsupported. Cost is estimated.
- No hosted UI, accounts, authentication, uploads, Docker, scheduling, or MVP-6 work.

Do not start:

- Do not begin MVP-6, scheduled validation, hosting, authentication, another provider,
  or a timeout-policy change without explicit user direction.

## 2026-08-01 - MVP-4 Usable Live CLI and MVP Release

Current branch and state:

- `master`; all MVP-4 changes are intentionally uncommitted.
- MVP-4 is complete. MVP-5 is not authorized.

Operator surface:

- `python cli.py run EXACT_CLAIM --db-path PATH --max-tokens N --max-cost-usd USD`
  launches the approved loopback Wigolo `0.2.1` plus direct Xiaomi
  `mimo-v2.5-pro` stack. `--run-id` is optional and `--max-llm-calls` defaults to 160.
- Required live secret: `MIMO_API_KEY`. Optional approved defaults are exposed through
  `MIMO_BASE_URL`, `MIMO_MODEL`, and loopback `WIGOLO_BASE_URL`. No `.env` is loaded.
- `inspect-run DATABASE RUN_ID` prints the authoritative audit and release reconstruction.
  `cancel-run DATABASE RUN_ID` persists cancellation for a running process.
- Exit codes: released `0`, blocked `10`, failed `11`, cancelled `12`, configuration
  error `20`, invalid input `21`.

Restart/cancellation contract:

- Same run ID requires the byte-exact claim and exact provider/model/prompt/schema/adapter/
  normalization/policy/budget/repository fingerprint. Any budget change requires a new
  run ID; usage is never reset.
- Released, blocked, and cancelled runs reconstruct without calls. Failed runs may resume
  with the exact same fingerprint and reuse valid checkpoints/attempts without duplicating
  snapshots, Ledger records, validation, or release artifacts.
- Cancellation is cooperative. A second process can persist it during an active request;
  that request may finish or reach its deadline, is recorded, and no later call starts
  after observation.

Verification handoff:

- Focused MVP-4: 12 passed, 1 skipped. Full suite: 420 passed, 2 skipped.
- Offline evaluation: 38 passed. Ruff lint/format, diff check, fixture smokes, mocked live
  CLI smoke, restart/inspection/redaction, and second-process cancellation passed.
- Clean Python 3.12.13 runtime installation, CLI help, and imports passed. Python 3.11 was
  unavailable locally but remains in the unchanged supported CI matrix.
- Optional live CLI smoke: not approved, not run, zero additional live cost.

Known limitations:

- Operators must bootstrap/warm native SearXNG and run pinned Wigolo on loopback. Process
  lifecycle is external; cold/degraded Search can fail its fixed deadline.
- MiMo cost is estimated. Public/non-sensitive claims and human review remain mandatory.
- The Streamlit app is still fixture-only. No production web UI, hosting, accounts, or
  scheduled validation was added.

Do not start:

- Do not begin MVP-5, modify Streamlit into a live UI, add providers, hosting, accounts,
  or scheduled live work without explicit user direction.

## 2026-07-31 - MVP-3B Full Live-Canary Stabilization

Current branch:

- `master`
- All MVP-3B changes are intentionally uncommitted.

Latest completed phase:

- MVP-3B is complete. A direct-MiMo positive canary released, its final hash and brief
  reconstructed from SQLite, and the controlled negative canary failed safely.

Live evidence:

- Positive: `For adults with hypertension, regular aerobic exercise lowers resting
  systolic blood pressure.` Run `2eb99893-b919-40c9-b5b8-b482b61e1c57`, terminal state
  `released`, 6 Search / 13 acquisition / 9 snapshot / 34 physical LLM calls, 145,738
  tokens, estimated USD 0.080223, valid final output, hash
  `4f17c54f0b2d475552266026d5b6c0dd84b91a0044c1e60970dfc2e9526551ba`.
- Negative: `The Moon is Earth's only natural satellite.` Run
  `4defb64a-1fe2-4249-b67f-fb61cd4a2974`, terminal state `failed` at the Researcher
  boundary, 6 Search / 29 acquisition / 12 snapshot / 1 physical LLM call, 3,255 tokens,
  estimated USD 0.0025555. The one-call ceiling was consumed by Planner; subsequent
  Extractor calls failed closed and no candidate reached the Ledger.
- Both databases reconstructed, remained inside their approved ceilings, and contained no
  MiMo credential. No accepted canary made an OpenRouter or MiniMax call.

Implementation handoff:

- `providers/mimo.py` is the direct Xiaomi JSON-mode adapter. Exact Pydantic validation
  remains mandatory; deterministic normalization is limited to application-owned identity,
  provenance, score-pair routing fields, approved connective templates, and exact text found
  in the immutable snapshot.
- `providers/wigolo.py` sends native `exclude_domains`, serializes calls for the local
  SearXNG process, and retains strict 15-second balanced Search behavior.
- Supporting/opposing live workers share one locked deduplication state, preventing
  cross-stance duplicate URLs/content from producing conflicting immutable snapshots.
- Direct-MiMo Analyst routing is derived from the fixed score-pair table after MiMo supplies
  semantic quality/fit scores; stance compatibility is explicit and an independent Reviewer
  still controls factual admission.
- StatementDraft and synthesis connective identities are stamped from their immutable input
  candidates/Ledger records; semantic draft text and approved factual statements are never
  healed or rewritten.

Verification:

- Focused provider/mocked integration/restart/cancellation tests: 108 passed.
- Full offline suite: 408 passed, 1 skipped.
- Offline evaluation: all 38 cases passed.
- Ruff lint, Ruff format, `git diff --check`, persistence reconstruction, and secret scans
  passed.

Known limitations and CLI suitability:

- Native SearXNG must be bootstrapped with Python 3.10+ before Wigolo starts. On this Mac,
  `/usr/bin/python3` 3.9 was incompatible; Python 3.12.13 bootstrapped successfully.
- Core-only Wigolo can collapse to one engine and return unrelated results. The successful
  canary used `WIGOLO_SEARCH=searxng`, `SEARXNG_MODE=native`, loopback port 3333, and an
  already warmed sidecar. A cold balanced probe exceeded 15 seconds; a warmed probe passed.
- Wigolo process ownership and SearXNG preflight are not implemented in this phase. They are
  requirements for a usable live CLI, not permission to begin MVP-4.
- MiMo cost is conservatively estimated from frozen pricing; billing confirmation is external.

Do not start:

- Do not add the live CLI, modify Streamlit, redesign orchestration, add another provider,
  or begin MVP-4 without explicit user approval.

## 2026-07-24 - MVP-3A Mocked Full-Provider Pipeline Integration

Current branch:

- `master`
- Changes are intentionally uncommitted.

Latest completed phase:

- MVP-3A is complete offline. No live provider call was made.

Implementation handoff:

- `providers/factory.py` is the sole configured construction boundary. Its frozen strict
  models validate Wigolo `0.2.1`, OpenRouter, all five MiMo Pro primary routes,
  MiniMax M3 as the only fallback, explicit temperatures, strict structured output,
  usage support, exact price-cap coverage, rank-five/keep-three acquisition, hard
  ceilings, and a caller-supplied repository revision.
- `run_mvp3a_pipeline()` constructs that bundle and delegates to
  `run_provider_pipeline()` with strict reservation and fingerprint enforcement. The
  existing direct injection surface remains available for older offline Phase 9 tests.
- Immutable configuration and thread-safe HTTP clients are shared. Wigolo Search locks
  health verification, OpenRouter uses thread-local call metadata, acquisition has no
  mutable per-request state, and each worker opens only short-lived SQLite connections.
- `ProviderRunContract` and SQLite migration 3 persist exact provider/adapter/model/
  prompt/schema/normalization/PDF/acquisition/retry/budget/pricing/repository/policy
  identity. A changed claim or incompatible fingerprint is rejected.
- `ModelRouteAttempt` now persists conservative token/cost reservation as well as exact
  usage. Reservations are atomic; completed exact usage replaces the active reservation
  in subsequent budget calculations. Failed, malformed, and locally rejected responses
  retain reported usage.
- The approved route is exactly primary, primary retry, fallback, fallback retry for
  objective failures. Semantic Reviewer disagreement still performs the one allowed
  revision and does not route.
- Cancellation is checked before/after Search, acquisition, and LLM calls and at stage
  boundaries. An in-flight synchronous request may finish; no immediate-interruption
  claim is made.
- Released and blocked terminal reinvocations return reconstructed persistence without
  new calls. Failed runs may resume only with the same claim/fingerprint. Cancelled runs
  remain terminal. Valid checkpoints, attempts, budgets, snapshots, Ledger records, and
  released output are not duplicated.

Verification:

- MVP-2B prerequisite: 40 passed.
- Focused MVP-3A: 16 passed.
- Full suite: 382 passed, 1 skipped.
- The remaining skip is explicitly opt-in; no live gate was enabled.
- Offline evaluation: all 38 cases passed; optional live comparison was skipped.
- Fixture CLI smokes: valid released with hash
  `7fecea19e1b9f01ff3fe68ef9a2b3a79cf88f0a6fe82897332548c258cb9e89f`;
  invalid blocked with no hash.
- Mocked full-pipeline smoke: passed.
- Ruff lint/format and `git diff --check`: passed. Final Git status showed only the
  intended uncommitted MVP-3A files.

Remaining risks:

- Exact live response compatibility, upstream identity, current price/cost reporting,
  and real deadline behavior remain MVP-3B work.
- The caller must provide an exact trustworthy repository revision for a live run.
- Cancellation remains cooperative around blocking synchronous HTTP deadlines.

Do not start:

- Do not run a live canary, add a live CLI, modify Streamlit, add another provider or
  browser path, or begin MVP-3B without explicit user direction.

## 2026-07-22 - MVP-2B Production Provider Adapters and Boundary Proof

Current branch:

- `master`
- Changes are intentionally uncommitted.

Latest completed phase:

- MVP-2B is complete offline. No live provider call was made.

Implementation handoff:

- `providers/wigolo.py` is the thread-safe discovery-only Search adapter. It verifies loopback
  Wigolo identity/version, sends the fixed five-result/no-fetch request, preserves provider/rank /
  telemetry metadata, removes duplicate URLs after their first rank, and raises secret-safe typed
  failures.
- `providers/acquisition.py` independently preflights original/final/canonical URL and media type,
  streams under approved caps, uses direct Wigolo extraction first, and permits one controlled
  rendered retry only after an explicit challenge/JavaScript-required status.
- `providers/normalization.py` owns `ra-normalization-v1` and `ra-digital-pdf-v1`; every quote
  offset refers to its final normalized text. PDF support is digital embedded text only, without
  OCR.
- `providers/openrouter.py` performs exactly one physical call. It sends the exact requested
  Pydantic JSON Schema in strict mode, rejects wrapper/fenced/malformed/truncated/refused output,
  records exact model/upstream/usage/cost metadata, and exposes typed usage to existing callers.
- `providers/config.py` contains strict deadlines, caps, loopback/HTTPS validation, full-run
  ceilings, and live-smoke gates. OpenRouter secrets come only from an explicitly provided process
  environment mapping and remain redacted.
- `providers/pricing.py` uses a dated conservative upper cap of USD 5/M input and USD 20/M output
  for both approved models. Provider-reported cost wins; otherwise the result is explicitly marked
  estimated. Unknown models/prices fail before a call.
- Default routing is now MiMo Pro then MiniMax M3 for every stage. Legacy enum aliases remain only
  for persisted compatibility and frozen historical quality evaluation.
- The standalone boundary smoke is `scripts/mvp2b_live_smoke.py`; it is not a product CLI command.
  Do not execute it without separate explicit approval for that exact run.

Verification:

- Focused MVP-2B: 40 passed.
- Full offline suite: 366 passed, 1 skipped.
- Offline evaluation: all 38 cases passed; approved default-route agreement is 100%.
- Live smoke: not run. Live observed calls, usage, and cost are therefore unavailable.

Known incompatibilities and next-phase cautions:

- Exact live Wigolo `0.2.1` payload compatibility remains to be proven by the approved smoke. The
  adapter accepts documented `results`, engine telemetry, fetch `status`, and Markdown/content
  fields and rejects malformed variants rather than guessing.
- A managed Node/Wigolo child-process lifecycle is not wired. The adapter requires and verifies an
  already running pinned loopback service; do not add lifecycle or product commands in MVP-3A
  unless its phase explicitly authorizes them.
- The new provenance is not persisted in SQLite because the user prohibited a migration. Keep it
  in typed boundary artifacts until a separately approved exact migration exists.
- The stack is suitable for MVP-3A mocked integration. It is not yet live-production proven.

Do not start:

- Do not run the live smoke, connect full orchestration, add a live CLI/UI, modify Streamlit, add a
  migration/provider/browser path, or begin MVP-3A without explicit user direction.

## 2026-07-21 - MVP-2A Architecture Gate

Current branch:

- `master`
- Changes are intentionally uncommitted.

Latest completed phase:

- MVP-2A Architecture Gate, documentation only.
- MVP-2B implementation has not started.

Approved primary design:

- Use pinned local Wigolo `0.2.1` for discovery and controlled source acquisition. A
  future ResearchAssistant process manager owns startup/health/identity/shutdown; users
  should not manually enter searches or operate a separate normal-run terminal.
- Search is discovery metadata only. Make six balanced discovery calls, rank five URLs
  per query, and attempt them until three usable unique snapshots exist. Search snippets,
  scores, evidence fields, and generated summaries never become source snapshots.
- Fetch directly first and allow one Chromium-rendered retry only for explicit challenge
  or JavaScript-required outcomes. No authentication, clicks, typing, profiles, or
  general browser automation.
- Support ordinary extracted HTML/text and a narrow digital-PDF path. Reject scanned,
  encrypted, malformed, empty, oversized/timed-out, or unusably extracted PDFs without
  OCR.
- Independently classify origin media type, preserve original/final/advisory-canonical
  URLs, deterministically normalize provider content to immutable 3,000-word plain-text
  snapshots, and make exact Python-verified offsets reference only that stored text.
- Use OpenRouter for all LLM calls: `xiaomi/mimo-v2.5-pro` primary for Planner,
  Extractor, Analyst, Reviewer, and Synthesizer; `minimax/minimax-m3` as the only fallback.
  Require strict JSON Schema and local exact Pydantic revalidation.
- Retry only objective failures: primary, primary retry, fallback, fallback retry. All
  physical calls share one run budget; reserve conservatively before calls, reconcile
  exact usage after, retain usage on failures, and fail closed on unknown price/route.
- Public/non-sensitive claims only. Configure OpenRouter data collection denied and
  prompt logging off. Keep `OPENROUTER_API_KEY` out of Wigolo, logs, SQLite, checkpoints,
  and exports; bind Wigolo to loopback.
- Resume only when repository/provider/adapter/model/prompt/schema/acquisition/
  normalization/PDF/retry/budget/pricing fingerprints match exactly.

Current-versus-approved warning:

- Current code and tests still implement fixed top-three retrieval, PDF unsupported,
  and the earlier MiMo/DeepSeek alias route. MVP-2A deliberately did not change them.
  MVP-2B must migrate these contracts explicitly and add regression tests; do not treat
  documentation completion as runtime completion.

Future implementation dependencies and limits requiring approval:

- Proposed dependencies: `httpx` and `markdown-it-py`; Node.js and Wigolo `0.2.1` are
  runtime prerequisites. No LLM SDK is proposed.
- Proposed hard maximum per live canary/run: USD 1.00, 1,000,000 tokens, 160 physical LLM
  calls, six searches, thirty acquisition candidates, and eighteen Extractor snapshots.
- Proposed response caps: 10 MiB HTML/text, 25 MiB PDF. Proposed deadlines are in the
  canonical plan.
- `.env.example` changes, live CLI/UI behavior, and any SQLite migration also require
  explicit approval.

Canonical details:

- `.agent/plans/phase-mvp-2a-architecture-gate.md` contains the two-stack evaluation,
  exact request policy, calls/costs, failures, normalization/PDF contract, data handling,
  deadlines, canary evidence, proof plan, acceptance criteria, and approval list.

Verification:

- Full pytest: 310 passed, 1 skipped; the skip is the existing optional live Phase 8
  integration gate and no live option was enabled.
- Ruff check passed; Ruff format check reported 34 files already formatted.
- `git diff --check` passed. Only documentation and assistant-governance files changed;
  no provider, dependency, environment template, schema, code, or test file changed.

Do not start:

- Do not add dependencies, providers, API keys, network-dependent tests, migrations,
  process management, live commands, or any MVP-2B code without explicit user direction
  and the approvals listed above.

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
